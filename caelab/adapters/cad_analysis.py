"""Declared saved FreeCAD Analysis candidates through existing native owners.

No model code/command/path is supplied by a Plan. Workbench resolves the exact
registered project and configured installed native executable at execution.
"""
from copy import deepcopy
import math
import os
from pathlib import Path
import shutil
import uuid

from ..storage import canonical_hash, load_json, save_json
from ..evaluation import file_hash
from ..execution_control import check_cancelled, run_owned_command, ExecutionCancelled, ExecutionCleanupFailed

BACKEND = 'structure.calculix.design'
ROOT = Path(__file__).resolve().parents[2]
FIELDS = ('COPEN', 'CSLIP1', 'CSLIP2', 'CPRESS', 'CSHEAR1', 'CSHEAR2', 'GeomGap_mm')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_recipe(recipe):
    if not isinstance(recipe, dict) or recipe.get('version') != 1 or recipe.get('route') not in {'contact', 'single_solid'}:
        raise ValueError('Choose a saved native Analysis research recipe')
    for key in ('analysis_id', 'solver_id'):
        if not isinstance(recipe.get(key), str) or not recipe[key]:
            raise ValueError('Select the native Analysis and solver')
    variables = recipe.get('variables')
    if not isinstance(variables, list) or not 1 <= len(variables) <= 32:
        raise ValueError('Register 1..32 native variables')
    ids, targets = set(), set()
    from ..registry import ID
    for row in variables:
        if (not ID.fullmatch(row['id']) or row['id'] in ids or
                not all(finite(row[k]) for k in ('lower', 'upper', 'value')) or
                not row['lower'] <= row['value'] <= row['upper'] or row['lower'] >= row['upper'] or
                not row.get('unit') or row.get('analysis_id') != recipe['analysis_id']):
            raise ValueError('Native model variable declaration is invalid')
        target = canonical_hash({'analysis_id': row['analysis_id'], 'target': row['target']})
        if target in targets:
            raise ValueError('A native target may have only one research variable')
        targets.add(target)
        ids.add(row['id'])
    responses = recipe.get('responses')
    if not isinstance(responses, list) or not 1 <= len(responses) <= 32:
        raise ValueError('Choose 1..32 explicit response definitions')
    ids = set()
    for row in responses:
        if not ID.fullmatch(row['id']) or row['id'] in ids:
            raise ValueError('Response names must be distinct identifiers')
        ids.add(row['id'])
        if row.get('kind') == 'pair':
            if (row.get('pair_id') not in {p['id'] for p in recipe['pairs']} or
                    row.get('quantity') not in ('CF', 'CFN', 'CFS') or row.get('component') not in ('X', 'Y', 'Z') or
                    row.get('unit') != 'N' or row.get('reduction') not in ('value', 'series')):
                raise ValueError('Pair force needs an exact pair, CF/CFN/CFS, X/Y/Z and N')
        elif row.get('kind') == 'contact_field':
            field = row.get('field')
            unit = 'mm' if field in ('COPEN', 'CSLIP1', 'CSLIP2', 'GeomGap_mm') else 'MPa'
            if (field not in FIELDS or row.get('pair_id') not in {p['id'] for p in recipe['pairs']} or
                    row.get('side') not in ('a', 'b', 'both') or row.get('unit') != unit or
                    row.get('reduction') not in ('min', 'max', 'mean', 'field')):
                raise ValueError('Contact field needs an explicit side, field, unit and reduction')
        elif row.get('kind') == 'displacement':
            if row.get('component') not in ('X', 'Y', 'Z') or row.get('unit') != 'mm' or row.get('reduction') not in ('min', 'max', 'mean', 'field'):
                raise ValueError('Displacement needs an explicit global component, mm and reduction')
        else:
            raise ValueError('Unsupported response definition')
        if row.get('increment') != 'final' and not (type(row.get('increment')) is int and row['increment'] >= 0):
            raise ValueError('Choose final or an exact zero-based retained increment')
    if recipe['route'] != 'contact' and any(row['kind'] != 'displacement' for row in responses):
        raise ValueError('Contact outputs require an actual contact Analysis')
    if not recipe.get('meshes') or recipe.get('correspondence', {}).get('policy') != 'freecad-mapped-element-v1':
        raise ValueError('Choose native mesh settings and the mapped-element correspondence policy')
    canonical_hash(recipe)
    return recipe


def validate_settings(settings):
    if not isinstance(settings, dict) or set(settings) - {'_native_context'} != {'data_id', 'source_sha256', 'recipe', 'values'}:
        raise ValueError('Native study requires the registered design, recipe and typed values')
    from ..storage import check_id
    check_id(settings['data_id'])
    if not isinstance(settings['source_sha256'], str) or len(settings['source_sha256']) != 64:
        raise ValueError('Saved native input hash is required')
    recipe = validate_recipe(settings['recipe'])
    values = settings['values']
    if not isinstance(values, dict) or set(values) != {r['id'] for r in recipe['variables']}:
        raise ValueError('Every registered variable needs its own current value')
    for row in recipe['variables']:
        value = values[row['id']]
        if not finite(value) or not row['lower'] <= value <= row['upper']:
            raise ValueError(row['label'] + ': value is outside the declared model limits')
    return settings


def _reduce(values, operation):
    if not values or any(not finite(value) for value in values):
        raise ValueError('Selected response has missing/nonfinite rows; inspect the retained raw result')
    if operation == 'field':
        return values
    return {'min': min, 'max': max, 'mean': lambda a: sum(a) / len(a)}[operation](values)


def select_responses(result, folder, recipe):
    """Read only the actual pinned output; never turn missing values into zero."""
    selected, details = {}, {}
    contact = recipe['route'] == 'contact'
    bundle = None
    if contact:
        from ..contact_inspection import load
        post = result['post_artifact']
        bundle = load(Path(folder) / post['relative'], post['native_metadata']['contact_inspection'])
    for definition in recipe['responses']:
        name, kind = definition['id'], definition['kind']
        increment = definition['increment']
        index = (len(bundle['frames']) - 1 if increment == 'final' else increment) if bundle else 0
        if bundle and not 0 <= index < len(bundle['frames']):
            raise ValueError(name + ': requested increment was not retained')
        metadata = {'definition': deepcopy(definition), 'active_state': 'UNKNOWN'}
        if kind == 'pair':
            from ..contact_inspection import force_history
            history = force_history(bundle, definition['pair_id'], definition['quantity'], 'XYZ'.index(definition['component']))
            rows = history['rows']
            metadata.update(scope='pair_specific_DAT_resultant', raw_rows=rows, frame=history['frame'], force_on='slave_A')
            if definition['reduction'] == 'series':
                valid = [r for r in rows if r['valid']]
                if not valid:
                    raise ValueError(name + ': no valid retained pair force samples')
                response = {'kind': 'series', 'value': [r['value'] for r in valid],
                            'axes': [{'name': 'load_parameter', 'unit': '1',
                                      'values': [r['static']['load_parameter'] for r in valid]}]}
            else:
                if not rows[index]['valid']:
                    raise ValueError(name + ': ' + str(rows[index]['reason']))
                response = {'kind': 'scalar', 'value': rows[index]['value']}
                metadata['static'] = rows[index]['static']
        elif kind == 'contact_field':
            from ..contact_inspection import inspect
            view = inspect(bundle, definition['pair_id'], definition['side'], index, definition['field'])
            if any(not row['valid'] for row in view['rows']):
                raise ValueError(name + ': selected surface contains unavailable raw samples')
            values = [row['value'] for row in view['rows']]
            response = {'kind': 'field' if definition['reduction'] == 'field' else 'scalar',
                        'value': _reduce(values, definition['reduction'])}
            metadata.update(scope=view['scope'], static=view['static'], node_ids=[r['node_id'] for r in view['rows']])
        else:
            if increment != 'final':
                raise ValueError(name + ': displacement response currently selects the retained final field')
            field = result.get('responses', {}).get('displacement')
            if not field:
                # The preserved single-solid adapter advertises its own native channels.
                raise ValueError(name + ': no compatible displacement field in this retained result')
            values = [row['XYZ'.index(definition['component'])] for row in field['value']]
            response = {'kind': 'field' if definition['reduction'] == 'field' else 'scalar',
                        'value': _reduce(values, definition['reduction'])}
            metadata.update(field.get('metadata', {}), scope='global_nodal_displacement')
        response.update(unit=definition['unit'], component=definition.get('component', definition.get('field')),
                        location=definition.get('pair_id', 'native_model'),
                        reduction='none' if definition['reduction'] == 'value' else definition['reduction'],
                        metadata=metadata)
        selected[name], details[name] = response, metadata
    return selected


class CADAnalysisAdapter:
    backend, version = BACKEND, '1'
    input_source_files = [__file__, ROOT / 'apps/desktop_pre/research_inputs.py',
                          ROOT / 'apps/desktop_pre/candidate_correspondence.py',
                          ROOT / 'apps/desktop_pre/candidate_worker.py']

    @staticmethod
    def input_runtime_identity():
        return {'host': 'configured FreeCAD GUI', 'mesh': 'native GmshTools',
                'solver': 'existing CalculiX adapter', 'status': 'NOT_PROBED'}

    @staticmethod
    def default_settings():
        return {'data_id': '', 'source_sha256': '', 'recipe': {}, 'values': {}}

    validate_settings = staticmethod(validate_settings)

    def describe_inputs(self, settings):
        validate_settings(settings)
        return [{'id': row['id'], 'label': row['label'], 'unit': row['unit'],
                 'value': settings['values'][row['id']], 'lower': row['lower'], 'upper': row['upper'],
                 'settings_path': ['values', row['id']], 'declaration_paths': [['model', 'values', row['id']]]}
                for row in settings['recipe']['variables']]

    def describe_model(self, settings):
        validate_settings(settings)
        return {'model': {key: deepcopy(value) for key, value in settings.items() if key != '_native_context'}}

    def bind_inputs(self, settings, assignments):
        from ..model_parameters import expected_settings
        return expected_settings(settings, self.describe_inputs(settings), assignments)

    def describe_ports(self, settings):
        validate_settings(settings)
        return {'inputs': self.describe_inputs(settings), 'responses': deepcopy(settings['recipe']['responses'])}

    def run(self, settings, *, output, runtime=None):
        validate_settings(settings)
        if runtime:
            raise ValueError('Use the configured native runtime')
        folder = Path(output).resolve()
        folder.mkdir(parents=True, exist_ok=True)
        if any(folder.iterdir()):
            raise ValueError('A native candidate needs a fresh owned folder')
        result = {'execution_status': 'FAILED', 'responses': {}, 'checks': [],
                  'qualification': 'UNKNOWN', 'decision': 'NOT_RELEASED', 'diagnostics': {}}
        phase = 'copy'
        try:
            context = settings.get('_native_context')
            if not context:
                raise ValueError('Run through the shared service to resolve this registered design')
            source = Path(context['source']).resolve(strict=True)
            if file_hash(source) != settings['source_sha256']:
                raise ValueError('Registered saved design changed before the candidate')
            from ..native_cad import inspect_project
            manifest = inspect_project(source)
            if canonical_hash(manifest['metadata'].get('candidate_recipe')) != canonical_hash(settings['recipe']):
                raise ValueError('Execution recipe differs from the actual saved native project')
            check_cancelled()
            copied = folder / 'base.caepre'
            shutil.copyfile(source, copied)
            if file_hash(copied) != settings['source_sha256']:
                raise ValueError('Candidate copy differs from the saved design')
            executable = Path(context['freecad_executable']).resolve(strict=True)
            config = {'source': str(copied), 'output': str(folder), 'settings': deepcopy(settings),
                      'gmsh': context.get('gmsh')}
            config_path = folder / 'candidate.json'
            save_json(config_path, config)
            macro = folder / 'candidate.FCMacro'
            macro.write_text('import sys\nsys.path.insert(0, ' + repr(str(ROOT)) +
                ')\nfrom apps.desktop_pre.candidate_worker import start\nstart(' + repr(str(config_path)) + ')\n',
                encoding='utf-8')
            phase = 'native_prepare'
            environment = os.environ.copy()
            for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'LD_LIBRARY_PATH'):
                environment.pop(key, None)
            prepared = run_owned_command([str(executable), '-u', str(folder / 'user.cfg'),
                '-s', str(folder / 'system.cfg'), str(macro)], folder, 'freecad_candidate', env=environment, owned_tree=True)
            receipt = load_json(folder / 'candidate-preparation.json')
            result['candidate_preparation'] = receipt
            if prepared.returncode or receipt.get('state') != 'PREPARED':
                raise ValueError(receipt.get('error') or 'Native candidate preparation failed')
            snapshot = Path(receipt['snapshot'])
            if not snapshot.resolve().is_relative_to(folder):
                raise ValueError('Candidate snapshot escaped its owned attempt')
            phase = 'solver'
            check_cancelled()
            if settings['recipe']['route'] == 'contact':
                from .contact_fem import ContactFemCalculixAdapter
                calculation = ContactFemCalculixAdapter().run({'snapshot_path': str(snapshot)}, output=folder / 'calculation')
            else:
                from .frozen_fem import FrozenFemCalculixAdapter
                calculation = FrozenFemCalculixAdapter().run({'snapshot_path': str(snapshot)}, output=folder / 'calculation')
            result['calculation'] = calculation
            result['execution_status'] = calculation['execution_status']
            editable = Path(receipt['editable_project'])
            if not editable.resolve().is_relative_to(folder) or file_hash(editable) != receipt['editable_sha256']:
                raise ValueError('Calculated editable project differs from native preparation')
            result['editable_design'] = {'relative': editable.relative_to(folder).as_posix(),
                'sha256': receipt['editable_sha256'], 'bytes': editable.stat().st_size,
                'calculated': calculation['execution_status'] == 'SUCCEEDED',
                'base_data_id': settings['data_id'], 'base_sha256': settings['source_sha256']}
            if calculation.get('post_artifact'):
                result['post_artifact'] = deepcopy(calculation['post_artifact'])
                result['post_artifact']['relative'] = 'calculation/' + result['post_artifact']['relative']
            if calculation['execution_status'] != 'SUCCEEDED':
                result['diagnostics'] = deepcopy(calculation.get('diagnostics', {}))
                result['diagnostics']['phase'] = 'solver'
            else:
                phase = 'response'
                result['responses'] = select_responses(calculation, folder / 'calculation', settings['recipe'])
        except ExecutionCleanupFailed:
            raise
        except ExecutionCancelled as error:
            result.update(execution_status='CANCELLED', responses={},
                          diagnostics={'phase': phase, 'reason': str(error)})
        except Exception as error:
            result.update(execution_status='FAILED', responses={},
                          diagnostics={'phase': phase, 'reason': str(error), 'error_type': type(error).__name__})
        preparation = folder / 'candidate-preparation.json'
        if preparation.is_file() and 'candidate_preparation' not in result:
            result['candidate_preparation'] = load_json(preparation)
        if result['execution_status'] != 'SUCCEEDED' and result.get('candidate_preparation'):
            result['diagnostics']['native_phase'] = result['candidate_preparation'].get('phase')
        result['artifacts'] = [{'path': p.relative_to(folder).as_posix(), 'sha256': file_hash(p)}
                               for p in sorted(folder.rglob('*')) if p.is_file() and not p.is_symlink()]
        return result
