"""Native elastic pair source/selection roundtrip; no solver or converter."""
from copy import deepcopy
from pathlib import Path
import json
import subprocess
import sys
import struct
import pytest

from caelab import impact_native,impact_native_b,impact_model
from caelab.impact_source import capture,SourceError
from caelab.impact_input_edits import edited_files,replace_range
from caelab.storage import canonical_hash

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'examples/impact/input_a/native_pair'


def settings():
    return impact_native.settings_from_source(capture(FIXTURE/'impact_0000.rad',FIXTURE,
        engine=FIXTURE/'impact_0001.rad',units='Mg/mm/s'))


def test_actual_generated_source_maps_exact_pair_and_exports_unchanged(tmp_path):
    s=settings();p=impact_native.parse_source(s['source']);d=p['b_definition']
    assert len(d['outputs']['groups'])==1 and 'b_responses' not in s
    g=d['outputs']['groups'][0]
    assert (g['id'],g['members'],g['contact_index'],g['type'])==(16,[1],0,101)
    assert g['tokens']==['FNX','FNY','FNZ','FTX','FTY','FTZ']
    assert g['surface_order']=={'surface1':'UPPER_FACE','surface2':'LOWER_FACE'}
    assert d['native_acceptance']=='NOT_RUN'
    impact_native.export_direct(s,tmp_path/'export')
    for name,raw in edited_files(s['source']).items():assert (tmp_path/'export'/name).read_bytes()==raw


@pytest.mark.parametrize('old,new',[
    ('         1\n/END','         2\n/END'),
    ('         1\n/END','         1         2\n/END'),
    ('FNX       FNY','FNX       FNX'),
    ('FNX       FNY','FTX       FNY'),
    ('FTZ       \n','FTZ       EXTRA\n'),
    ('B_PAIR_1\n','\n'),
    ('/END','/TH/INTER/17\nOTHER\nFNX       FNY       FNZ       FTX       FTY       FTZ       \n         1\n/END'),
    ('/TH/INTER/16','/TH/BRIC/16'),
    ('/MAT/ELAST/1','/MAT/LAW36/1'),
])
def test_invalid_native_output_or_unsupported_material_is_not_silently_ignored(old,new):
    s=settings();source=s['source'];raw=edited_files(source)['impact_0000.rad'];text=raw.decode('ascii')
    assert old in text
    at=text.index(old)
    source=replace_range(source,'impact_0000.rad',at,at+len(old),new,
        reason='반례: 정확한 원 카드 변경',expected_source_sha256=canonical_hash(source))
    with pytest.raises((SourceError,ValueError)):impact_native.settings_from_source(source)


def test_explicit_response_edit_preserves_source_and_unrelated_selections():
    s=settings();before=edited_files(s['source'])
    s=impact_native_b.select_response(s,native_contact_id=1,quantity='native_impulse',component='FNZ',name='pair_j')
    s=impact_native_b.select_response(s,native_contact_id=1,quantity='force',component='FNZ',name='pair_f')
    s=impact_native_b.select_response(s,native_contact_id=1,quantity='force',component='FNX',name='pair_f',replace_name='pair_f')
    assert [r['component'] for r in s['b_responses']]==['FNZ','FNX']
    assert edited_files(s['source'])==before
    f=next(f for f in impact_native.parse_source(s['source'])['fields'] if f['field']=='end_s')
    changed=impact_native.edit_field(s,f['id'],.0031,reason='명시 종료 시각',expected_source_sha256=canonical_hash(s['source']))
    assert changed['b_responses']==s['b_responses'] and changed['time']['end_s']==.0031
    impact_native.validate_settings(changed)
    with pytest.raises(ValueError):impact_native_b.select_response(s,native_contact_id=2,quantity='force',component='FNX',name='absent')
    with pytest.raises(ValueError):impact_native_b.select_response(s,native_contact_id=True,quantity='force',component='FNX',name='absent')


def test_missing_history_card_does_not_enable_pair_or_bulk_selection():
    s=settings();source=s['source'];text=edited_files(source)['impact_0000.rad'].decode('ascii')
    start=text.index('/TH/INTER/16');end=text.index('/END',start)
    source=replace_range(source,'impact_0000.rad',start,end,'',reason='반례 출력 없음',expected_source_sha256=canonical_hash(source))
    no_card=impact_native.settings_from_source(source)
    assert impact_native.parse_source(source)['b_definition'] is None
    no_card['b_responses']=[{'name':'missing','scope':'pair','identity':0,'quantity':'force','component':'FNX'}]
    with pytest.raises(ValueError,match='TH/INTER'):impact_native.validate_settings(no_card)
    s['bulk_damage']=[{}]
    with pytest.raises(ValueError,match='벌크'):impact_native.validate_settings(s)


def test_source_native_contact_title_is_not_guessed_from_pair_ordinal():
    s=settings();source=s['source'];text=edited_files(source)['impact_0000.rad'].decode('ascii')
    at=text.index('IMPACT1',text.index('/INTER/TYPE24/'))
    source=replace_range(source,'impact_0000.rad',at,at+7,'MY_CONTACT',reason='명시 접촉 제목',expected_source_sha256=canonical_hash(source))
    p=impact_native.parse_source(source)
    assert p['model']['native_contact_titles']=={'1':'MY_CONTACT'}
    assert p['b_definition']['outputs']['groups'][0]['members']==[1]


def test_native_adapter_preserves_definition_before_controlled_starter_failure(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from caelab.adapters import impact
    s=impact_native_b.select_response(settings(),native_contact_id=1,quantity='force',component='FNZ',name='chosen')
    calls=[]
    monkeypatch.setattr(impact,'selected_runtime',lambda:({'starter':'NO_NATIVE','engine':'NO_NATIVE'},{},{'controlled_boundary':True}))
    def no_native(argv,folder,label,**kwargs):
        assert label=='starter';calls.append(label)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(impact,'run_owned_command',no_native)
    out=tmp_path/'adapter';r=impact.ImpactAdapter().run(s,output=out,runtime={'threads':1})
    assert calls==['starter'] and r['execution_status']=='FAILED'
    assert json.loads((out/'b_definition.json').read_text(encoding='utf8'))==impact_native.parse_source(s['source'])['b_definition']
    assert 'b_definition.json' in r['retained_native']['input_artifacts']
    assert all((out/'native'/n).read_bytes()==v for n,v in edited_files(s['source']).items())


def test_same_simulation_source_selection_save_cold_and_byte_export(tmp_path,monkeypatch):
    from caelab.workbench import Workbench
    from caelab.adapters import impact
    def forbidden(*a,**k):raise AssertionError('No solver/converter/runtime call')
    monkeypatch.setattr(impact,'selected_runtime',forbidden);monkeypatch.setattr(impact,'run_owned_command',forbidden)
    s=impact_native_b.select_response(settings(),native_contact_id=1,quantity='native_impulse',component='FNZ',name='selected_pair')
    workspace=tmp_path/'workspace';wb=Workbench(workspace,configuration={'workers':1})
    try:
        d=wb.document_open(kind='simulation',draft={'backend':impact_model.BACKEND,'settings':s})
        f=next(f for f in impact_native.parse_source(s['source'])['fields'] if f['field']=='end_s')
        changed=impact_native.edit_field(s,f['id'],.0031,reason='문서 편집',expected_source_sha256=canonical_hash(s['source']))
        for op,args in [('simulation.update',{'draft':{'backend':impact_model.BACKEND,'settings':changed}}),('document.undo',{}),('document.redo',{}),('document.save',{})]:
            d=wb.document_command(d['id'],op,args,session_id=d['session_id'],expected_generation=d['generation'])['document']
        assert d['draft']['settings']==changed and not wb.manager.list();docid=d['id']
    finally:assert wb.shutdown()['joined']
    program="""
import sys
from pathlib import Path
from caelab.workbench import Workbench
from caelab.storage import canonical_hash
from caelab.impact_native import validate_settings,export_direct
from caelab.impact_input_edits import edited_files
from caelab.adapters import impact
def forbidden(*a,**k):raise AssertionError('Cold cannot calculate')
impact.selected_runtime=forbidden;impact.run_owned_command=forbidden
wb=Workbench(sys.argv[1],configuration={'workers':1})
try:
 d=wb.document_open(kind='simulation',document_id=sys.argv[2]);s=d['draft']['settings'];assert canonical_hash(s)==sys.argv[3]
 validate_settings(s);export_direct(s,sys.argv[4])
 assert all((Path(sys.argv[4])/n).read_bytes()==v for n,v in edited_files(s['source']).items())
 assert len(s['b_responses'])==1 and not wb.manager.list()
 print('COLD_NATIVE_PAIR_SELECTION_SOURCE_EXPORT_IDENTICAL_NO_JOBS')
finally:assert wb.shutdown()['joined']
"""
    cold=subprocess.run([sys.executable,'-c',program,str(workspace),docid,canonical_hash(changed),str(tmp_path/'cold-export')],capture_output=True,text=True,timeout=30)
    assert cold.returncode==0,cold.stdout+cold.stderr


def test_renamed_native_attempt_keeps_live_retained_and_history_pins_together(tmp_path):
    from caelab.impact_bulk_history import completed_pair_units,retained_pair_units,read,pair_provenance,bind
    from caelab.dynamic_result_store import file_pin
    from caelab.impact_retained import artifact_receipt
    from caelab.adapters.impact import starter_admission
    from caelab.adapters.opencourant_runtime import WINDOWS_FILES,WINDOWS_SOURCE
    from caelab.storage import save_json
    from impact_b_fixtures import rec,ints,floats,title
    native=tmp_path/'native';native.mkdir();name='user_pair'
    for p in FIXTURE.iterdir():
        (native/p.name.replace('impact',name)).write_bytes(p.read_bytes().replace(b'impact',name.encode()))
    s=impact_native.settings_from_source(capture(native/(name+'_0000.rad'),native,engine=native/(name+'_0001.rad'),units='Mg/mm/s'))
    s=impact_native_b.select_response(s,native_contact_id=1,quantity='native_impulse',component='FNZ',name='chosen')
    parsed=impact_native.parse_source(s['source']);model=parsed['model'];g=parsed['b_definition']['outputs']['groups'][0]
    data=rec(struct.pack('>i',3040)+title('SYNTHETIC_RENAMED_BOUNDARY_NOT_SOLVER',80))+rec(b' '*80)
    data+=ints(0,0,0,0,1,23)+ints(*range(1,24))
    data+=rec(struct.pack('>5i',g['id'],101,0,1,6)+title(g['title'],40))
    data+=rec(struct.pack('>i',1)+title('IMPACT1',40))+ints(*range(1,7))
    for i,t in enumerate((0.,.0001,.0003)):data+=floats(t)+floats(*([0.]*23))+floats(*[float(i*(j+1)) for j in range(6)])
    (native/(name+'T01')).write_bytes(data)
    (native/(name+'T01_TITLES')).write_text(''.join(f'{101:10d}\n{v:<10}\n' for v in g['tokens']),encoding='ascii')
    (native/(name+'_0000.out')).write_text('NORMAL TERMINATION\nNO SYNTAX ERROR DETECTED\n0 ERROR(S)\n0 WARNING(S)\nNUMNOD: 8\nWORK UNIT SYSTEM ( Mg , mm , s ) 1E3 1E-3 1E0\nINPUT UNIT SYSTEM ( Mg , mm , s ) 1E3 1E-3 1E0\n',encoding='ascii')
    for label in ('starter','engine'):save_json(native/(label+'.execution.json'),{'status':'COMPLETED','return_code':0,'tree_ownership':'WINDOWS_JOB','synthetic_boundary':True})
    save_json(tmp_path/'input.json',s);save_json(tmp_path/'b_definition.json',parsed['b_definition'])
    identity={'platform':'win64','source_tag':WINDOWS_SOURCE,'files':deepcopy(WINDOWS_FILES)}
    execution={'execution_status':'SUCCEEDED','checks':[starter_admission(native/(name+'_0000.out'),model)],
        'diagnostics':{'runtime':identity,'native_execution_status':'SUCCEEDED','native_termination':{'status':'NORMAL'}}}
    live=completed_pair_units(tmp_path,model,s,execution)
    history=read(native/(name+'T01'),titles=native/(name+'T01_TITLES'));bound=bind(history,parsed['b_definition']['outputs'])[0]
    assert pair_provenance(history,bound,identity,live)['legacy_unit_evidence']['native_run_name']==name
    execution['retained_native']=artifact_receipt(tmp_path,[]);save_json(tmp_path/'impact_execution.json',execution)
    retained=retained_pair_units(tmp_path,file_pin(tmp_path,tmp_path/'impact_execution.json'),model,s,identity)
    assert pair_provenance(history,bound,identity,retained)
    from caelab import impact_b
    rows,_,_=impact_b.readback(tmp_path,model,s,parsed['b_definition'],[],runtime_identity=identity,unit_evidence=retained)
    assert rows['chosen']['value']==[0.,3.,6.]
    # Same bytes under the old name cannot substitute for the exact selected file.
    wrong=deepcopy(history);wrong['source_pin']['relative']='impactT01'
    assert pair_provenance(wrong,bound,identity,retained) is None
    (native/(name+'_0000.out')).rename(native/'impact_0000.out')
    with pytest.raises((ValueError,KeyError,OSError)):completed_pair_units(tmp_path,model,s,execution)
