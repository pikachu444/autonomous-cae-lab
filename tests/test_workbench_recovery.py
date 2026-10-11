"""Integration regressions for real candidate dispatch and local file inputs."""
import os
import time
import sys

import numpy as np
import pytest

from caelab.evaluation import run
from caelab.numerical import optimize, fit_model
from caelab.workbench import Workbench


def test_expert_submission_uses_actual_tool_contract_and_enforces_uq_budget(tmp_path, monkeypatch):
    from copy import deepcopy
    from jsonschema import Draft202012Validator
    from caelab import backends
    from caelab.assist.experts import _TOOL_INPUTS
    from test_workbench_assist import mock_generator, runtime_for

    monkeypatch.setattr(backends, '_registry', dict(backends._registry))
    backend = 'test.uq.request.contract'
    def evaluator(values, settings):
        pytest.fail('This request-routing test must not evaluate a numerical candidate')
    backends.register_backend(backend, lambda: evaluator, roles=('prepared',))
    bench=Workbench(tmp_path/'workspace')
    submissions=[]
    def submit(operation, args, **kwargs):
        submissions.append((operation, deepcopy(args), deepcopy(kwargs)))
        return {'id': 'Jaccepted', 'state': 'QUEUED'}
    monkeypatch.setattr(bench,'submit',submit)
    schema = Draft202012Validator(_TOOL_INPUTS['calculations.submit'])
    base = {'purpose': 'TEST ONLY request-budget routing', 'operation': 'uq',
        'inputs': {'backend': backend, 'settings': {},
            'variables': [{'id': 'x', 'unit': '1', 'lower': 0, 'upper': 1}],
            'distributions': {'x': {'distribution': 'uniform', 'unit': '1', 'lower': 0, 'upper': 1}},
            'source': {'origin': 'SYNTHETIC', 'reference': 'TEST ONLY request contract'},
            'independence': 'INDEPENDENT_USER_DECLARED'},
        'budget': {'evaluations': 2}}
    try:
        too_many = deepcopy(base)
        too_many['inputs']['count'], too_many['budget']['evaluations'] = 100, 1
        schema.validate(too_many)  # Not an accidental missing-purpose/inputs rejection.
        with pytest.raises(ValueError, match='sample count exceeds the evaluation budget'):
            bench._proposed_submit(too_many)
        defaults = deepcopy(base)
        defaults['budget']['evaluations'] = 16
        schema.validate(defaults)  # Omitted UQ count means the existing default 128.
        with pytest.raises(ValueError, match='Sampling exceeds the allowed evaluation budget'):
            bench._proposed_submit(defaults)
        assert not submissions

        accepted = deepcopy(base)
        accepted['inputs']['count'] = 2
        accepted['resources'] = {'threads': 1}
        schema.validate(accepted)
        missing_purpose = deepcopy(accepted)
        del missing_purpose['purpose']
        assert list(schema.iter_errors(missing_purpose))
        callback_requests = []
        def callback(request):
            schema.validate(request)
            callback_requests.append(deepcopy(request))
            return bench._proposed_submit(request)
        generator = mock_generator([('calculations_submit', accepted),
                                    {'answer': 'The managed request was submitted.', 'sources': []}])
        _, runtime = runtime_for(tmp_path/'expert', generator, tools=['calculations.submit'],
                                 callbacks={'calculations.submit': callback})
        result = runtime.ask('materials', 'Submit the selected test-only UQ request', {
            'calculation_scope': {'allow_execution': True, 'max_evaluations': 2,
                'backends': [backend], 'variables': {'x': [0, 1]}, 'resources': {'threads': 1}}})
        assert result['status'] == 'ANSWERED', result
        assert callback_requests == [accepted] and len(submissions) == 1
        assert submissions[0][0] == 'uq' and submissions[0][1]['execution']['max_evaluations'] == 2
        assert submissions[0][2] == {'resources': {'threads': 1}}
        assert result['tool_events'][0]['summary']['request'] == accepted
        assert result['budget_used']['evaluations_requested'] == 2

        # Exporting an existing candidate definition is supported and does not
        # pretend to evaluate it. Keep its complete operation-specific inputs.
        batch = {'purpose': 'Export existing test-only candidate definitions', 'operation': 'batch_export',
            'inputs': {'variables': base['inputs']['variables'], 'candidates': [{'x': 0.2}, {'x': 0.8}],
                       'case_id': 'TEST_ONLY'}, 'budget': {'evaluations': 1}}
        schema.validate(batch)
        bench._proposed_submit(batch)
        assert submissions[-1] == ('batch_export', batch['inputs'], {'resources': None})
    finally:
        bench.shutdown()


def test_expert_turn_cannot_starve_its_child_with_one_solver_slot(tmp_path):
    from caelab.jobs import JobManager
    def execute(operation,arguments,identifier):
        if operation=='experts.ask':
            child=manager.submit('evaluate',{})
            deadline=time.monotonic()+3
            while manager.status(child['id'])['state']=='QUEUED' and time.monotonic()<deadline:
                time.sleep(.01)
            while not manager.status(child['id'])['result_refs'] and time.monotonic()<deadline:
                time.sleep(.01)
            return manager.result(child['id'])
        return {'value':42}
    manager=JobManager(tmp_path,execute,workers=1,cpu_budget=1)
    try:
        job=manager.submit('experts.ask',{})
        deadline=time.monotonic()+5
        while not manager.status(job['id'])['result_refs'] and time.monotonic()<deadline:
            time.sleep(.01)
        assert manager.result(job['id'])['value']==42
    finally:
        assert manager.shutdown()['joined']


def timed_candidate(values, settings):
    if settings.get('worker_readiness') and values['x'] != .5:
        from pathlib import Path
        directory=Path(settings['worker_readiness'])
        (directory/str(os.getpid())).touch()
        deadline=time.monotonic()+30
        while len(list(directory.iterdir()))<2:
            if time.monotonic()>deadline:
                raise RuntimeError('Both requested worker processes did not start')
            time.sleep(.01)
    start=time.monotonic_ns()
    time.sleep(.12)
    x=values['x']
    scalar=lambda value:{'kind':'scalar','unit':'1','value':value}
    return {'execution_status':'SUCCEEDED','responses':{
        'cost':scalar((x-.3)**2),'limit':scalar(x)},
        'diagnostics':{'pid':os.getpid(),'start_ns':start,'end_ns':time.monotonic_ns()}}


def test_de_dispatches_constraints_and_objective_in_overlapping_workers(tmp_path):
    variables=[{'id':'x','unit':'1','lower':0.,'upper':1.,'value':.5}]
    objective={'response':'cost','unit':'1'}
    constraints=[{'response':'limit','unit':'1','operator':'<=','limit':.8}]
    common=dict(constraints=constraints,seed=41,options={'max_generations':2,'population_size':6})
    serial=optimize(timed_candidate,variables,objective,**common)
    # Spawn startup is uneven under suite load; synchronize readiness while
    # still requiring two actual PIDs and overlapping candidate intervals.
    parallel=optimize(timed_candidate,variables,objective,settings={'worker_readiness':str(tmp_path)},
                      execution={'mode':'process','workers':2},**common)
    a,b=serial['candidates'],parallel['candidates']
    assert [r['values'] for r in b]==[r['values'] for r in a]
    assert [r['objective'] for r in b]==[r['objective'] for r in a]
    assert [r['constraint_residuals'] for r in b]==[r['constraint_residuals'] for r in a]
    assert parallel['best']['values']==serial['best']['values']
    intervals=[r['diagnostics'] for r in b]
    assert len({d['pid'] for d in intervals})==2
    assert any(a['pid']!=b['pid'] and max(a['start_ns'],b['start_ns'])<min(a['end_ns'],b['end_ns'])
               for a in intervals for b in intervals)
    assert parallel['timing']['model_calls']==len(b)
    assert parallel['algorithm']['vectorized'] is True


def test_de_budget_retains_dispatched_candidates_and_no_invented_feedback():
    result=optimize(timed_candidate,[{'id':'x','unit':'1','lower':0.,'upper':1.}],
        {'response':'cost','unit':'1'},options={'max_generations':2,'population_size':6},
        execution={'mode':'process','workers':2,'max_evaluations':3})
    assert result['termination_reason']=='EVALUATION_BUDGET_EXHAUSTED'
    assert result['timing']['model_calls']<=3
    assert all(row['objective'] is None for row in result['candidates'] if row['execution_status']=='REJECTED')


def test_unicode_streamed_snapshot_and_source_scope(tmp_path):
    source=tmp_path/'승인 폴더'; source.mkdir()
    payload=('시간,하중\n0,1\n'+'1,2\n'*3000000).encode()
    path=source/'한글 큰 결과.csv'; path.write_bytes(payload)
    bench=Workbench(tmp_path/'workspace',configuration={'input_roots':{'results':str(source)}})
    try:
        receipt=bench.register_local_input('results',path.name)
        assert receipt['name']==path.name and receipt['bytes']==len(payload)
        assert bench.input_path(receipt['id']).read_bytes()==payload
        assert len(bench.input_preview(receipt['id'])['text'])==16384
        assert bench.upload('시험 곡선.csv',b't,x\n0,1\n')['name']=='시험 곡선.csv'
        with pytest.raises(ValueError): bench.register_local_input('results','../outside.csv')
        with pytest.raises(ValueError): bench.upload('folder\\bad.csv',b'a')
        with pytest.raises(ValueError): bench.register_local_input('not-approved',path.name)
        assert bench.local_inputs('results')['entries'][0]['relative']==path.name
    finally:
        bench.shutdown()


def test_native_style_deck_fixed_width_and_unchanged_include(tmp_path):
    from caelab.adapters.external_files import ExternalFilesAdapter
    deck=tmp_path/'source.k'
    original=b'$ native $ comments\r\n*PARAMETER\r\n         1        20\r\n*INCLUDE\r\npart.inc\r\n'
    deck.write_bytes(original)
    include=tmp_path/'part.inc'; include.write_bytes(b'$ unchanged\r\n*END\r\n')
    config={'variables':{'load':{'lower':0,'upper':100,'unit':'N'}},
        'templates':[{'source':str(deck),'destination':'model.k','mode':'fixed_columns',
                       'replacements':[{'variable':'load','line':3,'start':10,'stop':20,'expected':'        20'}]}],
        'files':[{'source':str(include),'destination':'part.inc'}],
        'command':[sys.executable,'-c',
            "from pathlib import Path; v=float(Path('model.k').read_text().splitlines()[2][10:20]); "
            "Path('response.csv').write_text('t,f\\n0,0\\n1,'+str(v*2)+'\\n')"],
        'result':{'path':'response.csv','columns':{'force':{'column':'f','unit':'N','component':'y',
            'location':'support','axis':{'column':'t','name':'time','unit':'s'}}}}}
    result=run(ExternalFilesAdapter('test.deck',config),{'values':{'load':37}},output=tmp_path/'candidate')
    assert result['responses']['force']['value'].tolist()==[0,74]
    assert (tmp_path/'candidate/part.inc').read_bytes()==include.read_bytes()
    assert (tmp_path/'candidate/model.k').read_bytes()==original.replace(b'        20',b'        37')
    assert deck.read_bytes()==original
    config['templates'][0]['replacements'][0]['expected']='wrong'
    with pytest.raises(ValueError,match='expected bytes'):
        run(ExternalFilesAdapter('test.deck',config),{'values':{'load':37}},output=tmp_path/'rejected')
    assert not (tmp_path/'rejected/external.execution.json').exists()
def test_native_selection_restores_packed_outcome_identity(tmp_path, monkeypatch):
    from caelab.evaluation import save_evaluation, read_result
    from caelab.adapters import native_responses
    from hashlib import sha256
    output=tmp_path/'native'
    output.mkdir()
    outcome={'times':[0.,1.,2.], 'solver_status':'COMPLETED'}
    captured=b'TEST ONLY retained reader source; no native execution\n'
    (output/'parsed_history.json').write_bytes(captured)
    source={'backend':'explicit.openradioss', 'artifact':'parsed_history.json',
            'sha256':sha256(captured).hexdigest()}
    def selected(backend, restored, folder, name):
        assert restored==outcome and folder==output
        return {'kind':'series','value':[0.,2.,4.],'unit':'m',
                'axes':[{'name':'time','unit':'s','values':[0.,1.,2.]}], 'source':source}
    monkeypatch.setattr(native_responses,'read_native_response',selected)
    save_evaluation({'execution_status':'SUCCEEDED','responses':{},
                     'native_result':{'backend':'explicit.openradioss','directory':'native'},
                     'native_channels':{'displacement':{'source':source}},
                     'diagnostics':{'native_outcome':outcome}},tmp_path,existing=True)
    result=read_result(tmp_path,selection={'responses':['displacement'],'rows':[1,3]})
    assert result['responses']['displacement']['value']==[2.,4.]
    assert 'data_ref' in result['diagnostics']['native_outcome']['times']


def test_selected_rows_do_not_expand_unrelated_large_arrays(tmp_path):
    from caelab.evaluation import save_evaluation, read_result
    import numpy as np
    values=np.arange(300001,dtype=float)
    save_evaluation({'responses':{'x':{'kind':'series','unit':'m','value':values,
        'axes':[{'name':'time','unit':'s','values':values}]}},
        'diagnostics':{'native_field':values}},tmp_path,existing=True)
    result=read_result(tmp_path,selection={'responses':['x'],'rows':[20,25]})
    assert result['responses']['x']['value']==[20,21,22,23,24]
    assert 'data_ref' in result['diagnostics']['native_field']


def test_metadata_restores_native_selector_catalog_without_response_arrays(tmp_path):
    from caelab.evaluation import save_evaluation, read_result
    save_evaluation({'responses':{},'native_channels':{'u':{'node_ids':[0,544],
        'coordinates':[[0.,0.],[1.,.5]]}},'diagnostics':{'field':[1.,2.,3.]}},tmp_path,existing=True)
    result=read_result(tmp_path,selection={'metadata_only':True})
    assert result['native_channels']['u']['node_ids']==[0,544]
    assert result['native_channels']['u']['coordinates']==[[0.,0.],[1.,.5]]
    assert 'data_ref' in result['diagnostics']['field']


def test_fit_comparison_aliases_read_bounded_saved_curves(tmp_path):
    from caelab.evaluation import save_evaluation, read_result
    observation={'kind':'series','unit':'m','value':[1.,2.,3.,4.],
                 'axes':[{'name':'time','unit':'s','values':[0.,1.,2.,3.]}]}
    save_evaluation({'observation':observation,'prediction':[2.,3.,4.,5.],
        'mask':[True,True,False,True],
        'curves':[{'experiment_id':'axial','role':'holdout','observations':observation,
                   'prediction':[3.,4.,5.,6.]}]},tmp_path,existing=True)
    catalog=read_result(tmp_path,selection={'metadata_only':True})
    assert set(catalog['responses'])=={'observation','prediction','holdout: axial observed','holdout: axial predicted'}
    chosen=read_result(tmp_path,selection={'responses':['prediction','holdout: axial predicted'],'rows':[1,3]})
    assert chosen['responses']['prediction']['value']==[3.,4.]
    assert chosen['responses']['prediction']['mask']==[True,False]
    assert chosen['responses']['holdout: axial predicted']['value']==[4.,5.]
    assert 'data_ref' in chosen['observation']['value']
    assert chosen['responses']['prediction']['source']['status']=='UNKNOWN_LEGACY_PREDICTION_PROVENANCE'


def test_comparison_prediction_keeps_own_source_when_read_as_curve(tmp_path):
    from caelab.numerical import compare_curves
    from caelab.evaluation import save_evaluation, read_result
    observation={'kind':'series','unit':'m','component':'X','location':'mass','reduction':'none','value':[1.,2.],
                 'source':{'sha256':'observed'},'axes':[{'name':'time','unit':'s','values':[0.,1.]}]}
    prediction={**observation,'value':[2.,4.],'source':{'sha256':'predicted'},'model_conditions':{'mass_kg':2.}}
    save_evaluation(compare_curves(prediction,observation),tmp_path,existing=True)
    selected=read_result(tmp_path,selection={'responses':['prediction'],'rows':[0,1]})['responses']['prediction']
    assert selected['value']==[2.]
    assert selected['source']=={'sha256':'predicted'}
    assert selected['model_conditions']=={'mass_kg':2.}
    assert selected['axes'][0]['values']==[0.]
