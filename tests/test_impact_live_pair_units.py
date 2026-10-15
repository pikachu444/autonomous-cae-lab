"""Completed live unit proof and retained re-read share exact checks; no native solve."""
from copy import deepcopy
import json,struct,shutil
from pathlib import Path
import pytest
from caelab import impact_b
from caelab.impact_bulk_history import completed_pair_units,retained_pair_units,read
from caelab.dynamic_result_store import file_pin
from caelab.storage import save_json
from caelab.adapters.impact import starter_admission
from caelab.impact_retained import artifact_receipt
from examples.impact.pair_response import settings
from impact_b_fixtures import compile_fixture,rec,ints,floats,title
from test_impact_pair_csv import identity


@pytest.fixture(scope='module')
def compiled(tmp_path_factory):return compile_fixture(tmp_path_factory.mktemp('live-pair-compile'),settings())


def attempt(root,compiled):
    s,m,i,physics,deck,definition=deepcopy(compiled);native=root/'native';native.mkdir()
    save_json(root/'input.json',s);save_json(root/'b_definition.json',definition)
    (native/'impact_0000.rad').write_text(deck,encoding='ascii')
    groups=definition['outputs']['groups']
    data=rec(struct.pack('>i',3040)+title('SYNTHETIC_LIVE_BOUNDARY_NOT_SOLVER',80))+rec(b' '*80)
    data+=ints(0,0,0,0,len(groups),23)+ints(*range(1,24));titles=[]
    for g in groups:
        data+=rec(struct.pack('>5i',g['id'],g['type'],0,len(g['members']),len(g['tokens']))+title(g['title'],40))
        for member in g['members']:
            data+=rec(struct.pack('>i',member)+title('IMPACT1',40))
            for token in g['tokens']:titles.extend([f"{g['type']:10d}",f'{token:<10}'])
        data+=ints(*range(1,len(g['tokens'])+1))
    for n,t in enumerate((0.,.0001,.0003)):
        data+=floats(t)+floats(*([0.]*23))
        for g in groups:data+=floats(*[float(n*(j+1)) for j in range(len(g['tokens']))])
    (native/'impactT01').write_bytes(data);(native/'impactT01_TITLES').write_text('\n'.join(titles)+'\n',encoding='ascii')
    (native/'impact_0000.out').write_text('NORMAL TERMINATION\nNO SYNTAX ERROR DETECTED\n0 ERROR(S)\n0 WARNING(S)\nNUMNOD: 8\nWORK UNIT SYSTEM ( Mg , mm , s ) 1E3 1E-3 1E0\nINPUT UNIT SYSTEM ( Mg , mm , s ) 1E3 1E-3 1E0\n',encoding='ascii')
    for label in ('starter','engine'):
        save_json(native/(label+'.execution.json'),{'status':'COMPLETED','return_code':0,'tree_ownership':'WINDOWS_JOB','synthetic_boundary_test':True})
    execution={'execution_status':'SUCCEEDED','checks':[starter_admission(native/'impact_0000.out',m)],
        'diagnostics':{'runtime':identity(),'native_execution_status':'SUCCEEDED','native_termination':{'status':'NORMAL','synthetic_boundary_test':True}}}
    return s,m,execution


def test_first_read_without_execution_record_and_retained_read_have_same_exact_values(tmp_path,compiled):
    s,m,execution=attempt(tmp_path,compiled)
    assert not (tmp_path/'impact_execution.json').exists()
    proof=completed_pair_units(tmp_path,m,s,execution)
    impact_b.append_readback(tmp_path,m,s,execution,[],unit_evidence=proof)
    assert all(len(r['value'])==3 and r['metadata'].get('status')!='UNKNOWN' for r in execution['responses'].values())
    assert all(r['metadata']['legacy_unit_evidence']['source_execution_record']=='NOT_YET_PUBLISHED' for r in execution['responses'].values())
    assert not (tmp_path/'impact_execution.json').exists()
    expected={name:r['value'] for name,r in execution['responses'].items()}
    execution['retained_native']=artifact_receipt(tmp_path,[])
    save_json(tmp_path/'impact_execution.json',execution)
    pin=file_pin(tmp_path,tmp_path/'impact_execution.json')
    shutil.copyfile(tmp_path/'impact_execution.json',tmp_path/'original_execution.json')
    reread={'execution_status':'SUCCEEDED','source_execution_status':'SUCCEEDED','checks':[],
        'diagnostics':{'runtime':identity(),'original_execution_record':pin}}
    impact_b.append_readback(tmp_path,m,s,reread,[],partial=True)
    assert {name:r['value'] for name,r in reread['responses'].items()}==expected
    assert all('execution_pin' in r['metadata']['legacy_unit_evidence'] for r in reread['responses'].values())


@pytest.mark.parametrize('bad',['runtime','check','input','native_status','termination','cleanup','command_missing','command_failed','command_bool'])
def test_missing_or_wrong_live_evidence_does_not_promote_pair(tmp_path,compiled,bad):
    s,m,e=attempt(tmp_path,compiled)
    if bad=='runtime':e['diagnostics']['runtime']['files']={}
    elif bad=='check':e['checks'][0]['units']='kg/m/s'
    elif bad=='input':save_json(tmp_path/'input.json',{**s,'qualification':'DIFFERENT'})
    elif bad=='native_status':e['diagnostics']['native_execution_status']='STARTED'
    elif bad=='termination':e['diagnostics']['native_termination']['status']='FAILED'
    elif bad=='cleanup':e['diagnostics']['cleanup_unconfirmed']=True
    elif bad=='command_missing':(tmp_path/'native/engine.execution.json').unlink()
    else:save_json(tmp_path/'native/engine.execution.json',{'status':'COMPLETED','return_code':False if bad=='command_bool' else 1,'tree_ownership':'WINDOWS_JOB'})
    with pytest.raises((ValueError,OSError)):completed_pair_units(tmp_path,m,s,e)
    impact_b.append_readback(tmp_path,m,s,e,[],unit_evidence={'units':'Mg/mm/s','status':'PASS'})
    assert all(not r['value'] and r['metadata']['status']=='UNKNOWN' for r in e['responses'].values())
