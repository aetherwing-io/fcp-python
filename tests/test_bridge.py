"""Tests for bridge socket discovery."""

import os

import pytest

from fcp_python.bridge import _discover_socket


class TestDiscoverSocket:
    def test_env_var_exists(self, tmp_path):
        sock = tmp_path / "daemon.sock"
        sock.touch()
        env = {"SLIPSTREAM_SOCKET": str(sock)}
        orig = os.environ.copy()
        os.environ.update(env)
        try:
            result = _discover_socket()
            assert result == str(sock)
        finally:
            os.environ.clear()
            os.environ.update(orig)

    def test_env_var_missing_file(self, tmp_path):
        env = {"SLIPSTREAM_SOCKET": str(tmp_path / "nonexistent.sock")}
        orig = os.environ.copy()
        os.environ.update(env)
        try:
            # Remove XDG too
            os.environ.pop("XDG_RUNTIME_DIR", None)
            result = _discover_socket()
            # May return None or fallback to /tmp path
            # Just verify it doesn't crash
        finally:
            os.environ.clear()
            os.environ.update(orig)

    def test_xdg_runtime_dir(self, tmp_path):
        sock = tmp_path / "slipstream.sock"
        sock.touch()
        orig = os.environ.copy()
        os.environ.pop("SLIPSTREAM_SOCKET", None)
        os.environ["XDG_RUNTIME_DIR"] = str(tmp_path)
        os.environ.pop("TMPDIR", None)
        try:
            result = _discover_socket()
            assert result == str(sock)
        finally:
            os.environ.clear()
            os.environ.update(orig)

    def test_tmpdir_fallback(self, tmp_path):
        sock = tmp_path / "slipstream.sock"
        sock.touch()
        orig = os.environ.copy()
        os.environ.pop("SLIPSTREAM_SOCKET", None)
        os.environ.pop("XDG_RUNTIME_DIR", None)
        os.environ["TMPDIR"] = str(tmp_path)
        try:
            result = _discover_socket()
            assert result == str(sock)
        finally:
            os.environ.clear()
            os.environ.update(orig)

    def test_no_socket_found(self, tmp_path):
        orig = os.environ.copy()
        os.environ.pop("SLIPSTREAM_SOCKET", None)
        os.environ.pop("XDG_RUNTIME_DIR", None)
        try:
            # This may or may not find a socket via /tmp fallback
            # depending on system state. Just verify no crash.
            _discover_socket()
        finally:
            os.environ.clear()
            os.environ.update(orig)
