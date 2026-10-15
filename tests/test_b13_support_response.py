"""Analytic quadrature/translation and counterexamples, not solver validation."""
import pytest
from caelab.beam_support_response import integrate_face, moment_about, sum_observed_rf, derived_rotation

POINTS=[[0,-5,10],[0,-5,-10],[0,5,-10],[0,5,10],
        [0,-5,0],[0,0,-10],[0,5,0],[0,0,10]]


def test_analytic_axial_bending_reaction_and_reference_shift():
    # Rect 10x20 mm; N=100 N and My=1000 Nmm on opposite end.
    # sigma_xx=N/A + My*z/Iy. Tolerance declared at 1e-10 absolute.
    stress=[[.5+1000*p[2]/(10*20**3/12),0,0,0,0,0] for p in POINTS]
    zero=integrate_face(POINTS,stress,[-1,0,0],[0,0,0])
    assert zero['force_N']==pytest.approx([-100,0,0],abs=1e-10)
    assert zero['moment_Nmm']==pytest.approx([0,-1000,0],abs=1e-10)
    assert zero['area_mm2']==pytest.approx(200,abs=1e-10)
    moved=integrate_face(POINTS,stress,[-1,0,0],[4,3,2])
    assert moved['moment_Nmm']==pytest.approx(moment_about(zero['force_N'],zero['moment_Nmm'],[0,0,0],[4,3,2]),abs=1e-10)
    assert moved['discrete_constraint_reaction'] is False
    opposite=integrate_face(POINTS,stress,[1,0,0],[0,0,0])
    assert opposite['force_N'][0]>0  # Wrong outward sign fails the same equilibrium criterion.
    assert opposite['moment_Nmm'][1]>0


def test_raw_RF_has_its_own_moment_without_discrete_reaction_claim():
    value=sum_observed_rf({11:[0,0,1],17:[0,0,-1]},{11:[2,0,0],17:[-2,0,0]},[0,0,0])
    assert value['force_N']==[0,0,0] and value['moment_Nmm']==[0,4,0]
    assert value['total_constraint_reaction']=='UNAVAILABLE'
    with pytest.raises(ValueError):sum_observed_rf({11:[0,0,1],17:[0,0,-1]},{11:[2,0,0]},[0,0,0])


def test_missing_tensor_is_never_zero_and_duplicate_support_set_is_rejected():
    with pytest.raises(ValueError):integrate_face(POINTS,[[1]*6]*7,[-1,0,0],[0,0,0])
    from b13_raw_fixture import raw_model
    from caelab.beam_model import validate_draft
    m=raw_model();m['draft']['output']['supports'][0]['ends']=[0,0]
    assert any(r['path'].startswith('output.supports') for r in validate_draft(m['draft']))


def test_nonrigid_fit_keeps_residual_instead_of_claiming_native_rotation():
    section={'expanded_node_ids':list(range(8)),'positions_mm':POINTS,
             'element_id':23,'beam_node_id':101,'station_kind':'start'}
    displacements={i:[0,0,0] for i in range(8)};displacements[0]=[.25,0,0]
    value=derived_rotation(section,displacements,{})
    assert value['fit_rms_mm']>0 and value['native_generalized_rotation'] is False
    assert value['native_displacements_mm'][0]==[.25,0,0]
