"""Native-shaped portable doubles, not evidence of a live FreeCAD mesh run."""
import copy
import json
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre.mesh_binding import (
    INITIAL, PROPERTY_ATTRIBUTES, PROPERTY_NAME, REPLACED, MeshBindingObserver,
)


class NativeMeshObject:
    def __init__(self, document):
        self.Document = document
        self.Name = "GmshMesh"
        self.PropertiesList = []
        self.property_info = {}
        self.Shape = NS(Name="Solid", TypeId="Part::Feature", Document=document)
        self.Shape.Shape = NS(brep="native BRep initial")
        self.Shape.Shape.exportBrepToString = lambda: self.Shape.Shape.brep
        self.replace_mesh()

    def replace_mesh(self, x=1):
        self.FemMesh = NS(
            Nodes={1: NS(x=0, y=0, z=0), 2: NS(x=x, y=0, z=0),
                   3: NS(x=0, y=1, z=0), 4: NS(x=0, y=0, z=1)},
            Volumes=[7], Faces=[8], Edges=[9],
            connectivity={7: [1, 2, 3, 4], 8: [1, 2, 3], 9: [1, 2]},
        )
        self.FemMesh.getElementNodes = lambda identifier: self.FemMesh.connectivity[identifier]

    def addProperty(self, kind, name, group, description, *, attr, locked):
        assert attr == 25 == PROPERTY_ATTRIBUTES and locked
        self.PropertiesList.append(name)
        self.property_info[name] = [kind, ["ReadOnly", "Output", "NoRecompute"]]

    def getTypeIdOfProperty(self, name):
        return self.property_info[name][0]

    def getTypeOfProperty(self, name):
        return self.property_info[name][1]


@pytest.fixture
def mesh():
    # No recompute, save or solver APIs are provided by this double.
    return NativeMeshObject(NS(Name="Draft", Restoring=False, Importing=False))


def test_first_loaded_unknown_mesh_is_explicitly_unverified_without_native_action(mesh):
    observer = MeshBindingObserver(mesh.Document)
    record = observer.track(mesh)
    assert record["status"] == INITIAL
    assert record["qualification"] == "UNKNOWN"
    assert record["binding_validation"] == "CURRENT_SOURCE_AND_MESH_MATCH"
    assert record["source"]["name"] == "Solid"
    assert record["mesh"]["name"] == "GmshMesh"
    assert len(record["source"]["brep_sha256"]) == 64
    assert len(record["mesh"]["ordered_mesh_sha256"]) == 64
    assert observer.track(mesh) == observer.validate(mesh) == record


def test_validate_does_not_initialize_unknown_mesh(mesh):
    with pytest.raises(ValueError, match="track the loaded mesh first"):
        MeshBindingObserver(mesh.Document).validate(mesh)
    assert mesh.PropertiesList == []


def test_cad_change_and_recompute_notification_leave_old_mesh_blocked(mesh):
    observer = MeshBindingObserver(mesh.Document)
    observer.track(mesh)
    stamp = getattr(mesh, PROPERTY_NAME)
    mesh.Shape.Shape.brep = "changed native BRep"
    observer.slotChangedObject(mesh.Shape, "Shape")
    # Even a touch/reassignment callback with identical native mesh is insufficient.
    observer.slotChangedObject(mesh, "FemMesh")
    assert getattr(mesh, PROPERTY_NAME) == stamp
    with pytest.raises(ValueError, match="Source geometry changed"):
        observer.validate(mesh)
    with pytest.raises(ValueError, match="Source geometry changed"):
        observer.track(mesh)


def test_observed_changed_mesh_content_records_current_source_without_qualification(mesh):
    observer = MeshBindingObserver(mesh.Document)
    first = observer.track(mesh)
    mesh.Shape.Shape.brep = "changed native BRep"
    mesh.replace_mesh(x=2)
    with pytest.raises(ValueError, match="Source geometry changed"):
        observer.validate(mesh)
    observer.slotChangedObject(mesh, "FemMesh")
    record = observer.validate(mesh)
    assert record["status"] == REPLACED and record["qualification"] == "UNKNOWN"
    assert record["source"] != first["source"] and record["mesh"] != first["mesh"]
    mesh.Shape.Shape.brep = "another geometry edit"
    with pytest.raises(ValueError, match="Source geometry changed"):
        observer.validate(mesh)


@pytest.mark.parametrize("change", ["coordinate", "node_order", "surface", "edge", "node_id"])
def test_unobserved_mesh_edit_is_blocked_including_order_and_ancillary_connectivity(mesh, change):
    observer = MeshBindingObserver(mesh.Document)
    observer.track(mesh)
    if change == "coordinate": mesh.FemMesh.Nodes[2].x += 1e-14
    elif change == "node_order": mesh.FemMesh.connectivity[7].reverse()
    elif change == "surface": mesh.FemMesh.connectivity[8].reverse()
    elif change == "edge": mesh.FemMesh.connectivity[9].reverse()
    else:
        mesh.FemMesh.Nodes[5] = mesh.FemMesh.Nodes.pop(4)
        mesh.FemMesh.connectivity[7][-1] = 5
    with pytest.raises(ValueError, match="without an observed replacement"):
        observer.validate(mesh)


def reopened(mesh):
    # Simulate persisted native property restore into a renamed draft copy.
    restored = NativeMeshObject(NS(Name="RetainedCopy", Restoring=True, Importing=False))
    restored.Shape.Shape.brep = mesh.Shape.Shape.brep
    restored.replace_mesh(mesh.FemMesh.Nodes[2].x)
    restored.PropertiesList = list(mesh.PropertiesList)
    restored.property_info = copy.deepcopy(mesh.property_info)
    setattr(restored, PROPERTY_NAME, getattr(mesh, PROPERTY_NAME))
    return restored


def test_save_reopen_preserves_stamp_and_changed_source_rejection(mesh):
    MeshBindingObserver(mesh.Document).track(mesh)
    valid = reopened(mesh)
    valid.Document.Restoring = False
    assert MeshBindingObserver(valid.Document).track(valid)["status"] == INITIAL
    mesh.Shape.Shape.brep = "edited CAD saved with old mesh"
    restored = reopened(mesh)
    observer = MeshBindingObserver(restored.Document)
    before = getattr(restored, PROPERTY_NAME)
    observer.slotChangedObject(restored, "FemMesh")
    restored.Document.Restoring = False
    assert getattr(restored, PROPERTY_NAME) == before
    with pytest.raises(ValueError, match="Source geometry changed"):
        observer.track(restored)


@pytest.mark.parametrize("native_state", ["Restoring", "Importing"])
def test_file_restore_or_import_cannot_count_as_native_mesh_replacement(mesh, native_state):
    MeshBindingObserver(mesh.Document).track(mesh)
    before = getattr(mesh, PROPERTY_NAME)
    mesh.Shape.Shape.brep = "edited geometry"
    mesh.replace_mesh(x=2)
    observer = MeshBindingObserver(mesh.Document)
    setattr(mesh.Document, native_state, True)
    observer.slotChangedObject(mesh, "FemMesh")
    with pytest.raises(ValueError, match="restore/import"):
        observer.track(mesh)
    assert getattr(mesh, PROPERTY_NAME) == before
    setattr(mesh.Document, native_state, False)
    with pytest.raises(ValueError, match="Source geometry changed"):
        observer.validate(mesh)


@pytest.mark.parametrize("damage", ["syntax", "empty", "duplicate", "digest", "name", "status", "qualification", "extra", "version", "transient", "property_type"])
def test_malformed_or_nonpersistent_record_is_never_reset_even_on_mesh_event(mesh, damage):
    observer = MeshBindingObserver(mesh.Document)
    observer.track(mesh)
    value = json.loads(getattr(mesh, PROPERTY_NAME))
    if damage == "syntax": raw = "{"
    elif damage == "empty": raw = ""
    elif damage == "duplicate": raw = getattr(mesh, PROPERTY_NAME)[:-1] + ',"status":"INITIAL_ASSOCIATION_UNVERIFIED"}'
    else:
        if damage == "digest": value["source"]["brep_sha256"] = "not a digest"
        elif damage == "name": value["mesh"]["name"] = "anotherMesh"
        elif damage == "status": value["status"] = "VALIDATED"
        elif damage == "qualification": value["qualification"] = "PASS"
        elif damage == "extra": value["extra"] = "value"
        elif damage == "version": value["schema_version"] = True
        elif damage == "transient": mesh.property_info[PROPERTY_NAME][1].append("Transient")
        elif damage == "property_type": mesh.property_info[PROPERTY_NAME][0] = "App::PropertyInteger"
        raw = json.dumps(value)
    setattr(mesh, PROPERTY_NAME, raw)
    mesh.replace_mesh(x=2)
    with pytest.raises(ValueError):
        observer.track(mesh)
    observer.slotChangedObject(mesh, "FemMesh")
    assert observer.last_error and getattr(mesh, PROPERTY_NAME) == raw
    with pytest.raises(ValueError):
        observer.validate(mesh)


def test_other_document_or_cross_document_source_is_rejected(mesh):
    observer = MeshBindingObserver(NS(Name="Other"))
    with pytest.raises(ValueError, match="another document"):
        observer.track(mesh)
    observer.slotChangedObject(mesh, "FemMesh")
    assert mesh.PropertiesList == []
    mesh.Shape.Document = NS(Name="External")
    with pytest.raises(ValueError, match="same document"):
        MeshBindingObserver(mesh.Document).track(mesh)


@pytest.mark.parametrize("problem", ["empty", "nonfinite", "bad_connectivity"])
def test_invalid_native_mesh_never_gets_a_new_stamp(mesh, problem):
    if problem == "empty": mesh.FemMesh.Volumes = []
    elif problem == "nonfinite": mesh.FemMesh.Nodes[1].x = float("nan")
    else: mesh.FemMesh.connectivity[7][0] = 999
    observer = MeshBindingObserver(mesh.Document)
    with pytest.raises(ValueError):
        observer.track(mesh)
    observer.slotChangedObject(mesh, "FemMesh")
    assert mesh.PropertiesList == [] and observer.last_error
