"""Execute supplied official Python source with explicit numeric stand-ins.

These are differential source checks, not a native FreeCAD runtime test.
A full checkout without the supplied reference source skips only these checks.
"""
import ast
import io
import math
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from test_beam_support import model
from caelab.beam_model import native_axis_formula
from caelab.beam_deck import section_card

ROOT=Path(__file__).resolve().parents[1]/'reference_FreeCAD_1.1.4'/'Fem'


def test_example_solver_factory_exists_in_installed_freecad_source():
    """Read the native public API without importing FreeCAD or creating a model."""
    repo=Path(__file__).resolve().parents[1]
    installed=repo/'runs/prepost-session-20261008-01/tools/FreeCAD_1.1.4-Windows-x86_64-py311/Mod/Fem/ObjectsFem.py'
    source=ROOT/'ObjectsFem.py'
    if not source.is_file():source=installed
    if not source.is_file():pytest.skip('Pinned FreeCAD ObjectsFem source is not available')
    public={n.name for n in ast.parse(source.read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef)}
    example=ast.parse((repo/'examples/beam/beam_example.py').read_text(encoding='utf-8'))
    factories={n.func.attr for n in ast.walk(example) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
               and isinstance(n.func.value,ast.Name) and n.func.value.id=='ObjectsFem'}
    assert factories and factories<=public


def test_property_projection_binds_native_factory_names_without_using_sectiontype(monkeypatch):
    """Native API signatures, explicit object doubles; no FEM execution."""
    import sys
    from apps.desktop_pre import beam_edit
    objects={}
    analysis=NS(Group=[])
    analysis.addObject=lambda obj:analysis.Group.append(obj)
    objects['Analysis']=analysis;objects['Line']=NS(Name='Line')
    for name in ('End1','End2'):objects[name]=NS(Name=name,Proxy=NS(Type='CAELab::BeamEnd'));analysis.Group.append(objects[name])
    def make(doc,name):
        obj=NS(Name=name,Material={});objects[name]=obj;return obj
    # Preserve 1.1.4 positional meaning: argument 2 is sectiontype, not name.
    def make_section(doc,sectiontype='Rectangular',width=10.,height=25.,thickness=2.,name='ElementGeometry1D'):
        assert sectiontype=='Rectangular';return make(doc,name)
    module=NS(makeElementGeometry1D=make_section,makeElementRotation1D=make,makeMaterialSolid=make)
    monkeypatch.setitem(sys.modules,'ObjectsFem',module)
    monkeypatch.setattr(beam_edit.beam_native,'get_object',lambda owner,key,path:objects[key])
    draft=model()['draft']
    draft['section'].update(object_id=None,rotation_id=None);draft['material']['object_id']=None
    record={'draft':draft,'end_object_ids':['End1','End2']}
    beam_edit.project_properties(NS(doc=NS()),record)
    assert draft['section']['object_id']=='BeamSection' and objects['BeamSection'].SectionType=='Rectangular'
    assert objects['BeamSection'].RectWidth=='10 mm' and objects['BeamSection'].RectHeight=='20 mm'
    assert objects['End2'].MomentY=='1000 N*mm'


class Vector:
    def __init__(self,*args):self.v=list(args[0]) if len(args)==1 else list(args)
    def __iter__(self):return iter(self.v)
    @property
    def Length(self):return math.hypot(*self.v)
    def __mul__(self,a):return Vector([v*a for v in self.v])
    __rmul__=__mul__
    def __truediv__(self,a):return self*(1/a)
    def __add__(self,b):return Vector([a+b for a,b in zip(self.v,b.v)])
    def dot(self,b):return sum(x*y for x,y in zip(self.v,b.v))
    def cross(self,b):
        from caelab.beam_model import cross
        return Vector(cross(self.v,b.v))


def function(path,name,namespace):
    if not path.exists():pytest.skip('Supplied FreeCAD 1.1.4 reference source not present; run native acceptance separately')
    source=ast.parse(path.read_text(encoding='utf-8-sig'))
    node=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
    return namespace[name]


@pytest.mark.parametrize('direction',[(1,0,0),(-1,0,0),(0,1,0),(0,0,1),(0,0,-1),(.7,1.4,-2),(.7,1.4,2)])
@pytest.mark.parametrize('angle',[0,90,-90,45,360])
def test_rotation_against_official_source_body(direction,angle):
    native=function(ROOT/'femmesh'/'meshtools.py','get_beam_main_axis_m',{'FreeCAD':NS(Vector=Vector)})
    assert list(native(Vector(direction),angle))==pytest.approx(native_axis_formula(direction,angle),abs=1e-13)


@pytest.mark.parametrize('angle',[0,90,-45])
def test_section_against_official_writer_body(angle):
    native=function(ROOT/'femsolver'/'calculix'/'write_femelement_geometry.py','write_femelement_geometry',{})
    quantity=lambda value:NS(getValueAs=lambda unit:NS(Value=value))
    value=model(angle);section=NS(SectionType='Rectangular',RectWidth=quantity(10),RectHeight=quantity(20))
    context=NS(solver_obj=NS(ExcludeBendingStiffness=False),mat_geo_sets=[{'ccx_elset':[23,88],
        'ccx_elset_name':'BEAM','mat_obj_name':'BEAMMAT','beamsection_obj':section,'beam_axis_m':value['axes']['local1']}])
    stream=io.StringIO();native(stream,context)
    effective='\n'.join(line for line in stream.getvalue().splitlines() if line.strip() and not line.startswith('**'))+'\n'
    assert effective==section_card(value)
