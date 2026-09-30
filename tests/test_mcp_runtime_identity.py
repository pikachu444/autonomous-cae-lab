"""Resident MCP diagnostics preserve unknowns and never create an experiment store."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
from caelab.storage import source_identity
from openscience import mcp_server


URI = "caelab://runtime/source-identity"
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_COMMIT = "3e48bf6138f495299f45b1af254bfb4aaff307b8"


def read_resource():
    contents = list(asyncio.run(mcp_server.mcp.read_resource(URI)))
    assert len(contents) == 1 and contents[0].mime_type == "application/json"
    return json.loads(contents[0].content)


def forbid_execution(monkeypatch, tmp_path):
    store = tmp_path / "uncreated-store"
    monkeypatch.setenv("CAELAB_STORE", str(store))

    def forbidden(*args, **kwargs):
        pytest.fail("Read-only resource attempted Lab construction or CAD import")

    monkeypatch.setattr(mcp_server.Lab, "__init__", forbidden)
    monkeypatch.setattr(mcp_server.fixture_cadquery, "_upstream", forbidden)
    return store


def test_actual_stdio_resource_reads_resident_identity_without_creating_store(tmp_path, monkeypatch):
    store = tmp_path / "uncreated-stdio-store"

    async def read():
        params = StdioServerParameters(command=sys.executable,
            args=[str(ROOT / "openscience/mcp_server.py")],
            env={**os.environ, "CAELAB_STORE": str(store)})
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                resources = (await session.list_resources()).resources
                assert any(str(resource.uri) == URI and resource.mimeType == "application/json"
                           for resource in resources)
                response = await session.read_resource(URI)
                assert len(response.contents) == 1
                assert response.contents[0].mimeType == "application/json"
                return json.loads(response.contents[0].text)

    observed = asyncio.run(asyncio.wait_for(read(), timeout=45))
    assert not store.exists()
    assert observed["diagnostic_only"] is True
    assert observed["process"]["pid"] != os.getpid()
    assert Path(observed["core"]["module_path"]) == ROOT / "caelab/engine.py"
    assert Path(observed["core"]["repo_path"]) == ROOT
    assert Path(observed["fixture"]["repo_path"]) == ROOT / "plugins/fixture_design/upstream"
    assert observed["fixture"]["imported_module_paths"] == {}
    # Reuse the existing hashing implementation without its unbounded Git calls.
    with monkeypatch.context() as parity:
        parity.setattr(subprocess, "check_output", lambda *args, **kwargs: "0" * 40)
        expected = source_identity(ROOT)
    assert observed["core"]["fingerprint"]["sha256"] == expected["core_source_sha256"]
    expected_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3, check=False)
    if expected_commit.returncode == 0:
        assert observed["core"]["git"]["commit"] == expected_commit.stdout.strip()
    for component in ("core", "fixture"):
        dirty_probe = observed[component]["git"]["probes"]["dirty"]
        if dirty_probe["status"] == "KNOWN":
            assert isinstance(observed[component]["git"]["dirty"], bool)
        else:
            assert observed[component]["git"]["dirty"] is None
    if observed["fixture"]["git"]["commit"] != "UNKNOWN":
        assert observed["fixture"]["git"]["commit"] == FIXTURE_COMMIT
    if observed["fixture"]["files_probe"]["status"] == "KNOWN":
        original_check_output = subprocess.check_output

        def bounded_check_output(*args, **kwargs):
            return original_check_output(*args, **{**kwargs, "timeout": 3})

        with monkeypatch.context() as parity:
            parity.setattr(subprocess, "check_output", bounded_check_output)
            expected_fixture = FixtureCadQueryAdapter.source_fingerprint()
        assert observed["fixture"]["fingerprint"]["sha256"] == expected_fixture["files_sha256"]


@pytest.mark.parametrize("failure,classification", [
    ("timeout", "TIMEOUT"), ("missing", "NOT_FOUND"),
    ("denied", "ACCESS_DENIED"), ("nonzero", "NONZERO_EXIT"),
    ("decode", "INVALID_OUTPUT"),
])
def test_fastmcp_failure_is_bounded_sanitized_and_unknown(failure, classification, tmp_path, monkeypatch):
    store = forbid_execution(monkeypatch, tmp_path)
    secret = "PRIVATE_TOKEN_DO_NOT_DISCLOSE"
    calls = []

    def failing_git(args, **kwargs):
        calls.append((args, kwargs))
        assert args[0] == "git"
        assert args[1:4] == ["--no-optional-locks", "-c", "core.fsmonitor=false"]
        assert kwargs["timeout"] == 3
        assert kwargs["stderr"] == subprocess.DEVNULL
        if failure == "timeout":
            raise subprocess.TimeoutExpired([secret], 3, output=secret, stderr=secret)
        if failure == "missing":
            raise FileNotFoundError(secret)
        if failure == "denied":
            raise PermissionError(secret)
        if failure == "decode":
            raise UnicodeDecodeError("utf8", b"\xff", 0, 1, secret)
        return subprocess.CompletedProcess(args, 128, stdout=secret, stderr=secret)

    monkeypatch.setattr(mcp_server.subprocess, "run", failing_git)
    observed = read_resource()
    assert not store.exists()
    assert len(calls) == 5
    assert secret not in json.dumps(observed)
    for component in ("core", "fixture"):
        assert observed[component]["git"]["commit"] == "UNKNOWN"
        assert observed[component]["git"]["dirty"] is None
        for probe in observed[component]["git"]["probes"].values():
            assert probe["status"] == "UNKNOWN" and probe["error"] == classification
    assert observed["fixture"]["fingerprint"]["sha256"] is None
    assert observed["fixture"]["fingerprint"]["status"] == "UNKNOWN"
    assert observed["core"]["fingerprint"]["status"] == "KNOWN"
    assert "environment" not in observed and "store_path" not in observed
    assert observed["diagnostic_only"] is True


def test_fastmcp_invalid_commit_does_not_disclose_stdout(tmp_path, monkeypatch):
    store = forbid_execution(monkeypatch, tmp_path)
    secret = "PRIVATE_TOKEN_DO_NOT_DISCLOSE"

    def invalid_git(args, **kwargs):
        stdout = secret if "rev-parse" in args else ""
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr=secret)

    monkeypatch.setattr(mcp_server.subprocess, "run", invalid_git)
    observed = read_resource()
    assert not store.exists() and secret not in json.dumps(observed)
    for component in ("core", "fixture"):
        assert observed[component]["git"]["commit"] == "UNKNOWN"
        assert observed[component]["git"]["probes"]["commit"]["error"] == "INVALID_OUTPUT"
        assert observed[component]["git"]["dirty"] is False
    assert observed["fixture"]["fingerprint"]["status"] == "UNKNOWN"


def test_fastmcp_missing_source_and_outside_symlink_remain_unknown(tmp_path, monkeypatch):
    store = forbid_execution(monkeypatch, tmp_path)
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    outside = tmp_path / "private-file"
    outside.write_text("PRIVATE_DATA_DO_NOT_READ", encoding="utf-8")
    (fixture / "source.py").symlink_to(outside)
    monkeypatch.setattr(mcp_server.fixture_cadquery, "UPSTREAM", fixture)

    def git(args, **kwargs):
        if "ls-files" in args:
            return subprocess.CompletedProcess(args, 0, stdout="source.py\0", stderr="")
        return subprocess.CompletedProcess(args, 128, stdout="", stderr="")

    monkeypatch.setattr(mcp_server.subprocess, "run", git)
    observed = read_resource()
    assert not store.exists()
    assert observed["fixture"]["fingerprint"] == {
        "status": "UNKNOWN", "error": "OUTSIDE_SOURCE_ROOT", "sha256": None,
        "semantics": "FixtureCadQueryAdapter.source_fingerprint"}
    assert "PRIVATE_DATA_DO_NOT_READ" not in json.dumps(observed)
