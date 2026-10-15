"""Accurate tetra timestep generation and native byte editing; no native solve."""
from copy import deepcopy
from pathlib import Path
import json,shutil,subprocess,sys
import pytest
from caelab import impact_model,impact_native
from caelab.impact_source import capture,SourceError
from caelab.impact_input_edits import edited_files,original_files,apply_hunks
from caelab.storage import canonical_hash
from examples.impact.pair_response import settings as pair_settings
from test_impact_elastic_tetra_formulation import converted,simple_settings
ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'examples/impact/input_a/native'


def test_public_preview_matches_verified_effective_formulation(tmp_path):
    s,m,i,text,raw=converted(tmp_path,pair_settings());before=deepcopy(s)
    from caelab.adapters.impact_admission import normalize_elastic_tetra4,validate_physics
    text,_=normalize_elastic_tetra4(text,m,i,s);physics=validate_physics(text,m,i,s)
    public=impact_model.engine_deck(s)
    assert impact_model.engine_deck(s,model=m,physics=physics)==public
    lines=public.splitlines();scale=format(.9,'.17g')+' 0'
    assert lines[lines.index('/DT')+1]==lines[lines.index('/DT1/BRICK/STOP')+1]==scale
    receipt=impact_model.engine_timestep(s,model=m,physics=physics)
    assert receipt['element_ids']==[1,2] and receipt['effective_Itetra4']==1000
    assert s==before
    for broken in ({}, {**physics,'effective_formulation':{'Itetra4_by_element':{'1':3,'2':1000}}}):
        with pytest.raises(ValueError,match='admitted original'):impact_model.engine_deck(s,model=m,physics=broken)


@pytest.mark.parametrize('kind,plastic,mixed',[('C3D8',False,False),('C3D10',False,False),('C3D4',True,False),('C3D4',False,True)])
def test_other_element_material_or_mixed_route_is_unchanged(kind,plastic,mixed):
    s=simple_settings(kind,plastic,mixed);before=deepcopy(s)
    assert '/DT1' not in impact_model.engine_deck(s)
    assert s==before


def test_cohesive_mass_scaling_and_native_source_not_automatically_changed():
    from impact_b_fixtures import settings
    s=settings();assert '/DT1' not in impact_model.engine_deck(s)
    s=pair_settings();s['time'].update(mass_scaling=True,target_step_s=1e-7)
    deck=impact_model.engine_deck(s)
    assert '/DT/NODA/CST/0' in deck and '/DT1' not in deck
    s=impact_native.settings_from_source(capture(NATIVE/'impact_0000.rad',NATIVE,engine=NATIVE/'impact_0001.rad',units='Mg/mm/s'))
    assert '/DT1' not in impact_model.engine_deck(s)
    assert all(raw==original_files(s['source'])[name] for name,raw in edited_files(s['source']).items())


def native_dt1(folder,*,suffix=None,global_scale=.5,solid_scale=.5,minimum=0):
    shutil.copytree(NATIVE,folder)
    engine=folder/'impact_0001.rad';raw=engine.read_bytes()
    old=b'0.50000000000000000 0';assert old in raw
    raw=raw.replace(old,(format(global_scale,'.17g')+' 0').encode())
    card=('/DT1/BRICK/STOP\r\n'+format(solid_scale,'.17g')+' '+str(minimum)+'\r\n').encode()
    if suffix is not None:card=suffix
    raw=raw.replace(b'/ANIM/DT',card+b'/ANIM/DT');engine.write_bytes(raw)
    return capture(folder/'impact_0000.rad',folder,engine=engine,units='Mg/mm/s')


@pytest.mark.parametrize('card',[b'/DT1/BRICK/STOP\r\n.5 0\r\n/DT1/BRICK/STOP\r\n.5 0\r\n',
    b'/DT1/BRICK/STOP\r\n.5\r\n',b'/DT1/BRICK/STOP\r\n.5 1e-8\r\n',
    b'/DT1/BRICK/STOP\r\n.9 0\r\n',b'/DT1/BRICK/STOP\r\n.5 0 0\r\n',
    b'/DT1/BRICK/CST\r\n.5 0\r\n'])
def test_native_ambiguous_duplicate_minimum_mismatch_and_other_dt1_are_blocked(tmp_path,card):
    source=native_dt1(tmp_path/'native',suffix=card)
    with pytest.raises(SourceError):impact_native.settings_from_source(source)


def test_native_mass_scaling_and_old_tetra_formulation_cannot_take_dt1(tmp_path):
    source=native_dt1(tmp_path/'native')
    files=original_files(source);name='impact_0001.rad';raw=files[name]
    from caelab.impact_input_edits import replace_range
    start=raw.index(b'/DT\r\n')
    changed=replace_range(source,name,start,start+3,'/DT/NODA/CST/0',reason='UNIT mass scaling mismatch',expected_source_sha256=canonical_hash(source))
    with pytest.raises(SourceError):impact_native.settings_from_source(changed)
    name=next(k for k,v in files.items() if b'      1000        -1' in v);raw=files[name]
    start=raw.index(b'      1000        -1')
    changed=replace_range(source,name,start,start+10,'         3',reason='UNIT old tetra',expected_source_sha256=canonical_hash(source))
    with pytest.raises(SourceError,match='1000'):impact_native.settings_from_source(changed)


def test_native_scale_edit_updates_both_exact_fields_and_original_restore(tmp_path):
    source=native_dt1(tmp_path/'native');s=impact_native.settings_from_source(source)
    parsed=impact_native.parse_source(source);fields=[f for f in parsed['fields'] if f['field']=='scale']
    assert len(fields)==2 and s['time']['scale']==.5
    assert all(f['label']=='전체·고체 시간증분 계수 함께 변경' for f in fields)
    for chosen in fields:
        changed=impact_native.edit_field(s,chosen['id'],.9,reason='명시 공통 scale 편집',expected_source_sha256=canonical_hash(source))
        assert changed['time']['scale']==.9 and changed['source']['bundle']==source['bundle']
        assert len(changed['source']['edits'])==2
        emitted=edited_files(changed['source'])
        for name,raw in original_files(source).items():
            expected=raw
            for h in sorted((h for h in changed['source']['edits'] if h['file']==name),key=lambda h:h['start'],reverse=True):
                expected=expected[:h['start']]+h['after'].encode('ascii')+expected[h['end']:]
            assert emitted[name]==expected
        impact_native.export_direct(changed,tmp_path/('export'+str(fields.index(chosen))))
        restored=apply_hunks(changed['source'],[],expected_source_sha256=canonical_hash(changed['source']))
        assert edited_files(restored)==original_files(source)
        assert impact_native.settings_from_source(restored)['time']['scale']==.5


def test_existing_document_edit_undo_save_and_new_process_without_solver(tmp_path,monkeypatch):
    from caelab.workbench import Workbench
    from caelab.adapters import impact
    def forbidden(*a,**k):raise AssertionError('No native/model/runtime execution in document check')
    monkeypatch.setattr(impact,'selected_runtime',forbidden);monkeypatch.setattr(impact,'run_owned_command',forbidden)
    source=native_dt1(tmp_path/'native');s=impact_native.settings_from_source(source)
    f=next(f for f in impact_native.parse_source(source)['fields'] if f['card']=='/DT1/BRICK/STOP')
    changed=impact_native.edit_field(s,f['id'],.9,reason='문서 scale 편집',expected_source_sha256=canonical_hash(source))
    workspace=tmp_path/'workspace';wb=Workbench(workspace,configuration={'workers':1})
    try:
        doc=wb.document_open(kind='simulation',draft={'backend':impact_model.BACKEND,'settings':s})
        def command(op,args=None):
            nonlocal doc
            doc=wb.document_command(doc['id'],op,args or {},session_id=doc['session_id'],expected_generation=doc['generation'])['document']
        command('simulation.update',{'draft':{'backend':impact_model.BACKEND,'settings':changed}})
        command('document.undo');assert doc['draft']['settings']==s
        command('document.redo');assert doc['draft']['settings']==changed
        command('document.save');docid=doc['id'];digest=canonical_hash(changed)
        assert len(wb.manager.list())==0
    finally:assert wb.shutdown()['joined']
    program="""
import sys
from caelab.workbench import Workbench
from caelab.storage import canonical_hash
from caelab.impact_native import parse_source,edit_field,export_direct
from caelab.adapters import impact
def forbidden(*a,**k):raise AssertionError('Cold source edit cannot execute')
impact.selected_runtime=forbidden;impact.run_owned_command=forbidden
wb=Workbench(sys.argv[1],configuration={'workers':1})
try:
 d=wb.document_open(kind='simulation',document_id=sys.argv[2]);s=d['draft']['settings'];assert canonical_hash(s)==sys.argv[3]
 f=next(f for f in parse_source(s['source'])['fields'] if f['card']=='/DT')
 edited=edit_field(s,f['id'],.8,reason='cold 명시 scale 편집',expected_source_sha256=canonical_hash(s['source']))
 assert edited['time']['scale']==.8
 export_direct(edited,sys.argv[4]);assert len(wb.manager.list())==0
 print('COLD_SOURCE_SAME_REEDIT_EXPORT_NEW_JOBS_0')
finally:assert wb.shutdown()['joined']
"""
    cold=subprocess.run([sys.executable,'-c',program,str(workspace),docid,digest,str(tmp_path/'cold-export')],capture_output=True,text=True,timeout=30)
    assert cold.returncode==0,cold.stdout+cold.stderr


def test_adapter_and_public_preview_emit_identical_deck_and_receipt(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from caelab.adapters import impact
    s=pair_settings();before=deepcopy(s);calls=[]
    monkeypatch.setattr(impact,'selected_runtime',lambda:({'starter':'NO_NATIVE_STARTER','engine':'NO_NATIVE_ENGINE'},{},{'controlled_boundary':True}))
    def command(argv,folder,label,**kwargs):
        calls.append(label)
        if label=='convert':return subprocess.run(argv,cwd=folder,capture_output=True,timeout=30)
        assert label=='starter'
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(impact,'run_owned_command',command)
    output=tmp_path/'adapter';result=impact.ImpactAdapter().run(s,output=output,runtime={'threads':1})
    assert calls==['convert','starter'] and result['execution_status']=='FAILED'
    receipt=json.loads((output/'physical_admission.json').read_text(encoding='utf8'))
    assert receipt['solid_timestep']['applied'] and receipt['solid_timestep']['solid_scale']==.9
    assert (output/'native/impact_0001.rad').read_text(encoding='ascii')==impact_model.engine_deck(s)
    assert s==before


@pytest.mark.parametrize('scale',[0.,float('nan')])
def test_native_dt1_invalid_scale_is_not_admitted(tmp_path,scale):
    source=native_dt1(tmp_path/'native',global_scale=scale,solid_scale=scale)
    with pytest.raises(SourceError):impact_native.settings_from_source(source)


def test_inp_document_save_and_cold_engine_preview_same_without_jobs(tmp_path):
    from caelab.workbench import Workbench
    s=pair_settings();expected=impact_model.engine_deck(s);wb=Workbench(tmp_path/'workspace',configuration={'workers':1})
    try:
        doc=wb.document_open(kind='simulation',draft={'backend':impact_model.BACKEND,'settings':s})
        saved=wb.document_command(doc['id'],'document.save',{},session_id=doc['session_id'],expected_generation=doc['generation'])['document']
        assert saved['draft']['settings']==s and len(wb.manager.list())==0
    finally:assert wb.shutdown()['joined']
    script="""
import sys
from caelab.workbench import Workbench
from caelab.impact_model import engine_deck
wb=Workbench(sys.argv[1],configuration={'workers':1})
try:
 d=wb.document_open(kind='simulation',document_id=sys.argv[2])
 assert engine_deck(d['draft']['settings'])==sys.argv[3]
 assert d['draft']['settings']['time']['scale']==.9 and len(wb.manager.list())==0
finally:assert wb.shutdown()['joined']
"""
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path/'workspace'),doc['id'],expected],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
