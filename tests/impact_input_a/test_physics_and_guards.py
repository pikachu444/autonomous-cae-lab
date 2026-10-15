"""Analytic initial-state, exact-binding and owned cancellation tests.

These are algebra/transport tests, not native mechanical qualification.
"""
from copy import deepcopy
from pathlib import Path
import json
import math
import os
import subprocess
import sys
import threading
import pytest
import numpy as np
from caelab.impact_model import default_settings,model_from_settings,render,validate_settings
from caelab.impact_source import capture,SourceError
from caelab.impact_initial_state import describe,rotation_matrix
from caelab.storage import canonical_hash
from caelab.impact_input_edits import original_files,replace_range,original_offset
from caelab.impact_input_workflow import apply_text,inspect,declare_native_units
from test_native import definition as native_definition,edit_source,ROOT as NATIVE
from test_assembly import definition as assembly_definition


def test_actual_starter_resolved_tetra_strain_is_checked_even_without_warning(tmp_path):
    from caelab.adapters.impact import starter_admission
    text=('NORMAL TERMINATION\nNO SYNTAX ERROR DETECTED\n0 ERROR(S)\n0 WARNING(S)\nNUMNOD: 4\n'
          'WORK UNIT SYSTEM ( Mg , mm , s ) 1E3 1E-3 1E0\n'
          'INPUT UNIT SYSTEM ( Mg , mm , s ) 1E3 1E-3 1E0\n'
          'PART ELEMENT/MATERIAL PARAMETER REVIEW:\n'
          '  Isolid  Ismstr   Icpre  Iframe    IHKT Itetra4 Itetra10 IMATVIS ICONTROL\n'
          '       1      12       0       1       0       3       2       0       1\n')
    path=tmp_path/'starter.out';path.write_text(text,encoding='ascii')
    model=model_from_settings(native_definition())
    with pytest.raises(ValueError,match='incompatible Ismstr'):
        starter_admission(path,model)
    path.write_text(text.replace('1      12','1       2'),encoding='ascii')
    receipt=starter_admission(path,model)
    assert receipt['actual_formulation_review'][0]['Ismstr']==2
    # The unused tetra flag in a brick property's review is not a tetra law.
    path.write_text(text.replace('PART ELEMENT/MATERIAL PARAMETER REVIEW:\n',
        'PART ELEMENT/MATERIAL PARAMETER REVIEW:\nPart id,name: 1 BODY Mat type: 1 Elm type: BRICK\n'),encoding='ascii')
    assert starter_admission(path,model)['status']=='PASS'


def test_public_native_has_explicit_compatible_strain_and_preserves_automatic_old_draft():
    from caelab.impact_native import parse_source
    s=native_definition()
    parsed=parse_source(s['source'])
    assert parsed['physics']['effective_formulation']['Itetra4_by_element']=={'1':1000}
    assert parsed['physics']['effective_formulation']['Ismstr_by_element']=={'1':-1}
    # Historical original bytes must remain readable; resolved unsafe defaults
    # are blocked by the actual Starter postflight before Engine, not on reopen.
    original=edit_source(s,'impact_0000.rad','         0      1000        -1','         0         3        -1')
    old=parse_source(original)
    assert old['physics']['effective_formulation']['Ismstr_by_element']=={'1':-1}
    assert old['physics']['effective_formulation']['Itetra4_by_element']=={'1':3}


def free_tetra():
    # Source IDs deliberately differ from native example IDs.
    s=default_settings()
    s['source']['text']='*NODE\n10,0,0,0\n20,10,0,0\n30,0,20,0\n40,0,0,30\n*ELEMENT,TYPE=C3D4,ELSET=BODY\n70,10,20,30,40\n*NSET,NSET=BODY\n10,20,30,40\n*MATERIAL,NAME=MAT\n*DENSITY\n7.8e-9\n*ELASTIC\n210000,.3\n*SOLID SECTION,ELSET=BODY,MATERIAL=MAT\n'
    return s


def motion(**kwargs):
    r={'node_set':'BODY','mode':'velocity','height_mm':None,'velocity_mm_s':[2.,-3.,4.],
       'omega_rad_s':[.2,.4,-.7],'center_mm':[2.5,5.,7.5],'translation_mm':[3.,-4.,5.]}
    r.update(kwargs);return r


def test_full_tensor_pose_mass_energy_and_explicit_frame():
    s=free_tetra();r=rotation_matrix([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    s['motions']=[motion(pose={'rotation':r.tolist(),'frame':'MODEL_GLOBAL','vector_frame':'INITIAL_BODY'})]
    _,initial=render(s);m=model_from_settings(s);receipt=describe(m,initial,s)
    before,after=receipt['original'],receipt['initial']
    mass=7.8e-6
    assert before['mass_Mg']==pytest.approx(mass) and after['mass_Mg']==pytest.approx(mass)
    assert before['com_mm']==pytest.approx([2.5,5.,7.5])
    assert after['com_mm']==pytest.approx([5.5,1.,12.5])
    tensor=np.asarray(before['inertia_at_com_Mg_mm2'])
    np.testing.assert_allclose(after['inertia_at_com_Mg_mm2'],r@tensor@r.T,rtol=1e-12,atol=1e-18)
    velocity=r@np.asarray([2.,-3.,4.]);omega=r@np.asarray([.2,.4,-.7])
    expected=.5*mass*float(velocity@velocity)+.5*float(omega@(r@tensor@r.T)@omega)
    assert after['kinetic_energy_N_mm']==pytest.approx(expected,rel=1e-12)
    np.testing.assert_allclose(after['momentum_Mg_mm_s'],mass*velocity,rtol=1e-12)
    assert before['principal_axes_status']=='EIGENVECTORS_COLUMNS_SIGN_AMBIGUOUS'
    assert receipt['solver_rigidity']=='NOT_INFERRED' and receipt['native_body_mass_inertia']=='UNKNOWN'
    assert after['native_comparison']=='NOT_RUN'


def test_release_and_omitted_flight_are_distinct_and_no_double_application():
    s=free_tetra();s['gravity_mm_s2']=[0.,0.,-9810.]
    s['motions']=[motion(mode='release_height',height_mm=20.,velocity_mm_s=[0.,0.,0.],
                         omega_rad_s=[0.,0.,2.],translation_mm=[0.,0.,0.])]
    _,release=render(s);assert release['nodes'][10]==[0.,0.,20.]
    assert sum(v[2] for v in release['velocities_mm_s'].values())==0.
    s['motions'][0]['mode']='impact_height';_,impact=render(s)
    assert impact['nodes'][10]==[0.,0.,0.]
    assert impact['velocities_mm_s'][10][2]==pytest.approx(-math.sqrt(2*9810*20))
    s['motions'][0]['velocity_mm_s']=[0.,0.,-100.]
    with pytest.raises(ValueError,match='중복'):validate_settings(s)
    s['motions'][0]['mode']='velocity'
    with pytest.raises(ValueError,match='중복'):validate_settings(s)


@pytest.mark.parametrize('matrix',[
    [[-1,0,0],[0,1,0],[0,0,1]],[[1,1,0],[0,1,0],[0,0,1]],
    [[2,0,0],[0,1,0],[0,0,1]],[[1,0,0],[0,float('nan'),0],[0,0,1]],
])
def test_non_rigid_or_unknown_pose_not_repaired(matrix):
    with pytest.raises(ValueError):rotation_matrix(matrix)


def test_orientation_partial_pose_fixed_velocity_and_overlap_are_blocked():
    s=free_tetra();s['motions']=[motion()]
    s['source']['text']+='*BOUNDARY\n10,1,3,0\n'
    with pytest.raises(ValueError,match='충돌'):validate_settings(s)
    s=free_tetra();s['motions']=[motion(),motion()]
    with pytest.raises(ValueError,match='겹치지'):validate_settings(s)
    s=free_tetra();s['source']['text']+='*NSET,NSET=PARTIAL\n10,20,30\n'
    s['motions']=[motion(node_set='PARTIAL',pose={'rotation':np.eye(3).tolist(),'frame':'MODEL_GLOBAL','vector_frame':'MODEL_GLOBAL'})]
    with pytest.raises(ValueError,match='전체'):validate_settings(s)
    s=free_tetra();s['source']['text']=s['source']['text'].replace('70,10,20,30,40','70,10,30,20,40')
    _,initial=render(s)
    with pytest.raises(ValueError,match='양의'):describe(model_from_settings(s),initial,s)


def test_source_edit_does_not_silently_recycle_response_identity():
    from caelab.impact_reference_bindings import review,accept_review
    from caelab.impact_input_workflow import response_for_source
    s=assembly_definition()
    s['responses']=[response_for_source(s,name='body2_node10_vz',quantity='velocity',component='Z',
                                       association='POINTS',instance='BODY-2',local_id=10)]
    assert s['responses'][0]['identity']==5
    # Insert a distinct unused local node. Effective ID 5 now denotes BODY-1/40,
    # while the requested logical selection BODY-2/10 moves to ID 7.
    file='parts/mesh.inc';raw=original_files(s['source'])[file];offset=raw.index(b'10,0,0,0')
    edited=apply_text(s,file=file,start=offset,end=offset,replacement='5,1,1,1\n',reason='새 원절점 명시 추가',
                      expected_definition_sha256=canonical_hash(s))['settings']
    assert inspect(edited)['readiness']=='BLOCKED'
    with pytest.raises(ValueError,match='대응이 바뀌'):validate_settings(edited)
    selection=review(edited);assert selection['changed']
    with pytest.raises(ValueError):accept_review(edited,expected_definition_sha256=canonical_hash(edited),
                        expected_review_sha256=selection['review_sha256'],acknowledged=False)
    edited['responses']=[response_for_source(edited,name='body2_node10_vz',quantity='velocity',component='Z',
                           association='POINTS',instance='BODY-2',local_id=10)]
    selection=review(edited)
    accepted=accept_review(edited,expected_definition_sha256=canonical_hash(edited),
                          expected_review_sha256=selection['review_sha256'],acknowledged=True)
    assert accepted['responses'][0]['identity']==7
    validate_settings(accepted)


def test_geometric_edit_keeps_logical_targets_and_units_require_explicit_confirm():
    from caelab.impact_assembly import target_key
    s=assembly_definition();m=model_from_settings(s)
    s['motions']=[motion(node_set=target_key(m,'nsets','DROP.BODY-2.BODY'))]
    file='parts/mesh.inc';raw=original_files(s['source'])[file];offset=raw.index(b'20,10')+3
    edited=apply_text(s,file=file,start=offset,end=offset+2,replacement='12',reason='길이 명시 변경',
                      expected_definition_sha256=canonical_hash(s))['settings']
    validate_settings(edited)
    s=native_definition();s['source']['units']='UNKNOWN';s['source']['provenance']['units_declared_by_user']=False
    assert inspect(s)['readiness']=='BLOCKED'
    with pytest.raises(ValueError):declare_native_units(s,units='Mg/mm/s',acknowledged=False,expected_definition_sha256=canonical_hash(s))
    confirmed=declare_native_units(s,units='Mg/mm/s',acknowledged=True,expected_definition_sha256=canonical_hash(s))
    assert confirmed['inspection']['readiness']=='INPUT_ADMITTED_RUNTIME_NOT_PROBED'
    assert confirmed['settings']['source']['bundle']==s['source']['bundle']


def test_native_hidden_unreferenced_property_and_blank_data_row_are_blocked():
    from caelab.impact_native import parse_source
    s=native_definition();raw=original_files(s['source'])['impact_0000.rad'].decode()
    card=next(c for c in parse_source(s['source'])['cards'] if c['key']=='/PROP/SOLID/1')
    extra='/PROP/SOLID/999\r\n'+'\r\n'.join(r['text'] for r in card['rows'])
    extra=extra.replace('24','99',1)
    source=edit_source(s,'impact_0000.rad','/END',extra+'\r\n/END')
    with pytest.raises(ValueError,match='참조되지'):parse_source(source)
    source=edit_source(s,'impact_0000.rad','/MAT/ELAST/1\r\n','/MAT/ELAST/1\r\n\r\n')
    with pytest.raises(ValueError,match='빈 행'):parse_source(source)


def test_missing_new_include_and_invalid_effective_boundary_are_source_errors():
    s=assembly_definition();file='parts/body.inc';raw=original_files(s['source'])[file]
    offset=raw.index(b'mesh.inc')
    with pytest.raises(SourceError,match='포함 파일'):
        replace_range(s['source'],file,offset,offset+len(b'mesh.inc'),'missing.inc',reason='UNIT missing',
                      expected_source_sha256=canonical_hash(s['source']))
    for offset in (-1,True,10**9):
        with pytest.raises(SourceError):original_offset(s['source'],file,offset)


def test_real_owned_python_cancel_is_reaped_not_native_evidence(tmp_path,monkeypatch):
    from caelab import execution_control as control
    processes=[];original=control.subprocess.Popen
    def launch(*a,**kw):
        p=original(*a,**kw);processes.append(p);return p
    monkeypatch.setattr(control.subprocess,'Popen',launch)
    token=control.CancellationToken();timer=threading.Timer(.2,token.request)
    timer.start()
    try:
        with control.cancellation_scope(token),pytest.raises(control.ExecutionCancelled):
            control.run_owned_command([sys.executable,'-c','import time;time.sleep(30)'],tmp_path,
                                      'unit_owned_cancel_not_native',timeout=5,owned_tree=True)
    finally:
        timer.cancel();timer.join()
        # Preserve ownership even if an assertion or platform-specific failure occurs.
        for p in processes:
            if p.poll() is None:control.stop_owned_process(p,isolated_group=os.name=='posix')
    assert processes and all(p.poll() is not None for p in processes)
    assert token.observed and not token.cleanup_pending
