"""Bounded shared-workflow edges; no solver, native process or inference."""
from copy import deepcopy

from caelab.evaluation_definition import default_draft, document_reference
from caelab.storage import canonical_hash, save_json
from caelab.workbench import Workbench


def test_full_length_domain_title_can_open_unexecuted_plan(tmp_path):
    wb = Workbench(tmp_path)
    try:
        material = wb.document_open()
        material = wb.document_command(material['id'], 'document.save', {},
            session_id=material['session_id'], expected_generation=material['generation'])['document']
        draft = default_draft()
        draft['stages'] = [{'id': 'StageA', 'name': 'Saved actual Material inputs', 'source': document_reference(material)}]
        definition = wb.document_open(kind='evaluation', title='q' * 160, draft=draft)
        result = wb.desktop.domain_plan(definition['id'], session_id=definition['session_id'],
            expected_generation=definition['generation'], command_id='Clongtitle')
        assert result['executed'] is False
        assert result['document']['kind'] == 'numerical'
        assert len(result['document']['title']) <= 160
        assert result['document']['draft']['request']['purpose'] == definition['title']
        assert not wb.manager.list()
    finally:
        assert wb.shutdown()['joined']


def test_reopened_interrupted_job_progress_does_not_claim_live_stage_execution(tmp_path):
    wb = Workbench(tmp_path)
    definition = wb.document_open(kind='evaluation')
    job_id = 'Jinterruptedstage'
    run = {'job_id': job_id, 'input_revision': definition['input_revision'],
           'input_sha256': canonical_hash(definition['draft']), 'operation': 'evaluation.coupled', 'arguments': {}}
    internal = wb.evaluation_documents._documents[definition['id']]
    internal['runs'].append(deepcopy(run))
    wb.evaluation_documents._persist_draft(internal)
    save_json(wb.root / 'jobs' / (job_id + '.json'), {'id': job_id, 'job_id': job_id,
        'state': 'RUNNING', 'status': 'RUNNING', 'phase': 'CALCULATING', 'operation': 'evaluation.coupled',
        'arguments': {}, 'result_refs': [], 'workspace_id': 'local'})
    original_progress = {'phase': 'STAGE_RUNNING', 'execution_status': 'FAILED',
        'stages': [{'stage_id': 'StageA', 'attempt_id': 'Aunfinished', 'state': 'RUNNING',
                    'iteration': 0, 'result_directory': 'stages/i0000-StageA'}], 'iterations': [], 'transfers': []}
    save_json(wb.root / 'results' / job_id / 'progress.json', original_progress)
    assert wb.shutdown()['joined']
    wb = Workbench(tmp_path)
    try:
        assert wb.manager.status(job_id)['state'] == 'INTERRUPTED'
        progress = wb.evaluation_progress(definition['id'], job_id)
        assert progress['phase'] not in {'STAGE_RUNNING', 'ITERATING'}
        assert progress.get('job_state', progress.get('execution_status')) == 'INTERRUPTED'
        assert len(progress['stages']) == 1
        assert not (wb.root / 'results' / job_id / 'result.json').exists()
        assert len(wb.manager.list()) == 1  # No replay/submission.
    finally:
        assert wb.shutdown()['joined']


def test_transfer_rejected_before_dispatch_is_not_counted_as_executed_stage(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from caelab import backends
    from caelab.evaluation_definition import compile_definition, execute
    from caelab.material_document import default_draft as material_draft

    port = {'kind': 'field', 'unit': 'K', 'quantity': 'temperature', 'association': 'POINTS',
            'component': 'scalar', 'location': 'node', 'measure': 'absolute', 'frame': 'laboratory',
            'coordinate_units': 'm', 'coordinate_frame': 'laboratory'}
    def reject(settings, name, response):
        raise ValueError('Controlled retained mesh does not match the downstream declared mesh')
    adapter = SimpleNamespace(describe_ports=lambda settings: {'inputs': {'temperature': {
        **port, 'transfer': 'exact_same_mesh', 'required': False}}, 'outputs': {'temperature': port}}, bind_port=reject)
    monkeypatch.setattr(backends, 'get_backend', lambda backend: adapter)
    draft = default_draft()
    snapshots = {}
    for stage_id, document_id in [('StageA', 'Ma'), ('StageB', 'Mb')]:
        snapshot = {'id': document_id, 'kind': 'material', 'draft': material_draft(),
                    'input_revision': 'I' + stage_id, 'saved_revision': 'R' + stage_id, 'dirty': False}
        snapshots[stage_id] = snapshot
        draft['stages'].append({'id': stage_id, 'name': stage_id, 'source': document_reference(snapshot)})
    draft['transfers'] = [{'id': 'TransferA', 'from_stage': 'StageA', 'output': 'temperature',
        'to_stage': 'StageB', 'input': 'temperature', 'mapping': 'exact_same_mesh', 'lag': 0}]
    compiled = compile_definition(draft, snapshots)
    calls = []
    def controlled_stage(model, output):
        calls.append(output.name)
        return {'execution_status': 'SUCCEEDED', 'responses': {'temperature': {
            **port, 'value': [300.0], 'mesh_sha256': 'a' * 64}}}
    result = execute(compiled, tmp_path / 'evaluation', controlled_stage)
    assert result['execution_status'] == 'FAILED'
    assert len(calls) == 1
    assert [row['state'] for row in result['stages']] == ['SUCCEEDED', 'FAILED']
    assert result['stage_execution_count'] == len(calls)
    assert (tmp_path / 'evaluation' / 'stages' / 'i0000-StageA' / 'result.json').is_file()
    assert not (tmp_path / 'evaluation' / 'stages' / 'i0000-StageB').exists()
