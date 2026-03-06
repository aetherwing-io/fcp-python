"""Selector parsing and filtering for symbol resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from fcp_python.lsp.types import SymbolInformation, SymbolKind


class SelectorType(Enum):
    FILE = "file"
    CLASS = "class"
    KIND = "kind"
    MODULE = "module"
    LINE = "line"
    LINES = "lines"
    DECORATOR = "decorator"


@dataclass
class ParsedSelector:
    selector_type: SelectorType
    value: str


def parse_selector(selector: str) -> ParsedSelector | None:
    """Parse @type:value selector string.

    Maps: @file:PATH, @class:NAME (@struct:NAME alias),
    @kind:KIND, @module:NAME (@mod:NAME alias),
    @line:N, @lines:N-M, @decorator:NAME
    """
    if not selector.startswith("@"):
        return None

    rest = selector[1:]
    colon_idx = rest.find(":")
    if colon_idx == -1:
        return None

    type_str = rest[:colon_idx]
    value = rest[colon_idx + 1:]

    type_map: dict[str, SelectorType] = {
        "file": SelectorType.FILE,
        "class": SelectorType.CLASS,
        "struct": SelectorType.CLASS,  # Rust compat alias
        "kind": SelectorType.KIND,
        "module": SelectorType.MODULE,
        "mod": SelectorType.MODULE,
        "line": SelectorType.LINE,
        "lines": SelectorType.LINES,
        "decorator": SelectorType.DECORATOR,
    }

    selector_type = type_map.get(type_str)
    if selector_type is None:
        return None

    return ParsedSelector(selector_type=selector_type, value=value)


def filter_by_selectors(
    symbols: list[SymbolInformation],
    selectors: list[ParsedSelector],
) -> list[SymbolInformation]:
    """Filter symbols by selectors (AND logic)."""
    return [
        sym for sym in symbols
        if all(_matches_selector(sym, sel) for sel in selectors)
    ]


def _matches_selector(sym: SymbolInformation, sel: ParsedSelector) -> bool:
    match sel.selector_type:
        case SelectorType.FILE:
            return sel.value in sym.location.uri
        case SelectorType.CLASS:
            return (
                sym.container_name == sel.value
                or (sym.name == sel.value and sym.kind == SymbolKind.Class)
            )
        case SelectorType.KIND:
            kind = symbol_kind_from_string(sel.value)
            return kind is not None and sym.kind == kind
        case SelectorType.MODULE:
            container_match = (
                sym.container_name is not None and sel.value in sym.container_name
            )
            return container_match or sel.value in sym.location.uri
        case SelectorType.LINE:
            try:
                line = int(sel.value)
            except ValueError:
                return False
            return sym.location.range.start.line <= line <= sym.location.range.end.line
        case SelectorType.LINES:
            # Consumed by mutation handlers, not symbol filtering
            return True
        case SelectorType.DECORATOR:
            # Would need AST analysis; pass-through for now
            return True


def parse_line_range(value: str) -> tuple[int, int] | None:
    """Parse '15-30' into (15, 30). Returns None if invalid."""
    parts = value.split("-", 1)
    if len(parts) != 2:
        return None
    try:
        start = int(parts[0])
        end = int(parts[1])
    except ValueError:
        return None
    if start > end:
        return None
    return (start, end)


def symbol_kind_from_string(s: str) -> SymbolKind | None:
    """Convert string to SymbolKind. Python-specific additions included."""
    mapping: dict[str, SymbolKind] = {
        "function": SymbolKind.Function,
        "fn": SymbolKind.Function,
        "def": SymbolKind.Function,
        "method": SymbolKind.Method,
        "class": SymbolKind.Class,
        "struct": SymbolKind.Struct,
        "enum": SymbolKind.Enum,
        "interface": SymbolKind.Interface,
        "trait": SymbolKind.Interface,
        "variable": SymbolKind.Variable,
        "var": SymbolKind.Variable,
        "constant": SymbolKind.Constant,
        "const": SymbolKind.Constant,
        "property": SymbolKind.Property,
        "module": SymbolKind.Module,
        "mod": SymbolKind.Module,
        "namespace": SymbolKind.Namespace,
        "field": SymbolKind.Field,
        "constructor": SymbolKind.Constructor,
        "type_parameter": SymbolKind.TypeParameter,
        "typeparameter": SymbolKind.TypeParameter,
        "file": SymbolKind.File,
        "package": SymbolKind.Package,
        "string": SymbolKind.String,
        "number": SymbolKind.Number,
        "boolean": SymbolKind.Boolean,
        "bool": SymbolKind.Boolean,
        "array": SymbolKind.Array,
        "object": SymbolKind.Object,
        "key": SymbolKind.Key,
        "null": SymbolKind.Null,
        "enum_member": SymbolKind.EnumMember,
        "enummember": SymbolKind.EnumMember,
        "event": SymbolKind.Event,
        "operator": SymbolKind.Operator,
        "decorator": SymbolKind.Function,  # decorators are functions
    }
    return mapping.get(s.lower())
