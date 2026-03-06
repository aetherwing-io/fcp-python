"""Tests for LSP lifecycle manager."""

from fcp_python.lsp.lifecycle import LifecycleManager, ServerStatus


def test_initial_status_not_started():
    mgr = LifecycleManager(command="pylsp", args=[], root_uri="file:///test")
    assert mgr.status == ServerStatus.NotStarted


def test_track_untrack_document():
    mgr = LifecycleManager(command="pylsp", args=[], root_uri="file:///test")

    mgr.track_document("file:///main.py", "def main(): pass")
    assert len(mgr._tracked_documents) == 1
    assert mgr._tracked_documents["file:///main.py"] == "def main(): pass"

    mgr.untrack_document("file:///main.py")
    assert len(mgr._tracked_documents) == 0


def test_untrack_nonexistent():
    mgr = LifecycleManager(command="pylsp", args=[], root_uri="file:///test")
    # Should not raise
    mgr.untrack_document("file:///nonexistent.py")


def test_track_overwrites():
    mgr = LifecycleManager(command="pylsp", args=[], root_uri="file:///test")
    mgr.track_document("file:///main.py", "v1")
    mgr.track_document("file:///main.py", "v2")
    assert len(mgr._tracked_documents) == 1
    assert mgr._tracked_documents["file:///main.py"] == "v2"


def test_server_status_values():
    """All status values are distinct."""
    statuses = [
        ServerStatus.NotStarted,
        ServerStatus.Starting,
        ServerStatus.Ready,
        ServerStatus.Indexing,
        ServerStatus.Crashed,
        ServerStatus.Stopped,
    ]
    assert len(set(statuses)) == 6


def test_max_restarts_default():
    mgr = LifecycleManager(command="pylsp", args=[], root_uri="file:///test")
    assert mgr._max_restarts == 3


def test_max_restarts_custom():
    mgr = LifecycleManager(command="pylsp", args=[], root_uri="file:///test", max_restarts=5)
    assert mgr._max_restarts == 5


async def test_shutdown_without_client():
    """Shutdown when no client has been started should not error."""
    mgr = LifecycleManager(command="pylsp", args=[], root_uri="file:///test")
    await mgr.shutdown()
    assert mgr.status == ServerStatus.Stopped
