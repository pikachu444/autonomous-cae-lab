"""Pinned source metadata with native-reader doubles; no ParaView is launched."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from test_desktop_post_external import native, Array, Source


class NamedVector(Array):
    def GetComponentName(self,index):
        return ['UX','UY','UZ'][index]


@pytest.fixture
def result_reader(native,monkeypatch):
    fake,commands,external=native
    original=fake.reader
    def reader(*args,**kwargs):
        source=original(*args,**kwargs)
        source.PointData={'U_mm':NamedVector(3),'UX_mm':Array(),'NativeNodeId':Array()}
        source.CellData={'NativeElementId':Array()}
        return source
    monkeypatch.setattr(fake,'reader',reader)
    return native


def declared():
    return {'coordinate_units':'mm','coordinate_frame':'global_cartesian',
        'static':{'step':1,'increment':2,'load_parameter':2.0},
        'arrays':[{'association':'POINTS','name':'U_mm','components':3,'component_names':['UX','UY','UZ'],
                   'units':'mm','frame':'global_cartesian','measure':'displacement'},
                  {'association':'POINTS','name':'NativeNodeId','components':1,'units':'1','frame':'not_applicable','measure':'identity'},
                  {'association':'CELLS','name':'NativeElementId','components':1,'units':'1','frame':'not_applicable','measure':'identity'}]}


def open_declared(result_reader,tmp_path,monkeypatch,metadata=None):
    fake,commands,external=result_reader
    from caelab.workbench_client import Client
    entry=tmp_path/'displacement.vtu'
    entry.write_text('TEST_ONLY native reader boundary')
    receipt={'id':'Dnative','path':str(entry),'format':'vtu','source_pins':external.pins([entry]),
             'native_metadata':declared() if metadata is None else metadata}
    monkeypatch.setattr(Client,'native_input',lambda client,identifier:deepcopy(receipt))
    return external.open_registered('Dnative',tmp_path/'project','http://127.0.0.1:8000')


def test_registered_static_units_frame_measure_persist_through_save_restore(result_reader,tmp_path,monkeypatch):
    fake,commands,external=result_reader
    project=open_declared(result_reader,tmp_path,monkeypatch)
    stored=json.loads(project.read_text())['sources']['result']
    assert stored['native_metadata']==declared() and stored['native_metadata_sha256']
    metadata=external.inspect_result(fake.active)
    displacement=next(row for row in metadata['arrays'] if row['name']=='U_mm')
    assert (displacement['units'],displacement['frame'],displacement['measure'])==('mm','global_cartesian','displacement')
    assert metadata['coordinate_units']=='mm' and metadata['coordinate_frame']=='global_cartesian'
    assert metadata['static']=={'step':1,'increment':2,'load_parameter':2.0}
    assert metadata['time'] is None and metadata['time_units'] is None and metadata['timesteps']==[]
    selected=external.select_array(fake.active,'POINTS','U_mm',component='UX')
    assert selected['units']=='mm' and selected['frame']=='global_cartesian'
    assert selected['static']['load_parameter']==2 and selected['time_units'] is None
    # Undeclared scalar is not assigned semantics from its name or neighboring vector.
    undeclared=external.select_array(fake.active,'POINTS','UX_mm')
    assert undeclared['units'] is None and undeclared['metadata_status']=='UNKNOWN'
    saved=commands.save_project()
    fake.sources.clear()
    commands.restore_workspace()
    restored=external.inspect_result(fake.active)
    assert restored['static']==metadata['static']
    assert next(row for row in restored['arrays'] if row['name']=='U_mm')['units']=='mm'
    assert json.loads(saved.read_text())['sources']['result']['native_metadata']==declared()


def test_unregistered_same_names_and_filters_remain_unknown(result_reader,tmp_path,monkeypatch):
    fake,_,external=result_reader
    project=open_declared(result_reader,tmp_path,monkeypatch)
    original=fake.active
    derived=Source('PassArrays',[])
    derived.PointData={'U_mm':NamedVector(3)}
    fake.sources[('Filtered output',99)]=derived
    fake.SetActiveSource(derived)
    metadata=external.inspect_result(derived)
    assert metadata['coordinate_units'] is None and metadata['static'] is None
    assert metadata['arrays'][0]['units'] is None
    assert external.select_array(derived,'POINTS','U_mm')['frame'] is None
    other=tmp_path/'arbitrary.vtu'
    other.write_text('arbitrary external result')
    external.open_result(other,tmp_path/'arbitrary-project')
    metadata=external.inspect_result(fake.active)
    assert metadata['arrays'][0]['name']=='U_mm' and metadata['arrays'][0]['units'] is None
    assert metadata['coordinate_frame'] is None and metadata['static'] is None


@pytest.mark.parametrize('damage',['association','name','components','component_names','missing','duplicate','temporal_units'])
def test_declared_array_mismatch_is_rejected(result_reader,tmp_path,monkeypatch,damage):
    fake,_,_=result_reader
    metadata=declared()
    if damage=='association':metadata['arrays'][0]['association']='CELLS'
    elif damage=='name':metadata['arrays'][0]['name']='Displacement'
    elif damage=='components':metadata['arrays'][0]['components']=1
    elif damage=='component_names':metadata['arrays'][0]['component_names']=['X','Y','Z']
    elif damage=='missing':metadata['arrays'].append({**metadata['arrays'][0],'name':'NotPresent'})
    elif damage=='duplicate':metadata['arrays'].append(deepcopy(metadata['arrays'][0]))
    else:metadata['static']['time_unit']='s'
    with pytest.raises(ValueError,match='array|component|Static'):
        open_declared(result_reader,tmp_path,monkeypatch,metadata)
    assert fake.view is None


def test_declarations_require_registered_verified_receipt(result_reader,tmp_path):
    fake,_,external=result_reader
    entry=tmp_path/'unverified.vtu';entry.write_text('external')
    with pytest.raises(ValueError,match='verified registered'):
        external.open_result(entry,tmp_path/'invalid',native_metadata=declared())
    assert not fake.sources
    with pytest.raises(RuntimeError,match='source pins'):
        external.open_result(entry,tmp_path/'wrong-pins',input_id='Dnative',source_pins=[],native_metadata=declared())
    assert not fake.sources


def test_changed_metadata_or_reader_is_not_silently_reused(result_reader,tmp_path,monkeypatch):
    fake,commands,external=result_reader
    project=open_declared(result_reader,tmp_path,monkeypatch)
    doc=json.loads(project.read_text())
    doc['sources']['result']['native_metadata']['arrays'][0]['units']='m'
    project.write_text(json.dumps(doc))
    with pytest.raises(RuntimeError,match='metadata identity'):
        external.inspect_result(fake.active)
    fake.loaded=False
    with pytest.raises(RuntimeError,match='metadata identity'):
        external.restore_workspace(project,doc)
    assert not fake.loaded
    doc['sources']['result']['native_metadata']=declared()
    project.write_text(json.dumps(doc))
    fake.active.PointData['U_mm']=Array(1)
    with pytest.raises(ValueError,match='component count'):
        commands.save_project()
    with pytest.raises(ValueError,match='component count'):
        external.select_array(fake.active,'POINTS','U_mm')
