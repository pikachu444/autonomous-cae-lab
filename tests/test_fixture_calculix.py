"""Preflight tests use real CadQuery STEP, never synthetic solver success."""

import json
from pathlib import Path

import pytest

from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
from caelab.adapters.fixture_calculix import (FixtureCalculiXAdapter, UPSTREAM,
                                              _finite_displacement_table)
from caelab.storage import artifact_manifest


def parent(tmp_path: Path, *, roller_diameter: float = 8.3):
    root = tmp_path / "parent"
    cad = root / "cad"
    fixture = FixtureCadQueryAdapter()
    result = fixture.regenerate("roller_support",
                                {"support_width_mm": 38,
                                 "roller_diameter_mm": roller_diameter}, cad)
    assert result.generated
    revision = "a" * 64
    return root, {"experiment_id": "E-parent", "status": "COMPLETED_REVIEW_REQUIRED",
                  "decision": "NOT_RELEASED", "cad_revision": revision,
                  "provenance": {"adapter": "fixture.cadquery"},
                  "artifacts": artifact_manifest(root, revision=revision)}


def settings():
    material = json.loads((UPSTREAM / "examples/printed_material_ASSUMED.json").read_text())
    return {"load": {"force_per_support_N": 100.0, "source": "test load: unqualified"},
            "material": material, "mesh": {"max_sizes_mm": [4, 3, 2]}}


def test_verified_step_preflight_reaches_executable_gate(tmp_path, monkeypatch):
    root, result = parent(tmp_path)
    monkeypatch.setattr("caelab.adapters.fixture_calculix.shutil.which", lambda _: None)
    out = tmp_path / "analysis"
    with pytest.raises(RuntimeError, match="Missing open-source executable: gmsh"):
        FixtureCalculiXAdapter().solve(result, root, out, settings())
    assert not (out / "input.step").exists()


def test_tampered_parent_step_rejected_before_meshing(tmp_path):
    root, result = parent(tmp_path)
    with (root / "cad/assembly.step").open("ab") as stream:
        stream.write(b"\nmodified")
    out = tmp_path / "analysis"
    response = FixtureCalculiXAdapter().solve(result, root, out, settings())
    assert response["status"] == "REJECTED"
    assert response["checks"][-1]["code"] == "cad_artifact_integrity"
    assert response["solver_status"] == "NOT_RUN"
    assert list(out.iterdir()) == [out / "result.json"]


def test_unsupported_saddle_and_load_are_rejected(tmp_path):
    root, result = parent(tmp_path, roller_diameter=9.0)
    out = tmp_path / "analysis"
    rejected = FixtureCalculiXAdapter().solve(result, root, out, settings())
    assert rejected["status"] == "REJECTED"
    assert rejected["checks"][-1]["code"] == "saddle_boundary_compatibility"
    assert not (out / "input.step").exists()

    root2, result2 = parent(tmp_path / "second")
    invalid = settings()
    invalid["load"]["force_per_support_N"] = 0
    rejected = FixtureCalculiXAdapter().solve(result2, root2, tmp_path / "invalid", invalid)
    assert rejected["checks"][-1]["code"] == "load_definition"


def test_displacement_table_rejects_nonfinite_nonextreme_node(tmp_path):
    dat = tmp_path / "solver.dat"
    dat.write_text("displacements (vx,vy,vz)\n"
                   "1 0.0 0.0 -1.0\n"
                   "2 0.0 NaN -0.5\n"
                   "3 0.0 0.0 -1.1\n")
    with pytest.raises(RuntimeError, match="Nonfinite loaded-node displacement: 2"):
        _finite_displacement_table(dat, {1, 2, 3})
    dat.write_text("displacements (vx,vy,vz)\n"
                   "1 0.0 0.0 -1.0\n"
                   "2 0.0 0.0 -0.5\n"
                   "3 0.0 0.0 -1.1\n")
    _finite_displacement_table(dat, {1, 2, 3})
