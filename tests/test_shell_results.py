"""Synthetic native-format regressions. These do not assert CalculiX execution."""
from copy import deepcopy
import json
import math
import shutil
import subprocess
import pytest

from caelab.adapters.shell_results import read_expansion,read_frd,read_dat,locations,rotate_tensor
from caelab.adapters.shell_fem import collect
from caelab.adapters.shell_deck import sha
from caelab.shell_inspection import load,inspect,explicit_manifest
if __package__:
    from .test_shell_support import model,raw_sources
else:
    from test_shell_support import model,raw_sources

@pytest.mark.parametrize('offset',['0','.25','-.5','1.25'])
@pytest.mark.parametrize('flipped',[False,True])
def test_expanded_actual_surface_ids_offset_normal_and_internal_points(tmp_path,offset,flipped):
    data=model(offset=offset,flipped=flipped);mesh,xyz,expanded=raw_sources(tmp_path,data)
    expansion=read_expansion(tmp_path/'shell.12d',mesh['elements'])
    frd=read_frd(tmp_path/'shell.frd',expansion)
    assert frd['status']=='COMPLETE'
    mapped=locations(mesh,expansion,frd)
    assert len(mapped)==32 and len({r['expanded_node_id'] for r in mapped})<len(mapped)
    for r in mapped:
        assert r['position_mm']==pytest.approx(xyz[r['expanded_node_id']],abs=1e-5)
        assert r['side'] in ('top','bottom') and not r['exact_surface_integration_point']
        assert r['stress_recovery']=='native_extrapolated_nodal_averaged'
        assert r['normal_from_native_expansion'][2]==(-1 if flipped else 1)
    dat=read_dat(tmp_path/'shell.dat',mesh['elements'])
    assert dat['status']=='COMPLETE' and len(dat['rows'])==54
    assert all(not r['surface'] and abs(r['natural_coordinates'][2])<1 for r in dat['rows'])
    assert dat['rows'][0]['S']['values']==[1.,2.,3.,4.,6.,5.]

def test_no_nearest_node_or_geometry_only_mapping(tmp_path):
    data=model();mesh,_,_=raw_sources(tmp_path,data)
    path=tmp_path/'shell.12d';text=path.read_text();path.write_text(text.replace('1001','9001',1))
    mapping=read_expansion(path,mesh['elements'])
    with pytest.raises(ValueError):read_frd(tmp_path/'shell.frd',mapping)

@pytest.mark.parametrize('change',['S8R','C3D20R','duplicate','foreign'])
def test_expansion_profile_or_identity_mismatch_is_blocked(tmp_path,change):
    mesh,_,_=raw_sources(tmp_path,model());path=tmp_path/'shell.12d';text=path.read_text()
    if change=='S8R':text=text.replace('S8 ','S8R ')
    elif change=='C3D20R':text=text.replace('C3D20 L','C3D20RL')
    elif change=='duplicate':text+=text
    else:text=text.replace('ELEMENT 2 ','ELEMENT 999 ')
    path.write_text(text)
    with pytest.raises(ValueError):read_expansion(path,mesh['elements'])

def test_wrong_offset_never_relabels_surface_nodes(tmp_path):
    mesh,_,_=raw_sources(tmp_path,model(offset='.25'))
    ex=read_expansion(tmp_path/'shell.12d',mesh['elements']);frd=read_frd(tmp_path/'shell.frd',ex)
    mesh['section_values']['offset']=0.
    with pytest.raises(ValueError):locations(mesh,ex,frd)

def test_truncated_stress_leaves_displacement_only(tmp_path):
    mesh,_,_=raw_sources(tmp_path,model());path=tmp_path/'shell.frd';text=path.read_text()
    point=text.index(' -4 STRESS');text=text[:point]+text[point:].split(' -3',1)[0][:-30]
    path.write_text(text)
    ex=read_expansion(tmp_path/'shell.12d',mesh['elements']);frd=read_frd(path,ex)
    assert frd['status']=='PARTIAL'
    assert set(frd['frames'][-1]['fields'])=={'DISP'}

def test_dat_truncated_coord_does_not_fill_positions(tmp_path):
    mesh,_,_=raw_sources(tmp_path,model());path=tmp_path/'shell.dat';text=path.read_text()
    path.write_text(text[:text.index(' global coordinates')])
    dat=read_dat(path,mesh['elements'])
    assert dat['status']=='PARTIAL' and dat['rows']
    assert all('COORD' not in row for row in dat['rows'])


def test_dat_native_step_and_increment_headers_preserve_values(tmp_path):
    mesh,_,_=raw_sources(tmp_path,model());path=tmp_path/'shell.dat'
    expected=read_dat(path,mesh['elements']);raw=path.read_bytes()
    path.write_bytes(b'\n                        S T E P       1\n\n\n                                INCREMENT     1\n\n'+raw)
    observed=read_dat(path,mesh['elements'])
    assert observed['status']=='COMPLETE' and observed['rows']==expected['rows']


@pytest.mark.parametrize('prefix',[
    'S T E P 2\nINCREMENT 1\n',
    'S T E P 1\nS T E P 1\nINCREMENT 1\n',
    'INCREMENT 1\n',
    'S T E P 1\nINCREMENT 1\nINCREMENT 1\n',
    'S T E P 1\n',
    'S T E P 1\nINCREMENT 0\n',
    'S T E P 1 trailing\nINCREMENT 1\n',
])
def test_dat_invalid_control_headers_are_not_ignored(tmp_path,prefix):
    mesh,_,_=raw_sources(tmp_path,model());path=tmp_path/'shell.dat'
    path.write_bytes(prefix.encode('ascii')+path.read_bytes())
    result=read_dat(path,mesh['elements'])
    assert result['status']=='PARTIAL' and result['diagnostic'] and not result['rows']


def test_dat_repeated_step_preserves_prior_tables_without_merging(tmp_path):
    mesh,_,_=raw_sources(tmp_path,model());path=tmp_path/'shell.dat';raw=path.read_bytes()
    path.write_bytes(b'S T E P 1\nINCREMENT 1\n'+raw+b'\nS T E P 2\nINCREMENT 1\n'+raw)
    result=read_dat(path,mesh['elements'])
    assert result['status']=='PARTIAL' and result['diagnostic']
    assert len(result['rows'])==54


def test_dat_empty_next_increment_is_partial_and_keeps_completed_results(tmp_path):
    mesh,_,_=raw_sources(tmp_path,model());path=tmp_path/'shell.dat';raw=path.read_bytes()
    path.write_bytes(b'S T E P 1\nINCREMENT 1\n'+raw+b'\nINCREMENT 2\n')
    result=read_dat(path,mesh['elements'])
    assert result['status']=='PARTIAL' and result['diagnostic']
    assert len(result['rows'])==54


def test_dat_multiple_increments_keep_distinct_times_and_never_complete_previous_tables(tmp_path):
    mesh,_,_=raw_sources(tmp_path,model(),time=.5);path=tmp_path/'shell.dat';first=path.read_bytes()
    raw_sources(tmp_path,model(),increment=2,time=1.);second=path.read_bytes()
    prefix=b'S T E P 1\nINCREMENT 1\n'
    path.write_bytes(prefix+first+b'\nINCREMENT 2\n'+second)
    result=read_dat(path,mesh['elements'])
    assert result['status']=='COMPLETE' and len(result['rows'])==108
    assert {row['load_parameter'] for row in result['rows']}=={.5,1.}
    path.write_bytes(prefix+first[:first.index(b' global coordinates')]+b'\nINCREMENT 2\n'+second)
    result=read_dat(path,mesh['elements'])
    assert result['status']=='PARTIAL' and result['diagnostic']
    assert {row['load_parameter'] for row in result['rows']}=={.5}
    assert all('COORD' not in row for row in result['rows'])

def test_shear_components_are_tensor_components_and_rotation_only():
    assert rotate_tensor([1,2,3,4,5,6],[(1,0,0),(0,1,0),(0,0,1)])==[1,2,3,4,5,6]
    assert rotate_tensor([1,2,3,4,5,6],[(0,1,0),(-1,0,0),(0,0,1)])==[2,1,3,-4,-6,5]

def test_bundle_copy_reopen_and_native_tamper_fail_without_solver(tmp_path,monkeypatch):
    data=model();mesh,_,_=raw_sources(tmp_path/'job'/'solver',data)
    result=collect(tmp_path/'job',data,mesh,execution_status='SUCCEEDED')
    assert result['execution_status']=='SUCCEEDED' # synthetic parse lifecycle, not real solve
    view=tmp_path/'job'/result['post_artifact']['relative']; reference=result['post_artifact']['native_metadata']['shell_inspection']
    def forbidden(*a,**k):raise AssertionError('Reopen must not start any process')
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    saved=tmp_path/'copy';shutil.copytree(view.parent,saved)
    bundle=load(saved/view.name,reference)
    n=data['source_elements']['1'][0]
    row=inspect(saved/view.name,side='top',element_id=1,shell_node_id=n)
    assert set(row['available'])=={'DISP','STRESS','TOSTRAIN'}
    assert row['exact_surface_integration_stress']=='UNSUPPORTED'
    main,metadata=explicit_manifest(saved/'shell_inspection.json')
    assert main.name==view.name and metadata['shell_inspection']==reference
    (saved/'source'/'shell.frd').write_bytes((saved/'source'/'shell.frd').read_bytes()+b'changed')
    with pytest.raises(ValueError):load(saved/view.name,reference)

def test_cancelled_prefix_stays_cancelled_and_missing_fields_stay_absent(tmp_path):
    data=model();mesh,_,_=raw_sources(tmp_path/'job'/'solver',data,fields=('DISP',),end=False)
    result=collect(tmp_path/'job',data,mesh,execution_status='CANCELLED')
    assert result['execution_status']=='CANCELLED' and result['observation_status']=='PARTIAL'
    assert set(result['responses'])=={'shell_surface_displacement'}
    view=tmp_path/'job'/result['post_artifact']['relative']
    assert load(view)['data']['execution_status']=='CANCELLED'

def test_vtu_is_actual_quadratic_surface_not_solid_relabel(tmp_path):
    vtk=pytest.importorskip('vtk',reason='Optional existing local VTK reader verification only')
    data=model();mesh,_,_=raw_sources(tmp_path/'job'/'solver',data)
    result=collect(tmp_path/'job',data,mesh,execution_status='SUCCEEDED')
    reader=vtk.vtkXMLUnstructuredGridReader();reader.SetFileName(str(tmp_path/'job'/result['post_artifact']['relative']));reader.Update()
    grid=reader.GetOutput()
    assert grid.GetNumberOfPoints()==32 and grid.GetNumberOfCells()==4
    assert all(grid.GetCellType(i)==23 for i in range(4))
    assert grid.GetPointData().GetArray('ShellSide').GetRange()==(-1.,1.)
    assert grid.GetPointData().GetArray('S_surface_recovered').GetNumberOfComponents()==6
