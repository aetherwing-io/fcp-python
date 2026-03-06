"""Tests for output formatting functions."""

import pytest

from fcp_python.domain.format import (
    format_callers,
    format_callees,
    format_code_action_choices,
    format_definition,
    format_diagnostics,
    format_disambiguation,
    format_error,
    format_hover,
    format_implementations,
    format_mutation_result,
    format_navigation_result,
    format_symbol_outline,
    format_unused,
    format_workspace_map,
    relative_path,
    summarize_diagnostic_message,
)
from fcp_python.lsp.types import (
    CallHierarchyIncomingCall,
    CallHierarchyItem,
    CallHierarchyOutgoingCall,
    CodeAction,
    Diagnostic,
    DiagnosticSeverity,
    DocumentSymbol,
    Location,
    Position,
    Range,
    SymbolKind,
)
from fcp_python.lsp.workspace_edit import ApplyResult
from fcp_python.resolver.index import SymbolEntry


def _pos(line: int, character: int = 0) -> Position:
    return Position(line=line, character=character)


def _range(start_line: int, end_line: int) -> Range:
    return Range(start=_pos(start_line), end=_pos(end_line))


def _loc(uri: str, start_line: int) -> Location:
    return Location(uri=uri, range=_range(start_line, start_line + 5))


def test_format_navigation_result_multiple():
    locs = [
        _loc("file:///src/a.py", 10),
        _loc("file:///src/b.py", 20),
        _loc("file:///src/c.py", 30),
    ]
    result = format_navigation_result(locs, "references to foo")
    assert "references to foo (3):" in result
    assert "/src/a.py L11:1" in result
    assert "/src/b.py L21:1" in result
    assert "/src/c.py L31:1" in result


def test_format_navigation_result_empty():
    result = format_navigation_result([], "references")
    assert result == "No references found."


def test_format_definition_with_snippet():
    result = format_definition(
        "file:///src/lib.py",
        _range(10, 15),
        "def add(a: int, b: int) -> int: ...",
    )
    assert "Definition: /src/lib.py L11:1" in result
    assert "def add" in result


def test_format_definition_without_snippet():
    result = format_definition("file:///src/main.py", _range(0, 5))
    assert "Definition: /src/main.py L1:1" in result
    assert "\n\n" not in result


def test_format_symbol_outline_flat():
    symbols = [
        DocumentSymbol(name="main", kind=SymbolKind.Function, range=_range(0, 5), selection_range=_range(0, 0)),
        DocumentSymbol(name="Config", kind=SymbolKind.Class, range=_range(7, 12), selection_range=_range(7, 7)),
        DocumentSymbol(name="MAX", kind=SymbolKind.Constant, range=_range(14, 14), selection_range=_range(14, 14)),
    ]
    result = format_symbol_outline("file:///src/main.py", symbols, 0)
    assert "Symbols in /src/main.py:" in result
    assert "main (function) L1" in result
    assert "Config (class) L8" in result
    assert "MAX (constant) L15" in result


def test_format_diagnostics_mixed():
    diags = [
        Diagnostic(range=_range(5, 5), severity=DiagnosticSeverity.Error, message="type mismatch"),
        Diagnostic(range=_range(10, 10), severity=DiagnosticSeverity.Error, message="undefined variable"),
        Diagnostic(range=_range(15, 15), severity=DiagnosticSeverity.Warning, message="unused import"),
    ]
    result = format_diagnostics("file:///src/main.py", diags)
    assert "/src/main.py (3 issues):" in result
    assert "[ERROR] type mismatch" in result
    assert "[WARN] unused import" in result


def test_format_diagnostics_clean():
    result = format_diagnostics("file:///src/main.py", [])
    assert "clean" in result


def test_format_disambiguation():
    entries = [
        SymbolEntry(name="new", kind=SymbolKind.Function, container_name="Vec", uri="file:///std/vec.py", range=_range(0, 5), selection_range=_range(0, 0)),
        SymbolEntry(name="new", kind=SymbolKind.Function, container_name="HashMap", uri="file:///std/hashmap.py", range=_range(0, 5), selection_range=_range(0, 0)),
        SymbolEntry(name="new", kind=SymbolKind.Function, container_name=None, uri="file:///src/lib.py", range=_range(10, 15), selection_range=_range(10, 10)),
    ]
    result = format_disambiguation("new", entries)
    assert "? Multiple matches for 'new'" in result
    assert "1." in result
    assert "2." in result
    assert "3." in result
    assert "in Vec" in result
    assert "in HashMap" in result


def test_format_hover():
    result = format_hover(
        "add", "function", "file:///src/lib.py", _range(10, 15),
        "def add(a: int, b: int) -> int",
    )
    assert "add (function)" in result
    assert "/src/lib.py L11" in result
    assert "def add" in result


def test_format_callers():
    calls = [
        CallHierarchyIncomingCall(
            from_item=CallHierarchyItem(
                name="main", kind=SymbolKind.Function, uri="file:///src/main.py",
                range=_range(0, 10), selection_range=_range(0, 0),
            ),
            from_ranges=[_range(5, 5)],
        ),
    ]
    result = format_callers("add", calls)
    assert "Callers of 'add' (1):" in result
    assert "main" in result


def test_format_callees():
    calls = [
        CallHierarchyOutgoingCall(
            to=CallHierarchyItem(
                name="validate", kind=SymbolKind.Function, uri="file:///src/lib.py",
                range=_range(50, 60), selection_range=_range(50, 50),
            ),
            from_ranges=[_range(5, 5)],
        ),
    ]
    result = format_callees("handle_request", calls)
    assert "Callees of 'handle_request' (1):" in result
    assert "validate" in result


def test_format_implementations():
    locs = [
        _loc("file:///src/echo.py", 10),
        _loc("file:///src/log.py", 20),
    ]
    result = format_implementations("Handler", locs)
    assert "Implementations of 'Handler' (2):" in result


def test_format_workspace_map():
    result = format_workspace_map("file:///projects/myapp", 15, 120, 2, 5)
    assert "Workspace: /projects/myapp" in result
    assert "Files: 15" in result
    assert "Symbols: 120" in result
    assert "2 errors, 5 warnings" in result


def test_format_unused_empty():
    assert format_unused([]) == "No unused symbols found."


def test_format_unused_with_items():
    d1 = Diagnostic(range=_range(5, 5), severity=DiagnosticSeverity.Warning, message="unused variable `x`")
    d2 = Diagnostic(range=_range(10, 10), severity=DiagnosticSeverity.Warning, message="value assigned to `y` is never read")
    items = [("file:///src/main.py", d1), ("file:///src/lib.py", d2)]
    result = format_unused(items)
    assert "Unused symbols (2):" in result
    assert "[unused]" in result
    assert "[never_read]" in result


def test_format_mutation_result():
    result = ApplyResult(
        files_changed=[
            ("file:///projects/myapp/src/config.py", 4),
            ("file:///projects/myapp/src/main.py", 2),
            ("file:///projects/myapp/tests/test.py", 1),
        ],
    )
    output = format_mutation_result(
        "rename", "Config → Settings", result, "file:///projects/myapp",
    )
    assert "rename: Config → Settings (3 files, 7 edits)" in output
    assert "src/config.py: 4 edits" in output
    assert "src/main.py: 2 edits" in output
    assert "tests/test.py: 1 edit" in output


def test_format_code_action_choices():
    actions = [
        CodeAction(title="Extract into function", kind="refactor.extract.function", is_preferred=True),
        CodeAction(title="Extract into method", kind="refactor.extract.method"),
    ]
    output = format_code_action_choices(actions)
    assert "Multiple code actions available (2):" in output
    assert "1. [refactor.extract.function] Extract into function (preferred)" in output
    assert "2. [refactor.extract.method] Extract into method" in output


def test_format_error_with_suggestion():
    result = format_error("unknown verb 'fnd'.", "find")
    assert "! unknown verb 'fnd'." in result
    assert "Did you mean 'find'?" in result


def test_format_error_without_suggestion():
    result = format_error("no workspace open.")
    assert result == "! no workspace open."


def test_summarize_diagnostic_message_e0308():
    assert summarize_diagnostic_message("E0308: mismatched types") == "mismatched types"


def test_summarize_diagnostic_message_plain():
    assert summarize_diagnostic_message("unused variable `x`") == "unused variable `x`"


def test_relative_path():
    assert relative_path("file:///projects/myapp/src/main.py", "file:///projects/myapp") == "src/main.py"


def test_relative_path_no_match():
    assert relative_path("file:///other/path.py", "file:///projects/myapp") == "/other/path.py"
