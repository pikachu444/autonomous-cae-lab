"""Existing Simulation ownership with SYNTHETIC bytes, not native B acceptance."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

import pytest

from impact_b_fixtures import compile_fixture,history_bytes,vtk_bytes
from caelab.adapters import impact
from caelab.adapters.impact_results import GLOBAL_NAMES
from caelab.impact_bulk_history import read
from caelab.impact_retained import artifact_receipt,reference
from caelab.storage import canonical_hash,save_json
from caelab.workbench import Workbench


@pytest.fixture(scope='module')
def compiled(tmp_path_factory):
    return compile_fixture(tmp_path_factory.mktemp('b-cards'))


def template(root,compiled,mode):
    s,model,initial,physics,text,definition=deepcopy(compiled)
    native=root/'native';native.mkdir(parents=True)
    save_json(root/'input.json',s);save_json(root/'initial_conditions.json',initial)
    save_json(root/'physical_admission.json',{'physics':physics})
    save_json(root/'damage_definition.json',definition['cohesive'])
    save_json(root/'b_definition.json',definition)
    (native/'impact_0000.rad').write_text(text,encoding='ascii')
    data,titles,_=history_bytes(definition['outputs']['groups'])
    (native/'impactT01').write_bytes(data);(native/'impactT01_TITLES').write_bytes(titles)
    h=read(native/'impactT01',titles=native/'impactT01_TITLES')
    stream=io.StringIO(newline='');writer=csv.writer(stream)
    width=sum(len(g['members'])*len(g['tokens']) for g in definition['outputs']['groups'])
    writer.writerow(['time',*GLOBAL_NAMES,*['SYNTHETIC_GROUP_'+str(i) for i in range(width)]])
    for row in h['samples']:
        values=[row['time_s'],*row['globals']]
        for group in definition['outputs']['groups']:values.extend(row['groups'][str(group['id'])])
        writer.writerow([format(v,'.6e') for v in values])
    (native/'history.csv').write_bytes(stream.getvalue().encode('ascii'))
    for i,t in enumerate((0.,.0001,.0003)):
        (native/f'frame{i:04d}.vtk').write_bytes(vtk_bytes(model,t,cohesive_active=0 if i==2 else 1))
    result={'execution_status':'SUCCEEDED','responses':{},'checks':[],
            'diagnostics':{'source_sha256':canonical_hash(s['source']),
                           'native_execution_status':'SYNTHETIC_NOT_NATIVE'}}
    frames=[]
    impact.read_outputs(root,s,model,physics,definition['cohesive'],result,frames,name='impact')
    assert result['responses']['BULK_ACTIVE']['value']==[1.,1.,0.]
    assert result['responses']['BOND_FACE']['metadata']['origin']=='DERIVED'
    assert result['responses']['BOND_ACTIVE']['metadata']['origin']=='NATIVE'
    if mode!='normal':
        result['execution_status']='FAILED';result['responses']={};result['post_artifacts']=[]
        if mode=='prefix_gap':
            (native/'impactT01').write_bytes(data[:-13]);(native/'frame0001.vtk').write_bytes(b'SYNTHETIC_BROKEN_FRAME')
        elif mode=='missing_channel':
            (native/'impactT01_TITLES').write_bytes(titles.replace(b'DAMA',b'FAKE'))
        elif mode=='no_definition':(root/'b_definition.json').unlink()
    result['retained_native']=artifact_receipt(root,frames)
    save_json(root/'impact_execution.json',result)
    return s,result


def change(wb,doc,operation,args=None):
    return wb.document_command(doc['id'],operation,args or {},session_id=doc['session_id'],
        expected_generation=doc['generation'],command_id='C'+uuid.uuid4().hex)


def wait(wb,job):
    end=time.monotonic()+20
    while time.monotonic()<end:
        current=wb.manager.status(job['id'])
        if current['state'] in ('SUCCEEDED','FAILED','CANCELLED','PARTIAL_FAILURE','INTERRUPTED'):return current
        time.sleep(.01)
    raise AssertionError('Owned reader did not finish')


def test_normal_b_reader_does_not_admit_a_partial_or_wrong_title(tmp_path,compiled):
    s,_=template(tmp_path,compiled,'normal')
    _,model,_,physics,_,definition=compiled
    path=tmp_path/'native/impactT01_TITLES'
    path.write_bytes(path.read_bytes().replace(b'DAMA',b'FAKE'))
    with pytest.raises(ValueError,match='membership|title|group'):
        impact.read_outputs(tmp_path,s,model,physics,definition['cohesive'],
                            {'responses':{},'diagnostics':{}},[],name='impact')


@pytest.mark.parametrize('mode',['normal','prefix_gap','missing_channel','no_definition','pin_damage'])
def test_existing_owner_b_select_partial_pin_save_cold(tmp_path,monkeypatch,compiled,mode):
    source=tmp_path/'template';s,record=template(source,compiled,'normal' if mode=='pin_damage' else mode)
    assert ('b_definition.json' in record['retained_native']['input_artifacts'])==(mode!='no_definition')
    def controlled(self,settings,*,output,runtime=None):
        shutil.copytree(source,output,dirs_exist_ok=True)
        if mode=='pin_damage':
            path=Path(output)/'b_definition.json';path.write_bytes(path.read_bytes()+b' ')
        result=deepcopy(record);result['diagnostics']['native_outcome']=reference(output)
        return result
    def forbidden(*a,**k):raise AssertionError('No solver/converter/runtime probe in B reader check')
    monkeypatch.setattr(impact.ImpactAdapter,'run',controlled)
    monkeypatch.setattr(impact,'selected_runtime',forbidden)
    monkeypatch.setattr(impact,'run_owned_command',forbidden)
    monkeypatch.setattr('caelab.impact_recovery.run_owned_command',forbidden)
    workspace=tmp_path/'workspace';wb=Workbench(workspace,configuration={'workers':1})
    try:
        doc=wb.document_open(kind='simulation',draft={'backend':impact.domain.BACKEND,'settings':s})
        reply=change(wb,doc,'simulation.evaluate');doc=reply['document'];original=wait(wb,reply['job'])
        assert original['state']==record['execution_status'],original
        original_hash=canonical_hash(wb.document_result(doc['id'],original['id'],selection={'metadata_only':True}))
        if mode=='normal':
            selected=wb.document_result(doc['id'],original['id'],selection={'responses':['BULK_ACTIVE','BOND_FACE']})
            assert selected['responses']['BULK_ACTIVE']['value']==[1.,1.,0.]
            assert selected['responses']['BOND_FACE']['metadata']['origin']=='DERIVED'
        reply=change(wb,doc,'simulation.reprocess',{'source_job_id':original['id']})
        doc=reply['document'];derived=wait(wb,reply['job'])
        result=wb.document_result(doc['id'],derived['id'])
        assert result['operation_kind']=='READBACK_ONLY' and result['solver_execution']=='NOT_PERFORMED'
        assert result['source_execution_status']==record['execution_status']
        assert derived['state']==('SUCCEEDED' if mode=='normal' else 'FAILED')
        scopes=result['diagnostics'].get('readback_scopes',{})
        if mode=='pin_damage':
            assert 'hash/size' in result['diagnostics']['readback_error']
            assert not any(name.startswith('BULK_') for name in result['responses'])
        elif mode=='no_definition':
            assert scopes['b_definition']['status']=='UNKNOWN'
            assert not any(name.startswith(('BULK_','BOND_')) for name in result['responses'])
        elif mode=='missing_channel':
            assert scopes['b_bulk']['status']=='UNKNOWN'
            assert result['responses']['BOND_ACTIVE']['value']==[1.,1.,0.]
            assert result['responses']['global_2']['value']
        else:
            assert result['responses']['BULK_ACTIVE']['metadata']['origin']=='NATIVE'
            assert result['responses']['BOND_FACE']['metadata']['origin']=='DERIVED'
            assert result['responses']['BULK_ACTIVE']['metadata']['reader_operation']=='READBACK_ONLY'
            if mode=='prefix_gap':
                active=result['responses']['BOND_ACTIVE']
                assert active['source_rows']==[0,2] and len(active['segments'])==2
                assert active['raw_samples']['gap_before']==[False,True]
                assert result['responses']['BULK_ACTIVE']['value']==[1.,1.]
                assert scopes['b_bulk']['excluded_tail'] and scopes['b_interface']['unavailable_frames']
        assert canonical_hash(wb.document_result(doc['id'],original['id'],selection={'metadata_only':True}))==original_hash
        doc=change(wb,doc,'document.save')['document'];docid=doc['id'];jobid=derived['id']
        expected=canonical_hash(wb.document_result(docid,jobid));count=len(wb.manager.list())
    finally:assert wb.shutdown()['joined']
    # A new interpreter reopens the saved owner; computation is forbidden.
    program="""
import sys
from caelab.storage import canonical_hash
from caelab.workbench import Workbench
from caelab.adapters import impact
def forbidden(*a,**k):raise AssertionError('Cold read cannot calculate or probe runtime')
impact.ImpactAdapter.run=forbidden
impact.selected_runtime=forbidden
impact.run_owned_command=forbidden
wb=Workbench(sys.argv[1],configuration={'workers':1})
try:
    wb.document_open(kind='simulation',document_id=sys.argv[2])
    value=wb.document_result(sys.argv[2],sys.argv[3])
    assert canonical_hash(value)==sys.argv[4]
    assert len(wb.manager.list())==int(sys.argv[5])
finally:assert wb.shutdown()['joined']
"""
    cold=subprocess.run([sys.executable,'-c',program,str(workspace),docid,jobid,expected,str(count)],
                        capture_output=True,text=True,timeout=30)
    assert cold.returncode==0,cold.stdout+cold.stderr
