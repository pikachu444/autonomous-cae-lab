"""One tiny explicit-input exercise using the existing Simulation/JobManager.

Default: import, edit, save, and reopen in a different Python process; no solver.
--run-native: Windows only, exactly one Starter/Engine job through ImpactAdapter.
This file contains no solver double, alternate owner, installer, or network call.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

REPOSITORY = Path(__file__).resolve().parents[3]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from caelab.execution_control import run_owned_command
from caelab.impact_input_workflow import (
    apply_native_field, inspect, open_definition, response_for_source,
)
from caelab.impact_model import model_from_settings
from caelab.storage import canonical_hash, save_json
from caelab.workbench import Workbench

TERMINAL = {'SUCCEEDED', 'FAILED', 'CANCELLED', 'PARTIAL_FAILURE', 'INTERRUPTED'}
REPORT = 'input-a-check.json'
COLD_REPORT = 'input-a-cold-read.json'

# Declared before any Windows native run. These are smoke-test quantities, NOT
# qualification tolerances. Always evaluate displacement at actual native time.
EXPECTED = {
    'end_s': 0.0012,
    'velocity_Z_mm_s': -100.0,
    'moving_tetra_mass_Mg': 1.3e-6,
    'kinetic_energy_J': 6.5e-6,
    'native_tetra4_formulation': 1000,
    'native_time_step_scale': 0.5,
    'displacement_absolute_mm': 5e-5,
    'velocity_absolute_mm_s': 0.05,
    'mass_relative': 5e-6,
    'energy_relative': 5e-4,
    'mass_absolute_kg': 1e-12,
    'energy_absolute_J': 1e-12,
    'qualification': 'UNKNOWN',
}


def command(owner: Workbench, document: dict, name: str, arguments=None) -> dict:
    return owner.document_command(
        document['id'], name, arguments or {},
        session_id=document['session_id'], expected_generation=document['generation'],
        command_id='input_a_' + uuid.uuid4().hex,
    )


def make_definition(route: str) -> tuple[dict, int]:
    """Public original bytes plus one explicit edit; never writes input fixtures."""
    folder = Path(__file__).resolve().parent
    if route == 'native':
        native = folder / 'native'
        draft = open_definition(native / 'impact_0000.rad', native,
                                engine=native / 'impact_0001.rad', units='Mg/mm/s')
        settings = draft['settings']
        field = next(f for f in inspect(settings)['fields'] if f['field'] == 'end_s')
        settings = apply_native_field(
            settings, field['id'], EXPECTED['end_s'], reason='공개 검사: 종료 시간 명시 변경',
            expected_definition_sha256=canonical_hash(settings),
        )['settings']
        node = 2
        identity = {'native_id': node}
    elif route == 'assembly':
        draft = open_definition(folder / 'assembly.inp', folder)
        settings = draft['settings']
        from caelab.impact_assembly import target_key, exact_entity
        model = model_from_settings(settings)
        settings['gravity_mm_s2'] = [0., 0., 0.]
        settings['motions'] = [{
            'node_set': target_key(model, 'nsets', 'DROP.BODY-2.BODY'),
            'mode': 'velocity', 'height_mm': None,
            'velocity_mm_s': [0., 0., EXPECTED['velocity_Z_mm_s']],
            'omega_rad_s': [0., 0., 0.], 'center_mm': [0., 0., 0.],
            'translation_mm': [0., 0., 0.],
        }]
        settings['time'] = {'end_s': EXPECTED['end_s'], 'field_interval_s': .0001,
                            'history_interval_s': .00001, 'scale': .9,
                            'mass_scaling': False, 'target_step_s': None}
        node = exact_entity(model, 'POINTS', 'BODY-2', 20)
        identity = {'instance': 'BODY-2', 'local_id': 20}
    else:
        raise ValueError('Choose native or assembly')
    settings['responses'] = [response_for_source(
        settings, name='selected_' + quantity, quantity=quantity, component='Z',
        association='POINTS', **identity,
    ) for quantity in ('displacement', 'velocity')]
    # The script explicitly selects these exact source entities after the edit.
    # A GUI must show this same before/after review before its Apply action.
    from caelab.impact_reference_bindings import review, accept_review
    reviewed = review(settings)
    settings = accept_review(settings, expected_definition_sha256=canonical_hash(settings),
                             expected_review_sha256=reviewed['review_sha256'], acknowledged=True)
    draft['settings'] = settings
    return draft, node


def selectors(node: int) -> list[str]:
    return [f'impact.displacement.Z@{node}', f'impact.velocity.Z@{node}',
            'global_2', 'global_6']


def check_response(response: dict, unit: str, expected, *, atol: float, rtol=0.) -> dict:
    if response.get('unit') != unit:
        raise ValueError('Required physical unit is missing or differs: ' + unit)
    if response.get('has_calculation_gaps'):
        raise ValueError('A required response has calculation gaps')
    axes = response.get('axes', [])
    if len(axes) != 1 or axes[0].get('name') != 'time' or axes[0].get('unit') != 's':
        raise ValueError('Required physical time axis is missing')
    times, values = axes[0].get('values', []), response.get('value', [])
    if not times or len(times) != len(values):
        raise ValueError('Required sample values are missing')
    if any(type(t) not in (float, int) or not math.isfinite(t) or t < 0 for t in times):
        raise ValueError('Invalid native physical time')
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('Duplicate/non-monotonic native physical time')
    errors = []
    for clock, value in zip(times, values):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Required native value is missing or nonfinite')
        prediction = expected(clock)
        error = abs(value - prediction)
        if error > atol + rtol * abs(prediction):
            raise ValueError(f'Expected quantity differs at native time {clock:g} s')
        errors.append(error)
    return {'status': 'PASS', 'samples': len(values), 'time_first_s': times[0],
            'time_last_s': times[-1], 'max_absolute_error': max(errors), 'unit': unit,
            'sampling': 'RECORDED_SAMPLES_NOT_ALL_SOLVER_INCREMENTS'}


def check_expected(result: dict, route: str, node: int) -> dict:
    responses = result['responses']
    u = responses[f'impact.displacement.Z@{node}']
    v = responses[f'impact.velocity.Z@{node}']
    if u.get('frame') != 'MODEL_GLOBAL' or v.get('frame') != 'MODEL_GLOBAL':
        raise ValueError('Unknown native vector coordinate frame')
    mass_kg = EXPECTED['moving_tetra_mass_Mg'] * 1000 * (2 if route == 'assembly' else 1)
    return {
        'displacement': check_response(u, 'mm', lambda t: EXPECTED['velocity_Z_mm_s'] * t,
                                       atol=EXPECTED['displacement_absolute_mm']),
        'velocity': check_response(v, 'mm/s', lambda t: EXPECTED['velocity_Z_mm_s'],
                                   atol=EXPECTED['velocity_absolute_mm_s']),
        'total_mass': check_response(responses['global_6'], 'kg', lambda t: mass_kg,
                                     atol=EXPECTED['mass_absolute_kg'], rtol=EXPECTED['mass_relative']),
        'kinetic_energy': check_response(responses['global_2'], 'J', lambda t: EXPECTED['kinetic_energy_J'],
                                         atol=EXPECTED['energy_absolute_J'], rtol=EXPECTED['energy_relative']),
        'qualification': 'UNKNOWN', 'RBODY_native_inertia': 'NOT_SUPPORTED',
    }


def cold_read(workspace: Path) -> int:
    """No submit, runtime lookup, postprocessing or solver call exists here."""
    receipt = json.loads((workspace / REPORT).read_text(encoding='utf-8'))
    owner = Workbench(workspace, configuration={'workers': 1})
    report = {'operation': 'SAVED_INPUT_AND_SELECTED_RESULT_READ', 'solver_execution': 'NOT_PERFORMED'}
    try:
        before = [j['id'] for j in owner.manager.list()]
        doc = owner.document_open(kind='simulation', document_id=receipt['document_id'])
        if canonical_hash(doc['draft']) != receipt['draft_sha256']:
            raise ValueError('The saved input definition changed')
        report['saved_input'] = 'PASS'
        if receipt.get('selected_sha256'):
            result = owner.document_result(doc['id'], receipt['job_id'],
                                           selection={'responses': receipt['selection']})
            if canonical_hash(result) != receipt['selected_sha256']:
                raise ValueError('The saved selected result changed')
            report['selected_result'] = 'PASS'
        else:
            report['selected_result'] = 'NOT_RUN_NO_SELECTED_RESULT'
        if [j['id'] for j in owner.manager.list()] != before:
            raise ValueError('Reopening unexpectedly submitted a job')
        report['new_jobs'] = 0
        report['status'] = 'PASS'
    except Exception as error:
        report.update(status='FAILED', error=str(error))
    finally:
        report['shutdown'] = owner.shutdown()
        if not report['shutdown'].get('joined'):
            report.update(status='FAILED', cleanup='UNCONFIRMED')
        save_json(workspace / COLD_REPORT, report)
    print('별도 프로세스 재열기:', report['status'])
    return 0 if report['status'] == 'PASS' else 1


def exercise(workspace: Path, route: str, run_native: bool) -> int:
    # No overwriting previous evidence or mixing examples in a live user workspace.
    workspace.mkdir(parents=True, exist_ok=False)
    draft, node = make_definition(route)
    input_report = inspect(draft['settings'])
    save_json(workspace / 'input-a-inspection.json', input_report)
    report = {'request': 'PRO-IMPACT-INPUT-A-20261015-01', 'route': route,
              'native_execution': 'NOT_RUN', 'expected': deepcopy(EXPECTED),
              'selected_result': 'NOT_RUN', 'job_id': None, 'new_jobs_requested': 0,
              'status': 'INPUT_CHECK_ONLY', 'qualification': 'UNKNOWN'}
    owner = Workbench(workspace, configuration={'workers': 1})
    doc = None
    try:
        doc = owner.document_open(kind='simulation', title='공개 충격 입력 검사', draft=draft)
        doc = command(owner, doc, 'document.save')['document']
        report.update(document_id=doc['id'], draft_sha256=canonical_hash(doc['draft']),
                      selection=selectors(node))
        if input_report['readiness'] != 'INPUT_ADMITTED_RUNTIME_NOT_PROBED':
            raise ValueError('공개 입력의 실행 검증이 실패했습니다')
        print('입력 확인: 절점', input_report['node_count'], '/ 요소', input_report['element_count'])
        if not run_native:
            print('Windows 계산: 미실행. 입력 편집·저장·재열기만 확인합니다.')
        elif os.name != 'nt':
            report.update(status='NOT_RUN', reason='Windows native 실행 전용 검사입니다. 다른 runtime으로 바꾸지 않습니다.')
            print(report['reason'])
        else:
            reply = command(owner, doc, 'simulation.evaluate')
            doc, job = reply['document'], reply['job']
            report.update(job_id=job['id'], new_jobs_requested=1, native_execution='SUBMITTED')
            try:
                while True:
                    job = owner.manager.status(job['id'])
                    if job['state'] in TERMINAL:
                        break
                    time.sleep(.1)
            except KeyboardInterrupt:
                owner.manager.cancel(job['id'])
                report.update(status='CANCEL_REQUESTED', reason='사용자 취소 요청; 종료 사실은 원 Job에서 확인')
                raise
            report.update(job_state=job['state'], native_execution='ATTEMPTED', status=job['state'])
            actual = owner.document_result(doc['id'], job['id'], selection={'metadata_only': True})
            save_json(workspace / 'input-a-original-result.json', actual)
            report['native_outcome'] = actual.get('diagnostics', {})
            if job['state'] == 'SUCCEEDED':
                selected = owner.document_result(doc['id'], job['id'], selection={'responses': selectors(node)})
                report['expected_quantity_checks'] = check_expected(selected, route, node)
                if not selected.get('post_input'):
                    raise ValueError('The original Post source was not registered')
                report.update(selected_result='PASS', selected_sha256=canonical_hash(selected))
                save_json(workspace / 'input-a-selected-result.json', selected)
            print('기존 Simulation 계산 상태:', job['state'])
        doc = command(owner, doc, 'document.save')['document']
        report['draft_sha256'] = canonical_hash(doc['draft'])
    except KeyboardInterrupt:
        # Retain the original Job and let existing owned process cleanup run.
        pass
    except Exception as error:
        report.update(status='FAILED', error=str(error))
        print('검사 실패:', str(error))
    finally:
        if doc is not None:
            try:
                command(owner, doc, 'document.save')
            except Exception as error:
                report['save_error'] = str(error)
        report['shutdown'] = owner.shutdown()
        if not report['shutdown'].get('joined'):
            report.update(status='FAILED', cleanup='UNCONFIRMED')
        save_json(workspace / REPORT, report)
    if report.get('cleanup') == 'UNCONFIRMED':
        print('종료 확인 실패: 원 작업과 cleanup 기록을 보존했습니다.')
        return 1
    # A real, separately owned Python process; the child only reopens saved data.
    # Its command runner supplies its own finally stop/reap and durable log.
    if report.get('document_id'):
        try:
            child = run_owned_command([sys.executable, str(Path(__file__).resolve()),
                                       '--workspace', str(workspace), '--reopen-only'],
                                      workspace, 'input_a_cold_read', timeout=60, owned_tree=True)
            if child.returncode != 0:
                report['cold_reopen'] = 'FAILED'
                report['status'] = 'FAILED'
            else:
                report['cold_reopen'] = 'PASS'
        except Exception as error:
            report.update(cold_reopen='FAILED', cold_error=str(error), status='FAILED')
        save_json(workspace / REPORT, report)
    print('별도 프로세스 재열기:', report.get('cold_reopen', 'NOT_RUN'))
    print('검사 기록:', workspace / REPORT)
    if report['status'] == 'NOT_RUN':
        return 2  # Deliberately not a successful native test exit code.
    return 0 if report['status'] in ('INPUT_CHECK_ONLY', 'SUCCEEDED') else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='작은 공개 충격 입력: 기존 Simulation 저장·재열기 및 명시 Windows 실행')
    parser.add_argument('--workspace', type=Path, required=True, help='새 작업 폴더; 이전 결과를 덮어쓰지 않음')
    parser.add_argument('--route', choices=('native', 'assembly'), default='native')
    parser.add_argument('--run-native', action='store_true', help='Windows에서만 기존 pinned Starter/Engine 한 작업 실행')
    parser.add_argument('--reopen-only', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    workspace = args.workspace.expanduser().resolve()
    if args.reopen_only:
        return cold_read(workspace)
    return exercise(workspace, args.route, args.run_native)


if __name__ == '__main__':
    raise SystemExit(main())
