"""LSP client implementation."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from .transport import LspWriter, read_loop
from .types import InitializeResult, JsonRpcNotification, ServerCapabilities

logger = logging.getLogger(__name__)


class LspError(Exception):
    """Error from LSP server."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        super().__init__(f"LSP error {code}: {message}")


class LspClient:
    """JSON-RPC client for communicating with an LSP server subprocess."""

    def __init__(
        self,
        process: asyncio.subprocess.Process,
        writer: LspWriter,
        pending: dict[str, asyncio.Future],
        pending_lock: asyncio.Lock,
        notification_queue: asyncio.Queue[JsonRpcNotification],
        read_task: asyncio.Task,
        server_capabilities: ServerCapabilities | None = None,
    ) -> None:
        self._process = process
        self._writer = writer
        self._pending = pending
        self._pending_lock = pending_lock
        self._notification_queue = notification_queue
        self._read_task = read_task
        self._next_id = 1
        self.server_capabilities = server_capabilities

    @classmethod
    async def spawn(cls, command: str, args: list[str], root_uri: str) -> LspClient:
        """Spawn an LSP server process and perform the initialize handshake."""
        process = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        assert process.stdin is not None
        assert process.stdout is not None

        writer = LspWriter(process.stdin)
        pending: dict[str, asyncio.Future] = {}
        pending_lock = asyncio.Lock()
        notification_queue: asyncio.Queue[JsonRpcNotification] = asyncio.Queue(maxsize=64)

        reader = process.stdout
        read_task = asyncio.create_task(
            read_loop(reader, pending, notification_queue, pending_lock)
        )

        client = cls(
            process=process,
            writer=writer,
            pending=pending,
            pending_lock=pending_lock,
            notification_queue=notification_queue,
            read_task=read_task,
        )

        # Initialize handshake
        caps = await client._initialize(root_uri)
        client.server_capabilities = caps

        # Send initialized notification
        await client.notify("initialized", {})

        return client

    async def _initialize(self, root_uri: str) -> ServerCapabilities:
        params = {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "capabilities": {
                "textDocument": {
                    "codeAction": {
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
                                    "quickfix",
                                    "refactor",
                                    "refactor.extract",
                                    "refactor.inline",
                                    "refactor.rewrite",
                                    "source",
                                    "source.organizeImports",
                                ]
                            }
                        }
                    },
                    "rename": {"prepareSupport": False},
                },
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {
                        "documentChanges": True,
                        "resourceOperations": ["create", "rename", "delete"],
                    },
                },
            },
        }

        result = await self.request("initialize", params)
        init_result = InitializeResult.from_dict(result)
        return init_result.capabilities

    async def request(self, method: str, params: Any) -> Any:
        """Send a JSON-RPC request and await the response."""
        req_id = self._next_id
        self._next_id += 1

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()

        async with self._pending_lock:
            self._pending[str(req_id)] = fut

        await self._writer.send_request(req_id, method, params)

        resp = await fut

        if resp.error is not None:
            raise LspError(resp.error.code, resp.error.message)

        return resp.result

    async def notify(self, method: str, params: Any) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        await self._writer.send_notification(method, params)

    async def did_open(self, uri: str, text: str) -> None:
        """Send textDocument/didOpen notification."""
        params = {
            "textDocument": {
                "uri": uri,
                "languageId": "python",
                "version": 1,
                "text": text,
            }
        }
        await self.notify("textDocument/didOpen", params)

    async def did_change(self, uri: str, version: int, text: str) -> None:
        """Send textDocument/didChange notification (full sync)."""
        params = {
            "textDocument": {"uri": uri, "version": version},
            "contentChanges": [{"text": text}],
        }
        await self.notify("textDocument/didChange", params)

    async def did_close(self, uri: str) -> None:
        """Send textDocument/didClose notification."""
        params = {"textDocument": {"uri": uri}}
        await self.notify("textDocument/didClose", params)

    async def shutdown(self) -> None:
        """Send shutdown request and exit notification, then wait for process."""
        try:
            await self.request("shutdown", None)
        except Exception:
            pass
        try:
            await self.notify("exit", None)
        except Exception:
            pass
        try:
            await self._process.wait()
        except Exception:
            pass
        self._read_task.cancel()
        try:
            await self._read_task
        except asyncio.CancelledError:
            pass

    @property
    def notification_queue(self) -> asyncio.Queue[JsonRpcNotification]:
        return self._notification_queue
