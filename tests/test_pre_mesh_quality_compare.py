"""Read-only comparison uses real existing quality code, without native runs."""
from copy import copy, deepcopy

import pytest

from apps.desktop_pre.fem_edit import _mesh_hash
from apps.desktop_pre.mesh_quality_compare import compare_mesh_quality
from test_pre_fem_edit import native, Mesh, Object


def preserved(native, previous=None, current=None):
    archive = Object(native.doc, 'Previous', 'Fem::FemMeshObject', FemMesh=previous or Mesh())
    native.mesh.FemMesh = current or Mesh(2)
    record = {'id': 'history-one', 'mesh_id': native.mesh.Name, 'state': 'SUCCEEDED',
              'previous_mesh_object_id': archive.Name,
              'previous_mesh_sha256': _mesh_hash(archive.FemMesh),
              # This older generation's successor need not be the current mesh.
              'mesh_sha256': _mesh_hash(Mesh(3))}
    native.metadata['mesh_history'] = [record]
    return archive, record


def compare(native, expected=None):
    return compare_mesh_quality(native.editor, native.mesh, 'history-one',
                                expected or _mesh_hash(native.mesh.FemMesh))


def test_older_archive_and_current_use_same_quality_without_writes_or_false_bin_deltas(native):
    archive, _ = preserved(native)
    archive.ViewObject.Visibility = False
    native.mesh.ViewObject.Visibility = True
    native.mesh.ViewObject.ShowInner = True
    native.mesh.ViewObject.HighlightedNodes = [2, 7]
    views = deepcopy(vars(archive.ViewObject)), deepcopy(vars(native.mesh.ViewObject))
    before = deepcopy(native.metadata), _mesh_hash(archive.FemMesh), _mesh_hash(native.mesh.FemMesh)
    result = compare(native)
    for name, obj in [('previous', archive), ('current', native.mesh)]:
        quality = native.editor.quality(obj, limit=1)
        assert result[name] == {key: quality[key] for key in result[name]}
    delta = result['changes']
    assert delta['total_elements'] == delta['bad_element_count'] == 0
    absolute = delta['absolute_jacobian_mm3']
    assert absolute['minimum'] == pytest.approx(7)
    assert absolute['bin_boundaries_equal'] is False and absolute['bins'] is None
    assert result['previous']['absolute_jacobian_mm3']['bins'] != result['current']['absolute_jacobian_mm3']['bins']
    assert delta['normalized_jacobian']['minimum'] == pytest.approx(0)
    assert result['element_correspondence'] == 'NOT_ASSUMED_AFTER_REMESH'
    assert 'rows' not in result['previous'] and 'rows' not in result['current']
    assert before == (native.metadata, _mesh_hash(archive.FemMesh), _mesh_hash(native.mesh.FemMesh))
    assert views == (vars(archive.ViewObject), vars(native.mesh.ViewObject))
    assert native.transactions == [] and native.tools == []


@pytest.mark.parametrize('old_bad,new_bad,change', [(False, True, 1), (True, False, -1), (False, False, 0)])
def test_worse_improved_and_unchanged_counts_are_preserved(native, old_bad, new_bad, change):
    preserved(native, Mesh(invalid=old_bad), Mesh(invalid=new_bad))
    result = compare(native)
    assert result['previous']['bad_element_count'] == int(old_bad)
    assert result['current']['bad_element_count'] == int(new_bad)
    assert result['changes']['bad_element_count'] == change
    if change == 0:
        assert result['changes']['absolute_jacobian_mm3']['bins'][0]['count'] == 0
    assert 'verdict' not in result and 'run_admissibility' not in result


def test_no_element_pairing_even_with_sparse_different_ids_and_different_totals(native):
    previous = Mesh()
    current = Mesh()
    current.elements[107] = current.elements.pop(73)
    current.elements[990] = list(current.elements[107])
    current.Volumes = [107, 990]
    preserved(native, previous, current)
    result = compare(native)
    assert result['previous']['total_elements'] == 1
    assert result['current']['total_elements'] == 2
    assert result['changes']['total_elements'] == 1
    assert result['changes']['absolute_jacobian_mm3']['bins'][0]['count'] == 1


def test_empty_predecessor_keeps_unknown_extrema_and_actual_count_change(native):
    empty = Mesh()
    empty.Nodes, empty.Volumes, empty.Faces, empty.Edges = {}, [], [], []
    preserved(native, empty, Mesh())
    result = compare(native)
    assert result['previous']['total_elements'] == 0
    assert result['changes']['total_elements'] == 1
    assert result['previous']['absolute_jacobian_mm3']['minimum'] is None
    assert result['changes']['absolute_jacobian_mm3']['minimum'] is None
    assert result['changes']['absolute_jacobian_mm3']['bins'] is None


@pytest.mark.parametrize('damage', ['expected', 'history_mesh', 'state', 'duplicate',
                                   'archive_hash', 'archive_type', 'archive_document', 'missing_archive'])
def test_wrong_stale_or_missing_sources_are_rejected_and_preserved(native, damage):
    archive, record = preserved(native)
    expected = _mesh_hash(native.mesh.FemMesh)
    if damage == 'expected': expected = _mesh_hash(Mesh(4))
    elif damage == 'history_mesh': record['mesh_id'] = 'AnotherMesh'
    elif damage == 'state': record['state'] = 'FAILED'
    elif damage == 'duplicate': native.metadata['mesh_history'].append(deepcopy(record))
    elif damage == 'archive_hash': archive.FemMesh = Mesh(5)
    elif damage == 'archive_type': archive.TypeId = 'Fem::FemMeshGmsh'
    elif damage == 'archive_document': archive.Document = object()
    elif damage == 'missing_archive': native.doc.Objects.remove(archive)
    saved = deepcopy(native.metadata), _mesh_hash(native.mesh.FemMesh), _mesh_hash(archive.FemMesh)
    with pytest.raises(ValueError): compare(native, expected)
    assert saved == (native.metadata, _mesh_hash(native.mesh.FemMesh), _mesh_hash(archive.FemMesh))
    assert native.transactions == [] and native.tools == []


def test_replaced_current_mesh_is_rejected_by_identity(native):
    preserved(native)
    old = native.mesh
    replacement = copy(old)
    native.doc.Objects[native.doc.Objects.index(old)] = replacement
    with pytest.raises(ValueError, match='바뀌었습니다'):
        compare(native)


@pytest.mark.parametrize('binding_case', ['match', 'changed_shape', 'missing_observer'])
def test_source_relationship_is_read_only_and_never_assumed(native, binding_case):
    from apps.desktop_pre.mesh_binding import PROPERTY_NAME
    preserved(native)
    native.mesh_bindings.slotChangedObject(native.mesh, 'FemMesh')
    if binding_case == 'changed_shape':
        native.shape.Shape.brep = 'changed CAD, original native mesh retained'
    elif binding_case == 'missing_observer':
        del native.mesh_bindings
    saved = deepcopy(native.metadata), getattr(native.mesh, PROPERTY_NAME), _mesh_hash(native.mesh.FemMesh)
    result = compare(native)
    assert result['current_source_relationship']['state'] == ('MATCH' if binding_case == 'match' else 'UNCONFIRMED')
    if binding_case != 'match':
        assert '현재 형상 해석에는 다시 메시를 생성' in result['current_source_relationship']['message']
    assert saved == (native.metadata, getattr(native.mesh, PROPERTY_NAME), _mesh_hash(native.mesh.FemMesh))
    assert result['current']['total_elements'] == 1  # Stale source does not suppress reading retained mesh values.
    assert native.transactions == [] and native.tools == []
