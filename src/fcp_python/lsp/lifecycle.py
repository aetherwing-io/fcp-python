"""LSP server lifecycle manager with crash recovery."""

from __future__ import annotations

import logging
import time
from enum import Enum, auto

from .client import LspClient

logger = logging.getLogger(__name__)


class ServerStatus(Enum):
    NotStarted = auto()
    Starting = auto()
    Ready = auto()
    Indexing = auto()
    Crashed = auto()
    Stopped = auto()


class LifecycleManager:
    """Manages LSP server lifecycle including crash recovery and document replay."""

    def __init__(
        self,
        command: str,
        args: list[str],
        root_uri: str,
        max_restarts: int = 3,
    ) -> None:
        self._command = command
        self._args = args
        self._root_uri = root_uri
        self._client: LspClient | None = None
        self._status = ServerStatus.NotStarted
        self._restart_count = 0
        self._max_restarts = max_restarts
        self._last_restart: float | None = None
        self._tracked_documents: dict[str, str] = {}

    @property
    def status(self) -> ServerStatus:
        return self._status

    async def ensure_client(self) -> LspClient:
        """Ensure the LSP client is running. Starts or restarts if needed."""
        if self._client is not None and self._status == ServerStatus.Ready:
            return self._client

        if self._status == ServerStatus.Crashed and self._restart_count >= self._max_restarts:
            raise RuntimeError("max restarts exceeded")

        self._status = ServerStatus.Starting

        try:
            client = await LspClient.spawn(self._command, self._args, self._root_uri)
            self._client = client
            self._status = ServerStatus.Ready
            self._last_restart = time.monotonic()

            # Replay tracked documents
            for uri, text in list(self._tracked_documents.items()):
                try:
                    await client.did_open(uri, text)
                except Exception:
                    logger.warning("failed to replay document: %s", uri)

            return client
        except Exception as e:
            self._status = ServerStatus.Crashed
            self._restart_count += 1
            raise RuntimeError(f"failed to start LSP server: {e}") from e

    def track_document(self, uri: str, text: str) -> None:
        """Track a document for replay on restart."""
        self._tracked_documents[uri] = text

    def untrack_document(self, uri: str) -> None:
        """Untrack a document."""
        self._tracked_documents.pop(uri, None)

    async def shutdown(self) -> None:
        """Shutdown the LSP server gracefully."""
        if self._client is not None:
            await self._client.shutdown()
        self._client = None
        self._status = ServerStatus.Stopped
