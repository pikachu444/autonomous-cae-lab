"""Exact public C1 observations replayed through explicit native object doubles.

The original .caepre/FCStd/mesh/BREP bytes are actual retained public inputs.
Constructing the property doubles below is NOT a native FreeCAD restore.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import hashlib
import json
import zipfile

from caelab import native_cad
from apps.desktop_pre.shell_edit import ShellEditor
from test_shell_edit import OwnerDouble
from test_b13_native_boundaries import Doc

ARCHIVE = Path(__file__).parent/'fixtures/b13_c1_stamp_public_inputs.zip'
EXPECTED_SHA = '543356fc526483866e94eadfbf21d9b1f46286c9008283370896fb758239cd6e'


def public_inputs(folder):
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == EXPECTED_SHA
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read('MANIFEST.json'))
        assert set(archive.namelist()) == {'MANIFEST.json', *(r['path'] for r in manifest['files'])}
        for row in manifest['files']:
            data = archive.read(row['path'])
            assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
            path = folder/row['path']; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    return folder


def pose(values):
    return NS(Base=NS(x=values[0], y=values[1], z=values[2]), Rotation=NS(Q=values[3:]))


class Shape:
    """Returns recorded BREP bytes; only native geometry access is doubled."""
    def __init__(self, text):
        self.text = text
        self.names = {'Face1', 'Face2'}
        self.valid = True
    def isValid(self): return self.valid
    def exportBrepToString(self): return self.text
    def copy(self): return deepcopy(self)
    def getElement(self, name):
        if name not in self.names: raise ValueError('Missing native subelement: '+name)
        return name


def saved_editor(folder, *, project=None, current_text=None):
    inputs = public_inputs(folder/'inputs')
    project = project or inputs/'source/design.caepre'
    manifest, entry = native_cad.unpack_project(project, folder/'opened')
    aid = 'ShellAnalysis'; record = deepcopy(manifest['metadata']['shells'][aid])
    draft, observed = record['draft'], record['applied']['native']
    native = json.loads((inputs/'stamp/current-native-mesh.json').read_text(encoding='utf-8'))
    doc = Doc(); doc.Name = 'B13C1Replay'; doc.Label = doc.Name; doc.FileName = str(entry)
    doc.OutList = []; doc.Restoring = doc.Importing = False
    analysis = doc.new(aid, 'Fem::FemAnalysis'); analysis.Group = []
    analysis.addObject = lambda obj: analysis.Group.append(obj)
    source = doc.new('CurvedPatch', 'Part::Feature')
    source.Shape = Shape(current_text or (inputs/'stamp/CurvedPatch-exportBrepToString.brep').read_text(encoding='ascii'))
    source.pose = pose(draft['binding']['mesh_source']['placement'])
    source.getGlobalPlacement = lambda: source.pose
    for kind, name in observed['members']:
        analysis.addObject(doc.new(name, kind))
    mesh = doc.getObject(draft['mesh_id'])
    mesh.Shape = source; mesh.pose = pose(draft['binding']['mesh_placement'])
    mesh.getGlobalPlacement = lambda: mesh.pose
    nodes = {n: NS(x=p[0], y=p[1], z=p[2]) for n, p in native['nodes']}
    connectivity = {e: conn for family in native['elements'].values() for e, conn in family}
    mesh.FemMesh = NS(Nodes=nodes, getElementNodes=lambda e: connectivity[e],
                      **{family: [e for e, _ in rows] for family, rows in native['elements'].items()})
    solver = doc.getObject(draft['solver_id'])
    for key, value in observed['solver'].items(): setattr(solver, key, value)
    material = doc.getObject(draft['material_id'])
    material.Material = deepcopy(observed['material']); material.Category = 'Solid'
    def references(rows):
        return [(doc.getObject(r['object_id']), tuple(r['subelements'])) for r in rows]
    material.References = references(observed['material_refs'])
    for row in observed['regions']:
        section, pressure = doc.getObject(row['geometry_id']), doc.getObject(row['pressure_id'])
        section.Thickness = row['thickness_mm']; section.Offset = row['offset']
        section.CAEAxisReference = NS(**dict(zip('xyz', row['axis'])))
        section.CAENormalOrientation = row['orientation']
        section.CAEElementIds = deepcopy(row['section_elements'])
        section.References = references(row['section_refs'])
        pressure.Pressure = row['pressure_MPa']; pressure.Reversed = row['pressure_reversed']
        pressure.EnableAmplitude = row['pressure_amplitude']
        pressure.CAEElementIds = deepcopy(row['pressure_elements'])
        pressure.References = references(row['pressure_refs'])
    owner = OwnerDouble(manifest['metadata']); owner.doc = doc
    editor = ShellEditor(owner); owner.shell = editor
    if 'shell_binding_evidence' in manifest:
        editor.restore_binding_evidence(manifest['shell_binding_evidence'])
    return editor, inputs, manifest, entry, connectivity
