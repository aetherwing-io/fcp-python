"""Mutation dispatcher and handlers."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from fcp_core import VerbRegistry, parse_op, suggest, ParseError

from fcp_python.lsp.types import (
    CodeAction,
    WorkspaceEdit,
)
from fcp_python.lsp.workspace_edit import apply_workspace_edit, ApplyResult
from fcp_python.resolver.selectors import (
    SelectorType,
    parse_line_range,
    parse_selector,
)

from .format import (
    format_code_action_choices,
    format_disambiguation,
    format_error,
    format_mutation_result,
)
from .model import PythonModel
from .query import resolve_with_fallback


async def dispatch_mutation(
    model: PythonModel,
    registry: VerbRegistry,
    input_str: str,
) -> str:
    """Dispatch a mutation operation string to the appropriate handler."""
    op = parse_op(input_str)
    if isinstance(op, ParseError):
        return format_error(f"parse error: {op.error}", None)

    if registry.lookup(op.verb) is None:
        verb_names = [v.verb for v in registry.verbs]
        suggestion = suggest(op.verb, verb_names)
        return format_error(f"unknown verb '{op.verb}'.", suggestion)

    if model.lsp_client is None:
        return format_error("no workspace open. Use python_session open PATH first.", None)

    match op.verb:
        case "rename":
            return await handle_rename(model, op.positionals, op.selectors)
        case "extract":
            return await handle_extract(model, op.positionals, op.selectors)
        case "import":
            return await handle_import(model, op.positionals, op.selectors)
        case _:
            return format_error(f"verb '{op.verb}' is not a mutation.", None)


async def ensure_file_synced(model: PythonModel, uri: str) -> None:
    """Open a file in LSP if not already open, to sync with disk."""
    client = model.lsp_client
    if client is None:
        return
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return
    path = Path(unquote(parsed.path))
    text = path.read_text()
    await client.did_open(uri, text)


async def sync_after_edit(model: PythonModel, result: ApplyResult) -> None:
    """After applying a WorkspaceEdit, sync all changed files with LSP."""
    for uri, _ in result.files_changed:
        await ensure_file_synced(model, uri)
    for uri in result.files_created:
        await ensure_file_synced(model, uri)


def file_uri(model: PythonModel, file_value: str) -> str:
    """Build a file URI from a selector value, using model root as base."""
    if file_value.startswith("file://"):
        return file_value
    return f"{model.root_uri.rstrip('/')}/{file_value}"


# -- rename ---------------------------------------------------------------

async def handle_rename(
    model: PythonModel,
    positionals: list[str],
    selectors: list[str],
) -> str:
    if len(positionals) < 2:
        return format_error("rename requires SYMBOL and NEW_NAME.", None)
    old_name = positionals[0]
    new_name = positionals[1]

    parsed_selectors = [s for s in (parse_selector(sel) for sel in selectors) if s is not None]
    resolved = await resolve_with_fallback(model, old_name, parsed_selectors)

    if resolved.is_ambiguous:
        return format_disambiguation(old_name, resolved.entries)
    if resolved.is_not_found:
        return format_error(f"symbol '{old_name}' not found.", None)
    entry = resolved.entry

    client = model.lsp_client
    assert client is not None

    params = {
        "textDocument": {"uri": entry.uri},
        "position": {
            "line": entry.selection_range.start.line,
            "character": entry.selection_range.start.character,
        },
        "newName": new_name,
    }

    try:
        raw_edit = await client.request("textDocument/rename", params)
    except Exception as e:
        return format_error(f"rename failed: {e}", None)

    if raw_edit is None:
        return format_error("rename returned no edit.", None)

    workspace_edit = WorkspaceEdit.from_dict(raw_edit)
    try:
        result = apply_workspace_edit(workspace_edit)
    except Exception as e:
        return format_error(f"failed to apply rename: {e}", None)

    return format_mutation_result(
        "rename", f"{old_name} → {new_name}", result, model.root_uri
    )


# -- extract ---------------------------------------------------------------

async def handle_extract(
    model: PythonModel,
    positionals: list[str],
    selectors: list[str],
) -> str:
    if not positionals:
        return format_error("extract requires FUNC_NAME.", None)
    func_name = positionals[0]

    parsed_selectors = [s for s in (parse_selector(sel) for sel in selectors) if s is not None]

    file_sel = next((s for s in parsed_selectors if s.selector_type == SelectorType.FILE), None)
    lines_sel = next((s for s in parsed_selectors if s.selector_type == SelectorType.LINES), None)

    if file_sel is None:
        return format_error("extract requires @file:PATH selector.", None)
    if lines_sel is None:
        return format_error("extract requires @lines:N-M selector.", None)

    line_range = parse_line_range(lines_sel.value)
    if line_range is None:
        return format_error(
            f"invalid line range '{lines_sel.value}'. Use @lines:N-M.", None
        )
    start_line, end_line = line_range

    uri = file_uri(model, file_sel.value)
    # Convert 1-indexed user lines to 0-indexed LSP
    lsp_start = start_line - 1 if start_line > 0 else start_line
    lsp_end = end_line - 1 if end_line > 0 else end_line

    client = model.lsp_client
    assert client is not None

    try:
        await ensure_file_synced(model, uri)
    except Exception as e:
        return format_error(f"extract: {e}", None)

    params = {
        "textDocument": {"uri": uri},
        "range": {
            "start": {"line": lsp_start, "character": 0},
            "end": {"line": lsp_end, "character": 999},
        },
        "context": {
            "diagnostics": [],
            "only": ["refactor.extract.function", "refactor.extract"],
            "triggerKind": 1,
        },
    }

    try:
        raw_actions = await client.request("textDocument/codeAction", params)
    except Exception as e:
        return format_error(f"extract failed: {e}", None)

    if not raw_actions:
        raw_actions = []

    actions = [CodeAction.from_dict(a) for a in raw_actions]
    extract_actions = [
        a for a in actions
        if a.kind and a.kind.startswith("refactor.extract")
    ]

    if not extract_actions:
        return format_error("no extract action available for the selected range.", None)

    if len(extract_actions) == 1:
        action = extract_actions[0]
    else:
        # Prefer "Extract into function" over others
        func_action = next(
            (a for a in extract_actions if "function" in a.title.lower()), None
        )
        if func_action:
            action = func_action
        else:
            preferred = next((a for a in extract_actions if a.is_preferred), None)
            if preferred:
                action = preferred
            else:
                return format_code_action_choices(extract_actions)

    if action.edit is None:
        return format_error("extract action has no edit.", None)

    try:
        apply_result = apply_workspace_edit(action.edit)
    except Exception as e:
        return format_error(f"failed to apply extract: {e}", None)

    # Sync changed files
    try:
        await sync_after_edit(model, apply_result)
    except Exception:
        pass

    # Follow-up rename: pylsp/rope generates a placeholder name.
    rename_result = await _follow_up_rename(model, uri, func_name)

    if rename_result is not None:
        return format_mutation_result("extract", func_name, rename_result, model.root_uri)
    return format_mutation_result("extract", func_name, apply_result, model.root_uri)


async def _follow_up_rename(
    model: PythonModel,
    uri: str,
    desired_name: str,
) -> ApplyResult | None:
    """After extract, rename the generated function to the user's desired name."""
    client = model.lsp_client
    if client is None:
        return None

    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    path = Path(unquote(parsed.path))
    try:
        content = path.read_text()
    except Exception:
        return None

    # Rope generates "extracted_function" or similar placeholder names
    for generated_name in ["extracted_function", "extracted_method", "extracted_variable"]:
        fn_pattern = f"def {generated_name}"
        byte_offset = content.find(fn_pattern)
        if byte_offset >= 0:
            name_offset = byte_offset + 4  # "def ".len()
            line = content[:name_offset].count("\n")
            last_newline = content.rfind("\n", 0, name_offset)
            col = name_offset - (last_newline + 1) if last_newline >= 0 else name_offset

            params = {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": col},
                "newName": desired_name,
            }
            try:
                raw_edit = await client.request("textDocument/rename", params)
                if raw_edit:
                    workspace_edit = WorkspaceEdit.from_dict(raw_edit)
                    return apply_workspace_edit(workspace_edit)
            except Exception:
                pass
            break

    return None


# -- import ---------------------------------------------------------------

async def handle_import(
    model: PythonModel,
    positionals: list[str],
    selectors: list[str],
) -> str:
    if not positionals:
        return format_error("import requires SYMBOL.", None)
    symbol_name = positionals[0]

    parsed_selectors = [s for s in (parse_selector(sel) for sel in selectors) if s is not None]

    file_sel = next((s for s in parsed_selectors if s.selector_type == SelectorType.FILE), None)
    line_sel = next((s for s in parsed_selectors if s.selector_type == SelectorType.LINE), None)

    if file_sel is None:
        return format_error("import requires @file:PATH selector.", None)
    if line_sel is None:
        return format_error("import requires @line:N selector.", None)

    try:
        line_num = int(line_sel.value)
    except ValueError:
        return format_error("invalid line number.", None)

    uri = file_uri(model, file_sel.value)
    lsp_line = line_num - 1 if line_num > 0 else line_num

    client = model.lsp_client
    assert client is not None

    try:
        await ensure_file_synced(model, uri)
    except Exception as e:
        return format_error(f"import: {e}", None)

    params = {
        "textDocument": {"uri": uri},
        "range": {
            "start": {"line": lsp_line, "character": 0},
            "end": {"line": lsp_line, "character": 999},
        },
        "context": {
            "diagnostics": [],
            "only": ["quickfix", "source", "source.organizeImports"],
            "triggerKind": 1,
        },
    }

    try:
        raw_actions = await client.request("textDocument/codeAction", params)
    except Exception as e:
        return format_error(f"import failed: {e}", None)

    if not raw_actions:
        raw_actions = []

    actions = [CodeAction.from_dict(a) for a in raw_actions]
    symbol_lower = symbol_name.lower()

    import_actions = [
        a for a in actions
        if (
            (a.kind and (
                "import" in a.kind
                or a.kind == "quickfix"
                or a.kind.startswith("source")
            ))
            or "import" in a.title.lower()
            or "use " in a.title.lower()
        )
        and symbol_lower in a.title.lower()
    ]

    if not import_actions:
        return format_error(
            f"no import action for '{symbol_name}' at {file_sel.value}:{line_num}.",
            None,
        )

    if len(import_actions) == 1:
        action = import_actions[0]
    else:
        preferred = next((a for a in import_actions if a.is_preferred), None)
        if preferred:
            action = preferred
        else:
            return format_code_action_choices(import_actions)

    if action.edit is None:
        return format_error("import action has no edit.", None)

    try:
        result = apply_workspace_edit(action.edit)
    except Exception as e:
        return format_error(f"failed to apply import: {e}", None)

    return format_mutation_result("import", symbol_name, result, model.root_uri)
