"""Domain/routing tests. Process doubles below are NOT native solver evidence."""
from copy import deepcopy
from pathlib import Path
import json
import shutil
import subprocess
import pytest
from caelab.impact_source import capture,resolve,SourceError
from caelab.impact_native import parse_source,settings_from_source,edit_field,export_direct
from caelab.impact_input_edits import replace_range,edited_files,original_files
from caelab.storage import canonical_hash

ROOT=Path(__file__).resolve().parents[2]/'examples/impact/input_a/native'

def definition():
    return settings_from_source(capture(ROOT/'impact_0000.rad',ROOT,engine=ROOT/'impact_0001.rad',units='Mg/mm/s'))

def edit_source(s,file,before,after):
    raw=original_files(s['source'])[file];start=raw.index(before.encode())
    source=replace_range(s['source'],file,start,start+len(before),after,reason='UNIT explicit source edit',
                         expected_source_sha256=canonical_hash(s['source']))
    return source


def test_native_source_authority_and_exact_edit_bytes(tmp_path):
    s=definition();before=deepcopy(s);p=parse_source(s['source'])
    field=next(f for f in p['fields'] if f['role']=='engine' and f['field']=='end_s')
    s=edit_field(s,field['id'],.002,reason='종료 시간 명시 수정',expected_source_sha256=canonical_hash(s['source']))
    assert s['time']['end_s']==.002
    assert s['source']['bundle']==before['source']['bundle']
    hunk=s['source']['edits'][0];raw=original_files(s['source'])[hunk['file']]
    new=edited_files(s['source'])[hunk['file']]
    assert new==raw[:hunk['start']]+hunk['after'].encode()+raw[hunk['end']:]
    assert b'\r\n' in new
    record=export_direct(s,tmp_path/'direct')
    assert record['converter_execution']=='NOT_PERFORMED'
    for name,payload in edited_files(s['source']).items():assert (tmp_path/'direct'/name).read_bytes()==payload
    assert not list((tmp_path/'direct').rglob('*.inp'))
    with pytest.raises(FileExistsError):export_direct(s,tmp_path/'direct')
    with pytest.raises(SourceError):edit_field(s,field['id'],.003,reason='stale',expected_source_sha256=canonical_hash(before['source']))
    s2=edit_field(s,field['id'],.003,reason='재편집',expected_source_sha256=canonical_hash(s['source']))
    assert len(s2['source']['edits'])==1 and s2['time']['end_s']==.003
    from caelab.impact_model import render,validate_settings
    with pytest.raises(ValueError,match='direct'):render(s)
    forged=deepcopy(s);forged['time']['end_s']=.004
    with pytest.raises(SourceError,match='원문'):validate_settings(forged)


@pytest.mark.parametrize('before,after',[
    ('/NODE','/ALE/STRUCTURED_MESH'),
    ('/MAT/ELAST/1','/MAT/ELAST/1/UNKNOWN'),
    ('/BCS','/BCS/UNKNOWN'), # handled in a separate appended card if no BCS exists
    ('/END','/RBODY/1\r\nUnadmitted rigid\r\n/END'),
    ('/END','/END\r\n/TRANSFORM/ROT/1\r\nUnknown'),
])
def test_unknown_native_influence_cards_block_with_location(before,after):
    s=definition()
    if before=='/NODE':file='mesh.inc'
    else:file='impact_0000.rad'
    if before=='/BCS':before='/END';after='/BCS/999/UNKNOWN\r\n/END'
    source=edit_source(s,file,before,after)
    with pytest.raises(SourceError) as failure:parse_source(source)
    assert failure.value.file is not None


@pytest.mark.parametrize('source_change', ['units','units_unconfirmed','node_duplicate','missing_ref','property_extra','engine_unknown','engine_dt_extra'])
def test_native_units_identity_field_option_admission(source_change):
    s=definition()
    if source_change=='units':
        source=edit_source(s,'impact_0000.rad','                  Mg','                  kg')
    elif source_change=='units_unconfirmed':
        source=deepcopy(s['source']);source['units']='UNKNOWN'
    elif source_change=='node_duplicate':
        source=edit_source(s,'mesh.inc','         2','         1')
    elif source_change=='missing_ref':
        raw=original_files(s['source'])['impact_0000.rad'].decode();start=raw.index('/TETRA4/1');row=raw[start:].split('\r\n')[1]
        source=edit_source(s,'impact_0000.rad',row,row[:-10]+'       999')
    elif source_change=='property_extra':source=edit_source(s,'impact_0000.rad','/PROP/SOLID/1','/PROP/SOLID/1/7')
    elif source_change=='engine_unknown':source=edit_source(s,'impact_0001.rad','/STOP','/UNKNOWN/MASS/1\r\n/STOP')
    else:
        lines=original_files(s['source'])['impact_0001.rad'].decode('ascii').splitlines()
        row=lines[lines.index('/DT')+1]
        source=edit_source(s,'impact_0001.rad',row,row+' 7')
    with pytest.raises((ValueError,SourceError)):parse_source(source)


def test_native_include_graph_originals_and_edit_range_guards(tmp_path):
    shutil.copytree(ROOT,tmp_path/'input');root=tmp_path/'input';starter=root/'impact_0000.rad';engine=root/'impact_0001.rad'
    starter.write_bytes(starter.read_bytes().replace(b'#include mesh.inc',b'#include nested.inc'))
    (root/'nested.inc').write_bytes(b'#include mesh.inc\r\n')
    source=capture(starter,root,engine=engine,units='Mg/mm/s')
    assert len(source['bundle']['files'])==4
    s=settings_from_source(source);p=parse_source(source)
    assert p['model']['lineage']['nodes']['1']['file']=='mesh.inc'
    for bad in (b'#include ../escape.rad',b'#include C:\\bad.rad',b'#include nested.inc',b'#INCLUDE mesh.inc',b' #include mesh.inc'):
        (root/'nested.inc').write_bytes(bad+b'\r\n')
        with pytest.raises(SourceError):capture(starter,root,engine=engine,units='Mg/mm/s')
    bad=deepcopy(source);bad['bundle']['files'][0]['text']+='### tampered\n'
    with pytest.raises(SourceError):resolve(bad)
    target=source['bundle']['files'][0]['path']
    with pytest.raises(SourceError):replace_range(source,target,0,1,'#',reason='',expected_source_sha256=canonical_hash(source))
    with pytest.raises(SourceError):replace_range(source,target,-1,1,'#',reason='invalid',expected_source_sha256=canonical_hash(source))


def test_no_runtime_still_retains_native_edit_and_initial_mass(tmp_path,monkeypatch):
    from caelab.adapters.impact import ImpactAdapter
    def missing():raise FileNotFoundError('UNIT intentionally absent runtime')
    monkeypatch.setattr('caelab.adapters.impact.selected_runtime',missing)
    def forbidden(*a,**kw):raise AssertionError('No process is permitted in runtime-absent unit')
    monkeypatch.setattr('caelab.adapters.impact.run_owned_command',forbidden)
    s=definition();result=ImpactAdapter().run(s,output=tmp_path)
    assert result['execution_status']=='FAILED'
    assert result['diagnostics']['native_execution_status']=='NOT_STARTED'
    assert result['diagnostics']['last_phase']=='runtime'
    assert 'absent runtime' in result['diagnostics']['reason']
    assert not list(tmp_path.rglob('*.inp'))
    mass=json.loads((tmp_path/'initial_mass_properties.json').read_text())['initial']
    assert mass['mass_Mg']==pytest.approx(1.3e-6)
    assert mass['com_mm']==pytest.approx([2.5]*3)
    assert mass['kinetic_energy_N_mm']==pytest.approx(.0065)
    assert mass['inertia_at_com_Mg_mm2'][0]==pytest.approx([9.75e-6,1.625e-6,1.625e-6])
    assert mass['native_comparison']=='NOT_RUN'
    for name,raw in edited_files(s['source']).items():assert (tmp_path/'native'/name).read_bytes()==raw
    from caelab.impact_retained import context
    assert context(result['diagnostics']['native_outcome'],tmp_path)[1]['execution_status']=='FAILED'


def test_starter_failure_does_not_start_engine_or_converter(tmp_path,monkeypatch):
    from caelab.adapters.impact import ImpactAdapter
    calls=[]
    monkeypatch.setattr('caelab.adapters.impact.selected_runtime',lambda:({'starter':'unit-starter','engine':'unit-engine'},{},{'unit_boundary_double':True}))
    def command(argv,cwd,label,**kwargs):
        calls.append(label)
        assert kwargs['owned_tree'] is True
        (cwd/'impact_0000.out').write_text('UNIT STARTER WARNING; not native execution evidence')
        return subprocess.CompletedProcess(argv,0,stdout=b'UNIT',stderr=b'')
    monkeypatch.setattr('caelab.adapters.impact.run_owned_command',command)
    result=ImpactAdapter().run(definition(),output=tmp_path)
    assert calls==['starter'] and result['execution_status']=='FAILED'
    assert result['diagnostics']['native_execution_status']=='NOT_STARTED'
    assert result['diagnostics']['last_phase']=='starter'


def test_engine_finished_readback_failed_keeps_both_facts(tmp_path,monkeypatch):
    from caelab.adapters.impact import ImpactAdapter
    calls=[]
    monkeypatch.setattr('caelab.adapters.impact.selected_runtime',lambda:({'starter':'unit-starter','engine':'unit-engine'},{},{'unit_boundary_double':True}))
    def command(argv,cwd,label,**kw):
        calls.append(label);assert kw['owned_tree']
        return subprocess.CompletedProcess(argv,0,stdout=b'UNIT BOUNDARY DOUBLE',stderr=b'')
    monkeypatch.setattr('caelab.adapters.impact.run_owned_command',command)
    monkeypatch.setattr('caelab.adapters.impact.starter_admission',lambda *a:{'name':'UNIT_ONLY','status':'PASS'})
    monkeypatch.setattr('caelab.adapters.impact.engine_termination',lambda *a:{'status':'NORMAL','unit_boundary_double':True})
    result=ImpactAdapter().run(definition(),output=tmp_path)
    assert calls==['starter','engine']
    assert result['execution_status']=='FAILED' and result['diagnostics']['native_execution_status']=='SUCCEEDED'
    assert 'history' in result['diagnostics']['readback_error']
    assert not list(tmp_path.rglob('*.inp'))
