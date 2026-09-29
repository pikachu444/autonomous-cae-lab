import json
from pathlib import Path
import zipfile

import pytest
import cadquery as cq

from caelab import Lab


BACKEND = "fixture.cadquery"
MODEL = "roller_support"


@pytest.fixture
def lab(tmp_path):
    lab = Lab(tmp_path)
    lab.create_study("S004", "Bend support", "Does widening retain a valid fixture?",
                     "Width 38 mm retains the required land", "Compare bounds and CAD validity")
    return lab


def test_real_cad_vertical_slice_with_rejection_and_evidence(lab):
    candidates = lab.discover_parameters(BACKEND, MODEL)
    assert {"support_width_mm", "bolt_pitch_x_mm", "edge_land_mm"} <= {
        c["native"]["path"] for c in candidates}
    mapped = lab.register_parameter("S004", BACKEND, MODEL, "support_width_mm",
                                    "support_width", "Support width", 28, 60)
    assert mapped["native"]["path"] == "support_width_mm"
    assert mapped["geometry_effect"]["status"] == "PASS"
    # Symmetric bore movement preserves gross bounding-box and centroid metrics.
    bolt = lab.register_parameter("S004", BACKEND, MODEL, "bolt_pitch_x_mm",
                                  "bolt_pitch", "Bolt pitch", 18, 40)
    assert bolt["geometry_effect"]["status"] == "PASS"
    assert lab.registry("S004")["revision"] == 2

    accepted = lab.run_experiment(study_id="S004", experiment_id="E031", backend=BACKEND,
                                  model=MODEL, values={"support_width": 38})
    assert accepted["status"] == "COMPLETED_REVIEW_REQUIRED"
    assert accepted["decision"] == "NOT_RELEASED"
    assert accepted["metrics"]["cad_bounds"]["value"] == pytest.approx([38, 40, 26])
    step = lab.store / "experiments/E031/cad/assembly.step"
    assert cq.importers.importStep(str(step)).val().BoundingBox().xlen == pytest.approx(38)
    assert accepted["cad_revision"]
    assert any(v["type"] == "static_strength" and v["status"] == "UNKNOWN"
               for v in accepted["validations"])
    assert {"cad/cad_source.py", "cad/assembly.step", "cad/roller_support.stl",
            "cad/roller_support.3mf", "cad/report.html", "cad/bundle.zip"} <= {a["path"] for a in accepted["artifacts"]}
    with zipfile.ZipFile(lab.store / "experiments/E031/cad/bundle.zip") as bundle:
        assert "assembly.step" in bundle.namelist()
    assert lab.inspect_experiment("E031")["provenance"]["source_commit"] == (
        "3e48bf6138f495299f45b1af254bfb4aaff307b8")
    assert lab.research_summary("E031")["unknown"]

    rejected = lab.run_experiment(study_id="S004", experiment_id="E032", backend=BACKEND,
                                  model=MODEL, values={"bolt_pitch": 30})
    assert rejected["status"] == "REJECTED"
    assert rejected["cad_revision"] is None
    assert any(v["type"] == "cad_source_relation" and v["status"] == "FAIL"
               for v in rejected["validations"])
    assert not list((lab.store / "experiments/E032/cad").glob("*.step"))
    with zipfile.ZipFile(lab.store / "experiments/E032/cad/bundle.zip") as bundle:
        assert not any(n.endswith((".step", ".stl", ".3mf")) for n in bundle.namelist())
    assert any(e["method"] == "cad_source_relation" for e in rejected["evidence"])
    assert rejected["proposal_revision"] != accepted["proposal_revision"]

    out_of_bounds = lab.run_experiment(study_id="S004", experiment_id="E033", backend=BACKEND,
                                       model=MODEL, values={"support_width": 61})
    assert out_of_bounds["status"] == "REJECTED"
    assert not (lab.store / "experiments/E033/cad").exists()
    assert any(v["type"] == "parameter_support_width" and v["status"] == "FAIL"
               for v in out_of_bounds["validations"])


def test_ineffective_parameter_and_immutable_artifact_verification(lab):
    with pytest.raises(ValueError, match="no verified measurable effect"):
        lab.register_parameter("S004", BACKEND, MODEL, "edge_land_mm",
                               "edge_land", "Minimum edge land", 2, 8)
    assert lab.registry("S004")["entries"] == []
    lab.register_parameter("S004", BACKEND, MODEL, "support_width_mm",
                           "support_width", "Support width", 28, 60)
    lab.run_experiment(study_id="S004", experiment_id="E040", backend=BACKEND,
                       model=MODEL, values={"support_width": 38})
    with pytest.raises(FileExistsError):
        lab.run_experiment(study_id="S004", experiment_id="E040", backend=BACKEND,
                           model=MODEL, values={"support_width": 38})
    (lab.store / "experiments/E040/cad/report.html").write_text("modified")
    with pytest.raises(ValueError, match="hash mismatch"):
        lab.inspect_experiment("E040")


def test_backend_crash_is_not_a_design_rejection_and_result_is_checked(lab):
    from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
    from caelab.contracts import Outcome

    class CrashingAdapter(FixtureCadQueryAdapter):
        def regenerate(self, model, values, output):
            raise RuntimeError("fixture backend unavailable")

    lab.register_parameter("S004", BACKEND, MODEL, "support_width_mm",
                           "support_width", "Support width", 28, 60)
    failed = Lab(lab.store, adapters={BACKEND: CrashingAdapter()}).run_experiment(
        study_id="S004", experiment_id="E-crash", backend=BACKEND, model=MODEL,
        values={"support_width": 38})
    assert failed["status"] == "FAILED_EXECUTION"
    assert failed["cad_revision"] is None
    assert failed["decision"] == "NOT_RELEASED"
    result_path = lab.store / "experiments/E-crash/result.json"
    data = json.loads(result_path.read_text())
    data["decision"] = "RELEASED"
    result_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="result.json hash mismatch"):
        lab.inspect_experiment("E-crash")

    class SilentRejectAdapter(FixtureCadQueryAdapter):
        def regenerate(self, model, values, output):
            return Outcome(decision="REJECTED", checks=[], generated=False)

    rejected = Lab(lab.store, adapters={BACKEND: SilentRejectAdapter()}).run_experiment(
        study_id="S004", experiment_id="E-silent-reject", backend=BACKEND, model=MODEL,
        values={"support_width": 38})
    assert rejected["status"] == "REJECTED"
    assert any(v["type"] == "adapter_rejected" and v["status"] == "FAIL"
               for v in rejected["validations"])


def test_parameter_value_that_no_longer_changes_geometry_is_blocked(lab, tmp_path, monkeypatch):
    from caelab.adapters.fixture_cadquery import _upstream
    model_cad = _upstream()

    models = tmp_path / "models"
    models.mkdir()
    (models / "conditional_block.py").write_text('''import cadquery as cq
FIXTURE_META = {"title": "Conditional", "description": "For effect testing", "parameters": {
    "width_mm": {"label": "Width", "unit": "mm", "min": 10, "max": 30}}}
width_mm = 12.0
effective_width = width_mm if width_mm < 14 else 12.0
show_object(cq.Workplane("XY").box(effective_width, 9, 7))
''')
    monkeypatch.setattr(model_cad, "MODELS", models)
    lab.register_parameter("S004", BACKEND, "conditional_block", "width_mm",
                           "width", "Width", 10, 30)
    result = lab.run_experiment(study_id="S004", experiment_id="E-noop",
                                backend=BACKEND, model="conditional_block", values={"width": 20})
    assert result["status"] == "REJECTED"
    assert result["cad_revision"] is None
    assert any(v["type"] == "geometry_effect_width_mm" and v["status"] == "FAIL"
               for v in result["validations"])
    assert not (lab.store / "experiments/E-noop/cad").exists()


def test_registry_refresh_after_native_source_change(lab, tmp_path, monkeypatch):
    from caelab.adapters.fixture_cadquery import _upstream
    model_cad = _upstream()
    models = tmp_path / "models"
    models.mkdir()
    source = models / "revisable.py"

    def write_source(default):
        source.write_text('''import cadquery as cq
FIXTURE_META = {"title": "Revisable", "description": "A revised source", "parameters": {
  "width_mm": {"label": "Width", "unit": "mm", "min": 10, "max": 40}}}
width_mm = %s
show_object(cq.Workplane("XY").box(width_mm, 9, 7))
''' % default)

    write_source(12.0)
    monkeypatch.setattr(model_cad, "MODELS", models)
    lab.register_parameter("S004", BACKEND, "revisable", "width_mm",
                           "width", "Width", 10, 40)
    original = lab.run_experiment(study_id="S004", experiment_id="E-before",
                                  backend=BACKEND, model="revisable", values={"width": 18})
    write_source(13.0)
    with pytest.raises(ValueError, match="refresh registry"):
        lab.run_experiment(study_id="S004", experiment_id="E-stale",
                           backend=BACKEND, model="revisable", values={"width": 19})
    refreshed = lab.refresh_registry("S004", BACKEND, "revisable")
    assert refreshed["revision"] == 2
    assert refreshed["entries"][0]["current_value"] == 13
    assert (lab.store / "studies/S004/registry_history/0001.json").is_file()
    updated = lab.run_experiment(study_id="S004", experiment_id="E-after",
                                 backend=BACKEND, model="revisable", values={"width": 19})
    assert updated["status"] == "COMPLETED_REVIEW_REQUIRED"
    assert updated["cad_revision"] != original["cad_revision"]


def test_common_json_schemas(lab):
    jsonschema = pytest.importorskip("jsonschema")
    root = Path(__file__).resolve().parents[1]
    lab.register_parameter("S004", BACKEND, MODEL, "support_width_mm",
                           "support_width", "Support width", 28, 60)
    lab.run_experiment(study_id="S004", experiment_id="E051", backend=BACKEND,
                       model=MODEL, values={"support_width": 38})
    for name, instance in (("experiment", json.loads((lab.store / "experiments/E051/proposal.json").read_text())),
                           ("result", lab.inspect_experiment("E051"))):
        schema = json.loads((root / "schemas" / f"{name}.schema.json").read_text())
        jsonschema.validate(instance, schema)
