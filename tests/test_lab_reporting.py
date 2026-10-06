"""Portable local reports using real Core envelopes and TEST-ONLY adapters.

These small observations do not execute CAD kernels/native solvers or prove
physics. The tests verify evidence retention, safe paths and exported bytes.
"""

from copy import deepcopy
import hashlib
from html import escape
from html.parser import HTMLParser
import io
import json
from pathlib import PurePosixPath
from types import SimpleNamespace
import zipfile

import pytest

from apps.lab import reporting
from caelab import Lab
from caelab.contracts import Outcome
from caelab.storage import load_json, save_json


STUDY = "S-report"
INJECTION = '<script>alert("외부 텍스트")</script>'
REASON = "TEST ONLY: retained invalid observation " + INJECTION


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class ReportCAD:
    """Test-only native-looking bytes; no CAD kernel or geometry assertion."""

    backend = "test.report.cad"
    version = "test-only-1"
    domain = "structure"
    physics_domain = "solid_mechanics"
    analysis_type = "cad_preflight"
    default_metrics = ["test_volume"]

    def document_id(self, model):
        return "TEST-ONLY-CAD"

    def discover(self, model):
        return []

    def regenerate(self, model, native_values, output):
        output.mkdir()
        (output / "native.FCStd").write_bytes(b"TEST ONLY: editable native fixture bytes\n")
        (output / "assembly.step").write_bytes(b"TEST ONLY: fake CAD export, no geometry\n")
        save_json(output / "observations.json", {"test_only": True})
        return Outcome("REVIEW_REQUIRED", [{"code": "test_cad_contract", "status": "PASS", "observed": "TEST ONLY"}],
                       generated=True, metrics={"test_volume": {"value": 1.0, "unit": "mm3", "valid": True}},
                       pending_validations=["machine_interface", "material_qualification"],
                       native_revision="1" * 64, source_sha256="2" * 64, raw_result="cad/observations.json")


class ReportModel:
    backend = "test.report.model"
    version = "test-only-1"
    domain = "structure"
    physics_domain = "solid_mechanics"
    analysis_type = "linear_static"
    default_metrics = ["test_response"]

    def __init__(self, mode="rejected"):
        self.mode = mode

    def describe_model(self, settings):
        return {"model": {"geometry": {"kind": "test_only_declaration"}},
                "outputs": {"metrics": self.default_metrics},
                "loads": [{"type": "test_only", "note": INJECTION}]}

    def solve(self, output, settings):
        output.mkdir()
        (output / "native.inp").write_bytes(b"TEST ONLY: declared input, no native solver\n")
        (output / "raw.log").write_text("TEST ONLY: synthetic raw observation\n", encoding="utf-8")
        save_json(output / "processed.json", {"test_only": True, "value": 0.5})
        if self.mode == "crash":
            raise RuntimeError("TEST ONLY: partial execution failed " + INJECTION)
        rejected = self.mode == "rejected"
        metric = {"value": 0.5, "unit": "mm", "valid": not rejected}
        if rejected:
            metric["reason"] = REASON
        return {"status": "REJECTED" if rejected else "COMPLETED", "solver_status": "COMPLETED", "converged": True,
                "checks": [{"code": "test_screen", "status": "FAIL" if rejected else "PASS",
                            "observed": 0.5, "limit": 0.2, "detail": INJECTION},
                           {"code": "test_raw_completeness", "status": "PASS", "observed": "TEST ONLY"}],
                "metrics": {"test_response": metric}, "pending_validations": ["static_strength", "durability"],
                "provenance": {"versions": {"solver": "TEST-ONLY"}, "test_only": True, "note": INJECTION},
                "raw_result": f"{output.name}/raw.log"}


class ReportPDE(ReportModel):
    backend = "test.report.pde"
    domain = "pde"
    physics_domain = "scalar_elliptic"
    analysis_type = "weak_form_benchmark"


class ReportAnalysis(ReportModel):
    backend = "test.report.analysis"

    def solve(self, parent_result, parent_root, output, settings):
        outcome = super().solve(output, settings)
        (output / "input.step").write_bytes((parent_root / "cad/assembly.step").read_bytes())
        return outcome


def _store(path, *, model_mode="rejected"):
    cad, model, pde, analysis = ReportCAD(), ReportModel(model_mode), ReportPDE("complete"), ReportAnalysis("complete")
    lab = Lab(path, adapters={cad.backend: cad}, analysis_adapters={analysis.backend: analysis},
              doe_adapters={}, optimization_adapters={}, pde_adapters={pde.backend: pde},
              model_analysis_adapters={model.backend: model})
    lab.create_study(STUDY, "시험 보고서 " + INJECTION, "TEST ONLY: preserve evidence?", "TEST ONLY", "Retain all verdicts")
    results = {}
    results["E-cad"] = lab.run_experiment(study_id=STUDY, experiment_id="E-cad", backend=cad.backend,
                                           model="TEST-ONLY", values={})
    results["E-child"] = lab.run_analysis(parent_experiment_id="E-cad", experiment_id="E-child",
                                          backend=analysis.backend, settings={"note": INJECTION})
    results["E-model"] = lab.run_model_analysis(study_id=STUDY, experiment_id="E-model", backend=model.backend,
                                               settings={"note": INJECTION})
    results["E-pde"] = lab.run_pde(study_id=STUDY, experiment_id="E-pde", backend=pde.backend,
                                   settings={"note": INJECTION})
    return lab, results


def _reanchor(lab, identifier, result):
    """Only synthetic fixtures reanchor hashes to exercise path policy."""
    folder = lab.store / "experiments" / identifier
    save_json(folder / "result.json", result)
    ledger_path = lab.store / "ledger" / f"{identifier}.json"
    ledger = load_json(ledger_path)
    ledger["result_sha256"] = _sha((folder / "result.json").read_bytes())
    save_json(ledger_path, ledger)


def _originals(folder):
    return {path.relative_to(folder).as_posix(): path.read_bytes()
            for path in folder.rglob("*") if path.is_file()}


@pytest.mark.parametrize("identifier", ["E-cad", "E-child", "E-model", "E-pde"])
def test_common_record_preserves_exact_outcomes_hashes_unknown_and_parent(tmp_path, identifier):
    lab, results = _store(tmp_path)
    record = reporting.verified_record(lab, identifier)
    assert record["result"] == results[identifier]
    assert record["summary"] == lab.research_summary(identifier)
    assert record["integrity"] == "VERIFIED"
    assert record["result"]["decision"] == "NOT_RELEASED"
    assert any(validation["status"] == "UNKNOWN" for validation in record["result"]["validations"])
    assert record["hashes"]["artifacts"] == results[identifier]["artifacts"]
    for entry in record["hashes"]["documents"]:
        data = (lab.store / entry["path"]).read_bytes()
        assert entry["sha256"] == _sha(data) and entry["size_bytes"] == len(data)
    folder = lab.store / "experiments" / identifier
    assert record["hashes"]["result_sha256"] == record["ledger"]["result_sha256"] == _sha((folder / "result.json").read_bytes())
    assert record["hashes"]["thread_sha256"] == record["ledger"]["thread_sha256"] == _sha((folder / "thread.json").read_bytes())
    assert record["proposal"] == load_json(folder / "proposal.json")
    assert record["thread"] == load_json(folder / "thread.json")
    assert record["registry_snapshot"] == load_json(folder / "registry_snapshot.json")
    if identifier == "E-child":
        parent = record["parent_chain"][0]
        assert len(record["parent_chain"]) == 1 and parent["result"] == results["E-cad"]
        assert parent["hashes"]["result_sha256"] == record["result"]["provenance"]["parent_result_sha256"]
        assert parent["result"]["cad_revision"] == record["result"]["cad_revision"]
    else:
        assert record["parent_chain"] == []
    if identifier == "E-model":
        assert record["result"]["solver_status"] == "COMPLETED" and record["result"]["status"] == "REJECTED"
        assert record["result"]["metrics"]["test_response"] == {"value": 0.5, "unit": "mm", "valid": False, "reason": REASON}


def test_korean_html_escapes_all_external_text_and_keeps_verdicts_and_details(tmp_path):
    lab, _ = _store(tmp_path)
    record = reporting.verified_record(lab, "E-model")
    html = reporting.render_html(record)
    assert '<html lang="ko">' in html and "결과값" in html and "무효 사유" in html
    assert "REJECTED" in html and "COMPLETED" in html and "NOT_RELEASED" in html and "UNKNOWN" in html
    assert escape(REASON, quote=True) in html
    assert escape(INJECTION, quote=True) in html
    assert "<script" not in html and "<img" not in html and "src=" not in html and "href=" not in html
    assert "원격 보존" in html and "전자서명" in html and "물리 검증" in html
    for evidence in record["result"]["evidence"]:
        assert evidence["id"] in html
    for validation in record["result"]["validations"]:
        assert validation["type"] in html
    for label in ("result_sha256", "thread_sha256", "ledger_sha256"):
        assert record["hashes"][label] in html

    class FirstView(HTMLParser):
        """Observe initially readable content without opening technical records."""
        def __init__(self):
            super().__init__()
            self.closed_depth = 0
            self.style_depth = 0
            self.visible = []

        def handle_starttag(self, tag, attrs):
            if tag == "details":
                assert "open" not in dict(attrs)
                self.closed_depth += 1
            if tag == "style":
                self.style_depth += 1
            if tag == "pre":
                assert self.closed_depth > 0

        def handle_endtag(self, tag):
            if tag == "details":
                self.closed_depth -= 1
            if tag == "style":
                self.style_depth -= 1

        def handle_data(self, value):
            if not self.closed_depth and not self.style_depth:
                self.visible.append(value)

    first_view = FirstView()
    first_view.feed(html)
    readable = " ".join(first_view.visible)
    assert "공학적 사용 미승인" in readable and "판단에 사용할 수 없음" in readable
    assert "0.5" in readable and "mm" in readable and REASON in readable
    assert "result_sha256" not in readable and record["hashes"]["result_sha256"] not in readable
    assert "test_response" not in readable
    assert record["result"]["metrics"]["test_response"]["valid"] is False


@pytest.mark.parametrize("identifier", ["E-child", "E-model"])
def test_bundle_exact_payload_manifest_raw_parent_bytes_and_no_unlisted_secrets(tmp_path, identifier):
    lab, _ = _store(tmp_path)
    (lab.store / "experiments" / identifier / "secret.txt").write_text("UNLISTED SECRET", encoding="utf-8")
    (lab.store / "private_credentials.txt").write_text("UNLISTED CREDENTIAL", encoding="utf-8")
    before = _originals(lab.store)
    data = reporting.bundle_bytes(lab, identifier)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest = json.loads(archive.read("bundle_manifest.json"))
        assert manifest["schema_version"] == "1.0" and manifest["integrity"] == "VERIFIED"
        files = manifest["files"]
        paths = {entry["path"] for entry in files}
        assert set(archive.namelist()) == paths | {"bundle_manifest.json"}
        assert len(archive.namelist()) == len(paths) + 1
        assert "bundle_manifest.json" not in paths
        assert {"report.html", "report.json", f"experiments/{identifier}/simulation/native.inp",
                f"experiments/{identifier}/simulation/raw.log", f"experiments/{identifier}/simulation/processed.json",
                f"experiments/{identifier}/result.json", f"experiments/{identifier}/thread.json",
                f"ledger/{identifier}.json", f"studies/{STUDY}/study.json"} <= paths
        if identifier == "E-child":
            assert {"experiments/E-cad/cad/native.FCStd", "experiments/E-cad/cad/assembly.step",
                    "experiments/E-cad/result.json", "experiments/E-cad/thread.json", "ledger/E-cad.json"} <= paths
        record = json.loads(archive.read("report.json"))
        assert record == reporting.verified_record(lab, identifier)
        assert manifest["limitations"]["cryptographically_signed"] is False
        assert manifest["limitations"]["engineering_release"] is False
        for entry in files:
            path = PurePosixPath(entry["path"])
            assert not path.is_absolute() and ".." not in path.parts
            raw = archive.read(entry["path"])
            assert _sha(raw) == entry["sha256"] and len(raw) == entry["size_bytes"]
            assert entry["source_experiment_id"] in (identifier, "E-cad") and entry["revision"]
            if entry["role"] != "report":
                assert raw == (lab.store / entry["path"]).read_bytes()
        for source in (record, *record["parent_chain"]):
            for artifact in source["result"]["artifacts"]:
                path = f"experiments/{source['result']['experiment_id']}/{artifact['path']}"
                entry = next(entry for entry in files if entry["path"] == path)
                assert entry["revision"] == artifact["revision"]
        assert not any("secret" in name or "credentials" in name for name in archive.namelist())
    assert _originals(lab.store) == before


@pytest.mark.parametrize("relative", ["result.json", "thread.json", "proposal.json", "registry_snapshot.json", "simulation/raw.log"])
def test_changed_record_or_evidence_bytes_are_refused(tmp_path, relative):
    lab, _ = _store(tmp_path)
    path = lab.store / "experiments/E-model" / relative
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="(?i)hash mismatch"):
        reporting.verified_record(lab, "E-model")
    with pytest.raises(ValueError, match="(?i)hash mismatch"):
        reporting.bundle_bytes(lab, "E-model")


def test_ledger_and_parent_tamper_cannot_be_exported(tmp_path):
    lab, _ = _store(tmp_path)
    ledger_path = lab.store / "ledger/E-model.json"
    ledger = load_json(ledger_path)
    ledger["thread_sha256"] = "0" * 64
    save_json(ledger_path, ledger)
    with pytest.raises(ValueError, match="thread.json hash mismatch"):
        reporting.verified_record(lab, "E-model")
    path = lab.store / "experiments/E-cad/cad/native.FCStd"
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="(?i)hash mismatch"):
        reporting.bundle_bytes(lab, "E-child")


def test_manifest_size_is_checked_even_when_core_byte_hash_passes(tmp_path):
    lab, results = _store(tmp_path)
    result = deepcopy(results["E-model"])
    artifact = next(entry for entry in result["artifacts"] if entry["path"] == "simulation/raw.log")
    artifact["size_bytes"] += 1
    _reanchor(lab, "E-model", result)
    assert lab.inspect_experiment("E-model") == result  # Existing Core checks SHA, not byte size.
    with pytest.raises(ValueError, match="File size mismatch"):
        reporting.verified_record(lab, "E-model")


@pytest.mark.parametrize("document", ["proposal.json", "registry_snapshot.json"])
def test_canonical_input_hash_is_retained_beyond_reanchored_file_hashes(tmp_path, document):
    lab, results = _store(tmp_path)
    folder = lab.store / "experiments/E-model"
    value = load_json(folder / document)
    value["tampered"] = "TEST ONLY: changes frozen input metadata"
    save_json(folder / document, value)
    result = deepcopy(results["E-model"])
    artifact = next(entry for entry in result["artifacts"] if entry["path"] == document)
    raw = (folder / document).read_bytes()
    artifact.update(sha256=_sha(raw), size_bytes=len(raw))
    _reanchor(lab, "E-model", result)
    assert lab.inspect_experiment("E-model") == result
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        reporting.verified_record(lab, "E-model")


@pytest.mark.parametrize("unsafe", ["../outside", "a/../../outside", "/tmp/outside", "C:/outside",
                                  "C:\\outside", "a\\..\\outside", "./proposal.json", "a//file", "file:stream",
                                  "a/.. /outside", "simulation/raw.log.", "simulation/raw.log ", "NUL.log"])
def test_every_manifest_path_is_preflighted_before_core_inspection(tmp_path, monkeypatch, unsafe):
    lab, results = _store(tmp_path)
    result = deepcopy(results["E-model"])
    result["artifacts"].append({"path": unsafe, "sha256": "0" * 64, "size_bytes": 0})
    _reanchor(lab, "E-model", result)
    monkeypatch.setattr(lab, "inspect_experiment", lambda *args, **kwargs: pytest.fail("Unsafe manifest reached Core"))
    with pytest.raises(ValueError, match="Unsafe artifact path"):
        reporting.verified_record(lab, "E-model")


def test_duplicate_paths_and_unsafe_ancestor_fail_before_core(tmp_path, monkeypatch):
    lab, results = _store(tmp_path)
    result = deepcopy(results["E-cad"])
    result["artifacts"].append(deepcopy(result["artifacts"][0]))
    _reanchor(lab, "E-cad", result)
    monkeypatch.setattr(lab, "inspect_experiment", lambda *args, **kwargs: pytest.fail("Unsafe ancestor reached Core"))
    with pytest.raises(ValueError, match="Duplicate artifact path"):
        reporting.verified_record(lab, "E-child")


def test_external_symlink_is_rejected_even_when_its_bytes_match_manifest(tmp_path, monkeypatch):
    lab, _ = _store(tmp_path / "store")
    path = lab.store / "experiments/E-model/simulation/raw.log"
    outside = tmp_path / "outside.log"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    monkeypatch.setattr(lab, "inspect_experiment", lambda *args, **kwargs: pytest.fail("External link reached Core"))
    with pytest.raises(ValueError, match="escapes verified root"):
        reporting.verified_record(lab, "E-model")


def test_internal_symlink_keeps_only_named_manifest_file(tmp_path):
    lab, _ = _store(tmp_path)
    folder = lab.store / "experiments/E-model"
    path = folder / "simulation/raw.log"
    inside = folder / "unlisted-alias.log"
    inside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(inside)
    with zipfile.ZipFile(io.BytesIO(reporting.bundle_bytes(lab, "E-model"))) as archive:
        assert archive.read("experiments/E-model/simulation/raw.log") == inside.read_bytes()
        assert "experiments/E-model/unlisted-alias.log" not in archive.namelist()


def test_experiment_root_cannot_be_a_link_outside_configured_store(tmp_path, monkeypatch):
    lab, _ = _store(tmp_path / "store")
    folder = lab.store / "experiments/E-model"
    outside = tmp_path / "outside-experiment"
    folder.rename(outside)
    folder.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(lab, "inspect_experiment", lambda *args, **kwargs: pytest.fail("External store link reached Core"))
    with pytest.raises(ValueError, match="escapes verified root"):
        reporting.verified_record(lab, "E-model")


def test_parent_cycle_is_detected_before_core_recursion(tmp_path, monkeypatch):
    lab, results = _store(tmp_path)
    result = deepcopy(results["E-cad"])
    result["parent_experiment_id"] = "E-child"
    _reanchor(lab, "E-cad", result)
    monkeypatch.setattr(lab, "inspect_experiment", lambda *args, **kwargs: pytest.fail("Parent cycle reached Core"))
    with pytest.raises(ValueError, match="Cyclic"):
        reporting.verified_record(lab, "E-child")


@pytest.mark.parametrize("target", ["experiments/E-model/simulation/raw.log", "ledger/E-model.json"])
def test_export_rechecks_bytes_changed_after_record_verification(tmp_path, monkeypatch, target):
    lab, _ = _store(tmp_path)
    verified = reporting.verified_record

    def change_after_verify(*args):
        record = verified(*args)
        path = lab.store / target
        path.write_bytes(path.read_bytes() + b" ")
        return record

    monkeypatch.setattr(reporting, "verified_record", change_after_verify)
    with pytest.raises(ValueError, match="(?i)hash mismatch"):
        reporting.bundle_bytes(lab, "E-model")


def test_changed_manifest_after_first_core_inspection_never_reaches_summary_inspection(tmp_path, monkeypatch):
    lab, _ = _store(tmp_path)
    original_inspect = lab.inspect_experiment
    calls = 0

    def mutate_after_inspect(identifier, **kwargs):
        nonlocal calls
        calls += 1
        assert calls == 1, "Changed manifest reached another Core inspection"
        result = original_inspect(identifier, **kwargs)
        changed = deepcopy(result)
        changed["artifacts"].append({"path": "../outside", "sha256": "0" * 64, "size_bytes": 0})
        _reanchor(lab, identifier, changed)
        return result

    monkeypatch.setattr(lab, "inspect_experiment", mutate_after_inspect)
    with pytest.raises(ValueError, match="(?i)hash mismatch"):
        reporting.verified_record(lab, "E-model")
    assert calls == 1


def test_export_detects_artifact_change_after_collection_before_zip(tmp_path, monkeypatch):
    lab, _ = _store(tmp_path)
    record = reporting.verified_record(lab, "E-model")
    monkeypatch.setattr(reporting, "verified_record", lambda *args: record)
    original_read = reporting._read
    target = lab.store / "experiments/E-model/simulation/raw.log"
    changed = False

    def race(root, path, **kwargs):
        nonlocal changed
        data = original_read(root, path, **kwargs)
        if path == target and not changed:
            changed = True
            path.write_bytes(data + b"changed after collection")
        return data

    monkeypatch.setattr(reporting, "_read", race)
    with pytest.raises(ValueError, match="(?i)hash mismatch"):
        reporting.bundle_bytes(lab, "E-model")


def test_current_study_snapshot_and_missing_legacy_registry_are_explicit(tmp_path):
    lab, results = _store(tmp_path)
    study_path = lab.store / "studies" / STUDY / "study.json"
    study = load_json(study_path)
    study["hypothesis"] = "Current metadata; original result hypothesis stays TEST ONLY"
    save_json(study_path, study)
    result = deepcopy(results["E-pde"])
    result["artifacts"] = [entry for entry in result["artifacts"] if entry["path"] != "registry_snapshot.json"]
    (lab.store / "experiments/E-pde/registry_snapshot.json").unlink()
    _reanchor(lab, "E-pde", result)
    record = reporting.verified_record(lab, "E-pde")
    assert record["study"] == study and record["result"]["study"]["hypothesis"] == "TEST ONLY"
    assert record["registry_snapshot"] is None and record["hashes"]["registry_snapshot_sha256"] is None
    assert "Current study" in record["limitations"]["study"]
    with zipfile.ZipFile(io.BytesIO(reporting.bundle_bytes(lab, "E-pde"))) as archive:
        assert json.loads(archive.read(f"studies/{STUDY}/study.json")) == study
        assert "experiments/E-pde/registry_snapshot.json" not in archive.namelist()


def test_partial_execution_failure_remains_visible_with_retained_raw_files(tmp_path):
    lab, results = _store(tmp_path, model_mode="crash")
    record = reporting.verified_record(lab, "E-model")
    assert record["result"] == results["E-model"]
    assert record["result"]["status"] == record["result"]["solver_status"] == "FAILED_EXECUTION"
    assert record["result"]["decision"] == "NOT_RELEASED" and record["result"]["metrics"] == {}
    assert "FAILED_EXECUTION" in reporting.render_html(record)
    with zipfile.ZipFile(io.BytesIO(reporting.bundle_bytes(lab, "E-model"))) as archive:
        assert "experiments/E-model/simulation/raw.log" in archive.namelist()


def _memory_record(identifier, *, study_id=STUDY):
    """An in-memory verified-shape fixture; no real execution is claimed."""
    documents = []
    artifacts = []
    for name in ("result.json", "thread.json", "proposal.json", "registry_snapshot.json"):
        path = f"experiments/{identifier}/{name}"
        data = f"TEST ONLY: {path}".encode()
        documents.append({"path": path, "sha256": _sha(data), "size_bytes": len(data), "role": name})
        if name in ("proposal.json", "registry_snapshot.json"):
            artifacts.append({"path": name, "sha256": _sha(data), "size_bytes": len(data), "revision": "1" * 64})
    for path in (f"ledger/{identifier}.json", f"studies/{study_id}/study.json"):
        data = f"TEST ONLY: {path}".encode()
        documents.append({"path": path, "sha256": _sha(data), "size_bytes": len(data), "role": "metadata"})
    return {"result": {"experiment_id": identifier, "cad_revision": "1" * 64, "artifacts": artifacts},
            "hashes": {"documents": documents}, "parent_chain": []}


def test_aggregate_preflight_deduplicates_parents_without_rendering_summaries(tmp_path, monkeypatch):
    lab, results = _store(tmp_path)
    originals = _originals(tmp_path)
    calls = []
    preflight = reporting._preflight

    def counted(store, identifier):
        calls.append(identifier)
        return preflight(store, identifier)

    def forbidden(*args, **kwargs):
        pytest.fail("Aggregate preflight does not need a Core inspection or a research summary")

    monkeypatch.setattr(reporting, "_preflight", counted)
    monkeypatch.setattr(lab, "inspect_experiment", forbidden)
    monkeypatch.setattr(lab, "research_summary", forbidden)
    records = reporting.preflight_records(lab, ["E-child", "E-cad", "E-child", "E-model"])
    assert calls == ["E-child", "E-cad", "E-model"]
    assert {item["result"]["experiment_id"] for item in records} == {"E-child", "E-cad", "E-model"}
    assert all(item["result"] == results[item["result"]["experiment_id"]] for item in records)
    reporting.recheck_records(lab, records)
    assert _originals(tmp_path) == originals


@pytest.mark.parametrize("phase", ["before", "after"])
def test_aggregate_inspection_detects_changed_payload_before_and_after_core(tmp_path, phase):
    lab, _ = _store(tmp_path)
    records = reporting.preflight_records(lab, ["E-child", "E-cad"])
    (tmp_path / "experiments/E-child/simulation/raw.log").write_bytes(b"Changed TEST ONLY bytes")
    with pytest.raises(ValueError, match="hash mismatch"):
        if phase == "before":
            reporting.preflight_records(lab, ["E-child"])
        else:
            reporting.recheck_records(lab, records)


def test_aggregate_preflight_rejects_parent_cycle_before_any_payload(tmp_path, monkeypatch):
    child, parent = _memory_record("E-child"), _memory_record("E-parent")
    child["result"]["parent_experiment_id"] = "E-parent"
    parent["result"]["parent_experiment_id"] = "E-child"
    records = {"E-child": child, "E-parent": parent}
    monkeypatch.setattr(reporting, "_preflight", lambda store, identifier: deepcopy(records[identifier]))
    lab, forbidden = _memory_lab(tmp_path)
    monkeypatch.setattr(reporting, "_read", forbidden)
    with pytest.raises(ValueError, match="Cyclic"):
        reporting.preflight_records(lab, ["E-child"])


def test_aggregate_preflight_rejects_portable_alias_before_any_payload(tmp_path, monkeypatch):
    records = {name: _memory_record(name) for name in ("E-cad", "e-cad")}
    monkeypatch.setattr(reporting, "_preflight", lambda store, identifier: deepcopy(records[identifier]))
    lab, forbidden = _memory_lab(tmp_path)
    monkeypatch.setattr(reporting, "_read", forbidden)
    with pytest.raises(ValueError, match="Case-insensitive"):
        reporting.preflight_records(lab, ["E-cad", "e-cad"])


def _memory_lab(tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("Portable collision reached Core or artifact collection")

    return SimpleNamespace(store=tmp_path, inspect_experiment=forbidden,
                           research_summary=forbidden, inspect_study=forbidden), forbidden


@pytest.mark.parametrize("alias", ["Result.json", "THREAD.JSON", "Proposal.json", "Registry_snapshot.json"])
@pytest.mark.parametrize("operation", ["verified_record", "bundle_bytes"])
def test_memory_casefold_common_document_artifact_alias_is_rejected_before_core(tmp_path, monkeypatch, alias, operation):
    record = _memory_record("E-memory")
    record["result"]["artifacts"].append({"path": alias, "sha256": _sha(b"TEST ONLY"),
                                           "size_bytes": len(b"TEST ONLY"), "revision": "1" * 64})
    lab, forbidden = _memory_lab(tmp_path)
    monkeypatch.setattr(reporting, "_preflight", lambda *args: deepcopy(record))
    monkeypatch.setattr(reporting, "_read", forbidden)
    with pytest.raises(ValueError, match="Case-insensitive export path collision"):
        getattr(reporting, operation)(lab, "E-memory")


@pytest.mark.parametrize("operation", ["verified_record", "bundle_bytes"])
def test_memory_casefold_parent_chain_collision_is_rejected_before_any_bytes(tmp_path, monkeypatch, operation):
    child, parent = _memory_record("E-memory"), _memory_record("e-memory")
    child["result"]["parent_experiment_id"] = "e-memory"
    child["parent_chain"] = [parent]
    lab, forbidden = _memory_lab(tmp_path)
    monkeypatch.setattr(reporting, "_read", forbidden)
    if operation == "verified_record":
        records = {"E-memory": child, "e-memory": parent}
        monkeypatch.setattr(reporting, "_preflight", lambda store, identifier: deepcopy(records[identifier]))
    else:
        # Also exercise the bundle's independent global guard after inspection.
        monkeypatch.setattr(reporting, "verified_record", lambda *args: deepcopy(child))
    with pytest.raises(ValueError, match="Case-insensitive export path collision"):
        getattr(reporting, operation)(lab, "E-memory")


@pytest.mark.parametrize("reserved", ["report.html", "report.json", "bundle_manifest.json"])
@pytest.mark.parametrize("case", ["exact", "alias"])
def test_memory_casefold_generated_payload_names_are_reserved(tmp_path, monkeypatch, reserved, case):
    record = _memory_record("E-memory")
    path = reserved if case == "exact" else reserved.upper()
    record["hashes"]["documents"].append({"path": path, "sha256": _sha(b"TEST ONLY"),
                                           "size_bytes": len(b"TEST ONLY"), "role": "metadata"})
    lab, forbidden = _memory_lab(tmp_path)
    monkeypatch.setattr(reporting, "verified_record", lambda *args: deepcopy(record))
    monkeypatch.setattr(reporting, "_read", forbidden)
    with pytest.raises(ValueError, match="Case-insensitive export path collision"):
        reporting.bundle_bytes(lab, "E-memory")


def test_memory_casefold_exact_shared_sources_remain_unchanged():
    child, parent = _memory_record("E-child-memory"), _memory_record("E-parent-memory")
    originals = deepcopy([child, parent])
    sources = reporting._all_source_files([child, parent])
    assert [record for record, _ in sources] == originals
    assert [child, parent] == originals
    for record, files in sources:
        identifier = record["result"]["experiment_id"]
        assert len(files) == len(record["hashes"]["documents"])
        assert len({path.casefold() for path in files}) == len(files)
        for artifact in record["result"]["artifacts"]:
            path = f"experiments/{identifier}/{artifact['path']}"
            assert files[path]["sha256"] == artifact["sha256"]
            assert files[path]["size_bytes"] == artifact["size_bytes"]
            assert files[path]["revision"] == artifact["revision"]
    shared = f"studies/{STUDY}/study.json"
    assert sources[0][1][shared]["sha256"] == sources[1][1][shared]["sha256"]


class ReportConditionsCAD(ReportCAD):
    """An explicit TEST_ONLY selection catalog, with no CAD kernel lookup."""

    def conditions_catalog(self, parent_root, parent_result, proposal):
        return {"schema_version": "1.0", "cad_backend": self.backend, "model": "TEST_ONLY",
                "selections": [
                    {"id": "B-final", "label": "TEST ONLY 전체 솔리드 " + INJECTION,
                     "kind": "whole_final_solid", "roles": ["material"]},
                    {"id": "S-base", "label": "TEST ONLY 바닥", "kind": "adapter_region", "roles": ["boundary"]},
                    {"id": "S-saddle", "label": "TEST ONLY 새들", "kind": "adapter_region", "roles": ["load"]}],
                "coordinate_systems": [{"id": "global", "label": "TEST ONLY 전역 직교 좌표계",
                    "type": "cartesian", "unit": "mm", "origin": [0, 0, 0],
                    "basis": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}],
                "limitations": ["TEST ONLY: 영역과 원본 전달 검사이며 물리 검증이 아닙니다. " + INJECTION]}


class ReportConditionsAnalysis(ReportAnalysis):
    conditions_version = "TEST_ONLY"

    @staticmethod
    def conditions_preflight(catalog, declaration):
        return {"status": "SUPPORTED_DECLARED_INPUTS", "reasons": ["TEST ONLY transfer"],
                "native_runtime": "NOT_CHECKED"}

    @staticmethod
    def conditions_policy_identity():
        return {"TEST_ONLY": "a" * 64}

    @staticmethod
    def settings_from_conditions(catalog, declaration):
        # No mechanics: preserve exact inputs for report/immutable snapshot tests.
        return {"test_only_declaration": deepcopy(declaration)}


@pytest.fixture(scope="module")
def conditions_report_record(tmp_path_factory):
    cad, analysis = ReportConditionsCAD(), ReportConditionsAnalysis("complete")
    lab = Lab(tmp_path_factory.mktemp("report-test-only-conditions"), adapters={cad.backend: cad},
              analysis_adapters={analysis.backend: analysis}, model_analysis_adapters={},
              pde_adapters={}, doe_adapters={}, optimization_adapters={})
    lab.create_study(STUDY, "TEST ONLY readable conditions", "Retain exact declared inputs?", "TEST ONLY", "No physics")
    lab.run_experiment(study_id=STUDY, experiment_id="E-conditions-cad", backend=cad.backend,
                       model="TEST_ONLY", values={})
    described = lab.describe_analysis_conditions("E-conditions-cad")
    declaration = {
        "analysis_type": "linear_static", "units": {"length": "mm", "force": "N", "stress": "MPa"},
        "coordinate_system": "global",
        "materials": [{"id": "M-declared", "selection_id": "B-final", "law": "isotropic_linear_elastic",
            "young_modulus_MPa": 210000.0, "poisson_ratio": .3,
            "source": {"category": "ASSUMED", "description": "TEST ONLY 명시한 가정 " + INJECTION}}],
        "loads": [{"id": "L-signed", "selection_id": "S-saddle", "type": "resultant_force",
            "components": {"FX": -2.5, "FY": 0.0, "FZ": -150.0}, "unit": "N", "coordinate_system": "global",
            "source": "TEST ONLY signed vector " + INJECTION}],
        "boundary_conditions": [{"id": "BC-fixed", "selection_id": "S-base", "type": "displacement",
            "components": {"UX": 0, "UY": 0.0, "UZ": -0.0}, "unit": "mm", "coordinate_system": "global",
            "source": "TEST ONLY exact fixed components " + INJECTION}],
        "mesh": {"mode": "selected", "max_size_mm": 4.0},
        "contact": {"mode": "none", "source": "TEST ONLY no contact " + INJECTION}}
    saved = lab.save_analysis_conditions(conditions_id="C-report", experiment_id="E-conditions-cad",
        cad_revision=described["source"]["cad_revision"], catalog_revision=described["catalog_revision"],
        backend=analysis.backend, declaration=declaration)
    lab.run_analysis(parent_experiment_id="E-conditions-cad", experiment_id="E-conditions-child",
                     backend=analysis.backend, conditions_id=saved["id"])
    return lab, reporting.verified_record(lab, "E-conditions-child")


def _readable_html(document):
    class Visible(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth = 0
            self.values = []

        def handle_starttag(self, tag, attrs):
            if tag in ("details", "style"):
                self.depth += 1

        def handle_endtag(self, tag):
            if tag in ("details", "style"):
                self.depth -= 1

        def handle_data(self, value):
            if not self.depth:
                self.values.append(value)

    parser = Visible()
    parser.feed(document)
    return " ".join(parser.values)


def test_declared_conditions_are_readable_exact_escaped_and_unqualified(conditions_report_record):
    _, record = conditions_report_record
    before = deepcopy(record)
    document = reporting.render_html(record)
    readable = _readable_html(document)
    for token in ("이 해석에 사용한 선언 조건", "E-conditions-child", "E-conditions-cad", "C-report",
                  record["result"]["cad_revision"], "isotropic_linear_elastic", "210000.0", "0.3", "ASSUMED",
                  "B-final", "S-base", "S-saddle", "FX = -2.5", "FY = 0.0", "FZ = -150.0", "N",
                  "UX = 0", "UY = 0.0", "UZ = -0.0", "mm", "MPa", "global", "cartesian",
                  "selected", "4.0", "none", "UNKNOWN", "NOT_RELEASED", "USER_DECLARED_UNVERIFIED"):
        assert token in readable
    assert "재료" in readable and "0으로 선언한 성분은 고정 구속" in readable
    assert "메시 독립성이나 접촉 검증을 뜻하지 않습니다" in readable
    assert INJECTION in readable and escape(INJECTION, quote=True) in document
    assert "<script" not in document and "<img" not in document
    assert "기록된 converged: true" in readable and "수치 수렴: 확인됨" not in readable
    assert record == before


@pytest.mark.parametrize("path,value", [
    (("integrity",), "UNKNOWN"),
    (("summary", "experiment_id"), "E-other"),
    (("summary", "metrics"), {}),
    (("summary", "analysis_conditions_context", "source_experiment_id"), "E-template-baseline"),
    (("summary", "analysis_conditions_context", "cad_revision"), "0" * 64),
    (("summary", "analysis_conditions_context", "reference", "record_sha256"), "f" * 64),
    (("summary", "analysis_conditions_context", "engineering"), "PASS"),
    (("summary", "analysis_conditions_context", "catalog", "selections", 0, "label"), "Other model"),
    (("proposal", "study_id"), "S-other"),
    (("proposal", "parent_experiment_id"), "E-other"),
    (("proposal", "model", "geometry", "source_experiment_id"), "E-other"),
    (("proposal", "physics", "backend"), "other.backend"),
    (("proposal", "execution"), {}),
    (("proposal", "model", "materials", 0, "young_modulus_MPa"), 1800),
    (("proposal", "loads", 0, "components", "FZ"), 150.0),
    (("proposal", "boundary_conditions", 0, "components", "UZ"), 1.0),
    (("proposal", "model", "conditions_mesh", "max_size_mm"), 2.0),
    (("proposal", "model", "contact_declaration", "mode"), "bonded"),
    (("thread", "analysis_conditions"), {}),
    (("summary", "analysis_conditions_context", "declaration", "loads", 0, "unit"), "kN")])
def test_context_mismatch_never_presents_active_conditions(conditions_report_record, path, value):
    _, original = conditions_report_record
    before = deepcopy(original)
    record = deepcopy(original)
    target = record
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    document = reporting.render_html(record)
    readable = _readable_html(document)
    assert "이 기록에 결합된 선언형 실행 조건을 확인할 수 없습니다" in readable
    assert "이 해석에 사용한 선언 조건" not in readable and "E-template-baseline" not in readable
    assert "원 실행 입력은 아래 상세에 보존됩니다" in readable
    assert "실행 입력과 공통 모델 선언" in document
    assert original == before


def test_missing_snapshot_and_parent_only_do_not_borrow_active_conditions(conditions_report_record):
    lab, original = conditions_report_record
    missing = deepcopy(original)
    missing["result"]["artifacts"] = [item for item in missing["result"]["artifacts"]
                                       if item["path"] != "analysis_conditions.json"]
    assert "이 해석에 사용한 선언 조건" not in _readable_html(reporting.render_html(missing))
    parent = reporting.verified_record(lab, "E-conditions-cad")
    assert "analysis_conditions_context" not in parent["summary"]
    parent["summary"]["analysis_conditions_context"] = deepcopy(original["summary"]["analysis_conditions_context"])
    assert "이 기록에 결합된 선언형 실행 조건을 확인할 수 없습니다" in _readable_html(reporting.render_html(parent))


def test_named_contact_pairs_are_reported_as_declarations_only(conditions_report_record):
    _, original = conditions_report_record
    record = deepcopy(original)
    contact = {"mode": "frictionless", "source": "TEST ONLY declared pair " + INJECTION,
               "pairs": [{"selection_a": "B-final", "selection_b": "S-saddle"}]}
    record["summary"]["analysis_conditions_context"]["declaration"]["contact"] = deepcopy(contact)
    record["proposal"]["model"]["contact_declaration"] = deepcopy(contact)
    # In-memory presentation probe only: no physical native/contact evidence.
    readable = _readable_html(reporting.render_html(record))
    assert "frictionless" in readable and "↔" in readable
    assert "B-final" in readable and "S-saddle" in readable
    assert "접촉 검증을 뜻하지 않습니다" in readable


def test_conditions_bundle_keeps_snapshot_and_all_native_test_bytes_without_current_namespace(conditions_report_record):
    lab, record = conditions_report_record
    snapshot = lab.store / "experiments/E-conditions-child/analysis_conditions.json"
    raw = snapshot.read_bytes()
    # This TEST_ONLY mutable namespace is deliberately no longer readable.
    (lab.store / "analysis_conditions/C-report/record.json").write_bytes(b"TEST ONLY changed current namespace")
    before = _originals(lab.store)
    exported = reporting.bundle_bytes(lab, "E-conditions-child")
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        assert archive.read("experiments/E-conditions-child/analysis_conditions.json") == raw
        assert record["result"]["provenance"]["analysis_conditions"]["record_sha256"] == _sha(raw)
        for path in ("experiments/E-conditions-cad/cad/native.FCStd", "experiments/E-conditions-cad/cad/assembly.step",
                     "experiments/E-conditions-child/simulation/native.inp", "experiments/E-conditions-child/simulation/raw.log"):
            assert archive.read(path) == before[path]
        assert not any(path.startswith("analysis_conditions/") for path in archive.namelist())
        manifest = json.loads(archive.read("bundle_manifest.json"))
        for entry in manifest["files"]:
            payload = archive.read(entry["path"])
            assert _sha(payload) == entry["sha256"] and len(payload) == entry["size_bytes"]
        restored = json.loads(archive.read("report.json"))
        assert restored == record
        assert "FZ = -150.0" in _readable_html(archive.read("report.html").decode("utf-8"))
    assert _originals(lab.store) == before


def _loaded_displacement_record(original):
    """TEST_ONLY in-memory semantic envelope; no fake saved/native result."""
    record = deepcopy(original)
    record["result"]["provenance"].update(adapter="fixture.calculix", adapter_version="6")
    metric = {"value": .00002355013, "unit": "mm", "valid": True}
    record["result"]["metrics"] = {"max_displacement": metric,
        "peak_stress": {"value": None, "unit": "MPa", "valid": False, "reason": REASON}}
    record["summary"]["metrics"] = deepcopy(record["result"]["metrics"])
    record["summary"]["metric_semantics"] = {"max_displacement": {
        "label": "하중 새들 절점 최대 |UZ|", "quantity": "displacement", "component": "UZ", "reduction": "MAX_ABSOLUTE",
        "selection_id": "S-saddle", "coordinate_system": "global", "unit": "mm", "source": "ADAPTER_DECLARED_RESPONSE"}}
    return record


def test_metric_labels_use_exact_declared_scope_and_keep_invalid_observations(conditions_report_record):
    record = _loaded_displacement_record(conditions_report_record[1])
    before = deepcopy(record)
    readable = _readable_html(reporting.render_html(record))
    assert "하중 새들 절점 최대 |UZ|" in readable and "최대 변위 크기" not in readable
    assert "전체 |U|" not in readable and "2.355013e-05" in readable
    assert "판단에 사용할 수 없음" in readable and "MPa" in readable and REASON in readable
    assert "미확인" in readable and "공학적 사용 미승인" in readable
    assert record == before


@pytest.mark.parametrize("path,value", [
    (("result", "provenance", "adapter_version"), "5"),
    (("result", "provenance", "adapter"), "other.backend"),
    (("summary", "experiment_id"), "E-other"),
    (("summary", "metric_semantics"), None),
    (("summary", "metric_semantics"), []),
    (("summary", "metric_semantics", "max_displacement", "unit"), "m"),
    (("summary", "metric_semantics", "max_displacement", "component"), "norm"),
    (("summary", "metric_semantics", "max_displacement", "selection_id"), "B-final"),
    (("summary", "metric_semantics", "max_displacement", "source"), "INFERRED"),
    (("summary", "metric_semantics", "max_displacement", "label"), "")])
def test_incomplete_or_foreign_semantics_do_not_infer_loaded_response_label(conditions_report_record, path, value):
    record = _loaded_displacement_record(conditions_report_record[1])
    target = record
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    readable = _readable_html(reporting.render_html(record))
    assert "하중 새들 절점 최대 |UZ|" not in readable and "최대 변위 크기" not in readable
    assert "결과값 1" in readable and "2.355013e-05" in readable and REASON in readable


def test_custom_declared_metric_text_is_escaped(conditions_report_record):
    record = deepcopy(conditions_report_record[1])
    record["summary"]["metric_semantics"] = {"test_response": {
        "label": "TEST ONLY response " + INJECTION, "unit": "mm", "source": "ADAPTER_DECLARED_RESPONSE"}}
    document = reporting.render_html(record)
    assert "<script" not in document and escape(INJECTION, quote=True) in document
    assert "TEST ONLY response " + INJECTION in _readable_html(document)
