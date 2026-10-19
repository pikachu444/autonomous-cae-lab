"""Retained-plan bridges reuse real cheap numerical engines; no solver fit reruns."""
from copy import deepcopy
import json

import pytest

from caelab import numerical
from caelab.material_document import default_draft as material_draft
from caelab.numerical_document import (NumericalDocuments, adopted_draft, diagnostics,
                                      from_material_document, material_request, request_draft)
from caelab.research_operations import (result_reference, resolve_request_inputs, surrogate_result,
                                       validate_result_reference, validate_result_refs)
from caelab.storage import canonical_hash


@pytest.fixture
def qt_plan_window():
    """Real editable Qt controls, with no service job or native solver."""
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    pytest.importorskip('PySide6')
    pytest.importorskip('matplotlib')
    from PySide6.QtWidgets import QApplication
    from apps.research.numerical_window import NumericalWindow
    app = QApplication.instance() or QApplication([])
    window = NumericalWindow(None, auto_open=False, poll_interval=0)
    yield app, window
    window._allow_close = True
    window.close()


def show_plan(window, draft, *, result=None):
    document = {'id':'Nplan', 'kind':'numerical', 'title':'Visible operation',
                'session_id':'Ssession', 'generation':3, 'input_revision':'Iplan',
                'draft':deepcopy(draft), 'diagnostics':diagnostics(draft), 'dirty':False,
                'runs':[]}
    if result is not None:
        document['runs'] = [{'job_id':'Jactual', 'draft':deepcopy(draft),
                             'input_revision':'Iplan', 'input_sha256':'a'*64,
                             'input_generation':3, 'is_current_input':True,
                             'retention_complete':True, 'retained_state':'SUCCEEDED',
                             'retained_result':{'revision':'Rsaved'}}]
        window._result_cache['Jactual'] = deepcopy(result)
    window._show_document(document)
    return document


def option_item(window, path):
    from PySide6.QtCore import Qt
    pending = [window.operation_options.inputs.topLevelItem(0)]
    while pending:
        item = pending.pop()
        if item.data(0, Qt.ItemDataRole.UserRole)['path'] == path:
            return item
        pending.extend(item.child(index) for index in range(item.childCount()))
    raise AssertionError('Visible operation field missing: ' + str(path))


@pytest.mark.parametrize('mode', ['optimize', 'uq', 'epsilon'])
def test_bound_operation_ui_lossless_typed_edits(qt_plan_window, mode):
    _, window = qt_plan_window
    draft = bound(mode)
    show_plan(window, draft)
    assert window._view_error is None and window.edited_draft() == draft
    assert not window.operation_options.isHidden() and not window.local_dirty
    path = ('distributions','E','lower') if mode == 'uq' else ('options','population_size')
    option_item(window, path).setText(1, 'unfinished numeric declaration')
    window.budget.setText('unfinished budget')
    edited = window.edited_draft()
    value = edited['operation_options']
    for part in path:
        value = value[part]
    assert value == 'unfinished numeric declaration' and edited['budget'] == 'unfinished budget'
    assert edited['material'] == draft['material'] and edited['experiments'] == draft['experiments']
    assert edited['variables'] == draft['variables'] and diagnostics(edited)
    assert window.local_dirty and window.apply_button.isEnabled() and not window.run_button.isEnabled()


def test_operation_ui_switching_preserves_each_visible_definition(qt_plan_window):
    _, window = qt_plan_window
    draft = bound('optimize')
    show_plan(window, draft)
    option_item(window, ('objective','direction')).setText(1, 'maximize')
    window.mode.setCurrentText('uq')
    options = window.operation_options.value()
    assert options['source']['reference'] == '' and options['independence'] == ''
    options['source']['reference'] = 'Explicit laboratory uncertainty assumption'
    window._replace_options(options)
    window.mode.setCurrentText('fit')
    assert 'operation_options' not in window.edited_draft()
    window.mode.setCurrentText('optimize')
    assert window.edited_draft()['operation_options']['objective']['direction'] == 'maximize'
    window.mode.setCurrentText('uq')
    assert window.edited_draft()['operation_options']['source']['reference'] == 'Explicit laboratory uncertainty assumption'
    assert window.edited_draft()['material'] == draft['material']


def test_operation_ui_explicit_physical_response_and_distribution(qt_plan_window, monkeypatch):
    _, window = qt_plan_window
    from PySide6.QtWidgets import QInputDialog
    show_plan(window, bound('optimize'))
    answers = iter(['stress_xy', 'abs_max', 'maximize'])
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *args, **kwargs:(next(answers), True))
    window.choose_operation_response()
    declaration = window.edited_draft()['operation_options']['objective']
    assert declaration == {'response':'stress_xy', 'unit':'MPa', 'reduction':'abs_max',
                           'component':'xy','location':'material_point','direction':'maximize','scale':1.}
    window.mode.setCurrentText('uq')
    answers = iter(['E', 'uniform'])
    window.choose_distribution()
    options = window.edited_draft()['operation_options']
    variable = window.edited_draft()['variables'][0]
    assert options['distributions']['E'] == {'distribution':'uniform','unit':'MPa',
                                           'lower':variable['lower'],'upper':variable['upper']}
    assert options['source']['reference'] == '' and options['independence'] == ''
    assert diagnostics(window.edited_draft())  # No implicit independence or provenance.


def test_epsilon_ui_adds_explicit_secondary_threshold_without_replacing_grid(qt_plan_window, monkeypatch):
    _, window = qt_plan_window
    from PySide6.QtWidgets import QInputDialog
    draft = bound('epsilon')
    show_plan(window, draft)
    monkeypatch.setattr(QInputDialog, 'getItem', lambda parent,title,label,items,**kwargs:(items[0],True))
    monkeypatch.setattr(QInputDialog, 'getDouble', lambda *args,**kwargs:(3.5,True))
    window.choose_epsilon_threshold()
    edited = window.edited_draft()
    assert edited['operation_options']['threshold_grid'] == [[1.,2.,3.5]]
    assert edited['operation_options']['objectives'] == draft['operation_options']['objectives']
    assert 'budget' in diagnostics(edited)[0]['message']


@pytest.mark.parametrize('summary', [False, True])
def test_candidate_analysis_ui_pins_retained_result_and_actual_reduction(qt_plan_window, monkeypatch, summary):
    _, window = qt_plan_window
    from PySide6.QtWidgets import QInputDialog
    from PySide6.QtCore import QTimer
    row = {'candidate_id':'Cactual','values':{'E':1000.},'execution_status':'SUCCEEDED'}
    if summary:
        row['responses'] = {}
        row['response_reductions'] = [{'response':'stress_xx','kind':'scalar','value':2.,
                                      'unit':'MPa','component':'xx','location':'material_point','reduction':'final'}]
    else:
        row['responses'] = {'cost':response(2.)}
    result = {'kind':'optimization','candidates':[row]}
    document = show_plan(window, bound('optimize'), result=result)
    prompts = []
    def choose(parent,title,label,items,**kwargs):
        prompts.append(items)
        return items[0], True
    monkeypatch.setattr(QInputDialog, 'getItem', choose)
    monkeypatch.setattr(QTimer, 'singleShot', lambda *args:None)
    submitted = []
    class Client:
        def submit(self, operation, inputs):
            submitted.append((operation,deepcopy(inputs)))
            return {'id':'Janalysis'}
    window.client = Client()
    window._call = lambda action,accepted,**kwargs:accepted(action())
    window.analyze_result()
    assert prompts[-1] == (['final'] if summary else ['none'])
    operation, inputs = submitted[0]
    assert operation == 'analyze' and 'table' not in inputs and 'candidates' not in inputs
    assert inputs['result_refs']['table'] == result_reference(document,'Jactual',result)
    assert inputs['responses'][0]['reduction'] == ('final' if summary else 'none')
    assert window._result_cache['Jactual'] == result


def test_optimization_ui_plot_uses_only_actual_finite_objectives(qt_plan_window):
    _, window = qt_plan_window
    result = {'kind':'optimization','objective_definition':{'response':'stress_xx','unit':'MPa'},
              'candidates':[{'candidate_id':'Cok','execution_status':'SUCCEEDED','values':{'E':900.},'objective':2.,'feasible':True},
                            {'candidate_id':'Cfailed','execution_status':'FAILED','values':{'E':1000.},'objective':None},
                            {'candidate_id':'Cprediction','execution_status':'PREDICTED','values':{'E':1100.},'objective':1.}]}
    show_plan(window,bound('optimize'),result=result)
    axis = window.figure.axes[0]
    assert axis.collections[0].get_offsets().tolist() == [[0.,2.]]
    assert axis.get_ylabel() == 'stress_xx [MPa]'
    assert window.candidates.rowCount() == 3  # Failure and prediction identities remain visible.

VARIABLES = [{'id':'x', 'unit':'1', 'value':.5, 'lower':0., 'upper':1., 'transform':'linear'}]
RESPONSE = {'response':'cost', 'unit':'MPa', 'reduction':'none'}


def response(value):
    return {'kind':'scalar', 'value':value, 'unit':'MPa', 'component':'scalar',
            'location':'model', 'reduction':'none'}


def cheap_model(values, settings):
    x = values['x']
    if x > settings.get('fail_above', 1.):
        return {'execution_status':'FAILED', 'responses':{}, 'diagnostics':{'failure_reason':'actual synthetic domain limit'}}
    return {'execution_status':'SUCCEEDED', 'responses':{'cost':response(x*x), 'opposite':response((1-x)**2)}}


def retained(document_id, job_id, result, *, submitted=None):
    draft = deepcopy(submitted if submitted is not None else request_draft())
    run = {'job_id':job_id, 'input_revision':'I'+job_id, 'input_sha256':canonical_hash(draft), 'draft':draft,
           'retention_complete':True, 'retained_result':{'revision':'Rretained'}}
    document = {'id':document_id, 'kind':'numerical', 'runs':[run]}
    return document, result_reference(document, job_id, result)


def resolvers(*triples):
    docs, results = {}, {}
    for document, job_id, result in triples:
        if document['id'] in docs:
            docs[document['id']]['runs'].extend(deepcopy(document['runs']))
        else:
            docs[document['id']] = deepcopy(document)
        results[(document['id'],job_id)] = result
    return docs, results, {'resolve_document':lambda ref:docs[ref],
                           'resolve_result':lambda ref, job:results[(ref,job)]}


def test_exact_retained_reference_executes_real_analysis_preserving_failed_rows():
    table = numerical.run_doe(cheap_model, VARIABLES, settings={'fail_above':.8},
                             candidates=[{'x':x} for x in [0.,.15,.3,.45,.6,.75,.9]])
    doc, ref = retained('Nstudy','Jdoe',table)
    docs, results, callbacks = resolvers((doc,'Jdoe',table))
    inputs = {'result_refs':{'table':ref}, 'responses':[RESPONSE], 'seed':4}
    assert len(json.dumps(inputs)) < 1000 and 'candidates' not in inputs
    prepared = resolve_request_inputs('analyze', inputs, **callbacks)
    assert inputs['result_refs']['table'] == ref and prepared['table']['candidates'][-1]['execution_status'] == 'FAILED'
    result = numerical.analyze_candidates(**prepared)
    assert result['failure_count'] == 1 and result['candidate_count'] == 7
    assert result['exclusions'][-1]['id'] == table['candidates'][-1]['candidate_id']
    results[('Nstudy','Jdoe')] = deepcopy(table)
    results[('Nstudy','Jdoe')]['candidates'][0]['values']['x'] = .01
    with pytest.raises(ValueError, match='result hash changed'):
        resolve_request_inputs('analyze', inputs, **callbacks)
    results[('Nstudy','Jdoe')] = table
    docs['Nstudy']['runs'][0]['input_sha256'] = 'b'*64
    with pytest.raises(ValueError, match='input identity changed'):
        resolve_request_inputs('analyze', inputs, **callbacks)


def test_reference_cannot_use_arbitrary_path_or_unretained_result():
    table = numerical.run_doe(cheap_model, VARIABLES, count=3)
    document, reference = retained('Nstudy','Jdoe',table)
    with pytest.raises(ValueError, match='exact document'):
        validate_result_reference({**reference, 'path':'/server/table.json'})
    document['runs'][0]['retention_complete'] = False
    with pytest.raises(ValueError, match='Save and retain'):
        result_reference(document,'Jdoe',table)
    with pytest.raises(ValueError, match='mixed'):
        validate_result_refs('analyze', {'result_refs':{'table':reference}, 'job_id':'Jreplacement'})
    with pytest.raises(ValueError, match='exact retained result roles'):
        validate_result_refs('surrogate', {'result_refs':{'training':reference}})


def test_surrogate_uses_disjoint_retained_runs_and_reports_failed_exclusions():
    training = numerical.run_doe(cheap_model, VARIABLES, settings={'fail_above':.85},
                               candidates=[{'x':x} for x in [0.,.2,.4,.6,.8,.95]])
    holdout = numerical.run_doe(cheap_model, VARIABLES, candidates=[{'x':x} for x in [.1,.3,.5,.7]])
    td, tr = retained('Ntraining','Jtraining',training)
    hd, hr = retained('Nholdout','Jholdout',holdout)
    _, _, callbacks = resolvers((td,'Jtraining',training),(hd,'Jholdout',holdout))
    inputs = {'result_refs':{'training':tr,'holdout':hr}, 'response':RESPONSE,
              'points':[{'x':.25},{'x':1.1}]}
    args = resolve_request_inputs('surrogate',inputs,**callbacks)
    result = surrogate_result(**args)
    assert all(row['execution_status'] == 'PREDICTED' for row in result['predictions'])
    assert result['predictions'][1]['out_of_range']
    excluded = result['validation']['exclusions']['training']
    assert len(excluded) == 1 and excluded[0]['execution_status'] == 'FAILED'
    assert excluded[0]['values'] == {'x':.95}
    assert len(result['validation']['train_ids']) == 5 and len(result['validation']['holdout_ids']) == 4
    assert training['candidates'][-1]['execution_status'] == 'FAILED'
    with pytest.raises(ValueError, match='separate retained runs'):
        validate_result_refs('surrogate', {'result_refs':{'training':tr,'holdout':tr}})
    with pytest.raises(ValueError, match='overlap'):
        surrogate_result(training,training,RESPONSE,[{'x':.25}])
    with pytest.raises(ValueError, match='unit differs'):
        surrogate_result(training,holdout,{**RESPONSE,'unit':'Pa'},[{'x':.25}])


def test_retained_batch_manifest_preserves_missing_real_evaluations(tmp_path):
    manifest = numerical.export_batch(VARIABLES, [{'x':.1},{'x':.3}],tmp_path/'batch',case_id='Case')
    exported = {'batch_id':'Jexport','manifest':manifest,'mode':'FILE_EXCHANGE','solver_execution':'NOT_PERFORMED'}
    doc, ref = retained('Nbatch','Jexport',exported)
    _, _, callbacks = resolvers((doc,'Jexport',exported))
    row = manifest['candidates'][0]
    imported = {'candidate_id':row['candidate_id'],'values':row['values'],'case_id':'Case',
                'exchange_id':manifest['exchange_id'],**cheap_model(row['values'],{})}
    args = resolve_request_inputs('batch_import',{'result_refs':{'batch':ref},'results':[imported]},**callbacks)
    result = numerical.import_batch(**args)
    assert result['imported_count'] == 1 and result['missing_count'] == 1
    assert result['candidates'][1]['execution_status'] == 'NOT_EVALUATED'
    assert 'NOT_EVALUATED' in manifest['candidates'][1]['execution_status']


def material():
    return {'id':'Mmodel','kind':'material','generation':0,'input_revision':'Imodel','draft':material_draft()}


def bound(mode):
    result = from_material_document(material())
    result['mode'] = mode
    result['budget'] = 20
    objective = {'response':'stress_xx', 'unit':'MPa', 'reduction':'final', 'direction':'minimize',
                 'component':'xx', 'location':'material_point'}
    if mode == 'optimize':
        result['operation_options'] = {'objective':objective, 'options':{'population_size':5,'max_generations':1}}
    elif mode == 'uq':
        result['count'] = 4
        result['operation_options'] = {'distributions':{'E':{'distribution':'uniform','lower':500.,'upper':1500.,'unit':'MPa'}},
                                     'source':{'origin':'ASSUMED','reference':'declared uncertainty scenario'},
                                     'independence':'INDEPENDENT_USER_DECLARED','thresholds':[
                                         {key:value for key,value in objective.items() if key != 'direction'}]}
    else:
        result['operation_options'] = {'objectives':[objective,{**objective,'response':'stress_yy','component':'yy'}],
                                     'threshold_grid':[[1.,2.]],'primary_index':0,
                                     'options':{'population_size':5,'max_generations':1}}
    return result


@pytest.mark.parametrize('mode',['optimize','uq','epsilon'])
def test_bound_material_compiles_only_visible_parameters_and_exact_adoption(tmp_path, mode):
    draft = bound(mode)
    assert diagnostics(draft) == []
    current = material()
    documents = NumericalDocuments(tmp_path,'Ssession',None,None,
                                   resolve_document=lambda ref:current,resolve_result=lambda *args,**kwargs:None)
    request = material_request(draft)
    assert request['budget'] == {'evaluations':20}
    args = documents.job_arguments(draft)
    assert args['settings'] == draft['material']['draft']['settings']
    assert args['variables'][0]['id'] == 'E' and len(args['variables']) == 1
    assert args['execution']['max_evaluations'] == 20
    assert documents.evaluation_for(draft) == mode
    kind = {'optimize':'optimization','uq':'uq','epsilon':'epsilon_optimization'}[mode]
    result = {'kind':kind,'candidates':[{'candidate_id':'Cevaluated','execution_status':'SUCCEEDED',
                                       'values':{'E':1200.},'objective':1.}]}
    adopted = adopted_draft({'draft':draft},result,'Cevaluated')
    assert adopted['settings']['parameters'] == {'E':1200.,'nu':.25}
    assert adopted['settings']['model'] == draft['material']['draft']['settings']['model']
    result['candidates'][0]['execution_status'] = 'PREDICTED'
    with pytest.raises(ValueError, match='actually evaluated'):
        adopted_draft({'draft':draft},result,'Cevaluated')
    current['draft']['settings']['parameters']['E'] = 2000
    with pytest.raises(ValueError, match='Material input changed'):
        documents.job_arguments(draft)


def test_bound_search_budget_and_units_reject_before_execution():
    draft = bound('epsilon')
    draft['budget'] = 19
    assert 'budget' in diagnostics(draft)[0]['message']
    draft = bound('optimize')
    draft['operation_options']['objective']['unit'] = 'Pa'
    assert 'unit' in diagnostics(draft)[0]['message']
    draft = bound('uq')
    draft['count'] = 21
    assert 'budget' in diagnostics(draft)[0]['message']
    draft = bound('uq')
    draft['operation_options']['distributions']['nu'] = {'distribution':'uniform'}
    assert 'distribution' in diagnostics(draft)[0]['message']


def test_saved_general_source_is_frozen_but_independent_request_remains_editable(tmp_path):
    source_document = {'id':'Msource','kind':'material','input_revision':'Isource','draft':material_draft()}
    source = {'document_id':'Msource','kind':'material','saved_revision':'Rsaved',
              'input_revision':'Isource','input_sha256':canonical_hash(source_document['draft'])}
    request = {'purpose':'Independent material check', 'operation':'evaluate',
               'inputs':deepcopy(source_document['draft']), 'budget':{'evaluations':1}}
    draft = request_draft(request,source=source)
    draft['request']['inputs']['settings']['parameters']['E'] = 1200.
    assert diagnostics(draft) == []
    documents = NumericalDocuments(tmp_path,'Ssession',None,None,resolve_document=lambda ref:None,
        resolve_result=lambda *args:None,prepare_request=lambda req:req['inputs'],
        resolve_source_revision=lambda ref, revision:source_document)
    prepared = documents.job_arguments(draft)
    assert prepared['settings']['parameters']['E'] == 1200.
    assert source_document['draft']['settings']['parameters']['E'] == 1000.
    source_document['input_revision'] = 'Ichanged'
    with pytest.raises(ValueError, match='saved source research input changed'):
        documents.job_arguments(draft)


@pytest.mark.parametrize('mode',['optimize','uq','epsilon'])
def test_bound_operation_arguments_run_actual_existing_engine_with_hard_budget(tmp_path, mode):
    draft = bound(mode)
    documents = NumericalDocuments(tmp_path,'Ssession',None,None,resolve_document=lambda ref:material(),
                                   resolve_result=lambda *args,**kwargs:None)
    args = documents.job_arguments(draft)
    args.pop('backend')
    calls = []
    def model(values, settings):
        calls.append(deepcopy(values))
        channels = {}
        for name, component, magnitude in [('stress_xx','xx',values['E']/1000.),
                                            ('stress_yy','yy',(10000.-values['E'])/10000.)]:
            channels[name] = {'kind':'series','value':[0.,magnitude,2*magnitude],'unit':'MPa',
                              'component':component,'location':'material_point','reduction':'none',
                              'axes':[{'name':'time','unit':'s','values':[0.,1.,2.]}],
                              'frame':'material_cartesian','measure':'infinitesimal_Cauchy'}
        return {'execution_status':'SUCCEEDED','responses':channels}
    method = {'optimize':numerical.optimize,'uq':numerical.run_uq,'epsilon':numerical.epsilon_optimize}[mode]
    actual = method(model, **args)
    assert actual['execution_status'] == 'SUCCEEDED'
    assert 0 < len(calls) <= draft['budget']
    successful = next(row for row in actual['candidates'] if row['execution_status'] == 'SUCCEEDED')
    adopted = adopted_draft({'draft':draft},actual,successful['candidate_id'])
    assert adopted['settings']['parameters']['E'] == successful['values']['E']
    assert adopted['settings']['parameters']['nu'] == .25
    if mode == 'epsilon':
        assert len(actual['children']) == 2 and all(row['candidate_id'].startswith('E') for row in actual['candidates'])
    elif mode == 'uq':
        assert actual['probability_statistics'][0]['valid_count'] == 4


def test_sensitivity_resolver_preserves_exact_matched_plan_and_rows():
    table = numerical.run_doe(cheap_model, VARIABLES, candidates=[{'x':.1},{'x':.5},{'x':.9}])
    submitted = request_draft({'purpose':'Controlled cheap-model DOE', 'operation':'doe',
        'inputs':{'backend':'test.synthetic.cheap_model', 'settings':{}, 'variables':deepcopy(VARIABLES),
                  'candidates':[deepcopy(row['values']) for row in table['candidates']]},
        'budget':{'evaluations':3}})
    doc, ref = retained('Nsensitivity','Jsobol',table, submitted=submitted)
    docs, _, callbacks = resolvers((doc,'Jsobol',table))
    plan = {'variables':VARIABLES,'sampling':{'method':'SALib.sobol'},
            'candidates':[{'candidate_id':row['candidate_id'],'values':deepcopy(row['values'])} for row in table['candidates']]}
    prepared = resolve_request_inputs('sensitivity',{'result_refs':{'table':ref},'plan':plan,'response':RESPONSE},**callbacks)
    assert prepared['plan'] == plan and prepared['table']['candidates'] == table['candidates']
    assert prepared['evaluation_context']['backend'] == submitted['request']['inputs']['backend']
    docs['Nsensitivity']['runs'][0]['draft']['request']['inputs']['settings']['changed'] = True
    with pytest.raises(ValueError, match='exact saved submitted DOE input'):
        resolve_request_inputs('sensitivity',{'result_refs':{'table':ref},'plan':plan,'response':RESPONSE},**callbacks)
    # Optional SALib is not installed here: do not substitute LHS sensitivity.
    import importlib.util
    if importlib.util.find_spec('SALib') is None:
        with pytest.raises(RuntimeError, match='optional SALib'):
            numerical.analyze_sensitivity(**prepared)


def test_surrogate_never_relabels_holdout_parameter_units():
    training = numerical.run_doe(cheap_model, VARIABLES,candidates=[{'x':x} for x in [0.,.2,.4,.6,.8]])
    holdout = numerical.run_doe(cheap_model, VARIABLES,candidates=[{'x':.1},{'x':.3}])
    holdout['variables'][0]['unit'] = 'mm'
    with pytest.raises(ValueError, match='units and transforms'):
        surrogate_result(training,holdout,RESPONSE,[{'x':.25}])


def test_batch_export_and_sensitivity_plans_can_pin_large_rows_without_copying(tmp_path):
    table = numerical.run_doe(cheap_model,VARIABLES,candidates=[{'x':.1},{'x':.4}])
    submitted = request_draft({'purpose':'Controlled cheap-model DOE', 'operation':'doe',
        'inputs':{'backend':'test.synthetic.cheap_model', 'settings':{}, 'variables':deepcopy(VARIABLES),
                  'candidates':[deepcopy(row['values']) for row in table['candidates']]},
        'budget':{'evaluations':2}})
    doc, ref = retained('Nrows','Jrows',table, submitted=submitted)
    plan = {'variables':VARIABLES,'sampling':{'method':'SALib.sobol'},
            'candidates':[{'candidate_id':row['candidate_id'],'values':row['values']} for row in table['candidates']]}
    pd, pref = retained('Nplan','Jplan',plan)
    _, _, callbacks = resolvers((doc,'Jrows',table),(pd,'Jplan',plan))
    prepared = resolve_request_inputs('batch_export', {'result_refs':{'candidates':ref}, 'case_id':'external-case'}, **callbacks)
    exported = numerical.export_batch(directory=tmp_path/'bound-export',**prepared)
    assert exported['candidates'][1]['values'] == table['candidates'][1]['values']
    prepared = resolve_request_inputs('sensitivity', {'result_refs':{'table':ref,'plan':pref}, 'response':RESPONSE}, **callbacks)
    assert prepared['plan'] == plan and prepared['table'] == table
