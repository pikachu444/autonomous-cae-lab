"""Portable routing/format doubles; no FreeCAD or CalculiX solver is executed."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from test_pre_frozen_analysis import native  # Native API double, not a native run.
from apps.desktop_pre.freeze_analysis import _freeze_legacy_analysis as freeze_analysis
from caelab.adapters import frozen_fem as adapter
from caelab.execution_control import ExecutionCancelled


@pytest.fixture
def snapshot(native, tmp_path):
    return freeze_analysis(native.analysis, native.solver, tmp_path / "snapshots")


def repin(snapshot, relative):
    manifest = json.loads(snapshot.read_text())
    data = (snapshot.parent / relative).read_bytes()
    row = next(r for r in manifest["files"] if r["relative"] == relative)
    row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    snapshot.write_text(json.dumps(manifest))


def frd_text(mesh, increments=(1,)):
    """Source-derived fixed columns from CalculiX 2.21 frd.c/frdheader.c."""
    nodes, elements, _, _ = adapter._mesh(mesh)
    lines = ["    1C", "    1UPGM               CalculiX", "    1UVERSION           Version 2.21",
             f"    2C{len(nodes):30d}{1:38d}"]
    def record(n, vector):
        return " -1" + f"{n:10d}" + "".join(f"{v:12.5E}" for v in vector)
    lines.extend(record(n, xyz) for n, xyz in nodes.items())
    lines.extend([" -3", f"    3C{len(elements):30d}{1:38d}"])
    for e, ids in elements.items():
        lines.extend([" -1" + f"{e:10d}{6:5d}{0:5d}{1:5d}", " -2" + "".join(f"{n:10d}" for n in ids)])
    lines.append(" -3")
    # Component definitions are independent source-derived expectations,
    # so changes in the production label table cannot silently change the test.
    native_labels = {
        "DISP": ("D1 1 2 1 0", "D2 1 2 2 0", "D3 1 2 3 0", "ALL 1 2 0 0 1ALL"),
        "STRESS": ("SXX 1 4 1 1", "SYY 1 4 2 2", "SZZ 1 4 3 3", "SXY 1 4 1 2", "SYZ 1 4 2 3", "SZX 1 4 3 1"),
        "TOSTRAIN": ("EXX 1 4 1 1", "EYY 1 4 2 2", "EZZ 1 4 3 3", "EXY 1 4 1 2", "EYZ 1 4 2 3", "EZX 1 4 3 1"),
        "ERROR": ("STR(%) 1 1 0 0",),
    }
    count = 0
    for inc in increments:
        for name in ("DISP", "STRESS", "TOSTRAIN", "ERROR"):
            count += 1
            lines.append("    1PSTEP" + " " * 14 + f"{count:12d}{inc:12d}{1:12d}" + " " * 10)
            lines.append("  100CL" + f"{100+inc:5d}{float(inc):12.9f}{len(nodes):12d}" + " " * 21 + "0" + f"{inc:5d}" + " " * 11 + "1")
            labels = native_labels[name]
            lines.append(f" -4  {name:<12}{len(labels):1d}    1")
            lines.extend(" -5  " + label for label in labels)
            for n in nodes:
                if name == "DISP": values = [0., -.1 * inc if n == 4 else 0., .2 * inc if n == 4 else 0.]
                elif name in {"STRESS", "TOSTRAIN"}: values = [float(i) for i in range(6)]
                else: values = [0.]
                lines.append(record(n, values))
            lines.append(" -3")
    lines.append(" 9999")
    return "\n".join(lines) + "\n"


def test_retained_native_snapshot_admission(snapshot):
    manifest, mesh, pins, gates = adapter.validate_snapshot(snapshot)
    assert manifest["mesh"]["name"] == "ExistingMesh"
    assert set(pins) == {"snapshot.json", "editable.FCStd", "mesh.json", "ExistingMesh.inp"}
    assert gates["rigid_body_constraint_rank"] == 6
    assert gates["minimum_sampled_jacobian_mm3"] > 0
    assert len(mesh["nodes"]) == 10


@pytest.mark.parametrize("change", [
    ("*NODE,NSET=Nall", "*NODE,NSET=Nall,SYSTEM=C"),
    ("*ELEMENT,TYPE=C3D10,ELSET=Evolumes", "*ELEMENT,TYPE=C3D10,ELSET=Evolumes,OFFSET=10"),
    ("*BOUNDARY", "*BOUNDARY,AMPLITUDE=foreign"),
    ("*CLOAD", "*CLOAD,OP=NEW"),
    ("*STATIC", "*STATIC,NLGEOM"),
    ("*SOLID SECTION,ELSET=MaterialSolid,MATERIAL=UserMaterial", "*SOLID SECTION,ELSET=MaterialSolid,MATERIAL=Foreign"),
    ("*ELASTIC", "*ELASTIC,TYPE=ORTHO"),
    ("*NODE FILE", "*NODE FILE,NSET=UserFixed"),
    ("*OUTPUT,FREQUENCY=1", "*OUTPUT,FREQUENCY=1,FIELD"),
    ("*END STEP", "*TEMPERATURE\n1,300\n*END STEP"),
])
def test_repinning_does_not_admit_arbitrary_deck_capabilities(snapshot, change):
    path = snapshot.parent / "ExistingMesh.inp"
    path.write_text(path.read_text().replace(*change))
    repin(snapshot, path.name)
    with pytest.raises(ValueError):
        adapter.validate_snapshot(snapshot)


@pytest.mark.parametrize("changed", ["native_order", "native_coordinate", "unused_node", "unsupported_units"])
def test_mesh_admission_binds_actual_order_coordinates_units(snapshot, changed):
    path = snapshot.parent / "mesh.json"
    mesh = json.loads(path.read_text())
    if changed == "native_order": mesh["elements"][0]["native_node_ids"][0:2] = [2, 1]
    elif changed == "native_coordinate": mesh["nodes"][0]["native_position_mm"][0] += 1
    elif changed == "unused_node": mesh["nodes"].append({"node_id":99, "position_mm":[0,0,0], "native_position_mm":[0,0,0]})
    else: mesh["units"]["position"] = "m"
    path.write_text(json.dumps(mesh)); repin(snapshot, path.name)
    with pytest.raises(ValueError): adapter.validate_snapshot(snapshot)


def test_reader_checks_actual_native_ancillary_records_and_final_increment(snapshot, tmp_path):
    _, mesh, _, _ = adapter.validate_snapshot(snapshot)
    nodes, elements, _, _ = adapter._mesh(mesh)
    frd = tmp_path / "observed.frd"
    frd.write_text(frd_text(mesh, (1, 2)))
    observed = adapter.read_frd(frd, nodes, elements)
    assert observed["displacements"][4] == [0., -.2, .4]
    assert observed["static"] == {"step":1, "increment":2, "load_parameter":2.}
    assert observed["final_fields"] == ["DISP", "ERROR", "STRESS", "TOSTRAIN"]
    assert observed["field_count"] == 8
    # CRLF and insignificant trailing whitespace do not alter native meaning.
    frd.write_bytes(frd_text(mesh).replace("\n", "  \r\n").encode("ascii"))
    assert adapter.read_frd(frd, nodes, elements)["static"]["increment"] == 1


@pytest.mark.parametrize("changed", ["partial", "duplicate", "reordered", "wrong_component", "truncated", "foreign_step", "foreign_time", "binary"])
def test_reader_refuses_unassociated_or_incomplete_native_observations(snapshot, tmp_path, changed):
    _, mesh, _, _ = adapter.validate_snapshot(snapshot)
    nodes, elements, _, _ = adapter._mesh(mesh)
    text = frd_text(mesh)
    start = text.index(" -4  DISP")
    if changed in {"partial", "duplicate"}:
        pos = text.index(" -1         4", start); end = text.index("\n", pos) + 1
        text = text[:pos] + ("" if changed == "partial" else text[pos:end] * 2) + text[end:]
    elif changed == "reordered": text = text.replace(" -2         2         1", " -2         1         2", 1)
    elif changed == "wrong_component": text = text.replace(" -5  EZX 1 4 3 1", " -5  EZX 1 4 1 3")
    elif changed == "truncated": text = text.replace(" 9999\n", "")
    elif changed == "foreign_step": text = text.replace(f"{1:12d}{1:12d}{1:12d}", f"{1:12d}{1:12d}{2:12d}", 1)
    elif changed == "foreign_time": text = text.replace(" 1.000000000", " 2.000000000", 1)
    else: text = text.replace(" 9999", "\x00 9999")
    path = tmp_path / "bad.frd"; path.write_text(text)
    with pytest.raises(ValueError): adapter.read_frd(path, nodes, elements)


@pytest.fixture
def executable(monkeypatch, tmp_path):
    binary = tmp_path / "ccx-portable-double"
    binary.write_bytes(b"TEST_ONLY_NOT_EXECUTABLE")
    monkeypatch.setattr(adapter.shutil, "which", lambda name: str(binary))
    return binary


def test_adapter_retains_exact_deck_and_exports_actual_node_field(snapshot, tmp_path, monkeypatch, executable):
    original = {p.name:p.read_bytes() for p in snapshot.parent.iterdir()}
    def command(args, cwd, label):
        # This collaborator double produces portable records; never starts ccx.
        assert args == [str(executable), "-i", "ExistingMesh"]
        assert (cwd / "ExistingMesh.inp").read_bytes() == original["ExistingMesh.inp"]
        mesh = json.loads(original["mesh.json"])
        (cwd / "ExistingMesh.frd").write_text(frd_text(mesh))
        (cwd / "ExistingMesh.dat").write_text("TEST_ONLY native reaction totals retained")
        (cwd / (label + ".stdout.log")).write_text("TEST_ONLY portable double")
        return NS(returncode=0)
    monkeypatch.setattr(adapter, "run_owned_command", command)
    output = tmp_path / "run"
    result = adapter.FrozenFemAdapter().run({"snapshot_path":str(snapshot), "data_id":"Dsample"}, output=output)
    assert result["execution_status"] == "SUCCEEDED", result
    assert result["engineering_valid"] is False and result["qualification"] == "UNKNOWN"
    assert result["responses"]["displacement"]["value"][3] == [0, -.1, .2]
    assert result["responses"]["UY"]["unit"] == "mm"
    assert result["responses"]["displacement"]["metadata"]["node_ids"] == list(range(1, 11))
    assert result["post_artifact"]["relative"] == "post/displacement.vtu"
    for name, data in original.items(): assert (output / "frozen_input" / name).read_bytes() == data
    assert (output / "solver/ExistingMesh.inp").read_bytes() == original["ExistingMesh.inp"]
    assert (output / "post/displacement.vtu").is_file()
    assert json.loads((output / "frozen_execution.json").read_text())["execution_status"] == "SUCCEEDED"


@pytest.mark.parametrize("failure", ["failed", "cancelled", "source_race", "bad_frd"])
def test_failed_cancelled_raced_outputs_remain_and_never_publish_responses(snapshot, tmp_path, monkeypatch, executable, failure):
    before = (snapshot.parent / "editable.FCStd").read_bytes()
    def command(args, cwd, label):
        (cwd / "partial.raw").write_bytes(b"TEST_ONLY partial raw output")
        if failure == "cancelled": raise ExecutionCancelled("TEST_ONLY requested cancellation")
        if failure == "source_race": (snapshot.parent / "editable.FCStd").write_bytes(b"changed source")
        if failure == "bad_frd": (cwd / "ExistingMesh.frd").write_bytes(b"partial")
        return NS(returncode=1 if failure == "failed" else 0)
    monkeypatch.setattr(adapter, "run_owned_command", command)
    output = tmp_path / "run"
    result = adapter.FrozenFemAdapter().run({"snapshot_path":str(snapshot)}, output=output)
    assert result["execution_status"] == ("CANCELLED" if failure == "cancelled" else "FAILED")
    assert result["responses"] == {}
    assert (output / "solver/partial.raw").is_file()
    assert (output / "frozen_input/editable.FCStd").read_bytes() == before
    assert (output / "frozen_execution.json").is_file()


def test_missing_runtime_retains_admitted_snapshot_with_failure(snapshot, tmp_path, monkeypatch):
    monkeypatch.setattr(adapter.shutil, "which", lambda name: None)
    output = tmp_path / "run"
    result = adapter.FrozenFemAdapter().run({"snapshot_path":str(snapshot)}, output=output)
    assert result["execution_status"] == "FAILED"
    assert result["checks"][0]["status"] == "PASS"
    assert (output / "frozen_input/snapshot.json").is_file()


@pytest.mark.parametrize("scale,admitted", [(1e-5, False), (1., True), (1e5, True)])
def test_sampled_geometry_keeps_absolute_floor_and_scaled_guard(snapshot, scale, admitted):
    _, mesh, _, _ = adapter.validate_snapshot(snapshot)
    nodes, elements, fixed, _ = adapter._mesh(mesh)
    scaled = {n:tuple(scale * v for v in xyz) for n, xyz in nodes.items()}
    if not admitted:
        # det=1e-15 mm^3 is regular after normalization, but below the original floor.
        with pytest.raises(ValueError, match='1e-10 mm'):
            adapter._gates(scaled, elements, fixed)
        return
    gates = adapter._gates(scaled, elements, fixed)
    assert gates["rigid_body_constraint_rank"] == 6
    assert gates["minimum_sampled_jacobian_mm3"] > 1e-10
    assert gates["minimum_scaled_sampled_jacobian"] == pytest.approx(1.)


def test_normalized_singularity_guard_remains_additional_to_absolute_floor(snapshot):
    _, mesh, _, _ = adapter.validate_snapshot(snapshot)
    nodes, elements, fixed, _ = adapter._mesh(mesh)
    # det=1e6 mm^3 exceeds the absolute floor, but normalized det=1e-15 is singular.
    stretched = {n: (xyz[0] * 1e7, xyz[1] * 1e7, xyz[2] * 1e-8)
                 for n, xyz in nodes.items()}
    with pytest.raises(ValueError, match='numerically singular'):
        adapter._gates(stretched, elements, fixed)
