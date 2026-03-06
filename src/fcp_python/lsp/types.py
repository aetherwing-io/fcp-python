"""LSP 3.17 type definitions — hand-rolled subset."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Union


@dataclass
class Position:
    line: int
    character: int

    def to_dict(self) -> dict:
        return {"line": self.line, "character": self.character}

    @classmethod
    def from_dict(cls, d: dict) -> Position:
        return cls(line=d["line"], character=d["character"])


@dataclass
class Range:
    start: Position
    end: Position

    def to_dict(self) -> dict:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> Range:
        return cls(start=Position.from_dict(d["start"]), end=Position.from_dict(d["end"]))


@dataclass
class Location:
    uri: str
    range: Range

    def to_dict(self) -> dict:
        return {"uri": self.uri, "range": self.range.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> Location:
        return cls(uri=d["uri"], range=Range.from_dict(d["range"]))


class SymbolKind(IntEnum):
    File = 1
    Module = 2
    Namespace = 3
    Package = 4
    Class = 5
    Method = 6
    Property = 7
    Field = 8
    Constructor = 9
    Enum = 10
    Interface = 11
    Function = 12
    Variable = 13
    Constant = 14
    String = 15
    Number = 16
    Boolean = 17
    Array = 18
    Object = 19
    Key = 20
    Null = 21
    EnumMember = 22
    Struct = 23
    Event = 24
    Operator = 25
    TypeParameter = 26

    def display_name(self) -> str:
        return self.name.lower()

    @classmethod
    def from_value(cls, value: int) -> SymbolKind:
        try:
            return cls(value)
        except ValueError:
            # Return as-is for unknown values; store in Variable as fallback
            return cls(value)


class DiagnosticSeverity(IntEnum):
    Error = 1
    Warning = 2
    Information = 3
    Hint = 4


@dataclass
class SymbolInformation:
    name: str
    kind: SymbolKind
    location: Location
    container_name: str | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "name": self.name,
            "kind": int(self.kind),
            "location": self.location.to_dict(),
        }
        if self.container_name is not None:
            d["containerName"] = self.container_name
        return d

    @classmethod
    def from_dict(cls, d: dict) -> SymbolInformation:
        return cls(
            name=d["name"],
            kind=SymbolKind(d["kind"]),
            location=Location.from_dict(d["location"]),
            container_name=d.get("containerName"),
        )


@dataclass
class DocumentSymbol:
    name: str
    kind: SymbolKind
    range: Range
    selection_range: Range
    children: list[DocumentSymbol] | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "name": self.name,
            "kind": int(self.kind),
            "range": self.range.to_dict(),
            "selectionRange": self.selection_range.to_dict(),
        }
        if self.children is not None:
            d["children"] = [c.to_dict() for c in self.children]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> DocumentSymbol:
        children = None
        if "children" in d and d["children"] is not None:
            children = [DocumentSymbol.from_dict(c) for c in d["children"]]
        return cls(
            name=d["name"],
            kind=SymbolKind(d["kind"]),
            range=Range.from_dict(d["range"]),
            selection_range=Range.from_dict(d["selectionRange"]),
            children=children,
        )


@dataclass
class Diagnostic:
    range: Range
    message: str
    severity: DiagnosticSeverity | None = None
    code: Any = None
    source: str | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "range": self.range.to_dict(),
            "message": self.message,
        }
        if self.severity is not None:
            d["severity"] = int(self.severity)
        if self.code is not None:
            d["code"] = self.code
        if self.source is not None:
            d["source"] = self.source
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Diagnostic:
        severity = None
        if "severity" in d and d["severity"] is not None:
            severity = DiagnosticSeverity(d["severity"])
        return cls(
            range=Range.from_dict(d["range"]),
            message=d["message"],
            severity=severity,
            code=d.get("code"),
            source=d.get("source"),
        )


@dataclass
class PublishDiagnosticsParams:
    uri: str
    diagnostics: list[Diagnostic]

    @classmethod
    def from_dict(cls, d: dict) -> PublishDiagnosticsParams:
        return cls(
            uri=d["uri"],
            diagnostics=[Diagnostic.from_dict(diag) for diag in d["diagnostics"]],
        )


@dataclass
class TextEdit:
    range: Range
    new_text: str

    def to_dict(self) -> dict:
        return {"range": self.range.to_dict(), "newText": self.new_text}

    @classmethod
    def from_dict(cls, d: dict) -> TextEdit:
        return cls(range=Range.from_dict(d["range"]), new_text=d["newText"])


@dataclass
class VersionedTextDocumentIdentifier:
    uri: str
    version: int | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"uri": self.uri}
        if self.version is not None:
            d["version"] = self.version
        return d

    @classmethod
    def from_dict(cls, d: dict) -> VersionedTextDocumentIdentifier:
        return cls(uri=d["uri"], version=d.get("version"))


@dataclass
class TextDocumentEdit:
    text_document: VersionedTextDocumentIdentifier
    edits: list[TextEdit]

    def to_dict(self) -> dict:
        return {
            "textDocument": self.text_document.to_dict(),
            "edits": [e.to_dict() for e in self.edits],
        }

    @classmethod
    def from_dict(cls, d: dict) -> TextDocumentEdit:
        return cls(
            text_document=VersionedTextDocumentIdentifier.from_dict(d["textDocument"]),
            edits=[TextEdit.from_dict(e) for e in d["edits"]],
        )


@dataclass
class ResourceOperationCreate:
    uri: str
    kind: str = "create"

    def to_dict(self) -> dict:
        return {"kind": "create", "uri": self.uri}

    @classmethod
    def from_dict(cls, d: dict) -> ResourceOperationCreate:
        return cls(uri=d["uri"])


@dataclass
class ResourceOperationRename:
    old_uri: str
    new_uri: str
    kind: str = "rename"

    def to_dict(self) -> dict:
        return {"kind": "rename", "oldUri": self.old_uri, "newUri": self.new_uri}

    @classmethod
    def from_dict(cls, d: dict) -> ResourceOperationRename:
        return cls(old_uri=d["oldUri"], new_uri=d["newUri"])


@dataclass
class ResourceOperationDelete:
    uri: str
    kind: str = "delete"

    def to_dict(self) -> dict:
        return {"kind": "delete", "uri": self.uri}

    @classmethod
    def from_dict(cls, d: dict) -> ResourceOperationDelete:
        return cls(uri=d["uri"])


ResourceOperation = Union[ResourceOperationCreate, ResourceOperationRename, ResourceOperationDelete]


def resource_operation_from_dict(d: dict) -> ResourceOperation:
    kind = d["kind"]
    if kind == "create":
        return ResourceOperationCreate.from_dict(d)
    elif kind == "rename":
        return ResourceOperationRename.from_dict(d)
    elif kind == "delete":
        return ResourceOperationDelete.from_dict(d)
    else:
        raise ValueError(f"unknown resource operation kind: {kind}")


# DocumentChange is either a TextDocumentEdit or a ResourceOperation
DocumentChange = Union[TextDocumentEdit, ResourceOperation]


def document_change_from_dict(d: dict) -> DocumentChange:
    """Parse a document change from LSP JSON. If it has 'kind', it's a resource op; otherwise a text edit."""
    if "kind" in d:
        return resource_operation_from_dict(d)
    return TextDocumentEdit.from_dict(d)


@dataclass
class WorkspaceEdit:
    changes: dict[str, list[TextEdit]] | None = None
    document_changes: list[DocumentChange] | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {}
        if self.changes is not None:
            d["changes"] = {
                uri: [e.to_dict() for e in edits] for uri, edits in self.changes.items()
            }
        if self.document_changes is not None:
            d["documentChanges"] = [
                c.to_dict() for c in self.document_changes  # type: ignore[union-attr]
            ]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> WorkspaceEdit:
        changes = None
        if "changes" in d and d["changes"] is not None:
            changes = {
                uri: [TextEdit.from_dict(e) for e in edits]
                for uri, edits in d["changes"].items()
            }
        document_changes = None
        if "documentChanges" in d and d["documentChanges"] is not None:
            document_changes = [document_change_from_dict(dc) for dc in d["documentChanges"]]
        return cls(changes=changes, document_changes=document_changes)


@dataclass
class MarkupContent:
    kind: str
    value: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> MarkupContent:
        return cls(kind=d["kind"], value=d["value"])


# HoverContents: str | MarkupContent | list[str]
HoverContents = Union[str, MarkupContent, list[str]]


def hover_contents_from_dict(d: Any) -> HoverContents:
    if isinstance(d, str):
        return d
    if isinstance(d, list):
        return [str(item) for item in d]
    if isinstance(d, dict) and "kind" in d and "value" in d:
        return MarkupContent.from_dict(d)
    raise ValueError(f"cannot parse HoverContents from: {d!r}")


@dataclass
class Hover:
    contents: HoverContents
    range: Range | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Hover:
        range_ = Range.from_dict(d["range"]) if "range" in d and d["range"] is not None else None
        return cls(contents=hover_contents_from_dict(d["contents"]), range=range_)


@dataclass
class CallHierarchyItem:
    name: str
    kind: SymbolKind
    uri: str
    range: Range
    selection_range: Range

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": int(self.kind),
            "uri": self.uri,
            "range": self.range.to_dict(),
            "selectionRange": self.selection_range.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> CallHierarchyItem:
        return cls(
            name=d["name"],
            kind=SymbolKind(d["kind"]),
            uri=d["uri"],
            range=Range.from_dict(d["range"]),
            selection_range=Range.from_dict(d["selectionRange"]),
        )


@dataclass
class CallHierarchyIncomingCall:
    from_item: CallHierarchyItem
    from_ranges: list[Range]

    @classmethod
    def from_dict(cls, d: dict) -> CallHierarchyIncomingCall:
        return cls(
            from_item=CallHierarchyItem.from_dict(d["from"]),
            from_ranges=[Range.from_dict(r) for r in d["fromRanges"]],
        )


@dataclass
class CallHierarchyOutgoingCall:
    to: CallHierarchyItem
    from_ranges: list[Range]

    @classmethod
    def from_dict(cls, d: dict) -> CallHierarchyOutgoingCall:
        return cls(
            to=CallHierarchyItem.from_dict(d["to"]),
            from_ranges=[Range.from_dict(r) for r in d["fromRanges"]],
        )


@dataclass
class CodeAction:
    title: str
    kind: str | None = None
    edit: WorkspaceEdit | None = None
    is_preferred: bool | None = None

    @classmethod
    def from_dict(cls, d: dict) -> CodeAction:
        edit = WorkspaceEdit.from_dict(d["edit"]) if "edit" in d and d["edit"] is not None else None
        return cls(
            title=d["title"],
            kind=d.get("kind"),
            edit=edit,
            is_preferred=d.get("isPreferred"),
        )


@dataclass
class ServerCapabilities:
    raw: dict = field(default_factory=dict)

    def get(self, key: str) -> Any:
        return self.raw.get(key)

    @classmethod
    def from_dict(cls, d: dict) -> ServerCapabilities:
        return cls(raw=d)


@dataclass
class InitializeResult:
    capabilities: ServerCapabilities

    @classmethod
    def from_dict(cls, d: dict) -> InitializeResult:
        return cls(capabilities=ServerCapabilities.from_dict(d.get("capabilities", {})))


@dataclass
class JsonRpcError:
    code: int
    message: str
    data: Any = None

    @classmethod
    def from_dict(cls, d: dict) -> JsonRpcError:
        return cls(code=d["code"], message=d["message"], data=d.get("data"))


@dataclass
class JsonRpcResponse:
    id: Any
    result: Any = None
    error: JsonRpcError | None = None

    @classmethod
    def from_dict(cls, d: dict) -> JsonRpcResponse:
        error = JsonRpcError.from_dict(d["error"]) if d.get("error") else None
        return cls(id=d.get("id"), result=d.get("result"), error=error)


@dataclass
class JsonRpcNotification:
    method: str
    params: Any = None

    @classmethod
    def from_dict(cls, d: dict) -> JsonRpcNotification:
        return cls(method=d["method"], params=d.get("params"))
