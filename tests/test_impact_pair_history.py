"""Exact pair raw history + existing owner tests; synthetic bytes are not physics."""
from copy import deepcopy
from pathlib import Path
import json,struct
import pytest
from impact_b_fixtures import compile_fixture,history_bytes,rec,floats
from test_impact_interface_bulk import delayed
from caelab import impact_b
from caelab.impact_bulk_history import read,bind,series,impulse_secants
from caelab.impact_bulk_results import read_selected,sampled_integral
from caelab.adapters.opencourant_runtime import WINDOWS_SOURCE,WINDOWS_FILES


def identity():return {'source_tag':WINDOWS_SOURCE,'platform':'win64','files':deepcopy(WINDOWS_FILES)}


@pytest.fixture(scope='module')
def compiled(tmp_path_factory):
    settings=delayed()
    settings['source']['text']+='*SURFACE,TYPE=ELEMENT,NAME=OUTERLOWER\nLOWER,S1\n*SURFACE,TYPE=ELEMENT,NAME=OUTERUPPER\nUPPER,S2\n'
    settings['contacts'].append({'a':'OUTERLOWER','b':'OUTERUPPER','law':'TYPE24','friction':0.})
    settings['b_responses'] +=[{'name':f'PAIR{pair}_{quantity}_{component}','scope':'pair','identity':pair,'quantity':quantity,'component':component}
        for pair in range(2) for quantity in ('native_impulse','force','sampled_impulse') for component in ('FNX','FNY','FNZ','FTX','FTY','FTZ')]
    return compile_fixture(tmp_path_factory.mktemp('pair-cards'),settings)


def history(tmp_path,groups,*,values=None):
    data,titles,offsets=history_bytes(groups,times=(0.,.1,.4))
    if values is not None:
        data=data[:offsets[0]]
        for i,time in enumerate((0.,.1,.4)):
            data+=floats(time)+floats(*([0.]*23))
            for group in groups:
                if group['kind']=='pair':
                    base=values[group['contact_index']][i]
                    data+=floats(*[base*(k+1) for k in range(len(group['tokens']))])
                else:data+=floats(*([0.]*len(group['tokens'])))
    path=tmp_path/'pairT01';path.write_bytes(data);title=tmp_path/'pairT01_TITLES';title.write_bytes(titles)
    return read(path,titles=title)


def test_two_exact_pairs_components_native_impulse_mean_force_and_sampled_integral(tmp_path,compiled):
    settings,model,_,_,text,definition=compiled
    impact_b.verify(text,model,settings,definition)
    h=history(tmp_path,definition['outputs']['groups'],values=[[0.,2.,1.],[0.,-4.,-2.]])
    selected,record=read_selected(h,[],model,settings,definition,runtime_identity=identity())
    times=[sample['time_s'] for sample in h['samples']]
    for pair,raw in enumerate(([0.,2.,1.],[0.,-4.,-2.])):
        for k,component in enumerate(('FNX','FNY','FNZ','FTX','FTY','FTZ'),1):
            native=selected[f'PAIR{pair}_native_impulse_{component}'];force=selected[f'PAIR{pair}_force_{component}']
            integral=selected[f'PAIR{pair}_sampled_impulse_{component}']
            assert native['value']==[v*k for v in raw] and native['unit']=='N s'
            assert native['metadata']['origin']=='NATIVE'
            expected=[(raw[1]-raw[0])*k/(times[1]-times[0]),(raw[2]-raw[0])*k/(times[2]-times[0]),(raw[2]-raw[1])*k/(times[2]-times[1])]
            assert force['value']==pytest.approx(expected) and force['unit']=='N'
            assert force['metadata']['origin']=='DERIVED' and force['metadata']['instantaneous_force'] is False
            assert integral['value']==sampled_integral(times,force['value'])
            assert integral['metadata']['exact_solver_impulse'] is False and integral['value']!=native['value']
            assert native['metadata']['pair_member_id']==next(g['members'][0] for g in definition['outputs']['groups'] if g.get('contact_index')==pair)
    json.dumps({'responses':selected,'record':record},allow_nan=False)


def test_unpinned_runtime_or_wrong_channel_identity_does_not_promote_stored_values(tmp_path,compiled):
    settings,model,_,_,_,definition=compiled;h=history(tmp_path,definition['outputs']['groups'])
    for runtime in (None,{**identity(),'source_tag':'other'},{**identity(),'files':{}}):
        selected,_=read_selected(h,[],model,settings,definition,runtime_identity=runtime)
        assert all(not value['value'] and value['metadata']['status']=='UNKNOWN' for name,value in selected.items() if name.startswith('PAIR'))
    wrong=deepcopy(h)
    next(g for g in wrong['layout']['groups'] if g['type']==101)['variables'][0]=777
    selected,_=read_selected(wrong,[],model,settings,definition,runtime_identity=identity())
    assert not selected['PAIR0_force_FNX']['value']


def test_secants_never_bridge_missing_value_or_original_row_gap():
    assert impulse_secants([0.,.1,.4],[0.,2.,1.],source_rows=[0,1,3])[0]==[20.,None,None]
    assert impulse_secants([0.,.1,.4],[0.,None,1.])[0]==[None,None,None]
    assert impulse_secants([0.],[123.])[0]==[None]
    assert sampled_integral([0.,.1,.4],[20.,None,-2.])==[0.,None,None]


def test_old_pair_card_or_metadata_cannot_choose_another_contact(compiled):
    settings,model,_,_,text,definition=compiled;changed=deepcopy(definition)
    pair=next(g for g in changed['outputs']['groups'] if g['kind']=='pair')
    pair['contact_index']=1
    with pytest.raises(ValueError,match='pair receipt'):impact_b.verify(text,model,settings,changed)


@pytest.mark.parametrize('mode',['normal','prefix_gap'])
def test_existing_owner_pair_selection_save_and_cold_without_runtime_or_new_solver(tmp_path,monkeypatch,compiled,mode):
    import subprocess,sys
    from test_impact_b_retained import template,change,wait
    from caelab.adapters import impact
    from caelab.storage import canonical_hash,save_json
    from caelab.workbench import Workbench
    source=tmp_path/'original-attempt';settings,result=template(source,compiled,mode)
    result['diagnostics']['runtime']=identity()
    _,model,_,physics,_,definition=compiled
    from caelab.adapters.impact_results import read_vtk
    if mode=='normal':
        frames=[(path,read_vtk(path)) for path in sorted((source/'native').glob('frame*.vtk'))]
        impact_b.append_readback(source,model,settings,result,frames)
    save_json(source/'impact_execution.json',result)
    native_hash=canonical_hash({'responses':result['responses'],'original_status':result['execution_status']})
    if mode=='normal':assert result['responses']['PAIR0_native_impulse_FNX']['value']==[3.,4.,5.]
    runtimes=[]
    def controlled(self,settings,*,output,runtime=None):
        import shutil
        from caelab.impact_retained import reference
        runtimes.append(deepcopy(runtime))
        shutil.copytree(source,output,dirs_exist_ok=True)
        value=deepcopy(result);value['diagnostics']['native_outcome']=reference(output)
        return value
    def forbidden(*args,**kwargs):raise AssertionError('No solver/converter/runtime probe for retained pair owner check')
    monkeypatch.setattr(impact.ImpactAdapter,'run',controlled);monkeypatch.setattr(impact,'selected_runtime',forbidden)
    monkeypatch.setattr(impact,'run_owned_command',forbidden)
    for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):monkeypatch.setenv(key,'1')
    workspace=tmp_path/'workspace';wb=Workbench(workspace,configuration={'workers':1})
    try:
        wb.simulation_documents.submit=lambda operation,arguments,**kwargs:wb.submit(operation,arguments,resources={'threads':1},**kwargs)
        doc=wb.document_open(kind='simulation',draft={'backend':impact.domain.BACKEND,'settings':settings})
        reply=change(wb,doc,'simulation.evaluate');doc=reply['document'];job=wait(wb,reply['job'])
        assert job['state']==('SUCCEEDED' if mode=='normal' else 'FAILED')
        assert runtimes==[{'threads':1}]
        original=job
        if mode!='normal':
            reply=change(wb,doc,'simulation.reprocess',{'source_job_id':job['id']});doc=reply['document'];job=wait(wb,reply['job'])
            assert job['state']=='FAILED' and wb.manager.status(original['id'])['state']=='FAILED'
        names=['PAIR0_native_impulse_FNX','PAIR0_force_FNX','PAIR1_force_FTY','PAIR0_sampled_impulse_FNX']
        selected=wb.document_result(doc['id'],job['id'],selection={'responses':names})
        assert set(selected['responses'])==set(names)
        assert selected['responses'][names[0]]['metadata']['origin']=='NATIVE'
        if mode!='normal':
            assert selected['source_execution_status']=='FAILED'
            assert selected['responses'][names[0]]['value']==[3.,4.]
            assert selected['responses'][names[1]]['has_calculation_gaps']
            assert selected['diagnostics']['readback_scopes']['b_pair']['status']=='PARTIAL'
        assert selected['responses'][names[1]]['metadata']['origin']=='DERIVED'
        assert selected['responses'][names[2]]['metadata']['pair_member_id']!=selected['responses'][names[1]]['metadata']['pair_member_id']
        doc=change(wb,doc,'document.save')['document'];docid=doc['id'];jobid=job['id']
        expected=canonical_hash(wb.document_result(docid,jobid,selection={'responses':names}));jobs=len(wb.manager.list())
    finally:assert wb.shutdown()['joined']
    import shutil
    shutil.rmtree(workspace/'workbench/results'/jobid)
    program="""
import sys,json
from caelab.storage import canonical_hash
from caelab.workbench import Workbench
from caelab.adapters import impact
def forbidden(*args,**kwargs):raise AssertionError('Cold read cannot calculate or resolve runtime')
impact.ImpactAdapter.run=forbidden;impact.selected_runtime=forbidden;impact.run_owned_command=forbidden
wb=Workbench(sys.argv[1],configuration={'workers':1})
try:
 wb.document_open(kind='simulation',document_id=sys.argv[2])
 selected=wb.document_result(sys.argv[2],sys.argv[3],selection={'responses':json.loads(sys.argv[6])})
 assert canonical_hash(selected)==sys.argv[4]
 assert len(wb.manager.list())==int(sys.argv[5])
finally:assert wb.shutdown()['joined']
"""
    cold=subprocess.run([sys.executable,'-c',program,str(workspace),docid,jobid,expected,str(jobs),json.dumps(names)],capture_output=True,text=True,timeout=30)
    assert cold.returncode==0,cold.stdout+cold.stderr
    assert canonical_hash({'responses':result['responses'],'original_status':result['execution_status']})==native_hash


@pytest.mark.parametrize('threads',[True,0,-1,1.5,65])
def test_impact_operator_thread_validation_before_input_or_native(tmp_path,threads):
    from caelab.adapters.impact import ImpactAdapter
    with pytest.raises(ValueError,match='runtime threads'):
        ImpactAdapter().run({},output=tmp_path/'not-created',runtime={'threads':threads})
    assert not (tmp_path/'not-created').exists()
