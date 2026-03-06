"""Tests for query dispatch and handlers."""

import pytest

from fcp_core import VerbRegistry

from fcp_python.domain.model import PythonModel
from fcp_python.domain.query import (
    dispatch_query,
    find_by_name_in_doc_symbols,
    find_in_doc_symbols,
)
from fcp_python.domain.verbs import register_query_verbs, register_session_verbs
from fcp_python.lsp.types import (
    Diagnostic,
    DiagnosticSeverity,
    DocumentSymbol,
    Position,
    Range,
    SymbolKind,
)
from fcp_python.resolver.index import SymbolEntry


def _pos(line: int, character: int = 0) -> Position:
    return Position(line=line, character=character)


def _range(start_line: int, end_line: int) -> Range:
    return Range(start=_pos(start_line), end=_pos(end_line))


def _make_entry(
    name: str,
    kind: SymbolKind,
    uri: str,
    container: str | None = None,
) -> SymbolEntry:
    return SymbolEntry(
        name=name,
        kind=kind,
        container_name=container,
        uri=uri,
        range=_range(0, 5),
        selection_range=_range(0, 0),
    )


def _make_model(entries: list[SymbolEntry] | None = None) -> PythonModel:
    model = PythonModel("file:///project")
    if entries:
        for entry in entries:
            model.symbol_index.insert(entry)
    return model


def _make_registry() -> VerbRegistry:
    reg = VerbRegistry()
    register_query_verbs(reg)
    register_session_verbs(reg)
    return reg


# -- find --

@pytest.mark.asyncio
async def test_handle_find_with_results():
    model = _make_model([
        _make_entry("Config", SymbolKind.Class, "file:///src/config.py"),
        _make_entry("Config", SymbolKind.Class, "file:///src/other.py"),
    ])
    reg = _make_registry()
    result = await dispatch_query(model, reg, "find Config")
    assert "matches for 'Config' (2):" in result
    assert "config.py" in result
    assert "other.py" in result


@pytest.mark.asyncio
async def test_handle_find_no_results():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "find NonExistent")
    assert "no symbols matching 'NonExistent'" in result


@pytest.mark.asyncio
async def test_handle_find_with_kind_filter():
    model = _make_model([
        _make_entry("process", SymbolKind.Function, "file:///src/lib.py"),
        _make_entry("process", SymbolKind.Module, "file:///src/process.py"),
    ])
    reg = _make_registry()
    result = await dispatch_query(model, reg, "find process kind:function")
    assert "(1):" in result
    assert "lib.py" in result


# -- def --

@pytest.mark.asyncio
async def test_handle_def_found():
    model = _make_model([
        _make_entry("main", SymbolKind.Function, "file:///src/main.py"),
    ])
    reg = _make_registry()
    result = await dispatch_query(model, reg, "def main")
    assert "Definition:" in result
    assert "main.py" in result


@pytest.mark.asyncio
async def test_handle_def_not_found():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "def nonexistent")
    assert "not found" in result


@pytest.mark.asyncio
async def test_handle_def_ambiguous():
    model = _make_model([
        _make_entry("new", SymbolKind.Function, "file:///a.py", "A"),
        _make_entry("new", SymbolKind.Function, "file:///b.py", "B"),
    ])
    reg = _make_registry()
    result = await dispatch_query(model, reg, "def new")
    assert "Multiple matches" in result
    assert "in A" in result
    assert "in B" in result


# -- refs --

@pytest.mark.asyncio
async def test_handle_refs_not_found():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "refs unknown")
    assert "not found" in result


@pytest.mark.asyncio
async def test_handle_refs_no_client():
    model = _make_model([
        _make_entry("foo", SymbolKind.Function, "file:///lib.py"),
    ])
    reg = _make_registry()
    result = await dispatch_query(model, reg, "refs foo")
    assert "no workspace open" in result


# -- symbols --

@pytest.mark.asyncio
async def test_handle_symbols_no_client():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "symbols src/main.py")
    assert "no workspace open" in result


# -- diagnose --

@pytest.mark.asyncio
async def test_handle_diagnose_file():
    model = _make_model()
    model.update_diagnostics(
        "file:///project/src/main.py",
        [Diagnostic(
            range=_range(5, 5),
            severity=DiagnosticSeverity.Error,
            message="type mismatch",
        )],
    )
    reg = _make_registry()
    result = await dispatch_query(model, reg, "diagnose src/main.py")
    assert "1 issues" in result
    assert "type mismatch" in result


@pytest.mark.asyncio
async def test_handle_diagnose_workspace():
    model = _make_model()
    model.update_diagnostics(
        "file:///project/src/a.py",
        [Diagnostic(range=_range(1, 1), severity=DiagnosticSeverity.Error, message="err")],
    )
    model.update_diagnostics(
        "file:///project/src/b.py",
        [Diagnostic(range=_range(2, 2), severity=DiagnosticSeverity.Warning, message="warn")],
    )
    reg = _make_registry()
    result = await dispatch_query(model, reg, "diagnose")
    assert "1 errors, 1 warnings" in result


@pytest.mark.asyncio
async def test_handle_diagnose_clean():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "diagnose")
    assert "clean" in result


# -- inspect --

@pytest.mark.asyncio
async def test_handle_inspect_no_client_uses_index():
    model = _make_model([
        _make_entry("Config", SymbolKind.Class, "file:///src/config.py"),
    ])
    reg = _make_registry()
    result = await dispatch_query(model, reg, "inspect Config")
    assert "Config (class)" in result
    assert "config.py" in result


@pytest.mark.asyncio
async def test_handle_inspect_not_found():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "inspect NonExistent")
    assert "not found" in result


# -- callers/callees --

@pytest.mark.asyncio
async def test_handle_callers_not_found():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "callers unknown")
    assert "not found" in result


@pytest.mark.asyncio
async def test_handle_callers_no_client():
    model = _make_model([
        _make_entry("foo", SymbolKind.Function, "file:///lib.py"),
    ])
    reg = _make_registry()
    result = await dispatch_query(model, reg, "callers foo")
    assert "no workspace open" in result


@pytest.mark.asyncio
async def test_handle_callees_not_found():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "callees unknown")
    assert "not found" in result


# -- impl --

@pytest.mark.asyncio
async def test_handle_impl_not_found():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "impl NonExistent")
    assert "not found" in result


@pytest.mark.asyncio
async def test_handle_impl_no_client():
    model = _make_model([
        _make_entry("Handler", SymbolKind.Interface, "file:///lib.py"),
    ])
    reg = _make_registry()
    result = await dispatch_query(model, reg, "impl Handler")
    assert "no workspace open" in result


# -- map --

@pytest.mark.asyncio
async def test_handle_map():
    model = _make_model([
        _make_entry("main", SymbolKind.Function, "file:///src/main.py"),
        _make_entry("Config", SymbolKind.Class, "file:///src/config.py"),
    ])
    model.py_file_count = 5
    model.update_diagnostics(
        "file:///src/main.py",
        [Diagnostic(
            range=_range(0, 0),
            severity=DiagnosticSeverity.Warning,
            message="unused",
        )],
    )
    reg = _make_registry()
    result = await dispatch_query(model, reg, "map")
    assert "Workspace:" in result
    assert "Files: 5" in result
    assert "Symbols: 2" in result
    assert "0 errors, 1 warnings" in result


# -- dispatcher --

@pytest.mark.asyncio
async def test_dispatch_query_unknown_verb_with_suggestion():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "fnd Config")
    assert "unknown verb" in result
    assert "Did you mean 'find'?" in result


@pytest.mark.asyncio
async def test_dispatch_query_unknown_verb_no_suggestion():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "zzzzzzz Config")
    assert "unknown verb" in result


@pytest.mark.asyncio
async def test_dispatch_query_empty_input():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "")
    assert "parse error" in result


# -- unused --

@pytest.mark.asyncio
async def test_handle_unused_empty():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "unused")
    assert "No unused symbols found" in result


@pytest.mark.asyncio
async def test_handle_unused_with_matches():
    model = _make_model()
    model.update_diagnostics(
        "file:///project/src/main.py",
        [
            Diagnostic(
                range=_range(5, 5),
                severity=DiagnosticSeverity.Warning,
                message="unused variable `x`",
            ),
            Diagnostic(
                range=_range(10, 10),
                severity=DiagnosticSeverity.Error,
                message="type mismatch",
            ),
        ],
    )
    reg = _make_registry()
    result = await dispatch_query(model, reg, "unused")
    assert "Unused symbols (1):" in result
    assert "unused variable" in result
    assert "type mismatch" not in result


@pytest.mark.asyncio
async def test_handle_unused_file_filter():
    model = _make_model()
    model.update_diagnostics(
        "file:///project/src/a.py",
        [Diagnostic(range=_range(1, 1), severity=DiagnosticSeverity.Warning, message="unused import")],
    )
    model.update_diagnostics(
        "file:///project/src/b.py",
        [Diagnostic(range=_range(2, 2), severity=DiagnosticSeverity.Warning, message="unused variable `y`")],
    )
    reg = _make_registry()
    result = await dispatch_query(model, reg, "unused @file:a.py")
    assert "Unused symbols (1):" in result
    assert "a.py" in result
    assert "b.py" not in result


# -- documentSymbol fallback --

@pytest.mark.asyncio
async def test_resolve_field_no_client_graceful():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_query(model, reg, "inspect config @file:server.py @line:71")
    assert "not found" in result


# -- find_in_doc_symbols --

def test_find_in_doc_symbols_basic():
    symbols = [DocumentSymbol(
        name="Config",
        kind=SymbolKind.Class,
        range=_range(10, 20),
        selection_range=_range(10, 10),
        children=[DocumentSymbol(
            name="port",
            kind=SymbolKind.Field,
            range=_range(12, 12),
            selection_range=_range(12, 12),
        )],
    )]
    entry = find_in_doc_symbols(symbols, "port", 12)
    assert entry is not None
    assert entry.name == "port"
    assert entry.container_name == "Config"
    assert entry.kind == SymbolKind.Field


def test_find_in_doc_symbols_not_found():
    symbols = [DocumentSymbol(
        name="Config",
        kind=SymbolKind.Class,
        range=_range(10, 20),
        selection_range=_range(10, 10),
    )]
    assert find_in_doc_symbols(symbols, "port", 12) is None


def test_find_by_name_in_doc_symbols_basic():
    symbols = [
        DocumentSymbol(
            name="host",
            kind=SymbolKind.Field,
            range=_range(11, 11),
            selection_range=_range(11, 11),
        ),
        DocumentSymbol(
            name="port",
            kind=SymbolKind.Field,
            range=_range(12, 12),
            selection_range=_range(12, 12),
        ),
    ]
    entry = find_by_name_in_doc_symbols(symbols, "port", "Config")
    assert entry is not None
    assert entry.name == "port"
    assert entry.container_name == "Config"
