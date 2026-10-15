"""Existing small S1 coupled evaluation, portable prefix reuse and two cold reads.

One original coupled job and one explicitly requested destination job. The
destination reuses only the successful heat prefix and evaluates structure with
the existing adapter. Copy/read/edit/Undo/save/recopy perform no calculation.
"""
from copy import deepcopy
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from caelab.workbench import Workbench
from caelab.evaluation_definition import default_draft, document_reference
from caelab.storage import canonical_hash, load_json, save_json
from caelab.portable_project import inspect_copy, create_copy, open_project, verify_project
from caelab.portable_project_evaluation import read_execution
from caelab.research_workflows import evaluation_progress, evaluation_stage_result
from caelab.transfer_inspection import inspect_transfer
from examples.portable_physics_public import command, save, wait, hashes, no_execution
from examples.s1_windows_transfer import declarations


def fixture(wb):
    sources = []
    models, policy = declarations('uniform')
    for identifier, title, backend, settings in models:
        source = save(wb, wb.document_open(kind='simulation', title=title,
                      draft={'backend': backend, 'settings': settings}))
        sources.append((source, {'id': identifier, 'name': title, 'source': document_reference(source)}))
    draft = default_draft()
    draft['stages'] = [s for _, s in sources]
    draft['transfers'] = [{'id': 'TtoU', 'from_stage': 'Start', 'output': 'temperature',
                          'to_stage': 'Structure', 'input': 'temperature',
                          'mapping': 'p1_temperature', 'lag': 0, 'options': policy}]
    draft['responses'] = [{'id': 'displacement', 'stage': 'Structure', 'response': 'displacement', 'unit': 'm'},
                          {'id': 'stress', 'stage': 'Structure', 'response': 'stress', 'unit': 'Pa'}]
    doc = wb.document_open(kind='evaluation', title='다른 메시의 온도 전달', draft=draft)
    return [source for source, _ in sources], doc


def evaluate(wb, doc):
    receipt = command(wb, doc, 'evaluation.run')
    job = wait(wb, receipt['job']['id'])
    assert job['state'] == 'SUCCEEDED', job
    value = wb.document_result(doc['id'], job['id'])
    assert value['execution_status'] == 'SUCCEEDED', value
    return save(wb, wb.document_read(doc['id'])), value, job['id']


def publish(wb, docs, destination):
    plan = inspect_copy(wb, [d['id'] for d in docs])
    assert plan['status'] == 'READY', plan['issues']
    return create_copy(wb, plan, destination, approved=True, command_id='Ccopy'+os.urandom(8).hex(), session_id=wb.session_id)


def read(wb, doc, evidence):
    job = evidence['job_id']
    assert canonical_hash(wb.document_result(doc['id'], job)) == evidence['result_sha256']
    assert hashes(wb, doc, job) == evidence['files']
    progress = evaluation_progress(wb, doc['id'], job)
    assert progress['job_state'] == 'SUCCEEDED'
    attempts = [evaluation_stage_result(wb, doc['id'], job, s['attempt_id']) for s in progress['stages']]
    assert [canonical_hash(v) for v in attempts] == evidence['attempts']
    transfer = inspect_transfer(wb, doc['id'], job, 'TtoU', 0)
    # Current navigation IDs may differ; the physical transfer receipt is exact.
    assert transfer['exact_values_match'] and transfer['rows'] == evidence['transfer_rows']
    bridge = read_execution(wb.evaluation_documents, doc['id'], job)
    assert bridge['original_run']['arguments'] == evidence['original_run']['arguments']
    assert bridge['execution_replayed'] is False


def cold(output, phase):
    evidence = load_json(output/'evidence.json')
    receipt = load_json(output/('first.json' if phase == 1 else 'second.json'))
    wb = open_project(output/('copy-1' if phase == 1 else 'copy-2'))
    try:
        docs = [wb.document_read(r['document_id']) for r in receipt['documents']]
        doc = next(d for d in docs if d['kind'] == 'evaluation')
        with no_execution(wb):
            read(wb, doc, evidence)
            before = deepcopy(doc['draft']); edited = deepcopy(before)
            edited['responses'][0]['unit'] = 'unfinished'
            doc = command(wb, doc, 'evaluation.update', {'draft': edited})['document']
            doc = command(wb, doc, 'document.undo')['document']; assert doc['draft'] == before
            doc = save(wb, doc)
            assert not wb.manager.list()
        if phase == 1:
            reuse = deepcopy(doc['draft'])
            run = next(r for r in doc['runs'] if r['job_id'] == evidence['job_id'])
            reuse['reuse'] = {'source': {'document_id': doc['id'], 'job_id': run['job_id'],
                'input_revision': run['input_revision'], 'input_sha256': run['input_sha256'],
                'result_sha256': evidence['result_sha256']}, 'stages': ['Start']}
            doc = command(wb, doc, 'evaluation.update', {'draft': reuse})['document']
            doc, result, job = evaluate(wb, doc)
            assert result['stages'][0]['dispatched'] is False
            assert result['stages'][0]['original_attempt_id'] == evidence['original_attempt_id']
            assert result['stages'][1]['dispatched'] is True and job != evidence['job_id']
            save_json(output/'local.json', {'job_id': job, 'result_sha256': canonical_hash(result), 'files': hashes(wb, doc, job)})
            docs = [doc if d['kind'] == 'evaluation' else d for d in docs]
            with no_execution(wb):
                read(wb, doc, evidence)
                save_json(output/'second.json', publish(wb, docs, output/'copy-2'))
        else:
            local = load_json(output/'local.json')
            with no_execution(wb):
                assert canonical_hash(wb.document_result(doc['id'], local['job_id'])) == local['result_sha256']
                assert hashes(wb, doc, local['job_id']) == local['files']
            assert not wb.manager.list()
        assert verify_project(wb.workspace)['status'] == 'READY'
        save_json(output/f'cold-{phase}.json', {'status': 'PASS', 'pid': os.getpid(), 'new_jobs': 1 if phase == 1 else 0})
    finally:
        closed = wb.shutdown(); assert closed['joined'] and not closed['pending']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cold', type=int, choices=(1, 2))
    args = parser.parse_args(); output = args.output.resolve()
    if args.cold:
        cold(output, args.cold); return
    output.mkdir(parents=True, exist_ok=False)
    wb = Workbench(output/'origin')
    try:
        sources, doc = fixture(wb)
        doc, result, job = evaluate(wb, doc)
        transfer = inspect_transfer(wb, doc['id'], job, 'TtoU', 0)
        evidence = {'document_id': doc['id'], 'job_id': job, 'result_sha256': canonical_hash(result),
            'files': hashes(wb, doc, job), 'original_run': doc['runs'][0],
            'original_attempt_id': result['stages'][0]['attempt_id'], 'transfer_rows': transfer['rows'],
            'attempts': [canonical_hash(evaluation_stage_result(wb, doc['id'], job, s['attempt_id'])) for s in result['stages']]}
        save_json(output/'evidence.json', evidence)
        with no_execution(wb): save_json(output/'first.json', publish(wb, [*sources, doc], output/'copy-1'))
    finally:
        closed = wb.shutdown(); assert closed['joined'] and not closed['pending']
    (output/'origin').rename(output/'origin-preserved')
    for phase in (1, 2):
        if phase == 2: (output/'copy-1').rename(output/'copy-1-preserved')
        completed = subprocess.run([sys.executable, '-m', 'examples.portable_evaluation_public',
            '--output', str(output), '--cold', str(phase)], capture_output=True, encoding='utf-8', timeout=150,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        (output/f'process-{phase}.log').write_text(completed.stdout+completed.stderr, encoding='utf-8')
        assert completed.returncode == 0, completed.stdout+completed.stderr
    record = {'status': 'PASS', 'original_coupled_jobs': 1, 'explicit_local_jobs': 1,
        'local_reused_prefix_stages': 1, 'copy_read_edit_save_recopy_jobs': 0, 'provider_calls': 0,
        'native_CAD_Post': 'NOT_RUN', 'engineering_release': 'NOT_RELEASED'}
    save_json(output/'result.json', record); print(json.dumps(record), flush=True)


if __name__ == '__main__': main()
