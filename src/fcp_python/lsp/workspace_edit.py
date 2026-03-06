"""Apply WorkspaceEdit to the filesystem — pure client-side logic."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from .types import (
    Position,
    ResourceOperationCreate,
    ResourceOperationDelete,
    ResourceOperationRename,
    TextDocumentEdit,
    TextEdit,
    WorkspaceEdit,
)


@dataclass
class ApplyResult:
    """Result of applying a WorkspaceEdit to the filesystem."""

    files_changed: list[tuple[str, int]] = field(default_factory=list)
    files_created: list[str] = field(default_factory=list)
    files_renamed: list[tuple[str, str]] = field(default_factory=list)

    def total_edits(self) -> int:
        return sum(count for _, count in self.files_changed)


def position_to_offset(content: str, pos: Position) -> int | None:
    """Convert an LSP Position (line, character) to a string offset."""
    offset = 0
    for i, line in enumerate(content.split("\n")):
        if i == pos.line:
            clamped = min(pos.character, len(line))
            return offset + clamped
        offset += len(line) + 1  # +1 for '\n'
    # Position beyond end of file
    return len(content)


def apply_text_edits(content: str, edits: list[TextEdit]) -> str:
    """Apply text edits to a string. Edits are applied in reverse offset order."""
    if not edits:
        return content

    # Sort by start position descending (reverse order)
    sorted_edits = sorted(
        edits,
        key=lambda e: (e.range.start.line, e.range.start.character),
        reverse=True,
    )

    result = content
    for edit in sorted_edits:
        start = position_to_offset(result, edit.range.start)
        end = position_to_offset(result, edit.range.end)
        if start is not None and end is not None:
            result = result[:start] + edit.new_text + result[end:]
    return result


def uri_to_path(uri: str) -> Path | None:
    """Convert a file:// URI to a filesystem Path."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return None
    return Path(unquote(parsed.path))


def apply_workspace_edit(edit: WorkspaceEdit) -> ApplyResult:
    """Apply a WorkspaceEdit to disk files."""
    result = ApplyResult()

    if edit.document_changes is not None:
        for change in edit.document_changes:
            if isinstance(change, TextDocumentEdit):
                path = uri_to_path(change.text_document.uri)
                if path is None:
                    raise ValueError(f"invalid URI: {change.text_document.uri}")
                content = path.read_text()
                new_content = apply_text_edits(content, change.edits)
                path.write_text(new_content)
                result.files_changed.append((change.text_document.uri, len(change.edits)))
            elif isinstance(change, ResourceOperationCreate):
                path = uri_to_path(change.uri)
                if path is not None:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("")
                result.files_created.append(change.uri)
            elif isinstance(change, ResourceOperationRename):
                old_path = uri_to_path(change.old_uri)
                new_path = uri_to_path(change.new_uri)
                if old_path is not None and new_path is not None:
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    os.rename(old_path, new_path)
                result.files_renamed.append((change.old_uri, change.new_uri))
            elif isinstance(change, ResourceOperationDelete):
                path = uri_to_path(change.uri)
                if path is not None and path.exists():
                    path.unlink()
    elif edit.changes is not None:
        for uri, edits in edit.changes.items():
            path = uri_to_path(uri)
            if path is None:
                raise ValueError(f"invalid URI: {uri}")
            content = path.read_text()
            new_content = apply_text_edits(content, edits)
            path.write_text(new_content)
            result.files_changed.append((uri, len(edits)))

    return result
