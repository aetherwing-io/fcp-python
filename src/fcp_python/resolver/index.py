"""Triple-indexed symbol cache for fast resolution lookups."""

from __future__ import annotations

from dataclasses import dataclass, field

from fcp_python.lsp.types import Range, SymbolKind


@dataclass
class SymbolEntry:
    name: str
    kind: SymbolKind
    container_name: str | None
    uri: str
    range: Range
    selection_range: Range


class SymbolIndex:
    """Triple-indexed symbol store: by name, by file URI, by container."""

    def __init__(self) -> None:
        self._by_name: dict[str, list[SymbolEntry]] = {}
        self._by_file: dict[str, list[SymbolEntry]] = {}
        self._by_container: dict[str, list[SymbolEntry]] = {}

    def insert(self, entry: SymbolEntry) -> None:
        self._by_name.setdefault(entry.name, []).append(entry)
        self._by_file.setdefault(entry.uri, []).append(entry)
        if entry.container_name is not None:
            self._by_container.setdefault(entry.container_name, []).append(entry)

    def lookup_by_name(self, name: str) -> list[SymbolEntry]:
        return list(self._by_name.get(name, []))

    def lookup_by_file(self, uri: str) -> list[SymbolEntry]:
        return list(self._by_file.get(uri, []))

    def lookup_by_container(self, container: str) -> list[SymbolEntry]:
        return list(self._by_container.get(container, []))

    def invalidate_file(self, uri: str) -> None:
        self._by_file.pop(uri, None)

        for entries in self._by_name.values():
            entries[:] = [e for e in entries if e.uri != uri]
        self._by_name = {k: v for k, v in self._by_name.items() if v}

        for entries in self._by_container.values():
            entries[:] = [e for e in entries if e.uri != uri]
        self._by_container = {k: v for k, v in self._by_container.items() if v}

    def size(self) -> int:
        return sum(len(v) for v in self._by_file.values())
