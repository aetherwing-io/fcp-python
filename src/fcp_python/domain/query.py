"""Query dispatcher and handlers."""

from __future__ import annotations

from fcp_core import VerbRegistry, parse_op, suggest, ParseError

from fcp_python.lsp.types import (
    CallHierarchyIncomingCall,
    CallHierarchyOutgoingCall,
    CallHierarchyItem,
    Diagnostic,
    DiagnosticSeverity,
    DocumentSymbol,
    Hover,
    HoverContents,
    Location,
    MarkupContent,
    SymbolInformation,
    SymbolKind,
)
from fcp_python.resolver.index import SymbolEntry
from fcp_python.resolver.pipeline import ResolveResult, SymbolResolver
from fcp_python.resolver.selectors import (
    SelectorType,
    filter_by_selectors,
    parse_selector,
    symbol_kind_from_string,
    ParsedSelector,
)

from .format import (
    format_callers,
    format_callees,
    format_code_action_choices,
    format_definition,
    format_diagnostics,
    format_disambiguation,
    format_error,
    format_hover,
    format_implementations,
    format_navigation_result,
    format_symbol_outline,
    format_unused,
    format_workspace_map,
)
from .model import PythonModel


def find_in_doc_symbols(
    symbols: list[DocumentSymbol],
    name: str,
    line: int,
    parent_name: str | None = None,
) -> SymbolEntry | None:
    """Search a DocumentSymbol tree for a symbol matching by name + line range."""
    for sym in symbols:
        if sym.name == name and sym.range.start.line <= line <= sym.range.end.line:
            return SymbolEntry(
                name=sym.name,
                kind=sym.kind,
                container_name=parent_name,
                uri="",  # caller fills in
                range=sym.range,
                selection_range=sym.selection_range,
            )
        if sym.children:
            found = find_in_doc_symbols(sym.children, name, line, sym.name)
            if found is not None:
                return found
    return None


def find_by_name_in_doc_symbols(
    symbols: list[DocumentSymbol],
    name: str,
    parent_name: str | None = None,
) -> SymbolEntry | None:
    """Search a DocumentSymbol tree by name only (for @class: path resolution)."""
    for sym in symbols:
        if sym.name == name:
            return SymbolEntry(
                name=sym.name,
                kind=sym.kind,
                container_name=parent_name,
                uri="",  # caller fills in
                range=sym.range,
                selection_range=sym.selection_range,
            )
        if sym.children:
            found = find_by_name_in_doc_symbols(sym.children, name, sym.name)
            if found is not None:
                return found
    return None


async def resolve_with_fallback(
    model: PythonModel,
    name: str,
    selectors: list[ParsedSelector],
) -> ResolveResult:
    """3-tier resolution: index -> workspace/symbol -> documentSymbol."""
    # Tier 1: in-memory index
    resolver = SymbolResolver(model.symbol_index)
    result = resolver.resolve_from_index(name, selectors)

    if not result.is_not_found:
        return result

    client = model.lsp_client
    if client is None:
        return result

    # Tier 2: workspace/symbol LSP
    try:
        raw_symbols = await client.request("workspace/symbol", {"query": name})
    except Exception:
        raw_symbols = []

    if raw_symbols:
        symbols = [SymbolInformation.from_dict(s) for s in raw_symbols]

        if selectors:
            filtered = filter_by_selectors(symbols, selectors)
        else:
            filtered = symbols

        if len(filtered) == 1:
            sym = filtered[0]
            return ResolveResult.found(SymbolEntry(
                name=sym.name,
                kind=sym.kind,
                container_name=sym.container_name,
                uri=sym.location.uri,
                range=sym.location.range,
                selection_range=sym.location.range,
            ))
        elif len(filtered) > 1:
            entries = [
                SymbolEntry(
                    name=s.name,
                    kind=s.kind,
                    container_name=s.container_name,
                    uri=s.location.uri,
                    range=s.location.range,
                    selection_range=s.location.range,
                )
                for s in filtered
            ]
            return ResolveResult.ambiguous(entries)

    # Tier 3: documentSymbol fallback
    file_sel = next((s for s in selectors if s.selector_type == SelectorType.FILE), None)
    line_sel = next((s for s in selectors if s.selector_type == SelectorType.LINE), None)
    class_sel = next((s for s in selectors if s.selector_type == SelectorType.CLASS), None)

    # Tier 3a: @file + @line
    if file_sel is not None and line_sel is not None:
        try:
            line_num = int(line_sel.value)
        except ValueError:
            pass
        else:
            uri = (
                file_sel.value
                if file_sel.value.startswith("file://")
                else f"{model.root_uri.rstrip('/')}/{file_sel.value}"
            )
            try:
                raw_doc_symbols = await client.request(
                    "textDocument/documentSymbol", {"textDocument": {"uri": uri}}
                )
            except Exception:
                raw_doc_symbols = None

            if raw_doc_symbols:
                doc_symbols = [DocumentSymbol.from_dict(s) for s in raw_doc_symbols]
                lsp_line = line_num - 1 if line_num > 0 else line_num
                entry = find_in_doc_symbols(doc_symbols, name, lsp_line)
                if entry is not None:
                    entry.uri = uri
                    return ResolveResult.found(entry)

    # Tier 3b: @class:NAME — locate class file via workspace/symbol, then documentSymbol
    if class_sel is not None:
        try:
            raw_class_symbols = await client.request(
                "workspace/symbol", {"query": class_sel.value}
            )
        except Exception:
            raw_class_symbols = []

        if raw_class_symbols:
            class_symbols = [SymbolInformation.from_dict(s) for s in raw_class_symbols]
            class_info = next(
                (s for s in class_symbols if s.name == class_sel.value and s.kind == SymbolKind.Class),
                None,
            )
            if class_info is not None:
                uri = class_info.location.uri
                try:
                    raw_doc_symbols = await client.request(
                        "textDocument/documentSymbol", {"textDocument": {"uri": uri}}
                    )
                except Exception:
                    raw_doc_symbols = None

                if raw_doc_symbols:
                    doc_symbols = [DocumentSymbol.from_dict(s) for s in raw_doc_symbols]
                    for sym in doc_symbols:
                        if sym.name == class_sel.value and sym.kind == SymbolKind.Class:
                            if sym.children:
                                entry = find_by_name_in_doc_symbols(sym.children, name, sym.name)
                                if entry is not None:
                                    entry.uri = uri
                                    return ResolveResult.found(entry)
                            break

    return ResolveResult.not_found()


async def dispatch_query(
    model: PythonModel,
    registry: VerbRegistry,
    input_str: str,
) -> str:
    """Parse input, route to handler."""
    op = parse_op(input_str)
    if isinstance(op, ParseError):
        return format_error(f"parse error: {op.error}", None)

    if registry.lookup(op.verb) is None:
        verb_names = [v.verb for v in registry.verbs]
        suggestion = suggest(op.verb, verb_names)
        return format_error(f"unknown verb '{op.verb}'.", suggestion)

    match op.verb:
        case "find":
            return await handle_find(model, op.positionals, op.params)
        case "def":
            return await handle_def(model, op.positionals, op.selectors)
        case "refs":
            return await handle_refs(model, op.positionals, op.selectors)
        case "symbols":
            return await handle_symbols(model, op.positionals)
        case "diagnose":
            return handle_diagnose(model, op.positionals)
        case "inspect":
            return await handle_inspect(model, op.positionals, op.selectors)
        case "callers":
            return await handle_callers(model, op.positionals, op.selectors)
        case "callees":
            return await handle_callees(model, op.positionals, op.selectors)
        case "impl":
            return await handle_impl(model, op.positionals, op.selectors)
        case "map":
            return handle_map(model)
        case "unused":
            return handle_unused(model, op.selectors)
        case _:
            return format_error(f"unhandled verb '{op.verb}'.", None)


async def handle_find(
    model: PythonModel,
    positionals: list[str],
    params: dict[str, str],
) -> str:
    if not positionals:
        return format_error("find requires a search query.", None)
    query = positionals[0]
    kind_filter = params.get("kind")

    entries = model.symbol_index.lookup_by_name(query)

    if kind_filter is not None:
        target_kind = symbol_kind_from_string(kind_filter)
        if target_kind is None:
            return format_error(f"unknown kind '{kind_filter}'.", None)
        entries = [e for e in entries if e.kind == target_kind]

    if not entries:
        # Try LSP workspace/symbol as fallback
        if model.lsp_client is not None:
            try:
                raw_symbols = await model.lsp_client.request(
                    "workspace/symbol", {"query": query}
                )
                if raw_symbols:
                    symbols = [SymbolInformation.from_dict(s) for s in raw_symbols]
                    locs = [Location(uri=s.location.uri, range=s.location.range) for s in symbols]
                    return format_navigation_result(locs, f"matches for '{query}'")
            except Exception:
                pass
        return format_error(f"no symbols matching '{query}'.", None)

    locs = [Location(uri=e.uri, range=e.range) for e in entries]
    return format_navigation_result(locs, f"matches for '{query}'")


async def handle_def(
    model: PythonModel,
    positionals: list[str],
    selectors: list[str],
) -> str:
    if not positionals:
        return format_error("def requires a symbol name.", None)
    name = positionals[0]

    parsed_selectors = [s for s in (parse_selector(sel) for sel in selectors) if s is not None]
    result = await resolve_with_fallback(model, name, parsed_selectors)

    if result.is_found:
        return format_definition(result.entry.uri, result.entry.range)
    elif result.is_ambiguous:
        return format_disambiguation(name, result.entries)
    else:
        return format_error(f"symbol '{name}' not found.", None)


async def handle_refs(
    model: PythonModel,
    positionals: list[str],
    selectors: list[str],
) -> str:
    if not positionals:
        return format_error("refs requires a symbol name.", None)
    name = positionals[0]

    parsed_selectors = [s for s in (parse_selector(sel) for sel in selectors) if s is not None]
    result = await resolve_with_fallback(model, name, parsed_selectors)

    if result.is_ambiguous:
        return format_disambiguation(name, result.entries)
    if result.is_not_found:
        return format_error(f"symbol '{name}' not found.", None)
    entry = result.entry

    client = model.lsp_client
    if client is None:
        return format_error("no workspace open.", None)

    params = {
        "textDocument": {"uri": entry.uri},
        "position": {"line": entry.range.start.line, "character": entry.range.start.character},
        "context": {"includeDeclaration": True},
    }
    try:
        raw_locs = await client.request("textDocument/references", params)
        locations = [Location.from_dict(loc) for loc in raw_locs]
        return format_navigation_result(locations, f"references to '{name}'")
    except Exception as e:
        return format_error(f"LSP error: {e}", None)


async def handle_symbols(
    model: PythonModel,
    positionals: list[str],
) -> str:
    if not positionals:
        return format_error("symbols requires a file path.", None)
    path = positionals[0]

    client = model.lsp_client
    if client is None:
        return format_error("no workspace open.", None)

    uri = path if path.startswith("file://") else f"{model.root_uri.rstrip('/')}/{path}"
    params = {"textDocument": {"uri": uri}}

    try:
        raw_symbols = await client.request("textDocument/documentSymbol", params)
        if raw_symbols and isinstance(raw_symbols, list):
            # Try DocumentSymbol[] (hierarchical) first
            if "range" in raw_symbols[0]:
                symbols = [DocumentSymbol.from_dict(s) for s in raw_symbols]
                return format_symbol_outline(uri, symbols, 0)
            else:
                # Fallback: SymbolInformation[]
                sym_infos = [SymbolInformation.from_dict(s) for s in raw_symbols]
                doc_symbols = [
                    DocumentSymbol(
                        name=s.name,
                        kind=s.kind,
                        range=s.location.range,
                        selection_range=s.location.range,
                    )
                    for s in sym_infos
                ]
                return format_symbol_outline(uri, doc_symbols, 0)
        return format_symbol_outline(uri, [], 0)
    except Exception as e:
        return format_error(f"LSP error: {e}", None)


def handle_diagnose(model: PythonModel, positionals: list[str]) -> str:
    if positionals:
        path = positionals[0]
        uri = path if path.startswith("file://") else f"{model.root_uri.rstrip('/')}/{path}"
        for diag_uri, diags in model.diagnostics.items():
            if diag_uri == uri or diag_uri.endswith(path):
                return format_diagnostics(diag_uri, diags)
        return format_diagnostics(uri, [])
    else:
        if not model.diagnostics:
            return "Workspace: clean — no diagnostics."
        lines = []
        errors, warnings = model.total_diagnostics()
        lines.append(f"Workspace diagnostics: {errors} errors, {warnings} warnings")
        for uri, diags in model.diagnostics.items():
            lines.append(format_diagnostics(uri, diags))
        return "\n\n".join(lines)


async def handle_inspect(
    model: PythonModel,
    positionals: list[str],
    selectors: list[str],
) -> str:
    if not positionals:
        return format_error("inspect requires a symbol name.", None)
    name = positionals[0]

    parsed_selectors = [s for s in (parse_selector(sel) for sel in selectors) if s is not None]
    result = await resolve_with_fallback(model, name, parsed_selectors)

    if result.is_ambiguous:
        return format_disambiguation(name, result.entries)
    if result.is_not_found:
        return format_error(f"symbol '{name}' not found.", None)
    entry = result.entry

    client = model.lsp_client
    if client is None:
        kind_str = entry.kind.display_name()
        return format_hover(name, kind_str, entry.uri, entry.range, "")

    params = {
        "textDocument": {"uri": entry.uri},
        "position": {
            "line": entry.selection_range.start.line,
            "character": entry.selection_range.start.character,
        },
    }
    try:
        raw_hover = await client.request("textDocument/hover", params)
        if raw_hover is None:
            kind_str = entry.kind.display_name()
            return format_hover(name, kind_str, entry.uri, entry.range, "")
        hover = Hover.from_dict(raw_hover)
        contents = hover.contents
        if isinstance(contents, str):
            text = contents
        elif isinstance(contents, MarkupContent):
            text = contents.value
        elif isinstance(contents, list):
            text = "\n".join(contents)
        else:
            text = ""
        kind_str = entry.kind.display_name()
        return format_hover(name, kind_str, entry.uri, entry.range, text)
    except Exception as e:
        return format_error(f"LSP error: {e}", None)


async def handle_callers(
    model: PythonModel,
    positionals: list[str],
    selectors: list[str],
) -> str:
    if not positionals:
        return format_error("callers requires a symbol name.", None)
    name = positionals[0]

    parsed_selectors = [s for s in (parse_selector(sel) for sel in selectors) if s is not None]
    result = await resolve_with_fallback(model, name, parsed_selectors)

    if result.is_ambiguous:
        return format_disambiguation(name, result.entries)
    if result.is_not_found:
        return format_error(f"symbol '{name}' not found.", None)
    entry = result.entry

    client = model.lsp_client
    if client is None:
        return format_error("no workspace open.", None)

    prepare_params = {
        "textDocument": {"uri": entry.uri},
        "position": {
            "line": entry.selection_range.start.line,
            "character": entry.selection_range.start.character,
        },
    }
    try:
        raw_items = await client.request("textDocument/prepareCallHierarchy", prepare_params)
    except Exception as e:
        return format_error(f"LSP error: {e}", None)

    if not raw_items:
        return format_callers(name, [])

    item = CallHierarchyItem.from_dict(raw_items[0])
    try:
        raw_calls = await client.request(
            "callHierarchy/incomingCalls", {"item": item.to_dict()}
        )
        calls = [CallHierarchyIncomingCall.from_dict(c) for c in raw_calls]
        return format_callers(name, calls)
    except Exception as e:
        return format_error(f"LSP error: {e}", None)


async def handle_callees(
    model: PythonModel,
    positionals: list[str],
    selectors: list[str],
) -> str:
    if not positionals:
        return format_error("callees requires a symbol name.", None)
    name = positionals[0]

    parsed_selectors = [s for s in (parse_selector(sel) for sel in selectors) if s is not None]
    result = await resolve_with_fallback(model, name, parsed_selectors)

    if result.is_ambiguous:
        return format_disambiguation(name, result.entries)
    if result.is_not_found:
        return format_error(f"symbol '{name}' not found.", None)
    entry = result.entry

    client = model.lsp_client
    if client is None:
        return format_error("no workspace open.", None)

    prepare_params = {
        "textDocument": {"uri": entry.uri},
        "position": {
            "line": entry.selection_range.start.line,
            "character": entry.selection_range.start.character,
        },
    }
    try:
        raw_items = await client.request("textDocument/prepareCallHierarchy", prepare_params)
    except Exception as e:
        return format_error(f"LSP error: {e}", None)

    if not raw_items:
        return format_callees(name, [])

    item = CallHierarchyItem.from_dict(raw_items[0])
    try:
        raw_calls = await client.request(
            "callHierarchy/outgoingCalls", {"item": item.to_dict()}
        )
        calls = [CallHierarchyOutgoingCall.from_dict(c) for c in raw_calls]
        return format_callees(name, calls)
    except Exception as e:
        return format_error(f"LSP error: {e}", None)


async def handle_impl(
    model: PythonModel,
    positionals: list[str],
    selectors: list[str],
) -> str:
    if not positionals:
        return format_error("impl requires a symbol name.", None)
    name = positionals[0]

    parsed_selectors = [s for s in (parse_selector(sel) for sel in selectors) if s is not None]
    result = await resolve_with_fallback(model, name, parsed_selectors)

    if result.is_ambiguous:
        return format_disambiguation(name, result.entries)
    if result.is_not_found:
        return format_error(f"symbol '{name}' not found.", None)
    entry = result.entry

    client = model.lsp_client
    if client is None:
        return format_error("no workspace open.", None)

    params = {
        "textDocument": {"uri": entry.uri},
        "position": {
            "line": entry.selection_range.start.line,
            "character": entry.selection_range.start.character,
        },
    }
    try:
        raw_locs = await client.request("textDocument/implementation", params)
        locations = [Location.from_dict(loc) for loc in raw_locs]
        return format_implementations(name, locations)
    except Exception as e:
        return format_error(f"LSP error: {e}", None)


def handle_map(model: PythonModel) -> str:
    errors, warnings = model.total_diagnostics()
    return format_workspace_map(
        model.root_uri,
        model.py_file_count,
        model.symbol_index.size(),
        errors,
        warnings,
    )


def handle_unused(model: PythonModel, selectors: list[str]) -> str:
    parsed_selectors = [s for s in (parse_selector(sel) for sel in selectors) if s is not None]
    file_filter = next(
        (s.value for s in parsed_selectors if s.selector_type == SelectorType.FILE), None
    )

    unused_patterns = ["unused", "never read", "never constructed", "never used", "dead_code"]

    items: list[tuple[str, Diagnostic]] = []
    for uri, diags in model.diagnostics.items():
        if file_filter and file_filter not in uri:
            continue
        for diag in diags:
            msg_lower = diag.message.lower()
            if any(p in msg_lower for p in unused_patterns):
                items.append((uri, diag))

    items.sort(key=lambda x: (x[0], x[1].range.start.line))
    return format_unused(items)
