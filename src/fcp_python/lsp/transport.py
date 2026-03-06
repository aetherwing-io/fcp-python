"""Content-Length framed LSP transport."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .types import JsonRpcNotification, JsonRpcResponse

logger = logging.getLogger(__name__)


def encode_message(body: bytes) -> bytes:
    """Prepend Content-Length header to a message body."""
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


async def decode_message(reader: asyncio.StreamReader) -> dict:
    """Read a Content-Length framed message and parse as JSON."""
    content_length: int | None = None

    # Read headers line by line
    while True:
        line = await reader.readline()
        if not line:
            raise ConnectionError("unexpected EOF reading headers")

        line_str = line.decode("ascii", errors="replace").strip()
        if not line_str:
            # Empty line = end of headers
            break

        if line_str.lower().startswith("content-length:"):
            value = line_str.split(":", 1)[1].strip()
            try:
                content_length = int(value)
            except ValueError:
                raise ValueError(f"invalid Content-Length: {value}")

    if content_length is None:
        raise ValueError("missing Content-Length header")

    body = await reader.readexactly(content_length)
    return json.loads(body)


class LspWriter:
    """Writer wrapper for sending LSP messages with Content-Length framing."""

    def __init__(self, writer: asyncio.StreamWriter) -> None:
        self._writer = writer
        self._lock = asyncio.Lock()

    async def send_request(self, id: Any, method: str, params: Any) -> None:
        msg = {"jsonrpc": "2.0", "id": id, "method": method, "params": params}
        body = json.dumps(msg).encode("utf-8")
        frame = encode_message(body)
        async with self._lock:
            self._writer.write(frame)
            await self._writer.drain()

    async def send_notification(self, method: str, params: Any) -> None:
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        body = json.dumps(msg).encode("utf-8")
        frame = encode_message(body)
        async with self._lock:
            self._writer.write(frame)
            await self._writer.drain()


async def read_loop(
    reader: asyncio.StreamReader,
    pending: dict[str, asyncio.Future],
    notification_queue: asyncio.Queue[JsonRpcNotification],
    pending_lock: asyncio.Lock,
) -> None:
    """Dispatch incoming messages to pending futures or notification queue."""
    while True:
        try:
            msg = await decode_message(reader)
        except (ConnectionError, asyncio.IncompleteReadError):
            return  # EOF or read error
        except Exception:
            logger.debug("read_loop: error decoding message", exc_info=True)
            return

        # Response: has "id" and no "method"
        if "id" in msg and "method" not in msg:
            resp = JsonRpcResponse.from_dict(msg)
            id_str = str(resp.id)
            async with pending_lock:
                fut = pending.pop(id_str, None)
            if fut is not None and not fut.done():
                fut.set_result(resp)
        elif "method" in msg and "id" not in msg:
            # Notification
            notif = JsonRpcNotification.from_dict(msg)
            try:
                notification_queue.put_nowait(notif)
            except asyncio.QueueFull:
                logger.warning("notification queue full, dropping: %s", notif.method)
        # Server requests (both id and method) are ignored for now
