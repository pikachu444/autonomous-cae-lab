"""Native single-solid linear mechanics, separate from fixture idealizations."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

from ..execution_control import run_owned_command
from ..storage import canonical_hash, load_json, save_json
from .fixture_calculix import _artifact, _screen
from .native_structural_deck import write, read_tables
from .cad_condition_catalog import native_final_solid_catalog


def source_snapshot(path, data):
    return {'path': path.name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def verify_source_snapshots(output, sources):
    for source in sources.values():
        data = (output / source['path']).read_bytes()
        if source_snapshot(output / source['path'], data) != source:
            raise ValueError('Native response source changed before completion: ' + source['path'])


class NativeStructuralAdapter:
    backend = 'structure.calculix.native'
    version = '1'
    analysis_type = 'linear_static'
    default_metrics = ['max_displacement', 'applied_force', 'reaction_force']

    @staticmethod
    def condition_input_descriptors(catalog, declaration):
        from plugins.elasticity.native_condition_inputs import describe
        return describe(catalog, declaration)

    @staticmethod
    def bind_condition_inputs(catalog, declaration, assignments):
        from plugins.elasticity.native_condition_inputs import apply
        return apply(catalog, declaration, assignments)

    @staticmethod
    def condition_input_policy_identity():
        root = Path(__file__).resolve().parents[2]
        names = ['plugins/elasticity/native_condition_inputs.py', 'plugins/elasticity/native_conditions.py',
                 'plugins/elasticity/conditions.py', 'schemas/analysis-conditions-request.schema.json']
        return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in names}

    @staticmethod
    def conditions_preflight(catalog, declaration):
        from plugins.elasticity.native_conditions import support
        return support(catalog, declaration)

    @staticmethod
    def settings_from_conditions(catalog, declaration):
        from plugins.elasticity.native_conditions import project
        return project(catalog, declaration)

    @staticmethod
    def conditions_policy_identity():
        root = Path(__file__).resolve().parents[2]
        names = ['caelab/adapters/native_structural.py', 'caelab/adapters/native_structural_deck.py',
                 'caelab/adapters/native_structural_mesh_worker.py', 'plugins/elasticity/native_conditions.py',
                 'caelab/adapters/native_face_catalog.py', 'caelab/adapters/cad_condition_catalog.py']
        return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}

    @staticmethod
    def research_metric_semantics(result):
        if result['provenance'].get('adapter') != NativeStructuralAdapter.backend:
            return None
        return {'max_displacement': {'quantity': 'displacement', 'component': 'VECTOR_MAGNITUDE',
                'selection_id': 'B-final', 'reduction': 'MAX_MAGNITUDE', 'unit': 'mm',
                'coordinate_frame': 'CAD_DOCUMENT_GLOBAL', 'coverage': 'ALL_MESH_NODES',
                'description': '전체 솔리드 실제 메시 절점의 변위 벡터 크기 최대값'}}

    def solve(self, parent, parent_root, output, settings):
        if parent['provenance']['adapter'] != 'fixture.freecad':
            raise ValueError('Native mechanics requires the verified editable FreeCAD parent')
        catalog = native_final_solid_catalog(parent_root, parent, backend='fixture.freecad')
        if (not isinstance(settings, dict) or set(settings) != {'analysis_type', 'declaration', 'native_catalog', 'mesh'}
                or settings['native_catalog'] != catalog
                or settings != self.settings_from_conditions(catalog, settings['declaration'])):
            raise ValueError('Analysis settings differ from the verified native-face conditions projection')
        step, step_sha, _ = _artifact(parent, parent_root, 'cad/native.step')
        if not shutil.which('ccx'):
            raise RuntimeError('The configured CalculiX executable is required')
        output.mkdir(parents=True, exist_ok=False)
        worker = Path(__file__).with_name('native_structural_mesh_worker.py')
        request = {'step': str(step), 'step_sha256': step_sha, 'output': str(output.resolve()),
                   'catalog': deepcopy(catalog), 'declaration': deepcopy(settings['declaration'])}
        save_json(output / 'mesh_request.json', request)
        mesher = run_owned_command([sys.executable, str(worker), str(output / 'mesh_request.json'),
                                   str(output / 'mesh.json')], output, 'gmsh_native')
        if mesher.returncode:
            raise ValueError('Native Gmsh failed; owned logs and receipt are retained: ' + mesher.stderr[-1200:])
        mesh_data = (output / 'mesh.json').read_bytes()
        mesh = json.loads(mesh_data)
        sources = {'mesh': source_snapshot(output / 'mesh.json', mesh_data)}
        if mesh['step_sha256'] != step_sha:
            raise ValueError('Native mesher returned a different STEP source')
        nodes = {int(n): tuple(xyz) for n, xyz in mesh['nodes'].items()}
        elements = {int(e): tuple(row) for e, row in mesh['elements'].items()}
        deck = output / 'native.inp'
        boundary = write(deck, mesh, settings['declaration'])
        nodes = {int(n): tuple(xyz) for n,xyz in boundary['serialized_node_coordinates_mm'].items()}
        min_jacobian = _screen().quadratic_tet_jacobian_quality(nodes, elements)
        save_json(output / 'boundary.json', boundary)
        sources['deck'] = source_snapshot(deck, deck.read_bytes())
        sources['boundary'] = source_snapshot(output / 'boundary.json', (output / 'boundary.json').read_bytes())
        deck_sha = sources['deck']['sha256']
        solver = run_owned_command([shutil.which('ccx'), '-i', 'native'], output, 'ccx_native')
        if solver.returncode:
            raise ValueError('Native CalculiX failed; owned logs and receipt are retained: ' + solver.stdout[-1200:])
        if hashlib.sha256(deck.read_bytes()).hexdigest() != deck_sha:
            raise ValueError('Native input deck changed during execution')
        dat_data = (output / 'native.dat').read_bytes()
        sources['dat'] = source_snapshot(output / 'native.dat', dat_data)
        sources['frd'] = source_snapshot(output / 'native.frd', (output / 'native.frd').read_bytes())
        tables = read_tables(output / 'native.dat', nodes, data=dat_data)
        displacements = tables['U']
        reactions = [math.fsum(tables['RF'][row['node_id']][axis-1] for row in boundary['fixed_dofs']
                               if row['component'] == axis) for axis in (1, 2, 3)]
        applied = boundary['total_applied_force_N']
        residual = max(abs(a+r) for a, r in zip(applied, reactions)) / max(math.sqrt(sum(a*a for a in applied)), 1.)
        peak = max(displacements, key=lambda n: math.sqrt(sum(v*v for v in displacements[n])))
        maximum = math.sqrt(sum(v*v for v in displacements[peak]))
        field = {'schema_version': '1.0', 'kind': 'native_structural_nodal_displacement',
                 'backend': self.backend, 'adapter_version': self.version,
                 'parent_experiment_id': parent['experiment_id'], 'cad_revision': parent['cad_revision'],
                 'coordinate_frame': 'CAD_DOCUMENT_GLOBAL', 'position_unit': 'mm', 'displacement_unit': 'mm',
                 'force_unit': 'N', 'coverage': 'ALL_MESH_NODES', 'qualification': 'UNKNOWN',
                 'engineering_valid': False, 'static': {'step': 1, 'increment': 1, 'load_parameter': 1.},
                 'nodes': [{'node_id': n, 'position_mm': list(nodes[n]), 'displacement_mm': displacements[n]}
                           for n in sorted(nodes)],
                 'elements': [{'element_id': e, 'type': 'C3D10', 'node_ids': list(row)} for e, row in sorted(elements.items())],
                 'boundary_faces': sorted(mesh['boundary_triangles'], key=lambda face: face['element_id']),
                 'prescribed_dofs': boundary['fixed_dofs'],
                 'loads': boundary['loads'], 'load_regions': boundary['load_regions'],
                 'node_count': len(nodes), 'element_count': len(elements),
                 'boundary_face_count': len(mesh['boundary_triangles']), 'parent_step_sha256': step_sha,
                 'deck_sha256': deck_sha, 'peak_node_id': peak}
        field['native_catalog_revision'] = catalog['native_catalog_revision']
        field['mesh_size_max_mm'] = settings['declaration']['mesh']['max_size_mm']
        for node in field['nodes']:
            node['displacement_tokens'] = tables['tokens']['U'][node['node_id']]
        field['sources'] = sources
        verify_source_snapshots(output, sources)
        save_json(output / 'field.json', field)
        checks = [{'code': 'native_complete_displacement', 'status': 'PASS', 'observed': len(displacements), 'expected': len(nodes)},
                  {'code': 'native_positive_tetrahedral_jacobian', 'status': 'PASS', 'observed': min_jacobian},
                  {'code': 'native_signed_reaction_equilibrium', 'status': 'PASS' if residual <= 1e-5 else 'FAIL',
                   'observed': residual, 'limit': 1e-5}]
        failed = any(c['status'] == 'FAIL' for c in checks)
        outcome = {'status': 'REJECTED' if failed else 'COMPLETED', 'solver_status': 'COMPLETED', 'converged': True,
                   'checks': checks, 'metrics': {'max_displacement': {'value': maximum, 'unit': 'mm', 'valid': not failed},
                   'applied_force': {'value': applied, 'unit': 'N', 'valid': True},
                   'reaction_force': {'value': reactions, 'unit': 'N', 'valid': not failed}},
                   'pending_validations': ['material_qualification', 'static_strength', 'physical_load_test',
                                           'fatigue_durability', 'model_idealization'],
                   'provenance': {'parent_step_sha256': step_sha, 'deck_sha256': deck_sha, 'boundary': boundary,
                                  'field_artifact': 'simulation/field.json', 'gmsh_version': mesh['gmsh_version'],
                                  'scope': 'Native single-solid linear mechanics; one declared mesh, no contact'},
                   'raw_result': 'simulation/result.json'}
        if failed:
            for metric in outcome['metrics'].values():
                if not metric['valid']:
                    metric['reason'] = 'Signed reaction equilibrium did not pass'
        save_json(output / 'result.json', outcome)
        verify_source_snapshots(output, sources)
        return outcome
