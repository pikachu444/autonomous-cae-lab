"""M4 admission contract and retained partial drafts; native objects are doubles.

These tests call the M4 validator directly. They do NOT claim the separately
owned generic FEM mesh/freeze/contact/run gates have been integrated.
"""
from copy import deepcopy
from pathlib import Path
import pytest

from assembly_pose_doubles import source_fixture, Owner, pose
from test_assembly_pose_candidate import run_preparation
from apps.desktop_pre import metadata
from apps.desktop_pre.assembly_pose_candidate import (
    KEY, PoseCandidates, validate_model, require_valid, prepare_fem_object,
    _hold, _release,
)
from apps.desktop_pre.projects import remember_open
from caelab import native_cad


@pytest.fixture
def ready(tmp_path, monkeypatch):
    original, root, _ = source_fixture(tmp_path, monkeypatch)
    job = run_preparation(original, root)
    assert job.current['state'] == 'READY', job.current
    owner = Owner(job._document, original.export_root, App=original.App, Gui=original.Gui)
    owner.pose_candidates = PoseCandidates(owner)
    return original, owner


def state(owner, value):
    data = owner.read_metadata()
    data[KEY]['state'] = value
    owner.write_metadata(data)


def reopen(owner, path, folder):
    manifest, entry = native_cad.unpack_project(path, folder)
    doc = owner.App.openDocument(str(entry))
    remember_open(doc, manifest, path)
    return Owner(doc, owner.export_root, App=owner.App, Gui=owner.Gui)


@pytest.mark.parametrize('outcome', ['FAILED', 'CANCELLED'])
def test_partial_after_first_body_is_not_admitted_but_edit_save_reopen_survives(tmp_path, monkeypatch, outcome):
    original, root, _ = source_fixture(tmp_path, monkeypatch)
    source_before = original.read_metadata()
    def stop(job):
        if job._document is None:
            return
        if len(metadata.read(job._document).get(KEY, {}).get('bodies', [])) == 1:
            if outcome == 'CANCELLED':
                job.cancel()
            else:
                def fail():
                    raise RuntimeError('controlled failure before the second occurrence')
                job._check = fail
    job = run_preparation(original, root, stop)
    assert job.current['state'] == outcome
    draft = Path(job.current['draft_project'])
    preserved = draft.read_bytes()
    owner = reopen(original, draft, tmp_path/'부분 사본 열기')
    report = validate_model(owner)
    assert report['errors'] == [] and len(report['bodies']) == 1  # actual P2 trigger
    before = owner.read_metadata(); count = owner.doc.recomputes
    with pytest.raises(ValueError):
        require_valid(owner)
    body_id = report['bodies'][0]['body_id']
    for kind in ('mesh', 'material'):
        with pytest.raises(ValueError):
            prepare_fem_object(owner, body_id, kind)
    assert owner.read_metadata() == before and owner.doc.recomputes == count
    assert report['state'] == outcome and report['geometry_valid']
    assert not report['preparation_complete'] and not report['ready']
    # An ordinary explicit edit and .caepre save are not subject to FEM admission.
    body = owner._object(body_id)
    owner._transaction('준비 사본 편집', lambda: setattr(body, 'Label', '검토 후 저장한 부품'))
    saved = owner.project.save(tmp_path/'부분 사본 수정 저장.caepre')
    fresh = reopen(owner, saved['path'], tmp_path/'수정 사본 재열기')
    assert fresh._object(body_id).Label == '검토 후 저장한 부품'
    assert validate_model(fresh)['preparation_state'] == outcome
    with pytest.raises(ValueError): require_valid(fresh)
    assert draft.read_bytes() == preserved
    assert original.read_metadata() == source_before and original.doc.recomputes == 0
    assert not original.closed


@pytest.mark.parametrize('value', ['FAILED', 'CANCELLED', 'INTERRUPTED', 'PREPARING', 'DRAFT', 'UNKNOWN', '', None])
def test_nonready_complete_geometry_does_not_authorize_normal_fem(ready, value):
    _, owner = ready
    state(owner, value)
    before = owner.read_metadata(); count = owner.doc.recomputes
    report = validate_model(owner)
    assert report['errors'] == []
    with pytest.raises(ValueError): require_valid(owner, exact=False)
    assert not report['ready']
    assert report['blocked_reason']
    assert owner.read_metadata() == before and owner.doc.recomputes == count


def test_preparing_exact_readback_is_allowed_without_granting_normal_admission(ready):
    _, owner = ready
    state(owner, 'PREPARING')
    _hold(owner.doc)
    try:
        before = owner.read_metadata(); count = owner.doc.recomputes
        report = require_valid(owner, exact=True)
        assert report['state'] == 'PREPARING' and not report['ready']
        with pytest.raises(ValueError): require_valid(owner)
        state(owner, 'READY')
        assert require_valid(owner, exact=True)['state'] == 'READY'
        assert require_valid(owner)['ready']  # _hold also reserves native test owners; it is not a state
        assert owner.doc.recomputes == count
        state(owner, 'PREPARING'); assert owner.read_metadata() == before
    finally:
        _release(owner.doc)
    state(owner, 'READY')
    assert require_valid(owner)['ready']


@pytest.mark.parametrize('value', ['FAILED', 'CANCELLED', 'INTERRUPTED', 'DRAFT'])
def test_exact_is_not_an_escape_for_failed_or_draft_states(ready, value):
    _, owner = ready; state(owner, value)
    with pytest.raises(ValueError): require_valid(owner, exact=True)


def test_ready_means_model_admission_not_a_solved_or_fully_configured_fem(ready, tmp_path):
    _, owner = ready
    report = require_valid(owner)
    assert report['state'] == 'READY' and report['preparation_complete'] and report['ready']
    analysis = owner._object(report['analysis_id'])
    assert len(analysis.Group) == 1  # solver settings only; no mesh, material or BC required
    material = prepare_fem_object(owner, report['bodies'][0]['body_id'], 'material')
    assert owner._object(material['object_id']).Material == {}
    saved = owner.project.save(tmp_path/'미완성 재료 초안.caepre')
    fresh = reopen(owner, saved['path'], tmp_path/'미완성 재료 재열기')
    assert require_valid(fresh)['ready']
    assert fresh._object(material['object_id']).Material == {}


def test_descriptor_tracks_metadata_changes_without_generation_and_is_detached(ready):
    _, owner = ready
    initial = owner.pose_candidates.descriptor()['model']
    assert initial['ready']
    generation = owner.generation
    state(owner, 'FAILED')
    assert owner.generation == generation
    failed = owner.pose_candidates.descriptor()['model']
    assert failed['state'] == 'FAILED' and not failed['ready']
    failed['ready'] = True; failed['bodies'].clear()
    assert not owner.pose_candidates.descriptor()['model']['ready']
    state(owner, 'READY'); assert owner.pose_candidates.descriptor()['model']['ready']


@pytest.mark.parametrize('bad', [None, {}, [], '', {'version': 999}, {'version': 1}])
def test_present_malformed_metadata_is_invalid_not_an_ordinary_document(ready, bad):
    _, owner = ready; data = owner.read_metadata(); data[KEY] = deepcopy(bad); owner.write_metadata(data)
    report = validate_model(owner)
    assert report is not None and report['state'] == 'INVALID' and report['errors']
    assert not report['ready']
    with pytest.raises(ValueError): require_valid(owner)
    del data[KEY]; owner.write_metadata(data)
    assert validate_model(owner) is None


def test_ready_cannot_hide_a_retained_occurrence_by_truncating_the_row_list(ready):
    _, owner = ready; data = owner.read_metadata(); data[KEY]['bodies'].pop(); owner.write_metadata(data)
    report = validate_model(owner)
    assert report['state'] == 'INVALID' and report['errors'] and not report['ready']
    with pytest.raises(ValueError): require_valid(owner)


@pytest.mark.parametrize('mutation', ['SourceIdentity', 'SourcePart', 'Link', 'Support', 'stale_binder'])
def test_fresh_common_consumer_contract_checks_identity_not_just_equal_brep(ready, mutation):
    _, owner = ready
    row, other = owner.read_metadata()[KEY]['bodies']
    body = owner._object(row['body_id']); link = owner._object(row['link_id'])
    alternate = owner._object(other['link_id']); source = owner._object(row['copied_source_id'])
    alternate.Placement = link.Placement.copy(); owner.doc.recompute()
    assert require_valid(owner)['state'] == 'READY'
    # Prime the descriptor, then deliberately do not advance generation. Every
    # real mesh/freeze/run caller must call require_valid, not trust this cache.
    assert owner.pose_candidates.descriptor()['model']['ready']
    brep = body.Shape.exportBrepToString()
    if mutation == 'SourceIdentity': body.SourceIdentity = 'same-shape-wrong-source'
    elif mutation == 'SourcePart': body.SourcePart = alternate
    elif mutation == 'Link': link.setLink(owner.doc.copyObject([source], True)[0])
    elif mutation == 'Support': body.Support = [(alternate, ('',))]
    else: source.Shape.size = (19., 8., 6.)  # cached Binder unchanged
    before = owner.read_metadata(); count = owner.doc.recomputes
    assert body.Shape.exportBrepToString() == brep
    with pytest.raises(ValueError): require_valid(owner, exact=False)
    assert owner.read_metadata() == before and owner.doc.recomputes == count


@pytest.mark.parametrize('value', ['READY', 'FAILED', 'CANCELLED', 'PREPARING', 'DRAFT', 'INTERRUPTED'])
def test_panel_policy_uses_admission_not_just_a_valid_selected_row(ready, value):
    from apps.desktop_pre.assembly_pose_panel import model_actions
    _, owner = ready; state(owner, value)
    report = validate_model(owner)
    assert report['errors'] == []
    flags = model_actions(report, True)
    assert flags['cad']
    assert flags['mesh'] == flags['material'] == flags['condition'] == (value == 'READY')
    assert not any(model_actions(report, False).values())
    assert not any(model_actions(report, True, busy=True).values())
    assert not any(model_actions(report, True, closed=True).values())
