"""Tests for PythonModel."""

import pytest

from fcp_python.domain.model import PythonModel
from fcp_python.lsp.lifecycle import ServerStatus
from fcp_python.lsp.types import Diagnostic, DiagnosticSeverity, Position, Range


def _make_diag(severity: DiagnosticSeverity, message: str) -> Diagnostic:
    return Diagnostic(
        range=Range(
            start=Position(line=0, character=0),
            end=Position(line=0, character=10),
        ),
        severity=severity,
        message=message,
    )


class TestPythonModel:
    def test_new_model(self):
        model = PythonModel("file:///project")
        assert model.root_uri == "file:///project"
        assert model.lsp_client is None
        assert model.symbol_index.size() == 0
        assert model.diagnostics == {}
        assert model.open_documents == {}
        assert model.server_status == ServerStatus.NotStarted
        assert model.py_file_count == 0
        assert model.last_reload is None

    def test_update_diagnostics(self):
        model = PythonModel("file:///project")
        diags = [
            _make_diag(DiagnosticSeverity.Error, "type mismatch"),
            _make_diag(DiagnosticSeverity.Warning, "unused variable"),
        ]
        model.update_diagnostics("file:///main.py", diags)
        assert len(model.diagnostics) == 1
        assert len(model.diagnostics["file:///main.py"]) == 2

    def test_update_diagnostics_empty_removes(self):
        model = PythonModel("file:///project")
        model.update_diagnostics(
            "file:///main.py",
            [_make_diag(DiagnosticSeverity.Error, "err")],
        )
        assert len(model.diagnostics) == 1
        model.update_diagnostics("file:///main.py", [])
        assert len(model.diagnostics) == 0

    def test_total_diagnostics(self):
        model = PythonModel("file:///project")
        model.update_diagnostics(
            "file:///a.py",
            [
                _make_diag(DiagnosticSeverity.Error, "e1"),
                _make_diag(DiagnosticSeverity.Error, "e2"),
                _make_diag(DiagnosticSeverity.Warning, "w1"),
            ],
        )
        model.update_diagnostics(
            "file:///b.py",
            [_make_diag(DiagnosticSeverity.Warning, "w2")],
        )
        errors, warnings = model.total_diagnostics()
        assert errors == 2
        assert warnings == 2

    def test_diagnostic_count(self):
        model = PythonModel("file:///project")
        assert model.diagnostic_count() == 0
        model.update_diagnostics(
            "file:///a.py",
            [
                _make_diag(DiagnosticSeverity.Error, "e1"),
                _make_diag(DiagnosticSeverity.Warning, "w1"),
            ],
        )
        model.update_diagnostics(
            "file:///b.py",
            [_make_diag(DiagnosticSeverity.Error, "e2")],
        )
        assert model.diagnostic_count() == 3
