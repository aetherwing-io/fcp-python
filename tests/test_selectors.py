"""Tests for selector parsing and filtering."""

import pytest

from fcp_python.lsp.types import Location, Position, Range, SymbolInformation, SymbolKind
from fcp_python.resolver.selectors import (
    ParsedSelector,
    SelectorType,
    filter_by_selectors,
    parse_line_range,
    parse_selector,
    symbol_kind_from_string,
)


def make_sym(
    name: str,
    kind: SymbolKind,
    uri: str,
    container: str | None = None,
    start_line: int = 0,
    end_line: int = 5,
) -> SymbolInformation:
    return SymbolInformation(
        name=name,
        kind=kind,
        location=Location(
            uri=uri,
            range=Range(
                start=Position(line=start_line, character=0),
                end=Position(line=end_line, character=0),
            ),
        ),
        container_name=container,
    )


class TestParseSelector:
    def test_file_selector(self):
        sel = parse_selector("@file:main.py")
        assert sel is not None
        assert sel.selector_type == SelectorType.FILE
        assert sel.value == "main.py"

    def test_class_selector(self):
        sel = parse_selector("@class:MyClass")
        assert sel is not None
        assert sel.selector_type == SelectorType.CLASS
        assert sel.value == "MyClass"

    def test_struct_maps_to_class(self):
        sel = parse_selector("@struct:MyClass")
        assert sel is not None
        assert sel.selector_type == SelectorType.CLASS
        assert sel.value == "MyClass"

    def test_kind_selector(self):
        sel = parse_selector("@kind:function")
        assert sel is not None
        assert sel.selector_type == SelectorType.KIND
        assert sel.value == "function"

    def test_module_selector(self):
        sel = parse_selector("@module:utils")
        assert sel is not None
        assert sel.selector_type == SelectorType.MODULE
        assert sel.value == "utils"

    def test_mod_alias(self):
        sel = parse_selector("@mod:utils")
        assert sel is not None
        assert sel.selector_type == SelectorType.MODULE
        assert sel.value == "utils"

    def test_line_selector(self):
        sel = parse_selector("@line:42")
        assert sel is not None
        assert sel.selector_type == SelectorType.LINE
        assert sel.value == "42"

    def test_lines_selector(self):
        sel = parse_selector("@lines:15-30")
        assert sel is not None
        assert sel.selector_type == SelectorType.LINES
        assert sel.value == "15-30"

    def test_decorator_selector(self):
        sel = parse_selector("@decorator:property")
        assert sel is not None
        assert sel.selector_type == SelectorType.DECORATOR
        assert sel.value == "property"

    def test_unknown_type(self):
        assert parse_selector("@unknown:value") is None

    def test_no_at_prefix(self):
        assert parse_selector("file:main.py") is None

    def test_no_colon(self):
        assert parse_selector("@file") is None


class TestParseLineRange:
    def test_valid_range(self):
        assert parse_line_range("15-30") == (15, 30)

    def test_same_start_end(self):
        assert parse_line_range("1-1") == (1, 1)

    def test_reversed_range(self):
        assert parse_line_range("30-15") is None

    def test_not_a_range(self):
        assert parse_line_range("abc") is None

    def test_single_number(self):
        assert parse_line_range("15") is None


class TestSymbolKindFromString:
    def test_function_aliases(self):
        assert symbol_kind_from_string("function") == SymbolKind.Function
        assert symbol_kind_from_string("fn") == SymbolKind.Function
        assert symbol_kind_from_string("def") == SymbolKind.Function

    def test_class(self):
        assert symbol_kind_from_string("class") == SymbolKind.Class

    def test_various_kinds(self):
        assert symbol_kind_from_string("struct") == SymbolKind.Struct
        assert symbol_kind_from_string("enum") == SymbolKind.Enum
        assert symbol_kind_from_string("trait") == SymbolKind.Interface
        assert symbol_kind_from_string("method") == SymbolKind.Method
        assert symbol_kind_from_string("module") == SymbolKind.Module
        assert symbol_kind_from_string("constant") == SymbolKind.Constant
        assert symbol_kind_from_string("variable") == SymbolKind.Variable
        assert symbol_kind_from_string("field") == SymbolKind.Field
        assert symbol_kind_from_string("property") == SymbolKind.Property

    def test_decorator_maps_to_function(self):
        assert symbol_kind_from_string("decorator") == SymbolKind.Function

    def test_case_insensitive(self):
        assert symbol_kind_from_string("Function") == SymbolKind.Function
        assert symbol_kind_from_string("CLASS") == SymbolKind.Class

    def test_unknown(self):
        assert symbol_kind_from_string("unknown") is None


class TestFilterBySelectors:
    def test_filter_by_file(self):
        syms = [
            make_sym("foo", SymbolKind.Function, "file:///lib.py"),
            make_sym("bar", SymbolKind.Function, "file:///main.py"),
        ]
        sel = [parse_selector("@file:main.py")]
        result = filter_by_selectors(syms, [s for s in sel if s])
        assert len(result) == 1
        assert result[0].name == "bar"

    def test_filter_by_kind(self):
        syms = [
            make_sym("MyClass", SymbolKind.Class, "file:///lib.py", start_line=0, end_line=10),
            make_sym("foo", SymbolKind.Function, "file:///lib.py", start_line=12, end_line=20),
        ]
        sel = [parse_selector("@kind:function")]
        result = filter_by_selectors(syms, [s for s in sel if s])
        assert len(result) == 1
        assert result[0].name == "foo"

    def test_filter_by_class(self):
        syms = [
            make_sym("method_a", SymbolKind.Method, "file:///lib.py", "MyClass", 5, 10),
            make_sym("method_b", SymbolKind.Method, "file:///lib.py", "Other", 15, 20),
        ]
        sel = [parse_selector("@class:MyClass")]
        result = filter_by_selectors(syms, [s for s in sel if s])
        assert len(result) == 1
        assert result[0].name == "method_a"

    def test_filter_by_multiple_selectors(self):
        syms = [
            make_sym("foo", SymbolKind.Function, "file:///lib.py"),
            make_sym("bar", SymbolKind.Function, "file:///main.py"),
            make_sym("Baz", SymbolKind.Class, "file:///main.py", start_line=10, end_line=20),
        ]
        sels = [parse_selector("@file:main.py"), parse_selector("@kind:function")]
        result = filter_by_selectors(syms, [s for s in sels if s])
        assert len(result) == 1
        assert result[0].name == "bar"

    def test_filter_by_line(self):
        syms = [
            make_sym("foo", SymbolKind.Function, "file:///lib.py", start_line=0, end_line=5),
            make_sym("bar", SymbolKind.Function, "file:///lib.py", start_line=10, end_line=20),
        ]
        sel = [parse_selector("@line:15")]
        result = filter_by_selectors(syms, [s for s in sel if s])
        assert len(result) == 1
        assert result[0].name == "bar"

    def test_lines_passes_all(self):
        syms = [
            make_sym("foo", SymbolKind.Function, "file:///lib.py"),
            make_sym("bar", SymbolKind.Function, "file:///lib.py"),
        ]
        sel = [parse_selector("@lines:5-10")]
        result = filter_by_selectors(syms, [s for s in sel if s])
        assert len(result) == 2

    def test_decorator_passes_all(self):
        syms = [make_sym("foo", SymbolKind.Function, "file:///lib.py")]
        sel = [parse_selector("@decorator:property")]
        result = filter_by_selectors(syms, [s for s in sel if s])
        assert len(result) == 1
