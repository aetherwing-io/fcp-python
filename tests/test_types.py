"""Tests for LSP type deserialization."""

from fcp_python.lsp.types import (
    CallHierarchyIncomingCall,
    CallHierarchyItem,
    CallHierarchyOutgoingCall,
    CodeAction,
    Diagnostic,
    DiagnosticSeverity,
    DocumentSymbol,
    Hover,
    JsonRpcError,
    JsonRpcNotification,
    JsonRpcResponse,
    Location,
    MarkupContent,
    Position,
    Range,
    ResourceOperationCreate,
    ResourceOperationDelete,
    ResourceOperationRename,
    SymbolInformation,
    SymbolKind,
    TextEdit,
    VersionedTextDocumentIdentifier,
    WorkspaceEdit,
    document_change_from_dict,
    hover_contents_from_dict,
    resource_operation_from_dict,
)


def test_position_roundtrip():
    pos = Position(line=10, character=5)
    d = pos.to_dict()
    assert d == {"line": 10, "character": 5}
    assert Position.from_dict(d) == pos


def test_range_roundtrip():
    r = Range(start=Position(1, 0), end=Position(1, 10))
    d = r.to_dict()
    assert d["start"]["line"] == 1
    assert d["end"]["character"] == 10
    assert Range.from_dict(d) == r


def test_location_roundtrip():
    loc = Location(
        uri="file:///test.py",
        range=Range(start=Position(0, 0), end=Position(0, 5)),
    )
    d = loc.to_dict()
    assert d["uri"] == "file:///test.py"
    assert Location.from_dict(d) == loc


def test_symbol_kind_values():
    assert int(SymbolKind.Function) == 12
    assert int(SymbolKind.Method) == 6
    assert int(SymbolKind.Struct) == 23
    assert int(SymbolKind.Enum) == 10
    assert SymbolKind(12) == SymbolKind.Function
    assert SymbolKind(23) == SymbolKind.Struct


def test_symbol_kind_display_name():
    assert SymbolKind.Function.display_name() == "function"
    assert SymbolKind.Class.display_name() == "class"
    assert SymbolKind.Variable.display_name() == "variable"


def test_diagnostic_severity_values():
    assert int(DiagnosticSeverity.Error) == 1
    assert int(DiagnosticSeverity.Warning) == 2
    assert int(DiagnosticSeverity.Information) == 3
    assert int(DiagnosticSeverity.Hint) == 4
    assert DiagnosticSeverity(1) == DiagnosticSeverity.Error


def test_symbol_information_from_dict():
    d = {
        "name": "main",
        "kind": 12,
        "location": {
            "uri": "file:///main.py",
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 5, "character": 1}},
        },
    }
    sym = SymbolInformation.from_dict(d)
    assert sym.name == "main"
    assert sym.kind == SymbolKind.Function
    assert sym.container_name is None

    d["containerName"] = "module"
    sym2 = SymbolInformation.from_dict(d)
    assert sym2.container_name == "module"


def test_document_symbol_from_dict():
    d = {
        "name": "MyClass",
        "kind": 5,
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 10, "character": 1}},
        "selectionRange": {"start": {"line": 0, "character": 6}, "end": {"line": 0, "character": 13}},
        "children": [
            {
                "name": "method",
                "kind": 6,
                "range": {"start": {"line": 1, "character": 4}, "end": {"line": 3, "character": 0}},
                "selectionRange": {"start": {"line": 1, "character": 8}, "end": {"line": 1, "character": 14}},
            }
        ],
    }
    ds = DocumentSymbol.from_dict(d)
    assert ds.name == "MyClass"
    assert ds.kind == SymbolKind.Class
    assert ds.children is not None
    assert len(ds.children) == 1
    assert ds.children[0].name == "method"
    assert ds.children[0].kind == SymbolKind.Method


def test_diagnostic_from_dict():
    d = {
        "range": {"start": {"line": 5, "character": 0}, "end": {"line": 5, "character": 10}},
        "severity": 1,
        "code": "E303",
        "source": "pycodestyle",
        "message": "too many blank lines",
    }
    diag = Diagnostic.from_dict(d)
    assert diag.severity == DiagnosticSeverity.Error
    assert diag.message == "too many blank lines"
    assert diag.code == "E303"
    assert diag.source == "pycodestyle"


def test_diagnostic_from_dict_no_severity():
    d = {
        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
        "message": "test",
    }
    diag = Diagnostic.from_dict(d)
    assert diag.severity is None


def test_text_edit_from_dict():
    d = {
        "range": {"start": {"line": 5, "character": 0}, "end": {"line": 5, "character": 6}},
        "newText": "Settings",
    }
    edit = TextEdit.from_dict(d)
    assert edit.new_text == "Settings"
    assert edit.range.start.line == 5


def test_workspace_edit_changes_form():
    d = {
        "changes": {
            "file:///src/main.py": [
                {
                    "range": {"start": {"line": 1, "character": 4}, "end": {"line": 1, "character": 10}},
                    "newText": "Settings",
                }
            ]
        }
    }
    edit = WorkspaceEdit.from_dict(d)
    assert edit.changes is not None
    assert "file:///src/main.py" in edit.changes
    assert len(edit.changes["file:///src/main.py"]) == 1


def test_workspace_edit_document_changes_form():
    d = {
        "documentChanges": [
            {
                "textDocument": {"uri": "file:///src/main.py", "version": 1},
                "edits": [
                    {
                        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 6}},
                        "newText": "Settings",
                    }
                ],
            },
            {"kind": "create", "uri": "file:///src/new.py"},
        ],
    }
    edit = WorkspaceEdit.from_dict(d)
    assert edit.document_changes is not None
    assert len(edit.document_changes) == 2


def test_resource_operation_from_dict():
    create = resource_operation_from_dict({"kind": "create", "uri": "file:///new.py"})
    assert isinstance(create, ResourceOperationCreate)
    assert create.uri == "file:///new.py"

    rename = resource_operation_from_dict({"kind": "rename", "oldUri": "file:///old.py", "newUri": "file:///new.py"})
    assert isinstance(rename, ResourceOperationRename)

    delete = resource_operation_from_dict({"kind": "delete", "uri": "file:///old.py"})
    assert isinstance(delete, ResourceOperationDelete)


def test_hover_contents_string():
    result = hover_contents_from_dict("def main()")
    assert result == "def main()"


def test_hover_contents_markup():
    result = hover_contents_from_dict({"kind": "markdown", "value": "```python\ndef main()\n```"})
    assert isinstance(result, MarkupContent)
    assert result.kind == "markdown"


def test_hover_contents_array():
    result = hover_contents_from_dict(["line1", "line2"])
    assert result == ["line1", "line2"]


def test_hover_from_dict():
    d = {"contents": "def main()", "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 4}}}
    hover = Hover.from_dict(d)
    assert hover.contents == "def main()"
    assert hover.range is not None

    d2 = {"contents": {"kind": "markdown", "value": "test"}}
    hover2 = Hover.from_dict(d2)
    assert isinstance(hover2.contents, MarkupContent)
    assert hover2.range is None


def test_call_hierarchy_item_from_dict():
    d = {
        "name": "process",
        "kind": 12,
        "uri": "file:///lib.py",
        "range": {"start": {"line": 10, "character": 0}, "end": {"line": 20, "character": 1}},
        "selectionRange": {"start": {"line": 10, "character": 4}, "end": {"line": 10, "character": 11}},
    }
    item = CallHierarchyItem.from_dict(d)
    assert item.name == "process"
    assert item.kind == SymbolKind.Function


def test_call_hierarchy_incoming_from_dict():
    d = {
        "from": {
            "name": "caller",
            "kind": 12,
            "uri": "file:///a.py",
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 5, "character": 0}},
            "selectionRange": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 10}},
        },
        "fromRanges": [{"start": {"line": 2, "character": 4}, "end": {"line": 2, "character": 11}}],
    }
    call = CallHierarchyIncomingCall.from_dict(d)
    assert call.from_item.name == "caller"
    assert len(call.from_ranges) == 1


def test_call_hierarchy_outgoing_from_dict():
    d = {
        "to": {
            "name": "callee",
            "kind": 12,
            "uri": "file:///b.py",
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 5, "character": 0}},
            "selectionRange": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 10}},
        },
        "fromRanges": [{"start": {"line": 3, "character": 4}, "end": {"line": 3, "character": 10}}],
    }
    call = CallHierarchyOutgoingCall.from_dict(d)
    assert call.to.name == "callee"


def test_code_action_from_dict():
    d = {
        "title": "Extract function",
        "kind": "refactor.extract.function",
        "edit": {"changes": {}},
        "isPreferred": True,
    }
    action = CodeAction.from_dict(d)
    assert action.title == "Extract function"
    assert action.kind == "refactor.extract.function"
    assert action.is_preferred is True
    assert action.edit is not None


def test_jsonrpc_response_success():
    d = {"id": 1, "result": {"line": 10, "character": 5}}
    resp = JsonRpcResponse.from_dict(d)
    assert resp.id == 1
    assert resp.result is not None
    assert resp.error is None


def test_jsonrpc_response_error():
    d = {"id": 2, "error": {"code": -32600, "message": "Invalid Request"}}
    resp = JsonRpcResponse.from_dict(d)
    assert resp.error is not None
    assert resp.error.code == -32600


def test_jsonrpc_notification():
    d = {"method": "textDocument/publishDiagnostics", "params": {"uri": "file:///test.py"}}
    notif = JsonRpcNotification.from_dict(d)
    assert notif.method == "textDocument/publishDiagnostics"


def test_versioned_text_document_identifier():
    d = {"uri": "file:///test.py", "version": 3}
    vtdi = VersionedTextDocumentIdentifier.from_dict(d)
    assert vtdi.uri == "file:///test.py"
    assert vtdi.version == 3

    d2 = {"uri": "file:///test.py"}
    vtdi2 = VersionedTextDocumentIdentifier.from_dict(d2)
    assert vtdi2.version is None


def test_document_change_from_dict_text_edit():
    d = {
        "textDocument": {"uri": "file:///test.py", "version": 1},
        "edits": [
            {
                "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 6}},
                "newText": "new",
            }
        ],
    }
    from fcp_python.lsp.types import TextDocumentEdit
    change = document_change_from_dict(d)
    assert isinstance(change, TextDocumentEdit)


def test_document_change_from_dict_resource_op():
    d = {"kind": "create", "uri": "file:///new.py"}
    change = document_change_from_dict(d)
    assert isinstance(change, ResourceOperationCreate)
