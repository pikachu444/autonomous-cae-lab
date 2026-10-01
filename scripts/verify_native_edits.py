"""P1.2a actual imported/edited Part and named Sketcher acceptance.

Run with the existing pinned FREECAD_CMD. Every invocation requires a fresh store.
Analytical inputs, responses and tolerances below are fixed before execution.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import traceback

import cadquery as cq

from caelab import Lab

BACKEND = 'fixture.freecad'
REPO = Path(__file__).resolve().parents[1]
LENGTH_TOLERANCE_MM = 1e-5
VOLUME_TOLERANCE_MM3 = 1e-5
REFERENCE = {
    'part_original': {'bounds_mm': [12, 10, 8], 'volume_mm3': 960},
    'part_before_edit': {'bounds_mm': [18, 10, 8], 'volume_mm3': 1440},
    'part_after_edit': {'bounds_mm': [20, 10, 8], 'volume_mm3': 1600},
    'sketch_radius6': {'bounds_mm': [12, 12, 8], 'volume_mm3': 288 * math.pi},
    'sketch_center_to_origin_x5': {'center_mm': [-5, 0, 4]},
    'sketch_center_to_origin_x5_y7': {'center_mm': [-5, -7, 4]},
    'length_absolute_tolerance_mm': LENGTH_TOLERANCE_MM,
    'volume_absolute_tolerance_mm3': VOLUME_TOLERANCE_MM3,
    'distance_definition': 'DistanceX/Y(circle center, origin, positive value): origin minus center; signed centroid is negative.',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def near(actual, expected, tolerance):
    assert math.isfinite(actual) and abs(actual - expected) <= tolerance, (actual, expected, tolerance)


def inventory(folder):
    return [{'path': str(p.relative_to(folder)), 'size_bytes': p.stat().st_size, 'sha256': sha(p)}
            for p in sorted(folder.rglob('*')) if p.is_file()]


def run(store, run_id):
    if store.exists():
        raise FileExistsError('Use a new store; preserve every previous native revision')
    store.mkdir(parents=True)
    record = {'schema': 1, 'phase': 'P1.2a', 'run_id': run_id, 'outcome': 'RUNNING',
              'started_utc': datetime.now(timezone.utc).isoformat(), 'reference': REFERENCE,
              'cases': [], 'limitations': [
                  'Representative editor revisions use actual FreeCAD objects/API; no human GUI click or OS containment claim.',
                  'Name deletion/recreation with a different semantic dimension cannot be proven identical from name-only legacy metadata.',
                  'Cross-file write failure and transactional recovery are P1.2b, not this acceptance.',
                  'No solver/strength/physical/release acceptance. Generic-domain checks stay UNKNOWN.']}
    receipt = store / 'native_edit_acceptance.json'
    write(store / 'predeclared-reference.json', REFERENCE)
    record['predeclared_reference_sha256'] = sha(store / 'predeclared-reference.json')
    command_index = 0
    study = 'S-' + run_id
    lab = Lab(store)
    immutable_experiments = {}

    def fixture(action, document, **extra):
        nonlocal command_index
        command_index += 1
        folder = store / 'fixture-ops' / f'{command_index:02d}-{action}'
        request, result = folder / 'request.json', folder / 'result.json'
        write(request, {'action': action, 'document': str(document), **extra})
        env = {**os.environ, 'FIXTURE_FREECAD_REQUEST': str(request), 'FIXTURE_FREECAD_RESULT': str(result),
               'CAELAB_NATIVE_EDIT_REPO': str(REPO)}
        executed = subprocess.run([os.environ['FREECAD_CMD'], str(REPO / 'scripts/native_edit_fixture_worker.py')],
                                  env=env, capture_output=True, text=True, timeout=150)
        (folder / 'stdout.txt').write_text(executed.stdout)
        (folder / 'stderr.txt').write_text(executed.stderr)
        answer = json.loads(result.read_text())
        assert executed.returncode == 0 and answer['ok'], answer
        return answer['result']

    def native_source(model):
        return store / 'native_designs' / model / 'editable.FCStd'

    def freeze_source(model, name):
        target = store / 'source-revisions' / f'{name}.FCStd'
        target.parent.mkdir(parents=True, exist_ok=True)
        assert not target.exists()
        shutil.copy2(native_source(model), target)
        return target

    def rejected_precondition(name, call, expected):
        try:
            call()
        except ValueError as exc:
            assert any(marker in str(exc) for marker in expected), ('Unexpected refusal', name, str(exc), expected)
            record['cases'].append({'case': name, 'outcome': 'PASS_EXPECTED_PRECONDITION_REFUSAL', 'reason': str(exc)})
            write(receipt, record)
        else:
            raise AssertionError('Expected native identity/source refusal: ' + name)

    def stale_execution(model, name, values, expected=('refresh registry',)):
        experiment = 'E-' + run_id + '-' + name
        rejected_precondition(name, lambda: lab.run_experiment(study_id=study, experiment_id=experiment,
                                                              backend=BACKEND, model=model, values=values), expected)
        assert not (store / 'experiments' / experiment).exists()

    def result(model, name, values, bounds, volume, center=None):
        experiment = 'E-' + run_id + '-' + name
        observed = lab.run_experiment(study_id=study, experiment_id=experiment, backend=BACKEND,
                                      model=model, values=values)
        assert observed['status'] == 'COMPLETED_REVIEW_REQUIRED' and observed['decision'] == 'NOT_RELEASED'
        assert observed['metrics']['cad_bounds']['unit'] == 'mm'
        assert observed['metrics']['cad_volume']['unit'] == 'mm^3'
        assert len(observed['metrics']['cad_bounds']['value']) == len(bounds) == 3
        for actual, expected in zip(observed['metrics']['cad_bounds']['value'], bounds):
            near(actual, expected, LENGTH_TOLERANCE_MM)
        near(observed['metrics']['cad_volume']['value'], volume, VOLUME_TOLERANCE_MM3)
        assert observed['cad_revision'] and lab.inspect_experiment(experiment)['cad_revision'] == observed['cad_revision']
        unknown = [v['type'] for v in observed['validations'] if v['status'] == 'UNKNOWN']
        assert {'machine_interface', 'static_strength', 'physical_load_test', 'fatigue_durability'} <= set(unknown)
        cad = store / 'experiments' / experiment / 'cad'
        native = fixture('describe', cad / 'editable.FCStd')
        assert len(native['bounds_mm']) == 3
        for actual, expected in zip(native['bounds_mm'], bounds):
            near(actual, expected, LENGTH_TOLERANCE_MM)
        near(native['volume_mm3'], volume, VOLUME_TOLERANCE_MM3)
        shape = cq.importers.importStep(str(cad / 'native.step')).val()
        box = shape.BoundingBox()
        for actual, expected in zip((box.xlen, box.ylen, box.zlen), bounds):
            near(actual, expected, LENGTH_TOLERANCE_MM)
        near(shape.Volume(), volume, VOLUME_TOLERANCE_MM3)
        if center is not None:
            assert len(native['center_mm']) == len(center) == 3
            for actual, expected in zip(native['center_mm'], center):
                near(actual, expected, LENGTH_TOLERANCE_MM)
            for actual, expected in zip(shape.Center().toTuple(), center):
                near(actual, expected, LENGTH_TOLERANCE_MM)
        record['cases'].append({'case': name, 'outcome': 'PASS_ANALYTICAL_NATIVE_AND_STEP',
                                'experiment_id': experiment, 'cad_revision': observed['cad_revision'],
                                'native': native, 'metrics': observed['metrics'], 'unknown': unknown,
                                'artifacts': len(observed['artifacts']), 'decision': observed['decision']})
        write(receipt, record)
        immutable_experiments[experiment] = inventory(store / 'experiments' / experiment)
        write(store / 'original-experiment-inventories.json', immutable_experiments)
        print(json.dumps({'case': name, 'outcome': 'PASS_ANALYTICAL_NATIVE_AND_STEP'}), flush=True)
        return observed

    def discovery(model):
        candidates = lab.discover_parameters(BACKEND, model)
        paths = [c['native']['path'] for c in candidates]
        assert len(paths) == len(set(paths)), 'Ambiguous native selector'
        return candidates

    def named_candidate(model, name):
        matches = [c for c in discovery(model) if c['native']['object'] == 'LocatorProfile' and c['label'] == name]
        assert len(matches) == 1, (name, matches)
        assert matches[0]['lower'] is None and matches[0]['upper'] is None, 'Borrowed registered bounds'
        return matches[0]

    try:
        record['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
        record['source_dirty_before'] = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True).strip())
        record['fixture_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO / 'plugins/fixture_design/upstream', text=True).strip()
        assert not record['source_dirty_before'], 'Freeze/commit the source before actual native acceptance'
        lab.create_study(study, 'Imported native Part and Sketcher revisions',
                         'Do named dimensions survive native edits without ambiguous research mappings?',
                         'Old keys remain bound to named dimensions; new dimensions have source-bound unique selectors.',
                         'Verify analytical geometry, source refresh and refusal before export.')

        part_input = store / 'inputs/imported-box.FCStd'
        part_input.parent.mkdir()
        original = fixture('box_new', part_input)
        assert original['bounds_mm'] == REFERENCE['part_original']['bounds_mm']
        near(original['volume_mm3'], 960, VOLUME_TOLERANCE_MM3)
        part = lab.import_native_model(part_input)['design']
        lab.register_parameter(study, BACKEND, part, 'ImportedBox|property|Length', 'length', 'Box length', 10, 24)
        part_before = result(part, 'part-before', {'length': 18}, [18, 10, 8], 1440)
        part_before_hash = sha(store / 'experiments' / part_before['experiment_id'] / 'result.json')
        freeze_source(part, 'part-before-edit')
        fixture('part_length', native_source(part))
        freeze_source(part, 'part-after-edit')
        stale_execution(part, 'part-stale', {'length': 20})
        refresh = lab.refresh_registry(study, BACKEND, part)
        assert next(e for e in refresh['entries'] if e['parameter_id'] == 'length')['current_value'] == 14
        part_after = result(part, 'part-after', {'length': 20}, [20, 10, 8], 1600)
        assert part_after['cad_revision'] != part_before['cad_revision']
        assert sha(store / 'experiments' / part_before['experiment_id'] / 'result.json') == part_before_hash

        legacy = lab.create_native_model(template='sketch_locator')['design']
        fixture('legacy_register', native_source(legacy))
        legacy_input = freeze_source(legacy, 'legacy-input-radius4')
        sketch = lab.import_native_model(legacy_input)['design']
        radius_key = 'LocatorProfile|constraint|0'
        lab.register_parameter(study, BACKEND, sketch, radius_key, 'radius', 'Locator radius', 2, 10)
        sketch_before = result(sketch, 'sketch-before', {'radius': 6}, [12, 12, 8], 288 * math.pi, [0, 0, 4])
        sketch_before_hash = sha(store / 'experiments' / sketch_before['experiment_id'] / 'result.json')
        freeze_source(sketch, 'sketch-before-insert')
        fixture('sketch_layout', native_source(sketch), constraints=[
            {'type': 'DistanceX', 'name': 'center_x', 'value': 2},
            {'type': 'Radius', 'name': 'locator_radius', 'value': 4}])
        freeze_source(sketch, 'sketch-after-insert')
        stale_execution(sketch, 'sketch-stale', {'radius': 6})
        inserted = named_candidate(sketch, 'center_x')
        assert inserted['native']['path'] != radius_key and inserted['value'] == 2
        refresh = lab.refresh_registry(study, BACKEND, sketch)
        assert next(e for e in refresh['entries'] if e['parameter_id'] == 'radius')['native']['path'] == radius_key
        rejected_precondition('unregistered-positional-fallback', lambda: lab.register_parameter(
            study, BACKEND, sketch, 'LocatorProfile|constraint|1', 'wrong_radius_alias', 'Wrong alias', 2, 10),
            ('Selected native CAD parameter was not discovered',))
        assert not any(e['parameter_id'] == 'wrong_radius_alias' for e in lab.registry(study)['entries'])
        center_key = named_candidate(sketch, 'center_x')['native']['path']
        lab.register_parameter(study, BACKEND, sketch, center_key, 'center_offset', 'Origin minus center X', 0, 8)
        registered = {e['parameter_id']: e for e in lab.registry(study)['entries']}
        assert registered['radius']['native']['path'] == radius_key
        assert registered['center_offset']['native']['path'] == center_key
        result(sketch, 'sketch-offset', {'radius': 6, 'center_offset': 5}, [12, 12, 8], 288 * math.pi, [-5, 0, 4])

        fixture('sketch_layout', native_source(sketch), constraints=[
            {'type': 'DistanceY', 'name': 'center_y', 'value': 3},
            {'type': 'Radius', 'name': 'locator_radius', 'value': 4},
            {'type': 'DistanceX', 'name': 'center_offset', 'value': 2}])
        old_vertical = named_candidate(sketch, 'center_y')
        fixture('sketch_layout', native_source(sketch), constraints=[
            {'type': 'Radius', 'name': 'locator_radius', 'value': 4},
            {'type': 'DistanceX', 'name': 'center_offset', 'value': 2}])
        stale_execution(sketch, 'deleted-unregistered-stale', {'radius': 6, 'center_offset': 5})
        lab.refresh_registry(study, BACKEND, sketch)
        assert {e['parameter_id']: e['native']['path'] for e in lab.registry(study)['entries']}['center_offset'] == center_key
        result(sketch, 'sketch-after-delete', {'radius': 6, 'center_offset': 5}, [12, 12, 8], 288 * math.pi, [-5, 0, 4])

        fixture('sketch_layout', native_source(sketch), constraints=[
            {'type': 'DistanceY', 'name': 'center_y', 'value': 3},
            {'type': 'Radius', 'name': 'locator_radius', 'value': 4},
            {'type': 'DistanceX', 'name': 'center_offset', 'value': 2}])
        fixture('touch_label', native_source(sketch))
        stale_execution(sketch, 'opaque-reorder-stale', {'radius': 6, 'center_offset': 5})
        fresh_vertical = named_candidate(sketch, 'center_y')
        lab.refresh_registry(study, BACKEND, sketch)
        rejected_precondition('old-unregistered-selector', lambda: lab.register_parameter(
            study, BACKEND, sketch, old_vertical['native']['path'], 'vertical_stale', 'Old selection', 0, 8),
            ('Selected native CAD parameter was not discovered',))
        assert not any(e['parameter_id'] == 'vertical_stale' for e in lab.registry(study)['entries'])
        assert old_vertical['native']['path'] != fresh_vertical['native']['path']
        lab.register_parameter(study, BACKEND, sketch, fresh_vertical['native']['path'], 'vertical_offset', 'Origin minus center Y', 0, 8)
        result(sketch, 'sketch-reordered', {'radius': 6, 'center_offset': 5, 'vertical_offset': 7},
               [12, 12, 8], 288 * math.pi, [-5, -7, 4])
        recovered = freeze_source(sketch, 'all-registered-before-negative-cases')
        refusal_markers = {'rename_registered': 'NATIVE_REGISTERED_DIMENSION_MISSING',
                           'delete_registered': 'NATIVE_REGISTERED_DIMENSION_MISSING',
                           'reference_registered': 'NATIVE_REGISTERED_NOT_DRIVING',
                           'duplicate_key': 'NATIVE_DUPLICATE_KEY', 'duplicate_identity': 'NATIVE_DUPLICATE_IDENTITY'}
        for invalid, marker in refusal_markers.items():
            fixture(invalid, native_source(sketch))
            freeze_source(sketch, 'invalid-' + invalid)
            rejected_precondition(invalid, lambda: lab.inspect_native_model(sketch), (marker,))
            stale_execution(sketch, 'blocked-' + invalid, {'radius': 6}, (marker,))
            if invalid in ('duplicate_key', 'duplicate_identity'):
                native_models_before = inventory(store / 'native_designs')
                rejected_precondition('import-' + invalid, lambda: lab.import_native_model(native_source(sketch)), (marker,))
                assert inventory(store / 'native_designs') == native_models_before, 'Malformed import created native baseline/export'
            shutil.copy2(recovered, native_source(sketch))
            assert sha(native_source(sketch)) == sha(recovered)
        assert sha(store / 'experiments' / sketch_before['experiment_id'] / 'result.json') == sketch_before_hash
        for experiment, original_inventory in immutable_experiments.items():
            assert inventory(store / 'experiments' / experiment) == original_inventory, ('Historical experiment changed', experiment)
            lab.inspect_experiment(experiment)
        write(store / 'original-experiment-inventories.json', immutable_experiments)
        record['original_experiment_inventory_sha256'] = sha(store / 'original-experiment-inventories.json')
        record['all_original_experiment_files_hashes_sizes_unchanged'] = True
        final_entries = {e['parameter_id']: e for e in lab.registry(study)['entries']}
        assert final_entries['radius']['native']['path'] == radius_key and final_entries['center_offset']['native']['path'] == center_key
        record['registry_revision'] = lab.registry(study)['revision']
        record['registered_native_paths'] = {k: v['native']['path'] for k, v in final_entries.items()}
        record['source_commit_after'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
        record['fixture_commit_after'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO / 'plugins/fixture_design/upstream', text=True).strip()
        record['source_dirty_after'] = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO, text=True).strip())
        assert record['source_commit_after'] == record['source_commit'], 'Main source commit changed during acceptance'
        assert record['fixture_commit_after'] == record['fixture_commit'], 'Fixture pin changed during acceptance'
        assert not record['source_dirty_after']
        record['outcome'] = 'PASS_IMPORTED_EDITED_PART_NAMED_SKETCHER_REVISIONS'
        record['engineering_decision'], record['solver_status'] = 'NOT_RELEASED', 'NOT_RUN'
        record['completed_utc'] = datetime.now(timezone.utc).isoformat()
        write(receipt, record)
        print(json.dumps({'outcome': record['outcome'], 'cases': len(record['cases']), 'store': str(store)}), flush=True)
    except Exception as exc:
        record.update(outcome='FAIL', error=str(exc), traceback=traceback.format_exc(),
                      completed_utc=datetime.now(timezone.utc).isoformat())
        write(receipt, record)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--run-id', default='native-edits')
    args = parser.parse_args()
    run(args.store.resolve(), args.run_id)
