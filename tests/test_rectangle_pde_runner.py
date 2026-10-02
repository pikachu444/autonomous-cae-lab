"""Acceptance source-pin fault tests; no native/math result is supplied here."""

from copy import deepcopy
from pathlib import Path

import pytest

from caelab.storage import save_json
from scripts import verify_rectangle_pde as runner


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    repository = tmp_path / "source"
    for relative in runner.SOURCE_FILES:
        file = repository / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("# TEST ONLY source-pin fixture\n", encoding="utf-8")
    monkeypatch.setattr(runner, "REPOSITORY", repository)
    core = {"core_commit": "TEST_ONLY_SOURCE_ID", "core_dirty": False,
            "core_source_sha256": "0" * 64}
    monkeypatch.setattr(runner, "source_identity", lambda root: deepcopy(core))
    pin = runner._source_pin()
    return repository, pin, core


def test_per_call_source_gate_refuses_domain_change_and_preserves_result_bytes(tmp_path, frozen):
    repository, pin, _ = frozen
    store = tmp_path / "store"

    class FaultLab:
        def run_pde(self, **arguments):
            output = store / "experiments" / arguments["experiment_id"]
            output.mkdir(parents=True)
            (output / "result.json").write_bytes(b"TEST ONLY retained observation\n")
            (repository / "plugins/pde_elliptic/reference.py").write_text("# CHANGED source\n")
            return {"provenance": pin["core"]}

    with pytest.raises(AssertionError, match="source changed"):
        runner._run_fixed(FaultLab(), store, pin, "S-test", "test_only", "E-test", {})
    assert (store / "experiments/E-test/result.json").read_bytes() == b"TEST ONLY retained observation\n"


@pytest.mark.parametrize("key,value", [("core_commit", "OTHER_TEST_ONLY_SOURCE"),
                                     ("core_dirty", True), ("core_source_sha256", "1" * 64)])
def test_core_identity_drift_is_refused_before_next_call(frozen, key, value):
    _, pin, core = frozen
    core[key] = value
    with pytest.raises(AssertionError, match="source changed"):
        runner._verify_source(pin)


def test_retained_provenance_must_match_frozen_source(frozen):
    _, pin, _ = frozen
    result = {"provenance": {**pin["core"], "core_commit": "UNRELATED_TEST_ONLY_SOURCE"}}
    with pytest.raises(AssertionError, match="provenance differs"):
        runner._verify_source(pin, result)


@pytest.mark.parametrize("fault", ["different-digest", "missing-domain"])
def test_native_copy_manifest_cannot_mix_or_omit_frozen_sources(tmp_path, frozen, fault):
    _, pin, _ = frozen
    root = tmp_path / "experiment"
    records = {relative: {"repository_path": relative, "sha256": digest}
               for relative, digest in pin["files"].items() if relative != "scripts/verify_rectangle_pde.py"}
    save_json(root / "pde/command.json", {"test_only": True})
    save_json(root / "pde/source_manifest.json", {"files": records})
    runner._verify_source(pin, {"provenance": pin["core"]}, root)
    if fault == "different-digest":
        records["plugins/pde_elliptic/reference.py"]["sha256"] = "f" * 64
    else:
        records.pop("plugins/pde_elliptic/reference.py")
    save_json(root / "pde/source_manifest.json", {"files": records})
    with pytest.raises(AssertionError, match="source manifest"):
        runner._verify_source(pin, {"provenance": pin["core"]}, root)
