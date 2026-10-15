"""Retained BRep fallback contracts; native kernel acceptance is recorded separately."""
import json
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre import mesh_binding as binding
from test_pre_mesh_binding import NativeMeshObject


@pytest.fixture
def mesh():
    return NativeMeshObject(NS(Name='Draft', Restoring=False, Importing=False))


def test_serialization_change_requires_original_and_preserves_record(mesh, monkeypatch):
    observer = binding.MeshBindingObserver(mesh.Document)
    original = observer.track(mesh)
    stamp = getattr(mesh, binding.PROPERTY_NAME)
    assert original['schema_version'] == 3
    assert original['source']['brep'] == 'native BRep initial'
    mesh.Shape.Shape.brep = 'different serialization of the same native shape'
    calls = []
    def prove(brep, current):
        calls.append((brep, current))
        return {'status': 'PASS'}
    monkeypatch.setattr(binding, '_same_source_geometry', prove)
    result = observer.track(mesh)
    assert calls == [('native BRep initial', mesh.Shape.Shape)]
    assert result['source_equivalence']['status'] == 'PASS'
    assert result['source'] == original['source']
    assert result['qualification'] == 'UNKNOWN'
    assert getattr(mesh, binding.PROPERTY_NAME) == stamp


@pytest.mark.parametrize('change', ['name', 'type', 'placement', 'mesh'])
def test_geometry_equivalence_does_not_admit_other_identity_changes(mesh, monkeypatch, change):
    observer = binding.MeshBindingObserver(mesh.Document)
    observer.track(mesh)
    stamp = getattr(mesh, binding.PROPERTY_NAME)
    monkeypatch.setattr(binding, '_same_source_geometry', lambda *args: {'status': 'PASS'})
    mesh.Shape.Shape.brep = 'same geometry serialization'
    if change == 'name': mesh.Shape.Name = 'Other'
    elif change == 'type': mesh.Shape.TypeId = 'Part::Other'
    elif change == 'placement': mesh.Shape.placement.Base.x = 1e-14
    else: mesh.FemMesh.connectivity[7].reverse()
    with pytest.raises(ValueError):
        observer.validate(mesh)
    assert getattr(mesh, binding.PROPERTY_NAME) == stamp


def test_legacy_exact_hash_works_but_changed_serialization_cannot_be_migrated(mesh, monkeypatch):
    observer = binding.MeshBindingObserver(mesh.Document)
    record = observer.track(mesh)
    record.pop('binding_validation')
    record['schema_version'] = 2
    record['source'].pop('brep')
    stamp = json.dumps(record)
    setattr(mesh, binding.PROPERTY_NAME, stamp)
    assert observer.track(mesh)['schema_version'] == 2
    mesh.Shape.Shape.brep = 'other serialization'
    def forbidden(*args):
        pytest.fail('Legacy record has no original geometry evidence')
    monkeypatch.setattr(binding, '_same_source_geometry', forbidden)
    with pytest.raises(ValueError, match='no original BRep'):
        observer.track(mesh)
    observer.slotChangedObject(mesh, 'FemMesh')
    assert getattr(mesh, binding.PROPERTY_NAME) == stamp


def test_retained_brep_cannot_disagree_with_its_digest(mesh):
    observer = binding.MeshBindingObserver(mesh.Document)
    value = observer.track(mesh)
    value.pop('binding_validation')
    value['source']['brep'] += ' altered'
    stamp = json.dumps(value)
    setattr(mesh, binding.PROPERTY_NAME, stamp)
    mesh.replace_mesh(x=2)
    observer.slotChangedObject(mesh, 'FemMesh')
    assert observer.last_error
    assert getattr(mesh, binding.PROPERTY_NAME) == stamp
    with pytest.raises(ValueError, match='Malformed'):
        observer.validate(mesh)


@pytest.mark.parametrize('change', ['same', 'face_order', 'face_orientation', 'edge_order', 'vertex_order'])
def test_global_equivalence_does_not_allow_subelement_remapping(monkeypatch, change):
    import sys
    from caelab.adapters import freecad_face_catalog_worker as worker
    class Piece:
        Orientation = 'Forward'
        Area = Length = 1.0
        def __init__(self, key): self.key = key
        def common(self, other):
            return NS(isNull=lambda: self.key != other.key, isValid=lambda: True,
                      Area=1.0, Length=1.0)
    def shape():
        return NS(Faces=[Piece(1), Piece(2)], Edges=[Piece(1), Piece(2)],
                  Vertexes=[NS(Point=(0, 0, 0)), NS(Point=(1, 0, 0))])
    reference, current = shape(), shape()
    reference.importBrepFromString = lambda raw: None
    current.copy = lambda: current
    monkeypatch.setitem(sys.modules, 'Part', NS(Shape=lambda: reference))
    monkeypatch.setattr(worker, '_verify_geometry', lambda *args: {'status': 'PASS'})
    if change == 'face_order': current.Faces.reverse()
    elif change == 'face_orientation': current.Faces[0].Orientation = 'Reversed'
    elif change == 'edge_order': current.Edges.reverse()
    elif change == 'vertex_order': current.Vertexes.reverse()
    if change == 'same':
        proof = binding._same_source_geometry('retained original', current)
        assert proof['status'] == 'PASS'
        assert proof['subelement_correspondence'] == 'SAME_FACE_EDGE_VERTEX_ORDER_AND_ORIENTATION'
        return
    with pytest.raises(ValueError):
        binding._same_source_geometry('retained original', current)
