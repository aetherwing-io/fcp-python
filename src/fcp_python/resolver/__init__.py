"""Resolver layer: symbol indexing, selector filtering, resolution pipeline."""

from fcp_python.resolver.index import SymbolEntry, SymbolIndex
from fcp_python.resolver.selectors import (
    ParsedSelector,
    SelectorType,
    filter_by_selectors,
    parse_line_range,
    parse_selector,
    symbol_kind_from_string,
)
from fcp_python.resolver.pipeline import ResolveResult, SymbolResolver

__all__ = [
    "SymbolEntry",
    "SymbolIndex",
    "ParsedSelector",
    "SelectorType",
    "filter_by_selectors",
    "parse_line_range",
    "parse_selector",
    "symbol_kind_from_string",
    "ResolveResult",
    "SymbolResolver",
]
