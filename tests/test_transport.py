"""Tests for LSP transport layer."""

import asyncio
import json

import pytest

from fcp_python.lsp.transport import (
    LspWriter,
    decode_message,
    encode_message,
    read_loop,
)
from fcp_python.lsp.types import JsonRpcNotification


def test_encode_message():
    body = b'{"jsonrpc":"2.0"}'
    encoded = encode_message(body)
    expected = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    assert encoded == expected


async def test_decode_message():
    body = b'{"jsonrpc":"2.0","id":1}'
    frame = encode_message(body)
    reader = asyncio.StreamReader()
    reader.feed_data(frame)
    reader.feed_eof()
    msg = await decode_message(reader)
    assert msg["jsonrpc"] == "2.0"
    assert msg["id"] == 1


async def test_roundtrip():
    original = {"jsonrpc": "2.0", "id": 42, "method": "test", "params": None}
    body = json.dumps(original).encode("utf-8")
    frame = encode_message(body)
    reader = asyncio.StreamReader()
    reader.feed_data(frame)
    reader.feed_eof()
    decoded = await decode_message(reader)
    assert decoded == original


async def test_decode_eof():
    reader = asyncio.StreamReader()
    reader.feed_eof()
    with pytest.raises(ConnectionError):
        await decode_message(reader)


async def test_decode_missing_content_length():
    reader = asyncio.StreamReader()
    reader.feed_data(b"Content-Type: application/json\r\n\r\n{}")
    reader.feed_eof()
    with pytest.raises(ValueError, match="missing Content-Length"):
        await decode_message(reader)


async def test_read_loop_dispatches_response():
    resp = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    body = json.dumps(resp).encode("utf-8")
    frame = encode_message(body)

    reader = asyncio.StreamReader()
    reader.feed_data(frame)
    reader.feed_eof()

    pending: dict[str, asyncio.Future] = {}
    pending_lock = asyncio.Lock()
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    pending["1"] = fut

    notification_queue: asyncio.Queue[JsonRpcNotification] = asyncio.Queue()

    task = asyncio.create_task(read_loop(reader, pending, notification_queue, pending_lock))

    result = await asyncio.wait_for(fut, timeout=2.0)
    assert result.id == 1
    assert result.result is not None
    assert result.result["ok"] is True

    await task


async def test_read_loop_dispatches_notification():
    notif = {"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics", "params": {"uri": "file:///test.py"}}
    body = json.dumps(notif).encode("utf-8")
    frame = encode_message(body)

    reader = asyncio.StreamReader()
    reader.feed_data(frame)
    reader.feed_eof()

    pending: dict[str, asyncio.Future] = {}
    pending_lock = asyncio.Lock()
    notification_queue: asyncio.Queue[JsonRpcNotification] = asyncio.Queue()

    task = asyncio.create_task(read_loop(reader, pending, notification_queue, pending_lock))

    received = await asyncio.wait_for(notification_queue.get(), timeout=2.0)
    assert received.method == "textDocument/publishDiagnostics"

    await task


async def test_read_loop_eof():
    reader = asyncio.StreamReader()
    reader.feed_eof()

    pending: dict[str, asyncio.Future] = {}
    pending_lock = asyncio.Lock()
    notification_queue: asyncio.Queue[JsonRpcNotification] = asyncio.Queue()

    # Should return cleanly on EOF
    await asyncio.wait_for(
        read_loop(reader, pending, notification_queue, pending_lock),
        timeout=2.0,
    )


async def test_lsp_writer_send_request():
    reader = asyncio.StreamReader()
    # Create a mock writer using StreamReader/StreamWriter pair
    transport = _MockTransport(reader)
    protocol = asyncio.StreamReaderProtocol(reader)
    writer = asyncio.StreamWriter(transport, protocol, reader, asyncio.get_running_loop())

    lsp_writer = LspWriter(writer)
    await lsp_writer.send_request(1, "textDocument/definition", {"key": "value"})

    data = transport.written_data()
    text = data.decode("utf-8")
    assert text.startswith("Content-Length:")
    body_start = text.index("\r\n\r\n") + 4
    body = json.loads(text[body_start:])
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert body["method"] == "textDocument/definition"


async def test_lsp_writer_send_notification():
    reader = asyncio.StreamReader()
    transport = _MockTransport(reader)
    protocol = asyncio.StreamReaderProtocol(reader)
    writer = asyncio.StreamWriter(transport, protocol, reader, asyncio.get_running_loop())

    lsp_writer = LspWriter(writer)
    await lsp_writer.send_notification("initialized", {})

    data = transport.written_data()
    text = data.decode("utf-8")
    body_start = text.index("\r\n\r\n") + 4
    body = json.loads(text[body_start:])
    assert body["jsonrpc"] == "2.0"
    assert body["method"] == "initialized"
    assert "id" not in body


class _MockTransport(asyncio.Transport):
    """Simple mock transport that captures written bytes."""

    def __init__(self, reader: asyncio.StreamReader) -> None:
        super().__init__()
        self._buf = bytearray()
        self._closing = False

    def write(self, data: bytes) -> None:
        self._buf.extend(data)

    def written_data(self) -> bytes:
        return bytes(self._buf)

    def is_closing(self) -> bool:
        return self._closing

    def close(self) -> None:
        self._closing = True

    def get_extra_info(self, name: str, default=None):
        return default
