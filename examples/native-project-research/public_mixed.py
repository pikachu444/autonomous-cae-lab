"""Move existing native files with real Data/Study/Report owners; no native launch.

Run with --output NEW_FOLDER --native-project EXISTING_PUBLIC.caepre/FCStd.
Only the new example's source store is renamed. Supplied native files stay intact.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from caelab.evaluation import file_hash
from caelab.native_project_inputs import context_from_workbench, register_saved, verify_registered
from caelab.portable_project import inspect_copy, create_copy, verify_project, open_project
from caelab.storage import load_json, save_json


def command(wb, document, operation, arguments=None):
    return wb.document_command(document['id'], operation, arguments or {},
        session_id=wb.session_id, expected_generation=document['generation'])


def saved(wb, document):
    return command(wb, document, 'document.save')['document']


def finished(wb, job):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = wb.manager.status(job['id'])
        if result['state'] in {'SUCCEEDED', 'FAILED', 'CANCELLED'}:
            return result
        time.sleep(.01)
    raise TimeoutError('The owned public table import did not finish')


def create_research(wb, native_references):
    from caelab.study_document import default_draft, reference_error
    from caelab.report_document import default_draft as report_draft
    upload = wb.upload('공개 관측.csv', b'time,force\n0,0\n1,10\n2,20\n')
    draft = {'data_id': upload['id'], 'mapping': {'delimiter': ',', 'skip_header': 1, 'columns': {
        'force': {'column': 1, 'unit': 'N', 'component': 'X', 'location': 'public specimen',
                  'measure': 'force', 'frame': 'declared Cartesian',
                  'axis': {'column': 0, 'name': 'time', 'unit': 's'}}}},
        'test_metadata': {'test_id': 'PUBLIC_SYNTHETIC', 'specimen': '공개 합성 관측',
                          'protocol': '모델과 물리적 대응 미확인', 'temperature': 'UNKNOWN'}}
    data = wb.document_open(kind='data', title='공개 힘 관측', draft=draft)
    success = finished(wb, command(wb, data, 'data.import')['job'])
    assert success['state'] == 'SUCCEEDED'
    invalid = deepcopy(draft); invalid['mapping']['columns']['force']['column'] = 9
    data = command(wb, wb.document_read(data['id']), 'data.update', {'draft': invalid})['document']
    failure = finished(wb, command(wb, data, 'data.import')['job'])
    assert failure['state'] == 'FAILED'  # Real table-column failure, not solver failure.
    data = command(wb, wb.document_read(data['id']), 'data.update', {'draft': draft})['document']
    data = saved(wb, data)
    exact = wb.document_result_reference(data['id'], success['id'])
    reference = {'kind': 'result', **exact, 'response': 'force', 'selection': {'responses': ['force']}}
    study_draft = default_draft()
    study_draft['question'] = '관측과 모델을 대조하려면 어떤 추가 조건을 확인해야 하나요?'
    study_draft['hypotheses'] = [{'id': 'Hconditions', 'title': '비교 조건 확인',
        'statement': '모델과 관측의 물리적 대응은 아직 확인하지 않았다.', 'status': 'UNKNOWN'}]
    study_draft['evidence'] = [{'id': 'Eforce', 'label': '공개 힘 관측 (N)', 'kind': 'result',
        'reference': reference, 'note': '합성 원값과 실패 기록을 보존한다.'}]
    for index, native_reference in enumerate(native_references):
        issue = reference_error(native_reference)
        if issue: raise ValueError('이 모델 저장본을 연구 근거로 연결할 수 없습니다: ' + issue)
        forged = {**native_reference, 'snapshot_sha256': '0' * 64}
        try:
            wb.research_reference(forged)
        except ValueError:
            pass
        else:
            raise AssertionError('A different native snapshot was accepted as the selected source')
        label = 'FreeCAD 모델' if native_reference['kind'] == 'native_pre' else 'ParaView 결과'
        study_draft['evidence'].append({'id': 'Enative' + str(index), 'label': label,
            'kind': native_reference['kind'], 'reference': deepcopy(native_reference),
            'note': '저장본 전체의 참조이며 관측과의 물리적 대응을 승인하지 않는다.'})
    study = saved(wb, wb.document_open(kind='study', title='모델과 관측 검토', draft=study_draft))
    report = wb.document_open(kind='report', title='검토 기록')
    asset = wb.report_capture(report['id'], reference)
    report_body = report_draft()
    report_body['sections'] = [{'id': 'Rforce', 'title': '공개 관측과 확인할 조건',
        'text': '힘의 단위는 N, 시각의 단위는 s이다. 모델과의 물리적 대응과 강도는 미확인이다.',
        'include': True, 'table': True, 'curve': True, 'asset': asset}]
    for index, native_reference in enumerate(native_references):
        native_asset = wb.report_capture(report['id'], native_reference)
        label = 'FreeCAD 모델' if native_reference['kind'] == 'native_pre' else 'ParaView 결과'
        report_body['sections'].append({'id': 'Rnative' + str(index), 'title': label,
            'text': '선택한 저장 모델의 원정보를 유지한다.', 'include': True,
            'table': False, 'curve': False, 'asset': native_asset})
    report = command(wb, report, 'report.update', {'draft': report_body})['document']
    report = saved(wb, report)
    values = wb.document_result(data['id'], success['id'], selection={'responses': ['force']})
    frozen_assets = {row['asset']['id']: file_hash(wb.report_documents._folder(report['id']) /
        ('assets/' + row['asset']['id'] + '.json')) for row in report_body['sections']}
    return {'documents': [data['id'], study['id'], report['id']], 'native_references': native_references,
        'frozen_assets': frozen_assets,
        'result_job': success['id'], 'values': values['responses']['force']['value'],
        'retained_runs': [{k: r.get(k) for k in ('job_id', 'retained_state', 'retained_error')} for r in data['runs']],
        'research_native_link': 'SUPPORTED_BY_DOMAIN', 'engineering_release': 'NOT_RELEASED'}


def copy_mixed(wb, documents, native_references, destination, command_id):
    selection = [*documents, *[{'native': ref, 'copy_intent': 'complete', 'working_target': True}
        for ref in native_references]]
    inspection = inspect_copy(wb, selection)
    assert inspection['status'] == 'READY', inspection.get('issues')
    create_copy(wb, inspection, destination, approved=True, command_id=command_id, session_id=wb.session_id)
    checked = verify_project(destination)
    assert checked['status'] == 'READY' and checked['native_projects']
    return checked


def deny_sources(paths):
    roots = [Path(p).resolve() for p in paths]
    def audit(event, arguments):
        if event not in {'open', 'os.listdir', 'os.scandir'} or not arguments:
            return
        value = arguments[0]
        if not isinstance(value, (str, bytes, os.PathLike)):
            return
        path = Path(os.fsdecode(value)).resolve()
        if any(path == root or path.is_relative_to(root) for root in roots):
            raise PermissionError('The original store/native source is blocked in this cold process')
    sys.addaudithook(audit)


def read_research_sources(wb, documents, baseline):
    references = wb.study_references(documents['study']['id'])['references']
    assert references and all(row['status'] == 'AVAILABLE' for row in references), references
    bindings = [row['asset'] for row in documents['report']['draft']['sections'] if row.get('asset')]
    assets = wb.report_content(documents['report']['id'], bindings)['assets']
    assert len(assets) == len(bindings)
    assert all(row['source_status'] == 'AVAILABLE' for row in assets), assets
    native_rows = [row for row in references if row.get('kind') in {'native_pre', 'native_post'}]
    assert len(native_rows) == len(baseline['native_references'])
    native_assets = [row for row in assets if row['reference']['kind'] in {'native_pre', 'native_post'}]
    assert len(native_assets) == len(baseline['native_references'])
    assert all(row['navigation_status'] == 'VERIFIED_TYPED_SOURCE' for row in native_assets)
    assert {row['id']: file_hash(wb.report_documents._folder(documents['report']['id']) /
        ('assets/' + row['id'] + '.json')) for row in assets} == baseline['frozen_assets']


def cold_edit(first, second, baseline, denied, output):
    deny_sources(denied)
    checked = verify_project(first)
    assert checked['status'] == 'READY'
    wb = open_project(first)
    try:
        assert not wb.manager.list() and wb._assistance is None
        documents = {d['kind']: d for d in wb.documents()['documents']}
        assert set(documents) == {'data', 'study', 'report'}
        data = documents['data']
        assert wb.document_result(data['id'], baseline['result_job'], selection={'responses': ['force']})['responses']['force']['value'] == baseline['values']
        assert [{k: r.get(k) for k in ('job_id', 'retained_state', 'retained_error')} for r in data['runs']] == baseline['retained_runs']
        read_research_sources(wb, documents, baseline)
        for kind in ('data', 'study', 'report'):
            document = wb.document_read(documents[kind]['id']); draft = deepcopy(document['draft'])
            if kind == 'data': draft['test_metadata']['protocol'] = '사본에서 관측 조건 검토'
            elif kind == 'study': draft['question'] = '사본에서 추가 관측과 모델 조건을 검토합니다.'
            else: draft['title'] = '사본의 검토 기록'
            document = command(wb, document, kind + '.update', {'draft': draft})['document']
            saved(wb, document)
        current_references = []
        for target in checked['native_projects']:
            head = load_json(first / target['head_file'])
            verified = verify_registered(context_from_workbench(wb), head['reference'], full=True)
            original = next(row for row in baseline['native_references']
                if row['snapshot_sha256'] == verified.snapshot['snapshot_sha256'])
            assert verified.reference['document_id'] == original['document_id']
            assert verified.reference['saved_revision'] == original['saved_revision']
            assert verified.reference['input_id'] != original['input_id']
            current_references.append(head['reference'])
        second_checked = copy_mixed(wb, [d['id'] for d in documents.values()], current_references, second, 'CRecopyMixed')
        assert not ({row['working_document_id'] for row in second_checked['native_projects']} &
                    {row['working_document_id'] for row in checked['native_projects']})
        assert not wb.manager.list() and wb._assistance is None
        second_wb = open_project(second)
        try:
            second_documents = {d['kind']: d for d in second_wb.documents()['documents']}
            read_research_sources(second_wb, second_documents, baseline)
            assert not second_wb.manager.list() and second_wb._assistance is None
        finally:
            assert second_wb.shutdown()['joined']
        save_json(output, {'status': 'PASSED', 'pid': os.getpid(), 'read_edit_save': True,
            'study_report_sources_available': True,
            'original_sources_blocked': True, 'new_jobs': 0, 'solver_provider_native_launch': 'NOT_RUN',
            'native_snapshot_unchanged': True, 'states': [r['retained_state'] for r in data['runs']],
            'native_kinds': sorted(row['kind'] for row in baseline['native_references']),
            'frozen_assets_unchanged': True,
            'different_snapshot_rejected': True,
            'research_native_link': baseline['research_native_link'], 'verification': second_checked['status']})
    finally:
        assert wb.shutdown()['joined']


def run(output, native_project, *, post_project=None, post_root=None):
    from caelab.workbench import Workbench
    output, native_project = Path(output).absolute(), Path(native_project).resolve(strict=True)
    if output.exists(): raise FileExistsError('Choose a new output folder')
    output.mkdir(parents=True)
    originals = [native_project] + ([Path(post_project).resolve(strict=True)] if post_project else [])
    original_pins = {str(path): file_hash(path) for path in originals}
    roots = {'CAD': str(native_project.parent)}
    if post_project:
        roots['Post'] = str(Path(post_root).resolve(strict=True) if post_root else originals[1].parent)
    source, blocked = output / '예제 원본', output / '차단한 예제 원본'
    first, second = output / '연구와 모델 사본', output / '다시 옮긴 사본'
    wb = Workbench(source, configuration={'input_roots': roots, 'workers': 1})
    try:
        admitted = register_saved(context_from_workbench(wb), {'mode': 'selected_file', 'native_kind': 'pre',
            'root_id': 'CAD', 'relative': native_project.name}, command_id='CRegisterPublicModel')
        references = [admitted['reference']]
        if post_project:
            admitted_post = register_saved(context_from_workbench(wb), {'mode': 'selected_file',
                'native_kind': 'post', 'root_id': 'Post',
                'relative': originals[1].relative_to(Path(roots['Post'])).as_posix()}, command_id='CRegisterPublicPost')
            references.append(admitted_post['reference'])
        baseline = create_research(wb, references)
        copy_mixed(wb, baseline['documents'], references, first, 'CCopyMixed')
        save_json(output / 'baseline.json', baseline)
    finally:
        assert wb.shutdown()['joined']
    assert source.parent == output and blocked.parent == output and not blocked.exists()
    source.rename(blocked)  # Only the fresh example-owned store, never supplied native files.
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--cold', str(first),
        '--second', str(second), '--baseline', str(output / 'baseline.json'), '--receipt', str(output / 'cold.json'),
        '--deny', str(source), '--deny', str(blocked),
        *[arg for root in roots.values() for arg in ('--deny', root)]],
        capture_output=True, text=True, encoding='utf-8', timeout=90)
    (output / 'cold.stdout.log').write_text(child.stdout, encoding='utf-8')
    (output / 'cold.stderr.log').write_text(child.stderr, encoding='utf-8')
    if child.returncode: raise RuntimeError('The cold mixed check failed; see cold.stderr.log')
    assert all(file_hash(Path(path)) == pin for path, pin in original_pins.items())
    result = load_json(output / 'cold.json')
    assert result['pid'] != os.getpid() and verify_project(second)['status'] == 'READY'
    save_json(output / 'receipt.json', {**result, 'first': str(first), 'second': str(second),
        'native_source_unchanged': True, 'native_source_sha256': original_pins})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path); parser.add_argument('--native-project', type=Path)
    parser.add_argument('--post-project', type=Path); parser.add_argument('--post-root', type=Path)
    parser.add_argument('--cold', type=Path); parser.add_argument('--second', type=Path)
    parser.add_argument('--baseline', type=Path); parser.add_argument('--receipt', type=Path)
    parser.add_argument('--deny', action='append', default=[])
    args = parser.parse_args()
    if args.cold:
        cold_edit(args.cold, args.second, load_json(args.baseline), args.deny, args.receipt)
    else:
        if not args.output or not args.native_project: parser.error('--output and --native-project are required')
        run(args.output, args.native_project, post_project=args.post_project, post_root=args.post_root)
        print('연구 문서와 모델 사본을 저장했습니다. 원본 없이 연구 문서 편집과 재복사를 확인했습니다.')
