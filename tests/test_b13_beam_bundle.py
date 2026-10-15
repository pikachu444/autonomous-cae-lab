"""Full existing-adapter/portable-reader loop using SYNTHETIC native-format data.

No binary, solver, FreeCAD, or native engineering acceptance is represented by
this test double. Real executions remain the separate Windows native-check lane.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import json
import shutil
import pytest

from b13_raw_fixture import raw_model, write_sources
from test_beam_support import snapshot
from caelab.adapters import beam_fem
from caelab.beam_output import WRITER_OUTPUT,mechanical_identity
from caelab.beam_inspection import load,inspect_raw,inspect_section_responses
from caelab.storage import save_json
from caelab.beam_results import sha


def produced(monkeypatch,tmp_path,*,regional=False):
    value=raw_model(regional=regional);source=snapshot(tmp_path/'input',value)
    manifest=json.loads(source.read_text(encoding='utf-8'))
    manifest['writers']={'output':WRITER_OUTPUT['raw_stress'],'mechanical_sha256':mechanical_identity(value)}
    save_json(source,manifest)
    binary=tmp_path/'NOT_A_SOLVER';binary.write_bytes(b'explicit process double, not native solver')
    monkeypatch.setattr(beam_fem.shutil,'which',lambda _:str(binary))
    calls=[]
    def command(argv,cwd,label,**kwargs):
        calls.append(argv)
        assert kwargs['owned_tree'] is True and argv[-2:]==['-i','beam']
        write_sources(cwd,value)
        (cwd/'ccx_beam.stdout.log').write_text('SYNTHETIC TEST DOUBLE',encoding='ascii')
        return NS(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(beam_fem,'run_owned_command',command)
    result=beam_fem.BeamFemCalculixAdapter().run({'snapshot_path':str(source)},output=tmp_path/'run')
    assert result['execution_status']=='SUCCEEDED',result
    assert len(calls)==1
    assert result['engineering_valid'] is False
    assert result['output_mode']=='raw_stress'
    return tmp_path/'run',result


def reseal(view):
    path=view.parent/'beam_inspection.json';doc=json.loads(path.read_text(encoding='utf-8'))
    for row in doc['files']:
        member=view.parent/row['relative'];row.update(bytes=member.stat().st_size,sha256=sha(member))
    save_json(path,doc)


@pytest.mark.parametrize('regional',[False,True])
def test_one_explicit_run_and_cold_reopen_without_owner(monkeypatch,tmp_path,regional):
    run,result=produced(monkeypatch,tmp_path,regional=regional)
    monkeypatch.setattr(beam_fem,'run_owned_command',lambda *a,**k:pytest.fail('A read must not run a solver'))
    saved=beam_fem.read_saved_run(run)
    assert saved['observed']['complete_file']
    target=tmp_path/'portable';shutil.copytree(run/'post',target)
    shutil.rmtree(run);shutil.rmtree(tmp_path/'input')
    view=target/'beam.pvd';checked=load(view)
    assert checked['data']['observed']['output_mode']=='raw_stress'
    row=inspect_raw(view,element_id=88,integration_point=1,quantity='S')
    assert row['location']['association']=='CELLS' and row['point_measurement']=='UNSUPPORTED'
    assert row['unit']=='MPa' and row['position_mm'] is not None
    frames=inspect_section_responses(view)
    assert frames['native_generalized_rotation']=='UNAVAILABLE'
    assert frames['derived_rotations'] and frames['supports']
    assert not any('FreeCAD'==x for x in __import__('sys').modules)


def test_rehashed_changed_view_or_fit_is_rejected(monkeypatch,tmp_path):
    run,_=produced(monkeypatch,tmp_path);view=run/'post'/'beam.pvd'
    fields=view.parent/'beam_fields.json';doc=json.loads(fields.read_text(encoding='utf-8'))
    doc['observed']['frames'][0]['derived_rotations'][0]['value_rad'][0]+=1
    save_json(fields,doc);reseal(view)
    with pytest.raises(ValueError,match='observations|observed|native'):load(view)


def test_ip_view_cannot_be_recast_as_point_values(monkeypatch,tmp_path):
    run,_=produced(monkeypatch,tmp_path);view=run/'post'/'beam.pvd'
    ip=view.parent/'beam_ip_0000.vtu';raw=ip.read_bytes()
    assert b'CellData' in raw
    ip.write_bytes(raw.replace(b'CellData',b'PointData'));reseal(view)
    with pytest.raises(ValueError,match='view|native|VTK'):load(view)


def test_native_expansion_and_dat_are_required_dependencies(monkeypatch,tmp_path):
    run,_=produced(monkeypatch,tmp_path);view=run/'post'/'beam.pvd'
    manifest=view.parent/'beam_inspection.json';doc=json.loads(manifest.read_text(encoding='utf-8'))
    doc['files']=[r for r in doc['files'] if r['relative']!='source/solver/beam.dat']
    save_json(manifest,doc)
    with pytest.raises(ValueError,match='DAT|source|dependency|unlisted'):load(view)
