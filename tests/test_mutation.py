"""Tests for mutation dispatch and handlers."""

import pytest

from fcp_core import VerbRegistry

from fcp_python.domain.model import PythonModel
from fcp_python.domain.mutation import dispatch_mutation, file_uri
from fcp_python.domain.verbs import (
    register_mutation_verbs,
    register_query_verbs,
    register_session_verbs,
)


def _make_registry() -> VerbRegistry:
    reg = VerbRegistry()
    register_query_verbs(reg)
    register_mutation_verbs(reg)
    register_session_verbs(reg)
    return reg


def _make_model() -> PythonModel:
    return PythonModel("file:///project")


@pytest.mark.asyncio
async def test_dispatch_mutation_parse_error():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_mutation(model, reg, "")
    assert "parse error" in result


@pytest.mark.asyncio
async def test_dispatch_mutation_unknown_verb():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_mutation(model, reg, "refactor Config")
    assert "unknown verb" in result


@pytest.mark.asyncio
async def test_dispatch_mutation_no_workspace():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_mutation(model, reg, "rename Config Settings")
    assert "no workspace open" in result


@pytest.mark.asyncio
async def test_dispatch_rename_recognized():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_mutation(model, reg, "rename Config Settings")
    assert "no workspace open" in result


@pytest.mark.asyncio
async def test_dispatch_extract_recognized():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_mutation(model, reg, "extract validate @file:server.py @lines:15-30")
    assert "no workspace open" in result


@pytest.mark.asyncio
async def test_dispatch_import_recognized():
    model = _make_model()
    reg = _make_registry()
    result = await dispatch_mutation(model, reg, "import os @file:main.py @line:5")
    assert "no workspace open" in result


def test_file_uri_absolute():
    model = _make_model()
    assert file_uri(model, "file:///other/path.py") == "file:///other/path.py"


def test_file_uri_relative():
    model = _make_model()
    assert file_uri(model, "src/main.py") == "file:///project/src/main.py"
