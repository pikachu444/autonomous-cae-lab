"""Core retention tests. Every 'native' receipt below is a SCRIPTED contract fixture."""
from copy import deepcopy
import base64
import hashlib
import json
import shutil

import pytest

from caelab.report_document import ReportDocuments, default_draft, diagnostics
from caelab import report_image as images
from caelab.storage import canonical_hash, load_json, save_json
from caelab.workbench import Workbench
from apps.research.report_image_pages import image_markdown, availability_message
from report_image_fixture import fixture, png_bytes


def forbidden(*args, **kwargs):
    raise AssertionError('No provider/solver/job call is permitted in an image/report test')


def owner(root, resolve=forbidden):
    return ReportDocuments(root, 'Sservice', forbidden, None, resolve_reference=resolve)


def command(store, doc, operation, arguments=None):
    return store.command(doc['id'], operation, arguments or {}, session_id=doc['session_id'],
                         expected_generation=doc['generation'])['document']


def test_capture_existing_store_save_reopen_and_external_removal(tmp_path):
    f = fixture(tmp_path/'원 Post')
    store = owner(tmp_path/'보관소'); doc = store.open()
    previous = deepcopy(doc)
    binding = store.capture_image(doc['id'], f['command'])
    assert store.read(doc['id']) == previous  # capture is not document adoption
    asset = store.content(doc['id'], [binding])['assets'][0]
    assert asset['source_status'] == 'AVAILABLE'
    assert images.validate_content(asset['content']) == f['png'].read_bytes()
    draft = images.apply_binding(doc['draft'], binding, asset['content'])
    draft['sections'][0]['text'] = '판단: 아직 미승인. 다음 연구에서 경계 조건을 검토한다.'
    assert not diagnostics(draft)
    doc = command(store, doc, 'report.update', {'draft': draft})
    doc = command(store, doc, 'document.save')
    immutable = store._folder(doc['id']) / 'revisions' / doc['saved_revision']
    assert (immutable/'assets'/(binding['id']+'.json')).is_file()
    png = f['png'].read_bytes()
    shutil.rmtree(tmp_path/'원 Post')
    shutil.rmtree(store._folder(doc['id'])/'assets')  # read saved revision, not source export
    fresh = owner(tmp_path/'보관소')
    reopened = fresh.open(document_id=doc['id'])
    retained = fresh.content(doc['id'], [binding])['assets'][0]
    assert reopened['draft'] == draft
    assert retained['source_status'] == 'UNAVAILABLE'
    assert images.validate_content(retained['content']) == png
    assert reopened['runs'] == []
    markdown = image_markdown(retained['content'], draft['sections'][0])
    assert base64.b64encode(png).decode() in markdown
    # Report copied as a work folder remains readable independently of the source Post folder.
    moved = tmp_path/'이동 폴더'/'보고서 복사'; shutil.copytree(tmp_path/'보관소', moved)
    reopened_copy = owner(moved).open(document_id=doc['id'])
    assert reopened_copy['draft'] == draft
    assert images.validate_content(owner(moved).content(doc['id'], [binding])['assets'][0]['content']) == png


def test_study_judgments_and_old_assets_survive_image_replacement_undo(tmp_path):
    study = {'id': 'Dstudy', 'kind': 'study', 'title': '연구 판단',
             'draft': {'question': '경계 조건이 맞는가?', 'decisions': [{'statement': '승인 보류', 'status': 'UNKNOWN'}],
                       'hypotheses': [{'statement': '강성 영향'}], 'next_observations': [{'question': '재시험'}]}}
    ref = {'kind': 'document', 'document_kind': 'study', 'document_id': 'Dstudy',
           'saved_revision': 'Rstudy', 'input_revision': 'Istudy', 'input_sha256': canonical_hash(study['draft'])}
    store = owner(tmp_path/'store', lambda r: {'kind': 'document', 'document': deepcopy(study)})
    doc = store.open(); study_binding = store.capture(doc['id'], ref)
    draft = default_draft(); draft['sections'] = [{'id': 'Estudy', 'title': '연구 판단', 'text': '변경하지 않음',
        'include': True, 'table': True, 'curve': True, 'asset': study_binding}]
    f1, f2 = fixture(tmp_path/'first'), fixture(tmp_path/'second', command_id='Csecond', pixel=(30, 40, 50))
    b1 = store.capture_image(doc['id'], f1['command']); a1 = store.asset(doc['id'], b1)['content']
    draft = images.apply_binding(draft, b1, a1)
    draft['sections'][-1]['text'] = '기존 이미지에 대한 설명과 판단'
    doc = command(store, doc, 'report.update', {'draft': draft})
    doc = command(store, doc, 'document.save')
    saved_before = doc['saved_revision']
    old_section = deepcopy(draft['sections'][-1])
    b2 = store.capture_image(doc['id'], f2['command']); a2 = store.asset(doc['id'], b2)['content']
    # Cancellation: merely capture/read candidate; no draft command.
    assert store.read(doc['id'])['draft'] == draft
    changed = images.apply_binding(draft, b2, a2, section_id=old_section['id'], expected_section=old_section)
    assert changed['sections'][0] == draft['sections'][0]
    assert changed['sections'][-1]['text'] == old_section['text']
    doc = command(store, doc, 'report.update', {'draft': changed})
    doc = command(store, doc, 'document.undo'); assert doc['draft'] == draft
    doc = command(store, doc, 'document.redo'); assert doc['draft'] == changed
    doc = command(store, doc, 'document.save')
    assert doc['saved_revision'] != saved_before
    old_saved = load_json(store._folder(doc['id'])/'revisions'/saved_before/'document.json')
    assert old_saved['draft'] == draft
    reopened = owner(tmp_path/'store').open(document_id=doc['id'])
    assert reopened['draft'] == changed
    revision = store._folder(doc['id'])/'revisions'/doc['saved_revision']/'assets'
    assert all((revision/(binding['id']+'.json')).is_file() for binding in (b1, b2, study_binding))


@pytest.mark.parametrize('mutation', [
    lambda c: c.update(state='FAILED'), lambda c: c.update(state='UNKNOWN'),
    lambda c: c.update(state='INTERRUPTED'), lambda c: c['outcome'].update(state='FAILED'),
    lambda c: c['arguments'].pop('report_snapshot'),
    lambda c: c['outcome']['result'].update(document_id='Dwrong'),
    lambda c: c['outcome']['result'].update(session_id='Sother'),
    lambda c: c['outcome']['result'].update(command_id='Cwrong'),
    lambda c: c['arguments'].update(object_ref='Fother'),
    lambda c: c['outcome']['result']['result'].update(analysis_saved=True),
    lambda c: c['outcome']['result']['result']['report_snapshot'].update(capture_status='UNKNOWN'),
    lambda c: c['outcome']['result']['result']['report_snapshot']['data_match'].update(status='UNKNOWN'),
    lambda c: c['outcome']['result']['result']['report_snapshot']['scene']['clock'].update(value=.2500000001),
    lambda c: c['outcome']['result']['result']['report_snapshot']['scene']['field'].update(association='UNKNOWN'),
    lambda c: c['outcome']['result']['result']['report_snapshot']['scene'].update(view_name='RenderViewOther'),
])
def test_bad_capture_keeps_previous_draft_and_asset(tmp_path, mutation):
    f = fixture(tmp_path/'post'); store = owner(tmp_path/'store'); doc = store.open()
    b = store.capture_image(doc['id'], f['command']); a = store.asset(doc['id'], b)['content']
    doc = command(store, doc, 'report.update', {'draft': images.apply_binding(doc['draft'], b, a)})
    before = deepcopy(doc); bad = deepcopy(f['command']); mutation(bad)
    with pytest.raises((ValueError, KeyError, TypeError)):
        store.capture_image(doc['id'], bad)
    assert store.read(doc['id']) == before
    assert store.asset(doc['id'], b)['content'] == a


@pytest.mark.parametrize('target', ['png', 'source', 'result', 'state', 'manifest'])
@pytest.mark.parametrize('fault', ['missing', 'tampered'])
def test_missing_and_hash_changes_block_new_adoption_but_keep_frozen(tmp_path, target, fault):
    f = fixture(tmp_path/'post'); store = owner(tmp_path/'store'); doc = store.open()
    binding = store.capture_image(doc['id'], f['command']); frozen = store.asset(doc['id'], binding)
    path = f[target]
    if fault == 'missing': path.unlink()
    else: path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises((ValueError, OSError)):
        store.capture_image(doc['id'], f['command'])
    retained = store.content(doc['id'], [binding])['assets'][0]
    assert retained['content'] == frozen['content']
    assert retained['source_status'] == ('AVAILABLE' if target == 'png' else 'UNAVAILABLE')


def test_corrupt_report_asset_read_flags_and_failed_save_keeps_manifest(tmp_path):
    f = fixture(tmp_path/'post'); store = owner(tmp_path/'store'); doc = store.open()
    b = store.capture_image(doc['id'], f['command']); asset = store.content(doc['id'], [b])['assets'][0]
    doc = command(store, doc, 'report.update', {'draft': images.apply_binding(doc['draft'], b, asset['content'])})
    doc = command(store, doc, 'document.save'); before = deepcopy(doc)
    manifest = (store._folder(doc['id'])/'document.json').read_bytes()
    (store._folder(doc['id'])/'assets'/(b['id']+'.json')).write_text('{}')
    bad = store.content(doc['id'], [b])['assets'][0]
    assert bad['source_status'] == 'SNAPSHOT_UNAVAILABLE'
    preserved = images.merge_read_assets({b['id']: asset}, [bad])[b['id']]
    assert preserved['content'] == asset['content'] and preserved['retained_preview_only']
    assert '화면 사본' in availability_message(preserved)
    draft = deepcopy(doc['draft']); draft['title'] = '새 본문 (실패 시 보존)'
    doc = command(store, doc, 'report.update', {'draft': draft})
    with pytest.raises(ValueError): command(store, doc, 'document.save')
    assert (store._folder(doc['id'])/'document.json').read_bytes() == manifest
    assert store.read(doc['id'])['draft'] == draft
    assert load_json(store._folder(doc['id'])/'revisions'/before['saved_revision']/'document.json')['draft'] == before['draft']


def test_exact_replacement_rejects_late_section_edit_and_unknown_units_stay_unknown(tmp_path):
    f = fixture(tmp_path/'post'); ref, content = images.completed_content(f['command'])
    binding = {'id': 'A'+canonical_hash({'reference': ref, 'content': content}),
        'sha256': canonical_hash({'reference': ref, 'content': content}), 'reference': ref}
    draft = images.apply_binding(default_draft(), binding, content); expected = deepcopy(draft['sections'][0])
    draft['sections'][0]['text'] = '늦게 입력한 판단'
    with pytest.raises(ValueError): images.apply_binding(draft, binding, content, section_id=expected['id'], expected_section=expected)
    snapshot = deepcopy(f['snapshot']); field = snapshot['scene']['field']
    field.update(unit=None, unit_status='UNKNOWN')
    snapshot['scene']['clock'].update(status='NO_DATA_TIME', value=None)
    images.validate_snapshot(snapshot)
    text = images.caption(snapshot)
    assert '단위 미확인' in text and '0초 아님' in text and '공학 승인 없음' in text
    assert 'UNKNOWN' in text or '미확인' in text


def test_workbench_only_accepts_command_id_not_caller_receipt(tmp_path):
    f = fixture(tmp_path/'post')
    # Isolate the actual Workbench report method. The curated attachment omits
    # apps.desktop_pre, so full Workbench bootstrap is a separate integration test.
    from types import SimpleNamespace
    store = owner(tmp_path/'store'); report = store.open()
    wb = Workbench.__new__(Workbench)
    wb.report_documents = store
    calls = []
    def status(identifier):
        calls.append(identifier)
        assert identifier == 'Ccapture'
        return deepcopy(f['command'])
    wb.native_commands = SimpleNamespace(status=status)
    binding = wb.report_capture(report['id'], {'kind': 'post_image_command', 'command_id': 'Ccapture'})
    assert store.content(report['id'], [binding])['assets'][0]['content']['kind'] == 'post_image'
    with pytest.raises(ValueError):
        wb.report_capture(report['id'], {'kind': 'post_image_command', 'command_id': 'Ccapture', 'receipt': f['receipt']})
    assert calls == ['Ccapture']
    assert store.read(report['id'])['runs'] == []



@pytest.mark.parametrize('mutation', [lambda x: x[:-1], lambda x: b'not PNG',
    lambda x: x[:20]+bytes([x[20]^1])+x[21:], lambda x: x+b'trailing'])
def test_png_damage_detected(mutation):
    with pytest.raises(ValueError): images.png_dimensions(mutation(png_bytes()))


@pytest.mark.parametrize('width', [0, 9, 101, True, 50.0])
def test_image_size_contract(width):
    with pytest.raises(ValueError): images.image_options({'image': {'show': True, 'width_percent': width}})


@pytest.mark.parametrize('fault', ['missing', 'tampered'])
def test_cold_open_damaged_image_retains_verified_body_without_inventing_pixels(tmp_path, fault):
    f=fixture(tmp_path/'post'); store=owner(tmp_path/'store'); doc=store.open()
    b=store.capture_image(doc['id'],f['command']); content=store.asset(doc['id'],b)['content']
    draft=images.apply_binding(doc['draft'],b,content);draft['sections'][0]['text']='판단과 본문은 그대로'
    doc=command(store,doc,'report.update',{'draft':draft});doc=command(store,doc,'document.save')
    folder=store._folder(doc['id']); path=folder/'revisions'/doc['saved_revision']/'assets'/(b['id']+'.json')
    shutil.rmtree(folder/'assets');(folder/'working.json').unlink()
    if fault=='missing':path.unlink()
    else:path.write_text('{}')
    fresh=owner(tmp_path/'store');opened=fresh.open(document_id=doc['id'])
    assert opened['draft']==draft
    unavailable=fresh.content(doc['id'],[b])['assets'][0]
    assert unavailable['source_status']=='SNAPSHOT_UNAVAILABLE' and 'content' not in unavailable
    assert opened['runs']==[]


def test_degraded_reopen_never_ignores_corrupt_body(tmp_path):
    f=fixture(tmp_path/'post');store=owner(tmp_path/'store');doc=store.open()
    b=store.capture_image(doc['id'],f['command']);content=store.asset(doc['id'],b)['content']
    doc=command(store,doc,'report.update',{'draft':images.apply_binding(doc['draft'],b,content)})
    doc=command(store,doc,'document.save')
    (store._folder(doc['id'])/'revisions'/doc['saved_revision']/'document.json').write_text('{}')
    with pytest.raises(ValueError): owner(tmp_path/'store').open(document_id=doc['id'])


@pytest.mark.parametrize('problem', ['zlib', 'filter', 'short', 'long', 'trailing_stream', 'palette_missing'])
def test_crc_valid_but_undecodable_png_rejected(problem):
    import struct
    import zlib
    def chunk(tag, value):
        return struct.pack('>I', len(value)) + tag + value + struct.pack('>I', zlib.crc32(tag + value) & 0xffffffff)
    raw = b'\0' + b'\x10\x20\x30'
    payload = zlib.compress(raw)
    if problem == 'zlib': payload = b'not a deflate stream'
    if problem == 'filter': payload = zlib.compress(b'\x05' + raw[1:])
    if problem == 'short': payload = zlib.compress(raw[:-1])
    if problem == 'long': payload = zlib.compress(raw + b'excess')
    if problem == 'trailing_stream': payload += zlib.compress(raw)
    color = 3 if problem == 'palette_missing' else 2
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, color, 0, 0, 0)) +
           chunk(b'IDAT', payload) + chunk(b'IEND', b''))
    with pytest.raises(ValueError): images.png_dimensions(png)


def test_png_inflation_crosses_chunks_and_large_rows():
    # Exact stream output exceeds the 64 KiB temporary buffer; still bounded.
    assert images.png_dimensions(png_bytes(8000, 4)) == (8000, 4)


def test_upstream_warp_is_bound_to_used_revision_not_current_selection(tmp_path):
    from caelab.post_observation import file_pin
    f = fixture(tmp_path/'post')
    older = deepcopy(f['record']); older['id'] = 'Rwarp1'
    older['graph'] = {'nodes': [{'type': 'WarpByVector', 'properties': {'ScaleFactor': 7}}]}
    older['recipe'].update(filter='WarpByVector')
    newer = deepcopy(older); newer['id'] = 'Rwarp2'
    newer['graph']['nodes'][0]['properties']['ScaleFactor'] = 70
    upstream = {'id': 'Fupstream', 'kind': 'filter', 'position': 1, 'history': [older, newer]}
    f['project']['analysis']['objects']['Fupstream'] = upstream
    f['record']['recipe']['source_ref'] = 'Fupstream'
    f['record']['bindings'] = {'Fupstream': {'revision': canonical_hash({
        key: older[key] for key in ('id', 'recipe', 'graph', 'bindings')})}}
    f['record']['dependencies'] = {'Fupstream': 'Rwarp1'}
    f['manifest'].write_text(json.dumps(f['project'], ensure_ascii=False), encoding='utf-8')
    origin, project, obj, record = images.make_origin(file_pin(f['manifest']), 'Dpost', 'Snative', 123,
                                                   'Fresult', 'Rresult')
    lineage = images.retained_analyses(project, obj, record)
    assert [item['revision'] for item in lineage] == ['Rwarp1', 'Rresult']
    assert images.warp_conditions(lineage)[0]['scale'] == 7
    snapshot = f['snapshot']; snapshot.update(origin=origin, lineage=lineage,
        sources=images.source_records(project, obj, record), recipe=deepcopy(record['recipe']))
    snapshot['scene']['warp'] = images.warp_conditions(lineage)
    from caelab.report_image_axis import saved_axis_context
    snapshot['scene']['axis_context'] = saved_axis_context(project, obj, record)
    _, content = images.completed_content(f['command'])
    assert '×7' in images.caption(content['snapshot']) and '×70' not in images.caption(content['snapshot'])
    snapshot['scene']['warp'][0]['scale'] = 70
    with pytest.raises(ValueError): images.completed_content(f['command'])


@pytest.mark.parametrize('change', [lambda field:field.update(components=0),
    lambda field:field.update(unit='', unit_status='DECLARED'),
    lambda field:field.update(component={'mode':'COMPONENT','index':4})])
def test_incomplete_component_and_declared_unit_do_not_publish(tmp_path, change):
    f=fixture(tmp_path/'post'); change(f['snapshot']['scene']['field'])
    with pytest.raises(ValueError): images.completed_content(f['command'])


def test_damaged_unpublished_image_revision_cannot_use_degraded_read_to_commit(tmp_path, monkeypatch):
    f = fixture(tmp_path/'post'); store = owner(tmp_path/'store'); doc = store.open()
    binding = store.capture_image(doc['id'], f['command'])
    content = store.asset(doc['id'], binding)['content']
    doc = command(store, doc, 'report.update', {'draft': images.apply_binding(doc['draft'], binding, content)})
    doc = command(store, doc, 'document.save')
    publication = store._folder(doc['id'])/'document.json'; before = publication.read_bytes()
    previous = doc['saved_revision']; verify = store._verify_revision
    def damage_before_publish(identifier, revision):
        if revision != previous:
            (store._folder(identifier)/'revisions'/revision/'assets'/(binding['id']+'.json')).unlink()
        return verify(identifier, revision)
    monkeypatch.setattr(store, '_verify_revision', damage_before_publish)
    changed = deepcopy(doc['draft']); changed['sections'][0]['text'] = '계속 보존할 새 판단'
    doc = command(store, doc, 'report.update', {'draft': changed})
    with pytest.raises(ValueError): command(store, doc, 'document.save')
    assert publication.read_bytes() == before
    assert store.read(doc['id'])['draft'] == changed
