"""Evaluation retention/typed projection checks; worker responses are labelled doubles.

Actual two-mesh coupled prefix reuse is examples.portable_evaluation_public.
"""
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import patch
import pytest

from caelab.workbench import Workbench
from caelab.storage import canonical_hash, save_json
from caelab.evaluation import save_evaluation, file_hash
from caelab.evaluation_definition import default_draft, document_reference, definition_hash
from caelab.portable_project import inspect_copy, create_copy, open_project, verify_project
from caelab.portable_project_evaluation import check_run, read_execution, reuse_view
from caelab.research_workflows import evaluation_progress, evaluation_stage_result, result_folder
from examples.portable_physics_public import command, save, wait, hashes, no_execution


@contextmanager
def workspace(path):
    wb = Workbench(path)
    try: yield wb
    finally:
        closed = wb.shutdown(); assert closed['joined'] and not closed['pending']


def fixture(wb, kinds=('material','pde','simulation')):
    from caelab.material_document import default_draft as material
    from caelab.pde_document import default_draft as pde
    from caelab.simulation_document import default_draft as simulation
    drafts = {'material': material(), 'pde': pde('pde.scipy.ode'),
              'simulation': simulation('thermal.scikit_fem.rectangle')}
    sources=[];draft=default_draft()
    for i, kind in enumerate(kinds):
        source=save(wb, wb.document_open(kind=kind,draft=drafts[kind]));sources.append(source)
        draft['stages'].append({'id':'S'+str(i),'name':kind,'source':document_reference(source)})
    return sources,wb.document_open(kind='evaluation',draft=draft,title='공개 보관 경계')


def recorded(wb, doc, state='FAILED'):
    def controlled(operation,args,job):
        assert operation=='evaluation.coupled'
        folder=wb.root/'results'/job;folder.mkdir(parents=True)
        if state=='RAISED': raise RuntimeError('CONTROLLED missing runtime; no physics')
        stage=folder/'stages/i0000-S0';stage.mkdir(parents=True)
        (stage/'raw-output.bin').write_bytes(b'CONTROLLED retained original\r\n\x00')
        save_evaluation({'execution_status':'SUCCEEDED','responses':{},'checks':[],
            'diagnostics':{'qualification':'UNKNOWN','scope':'CONTROLLED, NOT PHYSICS'},
            'artifacts':[{'path':'raw-output.bin','sha256':file_hash(stage/'raw-output.bin')}]},stage,existing=True)
        result={'kind':'coupled_evaluation','execution_status':'FAILED' if state=='PROGRESS_ONLY' else state,'responses':{},'checks':[],
            'definition_sha256':definition_hash(args['definition']),'values':{},
            'stages':[{'stage_id':'S0','iteration':0,'attempt_id':'Aoriginal','state':'SUCCEEDED',
                'dispatched':True,'result_directory':'stages/i0000-S0',
                'input_sha256':canonical_hash(args['snapshots']['S0']['draft'])}],
            'iterations':[{'iteration':0,'status':'FAILED' if state=='FAILED' else 'NOT_REQUIRED'}],
            'transfers':[], 'diagnostics':{'qualification':'UNKNOWN','failure':'CONTROLLED later failure' if state=='FAILED' else None}}
        save_json(folder/'progress.json',result)
        if state=='PROGRESS_ONLY':
            raise RuntimeError('CONTROLLED terminal failure after completed stage; final parent result missing')
        save_evaluation(result,folder,existing=True);return result
    with patch.object(wb.manager,'_execute',controlled):
        receipt=command(wb,doc,'evaluation.run');wait(wb,receipt['job']['id'])
    if state=='PROGRESS_ONLY':
        # One save must not observe RUNNING in a pre-hook and FAILED later.
        # The same single snapshot determines retention and published state.
        terminal=wb.manager.status(receipt['job']['id'])
        running={**terminal,'state':'RUNNING'}
        with patch.object(wb.manager,'status',side_effect=[running,terminal]) as statuses:
            owner=wb.evaluation_documents
            owner._save(owner._documents[doc['id']])
            assert statuses.call_count==1
            assert not owner._documents[doc['id']]['runs'][0]['retention_complete']
    return save(wb,wb.document_read(doc['id'])),receipt['job']['id']


def copy(wb,docs,target):
    plan=inspect_copy(wb,[d['id'] for d in docs]);assert plan['status']=='READY',plan['issues']
    return create_copy(wb,plan,target,approved=True,command_id='Ccopy',session_id=wb.session_id)


def test_all_domain_sources_failed_attempt_bytes_edit_undo_recopy_no_manager(tmp_path):
    with workspace(tmp_path/'origin') as wb:
        sources,doc=fixture(wb);doc,job=recorded(wb,doc)
        raw=hashes(wb,doc,job);result=canonical_hash(wb.document_result(doc['id'],job))
        original=deepcopy(doc['runs'][0]);made=copy(wb,[*sources,doc],tmp_path/'copy')
    (tmp_path/'origin').rename(tmp_path/'origin-preserved')
    wb=open_project(tmp_path/'copy')
    try:
        with no_execution(wb):
            docs=[wb.document_read(r['document_id']) for r in made['documents']]
            doc=next(d for d in docs if d['kind']=='evaluation')
            assert hashes(wb,doc,job)==raw
            assert canonical_hash(wb.document_result(doc['id'],job))==result
            progress=evaluation_progress(wb,doc['id'],job)
            assert progress['execution_status']=='FAILED' and progress['stages'][0]['attempt_id']=='Aoriginal'
            assert evaluation_stage_result(wb,doc['id'],job,'Aoriginal')['diagnostics']['qualification']=='UNKNOWN'
            bridge=read_execution(wb.evaluation_documents,doc['id'],job)
            assert bridge['original_run']['arguments']==original['arguments']
            run=doc['runs'][0];check_run(run)
            assert {s['source']['kind'] for s in run['draft']['stages']}=={'material','pde','simulation'}
            for stage in run['draft']['stages']:
                snapshot=run['arguments']['snapshots'][stage['id']]
                assert snapshot['id']==stage['source']['document_id']
                assert snapshot['id'] not in {s['id'] for s in sources}
            before=deepcopy(doc['draft']);unfinished=deepcopy(before)
            unfinished['iteration']['maximum']='1e'
            doc=command(wb,doc,'evaluation.update',{'draft':unfinished})['document']
            assert doc['diagnostics']
            doc=save(wb,doc)
            doc=command(wb,doc,'document.undo')['document'];assert doc['draft']==before
            doc=command(wb,doc,'document.redo')['document'];assert doc['draft']==unfinished
            doc=save(wb,doc)
            made=copy(wb,[doc if d['kind']=='evaluation' else d for d in docs],tmp_path/'recopy')
            assert not wb.manager.list()
    finally: wb.shutdown()
    (tmp_path/'copy').rename(tmp_path/'copy-preserved')
    wb=open_project(tmp_path/'recopy')
    try:
        with no_execution(wb):
            doc=wb.document_read(next(r['document_id'] for r in made['documents'] if r['kind']=='evaluation'))
            assert {k:v for k,v in doc['draft'].items() if k!='stages'}=={k:v for k,v in unfinished.items() if k!='stages'}
            assert doc['diagnostics']
            assert [s['source']['kind'] for s in doc['draft']['stages']]==['material','pde','simulation']
            assert all(s['source']['document_id'] in {r['document_id'] for r in made['documents']} for s in doc['draft']['stages'])
            assert hashes(wb,doc,job)==raw and canonical_hash(wb.document_result(doc['id'],job))==result
            assert evaluation_progress(wb,doc['id'],job)['execution_status']=='FAILED'
        assert verify_project(wb.workspace)['status']=='READY'
    finally: wb.shutdown()


def test_terminal_missing_runtime_has_no_fabricated_result(tmp_path):
    with workspace(tmp_path/'origin') as wb:
        sources,doc=fixture(wb,('pde',));doc,job=recorded(wb,doc,'RAISED')
        failure=doc['runs'][0]['retained_error'];made=copy(wb,[*sources,doc],tmp_path/'copy')
    wb=open_project(tmp_path/'copy')
    try:
        with no_execution(wb):
            doc=wb.document_read(next(r['document_id'] for r in made['documents'] if r['kind']=='evaluation'))
            assert evaluation_progress(wb,doc['id'],job)['job_state']=='FAILED'
            assert doc['runs'][0]['retained_error']==failure
            assert read_execution(wb.evaluation_documents,doc['id'],job)['result'] is None
            with pytest.raises(ValueError,match='no response'):wb.document_result(doc['id'],job)
    finally:wb.shutdown()


@pytest.mark.parametrize('change',['source_revision','stage_order','transfer_unit','binding'])
def test_reuse_proof_does_not_admit_changed_definition(tmp_path,change):
    with workspace(tmp_path/'origin') as wb:
        sources,doc=fixture(wb);doc,job=recorded(wb,doc,'SUCCEEDED')
        made=copy(wb,[*sources,doc],tmp_path/'copy')
    wb=open_project(tmp_path/'copy')
    try:
        with no_execution(wb):
            doc=wb.document_read(next(r['document_id'] for r in made['documents'] if r['kind']=='evaluation'))
            value=wb.document_result(doc['id'],job);before=canonical_hash(value)
            ref={'document_id':doc['id'],'job_id':job}
            compiled={'definition_sha256':definition_hash(doc['runs'][0]['draft'])}
            view=reuse_view(wb,ref,compiled,value)
            assert view is not value and canonical_hash(value)==before
            draft=deepcopy(doc['runs'][0]['draft'])
            if change=='source_revision':draft['stages'][0]['source']['saved_revision']='Rchanged'
            elif change=='stage_order':draft['stages'].reverse()
            elif change=='transfer_unit':draft['transfers']=[{'unit':'degC'}]
            else:draft['bindings']=[{'value':'changed'}]
            with pytest.raises(ValueError,match='Reuse input/definition'):
                reuse_view(wb,ref,{'definition_sha256':definition_hash(draft)},value)
    finally:wb.shutdown()


def test_missing_dependency_and_retained_tamper_block_copy(tmp_path):
    with workspace(tmp_path/'origin') as wb:
        sources,doc=fixture(wb,('pde',));doc,job=recorded(wb,doc)
        assert inspect_copy(wb,[doc['id']])['status']=='BLOCKED'
        run=doc['runs'][0]
        path=wb.evaluation_documents._folder(doc['id'])/'revisions'/run['retained_result']['revision']/'results'/job/'stages/i0000-S0/raw-output.bin'
        path.write_bytes(b'changed')
        assert inspect_copy(wb,[* [s['id'] for s in sources],doc['id']])['status']=='BLOCKED'


def test_same_input_cannot_claim_other_evaluation_owner(tmp_path):
    with workspace(tmp_path/'origin') as wb:
        _,doc=fixture(wb,('pde',));doc,_=recorded(wb,doc)
        run=deepcopy(doc['runs'][0]);check_run(run,doc['id'])
        other=wb.document_open(kind='evaluation',draft=doc['draft'])
        assert canonical_hash(other['draft'])==run['input_sha256']
        run['arguments']['definition_source']['document_id']=other['id']
        with pytest.raises(ValueError,match='EVALUATION_OWNER_CHANGED'):check_run(run,doc['id'])


def test_progress_only_terminal_keeps_original_failed_attempt_through_cold_recopy(tmp_path):
    def assets(wb,doc,job):
        folder,_=result_folder(wb,doc['id'],job)
        return {p.relative_to(folder).as_posix():file_hash(p) for p in folder.rglob('*') if p.is_file()}
    def read_failed(wb,doc,job,original):
        run=doc['runs'][0]
        assert run['retained_state']=='FAILED' and not run.get('retained_result')
        with pytest.raises(ValueError,match='no response'):wb.document_result(doc['id'],job)
        progress=evaluation_progress(wb,doc['id'],job)
        assert progress['job_state']=='FAILED' and progress['execution_status']=='FAILED'
        assert progress['stages'][0]['attempt_id']=='Aoriginal'
        assert progress['stages'][0]['state']=='SUCCEEDED'
        assert evaluation_stage_result(wb,doc['id'],job,'Aoriginal')['diagnostics']['qualification']=='UNKNOWN'
        assert assets(wb,doc,job)==original
        assert 'result.json' not in original
        assert read_execution(wb.evaluation_documents,doc['id'],job)['result'] is None
    with workspace(tmp_path/'origin') as wb:
        sources,doc=fixture(wb,('pde',));doc,job=recorded(wb,doc,'PROGRESS_ONLY')
        original=assets(wb,doc,job)
        assert 'progress.json' in original and 'stages/i0000-S0/result.json' in original
        made=copy(wb,[*sources,doc],tmp_path/'copy')
    (tmp_path/'origin').rename(tmp_path/'origin-preserved')
    wb=open_project(tmp_path/'copy')
    try:
        with no_execution(wb):
            docs=[wb.document_read(r['document_id']) for r in made['documents']]
            doc=next(d for d in docs if d['kind']=='evaluation')
            read_failed(wb,doc,job,original)
            doc=save(wb,doc)  # Ordinary save must retain the same partial bytes.
            made=copy(wb,[doc if d['kind']=='evaluation' else d for d in docs],tmp_path/'recopy')
            assert not wb.manager.list()
    finally:wb.shutdown()
    (tmp_path/'copy').rename(tmp_path/'copy-preserved')
    wb=open_project(tmp_path/'recopy')
    try:
        with no_execution(wb):
            doc=wb.document_read(next(r['document_id'] for r in made['documents'] if r['kind']=='evaluation'))
            read_failed(wb,doc,job,original)
            assert not wb.manager.list()
        assert verify_project(wb.workspace)['status']=='READY'
    finally:wb.shutdown()
