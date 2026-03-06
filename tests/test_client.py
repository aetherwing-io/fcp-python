"""Tests for LSP client (mocked subprocess)."""

import asyncio
import json

import pytest

from fcp_python.lsp.client import LspClient, LspError
from fcp_python.lsp.transport import encode_message, read_loop
from fcp_python.lsp.types import JsonRpcNotification, JsonRpcResponse


async def test_request_response_via_streams():
    """Test that request/response works via in-memory streams."""
    # Simulate a server that reads a request and sends back a response
    client_reader = asyncio.StreamReader()
    server_reader = asyncio.StreamReader()

    # We'll manually wire things up without a real subprocess
    pending: dict[str, asyncio.Future] = {}
    pending_lock = asyncio.Lock()
    notification_queue: asyncio.Queue[JsonRpcNotification] = asyncio.Queue()

    # Start read loop on client_reader (where server responses arrive)
    read_task = asyncio.create_task(
        read_loop(client_reader, pending, notification_queue, pending_lock)
    )

    # Register a pending request for id=1
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    async with pending_lock:
        pending["1"] = fut

    # Simulate server sending back a response
    resp = {"jsonrpc": "2.0", "id": 1, "result": {"status": "ok"}}
    body = json.dumps(resp).encode("utf-8")
    frame = encode_message(body)
    client_reader.feed_data(frame)
    client_reader.feed_eof()

    result = await asyncio.wait_for(fut, timeout=2.0)
    assert result.id == 1
    assert result.result["status"] == "ok"

    await read_task


async def test_notification_dispatch():
    """Test that notifications from server are dispatched to queue."""
    client_reader = asyncio.StreamReader()
    pending: dict[str, asyncio.Future] = {}
    pending_lock = asyncio.Lock()
    notification_queue: asyncio.Queue[JsonRpcNotification] = asyncio.Queue()

    read_task = asyncio.create_task(
        read_loop(client_reader, pending, notification_queue, pending_lock)
    )

    notif = {"jsonrpc": "2.0", "method": "window/logMessage", "params": {"message": "hello"}}
    body = json.dumps(notif).encode("utf-8")
    frame = encode_message(body)
    client_reader.feed_data(frame)
    client_reader.feed_eof()

    received = await asyncio.wait_for(notification_queue.get(), timeout=2.0)
    assert received.method == "window/logMessage"

    await read_task


async def test_error_response():
    """Test that error responses are properly parsed."""
    client_reader = asyncio.StreamReader()
    pending: dict[str, asyncio.Future] = {}
    pending_lock = asyncio.Lock()
    notification_queue: asyncio.Queue[JsonRpcNotification] = asyncio.Queue()

    read_task = asyncio.create_task(
        read_loop(client_reader, pending, notification_queue, pending_lock)
    )

    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    async with pending_lock:
        pending["1"] = fut

    resp = {
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32601, "message": "Method not found"},
    }
    body = json.dumps(resp).encode("utf-8")
    frame = encode_message(body)
    client_reader.feed_data(frame)
    client_reader.feed_eof()

    result = await asyncio.wait_for(fut, timeout=2.0)
    assert result.error is not None
    assert result.error.code == -32601

    await read_task


async def test_lsp_error_raised():
    """Test that LspError has code and message."""
    err = LspError(code=-32601, message="Method not found")
    assert err.code == -32601
    assert "Method not found" in str(err)
