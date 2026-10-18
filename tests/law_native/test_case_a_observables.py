"""Retained-value projections only: these checks never run a solver/update."""
from copy import deepcopy
import numpy as np
import pytest
from caelab.law_native_fe import dp_observables
from caelab.law_native_inspection import populate
from caelab.storage import canonical_hash
from plugins.material_point import law_native as law
from caelab import law_native_fe as fe
from caelab.adapters.law_native_fe_worker import _boundary


@pytest.mark.parametrize('stress,pressure,q', [
    ([30.,0.,0.,0.,0.,0.], -10., 30.),
    ([-30.,0.,0.,0.,0.,0.], 10., 30.),
    ([-50.,-50.,-50.,0.,0.,0.], 50., 0.),
    ([0.,0.,0.,np.sqrt(2)*10,0.,0.], 0., np.sqrt(3)*10),
])
def test_signed_pressure_kelvin_shear_and_yield_value(stress,pressure,q):
    s=law.default_settings();state=deepcopy(s['initial_state'])
    state.update(plastic_strain_kelvin=[.001,.001,.001,0.,0.,0.],kappa=.002)
    original=canonical_hash([stress,state,s])
    actual=dp_observables(stress,state,s['parameters'])
    assert actual['pressure']==pytest.approx(pressure)
    assert actual['equivalent_stress']==pytest.approx(q)
    assert actual['plastic_volume_strain']==pytest.approx(.003)
    assert actual['kappa']==.002
    assert actual['yield_function']==pytest.approx(q-.2*pressure-250-1000*.002)
    assert canonical_hash([stress,state,s])==original


def test_missing_state_is_not_a_zero_plastic_strain():
    with pytest.raises(ValueError):
        dp_observables([0.]*6,{},law.default_settings()['parameters'])


def test_authored_cube_has_positive_tetrahedra_shared_midsides_and_free_center():
    from case_a_fixture import cube_c3d10
    fixture=cube_c3d10();points=np.asarray(fixture['points_mm'])
    assert len(points)==27 and len(fixture['cells_C3D10_1_based'])==6
    edges={};volumes=[]
    for cell in fixture['cells_C3D10_1_based']:
        assert len(set(cell))==10
        corners=points[np.asarray(cell[:4])-1]
        volumes.append(np.linalg.det((corners[1:]-corners[0]).T)/6)
        for (a,b),mid in zip(((0,1),(1,2),(0,2),(0,3),(1,3),(2,3)),cell[4:]):
            edge=tuple(sorted((cell[a],cell[b])))
            assert edges.setdefault(edge,mid)==mid
            np.testing.assert_array_equal(points[mid-1],(corners[a]+corners[b])/2)
    assert all(v>0 for v in volumes)
    assert sum(volumes)==pytest.approx(1.)
    interior=[p for p in points if all(0<x<1 for x in p)]
    assert len(interior)==1 and np.array_equal(interior[0],[.5,.5,.5])


def test_six_normal_face_dofs_are_not_affine_or_free_lateral():
    s=fe.default_settings();s['boundary']['mode']='box_normal_displacement'
    s['law']['deformation_gradient'][2]=np.diag([.994,.999,.999]).tolist()
    frozen=canonical_hash(s);fe.validate_settings(s)
    points=np.asarray(s['mesh']['points']);fixed,free,values=_boundary(s,points,2)
    actual=dict(zip(fixed,values));expected={}
    for node,p in enumerate(points):
        for axis in range(3):
            if p[axis]==0:expected[3*node+axis]=0.
            elif p[axis]==1:expected[3*node+axis]=s['law']['deformation_gradient'][2][axis][axis]-1
    assert actual==expected and len(free)==27
    assert all(3*13+i in free for i in range(3))
    assert canonical_hash(s)==frozen
    affine=deepcopy(s);affine['boundary']['mode']='affine_boundary'
    assert len(_boundary(affine,points,2)[1])==3
    uniaxial=deepcopy(s);uniaxial['boundary']['mode']='uniaxial_zero_lateral'
    uniaxial['law']['boundary_control']={'stress_components':{'yy':[0.]*4,'zz':[0.]*4},
        'solver':deepcopy(law.BOUNDARY_OPTIONS)}
    fe.validate_settings(uniaxial)
    assert len(_boundary(uniaxial,points,2)[1])==45


@pytest.mark.parametrize('fault',('shear','origin','initial','stress_control','finite_model','small_strain'))
def test_box_normal_rejects_unsupported_declarations_without_calculation(fault):
    s=fe.default_settings();s['boundary']['mode']='box_normal_displacement'
    if fault=='shear':s['law']['deformation_gradient'][2][0][1]=.001
    elif fault=='origin':s['boundary']['origin_mm']=[.1,0.,0.]
    elif fault=='initial':s['law']['deformation_gradient'][0][0][0]=1.001
    elif fault=='stress_control':s['law']['boundary_control']={'stress_components':{'yy':[0.]*4},'solver':deepcopy(law.BOUNDARY_OPTIONS)}
    elif fault=='finite_model':s['law']=law.default_settings('neo_hooke')
    else:s['law']['deformation_gradient'][2][0][0]=1.1
    original=canonical_hash(s)
    with pytest.raises(ValueError):fe.validate_settings(s)
    assert canonical_hash(s)==original


def test_skew_boundary_face_is_rejected_even_if_each_node_is_on_some_box_plane():
    s=fe.default_settings();s['boundary']['mode']='box_normal_displacement'
    node=s['mesh']['points'].index([1.,0.,.5])
    s['mesh']['points'][node]=[.8,0.,.5]  # Still on y-min, but breaks an x-max face.
    original=canonical_hash(s)
    with pytest.raises(ValueError,match='boundary face'):fe.validate_settings(s)
    assert canonical_hash(s)==original
    old=deepcopy(s);old['boundary']['mode']='affine_boundary'
    fe.validate_settings(old)  # The new admission must not change the old mode.
    old['boundary']['mode']='uniaxial_zero_lateral'
    old['law']['boundary_control']={'stress_components':{'yy':[0.]*4,'zz':[0.]*4},
        'solver':deepcopy(law.BOUNDARY_OPTIONS)}
    fe.validate_settings(old)


def test_native_authoring_inverts_existing_ccx_permutation_once_not_physics():
    from types import SimpleNamespace
    from case_a_fixture import cube_c3d10
    from apps.desktop_pre.freeze_analysis import CCX_FROM_NATIVE_TET10
    from apps.desktop_pre.fem_edit import _element_quality
    from caelab.contact import separate_meshes
    fixture=cube_c3d10()
    nodes={n:SimpleNamespace(x=p[0],y=p[1],z=p[2]) for n,p in enumerate(fixture['points_mm'],1)}
    native_cells={}
    for e,cell in enumerate(fixture['cells_C3D10_1_based'],1):
        native_ids=[None]*10
        for deck_slot,native_slot in enumerate(CCX_FROM_NATIVE_TET10):native_ids[native_slot]=cell[deck_slot]
        assert [native_ids[slot] for slot in CCX_FROM_NATIVE_TET10]==cell
        native_cells[e]=native_ids
    failed=SimpleNamespace(Nodes=nodes,getElementNodes=lambda e:fixture['cells_C3D10_1_based'][e-1])
    corrected=SimpleNamespace(Nodes=nodes,getElementNodes=lambda e:native_cells[e])
    assert all(_element_quality(failed,e)['errors'] for e in native_cells)
    assert all(not _element_quality(corrected,e)['errors'] for e in native_cells)
    captured=separate_meshes([dict(body_id='Specimen',
        nodes=[dict(node_id=n,position_mm=p) for n,p in enumerate(fixture['points_mm'],1)],
        elements=[dict(element_id=e,type='C3D10',native_node_ids=ids) for e,ids in native_cells.items()])],minimum_bodies=1)
    assert [e['node_ids'] for e in captured['elements']]==fixture['cells_C3D10_1_based']


def test_inspector_uses_exact_committed_state_not_input_or_trial():
    s=law.default_settings();initial=deepcopy(s['initial_state'])
    committed=deepcopy(initial);committed['plastic_strain_kelvin']=[.001]*3+[0.]*3
    row=dict(increment=1,time=1.,stress=[-30.,0.,0.,0.,0.,0.],
        stress_tensor=[[-30.,0.,0.],[0.,0.,0.],[0.,0.,0.]],stress_unit='MPa',
        stress_measure='infinitesimal_Cauchy',F=np.eye(3).tolist(),
        strain_kelvin=[0.]*6,initial_state=initial,initial_state_sha256=canonical_hash(initial),
        trial_state=deepcopy(initial),committed_state=committed,local={},tangent=None,
        tangent_pair=law.declaration(s)['tangent_pair'],frame=law.FRAME,
        stored_energy=None,dissipated_energy=None)
    result={'diagnostics':{'constitutive_increments':[row],'declaration':law.declaration(s)}}
    original=canonical_hash(result)
    view=populate({'unavailable':[]},result,s,1)
    quantities={q['components'][0]:q for q in view['quantities']}
    assert quantities['tr(εᵖ)']['values']==[.003]
    assert quantities['p']['values']==[10.]
    assert quantities['p']['origin']=='derived_from_retained_stress_and_committed_state'
    assert canonical_hash(result)==original
    # A tangent-probe failure can retain a trial with no committed state.
    row['committed_state']=None
    view=populate({'unavailable':[]},result,s,1)
    assert not any(q['components']==['tr(εᵖ)'] for q in view['quantities'])
