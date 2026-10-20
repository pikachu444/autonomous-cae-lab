"""C2 fixtures: real Workbench/owners/JobManager, explicitly synthetic P=mu*t.

No installed FELUPE registration is replaced. The small CSV reduces storage and
optimizer work; the immutable 138-sample Windows packet is tested separately.
"""
from copy import deepcopy
import time
from pathlib import Path
from caelab.backends import register_backend
from caelab.workbench import Workbench
from caelab.jobs import TERMINAL
from caelab.storage import canonical_hash
from caelab.material_document import default_draft
from caelab.numerical_document import from_material_document, request_draft
from caelab.material_test import measured_protocol
from caelab.data_material_service import DataMaterialService
from .helpers import command, fixture_mapping, recipe

BACKEND = 'test.c2.synthetic'

class SyntheticPoint:
    """Test-only arithmetic, never an engineering law or FELUPE execution."""
    version = 'explicit-C2-test-fixture-1'
    calls = []
    outcome = 'SUCCEEDED'
    def __call__(self, values, settings):
        type(self).calls.append({'values': deepcopy(values), 'settings': deepcopy(settings)})
        status = type(self).outcome
        if status == 'CANCELLED':
            from caelab.execution_control import ExecutionCancelled
            raise ExecutionCancelled('injected explicit test cancellation')
        if status != 'SUCCEEDED':
            return {'execution_status': status, 'responses': {}, 'diagnostics': {'reason': 'injected test outcome'}}
        return {'execution_status': 'SUCCEEDED', 'responses': {'stress_xx': {
            'kind': 'series', 'unit': 'MPa', 'component': 'xx', 'measure': 'first_Piola',
            'frame': 'material_cartesian', 'location': 'material_point', 'reduction': 'none',
            'value': [values.get('mu', 7.) * t for t in settings['time']],
            'axes': [{'name': 'time', 'unit': 's', 'values': list(settings['time'])}]}},
            'diagnostics': {'execution_kind': 'SYNTHETIC_TEST_ONLY; NOT_FELUPE'}}

def make_workbench(path, monkeypatch):
    from caelab import backends
    monkeypatch.setattr(backends, '_registry', dict(backends._registry))
    register_backend(BACKEND, SyntheticPoint, roles=('model',), replace=True)
    return Workbench(path, configuration={'workers': 1, 'cpu_budget': 1})

def wait(w, job_id, *, expected='SUCCEEDED'):
    # Wait for this existing manager's exact submitted future; no alternate
    # scheduler, busy deepcopy of multi-MiB arguments, or hand-authored receipt.
    w.manager._futures[job_id].result(timeout=45)
    job = w.manager.status(job_id)
    assert job['state'] in TERMINAL, job.get('error')
    if expected is not None:
        assert job['state'] == expected, job.get('error')
    return job

def make_processed_plan(w):
    rows = ['time_s,force_N,extension_mm,temperature_C']
    for i in range(9):
        t = i / 10
        force = "nan" if i == 4 else format(140*t, ".12g")
        rows.append(f'{t:.1f},{force},{.05*t:.12g},20')
    receipt = w.upload('합성 시험 공백.csv', ('\n'.join(rows)+'\n').encode('utf-8'))
    mapping = fixture_mapping()
    for name, channel in mapping['columns'].items():
        channel['row_selection'] = {'display_hidden_rows': [3]}
        if name == 'force':
            channel['row_selection'].update(exclude_rows=[5], quality_rows=[5],
                reasons={'5': 'dropout'}, quality_reasons={'5': 'instrument dropout'})
    d = w.document_open(kind='data', draft={'data_id': receipt['id'], 'mapping': mapping})
    res = command(w.data_documents, d, 'data.import'); wait(w, res['job']['id'])
    d = w.document_read(d['id']); run = d['runs'][-1]
    source = {'document_id': d['id'], 'job_id': run['job_id'], 'input_revision': run['input_revision'], 'input_sha256': run['input_sha256']}
    r = recipe()
    for original, out in [('P11', 'P_grid'), ('e', 'e_grid')]:
        r['operations'].append({'id': out, 'operation': 'resample', 'input': original, 'output': out,
            'settings': {'method': 'linear', 'max_gap': .11, 'range': [0., .8], 'step': .05}})
    draft = deepcopy(d['draft']); draft['processing'] = {'source': source, 'recipe': r}
    d = command(w.data_documents, d, 'data.update', {'draft': draft})['document']
    pv = w.data_documents.processing_preview(d['id'])
    applied = command(w.data_documents, d, 'data.processing.apply', {'preview_sha256': pv['preview_sha256']})
    d = applied['document']; rev = applied['processing']['id']
    processed = w.data_documents.processing_result(d['id'], rev, selection=['P_grid', 'e_grid'])
    kin = {'channel': 'e_grid', 'kind': 'engineering_strain', 'lateral_22': 1., 'lateral_33': 1.}
    material = default_draft(); material['settings'].update(model='neo_hooke', parameters={'mu': 7., 'lmbda': 6.})
    material['settings'] = measured_protocol(material['settings'], processed, kin)
    m = w.document_open(kind='material', draft=material)
    draft = from_material_document(m)
    for variable in draft['variables']:
        variable['free'] = variable['id'] == 'mu'
        if variable['id'] == 'mu': variable.update(lower=.1, upper=10.)
    draft['experiments'] = [{'id': 'Emeasured', 'role': 'fit', 'source': {**source, 'response': 'P_grid', 'processing_revision': rev},
        'response': 'stress_xx', 'settings': deepcopy(material['settings']), 'weight': 1., 'scale': 1., 'kinematics': kin}]
    n = w.document_open(kind='numerical', draft=draft)
    service = DataMaterialService(w)
    proposal = service.sample_policy_preview(d['id'], rev, 'P_grid')
    entries = deepcopy(proposal['entries'])
    channel = processed['responses']['P_grid']['processing_channel']
    for sample, t in zip(channel['samples'], channel['axis']['values']):
        entries[sample['sample_id']] = {'included': True, 'role': 'fit' if t < .4 else 'holdout', 'weight': 2. if abs(t-.1)<1e-12 else 1.}
    n = service.sample_policy_adopt(n['id'], 'Emeasured', proposal, session_id=n['session_id'],
        expected_generation=n['generation'], command_id='Cactual_sample_policy', entries=entries)['document']
    canonical_args = w.numerical_documents.job_arguments(n['draft'])
    assert canonical_args['frozen_inclusion']['format'] == 'frozen-fit-inclusion.v1'
    assert [sum(e['mask']) for e in canonical_args['experiments']] == [7, 7]
    # Explicit test adapter change is outside observations/settings/policy. It
    # is visible in the same owner's next editable request revision; it is not
    # a registered material.felupe replacement or hidden oracle fallback.
    args = deepcopy(canonical_args); args['backend'] = BACKEND
    args['options'] = {'max_nfev': 2, 'detail_retention': {'candidate_limit': 0, 'byte_limit': 0}}
    args['execution']['max_evaluations'] = 8
    request = {'purpose': 'C2 canonical contract synthetic P=mu*t; NOT FELUPE', 'operation': 'fit',
               'inputs': args, 'budget': {'evaluations': 8}}
    n = command(w.numerical_documents, n, 'numerical.update', {'draft': request_draft(request)})['document']
    assert not n['diagnostics'], n['diagnostics']
    return {'data': d, 'material': m, 'plan': n, 'args': args, 'processed': processed,
            'processing_revision': rev, 'proposal': proposal, 'uploaded': receipt}

def fit_and_detail(w, bundle, *, detail=True):
    from caelab.numerical_candidate_detail import read_candidate_detail
    n = bundle['plan']
    submitted = command(w.numerical_documents, n, 'numerical.run'); job = wait(w, submitted['job']['id'])
    n = w.document_read(n['id']); result = w.numerical_documents.result(n['id'], job['id'])
    cid = next(r['candidate_id'] for r in result['candidates'] if r['execution_status'] == 'SUCCEEDED')
    before = read_candidate_detail(w.numerical_documents, n['id'], job['id'], cid)
    assert before['can_detail_eval'] and len(before['missing_experiments']) == 2
    output = {**bundle, 'plan': n, 'fit_job': job, 'fit_result': result, 'candidate_id': cid,
              'original_view': before, 'source': before['source']}
    if detail:
        submitted = command(w.numerical_documents, n, 'numerical.detail_eval', {'source': before['source'], 'candidate_id': cid})
        attempt = wait(w, submitted['job']['id']); n = w.document_read(n['id'])
        view = read_candidate_detail(w.numerical_documents, n['id'], job['id'], cid, attempt_job_id=attempt['id'])
        assert not view['missing_experiments']
        output.update(plan=n, attempt=attempt, view=view)
    return output
