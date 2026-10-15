"""Public C2 owner fixture adapted ONLY for FN05 regression and public dispatch.
Source: current packet data-c2/tests/data_material_delivery/c2_fixtures.py
and helpers.py (source hashes in C1 verification manifest).
The policy/compiler/consumer/transport/evidence implementations are imported
from the product unchanged. P=mu*t is synthetic, not FELUPE or a native solver.
"""
from copy import deepcopy
import uuid
from caelab.jobs import TERMINAL
from caelab.material_document import default_draft
from caelab.numerical_document import from_material_document, request_draft
from caelab.material_test import measured_protocol
from caelab.data_material_service import DataMaterialService


BACKEND = 'test.fn05.c1.synthetic'

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
    proposal = service.dispatch('data.sample_policy.preview', {
        'document_id': d['id'], 'processing_revision': rev, 'response': 'P_grid'})
    entries = deepcopy(proposal['entries'])
    channel = processed['responses']['P_grid']['processing_channel']
    for sample, t in zip(channel['samples'], channel['axis']['values']):
        entries[sample['sample_id']] = {'included': True, 'role': 'fit' if t < .4 else 'holdout', 'weight': 2. if abs(t-.1)<1e-12 else 1.}
    n = service.dispatch('data.sample_policy.adopt', {
        'document_id': n['id'], 'experiment_id': 'Emeasured', 'proposal': proposal,
        'session_id': n['session_id'], 'expected_generation': n['generation'],
        'command_id': 'Cactual_sample_policy', 'entries': entries})['document']
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


def command(owner,document,operation,args=None,cid=None):
    return owner.command(document['id'], operation,args or {},session_id=document['session_id'],
       expected_generation=document['generation'],command_id=cid or 'C'+uuid.uuid4().hex)


def fixture_mapping(variant='A'):
    axis={'column':'time_s' if variant=='A' else 'time_ms','name':'time','unit':'s' if variant=='A' else 'ms'}
    def channel(column,unit,measure,drop=False):
        c={'column':column,'unit':unit,'component':'xx','measure':measure,'frame':'material_cartesian',
           'location':'material_point','reduction':'none','axis':deepcopy(axis)}
        c['row_selection']={'display_hidden_rows':[60]}
        if drop:
            c['row_selection'].update(exclude_rows=[82],quality_rows=[82],
                reasons={'82':'dropout'},quality_reasons={'82':'instrument dropout'})
        return c
    return {'delimiter':',','columns':{
        'force':channel('force_N' if variant=='A' else 'load_kN','N' if variant=='A' else 'kN','force',True),
        'extension':channel('extension_mm' if variant=='A' else 'extension_um','mm' if variant=='A' else 'um','gauge_extension'),
        'temperature':channel('temperature_C' if variant=='A' else 'temperature_K','C' if variant=='A' else 'K','absolute_temperature')}}


def recipe(variant='A'):
    operations=[]
    def op(id,kind,input,settings,output):
        operations.append({'id':id,'operation':kind,'input':input,'settings':settings,'output':output})
    if variant=='B':
        for name in ('extension','force','temperature'):
            op('axis_'+name,'convert_axis',name,{'quantity':'time','to_unit':'s'},name+'_s')
    suffix='_s' if variant=='B' else ''
    op('strain','engineering_strain','extension'+suffix,{'L0':50.,'length_unit':'mm','measurement':'extensometer_gauge_extension'},'e')
    op('stretch','stretch','e',{},'lambda')
    op('stress','nominal_stress','force'+suffix,{'A0':20.,'area_unit':'mm2'},'P11')
    op('temperature','convert','temperature'+suffix,{'quantity':'absolute_temperature','to_unit':'K'},'T_K')
    return {'version':1,'operations':operations}
