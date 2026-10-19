"""Export routing doubles only: these do not establish native FreeCAD acceptance."""
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre.freeze_analysis import _freeze_legacy_analysis as freeze_analysis, _serialized_coordinate_close


class Quantity:
    def __init__(self, value):
        self.Value = float(str(value).split()[0])

    def getValueAs(self, unit):
        return self

    def __rmul__(self, factor):
        return Quantity(factor * self.Value)


@pytest.fixture
def native(monkeypatch, tmp_path):
    source = tmp_path / "original.FCStd"
    source.write_bytes(b"original document")
    doc = NS(Name="UserDocument", FileName=str(source), Objects=[], touched=False)
    doc.isTouched = lambda: doc.touched
    copies, writes = [], []
    def save_copy(path):
        copies.append(path)
        Path(path).write_bytes(b"current editable snapshot")
    doc.saveCopy = save_copy

    def obj(name, kind, **fields):
        result = NS(Name=name, TypeId=kind, Document=doc, State=[], Suppressed=False, **fields)
        doc.Objects.append(result)
        return result

    shape = obj("UserSolid", "Part::Feature", Shape=NS(isValid=lambda: True, Solids=[1], Faces=[1, 2, 3, 4]))
    coordinates = [(1,0,0), (0,0,0), (0,1,0), (0,0,1), (.5,0,0),
                   (0,.5,0), (.5,.5,0), (.5,0,.5), (0,0,.5), (0,.5,.5)]
    points = {i: NS(x=x, y=y, z=z) for i, (x,y,z) in enumerate(coordinates, 1)}
    mesh = obj("ExistingMesh", "Fem::FemMeshObject", Shape=shape, FemMesh=NS(Nodes=points))
    settings = dict(AnalysisType="static", ModelSpace="3D", GeometricalNonlinearity="linear",
                    MaterialNonlinearity="linear", SplitInputWriter=False)
    solver = obj("UserCalculix", "Fem::SolverCcxTools", PropertiesList=list(settings), **settings)
    material = obj("UserMaterial", "Fem::MaterialCommon", Category="Solid", References=[],
                   Material={"YoungsModulus": "1000 MPa", "PoissonRatio": "0.25"})
    fixed = obj("UserFixed", "Fem::ConstraintFixed", References=[(shape, ["Face1"])])
    force = obj("UserForce", "Fem::ConstraintForce", References=[(shape, ["Face2"])],
                Force=Quantity(10), DirectionVector=NS(x=0., y=0., z=-1.), EnableAmplitude=False)
    analysis = obj("UserAnalysis", "Fem::FemAnalysis", Group=[solver, mesh, material, fixed, force])
    member = NS(mats_linear=[{"Object": material}], cons_fixed=[{"Object": fixed}], cons_force=[{"Object": force}])
    state = NS(doc=doc, source=source, shape=shape, analysis=analysis, solver=solver, mesh=mesh,
               material=material, fixed=fixed, force=force, copies=copies, writes=writes,
               error="", writer_mode="valid", edit=None, dialog=False, after_write=None)

    class Getter:
        def __init__(self, analysis, solver, selected_mesh, members):
            assert selected_mesh is mesh
            self.member = members
            self.mat_geo_sets = []

        def get_mesh_sets(self):
            self.member.cons_fixed[0]["Nodes"] = [1, 2, 3]
            self.member.cons_force[0]["NodeLoadTable"] = [("Face2", {4: Quantity(10)})]

    class Writer:
        def __init__(self, a, s, m, members, directory, mat_geo_sets):
            assert (a, s, m) == (analysis, solver, mesh)
            self.path = Path(directory) / (mesh.Name + ".inp")

        def write_solver_input(self):
            writes.append(self.path)
            if state.writer_mode == "failure":
                raise RuntimeError("native export failed")
            node_lines = [f"{i},{p.x},{p.y},{p.z}" for i, p in points.items()]
            if state.writer_mode == "different_node":
                node_lines[0] = "1,999,0,0"
            connectivity = "2,1,3,4,5,7,6,9,8,10"
            if state.writer_mode == "wrong_order":
                connectivity = "1,2,3,4,5,6,7,8,9,10"
            text = "*NODE,NSET=Nall\n" + "\n".join(node_lines) + "\n*ELEMENT,TYPE=C3D10,ELSET=Evolumes\n7," + connectivity + "\n"
            text += "*ELSET,ELSET=Eall\nEvolumes\n*ELSET,ELSET=MaterialSolid\nEall\n"
            text += "*NSET,NSET=UserFixed\n1,2,3\n"
            text += "*PHYSICAL CONSTANTS,ABSOLUTE ZERO=0,STEFAN BOLTZMANN=5.670374419e-11\n"
            text += "*MATERIAL,NAME=UserMaterial\n*ELASTIC\n1000,0.25\n*EXPANSION,ZERO=0\n0\n"
            text += "*SOLID SECTION,ELSET=MaterialSolid,MATERIAL=UserMaterial\n"
            text += "*STEP,INC=100\n*STATIC\n1,1,0.00001,1\n*BOUNDARY\nUserFixed,1\nUserFixed,2\nUserFixed,3\n*CLOAD\n4,3,-10\n"
            text += "*NODE FILE\nU\n*EL FILE\nS, E\n*NODE PRINT,NSET=UserFixed,TOTALS=ONLY\nRF\n*OUTPUT,FREQUENCY=1\n*END STEP\n"
            if state.writer_mode == "include":
                text += "*INCLUDE,INPUT=other.inp\n"
            if state.writer_mode == "stale_settings":
                solver.ModelSpace = "plane stress"
            self.path.write_text(text, encoding="utf-8")
            if state.after_write:
                state.after_write()
            return str(self.path)

    modules = {
        "FreeCAD": NS(GuiUp=True, Version=lambda: ["1", "1", "4"], Units=NS(Quantity=Quantity)),
        "FreeCADGui": NS(activeDocument=lambda: NS(getInEdit=lambda: state.edit), Control=NS(activeDialog=lambda: state.dialog)),
        "femtools": NS(femutils=NS(type_of_obj=lambda o: o.TypeId),
                       membertools=NS(get_mesh_to_solve=lambda a: (mesh, ""), AnalysisMember=lambda a: member),
                       checksanalysis=NS(check_member_for_solver_calculix=lambda *args: state.error)),
        "femmesh": NS(meshtools=NS(get_femelement_volumes_table=lambda m: {7: list(range(1, 11))})),
        "femmesh.meshsetsgetter": NS(MeshSetsGetter=Getter),
        "femsolver": NS(), "femsolver.calculix": NS(), "femsolver.calculix.writer": NS(FemInputWriterCcx=Writer),
    }
    for name, value in modules.items():
        monkeypatch.setitem(sys.modules, name, value)
    # Any accidental launch/remesh call fails; export uses neither module.
    monkeypatch.setitem(sys.modules, "femtools.ccxtools", None)
    monkeypatch.setitem(sys.modules, "femmesh.gmshtools", None)
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: pytest.fail("No external process allowed"))
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: pytest.fail("No external process allowed"))
    return state


def test_existing_native_writer_exports_new_identity_pinned_snapshot(native, tmp_path):
    original = native.source.read_bytes()
    output = tmp_path / "snapshots"
    first = freeze_analysis(native.analysis, native.solver, output)
    second = freeze_analysis(native.analysis, native.solver, output)
    assert first != second and first.parent.parent == output
    record = json.loads(first.read_text())
    assert record["kind"] == "freecad-fem-frozen" and record["solver_execution"] == "NOT_PERFORMED"
    assert record["analysis"]["name"] == "UserAnalysis" and record["mesh"]["name"] == "ExistingMesh"
    assert record["material"]["young_modulus_MPa"] == 1000
    assert record["conditions"][1]["references"] == [{"object": "UserSolid", "subelements": ["Face2"]}]
    for row in record["files"]:
        file = first.parent / row["relative"]
        assert file.stat().st_size == row["bytes"] and hashlib.sha256(file.read_bytes()).hexdigest() == row["sha256"]
    mesh = json.loads((first.parent / "mesh.json").read_text())
    assert mesh["elements"] == [{"element_id": 7, "type": "C3D10", "node_ids": [2,1,3,4,5,7,6,9,8,10], "native_node_ids": list(range(1, 11))}]
    assert len(mesh["fixed_dofs"]) == 9 and mesh["loads"] == [{"node_id": 4, "component": 3, "force_N": -10}]
    assert native.source.read_bytes() == original and native.doc.FileName == str(native.source)
    assert len(native.copies) == len(native.writes) == 2


@pytest.mark.parametrize("problem", ["stale", "edit", "dialog", "unknown", "split", "amplitude", "prerequisite", "reference"])
def test_unsupported_or_stale_input_is_rejected_before_copy_or_writer(native, tmp_path, problem):
    if problem == "stale": native.doc.touched = True
    elif problem == "edit": native.edit = object()
    elif problem == "dialog": native.dialog = True
    elif problem == "unknown": native.analysis.Group.append(NS(Name="Contact", Suppressed=False))
    elif problem == "split": native.solver.SplitInputWriter = True
    elif problem == "amplitude": native.force.EnableAmplitude = True
    elif problem == "prerequisite": native.error = "native prerequisites failed"
    else: native.force.References = [(native.shape, ["Edge1"])]
    with pytest.raises(ValueError):
        freeze_analysis(native.analysis, native.solver, tmp_path / "snapshots")
    assert native.copies == native.writes == []


@pytest.mark.parametrize("mode", ["different_node", "wrong_order", "include", "failure", "stale_settings"])
def test_failed_export_never_publishes_complete_manifest(native, tmp_path, mode):
    native.writer_mode = mode
    with pytest.raises((ValueError, RuntimeError)):
        freeze_analysis(native.analysis, native.solver, tmp_path / "snapshots")
    assert not list((tmp_path / "snapshots").glob("*/snapshot.json"))
    assert native.source.read_bytes() == b"original document" and native.doc.FileName == str(native.source)


@pytest.mark.parametrize("changed", ["force", "reference", "mesh", "group"])
def test_live_source_changes_during_writer_never_publish(native, tmp_path, changed):
    def mutate():
        if changed == "force": native.force.DirectionVector.z = 1.
        elif changed == "reference": native.fixed.References = [(native.shape, ["Face2"])]
        elif changed == "mesh": native.mesh.FemMesh.Nodes[1].x = 2.
        else: native.analysis.Group.pop()
    native.after_write = mutate
    with pytest.raises(ValueError):
        freeze_analysis(native.analysis, native.solver, tmp_path / "snapshots")
    assert not list((tmp_path / "snapshots").glob("*/snapshot.json"))
    assert list((tmp_path / "snapshots").glob("*/editable.FCStd"))


def test_export_hashing_works_without_python311_file_digest(native, tmp_path, monkeypatch):
    monkeypatch.delattr(hashlib, "file_digest", raising=False)
    assert freeze_analysis(native.analysis, native.solver, tmp_path / "snapshots").is_file()



def test_coordinate_identity_allows_native_print_precision_only():
    assert _serialized_coordinate_close(.123456789012345, .1234567890123)
    assert not _serialized_coordinate_close(1., 1. + 1e-10)
    assert not _serialized_coordinate_close(0., 1e-12)
