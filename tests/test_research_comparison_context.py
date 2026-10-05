"""Existing Core research summaries, TEST-ONLY producer; no provider/native solve."""

from copy import deepcopy
import hashlib
import pytest

from caelab import research_context
from caelab.storage import load_json, save_json
from test_response_comparison import lab, request, originals
from test_response_history import lab as history_lab, request as history_request


def test_legacy_shape_and_verified_same_record_context(lab):
    original = lab.research_summary("E-test")
    assert "comparison_context" not in original
    before = originals(lab)
    saved = lab.save_response_comparison(**request())
    files_before = {p.relative_to(lab.store).as_posix(): p.read_bytes() for p in lab.store.rglob("*") if p.is_file()}
    summary = lab.research_summary("E-test")
    assert {k: v for k, v in summary.items() if k != "comparison_context"} == original
    context = summary["comparison_context"]
    assert context["scan_complete"] is True
    assert context["records"][0]["record"] == saved
    assert context["records"][0]["record_sha256"] == hashlib.sha256(files_before["response_comparisons/C-test/record.json"]).hexdigest()
    assert context["records"][0]["record"]["comparison"]["difference"] == 1.
    assert context["records"][0]["record"]["request"]["observation"]["source_kind"] == "SYNTHETIC"
    assert context["physical_validation"] == "UNKNOWN" and context["decision"] == "NOT_RELEASED"
    assert context["scope_alignment"] == "USER_DECLARED_UNVERIFIED" and context["causal_verdict"] == "NOT_EVALUATED"
    assert files_before == {p.relative_to(lab.store).as_posix(): p.read_bytes() for p in lab.store.rglob("*") if p.is_file()}
    assert originals(lab) == before


def test_null_mismatch_remains_separate_from_metrics(lab):
    body = request()
    body["observation"]["conditions"][0]["value"] = 100.
    saved = lab.save_response_comparison(**body)
    summary = lab.research_summary("E-test")
    item = summary["comparison_context"]["records"][0]["record"]
    assert item == saved
    assert item["comparison"]["status"] == "DECLARED_CONDITION_MISMATCH"
    assert item["comparison"]["difference"] is None
    assert item["comparison"]["within_declared_tolerance"] is None
    assert summary["metrics"]["test_force"]["value"] == 150.
    assert summary["metrics"]["invalid_diagnostic"]["valid"] is False


def test_other_experiment_is_not_borrowed(lab):
    lab.run_model_analysis(study_id="S-test", experiment_id="E-other", backend="test.observation.model", settings={"force_N": 100.})
    saved = lab.save_response_comparison(**request())
    assert lab.research_summary("E-other")["comparison_context"]["records"] == []
    assert lab.research_summary("E-test")["comparison_context"]["records"][0]["record"] == saved


@pytest.mark.parametrize("damage", ["record", "receipt", "recomputed", "oversized", "oversized_receipt", "deep_record", "deep_receipt", "duplicate", "overflow_record", "overflow_receipt", "malformed"])
def test_corrupt_comparison_has_no_verified_payload(lab, damage):
    lab.save_response_comparison(**request())
    folder = lab.store / "response_comparisons/C-test"
    if damage == "record":
        record = load_json(folder / "record.json"); record["comparison"]["difference"] = 0.
        save_json(folder / "record.json", record)
    elif damage == "receipt":
        save_json(folder / "receipt.json", {"id": "other", "record_sha256": "0" * 64})
    elif damage == "recomputed":
        record = load_json(folder / "record.json"); record["comparison"]["difference"] = 0.
        save_json(folder / "record.json", record)
        save_json(folder / "receipt.json", {"id": "C-test", "record_sha256": hashlib.sha256((folder / "record.json").read_bytes()).hexdigest()})
    elif damage == "oversized":
        (folder / "record.json").write_bytes(b" " * (research_context.MAX_RECORD_BYTES + 1))
    elif damage == "oversized_receipt":
        (folder / "receipt.json").write_bytes(b" " * (research_context.MAX_RECEIPT_BYTES + 1))
    elif damage in ("deep_record", "deep_receipt"):
        path = folder / ("record.json" if damage == "deep_record" else "receipt.json")
        path.write_text('{"nest":' + '[' * 1100 + '0' + ']' * 1100 + '}')
    elif damage == "duplicate":
        (folder / "receipt.json").write_text('{"id":"C-test","id":"C-test","record_sha256":"' + '0' * 64 + '"}')
    elif damage in ("overflow_record", "overflow_receipt"):
        path = folder / ("record.json" if damage == "overflow_record" else "receipt.json")
        text = path.read_text().rstrip()
        path.write_text(text[:-1] + ',"extra":1e309}')
        if damage == "overflow_record":
            save_json(folder / "receipt.json", {"id":"C-test", "record_sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    else:
        (folder / "record.json").write_text("invalid json")
    context = lab.research_summary("E-test")["comparison_context"]
    assert context["records"] == []
    assert context["unverified"][0]["integrity"] == "UNKNOWN"
    assert "record" not in context["unverified"][0]
    assert context["decision"] == "NOT_RELEASED"


def test_summary_refuses_result_drift(lab, monkeypatch):
    lab.save_response_comparison(**request())
    original = research_context.inspect_comparison
    def drift(value, identifier):
        record = original(value, identifier)
        path = value.store / "experiments/E-test/result.json"
        changed = load_json(path); changed["input_parameters"]["late_change"] = 1.
        save_json(path, changed)
        return record
    monkeypatch.setattr(research_context, "inspect_comparison", drift)
    with pytest.raises(ValueError, match="changed during"):
        lab.research_summary("E-test")


def test_explicit_omission_does_not_claim_complete_evidence(lab, monkeypatch):
    monkeypatch.setattr(research_context, "MAX_RECORDS", 1)
    lab.save_response_comparison(**request(comparison_id="C-1"))
    lab.save_response_comparison(**request(comparison_id="C-2"))
    context = lab.research_summary("E-test")["comparison_context"]
    assert len(context["records"]) == 1
    assert context["omitted"]["related_records"] == 1 and context["scan_complete"] is False


def test_bounded_scan_and_untrusted_directory(lab, monkeypatch):
    lab.save_response_comparison(**request())
    (lab.store / "response_comparisons/AA-missing").mkdir()
    monkeypatch.setattr(research_context, "MAX_SCAN", 1)
    context = lab.research_summary("E-test")["comparison_context"]
    assert context["records"] == [] and context["unverified"][0]["id"] == "AA-missing"
    assert context["omitted"]["unscanned_entries"] == 1 and context["scan_complete"] is False


def test_history_context_preserves_signed_native_measure_and_axis(history_lab):
    body = history_request()
    saved = history_lab.save_response_comparison(**body)
    item = history_lab.research_summary("E-test")["comparison_context"]["records"][0]["record"]
    assert item == saved and item["schema_version"] == "1.1"
    assert item["comparison"]["response_value"] == pytest.approx(-.6)
    assert item["comparison"]["source_channel"]["component"] == "xy"
    assert item["comparison"]["response_axis"] == {"quantity": "time", "value": .2, "unit": "s"}
    assert item["comparison"]["source_channel"]["origin"]["driver"] == "mgis"


def test_history_mismatch_and_unprepared_initial_state_are_not_relabelled(history_lab):
    body = history_request()
    body["observation"]["axis"]["value"] = .1
    body["response"]["sample_index"] = 0
    history_lab.save_response_comparison(**body)
    record = history_lab.research_summary("E-test")["comparison_context"]["records"][0]["record"]
    comparison = record["comparison"]
    assert comparison["status"] == "DECLARED_AXIS_MISMATCH"
    assert comparison["difference"] is None and comparison["response_axis"]["value"] == 0.
    assert comparison["source_channel"]["initial_state"]["kind"] == "UNPREPARED_INITIAL_CONDITION"


def test_context_refuses_linked_comparison_before_reading_it(lab, tmp_path):
    lab.save_response_comparison(**request())
    folder = lab.store / "response_comparisons/C-test"
    outside = tmp_path / "untrusted-outside"
    outside.mkdir()
    (outside / "record.json").write_text('{"private":"must not be read"}')
    (folder / "record.json").unlink()
    (folder / "record.json").symlink_to(outside / "record.json")
    context = lab.research_summary("E-test")["comparison_context"]
    assert context["records"] == [] and context["unverified"][0]["integrity"] == "UNKNOWN"
    assert "private" not in str(context)


def test_later_record_cannot_leave_earlier_changed_record_verified(lab, monkeypatch):
    lab.save_response_comparison(**request(comparison_id="C-1"))
    lab.save_response_comparison(**request(comparison_id="C-2"))
    original = research_context.inspect_comparison
    def change_earlier(value, identifier):
        record = original(value, identifier)
        if identifier == "C-2":
            path = value.store / "response_comparisons/C-1/receipt.json"
            save_json(path, {"id":"C-1", "record_sha256":"0" * 64})
        return record
    monkeypatch.setattr(research_context, "inspect_comparison", change_earlier)
    context = lab.research_summary("E-test")["comparison_context"]
    assert [entry["record"]["id"] for entry in context["records"]] == ["C-2"]
    assert context["unverified"][0]["id"] == "C-1"
    assert context["unverified"][0]["integrity"] == "UNKNOWN"
