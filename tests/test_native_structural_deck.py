"""Syntax/mapping refusals; this fixture is UNSOLVED and not engineering proof."""
from copy import deepcopy
from pathlib import Path
import math
import pytest

from caelab.adapters.native_structural_deck import native_number, prepare, write, read_tables
from caelab.adapters.native_structural import source_snapshot, verify_source_snapshots


def test_calculix_small_negative_and_long_fields_keep_sign_within_native_width():
    for value in (1.8939262270347234e-15, -1.8939262270347234e-15, 123456789012345., -123456789012345., 1e-180):
        token=native_number(value)
        assert len(token)<=20 and math.copysign(1,float(token))==math.copysign(1,value)
        assert abs(float(token)-value)<=5e-13*abs(value)
    for value in (float('nan'),float('inf'),True):
        with pytest.raises(ValueError): native_number(value)


def mesh():
    # Eight cube corners suffice to verify rank and resultant assembly only.
    nodes={str(n+1):[x,y,z] for n,(x,y,z) in enumerate(((0,0,0),(1,0,0),(0,1,0),(1,1,0),
                                                    (0,0,1),(1,0,1),(0,1,1),(1,1,1)))}
    return {'nodes':nodes,'elements':{},'face_nodes':{'X0':[1,3,5,7],'Y0':[1,2,5,6],'Z0':[1,2,3,4]},
            'face_weights':{'X1':{'mesh_area_mm2':1.,'native_area_mm2':1.,
                'nodal_area_weights_mm2':{'2':-.125,'4':.375,'6':.375,'8':.375}}},
            'load_distribution':'TEST_ONLY_SIGNED_QUADRATIC_WEIGHTS'}


def declaration():
    return {'boundary_conditions':[{'selection_id':face,'components':{dof:0.}}
             for face,dof in (('X0','UX'),('Y0','UY'),('Z0','UZ'))],
            'loads':[{'id':'L1','selection_id':'X1','components':{'FX':150.,'FY':0.,'FZ':0.}}],
            'materials':[{'young_modulus_MPa':210000.,'poisson_ratio':.3}]}


def test_partial_dofs_signed_quadratic_weights_and_serialized_force_are_preserved(tmp_path):
    out=write(tmp_path/'native.inp',mesh(),declaration())
    assert out['rigid_body_constraint_rank']==6
    assert out['total_applied_force_N']==[150.,0.,0.]
    assert next(row for row in out['loads'] if row['node_id']==2)['force_N']==-18.75
    assert {(row['node_id'],row['component']) for row in out['fixed_dofs']}=={
        *((n,1) for n in (1,3,5,7)),*((n,2) for n in (1,2,5,6)),*((n,3) for n in (1,2,3,4))}
    text=(tmp_path/'native.inp').read_text()
    assert '1, 1, 1,' in text and '1, 1, 3,' not in text
    assert '2, 1, -1.875000000000e+01' in text


@pytest.mark.parametrize('kind',['rigid','conflict','force_on_fixed','wrong_resultant'])
def test_invalid_assembly_is_refused_before_solver(kind):
    m=mesh(); d=declaration()
    if kind=='rigid': d['boundary_conditions']=d['boundary_conditions'][:1]
    if kind=='conflict': d['boundary_conditions'].append({'selection_id':'X0','components':{'UX':1}})
    if kind=='force_on_fixed': d['loads'][0]['components']={'FX':0.,'FY':150.,'FZ':0.}
    if kind=='wrong_resultant': m['face_weights']['X1']['mesh_area_mm2']=2.
    with pytest.raises(ValueError): prepare(m,d)


def dat(path, rows):
    path.write_text('displacements (vx,vy,vz) for set ALL_NODES and time 0.1000000E+01\n'+rows+
                    '\nforces (fx,fy,fz) for set ALL_NODES and time 0.1000000E+01\n'+rows)


def test_dat_exact_complete_nodes_and_native_tokens(tmp_path):
    p=tmp_path/'native.dat'; dat(p,'1 0.1000000E-05 -0.2000000E-05 0.0D+00\n2 1.0E-6 0 0\n')
    response=read_tables(p,{1:None,2:None})
    assert response['U'][1]==[1e-6,-2e-6,0.]
    assert response['tokens']['U'][1][2]=='0.0D+00'


def test_native_response_snapshot_uses_parsed_bytes_and_refuses_changed_source(tmp_path):
    p = tmp_path / 'native.dat'
    dat(p, '1 0.1000000E-05 -0.2000000E-05 0.0D+00\n')
    raw = p.read_bytes()
    sources = {'dat': source_snapshot(p, raw)}
    verify_source_snapshots(tmp_path, sources)
    p.write_bytes(raw.replace(b'0.1000000E-05', b'0.3000000E-05'))
    response = read_tables(p, {1: None}, data=raw)
    assert response['U'][1] == [1e-6, -2e-6, 0.]
    with pytest.raises(ValueError, match='Native response source changed'):
        verify_source_snapshots(tmp_path, sources)


@pytest.mark.parametrize('kind',['missing','duplicate','foreign','nonfinite','load_parameter'])
def test_unowned_or_incomplete_native_dat_is_refused(kind,tmp_path):
    p=tmp_path/'native.dat'; dat(p,'1 0 0 0\n2 0 0 0\n')
    raw=p.read_text()
    if kind=='missing': raw=raw.replace('2 0 0 0\n','')
    if kind=='duplicate': raw=raw.replace('2 0 0 0\n','1 0 0 0\n')
    if kind=='foreign': raw=raw.replace('2 0 0 0\n','3 0 0 0\n')
    if kind=='nonfinite': raw=raw.replace('2 0 0 0\n','2 nan 0 0\n')
    if kind=='load_parameter': raw=raw.replace('0.1000000E+01','0.2000000E+01')
    p.write_text(raw)
    with pytest.raises(ValueError): read_tables(p,{1:None,2:None})
