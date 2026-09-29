"""Execute a seeded black-box DOE through registered CAD and real FEA child runs."""

import argparse
import hashlib
import json
from pathlib import Path

from caelab import Lab


def run(store: Path):
    lab = Lab(store)
    lab.create_study("S-doe-ci", "Seeded fixture DOE",
                     "How do registered CAD variables change the preliminary response?",
                     "Valid support widths solve while invalid bolt pitch is blocked before FEA.",
                     "Trace every sample, gate invalid CAD, and keep unqualified physics explicit.")
    lab.register_parameter("S-doe-ci", "fixture.cadquery", "roller_support",
                           "support_width_mm", "support_width", "Support width", 30, 42)
    lab.register_parameter("S-doe-ci", "fixture.cadquery", "roller_support",
                           "bolt_pitch_x_mm", "bolt_pitch", "Bolt pitch", 18, 40)
    material = json.loads((Path(__file__).resolve().parents[1] /
                           "plugins/fixture_design/upstream/examples/printed_material_ASSUMED.json").read_text())
    settings = {"load": {"force_per_support_N": 100.0,
                         "source": "Illustrative DOE screen; not a measured load"},
                "material": material, "mesh": {"max_sizes_mm": [3.0, 2.0]}}
    common = {"study_id": "S-doe-ci", "backend": "fixture.cadquery",
              "model": "roller_support", "sample_count": 2, "seed": 13,
              "analysis_backend": "fixture.calculix", "analysis_settings": settings}
    width_plan = lab.plan_doe(campaign_id="C-width", parameter_ids=["support_width"], **common)
    pitch_plan = lab.plan_doe(campaign_id="C-pitch", parameter_ids=["bolt_pitch"], **common)
    width = lab.run_doe("C-width")
    pitch = lab.run_doe("C-pitch")
    assert lab.inspect_doe("C-width") == width
    assert lab.inspect_doe("C-pitch") == pitch
    assert [v["values"] for v in width_plan["samples"]] == [v["values"] for v in width["samples"]]
    assert [v["values"] for v in pitch_plan["samples"]] == [v["values"] for v in pitch["samples"]]
    assert width["algorithm"]["seed"] == pitch["algorithm"]["seed"] == 13
    assert [v["cad_status"] for v in width["samples"]] == ["COMPLETED_REVIEW_REQUIRED"] * 2
    assert all(v["analysis_status"] in {"COMPLETED_REVIEW_REQUIRED", "REJECTED"}
               for v in width["samples"])
    assert [v["cad_status"] for v in pitch["samples"]] == ["COMPLETED_REVIEW_REQUIRED", "REJECTED"]
    assert pitch["samples"][0]["analysis_status"] in {"COMPLETED_REVIEW_REQUIRED", "REJECTED"}
    assert pitch["samples"][1]["analysis_status"] == "SKIPPED_CAD_REJECTED"
    assert pitch["samples"][1]["analysis_experiment_id"] is None
    assert not (store / "experiments/E-C-pitch-002-solve").exists()
    assert "cad_source_relation" in {v["type"] for v in pitch["samples"][1]["failures"]}
    revisions = set()
    verified = []
    numerical_rejections = []
    for campaign in (width, pitch):
        assert campaign["decision"] == "NOT_RELEASED"
        for row in campaign["samples"]:
            cad = lab.inspect_experiment(row["cad_experiment_id"])
            assert cad["campaign_id"] == campaign["campaign_id"]
            if row["analysis_experiment_id"] is None:
                assert cad["status"] == "REJECTED"
                continue
            solve = lab.inspect_experiment(row["analysis_experiment_id"])
            assert solve["cad_revision"] == cad["cad_revision"]
            assert solve["parent_experiment_id"] == cad["experiment_id"]
            assert solve["campaign_id"] == campaign["campaign_id"]
            assert solve["solver_status"] == "COMPLETED" and solve["converged"] is True
            assert solve["metrics"]["reaction_force"]["valid"] is True
            assert solve["metrics"]["peak_stress"]["valid"] is False
            if solve["status"] == "REJECTED":
                failures = {v["type"] for v in solve["validations"] if v["status"] == "FAIL"}
                assert failures == {"displacement_mesh_trend"}, failures
                assert solve["metrics"]["max_displacement"]["valid"] is False
                assert solve["metrics"]["displacement_mesh_change_ratio"]["value"] > .05
                numerical_rejections.append(solve["experiment_id"])
            else:
                assert solve["status"] == "COMPLETED_REVIEW_REQUIRED"
                assert solve["metrics"]["max_displacement"]["valid"] is True
                assert solve["metrics"]["displacement_mesh_change_ratio"]["value"] <= .05
            assert solve["decision"] == "NOT_RELEASED"
            assert solve["provenance"]["core_dirty"] is False
            a = store / "experiments" / cad["experiment_id"] / "cad/assembly.step"
            b = store / "experiments" / solve["experiment_id"] / "simulation/input.step"
            assert hashlib.sha256(a.read_bytes()).hexdigest() == hashlib.sha256(b.read_bytes()).hexdigest()
            revisions.add(cad["cad_revision"])
            verified.append({"campaign": campaign["campaign_id"], "values": row["values"],
                             "cad_revision": cad["cad_revision"],
                             "analysis_status": solve["status"],
                             "displacement_mm": solve["metrics"]["max_displacement"]["value"],
                             "displacement_valid": solve["metrics"]["max_displacement"]["valid"],
                             "mesh_change_ratio": solve["metrics"]["displacement_mesh_change_ratio"]["value"],
                             "reaction_balance_ratio": solve["metrics"]["reaction_balance_ratio"]["value"]})
    assert len(revisions) >= 3
    assert len(verified) == 3
    report = {"status": "PASS", "solver_runs": len(verified),
              "numerical_rejections": numerical_rejections,
              "rejected_before_solver": pitch["samples"][1]["cad_experiment_id"],
              "algorithm": width["algorithm"], "samples": verified,
              "decision": "NOT_RELEASED"}
    (store / "doe_acceptance.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--store", type=Path, required=True)
    run(parser.parse_args().store.resolve())
