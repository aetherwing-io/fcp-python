"""Tests for workspace_edit module."""

import tempfile
from pathlib import Path
from urllib.parse import quote

from fcp_python.lsp.types import (
    Position,
    Range,
    ResourceOperationCreate,
    ResourceOperationRename,
    TextDocumentEdit,
    TextEdit,
    VersionedTextDocumentIdentifier,
    WorkspaceEdit,
)
from fcp_python.lsp.workspace_edit import (
    ApplyResult,
    apply_text_edits,
    apply_workspace_edit,
    position_to_offset,
    uri_to_path,
)


def pos(line: int, character: int) -> Position:
    return Position(line=line, character=character)


def rng(sl: int, sc: int, el: int, ec: int) -> Range:
    return Range(start=pos(sl, sc), end=pos(el, ec))


def test_apply_text_edits_single():
    content = "def config(): pass"
    edits = [TextEdit(range=rng(0, 4, 0, 10), new_text="settings")]
    result = apply_text_edits(content, edits)
    assert result == "def settings(): pass"


def test_apply_text_edits_multiple_non_overlapping():
    content = "x = Config()\ny = Config()"
    edits = [
        TextEdit(range=rng(0, 4, 0, 10), new_text="Settings"),
        TextEdit(range=rng(1, 4, 1, 10), new_text="Settings"),
    ]
    result = apply_text_edits(content, edits)
    assert result == "x = Settings()\ny = Settings()"


def test_apply_text_edits_empty():
    content = "hello world"
    result = apply_text_edits(content, [])
    assert result == "hello world"


def test_apply_text_edits_insert():
    content = "def main(): pass"
    edits = [TextEdit(range=rng(0, 0, 0, 0), new_text="async ")]
    result = apply_text_edits(content, edits)
    assert result == "async def main(): pass"


def test_apply_text_edits_multiline():
    content = "line one\nline two\nline three"
    edits = [TextEdit(range=rng(1, 5, 1, 8), new_text="2")]
    result = apply_text_edits(content, edits)
    assert result == "line one\nline 2\nline three"


def test_position_to_offset():
    content = "hello\nworld\nfoo"
    assert position_to_offset(content, pos(0, 0)) == 0
    assert position_to_offset(content, pos(0, 5)) == 5
    assert position_to_offset(content, pos(1, 0)) == 6
    assert position_to_offset(content, pos(1, 5)) == 11
    assert position_to_offset(content, pos(2, 0)) == 12
    assert position_to_offset(content, pos(2, 3)) == 15


def test_position_to_offset_clamps():
    content = "hi\n"
    # Character beyond line length should clamp
    assert position_to_offset(content, pos(0, 100)) == 2


def test_uri_to_path():
    assert uri_to_path("file:///tmp/test.py") == Path("/tmp/test.py")
    assert uri_to_path("http://example.com") is None


def test_apply_result_total_edits():
    result = ApplyResult(
        files_changed=[("file:///a.py", 3), ("file:///b.py", 2)],
    )
    assert result.total_edits() == 5


def test_apply_result_total_edits_empty():
    result = ApplyResult()
    assert result.total_edits() == 0


def test_apply_workspace_edit_document_changes():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.py"
        file_path.write_text("def Config(): pass\nuse_Config()")

        uri = file_path.as_uri()
        edit = WorkspaceEdit(
            document_changes=[
                TextDocumentEdit(
                    text_document=VersionedTextDocumentIdentifier(uri=uri),
                    edits=[
                        TextEdit(range=rng(0, 4, 0, 10), new_text="Settings"),
                        TextEdit(range=rng(1, 4, 1, 10), new_text="Settings"),
                    ],
                )
            ]
        )

        result = apply_workspace_edit(edit)
        assert len(result.files_changed) == 1
        assert result.files_changed[0][1] == 2

        content = file_path.read_text()
        assert content == "def Settings(): pass\nuse_Settings()"


def test_apply_workspace_edit_create_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "new_file.py"
        uri = file_path.as_uri()

        edit = WorkspaceEdit(
            document_changes=[ResourceOperationCreate(uri=uri)]
        )

        result = apply_workspace_edit(edit)
        assert len(result.files_created) == 1
        assert file_path.exists()


def test_apply_workspace_edit_rename_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        old_path = Path(tmpdir) / "old.py"
        new_path = Path(tmpdir) / "new.py"
        old_path.write_text("content")

        old_uri = old_path.as_uri()
        new_uri = new_path.as_uri()

        edit = WorkspaceEdit(
            document_changes=[
                ResourceOperationRename(old_uri=old_uri, new_uri=new_uri)
            ]
        )

        result = apply_workspace_edit(edit)
        assert len(result.files_renamed) == 1
        assert not old_path.exists()
        assert new_path.exists()
        assert new_path.read_text() == "content"


def test_apply_workspace_edit_simple_changes_form():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.py"
        file_path.write_text("def old_name(): pass")

        uri = file_path.as_uri()
        edit = WorkspaceEdit(
            changes={
                uri: [TextEdit(range=rng(0, 4, 0, 12), new_text="new_name")]
            }
        )

        result = apply_workspace_edit(edit)
        assert len(result.files_changed) == 1

        content = file_path.read_text()
        assert content == "def new_name(): pass"
