"""Domain model for Python workspace."""

from __future__ import annotations

import time

from fcp_python.lsp.client import LspClient
from fcp_python.lsp.lifecycle import ServerStatus
from fcp_python.lsp.types import Diagnostic, DiagnosticSeverity
from fcp_python.resolver.index import SymbolIndex


class PythonModel:
    def __init__(self, root_uri: str) -> None:
        self.root_uri = root_uri
        self.lsp_client: LspClient | None = None
        self.symbol_index = SymbolIndex()
        self.diagnostics: dict[str, list[Diagnostic]] = {}
        self.open_documents: dict[str, int] = {}  # uri -> version
        self.server_status = ServerStatus.NotStarted
        self.py_file_count = 0
        self.last_reload: float | None = None

    def update_diagnostics(self, uri: str, diagnostics: list[Diagnostic]) -> None:
        if not diagnostics:
            self.diagnostics.pop(uri, None)
        else:
            self.diagnostics[uri] = diagnostics

    def total_diagnostics(self) -> tuple[int, int]:
        errors = 0
        warnings = 0
        for diags in self.diagnostics.values():
            for d in diags:
                if d.severity == DiagnosticSeverity.Error:
                    errors += 1
                elif d.severity == DiagnosticSeverity.Warning:
                    warnings += 1
        return (errors, warnings)

    def diagnostic_count(self) -> int:
        return sum(len(v) for v in self.diagnostics.values())
