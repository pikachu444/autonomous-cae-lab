"""C1 native semantic unit evidence. NO FreeCAD runtime/FCStd claim."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
from unittest.mock import patch
import pytest

from apps.desktop_pre import law_native_material as native
from caelab import material_fe_transfer as transfer
from caelab.storage import canonical_hash
from caelab.law_native_identity import (semantic_target, capture_proxy,
    require_native_version, PROXY_CLASSES)

FROZEN = Path(__file__).parent/'fixtures/c1-frozen-simulation.json'


def seed():
    return json.loads(FROZEN.read_text(encoding='utf-8'))


def other_session(target):
    value = deepcopy(target)
    value.update(session_id='SnewSession', generation=0)
    for obj in (value['material'], value['native_context_solver'], *value['native_analysis_members']):
        if 'Proxy' in obj['properties']:
            name = PROXY_CLASSES[obj['type']]
            obj['properties']['Proxy'] = '<' + name + ' object at 0x1111222233334444>'
    return value


def _scripted_object(row, owner):
    clsname = PROXY_CLASSES[row['type']];module, name = clsname.rsplit('.', 1)
    Proxy = type(name, (), {'__module__': module, 'Type': row['type']})
    obj = SimpleNamespace(Name=row['object_id'], Document=owner.doc, TypeId='App::FeaturePython',
                          PropertiesList=list(row['properties']))
    for key, value in row['properties'].items():
        if key == 'References':
            value = [(SimpleNamespace(Name=link['object_id'], Document=owner.doc), names) for link, names in value]
        setattr(obj, key, Proxy() if key == 'Proxy' else value if key == 'References' else deepcopy(value))
    return obj


def test_two_sessions_ignore_only_recognized_proxy_allocation_addresses():
    original = seed()['native_target'];new = other_session(original)
    assert original['material']['properties']['Proxy'] != new['material']['properties']['Proxy']
    # Baseline comparison would differ; C1 recognizes exact class declaration.
    old_semantic = lambda t: {k: v for k, v in t.items() if k not in ('session_id', 'generation')}
    assert old_semantic(original) != old_semantic(new)
    assert semantic_target(original) == semantic_target(new)
    assert semantic_target(original)['document_id'] == original['document_id']


def test_capture_stable_proxy_without_calling_repr():
    t = seed()['native_target']
    owner = SimpleNamespace(document_id=t['document_id'], doc=SimpleNamespace(Name='specimen'))
    for key in ('material', 'native_context_solver'):
        a, b = _scripted_object(t[key], owner), _scripted_object(t[key], owner)
        type(a.Proxy).__str__ = lambda _: (_ for _ in ()).throw(AssertionError('NO_PROXY_STR'))
        assert native._physics(a, owner=owner) == native._physics(b, owner=owner)
        assert native._physics(a, owner=owner) == semantic_target(t)[key]
    with pytest.raises(ValueError, match='UNSUPPORTED'):
        capture_proxy(SimpleNamespace(Type='Fem::MaterialCommon'), 'Fem::MaterialCommon')
    with pytest.raises(ValueError, match='runtime object'):
        native._native_value(object())


@pytest.mark.parametrize('field', ('material', 'solver', 'step', 'region', 'geometry', 'mesh',
    'connectivity', 'native_node_ids', 'membership', 'member_property', 'metadata', 'assignment',
    'document', 'selection', 'solver_type'))
def test_real_physical_or_document_changes_still_stale(field):
    a = seed()['native_target'];b = other_session(a)
    if field == 'material': b['material']['properties']['Material']['YoungsModulus'] = '209000 MPa'
    elif field == 'solver': b['native_context_solver']['properties']['MatrixSolverType'] = 'changed'
    elif field == 'step': b['native_context_solver']['properties']['TimePeriod'] = '2.0 s'
    elif field == 'region': b['region']['target']['subelements'][0]['name'] = 'Solid2'
    elif field == 'geometry': b['geometry']['brep_sha256'] = 'a'*64
    elif field == 'mesh': b['mesh']['points'][13][0] += .01
    elif field == 'connectivity': b['mesh']['cells'][0][0], b['mesh']['cells'][0][1] = b['mesh']['cells'][0][1], b['mesh']['cells'][0][0]
    elif field == 'native_node_ids': b['native_node_ids'][0] += 100
    elif field == 'membership': b['native_analysis_members'].pop()
    elif field == 'member_property': b['native_analysis_members'][0]['properties']['Suppressed'] = True
    elif field == 'metadata': b['metadata_sha256'] = 'b'*64
    elif field == 'assignment': b['current_assignment_property'] += ' '
    elif field == 'document': b['document_id'] = 'Pdifferent'
    elif field == 'selection': b['selection']['analysis_id'] = 'AnotherAnalysis'
    elif field == 'solver_type': b['native_context_solver']['type'] = 'Fem::DifferentSolver'
    try:
        assert semantic_target(a) != semantic_target(b)
    except ValueError:
        assert field == 'solver_type'


def test_addresses_are_not_stripped_from_other_physical_text():
    a = seed()['native_target'];b = deepcopy(a)
    b['material']['properties']['Material']['Name'] = '<Custom object at 0x1234>'
    assert semantic_target(a) != semantic_target(b)
    b = deepcopy(a);b['material']['properties']['Proxy'] = '<untrusted.Custom object at 0x1234>'
    with pytest.raises(ValueError, match='UNSUPPORTED'): semantic_target(b)
    b = semantic_target(a);b['material']['properties']['Proxy']['native_type'] = 'other'
    with pytest.raises(ValueError, match='UNSUPPORTED'): semantic_target(b)


class RetainedFixture:
    """Frozen snapshot fixture only, no shape/mesh recreation and no transaction."""
    def __init__(self, record):
        self.data = {'law_native_assignments': [deepcopy(record)]}
        self.base = SimpleNamespace(CAELabLawNative=record['native_property'])
        self.owner = SimpleNamespace(_object=lambda _: self.base)
    def _metadata(self): return deepcopy(self.data)


def test_old_assignment_refreeze_preserves_exact_receipt_without_live_cas(monkeypatch, historical_installation):
    original = seed();r = original['simulation_draft']['settings']['source_receipt']
    f = RetainedFixture(r);new = other_session(original['native_target'])
    # New process has the filename-derived internal name, not the original name.
    owner = SimpleNamespace(document_id=new['document_id'], doc=SimpleNamespace(Name='specimen'))
    # New capture representation, rather than another legacy repr.
    for key in ('material', 'native_context_solver'):
        new[key] = native._physics(_scripted_object(new[key], owner), owner=owner)
    for index, obj in enumerate(new['native_analysis_members']):
        if 'Proxy' in obj['properties']:
            new['native_analysis_members'][index] = native._physics(_scripted_object(obj, owner), owner=owner)
    before = deepcopy(f.data)
    monkeypatch.setattr(native, 'capture', lambda *args: deepcopy(new))
    with patch.object(transfer, 'file_hash', side_effect=AssertionError('LIVE_CAS_IO')):
        out = native.freeze(f, r['selection'])
    assert out['simulation_draft'] == original['simulation_draft']
    assert out['assignment_sha256'] == r['assignment_sha256'] and f.data == before
    assert out['native_target']['session_id'] != original['native_target']['session_id']
    new['native_context_solver']['properties']['TimePeriod'] = '9 s'
    with pytest.raises(ValueError, match='ASSIGNMENT_STALE'): native.freeze(f, r['selection'])


def test_live_apply_cas_is_not_semantic_reopen_comparison():
    review = seed()['simulation_draft']['settings']['source_receipt']['review']
    target = deepcopy(review['target']);target['generation'] += 1
    with pytest.raises(ValueError, match='TARGET_CONFLICT'):
        transfer.verify_review(review, target, live_source=False)
    target = deepcopy(review['target']);target['session_id'] = 'Sdifferent'
    with pytest.raises(ValueError, match='TARGET_CONFLICT'):
        transfer.verify_review(review, target, live_source=False)
    # Isolate both guard states; the original Windows files may exist locally.
    # No real source path is accessed and a live hash mismatch must still block.
    for exists in (False, True):
        with patch.object(transfer, 'Path') as guard_path, patch.object(
                transfer, 'file_hash', return_value='0'*64) as guard_hash:
            guard_path.return_value.is_symlink.return_value = False
            guard_path.return_value.is_file.return_value = exists
            with pytest.raises(ValueError, match='SOURCE_CONFLICT'):
                transfer.verify_source(review['source'], live=True, current_code=True)
            guard_path.assert_called_once_with(review['source']['source_guard'][0]['path'])
            assert guard_hash.call_count == int(exists)


def test_supported_native_version_is_explicit():
    require_native_version(['1', '1', '4', 'build-metadata'])
    for version in (['1','1','5'], ['1','0','2'], ['UNKNOWN']):
        with pytest.raises(ValueError, match='VERSION_UNSUPPORTED'): require_native_version(version)


def test_local_link_uses_persistent_document_and_rejects_same_named_foreign_object():
    t = seed()['native_target']
    a = SimpleNamespace(document_id=t['document_id'], doc=SimpleNamespace(Name='LawNativeSpecimen'))
    b = SimpleNamespace(document_id=t['document_id'], doc=SimpleNamespace(Name='specimen'))
    oa = SimpleNamespace(Name='Specimen', Document=a.doc)
    ob = SimpleNamespace(Name='Specimen', Document=b.doc)
    assert native._native_value(oa, owner=a) == native._native_value(ob, owner=b)
    with pytest.raises(ValueError, match='same-document'):
        native._native_value(ob, owner=a)
    target = semantic_target(t)
    target['material']['properties']['References'][0][0]['document_id'] = 'Pforeign'
    with pytest.raises(ValueError, match='different document'):
        semantic_target(target)
    t['native_analysis_members'][0]['properties']['References'][0][0]['document'] = 'Contradictory'
    with pytest.raises(ValueError, match='contradictory'):
        semantic_target(t)
