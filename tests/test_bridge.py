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

    def test_env_var_no_file(self, tmp_path):
        """Returns env var path even if file doesn't exist yet (race-safe)."""
        path = str(tmp_path / "nonexistent.sock")
        orig = os.environ.copy()
        os.environ["SLIPSTREAM_SOCKET"] = path
        try:
            result = _discover_socket()
            assert result == path
        finally:
            os.environ.clear()
            os.environ.update(orig)

    def test_xdg_runtime_dir(self, tmp_path):
        orig = os.environ.copy()
        os.environ.pop("SLIPSTREAM_SOCKET", None)
        os.environ["XDG_RUNTIME_DIR"] = str(tmp_path)
        os.environ.pop("TMPDIR", None)
        try:
            result = _discover_socket()
            assert result == str(tmp_path / "slipstream.sock")
        finally:
            os.environ.clear()
            os.environ.update(orig)

    def test_tmpdir_fallback(self, tmp_path):
        orig = os.environ.copy()
        os.environ.pop("SLIPSTREAM_SOCKET", None)
        os.environ.pop("XDG_RUNTIME_DIR", None)
        os.environ["TMPDIR"] = str(tmp_path)
        try:
            result = _discover_socket()
            assert result == str(tmp_path / "slipstream.sock")
        finally:
            os.environ.clear()
            os.environ.update(orig)

    def test_default_fallback(self, tmp_path):
        """Always returns a path string, never None."""
        orig = os.environ.copy()
        os.environ.pop("SLIPSTREAM_SOCKET", None)
        os.environ.pop("XDG_RUNTIME_DIR", None)
        os.environ.pop("TMPDIR", None)
        try:
            result = _discover_socket()
            assert isinstance(result, str)
            assert result.endswith("slipstream.sock")
        finally:
            os.environ.clear()
            os.environ.update(orig)
