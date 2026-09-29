"""Preflight tests use real CadQuery STEP, never synthetic solver success."""

import json
from pathlib import Path

import pytest

from caelab.adapters.fixture_cadquery import FixtureCadQueryAdapter
from caelab.adapters.fixture_calculix import (FixtureCalculiXAdapter, UPSTREAM,
                                              _base_reactions, _finite_displacement_table,
                                              _request_base_reactions, _apply_saddle_forces)
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


def test_fixed_reaction_table_checks_signed_balance_and_completeness(tmp_path):
    dat = tmp_path / "solver.dat"
    dat.write_text("displacements (vx,vy,vz) for set ROLLER_NODES\n"
                   "3 0 0 -0.01\n\n"
                   "forces (fx,fy,fz) for set BASE_FIXED and time  0.1000000E+01\n\n"
                   "1 1.0 0.0 30.0\n"
                   "2 -1.0 0.0 70.0\n\n")
    reaction = _base_reactions(dat, {1, 2}, 100.0)
    assert reaction["reaction_force_N"] == [0.0, 0.0, 100.0]
    assert reaction["relative_imbalance"] == 0
    original = dat.read_text()
    dat.write_text(original.replace("70.0", "-70.0"))
    assert _base_reactions(dat, {1, 2}, 100.0)["relative_imbalance"] > 1
    dat.write_text(original.replace("2 -1.0 0.0 70.0", ""))
    with pytest.raises(RuntimeError, match="Incomplete fixed-node reactions"):
        _base_reactions(dat, {1, 2}, 100.0)
    dat.write_text(original.replace("2 -1.0 0.0 70.0", "2 -1.0 NaN 70.0"))
    with pytest.raises(RuntimeError, match="Nonfinite fixed-node reaction"):
        _base_reactions(dat, {1, 2}, 100.0)


def test_reaction_request_preserves_the_existing_step(tmp_path):
    deck = tmp_path / "support.inp"
    deck.write_text("*STEP\n*STATIC\n*NODE PRINT, NSET=ROLLER_NODES\nU\n*END STEP\n")
    _request_base_reactions(deck)
    assert deck.read_text().endswith("*NODE PRINT, NSET=ROLLER_NODES\nU\n"
                                     "*NODE PRINT, NSET=BASE_FIXED\nRF\n*END STEP\n")


def test_area_load_replaces_only_saddle_set_and_forces(tmp_path):
    deck = tmp_path / "support.inp"
    deck.write_text("*NSET, NSET=BASE_FIXED\n10\n"
                    "*NSET, NSET=ROLLER_NODES\n1, 2\n"
                    "*MATERIAL, NAME=PRINT_INPUT\n*ELASTIC\n100, 0.3\n"
                    "*STEP\n*STATIC\n*BOUNDARY\nBASE_FIXED, 1, 3\n"
                    "*CLOAD\n1, 3, -50\n2, 3, -50\n"
                    "*NODE PRINT, NSET=ROLLER_NODES\nU\n*END STEP\n")
    _apply_saddle_forces(deck, {1: -20.0, 2: -30.0, 3: -50.0}, 2)
    text = deck.read_text()
    assert "*NSET, NSET=BASE_FIXED\n10\n" in text
    assert "*NSET, NSET=ROLLER_NODES\n1, 2, 3\n" in text
    assert "*CLOAD\n1, 3, -20\n2, 3, -30\n3, 3, -50\n" in text
    assert "*MATERIAL, NAME=PRINT_INPUT\n*ELASTIC\n100, 0.3\n" in text
    deck.write_text(text.replace("*CLOAD\n", "*DLOAD\n"))
    with pytest.raises(RuntimeError, match="Unexpected solver deck structure"):
        _apply_saddle_forces(deck, {1: -100.0}, 2)
