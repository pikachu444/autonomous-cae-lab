"""Bounded portable checks of Data input and Numerical Plan ownership."""
from copy import deepcopy
from pathlib import Path
import time

import pytest

from caelab.adapters.file_table import read_table, preview_table
from caelab.data_document import default_draft as data_draft
from caelab.material_document import default_draft as material_draft
from caelab.numerical_document import NumericalDocuments, adopted_draft, diagnostics, from_material_document
from caelab.storage import canonical_hash


def material():
    return {'id': 'Mmodel', 'kind': 'material', 'generation': 0, 'input_revision': 'Imodel', 'draft': material_draft()}


def response():
    return {'kind': 'series', 'value': [0, 1.2, 2.4], 'unit': 'MPa', 'component': 'xx',
            'location': 'material_point', 'reduction': 'none', 'measure': 'infinitesimal_Cauchy',
            'frame': 'material_cartesian', 'coordinate_system': 'UNSPECIFIED',
            'axes': [{'name': 'time', 'unit': 's', 'values': [0, 1, 2]}]}


def plan():
    draft = from_material_document(material())
    draft['variables'][0].update(value=800, lower=500, upper=2000)
    draft['experiments'] = [{'id': 'Efit', 'role': 'fit',
        'source': {'document_id': 'Tdata', 'job_id': 'Jimport', 'response': 'measured', 'input_revision': 'Idata', 'input_sha256': 'a'*64},
        'response': 'stress_xx', 'settings': material_draft()['settings'], 'weight': 1, 'scale': 1}]
    return draft


def owner(tmp_path, observed=None):
    model = material()
    data = {'kind': 'data', 'runs': [{'job_id': 'Jimport', 'input_revision': 'Idata', 'input_sha256': 'a'*64}]}
    def resolve(identifier):
        return model if identifier == 'Mmodel' else data
    def result(*args, **kwargs):
        return {'execution_status': 'SUCCEEDED', 'responses': {'measured': deepcopy(response() if observed is None else observed)}}
    return NumericalDocuments(tmp_path, 'Ssession', None, None, resolve_document=resolve, resolve_result=result), model, data


def test_compile_frozen_refs_once_and_preserve_metadata(tmp_path):
    documents, model, data = owner(tmp_path)
    draft = plan()
    assert diagnostics(draft) == []
    arguments = documents.job_arguments(draft)
    assert arguments['variables'][0]['id'] == 'E'
    assert arguments['experiments'][0]['settings']['parameters'] == {'E': 800, 'nu': .25}
    assert arguments['experiments'][0]['observations'] == response()
    assert 'observations' not in draft['experiments'][0]
    # Compiled input is detached from subsequent draft/source edits.
    model['draft']['settings']['parameters']['E'] = 1500
    assert arguments['experiments'][0]['observations']['value'] == [0, 1.2, 2.4]
    with pytest.raises(ValueError, match='Material input changed'):
        documents.job_arguments(draft)


@pytest.mark.parametrize('field,value,message', [('measure', 'Cauchy', 'stress measure'), ('frame', 'laboratory', 'frame'), ('unit', 'Pa', 'unit'), ('component', 'yy', 'component')])
def test_no_implicit_measure_frame_unit_or_component_conversion(tmp_path, field, value, message):
    observation = response()
    observation[field] = value
    documents, _, _ = owner(tmp_path, observation)
    with pytest.raises(ValueError, match=message):
        documents.job_arguments(plan())


def test_data_source_identity_and_protocol_are_explicit(tmp_path):
    documents, _, data = owner(tmp_path)
    draft = plan()
    draft['experiments'][0]['settings']['deformation_gradient'][1][1][1] = ''
    assert diagnostics(draft)
    draft = plan()
    data['runs'][0]['input_sha256'] = 'b'*64
    with pytest.raises(ValueError, match='retained Data import'):
        documents.job_arguments(draft)


def test_fit_actual_library_and_explicit_adoption(tmp_path):
    pytest.importorskip('felupe')
    from caelab.numerical import fit_model
    documents, _, _ = owner(tmp_path)
    draft = plan()
    holdout = deepcopy(draft['experiments'][0])
    holdout.update(id='Eholdout', role='holdout')
    draft['experiments'].append(holdout)
    args = documents.job_arguments(draft)
    backend = args.pop('backend')
    result = fit_model(backend, **args)
    assert result['execution_status'] == 'SUCCEEDED'
    assert result['parameters']['E'] == pytest.approx(1000, rel=1e-6)
    assert {curve['role'] for curve in result['curves']} == {'fit', 'holdout'}
    assert all(curve['prediction_metadata']['frame'] == 'material_cartesian' for curve in result['curves'])
    candidate = min((row for row in result['candidates'] if row['execution_status'] == 'SUCCEEDED'), key=lambda row: row['objective'])
    # A successful objective alone is not preserved candidate-detail evidence.
    # The actual owner/adoption path is covered by the C1 consumer integration test.
    from caelab.numerical_candidate_evidence import DetailEvidenceBlocked
    with pytest.raises(DetailEvidenceBlocked):
        adopted_draft({'draft': draft}, result, candidate['candidate_id'])
    assert draft['material']['draft']['settings']['parameters']['E'] == 1000
    rejected = deepcopy(result)
    rejected['candidates'][0]['execution_status'] = 'FAILED'
    with pytest.raises(ValueError, match='successful candidate'):
        adopted_draft({'draft': draft}, rejected, rejected['candidates'][0]['candidate_id'])


def test_original_row_labels_survive_comments_blank_and_header(tmp_path):
    source = tmp_path/'measured.csv'
    source.write_text('# exported result\ntime,stress\n\n0,0\n# segment note\n1,1.2\n2,2.4\n')
    mapping = data_draft()['mapping']
    mapping['skip_header'] = 2
    spec = mapping['columns']['response']
    spec.update(unit='MPa', component='xx', location='material_point', measure='infinitesimal_Cauchy', frame='material_cartesian')
    spec['axis'].update(name='time', unit='s')
    result = read_table(source, mapping)['responses']['response']
    assert result['source_rows'].tolist() == [3,5,6]
    assert preview_table(source.read_text())['row_numbers'] == [3,5,6]
    assert result['measure'] == 'infinitesimal_Cauchy'
    assert result['frame'] == 'material_cartesian'


def test_raw_invalid_plan_remains_saveable_undoable_without_run(tmp_path):
    documents, _, _ = owner(tmp_path)
    document = documents.open(draft=plan())
    changed = deepcopy(document['draft'])
    changed['variables'][0]['lower'] = 'unfinished'
    def command(doc, op, arguments=None):
        return documents.command(doc['id'], op, arguments or {}, session_id='Ssession', expected_generation=doc['generation'])['document']
    edited = command(document, 'numerical.update', {'draft': changed})
    assert edited['diagnostics'] and edited['draft']['variables'][0]['lower'] == 'unfinished'
    saved = command(edited, 'document.save')
    documents._documents.clear()
    reopened = documents.read(saved['id'])
    assert reopened['draft'] == changed
    undone = command(reopened, 'document.undo')
    assert undone['draft'] == document['draft'] and not undone['diagnostics']


def test_service_data_fit_doe_adoption_retention_and_undo(tmp_path):
    """One real portable service flow; no native/visible/physical validation claim."""
    pytest.importorskip('felupe')
    from caelab.workbench import Workbench
    wb = Workbench(tmp_path)
    def command(doc, op, args=None, **options):
        return wb.document_command(doc['id'], op, args or {}, session_id=doc['session_id'], expected_generation=doc['generation'], **options)
    def completed(job):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            status=wb.manager.status(job['id'])
            if status['state'] in {'SUCCEEDED','FAILED','REJECTED','CANCELLED'}:
                assert status['state']=='SUCCEEDED', status
                return wb.result(job['id'])
            time.sleep(.01)
        raise AssertionError('Portable service job did not finish')
    try:
        material_doc=wb.document_open(kind='material')
        data_docs=[]
        for name, content, delimiter, skip in [('fit.csv', '# source\nt,stress\n0,0\n\n1,1.2\n2,2.4\n', ',', 2), ('holdout.dat', '0 0\n1 1.2\n# line note\n2 2.4\n', None, 0)]:
            receipt=wb.upload(name,content.encode())
            draft=data_draft()
            draft['data_id']=receipt['id']
            draft['mapping'].update(delimiter=delimiter,skip_header=skip)
            spec=draft['mapping']['columns']['response']
            spec.update(unit='MPa',component='xx',location='material_point',measure='infinitesimal_Cauchy',frame='material_cartesian')
            spec['axis'].update(name='time',unit='s')
            doc=wb.document_open(kind='data',draft=draft)
            imported=command(doc,'data.import')
            completed(imported['job'])
            doc=command(wb.document_read(doc['id']),'document.save')['document']
            data_docs.append(doc)
            # The Data owner remains sufficient after original registration loss.
            import shutil
            shutil.rmtree(wb.root/'inputs'/receipt['id'])
            assert wb.document_source_preview(doc['id'])['retained']
        draft=from_material_document(material_doc)
        draft['variables'][0].update(value=750,lower=500,upper=2000)
        for index, doc in enumerate(data_docs):
            run=doc['runs'][0]
            draft['experiments'].append({'id':'E'+str(index),'role':'fit' if index==0 else 'holdout',
                'source':{'document_id':doc['id'],'job_id':run['job_id'],'response':'response','input_revision':run['input_revision'],'input_sha256':run['input_sha256']},
                'response':'stress_xx','settings':deepcopy(material_doc['draft']['settings']),'weight':1,'scale':1})
        plan_doc=wb.document_open(kind='numerical',draft=draft)
        submitted=command(plan_doc,'numerical.run')
        result=completed(submitted['job'])
        assert result['parameters']['E']==pytest.approx(1000,rel=1e-6)
        assert {curve['role'] for curve in result['curves']}=={'fit','holdout'}
        assert not material_doc['runs']
        candidate=min((r for r in result['candidates'] if r['execution_status']=='SUCCEEDED'),key=lambda r:r['objective'])
        adopted=wb.desktop.adopt(plan_doc['id'],submitted['job']['id'],candidate['candidate_id'],material_document_id=material_doc['id'],session_id=material_doc['session_id'],expected_generation=0,command_id='Cadopt')['document']
        assert adopted['generation']==1 and adopted['draft']['settings']['parameters']['E']==pytest.approx(1000,rel=1e-6)
        retained_plan_revision=wb.document_read(plan_doc['id'])['saved_revision']
        assert wb.desktop.adopt(plan_doc['id'],submitted['job']['id'],candidate['candidate_id'],material_document_id=material_doc['id'],session_id=material_doc['session_id'],expected_generation=0,command_id='Cadopt')['document']['generation']==1
        assert wb.document_read(plan_doc['id'])['saved_revision']==retained_plan_revision
        undone=command(adopted,'document.undo')['document']
        assert undone['draft']==material_doc['draft']
        doe=from_material_document(undone)
        doe.update(mode='doe',count=3,budget=3)
        doe_doc=wb.document_open(kind='numerical',draft=doe)
        submitted_doe=command(doe_doc,'numerical.run')
        doe_result=completed(submitted_doe['job'])
        assert len(doe_result['candidates'])==3 and doe_result['timing']['model_calls']==3
        saved=command(wb.document_read(plan_doc['id']),'document.save')['document']
        assert saved['runs'][0]['retention_complete']
        assert wb.shutdown()['joined']
        wb=Workbench(tmp_path)
        reopened=wb.document_read(plan_doc['id'])
        assert reopened['runs'][0]['retained_result']
        assert wb.document_result(plan_doc['id'],submitted['job']['id'])['parameters']['E']==pytest.approx(1000,rel=1e-6)
    finally:
        assert wb.shutdown()['joined']


def test_unregistered_invalid_data_identity_does_not_prevent_draft_save(tmp_path):
    from caelab.data_document import DataDocuments
    def missing(identifier):
        raise FileNotFoundError(identifier)
    documents=DataDocuments(tmp_path,'Sowner',None,None,resolve_input=missing)
    draft=data_draft()
    draft['data_id']='Dunfinished'
    document=documents.open(draft=draft)
    saved=documents.command(document['id'],'document.save',{},session_id='Sowner',expected_generation=0)['document']
    assert saved['draft']==draft and saved['unresolved_inputs']==['Dunfinished']
    documents._documents.clear()
    assert documents.read(document['id'])['draft']==draft


def test_scalar_analysis_honors_explicit_measure_and_frame():
    from caelab.numerical import _scalar
    evaluation={'execution_status':'SUCCEEDED','responses':{'stress':{**response(),'kind':'scalar','value':1.2}}}
    definition={'response':'stress','unit':'MPa','measure':'first_Piola','frame':'material_cartesian'}
    with pytest.raises(ValueError,match='measure differs'):
        _scalar(evaluation,definition)
    definition['measure']='infinitesimal_Cauchy'
    assert _scalar(evaluation,definition)==1.2
    definition['frame']='laboratory'
    with pytest.raises(ValueError,match='frame differs'):
        _scalar(evaluation,definition)


def test_invalid_material_reference_can_be_opened_as_blocked_plan():
    model=material()
    model['draft']['settings']=[]
    draft=from_material_document(model)
    assert draft['material']['draft']==model['draft'] and draft['variables']==[]
    assert diagnostics(draft)
