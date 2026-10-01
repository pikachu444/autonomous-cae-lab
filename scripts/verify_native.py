"""Exercise the CAE-Lab Core against actual editable FreeCAD documents.

Run only where FREECAD_CMD points to a working FreeCAD command wrapper. The
underlying native worker belongs to the pinned fixture domain plugin.
"""

import argparse
import json
from pathlib import Path
import zipfile

from caelab import Lab


BACKEND = "fixture.freecad"


def artifact_paths(result):
    return {item["path"] for item in result["artifacts"]}


def run(store: Path):
    lab = Lab(store)
    lab.create_study("S-native", "Editable three-point bending fixture",
                     "Can native dimensions be researched without losing FCStd history?",
                     "A 38 mm support remains CAD-valid, while a 5 mm bore violates edge land.",
                     "Preserve the editable CAD revision and reject invalid designs before export.")

    model = lab.create_native_model(template="roller_support")["design"]
    candidates = {item["native"]["path"] for item in lab.discover_parameters(BACKEND, model)}
    assert {"SupportBlock|property|Length", "BoltBore1|property|Radius"} <= candidates
    width = lab.register_parameter("S-native", BACKEND, model,
                                   "SupportBlock|property|Length", "support_width",
                                   "Support width", 28, 60)
    assert width["geometry_effect"]["status"] == "PASS"
    bore = lab.register_parameter("S-native", BACKEND, model,
                                  "BoltBore1|property|Radius", "bore_radius",
                                  "Bore radius", 2, 20)
    assert bore["geometry_effect"]["status"] == "PASS"
    assert {p["parameter_id"] for p in lab.registry("S-native")["entries"]} == {
        "support_width", "bore_radius"}

    valid = lab.run_experiment(study_id="S-native", experiment_id="E-native-width38",
                               backend=BACKEND, model=model, values={"support_width": 38})
    assert valid["status"] == "COMPLETED_REVIEW_REQUIRED"
    assert valid["decision"] == "NOT_RELEASED" and valid["cad_revision"]
    assert abs(valid["metrics"]["cad_bounds"]["value"][0] - 38) < 1e-5
    assert {"cad/editable.FCStd", "cad/native.step", "cad/native_printed_part.stl",
            "cad/native_printed_part.3mf", "cad/report.html", "cad/bundle.zip"} <= artifact_paths(valid)
    assert any(v["type"] == "static_strength" and v["status"] == "UNKNOWN"
               for v in valid["validations"])
    assert lab.inspect_experiment("E-native-width38")["cad_revision"] == valid["cad_revision"]
    editable = store / "experiments/E-native-width38/cad/editable.FCStd"
    with zipfile.ZipFile(editable) as cad:
        assert "Document.xml" in cad.namelist()
    reopened = lab.import_native_model(editable)
    assert {p["name"] for p in reopened["parameters"]} == {"support_width", "bore_radius"}

    rejected = lab.run_experiment(study_id="S-native", experiment_id="E-native-clearance",
                                  backend=BACKEND, model=model, values={"bore_radius": 5})
    assert rejected["status"] == "REJECTED" and rejected["cad_revision"] is None
    assert any(v["type"] == "bore_1_edge_land" and v["status"] == "FAIL"
               for v in rejected["validations"])
    assert not any(path.endswith((".step", ".stl", ".3mf", ".FCStd"))
                   for path in artifact_paths(rejected))
    assert lab.research_summary("E-native-clearance")["failures"]

    sketch = lab.create_native_model(template="sketch_locator")["design"]
    sketch_candidates = [item for item in lab.discover_parameters(BACKEND, sketch)
                         if item["native"]["object"] == "LocatorProfile"]
    assert len(sketch_candidates) == 1 and sketch_candidates[0]["value"] == 4
    lab.register_parameter("S-native", BACKEND, sketch, sketch_candidates[0]["native"]["path"],
                           "locator_radius", "Locator radius", 2, 10)
    sketch_result = lab.run_experiment(study_id="S-native", experiment_id="E-native-sketch6",
                                       backend=BACKEND, model=sketch, values={"locator_radius": 6})
    assert sketch_result["status"] == "COMPLETED_REVIEW_REQUIRED"
    assert abs(sketch_result["metrics"]["cad_bounds"]["value"][0] - 12) < 1e-5
    assert "cad/editable.FCStd" in artifact_paths(sketch_result)

    try:
        lab.register_parameter("S-native", BACKEND, model, "BoltBore1|property|Height",
                               "ineffective_height", "Cutter height", 20, 40)
    except ValueError as exc:
        assert "no measurable effect" in str(exc).lower(), str(exc)
    else:
        raise AssertionError("A dimension without final-solid effect was accepted")

    summary = {"status": "PASS", "model": model,
               "valid_cad_revision": valid["cad_revision"],
               "valid_bounds_mm": valid["metrics"]["cad_bounds"]["value"],
               "reopened_editable_parameters": sorted(p["name"] for p in reopened["parameters"]),
               "rejected_validation": "bore_1_edge_land", "sketch_bounds_mm":
               sketch_result["metrics"]["cad_bounds"]["value"],
               "ineffective_dimension_blocked": True,
               "release": valid["decision"]}
    (store / "native_acceptance.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    run(parser.parse_args().store.resolve())
