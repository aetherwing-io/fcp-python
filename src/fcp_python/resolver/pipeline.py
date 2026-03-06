"""3-tier symbol resolution pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from fcp_python.lsp.types import Location, SymbolInformation
from fcp_python.resolver.index import SymbolEntry, SymbolIndex
from fcp_python.resolver.selectors import ParsedSelector, filter_by_selectors


class _ResultKind(Enum):
    FOUND = auto()
    AMBIGUOUS = auto()
    NOT_FOUND = auto()


class ResolveResult:
    """Tagged union: Found(entry), Ambiguous(entries), NotFound."""

    def __init__(self, kind: _ResultKind, entry: SymbolEntry | None = None, entries: list[SymbolEntry] | None = None):
        self._kind = kind
        self._entry = entry
        self._entries = entries

    @staticmethod
    def found(entry: SymbolEntry) -> ResolveResult:
        return ResolveResult(_ResultKind.FOUND, entry=entry)

    @staticmethod
    def ambiguous(entries: list[SymbolEntry]) -> ResolveResult:
        return ResolveResult(_ResultKind.AMBIGUOUS, entries=entries)

    @staticmethod
    def not_found() -> ResolveResult:
        return ResolveResult(_ResultKind.NOT_FOUND)

    @property
    def is_found(self) -> bool:
        return self._kind == _ResultKind.FOUND

    @property
    def is_ambiguous(self) -> bool:
        return self._kind == _ResultKind.AMBIGUOUS

    @property
    def is_not_found(self) -> bool:
        return self._kind == _ResultKind.NOT_FOUND

    @property
    def entry(self) -> SymbolEntry:
        assert self._kind == _ResultKind.FOUND and self._entry is not None
        return self._entry

    @property
    def entries(self) -> list[SymbolEntry]:
        assert self._kind == _ResultKind.AMBIGUOUS and self._entries is not None
        return self._entries


def _entry_to_symbol_info(entry: SymbolEntry) -> SymbolInformation:
    return SymbolInformation(
        name=entry.name,
        kind=entry.kind,
        location=Location(uri=entry.uri, range=entry.range),
        container_name=entry.container_name,
    )


class SymbolResolver:
    """Multi-tier symbol resolver."""

    def __init__(self, index: SymbolIndex) -> None:
        self._index = index

    def resolve_from_index(
        self,
        name: str,
        selectors: list[ParsedSelector],
    ) -> ResolveResult:
        """Tier 1: resolve from in-memory index with selector filtering."""
        entries = self._index.lookup_by_name(name)

        if not entries:
            return ResolveResult.not_found()

        if selectors:
            sym_infos = [_entry_to_symbol_info(e) for e in entries]
            filtered_infos = filter_by_selectors(sym_infos, selectors)
            # Map back to entries by matching indices
            filtered_info_set = set(id(si) for si in filtered_infos)
            filtered = [
                e for e, si in zip(entries, sym_infos)
                if id(si) in filtered_info_set
            ]
        else:
            filtered = entries

        if len(filtered) == 0:
            return ResolveResult.not_found()
        elif len(filtered) == 1:
            return ResolveResult.found(filtered[0])
        else:
            return ResolveResult.ambiguous(filtered)
