"""Native API boundary tests; real GUI and solver use remain separate checks."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import xml.etree.ElementTree as ET

import pytest

from test_pre_frozen_analysis import native
from test_frozen_fem import frd_text
from apps.desktop_pre.freeze_analysis import freeze_analysis, _freeze_legacy_analysis
from apps.desktop_pre.native_calculix import PROFILE, _ORDERS, read_deck, _mesh_quality
from caelab.adapters import frozen_fem
from caelab.adapters.native_calculix_results import inspect_frd, publish_conversion
from caelab.native_inputs import _frozen_files


def test_native_writer_snapshot_preserves_settings_and_registered_inputs(native, tmp_path):
    native.solver.GeometricalNonlinearity = 'nonlinear'
    native.solver.MaterialNonlinearity = 'nonlinear'
    native.mesh.FemMesh.getElementNodes = lambda identifier: list(range(1, 11))
    native.mesh.Shape = None  # An imported mesh need not have a CAD solid.
    record = freeze_analysis(native.analysis, native.solver, tmp_path / 'model')
    manifest, mesh, _, _ = frozen_fem.validate_snapshot(record)
    assert manifest['export_profile'] == PROFILE
    assert manifest['solver']['settings']['GeometricalNonlinearity'] == 'nonlinear'
    assert manifest['materials'][0]['properties']['Material']['YoungsModulus'] == '1000 MPa'
    assert manifest['conditions'][1]['properties']['References'][0][1] == ['Face2']
    assert mesh['elements'][0]['native_node_ids'] == list(range(1, 11))
    quality = manifest['mesh_quality']
    assert quality['status'] == 'MEASURED'
    assert quality['jacobian']['minimum'] == pytest.approx(1.)
    assert quality['jacobian']['unmeasured_element_count'] == 0
    paths, _ = _frozen_files(record, record.parent)
    assert {p.name for p in paths} == {'snapshot.json', 'editable.FCStd', 'mesh.json', 'ExistingMesh.inp'}


@pytest.mark.parametrize('element', ['C3D4', 'C3D6', 'C3D8', 'C3D10', 'C3D15', 'C3D20', 'S3', 'S4', 'S6', 'S8', 'B31', 'B32R'])
def test_native_writer_mesh_families_and_split_input_are_preserved(native, tmp_path, monkeypatch, element):
    count = len(_ORDERS[element])
    native.mesh.FemMesh.Nodes = {i: NS(x=float(i), y=0., z=0.) for i in range(1, count + 1)}
    inverse = [None] * count
    for i, slot in enumerate(_ORDERS[element]):
        inverse[slot] = i + 1
    native.mesh.FemMesh.getElementNodes = lambda identifier: inverse
    class Writer:
        def __init__(self, a, s, m, member, folder, sets):
            self.root = Path(folder)
        def write_solver_input(self):
            nodes = '\n'.join(f'{i},{i},0,0' for i in range(1, count + 1))
            (self.root / 'mesh.inp').write_text('*NODE\n' + nodes + f'\n*ELEMENT,TYPE={element}\n1,' + ','.join(map(str, range(1, count+1))) + '\n')
            text = ('*INCLUDE,INPUT=mesh.inp\n*MATERIAL,NAME=Steel\n*ELASTIC\n210000,.3\n'
                    '*PLASTIC\n300,0\n400,.1\n*SURFACE INTERACTION,NAME=Interface\n*FRICTION\n.2\n'
                    '*STEP,NLGEOM\n*STATIC\n.1,1\n*DLOAD\nBody,GRAV,9810,0,0,-1\n'
                    'Face,P,2\n*NODE FILE\nU\n*END STEP\n')
            path = self.root / 'model.inp'
            path.write_text(text)
            return str(path)
    monkeypatch.setattr(sys.modules['femsolver.calculix.writer'], 'FemInputWriterCcx', Writer)
    record = freeze_analysis(native.analysis, native.solver, tmp_path / element)
    manifest, mesh, _, _ = frozen_fem.validate_snapshot(record)
    assert mesh['elements'][0]['type'] == element
    assert {'*DLOAD', '*PLASTIC', '*FRICTION'} <= set(manifest['native_cards'])
    assert manifest['input_dependencies'] == ['model.inp', 'mesh.inp']
    assert len(_frozen_files(record, record.parent)[0]) == 5


@pytest.mark.parametrize('height,negative,zero', [(1., 0, 0), (-1., 1, 0), (0., 0, 1)])
def test_mesh_quality_reports_signed_measurements_without_a_gate(height, negative, zero):
    nodes = {1: NS(x=1., y=0., z=0.), 2: NS(x=0., y=0., z=0.),
             3: NS(x=0., y=1., z=0.), 4: NS(x=0., y=0., z=height)}
    mesh = NS(Nodes=nodes, getElementNodes=lambda identifier: [1, 2, 3, 4])
    quality = _mesh_quality(mesh, [{'element_id': 9, 'type': 'C3D4'}])
    metric = quality['jacobian']
    assert metric['minimum'] == metric['maximum'] == height
    assert metric['negative_element_count'] == negative
    assert metric['zero_element_count'] == zero
    assert 'errors' not in quality and 'admissible' not in quality


def test_mesh_quality_discloses_sampling_unsupported_types_and_missing_api():
    nodes = {1: NS(x=1., y=0., z=0.), 2: NS(x=0., y=0., z=0.),
             3: NS(x=0., y=1., z=0.), 4: NS(x=0., y=0., z=1.)}
    calls = []
    def connectivity(identifier):
        calls.append(identifier)
        return [1, 2, 3, 4]
    elements = [{'element_id': i, 'type': 'C3D4'} for i in range(1, 601)]
    elements[0]['type'] = 'C3D8'
    quality = _mesh_quality(NS(Nodes=nodes, getElementNodes=connectivity), elements)
    assert quality['status'] == 'PARTIALLY_MEASURED'
    assert quality['unmeasured_element_types'] == ['C3D8']
    assert len(quality['sampled_element_ids']) == 256 and len(calls) == 255
    assert quality['jacobian']['unmeasured_element_count'] == 345
    missing = _mesh_quality(NS(), elements)
    assert missing['status'] == 'NOT_MEASURED'
    assert missing['jacobian']['minimum'] is None
    assert missing['jacobian']['unmeasured_element_count'] == 600


def test_native_input_checks_are_not_replaced_with_case_whitelist(native, tmp_path):
    native.force.EnableAmplitude = True
    native.force.References = [(native.shape, ['Edge1'])]
    assert freeze_analysis(native.analysis, native.solver, tmp_path / 'valid').is_file()
    native.error = 'UserPressure has empty references.'
    with pytest.raises(ValueError, match='UserPressure'):
        freeze_analysis(native.analysis, native.solver, tmp_path / 'invalid')


def test_registered_mesh_binding_mismatch_is_not_ignored(native, tmp_path):
    native.mesh.PropertiesList = ['CAELabMeshSourceBinding']
    native.mesh.CAELabMeshSourceBinding = '{}'
    def invalid(mesh):
        raise ValueError('Source geometry changed')
    with pytest.raises(ValueError, match='Source geometry changed'):
        freeze_analysis(native.analysis, native.solver, tmp_path, binding_validator=invalid)


@pytest.mark.parametrize('family', ['Edges', 'Faces', 'Volumes'])
def test_native_writer_cannot_mutate_saved_mesh_connectivity(native, tmp_path, family):
    mesh = native.mesh.FemMesh
    setattr(mesh, family, [42])
    connectivity = [1, 2, 3]
    mesh.getElementNodes = lambda identifier: list(range(1, 11)) if identifier == 7 else connectivity
    native.after_write = lambda: connectivity.reverse()
    with pytest.raises(ValueError, match='source model changed'):
        freeze_analysis(native.analysis, native.solver, tmp_path)
    assert not list(tmp_path.rglob('snapshot.json'))


@pytest.mark.parametrize('changed', ['material', 'solver'])
def test_native_writer_cannot_mutate_material_or_solver(native, tmp_path, changed):
    def alter():
        if changed == 'material':
            native.material.Material['YoungsModulus'] = '2000 MPa'
        else:
            native.solver.MaterialNonlinearity = 'nonlinear'
    native.after_write = alter
    with pytest.raises(ValueError, match='source model changed'):
        freeze_analysis(native.analysis, native.solver, tmp_path)
    assert not list(tmp_path.rglob('snapshot.json'))
    assert native.source.read_bytes() == b'original document'


def test_generic_snapshot_reports_unconnected_aster_translation(native, tmp_path):
    from caelab.adapters.codeaster_frozen import prepare_input
    record = freeze_analysis(native.analysis, native.solver, tmp_path / 'input')
    with pytest.raises(ValueError, match='CalculiX'):
        prepare_input(record, tmp_path / 'aster')


def test_include_escape_and_missing_source_are_rejected(tmp_path):
    path = tmp_path / 'model.inp'
    path.write_text('*INCLUDE,INPUT=../other.inp\n')
    with pytest.raises(ValueError):
        read_deck(path)


def test_native_result_coverage_and_truncation(native, tmp_path):
    legacy = _freeze_legacy_analysis(native.analysis, native.solver, tmp_path / 'legacy')
    mesh = json.loads((legacy.parent / 'mesh.json').read_text())
    path = tmp_path / 'solver.frd'
    path.write_text(frd_text(mesh, (1, 2)))
    nodes, frames = inspect_frd(path)
    assert nodes == list(range(1, 11))
    assert [frame['value'] for frame in frames] == [1., 2.]
    assert frames[0]['fields']['DISP']['arrays'] == {'DISP'}
    path.write_text(path.read_text().replace(' 9999\n', ''))
    with pytest.raises(ValueError, match='complete result'):
        inspect_frd(path)


def test_converter_preserves_native_topology_and_missing_field_coverage(tmp_path):
    post = tmp_path / 'post'
    post.mkdir()
    frames = []
    for index, value in enumerate((.5, 1.)):
        (post / f'frame{index}.vtu').write_text(f'''<VTKFile type="UnstructuredGrid"><UnstructuredGrid>
<FieldData><DataArray Name="TimeValue" format="ascii">{value}</DataArray></FieldData>
<Piece NumberOfPoints="2" NumberOfCells="1"><PointData>
<DataArray Name="DISP" NumberOfComponents="3" format="ascii">0 0 0 {value} 0 0</DataArray>
<DataArray Name="CPRESS" format="ascii">12 0</DataArray>
<DataArray Name="PE" format="ascii">-0.1 0.2</DataArray></PointData>
<Points><DataArray NumberOfComponents="3" format="ascii">0 0 0 1 0 0</DataArray></Points>
<Cells><DataArray Name="types" format="ascii">3</DataArray></Cells>
</Piece></UnstructuredGrid></VTKFile>''')
        frames.append({'value': value, 'fields': {
            'DISP': {'name': 'DISP', 'ids': {17, 42}, 'arrays': {'DISP'}},
            'CONTACT': {'name': 'CONTACT', 'ids': {17}, 'arrays': {'CPRESS'}},
            'PE': {'name': 'PE', 'ids': {17, 42}, 'arrays': {'PE'}}}})
    result = publish_conversion(post, {'verification_case': '없음'}, [17, 42], frames)
    assert result['responses']['displacement']['value'] == [[0., 0., 0.], [1., 0., 0.]]
    fields = {row['name']: row for row in result['native_field_summary']['fields']}
    assert fields['PE']['ranges'][0] == {'minimum': -.1, 'maximum': .2, 'finite_count': 2, 'missing_count': 0}
    assert fields['CPRESS']['ranges'][0] == {'minimum': 12., 'maximum': 12., 'finite_count': 1, 'missing_count': 1}
    assert result['post_artifact']['native_metadata']['time']['values'] == [.5, 1.]
    collection = ET.parse(post / 'results.pvd')
    assert len(collection.findall('.//DataSet')) == 2
    tree = ET.parse(post / 'frame1.vtu')
    assert tree.find('.//DataArray[@Name="types"]').text == '3'
    # Missing contact nodes are represented as NaN via the existing VTK codec,
    # not the zero with which FreeCAD initializes absent tuples.
    assert tree.find('.//DataArray[@Name="CPRESS"]').get('format') == 'binary'


def test_independent_converter_retains_missing_fields_without_invented_units_or_completion(tmp_path):
    post = tmp_path / 'post'; post.mkdir()
    (post / 'frame.vtu').write_text('''<VTKFile><UnstructuredGrid>
<FieldData><DataArray Name="TimeValue">0.25</DataArray></FieldData>
<Piece NumberOfPoints="2" NumberOfCells="1"><PointData>
<DataArray Name="TEMP" format="ascii">72 0</DataArray></PointData>
<Points><DataArray>0 0 0 1 0 0</DataArray></Points></Piece></UnstructuredGrid></VTKFile>''')
    frames = [{'value': .25, 'fields': {'NDTEMP': {'name': 'NDTEMP', 'ids': {3}, 'arrays': {'TEMP'}}}}]
    result = publish_conversion(post, {}, [3, 9], frames, managed=False)
    summary = result['native_field_summary']
    assert summary['output_values'] == [.25]
    assert summary['time_units'] is None and summary['time_semantics'] is None
    assert summary['fields'][0]['units'] is None and summary['fields'][0]['frame'] is None
    assert summary['fields'][0]['ranges'][0] == {
        'minimum': 72., 'maximum': 72., 'finite_count': 1, 'missing_count': 1}
    assert 'responses' not in result and 'execution_status' not in result


@pytest.mark.parametrize('installation', ['PATH', 'root', 'bin'])
def test_adapter_runs_split_native_deck_and_uses_native_conversion(native, tmp_path, monkeypatch, installation):
    record = freeze_analysis(native.analysis, native.solver, tmp_path / 'input')
    app_root = tmp_path / 'FreeCAD'
    (app_root / 'bin').mkdir(parents=True)
    executable = (tmp_path if installation == 'PATH' else app_root / 'bin') / 'ccx.exe'
    executable.write_bytes(b'non-executable test boundary')
    app = (app_root if installation == 'root' else app_root / 'bin') / 'FreeCAD.exe'
    app.write_bytes(b'non-executable test boundary')
    runtime = None if installation == 'PATH' else {'freecad_executable': str(app)}
    monkeypatch.setattr(frozen_fem.shutil, 'which', lambda name: str(executable) if installation == 'PATH' else None)
    def command(args, cwd, label):
        assert Path(args[0]) == executable
        assert (cwd / 'ExistingMesh.inp').read_bytes() == (record.parent / 'ExistingMesh.inp').read_bytes()
        return NS(returncode=0)
    monkeypatch.setattr(frozen_fem, 'run_owned_command', command)
    def convert(frd, output, manifest, **kwargs):
        assert manifest['export_profile'] == PROFILE
        assert kwargs['freecad_executable'] == (runtime or {}).get('freecad_executable')
        post = output / 'post'
        post.mkdir()
        (post / 'results.pvd').write_text('<VTKFile/>')
        return {'responses': {}, 'post_artifact': {'relative': 'post/results.pvd'}, 'result_readability': 'READABLE'}
    monkeypatch.setattr('caelab.adapters.native_calculix_results.convert', convert)
    result = frozen_fem.FrozenFemAdapter().run({'snapshot_path': str(record)}, output=tmp_path / 'run', runtime=runtime)
    assert result['execution_status'] == 'SUCCEEDED'
    assert result['solver_exit_code'] == 0 and result['result_readability'] == 'READABLE'
    assert result['qualification'] == 'UNKNOWN' and not result['engineering_valid']
    assert result['runtime']['configuration'] == ('configured PATH' if installation == 'PATH' else 'configured FreeCAD installation')


@pytest.mark.skipif(not os.environ.get('CAELAB_TEST_FREECADCMD'), reason='Native FreeCAD converter is opt-in')
def test_installed_freecad_converts_original_solver_result(tmp_path, monkeypatch):
    from caelab.adapters.native_calculix_results import convert, convert_independent
    monkeypatch.setenv('FREECAD_CMD', os.environ['CAELAB_TEST_FREECADCMD'])
    source = Path(__file__).parent / 'fixtures/calculix_221_structural_family/family.frd'
    result = convert(source, tmp_path, {'steps': [{'period': 1.}], 'verification_case': '없음'})
    assert result['result_readability'] == 'READABLE'
    assert len(result['responses']['displacement']['value']) == 80
    assert (tmp_path / 'post/results.pvd').is_file()
    assert result['post_artifact']['native_metadata']['time']['values'] == [1.]
    standalone = convert_independent(source, tmp_path / 'independent')
    assert Path(standalone['entry_path']).is_file()
    assert standalone['units'] is None and standalone['execution_status'] is None
    summary = standalone['summary']
    assert summary['output_values'] == [1.]
    assert summary['frames'][0]['analysis_type'] is not None
    assert next(row for row in summary['fields'] if row['name'] == 'DISP')['component_names'] == ['D1', 'D2', 'D3']
    assert Path(standalone['retained_path']).read_bytes() == source.read_bytes()


@pytest.mark.parametrize('changed_during_write', [False, True])
@pytest.mark.parametrize('hardening', ['isotropic hardening', 'kinematic hardening'])
def test_applied_material_uses_official_writer_with_hex_pressure_and_gravity(native, tmp_path, monkeypatch,
                                                                          changed_during_write, hardening):
    import importlib.util
    import io
    from copy import deepcopy
    from test_b13_native_boundaries import reference_writers, Quantity
    from test_ns1_native_edit import draft
    from apps.desktop_pre import nonlinear_material as nm
    saved_modules = {name: sys.modules[name] for name in ('FreeCAD', 'femtools', 'femsolver', 'femsolver.calculix')}
    reference_writers(monkeypatch)
    from femsolver.calculix.write_femelement_material import write_femelement_material
    from femsolver.calculix import write_constraint_pressure
    spec = importlib.util.spec_from_file_location('reference_selfweight',
        Path(write_constraint_pressure.__file__).with_name('write_constraint_selfweight.py'))
    selfweight_writer = importlib.util.module_from_spec(spec); spec.loader.exec_module(selfweight_writer)
    for name, module in saved_modules.items(): monkeypatch.setitem(sys.modules, name, module)
    n = native; stored = {}
    for obj in n.doc.Objects: obj.Label = obj.Name
    n.doc.getObject = lambda name: next((obj for obj in n.doc.Objects if obj.Name == name), None)
    monkeypatch.setattr('apps.desktop_pre.metadata.read', lambda doc: deepcopy(stored))
    n.analysis.addObject = lambda obj: n.analysis.Group.append(obj)
    def make_plastic(doc, base):
        obj = NS(Name='AppliedPlastic', Label='Applied plasticity', TypeId=nm.KIND, Document=doc,
                 State=[], Suppressed=False)
        doc.Objects.append(obj); return obj
    monkeypatch.setitem(sys.modules, 'ObjectsFem', NS(makeMaterialMechanicalNonlinear=make_plastic))
    def store(value): stored.clear(); stored.update(deepcopy(value))
    fem = NS(owner=NS(doc=n.doc, _object=n.doc.getObject, write_metadata=store),
             _metadata=lambda: deepcopy(stored), _transaction=lambda title, change: change())
    n.material.Material.update(Name='User steel', Density='7.85e-9 t/mm^3')
    source = draft(); nm.apply(fem, n.material, n.analysis.Name, source)
    plastic, = nm.native_objects(n.analysis)
    # A preserved, unapplied UI draft cannot replace the current FreeCAD model.
    stored['plasticity_drafts'][0]['draft']['definitions_confirmed'] = False
    plastic.MaterialModelNonlinearity = hardening
    plastic.YieldPoints = [f'{300+i},{i*.001:.3f}' for i in range(201)]
    native_curve = list(plastic.YieldPoints)
    original_source = n.source.read_bytes(); original_metadata = deepcopy(stored)
    pressure = NS(Name='UserPressure', Label='User pressure', TypeId='Fem::ConstraintPressure', Document=n.doc,
        State=[], Suppressed=False, Pressure=Quantity('1.2 MPa'), EnableAmplitude=False, Reversed=False)
    gravity = NS(Name='UserGravity', Label='User gravity', TypeId='Fem::ConstraintSelfWeight', Document=n.doc,
        State=[], Suppressed=False, GravityAcceleration=Quantity('9810 mm/s^2'), GravityDirection=NS(x=0., y=0., z=-1.))
    n.doc.Objects.extend([pressure, gravity]); n.analysis.Group.remove(n.force)
    n.analysis.Group.extend([pressure, gravity])
    hex_points = [(0., 0., 0.), (1., 0., 0.), (1., 1., 0.), (0., 1., 0.),
                  (0., 0., 1.), (1., 0., 1.), (1., 1., 1.), (0., 1., 1.)]
    n.mesh.FemMesh.Nodes = {i: NS(x=x, y=y, z=z) for i, (x, y, z) in enumerate(hex_points, 1)}
    inverse = [None] * 8
    for index, slot in enumerate(_ORDERS['C3D8']): inverse[slot] = index + 1
    n.mesh.FemMesh.getElementNodes = lambda identifier: inverse
    member = NS(mats_linear=[{'Object': n.material}], mats_nonlinear=[{'Object': plastic}],
                cons_fixed=[{'Object': n.fixed}], cons_force=[], cons_pressure=[{'Object': pressure}],
                cons_selfweight=[{'Object': gravity}], cons_centrif=[])
    monkeypatch.setattr(sys.modules['femtools'].membertools, 'AnalysisMember', lambda analysis: member)
    monkeypatch.setattr(sys.modules['femmesh.meshsetsgetter'], 'MeshSetsGetter',
        lambda *args: NS(member=member, mat_geo_sets=[], get_mesh_sets=lambda: None))
    class Writer:
        def __init__(self, analysis, solver, mesh, members, folder, sets):
            self.root = Path(folder); self.member = members; self.solver_obj = solver
            self.analysis_type = 'static'; self.ccx_eall = 'Eall'
        def write_solver_input(self):
            stream = io.StringIO()
            stream.write('*NODE\n' + '\n'.join(f'{i},{x},{y},{z}' for i, (x, y, z) in enumerate(hex_points, 1)))
            stream.write('\n*ELEMENT,TYPE=C3D8,ELSET=Eall\n7,1,2,3,4,5,6,7,8\n')
            write_femelement_material(stream, self)
            stream.write('*SOLID SECTION,ELSET=Eall,MATERIAL=UserMaterial\n*STEP\n*STATIC\n.1,1\n')
            write_constraint_pressure.write_meshdata_constraint(stream,
                {'PressureFaces': [((n.shape, ['Face2']), [(7, 2)], True)]}, pressure, self)
            selfweight_writer.write_constraint(stream, {}, gravity, self)
            stream.write('*NODE FILE\nU\n*END STEP\n')
            path = self.root / 'native.inp'; path.write_text(stream.getvalue(), encoding='utf-8')
            if changed_during_write: plastic.YieldPoints = ['400,0', '450,.01']
            return str(path)
    monkeypatch.setattr(sys.modules['femsolver.calculix.writer'], 'FemInputWriterCcx', Writer)
    output = tmp_path / 'applied'
    if changed_during_write:
        with pytest.raises(ValueError, match='source model changed'):
            freeze_analysis(n.analysis, n.solver, output)
        assert not list(output.glob('*/snapshot.json'))
    else:
        record = freeze_analysis(n.analysis, n.solver, output)
        manifest, mesh, _, _ = frozen_fem.validate_snapshot(record)
        text = (record.parent / manifest['input_file']).read_text()
        keyword = '*PLASTIC' if hardening == 'isotropic hardening' else '*PLASTIC, HARDENING=KINEMATIC'
        assert keyword+'\n'+'\n'.join(native_curve)+'\n' in text
        assert float(text.split('*DENSITY\n')[1].splitlines()[0]) == 7.85e-9
        assert '7,P2,1.2\n' in text and 'Eall,GRAV,9810,0,0,-1\n' in text
        assert mesh['elements'][0]['type'] == 'C3D8'
        assert {'*PLASTIC', '*DENSITY', '*DLOAD'} <= set(manifest['native_cards'])
        assert plastic.YieldPoints == native_curve
    assert stored == original_metadata
    assert stored['plasticity_drafts'][0]['applied_draft'] == source
    assert n.source.read_bytes() == original_source
