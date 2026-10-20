"""Production editor/writer paths with explicit property and geometry doubles.

The included FreeCAD 1.1.4 Python writer functions themselves are executed.
CAD geometry/Units/objects are doubles, not a FreeCAD/native acceptance claim.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS,ModuleType
import importlib.util
import json
import hashlib
import os
import sys
import pytest
from b13_shell_fixture import model
from test_shell_edit import OwnerDouble
from apps.desktop_pre.shell_edit import ShellEditor,SETTINGS
from apps.desktop_pre.shell_freeze import _native_fragments
from caelab.shell_model import prepare_mesh,ShellError
from caelab.adapters.shell_deck import build


class Quantity:
    def __init__(self,value):self.Value=float(str(value).split()[0])
    def getValueAs(self,unit):return self


class Object:
    def __init__(self,doc,name,kind):
        self.Document=doc;self.Name=name;self.Label=name;self.TypeId=kind
        self.PropertiesList=[];self.State=[];self.References=[];self.Suppressed=False
    def __setattr__(self,key,value):
        if key in ('Thickness','Pressure'):value=Quantity(value)
        super().__setattr__(key,value)
    def addProperty(self,kind,name,group):self.PropertiesList.append(name)


class Doc:
    def __init__(self):self.objects={}
    @property
    def Objects(self):return list(self.objects.values())
    def getObject(self,name):return self.objects.get(name)
    def new(self,name,kind):
        candidate=name;i=1
        while candidate in self.objects:i+=1;candidate=name+str(i)
        o=Object(self,candidate,kind);self.objects[candidate]=o;return o


class Editor(ShellEditor):
    def __init__(self,owner,m):super().__init__(owner);self.m=m
    def _stamp(self,d):return d['binding']
    def _mesh(self,d):
        return self._object(d['mesh_id']),{int(n):p for n,p in self.m['source_nodes'].items()},{int(e):c for e,c in self.m['source_elements'].items()}
    def _fixed(self,d,mesh):return self.m['fixed_nodes']
    def inspect(self,analysis_id):return {'record':self._record(analysis_id)}


@pytest.fixture
def editor(monkeypatch):
    m=model();d=m['draft'];doc=Doc()
    analysis=doc.new(d['analysis_id'],'Fem::FemAnalysis');analysis.Group=[];analysis.addObject=lambda o:analysis.Group.append(o)
    solver=doc.new(d['solver_id'],'Fem::SolverCcxTools');analysis.addObject(solver)
    mesh=doc.new(d['mesh_id'],'Fem::FemMeshObject');mesh.FemMesh=NS();analysis.addObject(mesh)
    for ref in [r for row in d['regions'] for r in row['face_refs']]:
        if not doc.getObject(ref['object_id']):doc.new(ref['object_id'],'Part::Feature')
    d['material_id']=None
    for row in d['regions']:row['geometry_id']='';row['pressure_id']=''
    owner=OwnerDouble({'shells':{d['analysis_id']:{'draft':d,'applied':None}}});owner.doc=doc
    vector=lambda x,y,z:NS(x=x,y=y,z=z)
    owner.App=NS(Vector=vector,Units=NS(Quantity=Quantity))
    factories=ModuleType('ObjectsFem')
    def material(doc):
        o=doc.new('Material','Fem::MaterialCommon');o.Category='Solid';o.Material={};return o
    factories.makeMaterialSolid=material
    factories.makeElementGeometry2D=lambda doc:doc.new('Section','Fem::ElementGeometry2D')
    factories.makeConstraintPressure=lambda doc:doc.new('Pressure','Fem::ConstraintPressure')
    monkeypatch.setitem(sys.modules,'ObjectsFem',factories)
    return Editor(owner,m)


def test_native_region_apply_import_stale_and_new_owner_metadata(editor):
    key=editor.m['draft']['analysis_id'];editor.apply(key)
    record,mesh,fixed=editor.effective(key)
    assert [r['thickness_mm'] for r in record['applied']['native']['regions']]==[2.,3.]
    before=deepcopy(record);fresh_owner=OwnerDouble(json.loads(json.dumps(editor.owner.data)))
    fresh_owner.doc=editor.owner.doc;fresh_owner.App=editor.owner.App
    fresh=Editor(fresh_owner,editor.m);assert fresh.effective(key)[0]==before
    section=fresh._object(record['draft']['regions'][1]['geometry_id']);section.Thickness='4 mm'
    with pytest.raises(ShellError,match='native'):fresh.effective(key)
    from apps.desktop_pre.shell_region_native import import_properties
    import_properties(fresh,key)
    updated=fresh._record(key)
    assert updated['draft']['regions'][1]['thickness_mm']=='4.0' and 'applied' not in updated
    assert before['applied']['draft']['regions'][1]['thickness_mm']=='3'


def reference_writers(monkeypatch):
    root=Path(os.environ.get('CAELAB_FREECAD_REFERENCE_FEM',
        str(Path(__file__).resolve().parents[1]/'reference_FreeCAD_1.1.4/Fem')))
    expected={'write_constraint_pressure':'3feb8913d0146c5434a09e27bf64f926023e10c5108ff019596a95872eaf96c7',
        'write_femelement_geometry':'d18c36cee7a297f23195d46a0f695d025b67770a390b08bc979a9baed5dd7af4',
        'write_femelement_material':'3e056939b6d465079ec79a3fcdd1157bf3bff8b2f9a7b52bc415bacc4dcf20fa'}
    for leaf,digest in expected.items():
        path=root/'femsolver/calculix'/f'{leaf}.py'
        assert path.is_file(), 'Set CAELAB_FREECAD_REFERENCE_FEM to the exact FreeCAD 1.1.4 Mod/Fem source'
        # Release ZIP and official Git source differ only in line endings.
        assert hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()==digest, f'FreeCAD 1.1.4 source changed: {path}'
    for name in ('FreeCAD','femtools','femtools.constants','femsolver','femsolver.calculix'):
        mod=ModuleType(name);mod.__path__=[];monkeypatch.setitem(sys.modules,name,mod)
    sys.modules['FreeCAD'].Units=NS(Quantity=Quantity)
    sys.modules['femtools'].constants=sys.modules['femtools.constants']
    for leaf in ('write_femelement_geometry','write_femelement_material','write_constraint_pressure'):
        name='femsolver.calculix.'+leaf
        spec=importlib.util.spec_from_file_location(name,root/'femsolver/calculix'/f'{leaf}.py')
        module=importlib.util.module_from_spec(spec);monkeypatch.setitem(sys.modules,name,module);spec.loader.exec_module(module)


def test_actual_reference_python_writers_not_replacement_sections(editor,monkeypatch):
    reference_writers(monkeypatch)
    key=editor.m['draft']['analysis_id'];editor.apply(key)
    record,prepared,_=editor.effective(key)
    sections,pressure,material=_native_fragments(editor,record['draft'],prepared)
    m=deepcopy(editor.m);m.update(draft=record['draft'],applied=record['applied'],native_sections=sections,
                                 native_pressure=pressure,native_material=material,material_name=record['draft']['material_id'])
    text,_=build(m)
    assert '*SHELL SECTION' in text and '*DLOAD' in text
    assert 'OFFSET=0.25' in text or 'OFFSET=-0.25' in text
    # A changed writer may not silently consume a wrong region thickness.
    m['native_sections']=sections.replace('\n3\n','\n4\n')
    assert m['native_sections']!=sections
    with pytest.raises(ValueError):build(m)


def test_beam_region_read_maps_only_exact_retained_bijection(monkeypatch):
    from test_beam_mesh_binding import data,bind
    from apps.desktop_pre import beam_native,beam_axis_native
    from caelab.beam_output import DEFAULT,element_axes
    old,record,current,binding=data('moment_1');bind(record,old)
    d=record['draft'];d['output']=deepcopy(DEFAULT);d['output']['mode']='raw_stress'
    d['axis_regions']=[{'id':'R1','label':'전체','elements':[r['id'] for r in old['elements']],
                       'rotation_deg':'90','rotation_id':'RNative'}]
    original=deepcopy(record)
    monkeypatch.setattr(beam_native,'geometry',lambda owner,draft:(deepcopy(current),deepcopy(binding)))
    def axes(owner,m):m['element_axes']=element_axes(m['draft'],m['axes']['tangent'],{r['id'] for r in m['elements']})
    monkeypatch.setattr(beam_axis_native,'geometry_axes',axes)
    out,_,mapping=beam_axis_native.geometry_with_reference(NS(),record)
    assert mapping['kind']=='RENUMBERED' and out['draft']['axis_regions'][0]['elements']==list(range(1,11))
    assert record==original
    current['nodes'][1]['xyz_mm'][0]+=1e-12
    with pytest.raises(ValueError):beam_axis_native.geometry_with_reference(NS(),record)


def test_explicit_import_of_new_native_regions_does_not_refresh_old_binding(editor,monkeypatch):
    from apps.desktop_pre.shell_region_native import import_properties
    key=editor.m['draft']['analysis_id'];editor.apply(key)
    record=editor._record(key)
    # A saved legacy/uniform record with native sections changed externally.
    old_binding={'source':'previous_geometry'}
    record['draft']['binding']=deepcopy(old_binding)
    record['draft'].pop('regions')
    editor._store(key,record,'retain legacy raw record')
    monkeypatch.setattr(editor,'_stamp',lambda draft:{'source':'current_geometry'})
    native_names=[o.Name for o in editor._object(key).Group]
    import_properties(editor,key)
    imported=editor._record(key)
    assert len(imported['draft']['regions'])==2
    assert [r['thickness_mm'] for r in imported['draft']['regions']]==['2.0','3.0']
    assert imported['draft']['binding']==old_binding and imported['applied'] is None
    assert [o.Name for o in editor._object(key).Group]==native_names
    with pytest.raises(ShellError):editor._binding(imported['draft'])
