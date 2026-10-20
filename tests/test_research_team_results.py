"""Retained-owner/selector checks. Only the fixture producer is controlled."""
from copy import deepcopy
import time

import numpy as np
import pytest

from caelab import research_team_results as results
from caelab.evaluation import read_result, save_evaluation
from caelab.storage import canonical_hash
from caelab.workbench import Workbench


def command(wb, document, operation, arguments=None):
    return wb.document_command(document['id'], operation, arguments or {}, session_id=document['session_id'],
                               expected_generation=document['generation'])


def finished(wb, job):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        state = wb.manager.status(job['id'])
        if state['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED'}:
            assert state['state'] == 'SUCCEEDED', state
            return
        time.sleep(.005)
    raise AssertionError('Owned fixture job did not finish')


def retain_fixture(wb, monkeypatch, payload):
    """Use real JobManager/Material owner; no material/native/provider calculation."""
    import caelab.workbench as module
    original = module.evaluate
    monkeypatch.setattr(module, 'evaluate', lambda *a, **k: deepcopy(payload))
    try:
        document = wb.document_open(kind='material', title='Manufactured retained source, not physics')
        submitted = command(wb, document, 'material.evaluate')
        finished(wb, submitted['job'])
        document = wb.document_read(document['id'])
        saved = command(wb, document, 'document.save')['document']
        reference = wb.document_result_reference(saved['id'], submitted['job']['id'])
        verification = results.capture_result_verification(wb, reference)
        readers = results.workbench_readers(wb, verification_receipts=lambda ref: deepcopy(verification))
        return saved, reference, verification, readers
    finally:
        monkeypatch.setattr(module, 'evaluate', original)


@pytest.fixture
def wb(tmp_path):
    bench = Workbench(tmp_path / 'workspace', configuration={'workers': 1})
    yield bench
    assert bench.shutdown()['joined']


@pytest.fixture
def saved(wb, monkeypatch):
    payload = {'execution_status': 'SUCCEEDED', 'responses': {
        'u_x_A': {'kind': 'series', 'label': 'A점 X변위', 'value': [1., 2., 3.], 'unit': 'mm',
                  'component': 'X', 'location': 'A', 'measure': 'displacement', 'frame': 'global',
                  'source_rows': [10, 12, 14], 'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1., 1.]}]},
        'u_y_B': {'kind': 'series', 'value': [4., 5., 6.], 'unit': 'mm', 'component': 'Y', 'location': 'B',
                  'source_rows': [10, 12, 14], 'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1., 1.]}]},
        'field_z': {'kind': 'field', 'value': [7., 8., 9.], 'unit': 'Pa', 'component': 'ZZ',
                    'association': 'CELLS', 'location': 'part A', 'source_rows': [21, 23, 24],
                    'measure': 'Cauchy stress', 'coordinate_system': 'native Cartesian'}}}
    return retain_fixture(wb, monkeypatch, payload)


def choose(descriptor, response, **axes):
    return {'metadata_only': False, 'channels': [{'response': response, **axes}]}


def test_actual_owner_exact_frame_original_rows_and_field(saved):
    _, reference, _, readers = saved
    descriptor = readers['probe'](reference)
    selected = results.make_result_selection(descriptor, source_id='selected',
        selection_request=choose(descriptor, 'u_x_A', frame_indices=[2]))
    read = results.read_selected_result(reference, selected['selector'], readers=readers, read_limits=results.READ_LIMITS)
    response = read['payload']['channels'][0]['response']
    assert response['value'] == [3.] and response['source_rows'] == [14]
    assert response['axes'][0]['values'] == [1.]  # duplicate time retains frame 2, never nearest frame 1.
    assert read['receipt']['returned_selector']['channels'][0]['frame_indices'] == [2]
    assert next(d for d in descriptor['descriptor']['channels'] if d['response'] == 'u_x_A')['label'] == 'A점 X변위'
    field = results.make_result_selection(descriptor, source_id='cell',
        selection_request=choose(descriptor, 'field_z', row_intervals=[[23, 25]]))
    actual = results.read_selected_result(reference, field['selector'], readers=readers, read_limits=results.READ_LIMITS)
    assert actual['payload']['channels'][0]['response']['value'] == [8., 9.]
    assert actual['payload']['channels'][0]['response']['association'] == 'CELLS'


@pytest.mark.parametrize('change', [
    {'component': 'X', 'location_ids': ['B']}, {'unit': 'm'}, {'measure': 'engineering stress'},
    {'frame_indices': [3]}, {'frame_indices': [1], 'row_intervals': [[14, 15]]},
])
def test_fieldwise_union_unknown_unit_and_wrong_frame_are_blocked_before_numeric_read(saved, change):
    _, reference, _, readers = saved
    descriptor = readers['probe'](reference)
    grant = results.make_result_selection(descriptor, source_id='allowed')['selector']
    calls = []
    readers['read'] = lambda *args: calls.append(args)
    with pytest.raises(ValueError):
        results.normalize_selection(descriptor, choose(descriptor, 'u_x_A', **change), granted_selector=grant)
    assert calls == []


def test_changed_hash_missing_verification_and_interleaved_source_change_are_refused(saved):
    _, reference, _, readers = saved
    wrong = dict(reference, result_sha256='0' * 64)
    with pytest.raises(ValueError):
        readers['probe'](wrong)
    descriptor = readers['probe'](reference)
    selected = results.make_result_selection(descriptor, source_id='chosen', selection_request=choose(descriptor, 'u_x_A'))
    original = readers['probe']
    count = 0
    def changing(ref):
        nonlocal count
        value = original(ref)
        count += 1
        if count > 1:
            value['verified_storage_ref']['revision_sha256'] = '0' * 64
        return value
    readers['probe'] = changing
    with pytest.raises(ValueError, match='changed during'):
        results.read_selected_result(reference, selected['selector'], readers=readers, read_limits=results.READ_LIMITS)


def test_packed_candidate_series_slices_before_tolist_and_does_not_open_unselected_settings(tmp_path, monkeypatch):
    folder = tmp_path / 'result'
    curve = {'kind': 'series', 'value': list(range(20000)), 'unit': 'N',
             'axes': [{'name': 'time', 'unit': 's', 'values': list(range(20000))}]}
    payload = {'variables': [], 'candidates': [{'candidate_id': 'Cfirst', 'values': {},
        'responses': {'force': curve, 'unselected': {**curve, 'value': list(range(30000))}},
        'settings': {'private': list(range(40000))}, 'diagnostics': {'unselected': list(range(50000))},
        'response_reductions': [{'response': 'force', 'kind': 'scalar', 'value': 0, 'reduction': 'min'},
                                {'response': 'force', 'kind': 'scalar', 'value': 19999, 'reduction': 'max'}]}]}
    packed = save_evaluation(payload, folder)
    blocked = {packed['candidates'][0][key]['private' if key == 'settings' else 'unselected']['data_ref']['path']
               for key in ('settings', 'diagnostics')}
    blocked.add(packed['candidates'][0]['responses']['unselected']['value']['data_ref']['path'])
    actual_load, actual_asarray, opened, arrays = np.load, np.asarray, [], []
    class GuardedArray(np.ndarray):
        def tolist(self):
            assert self.size <= 3, 'Unselected series rows were materialized'
            return super().tolist()
    def load(path, **options):
        relative = path.relative_to(folder).as_posix()
        assert relative not in blocked
        opened.append(relative)
        array = actual_load(path, **options)
        arrays.append(array)
        return array.view(GuardedArray)
    monkeypatch.setattr(np, 'load', load)
    monkeypatch.setattr(np, 'asarray', lambda *a, **k: actual_asarray(*a, **k).view(GuardedArray))
    try:
        actual = read_result(folder, selection={'candidate_ids': ['Cfirst'], 'responses': ['force'], 'rows': [100, 103]})
        assert actual['candidates'][0]['responses']['force']['value'] == [100, 101, 102]
        assert opened and blocked.isdisjoint(opened)
    finally:
        for array in arrays:
            mapping = getattr(array, '_mmap', None)
            if mapping is not None:
                mapping.close()
    reduced = read_result(folder, selection={'candidate_ids': ['Cfirst'], 'responses': ['force'], 'reduction_index': 1})
    assert reduced['candidates'][0]['response_reductions'][0]['value'] == 19999


def test_metadata_selection_does_not_return_unselected_physical_catalog(saved):
    _, reference, _, readers = saved
    descriptor = readers['probe'](reference)
    selected = results.make_result_selection(descriptor, source_id='selected', selection_request={
        'metadata_only': True, 'channels': [{'response': 'u_x_A', 'frame_indices': [2]}]})
    value = results.read_selected_result(reference, selected['selector'], readers=readers,
                                         read_limits=results.READ_LIMITS)
    encoded = str(value['payload'])
    assert 'u_x_A' in encoded and 'u_y_B' not in encoded and 'field_z' not in encoded
    assert 'value' not in value['payload']['descriptor']['channels'][0]
    assert value['payload']['descriptor']['channels'][0]['frame_indices'] == [2]


def test_candidate_tool_input_preserves_actual_failure_reason_and_classification(wb, monkeypatch):
    response = {'kind': 'scalar', 'value': 17., 'unit': 'N', 'component': 'Y', 'location': 'support',
                'measure': 'force', 'frame': 'global', 'coordinate_system': 'cartesian', 'association': 'POINTS'}
    payload = {'execution_status': 'SUCCEEDED', 'responses': {}, 'candidates': [
        {'candidate_id': 'Caccepted', 'execution_status': 'SUCCEEDED', 'responses': {'force': response}},
        {'candidate_id': 'Cfailed', 'execution_status': 'FAILED', 'responses': {},
         'failure_reason': 'Contact increment did not converge', 'diagnostics': {'error_type': 'ConvergenceError'}}]}
    _, reference, _, readers = retain_fixture(wb, monkeypatch, payload)
    descriptor = readers['probe'](reference)
    selected = results.make_result_selection(descriptor, source_id='candidates',
        selection_request=choose(descriptor, 'force', row_intervals=[[0, 2]]))
    actual = results.read_selected_result(reference, selected['selector'], readers=readers, read_limits=results.READ_LIMITS)
    returned = actual['payload']['channels'][0]['response']
    assert returned['value'] == [17., None]
    assert returned['failure_reasons'] == [None, 'Contact increment did not converge']
    assert returned['failure_classifications'] == ['SUCCEEDED', 'ConvergenceError']


def test_unsupported_legacy_catalog_preserves_existing_metadata_but_corruption_raises(wb, monkeypatch):
    payload = {'execution_status': 'SUCCEEDED', 'responses': {'old': {
        'kind': 'series', 'value': [1., 2.], 'unit': 'N', 'source_rows': [4, 4],
        'axes': [{'name': 'time', 'unit': 's', 'values': [0., 1.]}]}}}
    import caelab.workbench as module
    monkeypatch.setattr(module, 'evaluate', lambda *a, **k: deepcopy(payload))
    document = wb.document_open(kind='material')
    submitted = command(wb, document, 'material.evaluate')
    finished(wb, submitted['job'])
    document = command(wb, wb.document_read(document['id']), 'document.save')['document']
    metadata = wb.document_result_metadata(document['id'], submitted['job']['id'])
    assert metadata['research_team_descriptor']['status'] == 'UNSUPPORTED_SELECTION'
    assert 'old' in str(metadata['responses'])
    revision = document['runs'][0]['retained_result']['revision']
    path = wb.material_documents._folder(document['id']) / 'revisions' / revision / 'results' / submitted['job']['id'] / 'result.json'
    path.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError):
        wb.document_result_metadata(document['id'], submitted['job']['id'])


def test_actual_expert_update_capture_is_atomic_and_unchanged_legacy_selection_does_not_capture(saved, wb):
    from test_research_team_owner import team_draft, definitions
    _, reference, proof, readers = saved
    owner = wb.discussion_documents
    owner.list_experts = lambda: {'experts': definitions()}
    draft = team_draft(roles=('r0',))
    opened = owner.open(draft=draft)
    selected = results.make_result_selection(readers['probe'](reference), source_id='Sexplicit',
                                             selection_request=choose(readers['probe'](reference), 'u_x_A'))
    candidate = deepcopy(draft)
    candidate['context']['research_team']['assignments'][0]['result_refs'] = [selected]
    wrong = deepcopy(selected); wrong['source_id'] = 'Sbad'; wrong['reference']['result_sha256'] = '0' * 64
    candidate['context']['research_team']['assignments'][0]['result_refs'].append(wrong)
    with pytest.raises(ValueError):
        owner.command(opened['id'], 'expert.update', {'draft': candidate}, session_id=wb.session_id,
                      expected_generation=opened['generation'], command_id='CbadCapture')
    current = owner.read(opened['id'])
    assert current['draft'] == draft and not current['discussion'].get('research_team', {}).get('result_verifications')
    assert not (owner._folder(opened['id']) / 'commands' / 'CbadCapture.json').exists()
    candidate['context']['research_team']['assignments'][0]['result_refs'] = [selected]
    accepted = owner.command(opened['id'], 'expert.update', {'draft': candidate}, session_id=wb.session_id,
        expected_generation=opened['generation'], command_id='CgoodCapture')['document']
    assert canonical_hash(reference) in accepted['discussion']['research_team']['result_verifications']
    legacy = owner._documents[opened['id']]
    legacy['discussion']['research_team']['result_verifications'] = {}
    owner._persist_draft(legacy)
    owner.capture_result_verification = lambda ref: (_ for _ in ()).throw(AssertionError('Editing old selections cannot capture'))
    changed = deepcopy(accepted['draft']); changed['composer']['text'] = 'Keep my authored question edit'
    edited = owner.command(opened['id'], 'expert.update', {'draft': changed}, session_id=wb.session_id,
        expected_generation=accepted['generation'], command_id='ClegacyEdit')['document']
    assert edited['draft'] == changed and edited['discussion']['research_team']['result_verifications'] == {}


def test_lazy_native_item_without_exact_sample_catalog_is_explicitly_unsupported():
    with pytest.raises(results.UnsupportedSelection, match='기존 결과 화면'):
        results.descriptor_from_metadata({'native_channels': {'displacement.X': {
            'unit': 'mm', 'component': 'X', 'selector_template': 'displacement.X@<node_id>'}}})
    described = results.descriptor_from_metadata({'responses': {'native_scalar': {
        'kind': 'scalar', 'value': 2., 'unit': 'N', 'component': 'X', 'measure': 'reaction'}},
        'native_channels': {'unavailable': {'unit': 'Pa'}}})
    assert described['channels'][0]['response'] == 'native_scalar'
    assert described['unsupported_channels'][0]['reason'].endswith('기존 결과 화면에서 확인하세요.')


def test_portable_navigation_is_reused_only_within_one_request_while_asset_and_result_checks_repeat(saved, wb, monkeypatch):
    from caelab import portable_research_owner as portable
    from caelab import research_team_followup as followup
    from caelab.discussion_research_team import empty_state, retain_result_verification
    from caelab.connection_graph_refs import TypedReference
    _, current, proof, readers = saved
    selected = results.make_result_selection(readers['probe'](current), source_id='Soriginal')
    original = {**current, 'document_id': 'Moriginal'}
    proof = {**proof, 'reference': original}
    opened = wb.discussion_documents.open()
    owner = wb.discussion_documents; document = owner._documents[opened['id']]
    document['discussion']['research_team'] = empty_state()
    asset = retain_result_verification(owner, document, proof)
    counts = {'navigation': 0, 'result': 0}
    allowed = [True]
    snapshot = results._owner_snapshot
    def projected(folder, source, typed):
        counts['navigation'] += 1
        assert typed.value == original
        return TypedReference(typed.path, typed.role, typed.form,
                              current if allowed[0] else {**current, 'document_id': 'Mmissing'})
    def checked_snapshot(*args):
        counts['result'] += 1
        return snapshot(*args)
    monkeypatch.setattr(portable, 'historical_reference', projected)
    monkeypatch.setattr(results, '_owner_snapshot', checked_snapshot)
    context = followup.build_transfer_context(wb, document)
    row = {'kind': 'result', 'exact_ref': original, 'selector': selected['selector']}
    assert context['check_local_dependency'](row) is True
    assert context['check_local_dependency'](row) is True
    assert counts == {'navigation': 1, 'result': 2}
    path = owner._folder(document['id']) / asset['path']
    before = path.read_bytes()
    path.write_bytes(b'{}')
    with pytest.raises(ValueError, match='바뀌었습니다'):
        context['check_local_dependency'](row)
    path.write_bytes(before)  # Restore only this manufactured test asset.
    allowed[0] = False
    fresh = followup.build_transfer_context(wb, document)
    with pytest.raises((ValueError, FileNotFoundError)):
        fresh['check_local_dependency'](row)
    assert counts == {'navigation': 2, 'result': 3}
