"""Declared body/material/BC/load/contact mechanics on a retained mesh.

The operator supplies original qualification, the engineer supplies conditions,
and the same frozen CAD revision owns the complete native child. No remeshing.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from . import fixture_assembly_mesh_reuse as reuse
from . import fixture_assembly_native_import as transport
from .fixture_assembly_conditions_catalog import AssemblyConditionsCADAdapter
from .assembly_conditions_projection import compile_packet, SOLVER_POLICY
from .fixture_assembly_mechanics_fields import parse_fields, numerical_summary
from ..execution_control import ExecutionCancelled, ExecutionCleanupFailed


_WORKER = 'fixture_assembly_mechanics_worker.py'
_CAPSULE = (_WORKER, 'codeaster_worker.py', 'fixture_assembly_native_import_worker.py',
            'fixture_assembly_field_geometry.py', 'assembly_mesh.py', 'fixture_assembly_affine_field_worker.py')
_PENDING = ['physical_material_qualification', 'fixture_contact_and_load_path',
            'fixture_fastening_and_mounting', 'omitted_fasteners_preload_anchor',
            'machine_requirements', 'physical_strength', 'durability', 'compiled_image_source_equivalence']


def source_files():
    base = Path(__file__).resolve().parent
    root = base.parent.parent
    return transport.source_files() | {name: base / name for name in _CAPSULE if name != 'assembly_mesh.py'} | {
        'assembly_mesh.py': root / 'plugins/fixture_design/assembly_mesh.py',
        'assembly_conditions.py': root / 'plugins/fixture_design/assembly_conditions.py',
        'conditions_schema': root / 'schemas/analysis-conditions-request.schema.json',
        'fixture_assembly_mechanics.py': Path(__file__).resolve(),
        'fixture_assembly_mechanics_fields.py': base / 'fixture_assembly_mechanics_fields.py',
        'assembly_conditions_projection.py': base / 'assembly_conditions_projection.py',
        'fixture_assembly_conditions_catalog.py': base / 'fixture_assembly_conditions_catalog.py'}


def _pins():
    return {name: transport._entry(path) for name, path in source_files().items()}


class FixtureAssemblyMechanicsAdapter:
    backend = 'fixture.assembly_mechanics.code_aster'
    version = '1'
    conditions_version = '1'
    analysis_type = 'nonlinear_static'
    default_metrics = ['max_displacement', 'reaction_balance_ratio', 'peak_stress']

    def __init__(self, bundle, retained_mesh, configuration):
        if type(bundle) is not transport.QualifiedAssemblyMeshBundle:
            raise TypeError('Trusted operator mesh bundle required')
        self.bundle, self.retained_mesh = bundle, deepcopy(retained_mesh)
        self.configuration = deepcopy(configuration)

    @staticmethod
    def field_response_resources(result):
        return {'field': {'path': 'simulation/admitted-fields.json', 'maximum_bytes': 536870912},
                'mapping': {'path': 'simulation/mesh-reuse/mapping.json', 'maximum_bytes': 134217728}}

    @staticmethod
    def display_response_fields(result, proposal, resources):
        from .assembly_response_fields import display_field
        return display_field(result, proposal, *resources['field'], *resources['mapping'])

    @staticmethod
    def select_response_fields(result, proposal, resources, selection):
        from .assembly_response_fields import select_field_response
        raw, artifact = resources['field']
        mapping, mapping_artifact = resources['mapping']
        return select_field_response(result, proposal, raw, artifact, selection,
                                     mapping=mapping, mapping_artifact=mapping_artifact)

    @staticmethod
    def conditions_policy_identity():
        return {name: value['sha256'] for name, value in _pins().items()}

    def conditions_preflight(self, catalog, declaration):
        result = {'status': 'UNSUPPORTED_FOR_CONDITIONS', 'reasons': [], 'native_runtime': 'NOT_CHECKED'}
        if catalog.get('cad_backend') != 'fixture.assembly':
            return result | {'status': 'UNSUPPORTED_FOR_MODEL', 'reasons': ['원본 조립체의 보존 CAD 개정이 필요합니다.']}
        try:
            if catalog.get('retained_mesh') != self.retained_mesh:
                raise ValueError('Declared mesh catalog differs from trusted operator configuration')
            from plugins.fixture_design.assembly_conditions import validate_declaration, require_initial_translation_support
            validate_declaration(catalog, declaration)
            require_initial_translation_support(catalog, declaration)
        except (ValueError, TypeError, KeyError) as error:
            result['reasons'] = [str(error)]
            return result
        return result | {'status': 'SUPPORTED_DECLARED_INPUTS', 'reasons': [
            '선언 조건은 보존 7부품 메시 경로에 속합니다. 실행 시 원본·native group·접촉/구속 충돌을 재검사합니다.',
            '합력은 선택한 native 표면 절점에 균등 분포합니다. 실제 물성·체결·접촉·강도 자격 UNKNOWN.']}

    def settings_from_conditions(self, catalog, declaration):
        verdict = self.conditions_preflight(catalog, declaration)
        if verdict['status'] != 'SUPPORTED_DECLARED_INPUTS':
            raise ValueError('; '.join(verdict['reasons']))
        return {'analysis_type': self.analysis_type, 'catalog': deepcopy(catalog),
                'declaration': deepcopy(declaration), 'mesh': deepcopy(declaration['mesh']),
                'solver_policy': deepcopy(SOLVER_POLICY)}

    def solve(self, parent_result, parent_root, output, settings):
        root = reuse._absolute(output)
        if root.exists() and (not root.is_dir() or any(root.iterdir())):
            raise ValueError('Fresh empty assembly mechanics output required')
        catalog, declaration = settings['catalog'], settings['declaration']
        actual = AssemblyConditionsCADAdapter(self.retained_mesh).conditions_catalog(parent_root, parent_result, {})
        if actual != catalog or self.settings_from_conditions(actual, declaration) != settings:
            raise ValueError('Assembly CAD catalog/declaration/solver policy changed before execution')
        sources, budgets = _pins(), transport._budgets()
        root.mkdir(parents=True, exist_ok=True)
        captured = checked = attempted = returned = False
        provenance = {'adapter': self.backend, 'adapter_version': self.version, 'source_files': sources,
            'execution_settings': deepcopy(settings), 'operator_configuration': self.configuration,
            'scope': 'DECLARED_RETAINED_ASSEMBLY_MECHANICS', 'decision': 'NOT_RELEASED', 'budgets': budgets}
        known = {}
        try:
            descriptor = self.bundle.capture(parent_result, parent_root, root / 'mesh-reuse')
            captured = True
            capture = root / 'mesh-reuse'
            receipt = reuse._json(transport._bytes(capture, descriptor['receipt']['path'],
                                    {k: descriptor['receipt'][k] for k in ('sha256', 'size_bytes')}))
            if receipt['mesh_revision'] != self.retained_mesh['mesh_revision'] or receipt['parent']['cad_revision'] != parent_result['cad_revision']:
                raise ValueError('Captured retained mesh/CAD revision differs')
            original_pin, mapping_pin, quality_pin = (receipt['output_files'][name]
                for name in ('mesh.msh', 'mapping.json', 'quality.json'))
            mapping = reuse._json(transport._bytes(capture, 'mapping.json', mapping_pin))
            quality = reuse._json(transport._bytes(capture, 'quality.json', quality_pin))
            packet, translation = compile_packet(catalog, declaration, mapping, solver_policy=settings['solver_policy'])
            original = transport._bytes(capture, 'mesh.msh', original_pin)
            mesh_bytes, transform = transport.transport_msh(original, mapping)
            image, image_pin, executable, executable_pin = transport._image_identity()
            for folder in ('native', 'capsule', 'preferences', 'scratch'):
                (root / folder).mkdir(exist_ok=False)
            native = root / 'native'
            (native / 'mesh-transport.msh').write_bytes(mesh_bytes)
            files, native_sources = source_files(), {}
            for name in _CAPSULE:
                data = transport._bytes(files[name].parent, files[name].name, sources[name])
                with (root / 'capsule' / name).open('xb') as stream:
                    stream.write(data)
                native_sources[name] = transport._entry(root / 'capsule' / name)
            config = {'schema_version': 1, 'settings': packet, 'mesh_revision': receipt['mesh_revision'],
                'parent': receipt['parent'], 'profile': receipt['profile'], 'mapping_entry': mapping_pin,
                'quality_entry': quality_pin, 'transport_entry': transform['transport_entry'],
                'original_mesh_entry': original_pin, 'native_sources': native_sources}
            input_pin = transport._save(native, 'input.json', config)
            transport._save(root, 'transport.json', transform)
            transport._save(root, 'condition-translation.json', translation)
            provenance.update(reuse=descriptor, mesh_revision=receipt['mesh_revision'], cad_parent=receipt['parent'],
                native_sources=native_sources, input_entry=input_pin, original_mesh_entry=original_pin,
                image={'path': str(image), **image_pin}, container_runtime={'path': str(executable), **executable_pin},
                compiled_image_source_equivalence='UNKNOWN', translation=translation)
            transport._save(root, 'intent.json', provenance | {'solver_status': 'NOT_RUN', 'converged': None})
            comm = ('from pathlib import Path\nimport hashlib\n'
                f"p=Path('/work/capsule/{_WORKER}')\nb=p.read_bytes()\n"
                f"assert hashlib.sha256(b).hexdigest()=={native_sources[_WORKER]['sha256']!r} and len(b)=={native_sources[_WORKER]['size_bytes']}\n"
                "ns={'__file__':str(p),'__name__':'_mechanics_bootstrap','__package__':''}\n"
                "exec(compile(b,str(p),'exec',dont_inherit=True),ns)\nns['bootstrap']('/work/native/input.json')\n")
            (native / 'mechanics.comm').write_text(comm, encoding='utf-8', newline='\n')
            export = (f"P actions make_etude\nP memory_limit {budgets['solver_memory_mb']}\n"
                f"P time_limit {budgets['solver_time_seconds']}\nP mpi_nbcpu 1\nP ncpus 1\n"
                'F comm /work/native/mechanics.comm D 1\nF mmed /work/native/mesh-transport.msh D 20\n'
                'F mess /work/native/aster.mess R 6\nF resu /work/native/aster.resu R 8\nF rmed /work/native/fields.med R 80\n')
            (native / 'mechanics.export').write_text(export, encoding='utf-8', newline='\n')
            names = ('native/input.json', 'native/mesh-transport.msh', 'native/mechanics.comm',
                'native/mechanics.export', 'transport.json', 'intent.json', 'condition-translation.json',
                *('capsule/' + name for name in _CAPSULE))
            known = {name: transport._entry(root / name) for name in names}

            def recheck():
                if _pins() != sources or transport._entry(image) != image_pin or transport._entry(executable) != executable_pin:
                    raise ValueError('Assembly mechanics source/image/runtime drift')
                for name, pin in known.items():
                    transport._bytes(root, name, pin)

            recheck()
            container_version = transport._owned_process([str(executable), '--version'], native,
                'container-version', timeout=budgets['subprocess_timeout_seconds'])
            transport._save(root, 'container-version.json', {'observed': container_version})
            self.bundle.recheck(capture)
            recheck()
            command = [str(executable), 'exec', '--cleanenv', '--containall', '--no-home', '--env', 'OMP_NUM_THREADS=1',
                '--bind', str(root) + ':/work:rw', '--bind', str(root / 'preferences') + ':' + str(Path.home()) + ':rw',
                '--bind', str(root / 'scratch') + ':/tmp:rw', '--pwd', '/work', str(image),
                '/bin/bash', '--noprofile', '--norc', '-c', 'source /opt/activate.sh; exec run_aster "$1"',
                'caelab-assembly-mechanics', '/work/native/mechanics.export']
            attempted = True
            transport._owned_process(command, native, 'native-mechanics', timeout=budgets['subprocess_timeout_seconds'])
            returned = True
            recheck()
            raw_pin = transport._entry(native / 'worker-result.json')
            raw = reuse._json(transport._bytes(native, 'worker-result.json', raw_pin))
            if (raw.get('schema_version') != 1 or raw.get('status') != 'ASSEMBLY_MECHANICS_NATIVE_OBSERVED'
                    or raw.get('input_entry') != input_pin or raw.get('native_sources') != native_sources
                    or any(raw.get(key) != config[key] for key in ('mesh_revision', 'parent', 'profile', 'transport_entry'))
                    or raw.get('decision') != 'NOT_RELEASED'):
                raise ValueError('Actual worker input/native source/CAD/mesh identity differs')
            before, after = (reuse._json((native / name).read_bytes()) for name in ('runtime-before.json', 'runtime-after.json'))
            if (before != raw['runtime_before'] or after != raw['runtime_after'] or before != after
                    or before.get('versions', {}).get('code_aster') != '17.4.0'):
                raise ValueError('Actual Code_Aster runtime drift')
            original_catalog = reuse._json(transport._bytes(native, 'native-catalog.json', raw['pre_catalog_entry']))
            oriented = reuse._json(transport._bytes(native, 'oriented-catalog.json', raw['oriented_catalog_entry']))
            from .fixture_assembly_mechanics_worker import validate_orientation, validate_conditions, validate_nodal_history
            application = validate_conditions(packet, mapping, original_catalog, packet['components'])
            if application != raw['nodal_application_receipt']:
                raise ValueError('Native condition/force/tie projection differs from exact original groups')
            if reuse._json(transport._bytes(native, 'nodal-application-receipt.json', raw['nodal_application_receipt_entry'])) != application:
                raise ValueError('Saved native application differs from embedded receipt')
            orientation = validate_orientation(original_catalog, oriented, application['node_groups'], application['cell_groups'])
            if orientation != raw['orientation_receipt']:
                raise ValueError('Actual original/oriented mesh transformation receipt differs')
            if reuse._json(transport._bytes(native, 'orientation-receipt.json', raw['orientation_receipt_entry'])) != orientation:
                raise ValueError('Saved native orientation differs from embedded receipt')
            for name in ('DEPL', 'REAC_NODA', 'SIEF_ELGA', 'COOR_ELGA'):
                if reuse._json(transport._bytes(native, name.lower() + '.table.json', raw['table_entries'][name])) != raw['tables'][name]:
                    raise ValueError('Embedded full field differs from original table')
            if set(raw['history_tables']) != {'DEPL', 'REAC_NODA'} or set(raw['history_table_entries']) != {'DEPL', 'REAC_NODA'}:
                raise ValueError('Complete native displacement/reaction histories required')
            for name in ('DEPL', 'REAC_NODA'):
                table = reuse._json(transport._bytes(native, name.lower() + '-all-orders.table.json', raw['history_table_entries'][name]))
                if table != raw['history_tables'][name]:
                    raise ValueError('Embedded native history differs from original table')
                validate_nodal_history(table, original_catalog, raw['available_orders'], name + ' history')
            expected_contacts = {}
            if set(raw['native_contact']) != {item['id'] for item in application['contacts']}:
                raise ValueError('Native contact channel scope differs from declared projection')
            for number, item in enumerate(application['contacts'], 1):
                observations = raw['native_contact'][item['id']]
                if set(observations) != {'DEPL.LAGS_C', 'CONT_NOEU'}:
                    raise ValueError('Native contact channel identity differs')
                for channel, suffix in (('DEPL.LAGS_C', 'lags_c'), ('CONT_NOEU', 'cont_noeu')):
                    filename = f'contact-{number:03d}-{suffix}.table.json'
                    observed = reuse._json(transport._bytes(native, filename, raw['contact_table_entries'][filename]))
                    if observed != observations[channel] or observed['status'] not in {'OBSERVED', 'UNKNOWN'}:
                        raise ValueError('Saved native contact observation differs')
                    expected_contacts[filename] = raw['contact_table_entries'][filename]
            if set(expected_contacts) != set(raw['contact_table_entries']):
                raise ValueError('Foreign native contact table entry')
            if set(raw['native_energy']) != set(packet['components']) or set(raw['energy_table_entries']) != set(packet['components']):
                raise ValueError('Native body-energy scope differs')
            for component in packet['components']:
                energy = reuse._json(transport._bytes(native, 'energy-' + component + '.table.json', raw['energy_table_entries'][component]))
                if energy != raw['native_energy'][component] or energy['status'] not in {'OBSERVED', 'UNKNOWN'}:
                    raise ValueError('Saved native energy observation differs')
            fields = parse_fields(raw, mapping, original_catalog, quality, packet)
            comparison = numerical_summary(fields, packet)
            transport._save(root, 'admitted-fields.json', fields)
            transport._save(root, 'comparison.json', comparison)
            self.bundle.recheck(capture)
            checked = True
            recheck()
            provenance.update(native_runtime=before, worker_result_entry=raw_pin,
                native_catalog_entry=raw['pre_catalog_entry'], oriented_catalog_entry=raw['oriented_catalog_entry'],
                orientation_receipt=orientation, geometry_checks=fields['geometry_checks'],
                native_application=raw['nodal_application_receipt'], actual_load_parameters=raw['access_parameters']['INST'],
                axis_semantics=fields['axis_semantics'],
                retained_native_files={p.relative_to(root).as_posix(): transport._entry(p) for p in sorted(native.iterdir()) if p.is_file()})
            outcome = {'status': 'COMPLETED' if all(c['status'] == 'PASS' for c in comparison['checks']) else 'REJECTED',
                'solver_status': 'COMPLETED', 'converged': True,
                'checks': [{'code': 'assembly_original_native_identity', 'status': 'PASS'},
                           {'code': 'assembly_complete_native_field_identity', 'status': 'PASS'}] + comparison['checks'],
                'metrics': comparison['metrics'], 'pending_validations': list(_PENDING),
                'provenance': provenance, 'raw_result': 'simulation/comparison.json'}
            transport._save(root, 'adapter-outcome.json', outcome)
            return outcome
        except (ExecutionCancelled, ExecutionCleanupFailed):
            raise
        except Exception as error:
            failure = {'error': type(error).__name__ + ': ' + str(error), 'native_execution_attempted': attempted,
                'native_process_returned': returned, 'numerical_verdict': 'UNKNOWN', 'decision': 'NOT_RELEASED',
                'provenance': provenance}
            transport._save(root, 'failure.json', failure)
            return {'status': 'REJECTED', 'solver_status': 'UNKNOWN' if returned else 'FAILED_EXECUTION' if attempted else 'NOT_RUN',
                'converged': None, 'checks': [{'code': 'assembly_mechanics_admission', 'status': 'FAIL', 'observed': failure['error']}],
                'metrics': {}, 'pending_validations': list(_PENDING), 'provenance': provenance,
                'raw_result': 'simulation/failure.json'}
        finally:
            if captured and not checked:
                self.bundle.recheck(root / 'mesh-reuse')
