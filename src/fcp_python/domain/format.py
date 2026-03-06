"""Output formatting for query results."""

from __future__ import annotations

from fcp_python.lsp.types import (
    CallHierarchyIncomingCall,
    CallHierarchyOutgoingCall,
    CodeAction,
    Diagnostic,
    DiagnosticSeverity,
    DocumentSymbol,
    Location,
    Range,
)
from fcp_python.lsp.workspace_edit import ApplyResult
from fcp_python.resolver.index import SymbolEntry


def format_navigation_result(locations: list[Location], description: str) -> str:
    if not locations:
        return f"No {description} found."
    lines = [f"{description} ({len(locations)}):"]
    for loc in locations:
        lines.append(
            f"  {short_uri(loc.uri)} L{loc.range.start.line + 1}:{loc.range.start.character + 1}"
        )
    return "\n".join(lines)


def format_definition(uri: str, range_: Range, source_snippet: str | None = None) -> str:
    result = f"Definition: {short_uri(uri)} L{range_.start.line + 1}:{range_.start.character + 1}"
    if source_snippet:
        result += f"\n\n{source_snippet}"
    return result


def format_symbol_outline(file: str, symbols: list[DocumentSymbol], indent: int) -> str:
    lines: list[str] = []
    if indent == 0:
        lines.append(f"Symbols in {short_uri(file)}:")
    prefix = "  " * (indent + 1)
    for sym in symbols:
        kind_str = sym.kind.display_name()
        lines.append(f"{prefix}{sym.name} ({kind_str}) L{sym.range.start.line + 1}")
        if sym.children:
            lines.append(format_symbol_outline(file, sym.children, indent + 1))
    return "\n".join(lines)


def format_diagnostics(uri: str, diagnostics: list[Diagnostic]) -> str:
    if not diagnostics:
        return f"{short_uri(uri)}: clean"
    lines = [f"{short_uri(uri)} ({len(diagnostics)} issues):"]
    for d in diagnostics:
        severity = {
            DiagnosticSeverity.Error: "ERROR",
            DiagnosticSeverity.Warning: "WARN",
            DiagnosticSeverity.Information: "INFO",
            DiagnosticSeverity.Hint: "HINT",
        }.get(d.severity, "???")  # type: ignore[arg-type]
        lines.append(
            f"  L{d.range.start.line + 1}: [{severity}] {summarize_diagnostic_message(d.message)}"
        )
    return "\n".join(lines)


def format_disambiguation(name: str, entries: list[SymbolEntry]) -> str:
    lines = [f"? Multiple matches for '{name}'. Narrow with a selector:"]
    for i, entry in enumerate(entries):
        container = f" in {entry.container_name}" if entry.container_name else ""
        lines.append(
            f"  {i + 1}. {entry.name} ({entry.kind!r}){container} — {short_uri(entry.uri)}"
        )
    return "\n".join(lines)


def format_hover(
    name: str, kind: str, uri: str, range_: Range, contents: str
) -> str:
    lines = [f"{name} ({kind}) — {short_uri(uri)} L{range_.start.line + 1}"]
    if contents:
        lines.append("")
        lines.append(contents)
    return "\n".join(lines)


def format_callers(name: str, calls: list[CallHierarchyIncomingCall]) -> str:
    if not calls:
        return f"No callers of '{name}'."
    lines = [f"Callers of '{name}' ({len(calls)}):"]
    for call in calls:
        lines.append(
            f"  {call.from_item.name} ({call.from_item.kind!r}) — "
            f"{short_uri(call.from_item.uri)} L{call.from_item.range.start.line + 1}"
        )
    return "\n".join(lines)


def format_callees(name: str, calls: list[CallHierarchyOutgoingCall]) -> str:
    if not calls:
        return f"No callees of '{name}'."
    lines = [f"Callees of '{name}' ({len(calls)}):"]
    for call in calls:
        lines.append(
            f"  {call.to.name} ({call.to.kind!r}) — "
            f"{short_uri(call.to.uri)} L{call.to.range.start.line + 1}"
        )
    return "\n".join(lines)


def format_implementations(name: str, locations: list[Location]) -> str:
    if not locations:
        return f"No implementations of '{name}'."
    lines = [f"Implementations of '{name}' ({len(locations)}):"]
    for loc in locations:
        lines.append(
            f"  {short_uri(loc.uri)} L{loc.range.start.line + 1}:{loc.range.start.character + 1}"
        )
    return "\n".join(lines)


def format_workspace_map(
    root_uri: str,
    file_count: int,
    symbol_count: int,
    errors: int,
    warnings: int,
) -> str:
    lines = [
        f"Workspace: {short_uri(root_uri)}",
        f"  Files: {file_count}",
        f"  Symbols: {symbol_count}",
    ]
    if errors > 0 or warnings > 0:
        lines.append(f"  Diagnostics: {errors} errors, {warnings} warnings")
    else:
        lines.append("  Diagnostics: clean")
    return "\n".join(lines)


def format_unused(items: list[tuple[str, Diagnostic]]) -> str:
    if not items:
        return "No unused symbols found."
    lines = [f"Unused symbols ({len(items)}):"]
    for uri, diag in items:
        classification = _classify_unused(diag.message)
        lines.append(
            f"  {short_uri(uri)} L{diag.range.start.line + 1}: "
            f"[{classification}] {summarize_diagnostic_message(diag.message)}"
        )
    return "\n".join(lines)


def format_mutation_result(
    verb: str, description: str, result: ApplyResult, root_uri: str
) -> str:
    total = result.total_edits()
    file_count = len(result.files_changed)
    lines = [
        f"{verb}: {description} ({file_count} {'file' if file_count == 1 else 'files'}, "
        f"{total} {'edit' if total == 1 else 'edits'})"
    ]
    for uri, count in result.files_changed:
        lines.append(
            f"  {relative_path(uri, root_uri)}: {count} {'edit' if count == 1 else 'edits'}"
        )
    for uri in result.files_created:
        lines.append(f"  {relative_path(uri, root_uri)} (created)")
    for old, new in result.files_renamed:
        lines.append(
            f"  {relative_path(old, root_uri)} → {relative_path(new, root_uri)} (renamed)"
        )
    return "\n".join(lines)


def format_code_action_choices(actions: list[CodeAction]) -> str:
    lines = [f"? Multiple code actions available ({len(actions)}):"]
    for i, action in enumerate(actions):
        kind = action.kind or "unknown"
        preferred = " (preferred)" if action.is_preferred else ""
        lines.append(f"  {i + 1}. [{kind}] {action.title}{preferred}")
    return "\n".join(lines)


def _classify_unused(message: str) -> str:
    lower = message.lower()
    if "dead_code" in lower or "never constructed" in lower:
        return "dead_code"
    if "never read" in lower:
        return "never_read"
    return "unused"


def format_error(message: str, suggestion: str | None = None) -> str:
    if suggestion:
        return f"! {message} Did you mean '{suggestion}'?"
    return f"! {message}"


def summarize_diagnostic_message(raw: str) -> str:
    # Strip Python error code prefixes like "E0308: "
    if raw.startswith("E") and len(raw) > 5:
        code = raw[1:5]
        if code.isdigit():
            after = raw[5:]
            if after.startswith(": "):
                return after[2:]
    return raw


def short_uri(uri: str) -> str:
    return uri.removeprefix("file://")


def relative_path(uri: str, root_uri: str) -> str:
    path = short_uri(uri)
    root = short_uri(root_uri).rstrip("/")
    if path.startswith(root):
        rel = path[len(root):]
        return rel.lstrip("/")
    return path
