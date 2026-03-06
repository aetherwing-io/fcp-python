"""Slipstream bridge — connects FCP server to daemon via Unix socket.

Runs in a daemon thread so it never blocks the main MCP server.
Silently returns on any connection failure (bridge is invisible
when Slipstream isn't running).
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any, Awaitable, Callable

_AGENT_HELP = """\
### python — LSP-powered Python navigation and refactoring

#### Session
```
slipstream fcp python "open /path/to/project"
slipstream fcp python "status"
slipstream fcp python "close"
```

#### Navigation
```
slipstream fcp python_query "find MyClass"
slipstream fcp python_query "find process kind:function"
slipstream fcp python_query "def main @file:src/app.py"
slipstream fcp python_query "refs Config @file:models.py"
slipstream fcp python_query "symbols src/utils.py"
slipstream fcp python_query "impl BaseHandler"
```

#### Inspection
```
slipstream fcp python_query "inspect MyClass"
slipstream fcp python_query "callers process_data"
slipstream fcp python_query "callees handle_request"
slipstream fcp python_query "diagnose"
slipstream fcp python_query "diagnose src/main.py"
slipstream fcp python_query "map"
slipstream fcp python_query "unused @file:src/utils.py"
```

#### Refactoring
```
slipstream fcp python "rename Config Settings"
slipstream fcp python "extract validate @file:server.py @lines:15-30"
slipstream fcp python "import os @file:main.py @line:5"
```

#### Selectors
- `@file:PATH` — filter by file path
- `@class:NAME` — filter by containing class
- `@module:NAME` — filter by module
- `@kind:KIND` — function, class, method, variable, constant, module, property
- `@line:N` — filter by line number
- `@lines:N-M` — line range (for extract)
- `@decorator:NAME` — filter by decorator (e.g. `@decorator:staticmethod`)
"""


def start_bridge(
    handle_session: Callable[[str], Awaitable[str]],
    handle_query: Callable[[str], Awaitable[str]],
    handle_mutation: Callable[[list[str]], Awaitable[str]],
) -> threading.Thread | None:
    """Connect to Slipstream daemon if available.

    Spawns a daemon thread with its own event loop. Returns the thread
    (for join in bridge-only mode) or None if no socket found.
    """
    try:
        path = _discover_socket()
        if path is None:
            return None
        t = threading.Thread(
            target=_bridge_thread,
            args=(path, handle_session, handle_query, handle_mutation),
            daemon=True,
        )
        t.start()
        return t
    except Exception:  # noqa: BLE001
        return None


def _bridge_thread(
    path: str,
    handle_session: Callable[[str], Awaitable[str]],
    handle_query: Callable[[str], Awaitable[str]],
    handle_mutation: Callable[[list[str]], Awaitable[str]],
) -> None:
    """Entry point for the daemon thread."""
    try:
        asyncio.run(_run_bridge_at(path, handle_session, handle_query, handle_mutation))
    except Exception:  # noqa: BLE001
        pass


def _discover_socket() -> str | None:
    """Find daemon socket path.

    Matches slipstream-core's default_socket_path():
      SLIPSTREAM_SOCKET || {XDG_RUNTIME_DIR || TMPDIR || /tmp}/slipstream.sock
    """
    # 1. SLIPSTREAM_SOCKET env var (set by daemon when it spawns plugins)
    path = os.environ.get("SLIPSTREAM_SOCKET")
    if path and os.path.exists(path):
        return path

    # 2. Default path: {runtime_dir}/slipstream.sock
    runtime_dir = (
        os.environ.get("XDG_RUNTIME_DIR")
        or os.environ.get("TMPDIR")
        or "/tmp"
    )
    path = os.path.join(runtime_dir, "slipstream.sock")
    if os.path.exists(path):
        return path

    return None


async def _run_bridge_at(
    path: str,
    handle_session: Callable[[str], Awaitable[str]],
    handle_query: Callable[[str], Awaitable[str]],
    handle_mutation: Callable[[list[str]], Awaitable[str]],
) -> None:
    """Async loop: connect, register, then handle NDJSON requests."""
    reader, writer = await asyncio.open_unix_connection(path)

    # Send registration
    register = {
        "jsonrpc": "2.0",
        "method": "fcp.register",
        "params": {
            "handler_name": "fcp-python",
            "extensions": ["py"],
            "capabilities": {"ops": True, "query": True, "session": True},
            "agent_help": _AGENT_HELP,
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
