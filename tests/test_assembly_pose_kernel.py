"""Real OCC tests, including original retained source/draft binary geometries.

These are NOT Windows FreeCAD/Gmsh/cold-process acceptance. The small adapter
only exposes real OCC shapes through the read-only protocol used by production.
"""
import hashlib
import io
import json
from pathlib import Path
import pytest

pytest.importorskip('cadquery', reason='Optional existing OCC kernel; no new product dependency')
from assembly_pose_kernel_support import KernelShape, retained_shape, location, cq, brep
from apps.desktop_pre.assembly_pose_geometry import assert_same_shape
from caelab.adapters.native_face_catalog import GEOMETRY_TOLERANCES

FIXTURE = Path(__file__).parent/'fixtures/assembly_pose_native'


def retained():
    observation=json.loads((FIXTURE/'geometry.json').read_text())
    source=retained_shape(FIXTURE/'source.caepre','SliderBlock')
    copied=retained_shape(FIXTURE/'draft.caepre','SliderBlock')
    binder=retained_shape(FIXTURE/'draft.caepre','PoseBody')
    world=KernelShape(source.s.moved(location(observation['expected_occurrence']['world_pose'])))
    return source,copied,binder,world


def test_actual_retained_binary_solid_compound_unique_full_faces_without_mutation():
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURE.iterdir() if p.is_file()}
    source,copied,binder,world=retained()
    assert binder.s.ShapeType()=='Compound' and world.s.ShapeType()=='Solid'
    assert binder.s.location().toTuple()[0] == (0.,0.,0.)
    assert len(binder.Solids)==1 and len(binder.Faces)==6
    assert brep(binder)!=brep(world), 'Must exercise two different native representations'
    snapshots=[brep(s) for s in (source,copied,binder,world)]
    assert_same_shape(None,source,copied,'복사본')
    result=assert_same_shape(None,binder,world,'보존한 기준 부품')
    assert result['tolerances']==GEOMETRY_TOLERANCES
    assert result['symmetric_difference_mm3']==0.
    assert result['native_face_count']==result['step_face_count']==6
    assert [brep(s) for s in (source,copied,binder,world)]==snapshots
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in FIXTURE.iterdir() if p.is_file()}==before


@pytest.mark.parametrize('which', ['translate','rotate','different_solid'])
def test_real_location_rotation_or_solid_change_is_rejected(which):
    _,_,binder,world=retained()
    if which=='translate': wrong=KernelShape(world.s.translate((.01,0,0)))
    elif which=='rotate': wrong=KernelShape(world.s.rotate((100,25,15),(100,25,16),.01))
    else: wrong=KernelShape(cq.Solid.makeBox(12,8,6.1).moved(world.s.location()))
    with pytest.raises(ValueError):assert_same_shape(None,binder,wrong,'변경 부품')


@pytest.mark.parametrize('extra', ['face','edge','vertex','solid'])
def test_one_solid_plus_stray_topology_never_admitted(extra):
    _,_,binder,world=retained()
    if extra=='face': stray=cq.Face.makePlane(2,2,(400,400,400))
    elif extra=='edge': stray=cq.Edge.makeLine((400,400,400),(401,400,400))
    elif extra=='vertex': stray=cq.Vertex.makeVertex(400,400,400)
    else: stray=cq.Solid.makeBox(2,2,2).translate((400,400,400))
    wrong=KernelShape(cq.Compound.makeCompound([binder.s,stray]))
    with pytest.raises(ValueError):assert_same_shape(None,wrong,world,'추가 형상')


def test_same_bounds_volume_center_and_face_count_but_different_cavities_are_rejected():
    block=cq.Solid.makeBox(12,8,6)
    # Equal-size mirrored hole pairs: same volume, centroid, outer bounds and
    # face count. Only full solid/face geometry can distinguish them reliably.
    def hollow(points):
        result=block
        for x,y in points:
            result=result.cut(cq.Solid.makeCylinder(.5,8,(x,y,-1)))
        return KernelShape(result)
    a=hollow([(3,2),(9,6)]);b=hollow([(3,6),(9,2)])
    assert abs(a.Volume-b.Volume)<1e-8 and len(a.Faces)==len(b.Faces)
    assert (a.CenterOfMass-b.CenterOfMass).Length<1e-8
    assert vars(a.BoundBox)==vars(b.BoundBox)
    with pytest.raises(ValueError):assert_same_shape(None,a,b,'다른 구멍')


def test_brep_readback_of_distinct_topology_remains_equal():
    _,_,binder,world=retained()
    restored=KernelShape(cq.Shape.importBrep(io.BytesIO(brep(binder))))
    assert not restored.s.isSame(binder.s)  # Not a shared-TShape comparison.
    assert_same_shape(None,restored,world,'다시 읽은 형상')


def test_same_solid_different_face_partition_cannot_reuse_face_identity():
    split_x=cq.Solid.makeBox(6,8,6).fuse(cq.Solid.makeBox(6,8,6).translate((6,0,0)))
    split_y=cq.Solid.makeBox(12,4,6).fuse(cq.Solid.makeBox(12,4,6).translate((0,4,0)))
    a,b=KernelShape(split_x),KernelShape(split_y)
    assert len(a.Faces)==len(b.Faces) and len(a.Faces)>6
    assert abs(a.cut(b).Volume)+abs(b.cut(a).Volume)<1e-8
    with pytest.raises(ValueError) as error:assert_same_shape(None,a,b,'분할된 면')
    assert 'face' in str(error.value.__cause__).lower()


@pytest.mark.parametrize('embedded',[False,True])
def test_definition_to_link_removes_object_transform_not_assumed_local_outer(embedded):
    from types import SimpleNamespace as NS
    from assembly_pose_kernel_support import KernelPlacement
    from apps.desktop_pre.assembly_pose_geometry import definition_at_link
    import math
    object_pose=location([50.,10.,-3.,0.,0.,math.sin(.2),math.cos(.2)])
    link_pose=location([100.,25.,15.,0.,0.,math.sin(.13),math.cos(.13)])
    internal=location([3.,4.,5.,math.sin(.1),0.,0.,math.cos(.1)])
    local=cq.Solid.makeBox(12,8,6).moved(internal)
    if embedded:shape=KernelShape(cq.Compound.makeCompound([local.moved(object_pose)]))
    else:shape=KernelShape(local.moved(object_pose))
    source=NS(Placement=KernelPlacement(object_pose),Shape=shape)
    link=NS(Placement=KernelPlacement(link_pose))
    before=brep(shape)
    result=definition_at_link(source,link)
    expected=KernelShape(local.moved(link_pose))
    assert_same_shape(None,result,expected,'현재 원부품')
    assert brep(shape)==before
