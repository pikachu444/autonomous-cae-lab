"""Pure example geometry/reference checks. Native create/check functions NOT run."""
from copy import deepcopy
import pytest
from examples.b13.models import curved_mesh,beam_reference
from caelab.shell_model import DEFAULTS,prepare_mesh
from caelab.shell_regions import uniform_region,reverse_region


def test_cylindrical_two_thickness_mesh_and_explicit_reversal():
    nodes,elements,fixed,groups=curved_mesh()
    d=deepcopy(DEFAULTS);d.update(elements=sorted(elements),orientation='native',axis_x='0',axis_z='1',face_refs=[])
    rows=[]
    for i,ids in enumerate(groups):
        r=uniform_region(d);r.update(id=f'R{i+1}',label=f'곡면 {i+1}',elements=ids,thickness_mm=str(i+2),offset='0.25' if i else '0')
        rows.append(r)
    d['regions']=rows
    mesh=prepare_mesh(nodes,elements,d);changed=prepare_mesh(nodes,elements,reverse_region(d,'R2'))
    assert len(mesh['elements'])==8 and len(fixed)==5
    assert set(groups[0]).isdisjoint(groups[1]) and set(groups[0]+groups[1])==set(elements)
    assert mesh['normals'][groups[1][0]]==pytest.approx([-x for x in changed['normals'][groups[1][0]]])
    assert len({tuple(p) for p in mesh['normals'].values()})>1


def test_analytical_reference_is_not_a_native_observation():
    a=beam_reference(0.,'moment_1');b=beam_reference(90.,'moment_1')
    assert a['reference_only'] and b['reference_only']
    assert b['tip_U_mm'][2]==pytest.approx(4*a['tip_U_mm'][2])
    assert a['support_M_about_global_origin_Nmm']==[0.,-1000.,0.]
    assert beam_reference(0.,'end_force')['support_F_N']==[0.,0.,1.]
