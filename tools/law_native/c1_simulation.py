"""One exact frozen Simulation FE job OR a separate-process no-compute cold read.

Use c1_acceptance.py to supervise both stages through existing owned_check.
No new runtime, solver, owner or queue; no edits/re-signing of saved provenance.
"""
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import argparse
import builtins
import hashlib
import json
import os
import sys
import time
import traceback
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from caelab.workbench import Workbench
from caelab.storage import canonical_hash, load_json, save_json
from caelab import evaluation, law_native_fe
from caelab.jobs import JobManager, TERMINAL
from caelab.adapters.law_native_runtime import source_identity
from tools.law_native.c1_tripwires import SourceGuardTripwire


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(wb, d, op, arguments=None):
    return wb.document_command(d['id'], op, arguments or {}, session_id=d['session_id'],
                              expected_generation=d['generation'])


def exact_sources(receipt):
    old = receipt['review']['source']['law_source']['files']
    now = source_identity()['files']
    if set(old) != set(now) or any(old[k]['sha256'] != now[k]['sha256'] for k in old):
        raise AssertionError('Original ten constitutive/FE sources differ; do not re-sign input')
    return {k: v['sha256'] for k, v in now.items()}


def run_stage(frozen_path, output):
    folder = Path(output);folder.mkdir(parents=True, exist_ok=False)
    frozen_path = Path(frozen_path);raw = frozen_path.read_bytes();frozen = json.loads(raw)
    draft = frozen['simulation_draft'];receipt = draft['settings']['source_receipt']
    (folder/'exact-frozen-input.json').write_bytes(raw)
    report = {'status': 'STARTING', 'stage': 'EXACT_FROZEN_SIMULATION', 'pid': os.getpid(),
              'platform': sys.platform, 'Windows': 'ACTUAL' if sys.platform == 'win32' else 'NOT_RUN',
              'FreeCAD_in_this_stage': 'NOT_RUN', 'input_file_sha256': sha(frozen_path),
              'draft_sha256': canonical_hash(draft), 'settings_gate_calls': [], 'cleanup': 'NOT_STARTED'}
    wb = None;code = 1;tripwire = SourceGuardTripwire(receipt)
    try:
        report['protected_sources'] = exact_sources(receipt)
        with tripwire:
            wb = Workbench(folder/'workspace', configuration={'workers': 1, 'cpu_budget': 1})
            original_settings = wb._settings
            def observe(backend, settings):
                report['settings_gate_calls'].append({'backend': backend, 'settings_sha256': canonical_hash(settings)})
                assert settings == draft['settings'], 'A settings entry changed the frozen input'
                return original_settings(backend, settings)
            wb._settings = observe
            d = wb.document_open(kind='simulation', title='LAW-C1 exact native frozen DP specimen', draft=deepcopy(draft))
            d = command(wb, d, 'document.save')['document']
            launched = command(wb, d, 'simulation.evaluate');jobid = launched['job']['id']
            report.update(document_id=d['id'], job_id=jobid)
            deadline = time.monotonic() + 195
            while time.monotonic() < deadline:
                job = wb.manager.status(jobid)
                if job['state'] in TERMINAL or job['state'] == 'CLEANUP_PENDING':
                    break
                time.sleep(.025)
            else:
                wb.manager.cancel(jobid)
                raise TimeoutError('Exact FE job exceeded the bounded wait; cancelled only this owned job')
            report['job'] = job
            # Preserve the PRIMARY failure; never replace it with a no-result error.
            if job['state'] != 'SUCCEEDED':
                command(wb, wb.document_read(d['id']), 'document.save')
                raise AssertionError('Exact FE job did not succeed: ' + json.dumps(job.get('error', job['state'])))
            result = wb.result(jobid);diag = result['diagnostics'];steps = diag['steps']
            if (result['execution_status'] != 'SUCCEEDED' or diag['FE_execution'] != 'ACTUAL' or
                    diag['pair_comparison']['status'] != 'PASS'):
                raise AssertionError('Actual spatial FE and every-IP pair have not both passed')
            assert len(report['settings_gate_calls']) == 2
            assert diag['source_receipt'] == receipt
            assert len(steps) == len(draft['settings']['law']['time']) == 4
            assert diag['global_newton_calls'] == 3 and diag['constitutive_calls']['hessian'] > 0
            assert all(len(step['local']) == 64 and step['actual_free_dofs'] == 3 for step in steps)
            accepted = [deepcopy(draft['settings']['law']['initial_state']) for _ in range(64)]
            for step in steps:
                assert step['force_residual_N'] <= draft['settings']['solver']['force_tolerance_N']
                assert [row['initial_state_sha256'] for row in step['local']] == [canonical_hash(s) for s in accepted]
                accepted = [deepcopy(row['state']) for row in step['local']]
            assert diag['last_accepted_states'] == accepted and diag['failed_increment'] is None
            d = command(wb, wb.document_read(d['id']), 'document.save')['document']
            saved_result = wb.document_result(d['id'], jobid)
            assert canonical_hash(saved_result) == canonical_hash(result)
            assert wb.document_read(d['id'])['draft'] == draft
            report.update(saved_revision=d['saved_revision'], result_sha256=canonical_hash(result),
                source_receipt_sha256=canonical_hash(receipt), source_sha256=receipt['review']['source']['snapshot_sha256'],
                assignment_sha256=receipt['assignment_sha256'], review_sha256=receipt['review']['review_sha256'],
                job_file_sha256=sha(wb.root/'jobs'/(jobid+'.json')), job_count=len(wb.manager.list()),
                FE_execution=diag['FE_execution'], runtime=diag['runtime'],
                pair_comparison=diag['pair_comparison'], global_newton_calls=diag['global_newton_calls'],
                integration_points_per_step=[len(s['local']) for s in steps],
                actual_free_dofs=[s['actual_free_dofs'] for s in steps],
                force_residual_N=[s['force_residual_N'] for s in steps],
                accepted_state_isolation='PASS', FE_LIMITS=deepcopy(law_native_fe.FE_LIMITS))
            assert sha(frozen_path) == report['input_file_sha256']
            assert exact_sources(receipt) == report['protected_sources']
            report['status'] = 'PASS';code = 0
    except BaseException as error:
        report.update(status='FAIL', error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        report['source_guard_io_attempts'] = tripwire.attempts
        if wb is not None:
            report['shutdown'] = wb.shutdown()
            report['cleanup'] = 'CONFIRMED_JOINED' if report['shutdown']['joined'] else 'UNKNOWN'
            if not report['shutdown']['joined']:
                report['status'] = 'FAIL';code = 125
        else:
            report['cleanup'] = 'NO_OWNER_CREATED'
        save_json(folder/'stage.json', report)
    return code


def cold_stage(previous, output):
    prior = Path(previous);folder = Path(output);folder.mkdir(parents=True, exist_ok=False)
    saved = load_json(prior/'stage.json');frozen = load_json(prior/'exact-frozen-input.json')
    receipt = frozen['simulation_draft']['settings']['source_receipt']
    report = {'status': 'STARTING', 'stage': 'FRESH_PROCESS_COLD_READ', 'pid': os.getpid(),
              'previous_pid': saved['pid'], 'calculation_attempts': [], 'cleanup': 'NOT_STARTED'}
    wb = None;code = 1;tripwire = SourceGuardTripwire(receipt)
    def forbidden(*args, **kwargs):
        report['calculation_attempts'].append('forbidden submission/evaluation/process')
        raise AssertionError('COLD_MUST_NOT_SUBMIT_EVALUATE_OR_SPAWN')
    original_import = builtins.__import__
    def import_without_felupe(name, *args, **kwargs):
        if name == 'felupe' or name.startswith('felupe.'):
            report['calculation_attempts'].append('felupe import')
            raise AssertionError('COLD_MUST_NOT_IMPORT_FELUPE_RUNTIME')
        return original_import(name, *args, **kwargs)
    try:
        assert saved['status'] == 'PASS' and os.getpid() != saved['pid']
        from plugins.material_point import law_native as law
        with ExitStack() as stack:
            stack.enter_context(tripwire)
            for obj, name in ((Workbench, 'submit'), (Workbench, '_execute'), (JobManager, 'submit'),
                              (evaluation, 'run'), (evaluation, 'evaluate'),
                              (law, 'update'), (law, 'initial_response')):
                stack.enter_context(patch.object(obj, name, forbidden))
            stack.enter_context(patch('subprocess.Popen', forbidden))
            stack.enter_context(patch.object(builtins, '__import__', import_without_felupe))
            wb = Workbench(prior/'workspace')
            assert len(wb.manager.list()) == saved['job_count'] == 1
            before_job = sha(wb.root/'jobs'/(saved['job_id']+'.json'))
            d = wb.document_open(kind='simulation', document_id=saved['document_id'])
            assert d['draft'] == frozen['simulation_draft'] and d['saved_revision'] == saved['saved_revision']
            result = wb.document_result(d['id'], saved['job_id'])
            assert canonical_hash(result) == saved['result_sha256']
            assert result['diagnostics']['source_receipt'] == receipt
            assert canonical_hash(wb.result(saved['job_id'])) == saved['result_sha256']
            assert sha(wb.root/'jobs'/(saved['job_id']+'.json')) == before_job == saved['job_file_sha256']
            assert len(wb.manager.list()) == 1 and not report['calculation_attempts']
            report.update(status='PASS', new_jobs=0, result_sha256=canonical_hash(result),
                saved_revision=d['saved_revision'], assignment_sha256=receipt['assignment_sha256'],
                review_sha256=receipt['review']['review_sha256'], source_sha256=receipt['review']['source']['snapshot_sha256'],
                runtime_imports=0, source_guard_io_attempts=tripwire.attempts)
            code = 0
    except BaseException as error:
        report.update(status='FAIL', error_type=type(error).__name__, error=str(error), traceback=traceback.format_exc())
        traceback.print_exc()
    finally:
        report['source_guard_io_attempts'] = tripwire.attempts
        if wb is not None:
            report['shutdown'] = wb.shutdown()
            report['cleanup'] = 'CONFIRMED_JOINED' if report['shutdown']['joined'] else 'UNKNOWN'
            if not report['shutdown']['joined']:
                report['status'] = 'FAIL';code = 125
        else:
            report['cleanup'] = 'NO_OWNER_CREATED'
        save_json(folder/'stage.json', report)
    return code


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage', required=True, choices=('run', 'cold'));p.add_argument('--output', required=True)
    p.add_argument('--frozen');p.add_argument('--previous');a = p.parse_args()
    if a.stage == 'run' and not a.frozen or a.stage == 'cold' and not a.previous:
        p.error('run requires --frozen; cold requires --previous')
    raise SystemExit(run_stage(a.frozen, a.output) if a.stage == 'run' else cold_stage(a.previous, a.output))
