"""Slipstream bridge — connects FCP server to daemon via Unix socket."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Awaitable, Callable


async def connect(
    handle_session: Callable[[str], Awaitable[str]],
    handle_query: Callable[[str], Awaitable[str]],
    handle_mutation: Callable[[list[str]], Awaitable[str]],
) -> None:
    """Connect to slipstream daemon. Silently returns on failure."""
    try:
        await _run_bridge(handle_session, handle_query, handle_mutation)
    except Exception:
        pass


def _discover_socket() -> str | None:
    """Find daemon socket path."""
    # 1. SLIPSTREAM_SOCKET env var
    path = os.environ.get("SLIPSTREAM_SOCKET")
    if path and os.path.exists(path):
        return path

    # 2. XDG_RUNTIME_DIR/slipstream/daemon.sock
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        path = os.path.join(xdg, "slipstream", "daemon.sock")
        if os.path.exists(path):
            return path

    # 3. /tmp/slipstream-{uid}/daemon.sock
    uid = os.getuid()
    path = f"/tmp/slipstream-{uid}/daemon.sock"
    if os.path.exists(path):
        return path

    return None


async def _run_bridge(
    handle_session: Callable[[str], Awaitable[str]],
    handle_query: Callable[[str], Awaitable[str]],
    handle_mutation: Callable[[list[str]], Awaitable[str]],
) -> None:
    """Connect and handle requests via newline-delimited JSON-RPC."""
    path = _discover_socket()
    if path is None:
        return

    reader, writer = await asyncio.open_unix_connection(path)

    # Send registration
    register = {
        "jsonrpc": "2.0",
        "method": "fcp.register",
        "params": {
            "handler_name": "fcp-py",
            "extensions": ["py"],
            "capabilities": ["ops", "query", "session"],
        },
    }
    writer.write((json.dumps(register) + "\n").encode())
    await writer.drain()

    # Request loop (newline-delimited JSON)
    while True:
        line = await reader.readline()
        if not line:
            break

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        text = await _handle_request(
            method, params, handle_session, handle_query, handle_mutation
        )

        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"text": text},
        }
        writer.write((json.dumps(response) + "\n").encode())
        await writer.drain()

    writer.close()


async def _handle_request(
    method: str,
    params: dict[str, Any],
    handle_session: Callable[[str], Awaitable[str]],
    handle_query: Callable[[str], Awaitable[str]],
    handle_mutation: Callable[[list[str]], Awaitable[str]],
) -> str:
    if method == "fcp.session":
        action = params.get("action", "")
        return await handle_session(action)
    elif method == "fcp.ops":
        ops = params.get("ops", [])
        return await handle_mutation(ops)
    elif method == "fcp.query":
        q = params.get("q", "")
        return await handle_query(q)
    else:
        return f"unknown method: {method}"
