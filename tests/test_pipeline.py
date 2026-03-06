"""Tests for the symbol resolution pipeline."""

import pytest

from fcp_python.lsp.types import Position, Range, SymbolKind
from fcp_python.resolver.index import SymbolEntry, SymbolIndex
from fcp_python.resolver.pipeline import ResolveResult, SymbolResolver
from fcp_python.resolver.selectors import parse_selector


def make_range(line: int) -> Range:
    return Range(start=Position(line=line, character=0), end=Position(line=line, character=10))


def make_entry(name: str, kind: SymbolKind, uri: str, container: str | None = None) -> SymbolEntry:
    return SymbolEntry(
        name=name,
        kind=kind,
        container_name=container,
        uri=uri,
        range=make_range(0),
        selection_range=make_range(0),
    )


class TestResolveFromIndex:
    def test_found(self):
        index = SymbolIndex()
        index.insert(make_entry("main", SymbolKind.Function, "file:///main.py"))

        resolver = SymbolResolver(index)
        result = resolver.resolve_from_index("main", [])
        assert result.is_found
        assert result.entry.name == "main"

    def test_not_found(self):
        index = SymbolIndex()
        resolver = SymbolResolver(index)
        result = resolver.resolve_from_index("nonexistent", [])
        assert result.is_not_found

    def test_ambiguous(self):
        index = SymbolIndex()
        index.insert(make_entry("__init__", SymbolKind.Function, "file:///a.py", "A"))
        index.insert(make_entry("__init__", SymbolKind.Function, "file:///b.py", "B"))

        resolver = SymbolResolver(index)
        result = resolver.resolve_from_index("__init__", [])
        assert result.is_ambiguous
        assert len(result.entries) == 2

    def test_with_file_selector(self):
        index = SymbolIndex()
        index.insert(make_entry("__init__", SymbolKind.Function, "file:///a.py", "A"))
        index.insert(make_entry("__init__", SymbolKind.Function, "file:///b.py", "B"))

        resolver = SymbolResolver(index)
        selectors = [parse_selector("@file:a.py")]
        result = resolver.resolve_from_index("__init__", [s for s in selectors if s])
        assert result.is_found
        assert result.entry.name == "__init__"
        assert "a.py" in result.entry.uri

    def test_selectors_filter_to_none(self):
        index = SymbolIndex()
        index.insert(make_entry("foo", SymbolKind.Function, "file:///a.py"))

        resolver = SymbolResolver(index)
        selectors = [parse_selector("@file:nonexistent.py")]
        result = resolver.resolve_from_index("foo", [s for s in selectors if s])
        assert result.is_not_found

    def test_with_class_selector(self):
        index = SymbolIndex()
        index.insert(make_entry("process", SymbolKind.Method, "file:///a.py", "Handler"))
        index.insert(make_entry("process", SymbolKind.Method, "file:///a.py", "Worker"))

        resolver = SymbolResolver(index)
        selectors = [parse_selector("@class:Handler")]
        result = resolver.resolve_from_index("process", [s for s in selectors if s])
        assert result.is_found
        assert result.entry.container_name == "Handler"
