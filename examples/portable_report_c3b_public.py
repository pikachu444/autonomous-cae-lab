"""Report C3B public cold-process workflow on actual existing owners.

Run after applying both patches to the pinned repository:
  python -m examples.portable_report_c3b_public --output <NEW DIRECTORY>

Real Data imports/Report commands; image receipt is the repository's explicit
SCRIPTED fixture, NOT FreeCAD/ParaView or an AI/solver execution. Only directories
created by this example are removed. Child stdout/stderr and witness are retained.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

from caelab.connection_graph import saved_reference
from caelab.evaluation import file_hash
from caelab.portable_project import create_copy, inspect_copy, open_project, verify_project
from caelab.portable_project_report import asset_name
from caelab.report_image import apply_binding, validate_content
from caelab.storage import canonical_hash, load_json, save_json
from caelab.workbench import Workbench
from examples.portable_connection_public import command, create_public_store, save

_CREATED_ROOT = None


def section(binding, identifier):
    return {'id': identifier, 'title': '공개 공학 근거', 'text': '판단: UNKNOWN. 후속 실행은 아직 하지 않았습니다.',
            'include': True, 'table': True, 'curve': False, 'asset': deepcopy(binding)}


def _close(wb):
    state = wb.shutdown()
    if not state['joined'] or state['pending']:
        raise RuntimeError('Example-owned Workbench did not finish shutdown: ' + repr(state))


def _tree(folder):
    return {p.relative_to(folder).as_posix(): file_hash(p) for p in sorted(folder.rglob('*'))
            if p.is_file() and p.relative_to(folder).as_posix() != 'workbench/controller.lock'}


def _remove_created(root, target):
    """Remove only an exact synthetic directory created by this invocation."""
    base, resolved = Path(root).resolve(strict=True), Path(target).resolve(strict=True)
    allowed = {base / name for name in ('원 보관소', '원 외부 자료', '새 위치 한글 공백 사본')}
    if base != _CREATED_ROOT or resolved not in allowed or Path(target).is_symlink():
        raise ValueError('Refuse removal outside this invocation\'s exact synthetic paths')
    shutil.rmtree(resolved)


def _publish(wb, documents, target, command_id):
    plan = inspect_copy(wb, documents, draft_policy='acknowledged')
    if plan['status'] != 'READY':
        raise RuntimeError(plan)
    return create_copy(wb, plan, target, approved=True, command_id=command_id, session_id=wb.session_id)


def _scripted_image(root):
    # Exact shipped fixture, not a new provider, native receipt broker or store.
    path = Path(__file__).resolve().parents[1] / 'tests' / 'report_image_fixture.py'
    spec = importlib.util.spec_from_file_location('_report_c3b_public_fixture', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.fixture(root)


def prepare(root):
    source, external = root / '원 보관소', root / '원 외부 자료'
    wb, originals = create_public_store(source)
    try:
        material = originals['material']
        report = wb.document_open(kind='report', title='이동 보고서 공개 예제')
        first = wb.report_capture(report['id'], saved_reference(material))
        raw_path = wb.report_documents._folder(report['id']) / asset_name(first)
        # Preserve legal but noncanonical whitespace bytes across both copies.
        raw_path.write_text(json.dumps(load_json(raw_path), ensure_ascii=False) + '\n\n', encoding='utf-8')
        draft = deepcopy(report['draft']); draft['sections'] = [section(first, 'Einput')]
        report = save(wb, command(wb, report, 'report.update', {'draft': draft}))
        report_folder = wb.report_documents._folder(report['id'])
        original_document = report_folder / 'revisions' / report['saved_revision'] / 'document.json'
        original_document_sha = file_hash(original_document)
        changed = deepcopy(material['draft']); changed['settings']['parameters']['E'] += 10
        material = save(wb, command(wb, material, 'material.update', {'draft': changed}))
        second = wb.report_capture(report['id'], saved_reference(material))
        result_ref = {'kind': 'result', **wb.document_result_reference(originals['data']['id'], originals['success_job']['id'])}
        result_ref['selection'] = {'responses': ['stress'], 'rows': [1, 3]}
        result = wb.report_capture(report['id'], result_ref)
        scripted = _scripted_image(external)
        image = wb.report_documents.capture_image(report['id'], scripted['command'])
        image_content = wb.report_documents.asset(report['id'], image)['content']
        png = validate_content(image_content)
        draft = deepcopy(report['draft'])
        draft['sections'] = [section(second, 'Einput'), section(result, 'Eresult')]
        draft = apply_binding(draft, image, image_content)
        draft['title'] = '저장본 이후의 acknowledged 편집'
        report = command(wb, report, 'report.update', {'draft': draft})
        witness = {'original_report_id': report['id'], 'original_saved_document_sha256': original_document_sha,
            'original_paths': [str(source), str(external)],
            'asset_raw_sha256': {b['id']: file_hash(report_folder / asset_name(b)) for b in (first, second, result, image)},
            'first_asset_id': first['id'], 'png_sha256': hashlib.sha256(png).hexdigest(),
            'frozen': {b['id']: wb.report_documents.asset(report['id'], b) for b in (second, result, image)},
            'native_capture': 'SCRIPTED_CONTRACT_FIXTURE_NOT_NATIVE', 'solver': 'NOT_RUN',
            'ai_provider_calls': 0, 'original_import_states': [originals['success_job']['state'], originals['failure_job']['state']]}
        before = _tree(source)
        receipt = _publish(wb, [report['id'], material['id'], originals['data']['id']], root / '첫 사본', 'Cpublic_report_first')
        assert _tree(source) == before, 'copy mutated the original owner'
        witness['first_receipt'] = receipt
        save_json(root / 'witness.json', witness)
    finally:
        _close(wb)
    _remove_created(root, source)  # Workbench was joined above before removal.
    _remove_created(root, external)
    moved = root / '새 위치 한글 공백 사본'
    (root / '첫 사본').rename(moved)
    return moved


@contextmanager
def cold_guard():
    from caelab import report_image
    calls = []
    def forbidden(*args, **kwargs):
        calls.append('unexpected execution/original native access')
        raise AssertionError(calls[-1])
    with patch.object(Workbench, 'submit', forbidden), patch.object(Workbench, '_execute', forbidden), \
         patch.object(Workbench, 'assistance_call', forbidden), patch.object(report_image, 'verify_origin', forbidden):
        yield calls
    assert not calls


def cold(folder, witness_path, next_copy=None):
    folder = Path(folder)
    witness = load_json(witness_path)
    assert all(not Path(p).exists() for p in witness['original_paths'])
    before = _tree(folder / 'portable')
    with cold_guard() as calls:
        wb = open_project(folder)
        try:
            documents = wb.documents()['documents']
            report = next(doc for doc in documents if doc['kind'] == 'report')
            data = next(doc for doc in documents if doc['kind'] == 'data')
            assert {doc['kind'] for doc in documents} == {'report', 'material', 'data'}
            assert wb.portable_recovery_catalog([report['id']])['archives'] == []
            bindings = [row['asset'] for row in report['draft']['sections']]
            contents = wb.report_content(report['id'], bindings)['assets']
            assert [row['source_status'] for row in contents] == ['AVAILABLE', 'AVAILABLE', 'UNAVAILABLE']
            for binding, content in zip(bindings, contents):
                frozen = witness['frozen'][binding['id']]
                assert content['reference'] == frozen['reference'] and content['content'] == frozen['content']
                assert content['snapshot_status'] == 'AVAILABLE'
            assert contents[-1]['navigation_reference'] is None
            assert hashlib.sha256(validate_content(contents[-1]['content'])).hexdigest() == witness['png_sha256']
            assert contents[-1]['content']['snapshot']['result_status']['execution_status'] == 'UNKNOWN'
            assert {run['retained_state'] for run in data['runs']} == {'SUCCEEDED', 'FAILED'}
            assert wb.document_source_preview(data['id'])['retained']
            draft = deepcopy(report['draft']); draft['title'] = '새 process에서 편집·저장한 보고서'
            draft['sections'][0]['text'] = '현재 판단을 수정했습니다. 원 자료와 원 성공·실패 상태는 그대로입니다.'
            edited = command(wb, report, 'report.update', {'draft': draft})
            undone = command(wb, edited, 'document.undo')
            report = save(wb, command(wb, undone, 'document.redo'))
            assert report['draft'] == draft and not wb.manager.list()
            saved_folder = wb.report_documents._folder(report['id']) / 'revisions' / report['saved_revision']
            hashes = {file_hash(p) for p in (saved_folder / 'portable_execution' / 'report_archive').glob('*.json')}
            assert witness['original_saved_document_sha256'] in hashes
            for asset_id, digest in witness['asset_raw_sha256'].items():
                assert file_hash(saved_folder / 'assets' / (asset_id + '.json')) == digest
            receipt = _publish(wb, [doc['id'] for doc in documents], next_copy, 'Cpublic_report_again') if next_copy else None
            outcome = {'status': 'PASS', 'pid': os.getpid(), 'workspace': str(folder),
                'original_store_and_external_absent': True, 'current_owner_edited_saved': True,
                'undo_redo': 'PASS', 'original_saved_document_bytes': 'PRESERVED',
                'all_A_raw_bytes': 'PRESERVED', 'png_bytes': 'PRESERVED',
                'source_statuses': [row['source_status'] for row in contents],
                'actual_original_import_states': sorted({run['retained_state'] for run in data['runs']}),
                'execution_or_original_native_calls': len(calls), 'next_receipt': receipt,
                'native_capture': witness['native_capture'], 'windows_qt': 'NOT_RUN',
                'engineering_release': 'NOT_RELEASED'}
        finally:
            _close(wb)
    assert _tree(folder / 'portable') == before
    assert verify_project(folder)['status'] == 'READY'
    return outcome


def _child(root, folder, label, next_copy=None):
    args = [sys.executable, '-m', 'examples.portable_report_c3b_public', '--cold', str(folder),
            '--witness', str(root / 'witness.json')]
    if next_copy:
        args += ['--next-copy', str(next_copy)]
    # subprocess.run kills AND waits for this child on timeout. Workbench itself
    # is joined in the child's finally. No caller process/window is targeted.
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
            timeout=45, env={**os.environ, 'PYTHONUTF8': '1'}, check=False)
    except subprocess.TimeoutExpired as error:
        save_json(root / (label + '-timeout.json'), {'status': 'TIMEOUT', 'timeout_seconds': 45,
            'stdout': str(error.stdout), 'stderr': str(error.stderr)})
        raise
    (root / (label + '.stdout.log')).write_text(result.stdout, encoding='utf-8')
    (root / (label + '.stderr.log')).write_text(result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Cold child failed; preserved log: ' + str(root / (label + '.stderr.log')))
    outcome = json.loads(result.stdout)
    save_json(root / (label + '.json'), outcome)
    return outcome


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output'); parser.add_argument('--cold'); parser.add_argument('--witness')
    parser.add_argument('--next-copy')
    args = parser.parse_args(argv)
    if args.cold:
        if not args.witness:
            parser.error('--cold requires --witness')
        print(json.dumps(cold(args.cold, args.witness, args.next_copy), ensure_ascii=False))
        return 0
    if not args.output:
        parser.error('--output is required')
    global _CREATED_ROOT
    root = Path(args.output).resolve(); root.mkdir(parents=False, exist_ok=False)
    _CREATED_ROOT = root
    moved = prepare(root)
    next_copy = root / '재복사 후 독립 작업 사본'
    first = _child(root, moved, 'cold-first', next_copy)
    _remove_created(root, moved)  # First child has finished and joined its owner.
    second = _child(root, next_copy, 'cold-second')
    assert len({os.getpid(), first['pid'], second['pid']}) == 3
    result = {'status': 'PASS', 'parent_pid': os.getpid(), 'child_pids': [first['pid'], second['pid']],
        'original_and_first_copy_deleted': True, 'final_copy': str(next_copy),
        'verified_final_copy': verify_project(next_copy)['status'], 'new_jobs_on_cold': 0,
        'actual_table_import': 'SUCCEEDED_AND_FAILED', 'actual_native': 'NOT_RUN',
        'actual_qt': 'NOT_RUN', 'provider_calls': 0, 'scope': 'REPORT_ENGINEERING_WORKING_COPY_PARTIAL_C3B'}
    save_json(root / 'public-check.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
