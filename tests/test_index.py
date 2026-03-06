"""Tests for SymbolIndex — triple-indexed symbol cache."""

import pytest

from fcp_python.lsp.types import Position, Range, SymbolKind
from fcp_python.resolver.index import SymbolEntry, SymbolIndex


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


class TestInsertAndLookup:
    def test_insert_and_lookup_by_name(self):
        idx = SymbolIndex()
        idx.insert(make_entry("main", SymbolKind.Function, "file:///main.py"))
        results = idx.lookup_by_name("main")
        assert len(results) == 1
        assert results[0].name == "main"

    def test_lookup_by_file(self):
        idx = SymbolIndex()
        idx.insert(make_entry("foo", SymbolKind.Function, "file:///lib.py"))
        idx.insert(make_entry("bar", SymbolKind.Function, "file:///lib.py"))
        idx.insert(make_entry("baz", SymbolKind.Function, "file:///main.py"))
        results = idx.lookup_by_file("file:///lib.py")
        assert len(results) == 2

    def test_lookup_by_container(self):
        idx = SymbolIndex()
        idx.insert(make_entry("method_a", SymbolKind.Method, "file:///lib.py", "MyClass"))
        idx.insert(make_entry("method_b", SymbolKind.Method, "file:///lib.py", "MyClass"))
        results = idx.lookup_by_container("MyClass")
        assert len(results) == 2

    def test_lookup_missing(self):
        idx = SymbolIndex()
        assert idx.lookup_by_name("nonexistent") == []
        assert idx.lookup_by_file("file:///none.py") == []
        assert idx.lookup_by_container("Nothing") == []

    def test_multiple_entries_same_name(self):
        idx = SymbolIndex()
        idx.insert(make_entry("__init__", SymbolKind.Function, "file:///a.py", "A"))
        idx.insert(make_entry("__init__", SymbolKind.Function, "file:///b.py", "B"))
        results = idx.lookup_by_name("__init__")
        assert len(results) == 2


class TestInvalidate:
    def test_invalidate_file(self):
        idx = SymbolIndex()
        idx.insert(make_entry("foo", SymbolKind.Function, "file:///lib.py", "Mod"))
        idx.insert(make_entry("bar", SymbolKind.Function, "file:///main.py"))

        idx.invalidate_file("file:///lib.py")

        assert idx.lookup_by_file("file:///lib.py") == []
        assert idx.lookup_by_name("foo") == []
        assert idx.lookup_by_container("Mod") == []
        assert len(idx.lookup_by_name("bar")) == 1

    def test_invalidate_nonexistent_file(self):
        idx = SymbolIndex()
        idx.insert(make_entry("a", SymbolKind.Function, "file:///a.py"))
        idx.invalidate_file("file:///nonexistent.py")
        assert idx.size() == 1


class TestSize:
    def test_size_empty(self):
        assert SymbolIndex().size() == 0

    def test_size_after_inserts(self):
        idx = SymbolIndex()
        idx.insert(make_entry("a", SymbolKind.Function, "file:///a.py"))
        idx.insert(make_entry("b", SymbolKind.Function, "file:///a.py"))
        idx.insert(make_entry("c", SymbolKind.Function, "file:///b.py"))
        assert idx.size() == 3

    def test_size_after_invalidate(self):
        idx = SymbolIndex()
        idx.insert(make_entry("a", SymbolKind.Function, "file:///a.py"))
        idx.insert(make_entry("b", SymbolKind.Function, "file:///b.py"))
        assert idx.size() == 2
        idx.invalidate_file("file:///a.py")
        assert idx.size() == 1
