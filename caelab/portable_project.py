"""Portable Data/Material/Numerical/Report working copies using existing document owners.

Public commands: inspect_copy, create_copy, verify_project, open_project,
repair_asset and extract_project. Inspection is read-only. Creation copies only
explicitly selected saved bases, acknowledged working states and declared assets.
No new store/controller, input registration, directory crawling or execution.

Original revision files (including original inputs, failures and metadata) are
kept byte-for-byte under portable/originals. The working projection gets new
owner/revision/input identities and remaps only the documented typed fields.
Solver result files/arrays remain byte-identical. This separation prevents a
copied result from being relabelled as a newly executed calculation.
"""
from __future__ import annotations
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import asdict
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
import uuid

from .connection_graph_refs import (TypedReference, comparison_references,
                                    document_references, draft_references, replace_at)
from .evaluation import file_hash, read_result
from .portable_project_io import (Issue, PortableProjectError, MAX_BYTES, MAX_FILES,
    copy_verified, extract_archive, fail, fingerprint_file, inside, json_file,
    no_links, relative_name, verify_inventory)
from .storage import canonical_hash, check_id, load_json, save_json, utc_now

FORMAT = 'caelab.portable-project/1'
MANIFEST = 'portable-project.json'
SUPPORTED = {'data', 'material', 'numerical', 'report', 'study', 'expert', 'pde', 'simulation', 'evaluation'}
_PREFIX = {'data': 'T', 'material': 'M', 'numerical': 'N', 'report': 'B', 'study': 'S', 'expert': 'X', 'pde': 'Q', 'simulation': 'V', 'evaluation': 'E'}
_DENIED_NAMES = {'.env', 'credentials', 'credentials.json', 'token', 'token.json',
                 'id_rsa', 'id_ed25519', 'operator.json', 'service.json'}


def _research_dependencies():
    # Native-only file work must run in the existing FreeCAD/ParaView Python
    # without importing research owners, JobManager or its filelock dependency.
    global SnapshotReader, is_acknowledged_container
    global AcknowledgedReader, WORKING, POLICIES, CAPSULE_CONTRACT, virtual_revision
    from .connection_graph import SnapshotReader, is_acknowledged_container
    from .portable_project_drafts import AcknowledgedReader, WORKING, POLICIES, CAPSULE_CONTRACT, virtual_revision


def _asset_name(name: str, kind: str | None = None) -> str:
    relative_name(name)
    parts = Path(name).parts
    if any(part.lower() in _DENIED_NAMES for part in parts):
        fail('PRIVATE_ASSET_REFUSED', name, '인증/환경설정 파일은 자동 수집하지 않습니다.', '인증/환경설정 자료를 제외하고 선택 목록을 다시 확인하세요. 공학 자료의 공개 여부는 제한하지 않습니다.')
    if kind == 'evaluation' and name == 'stage_inputs.json':
        return name
    if kind == 'expert':
        from .portable_research_team import is_team_asset
        if is_team_asset(name):
            return name
    if kind == 'report':
        from .portable_project_report import ASSET
        if ASSET.fullmatch(name):
            return name
    if name != 'document.json' and parts[0] not in {'sources', 'inputs', 'jobs', 'results', 'comparisons', 'candidate_evidence', 'portable_execution'}:
        fail('UNSUPPORTED_ASSET', name, '이 owner 자료 형식은 작업 사본 대상으로 지원하지 않습니다.', '원문서에 보존하고 root 통합 계약을 추가하세요.')
    return name


def _selections(reader: SnapshotReader, selections: list[str | dict], draft_policy='acknowledged') -> list[dict]:
    if not isinstance(selections, list) or not 1 <= len(selections) <= 128:
        raise ValueError('문서를 1~128개 선택하세요.')
    result, seen = [], set()
    for value in selections:
        value = {'document_id': value} if isinstance(value, str) else deepcopy(value)
        if not isinstance(value, dict) or set(value) - {'document_id', 'saved_revision'}:
            raise ValueError('문서와 선택할 저장 개정만 지정하세요.')
        identifier = check_id(value['document_id'])
        if identifier in seen:
            raise ValueError('한 원문서에는 하나의 작업 시작 개정만 선택하세요.')
        seen.add(identifier)
        current = reader.current(identifier)
        if current['kind'] not in SUPPORTED:
            fail('OWNER_NOT_SUPPORTED', identifier, '현재 작업 사본은 Data, Material, Numerical, PDE, Simulation, Evaluation, Study, Expert와 Report를 지원합니다.',
                 '다른 도구의 원자료는 원문서에 그대로 보존하세요.', identifier)
        revision = value.get('saved_revision') or current.get('saved_revision')
        if draft_policy == 'acknowledged' and revision != current.get('saved_revision'):
            fail('DRAFT_BASE_MISMATCH', identifier, '현재 초안의 저장 base와 선택한 개정이 다릅니다.',
                 '현재 저장 base를 선택하거나 이전 개정은 저장본만 복사로 명시하세요.', identifier)
        if revision and is_acknowledged_container(reader.revision(identifier, revision)):
            fail('SNAPSHOT_NOT_SAVED', identifier, '초안 보존 컨테이너는 저장 개정이 아닙니다.',
                 '실제 저장 개정을 선택하거나 현재 acknowledged 초안을 포함하세요.', identifier)
        if not revision and draft_policy == 'saved_only':
            fail('SAVE_REQUIRED', identifier, '선택한 문서에 저장 개정이 없습니다.', '원문서에서 저장한 뒤 다시 선택하세요.', identifier)
        result.append({'document_id': identifier, 'saved_revision': check_id(revision) if revision else None})
    return sorted(result, key=lambda r: r['document_id'])


def _internal_revisions(document: dict):
    for source in document.get('retained_inputs', {}).values():
        yield source['revision']
    for run in document.get('runs', []):
        for key in ('retained_record', 'retained_result'):
            if run.get(key):
                yield run[key]['revision']
        args = run.get('arguments', {})
        sources = [args.get('source_ref'), *args.get('calibration_sources', [])]
        for source in sources:
            if isinstance(source, dict) and source.get('kind') == 'retained_data_input':
                # Data's source_ref includes its owner, never an arbitrary path.
                if source.get('document_id') == document['id']:
                    yield source['revision']
    for row in [*document.get('candidate_evidence', []), *document.get('portable_capture_history', [])]:
        if row.get('retained_revision') or row.get('revision'):
            yield row.get('retained_revision') or row['revision']
    for row in document.get('comparisons', []):
        if row.get('retained_revision'):
            yield row['retained_revision']


def _unpinned_job_inputs(document: dict):
    """Known legacy engine job links need typed owner bindings before copying.

    This is a deny guard on the existing contract, not JSON/ID discovery. Inline
    numeric inputs are not paths and remain valid. No source-directory scan.
    """
    if document['kind'] != 'numerical':
        return
    drafts = [('draft', document['draft'])]
    drafts += [('runs/' + str(i) + '/draft', r['draft']) for i, r in enumerate(document.get('runs', []))]
    for stack in ('_undo', '_redo'):
        drafts += [(stack + '/' + str(i), d) for i, d in enumerate(document.get(stack, []))]
    for location, draft in drafts:
        if draft.get('mode') != 'request':
            continue
        inputs = [(location + '/request/inputs', draft.get('request', {}).get('inputs', {}))]
        inputs += [(location + '/method_inputs/' + method, value) for method, value in draft.get('method_inputs', {}).items()]
        for path, value in inputs:
            # These actual Workbench._settings contracts consume a global
            # registered input/design, NOT an owner-retained Data result. Merely
            # copying a Plan (even alongside a Data doc) cannot rebind them.
            if value.get('backend') in {'files.table', 'structure.calculix.frozen', 'structure.codeaster.frozen', 'structure.calculix.contact', 'structure.calculix.pretension',
                    'structure.calculix.shell', 'structure.calculix.shell.composite', 'structure.calculix.beam', 'structure.calculix.design'}:
                yield path + '/settings'
            for field in ('job_id', 'training_job', 'holdout_job', 'batch_job'):
                if field in value:
                    yield path + '/' + field


def _inspect_research_copy(workbench, selections: list[str | dict], *, draft_policy='acknowledged', recovery_archives=None) -> dict[str, Any]:
    """List pinned files and missing dependencies without saving or collecting.

    The user reviews this exact inventory before approving creation. A selected
    saved base and the acknowledged working state remain separate. Excluding
    drafts requires explicit saved_only. Missing files block publication with
    locations/recovery; no implicit save, apply, execution or UI collection.
    """
    _research_dependencies()
    if draft_policy not in POLICIES:
        raise ValueError('초안 포함(acknowledged) 또는 저장본만(saved_only)을 명시하세요.')
    reader = AcknowledgedReader(workbench)
    issues: list[Issue] = []
    warnings: list[dict] = []
    native_references = []
    try:
        chosen = _selections(reader, selections, draft_policy)
    except PortableProjectError as error:
        return {**error.as_dict(), 'format': FORMAT, 'service_session_id': workbench.session_id}
    except (ValueError, KeyError, TypeError, OSError) as error:
        problem = PortableProjectError(Issue('SELECTION_UNAVAILABLE', str(workbench.workspace), str(error),
            '문서의 정확한 저장 개정과 필수 자료를 확인한 뒤 다시 선택하세요.'))
        return {**problem.as_dict(), 'format': FORMAT, 'service_session_id': workbench.session_id}
    selected = {row['document_id']: row['saved_revision'] for row in chosen}
    reader.included = set(selected) if draft_policy == 'acknowledged' else set()
    queue = [(i, r) for i, r in selected.items() if r]
    queue += [(i, WORKING) for i in sorted(reader.included)]
    visited: dict[tuple[str, str], dict] = {}
    inventory: dict[str, dict] = {}
    summaries = []
    pins = []
    for identifier, revision in selected.items():
        current = reader.current(identifier)
        pointer = reader.owner(identifier)._folder(identifier) / 'document.json'
        pins.append({'document_id': identifier, 'generation': current['generation'],
                     'input_revision': current['input_revision'], 'draft_sha256': canonical_hash(current['draft']),
                     'pointer_sha256': file_hash(pointer) if pointer.is_file() else None,
                     'acknowledged_sha256': canonical_hash(current) if draft_policy == 'acknowledged' else None})
        if draft_policy == 'saved_only' and reader.owner(identifier)._fingerprint(current) != current.get('_saved_fingerprint'):
            warnings.append({'code': 'UNSAVED_DRAFT_EXCLUDED', 'document_id': identifier,
                             'message': '현재 미저장 편집은 포함하지 않습니다. 선택한 저장 개정만 복사합니다.'})
        summaries.append({'document_id': identifier, 'saved_revision': revision,
                          'title': current['title'], 'kind': current['kind'],
                          'draft_included': draft_policy == 'acknowledged'})
    from .portable_project_recovery import collect as collect_recovery
    recovery = {'recovery_selections': [], 'recovery_archives': [], 'recovery_files': []}
    try:
        recovery = collect_recovery(workbench, selected, recovery_archives)
        from .portable_recovery_dependencies import seed_dependencies
        queue += seed_dependencies(reader, selected, recovery)
    except PortableProjectError as error:
        issues.extend(error.issues)
    except (ValueError, OSError, KeyError, TypeError) as error:
        issues.append(Issue('RECOVERY_ARCHIVE_UNAVAILABLE', str(workbench.workspace), str(error),
            '원문서의 보관 자료와 receipt를 확인하세요. 원문은 변경하지 않았습니다.'))
    while queue:
        identifier, revision = queue.pop(0)
        if (identifier, revision) in visited:
            continue
        try:
            document = reader.revision(identifier, revision)
            visited[(identifier, revision)] = document
            for position in _unpinned_job_inputs(document):
                issues.append(Issue('EXTERNAL_INPUT_CONTRACT' if position.endswith('/settings') else 'UNPINNED_JOB_INPUT',
                    identifier + '/' + position,
                    '보관소 등록 파일/설계 또는 소유자 없는 계산 입력은 사본에 자동 포함하지 않습니다.',
                    'Data 가져오기 결과를 정확한 저장 참조로 선택하세요. Native 입력은 해당 팀의 별도 보존 계약이 필요합니다.', identifier))
            folder = reader.revision_folder(identifier, revision)
            if virtual_revision(revision):
                for entry in reader.working_files[identifier]:
                    if entry['saved_revision'] != revision:
                        continue
                    if not entry.get('archive_only'):
                        _asset_name(entry['asset'], document['kind'])
                    # The same declared source may be used by multiple snapshots.
                    inventory[canonical_hash([identifier, revision, entry['asset']])] = deepcopy(entry)
            else:
                record = json_file(folder / 'revision.json')
                entries = [*record['files'], {'path': 'revision.json', 'sha256': file_hash(folder / 'revision.json')}]
                for item in entries:
                    name = item['path']
                    if name != 'revision.json':
                        _asset_name(name, document['kind'])
                    source = inside(folder, name)
                    identity = fingerprint_file(source)
                    if identity['sha256'] != item['sha256']:
                        fail('SOURCE_CHANGED', source, '저장 개정의 파일 내용이 다릅니다.', '같은 원본을 복구하고 다시 확인하세요.', identifier)
                    relative = source.relative_to(workbench.workspace).as_posix()
                    inventory[canonical_hash([identifier, revision, name])] = {'path': relative, **identity,
                        'document_id': identifier, 'saved_revision': revision, 'asset': name}
            for old_revision in _internal_revisions(document):
                queue.append((identifier, check_id(old_revision)))
            if document.get('unresolved_inputs'):
                for data_id in document['unresolved_inputs']:
                    issues.append(Issue('UNRETAINED_SOURCE', str(workbench.root / 'inputs' / str(data_id)),
                        '원자료가 이 저장 개정에 보존되지 않았습니다.',
                        'Data에서 원파일을 명시적으로 다시 선택/가져온 뒤 저장하고 새 사본을 만드세요.', identifier))
            if document['kind'] == 'data':
                # Reuse Data's exact receipt/bytes validation; never search the
                # source filesystem or fall back to the global input registry.
                for data_id in document.get('retained_inputs', {}):
                    if document['retained_inputs'][data_id]['revision'] != WORKING:
                        reader.owner(identifier)._retained_source(document, data_id)
                data_id = document['draft'].get('data_id')
                if data_id and data_id not in document.get('retained_inputs', {}):
                    issues.append(Issue('UNRETAINED_SOURCE', str(folder / 'sources' / data_id),
                        '선택한 Data 원자료가 저장 개정에 없습니다.', '원파일을 명시적으로 선택한 뒤 원문서를 저장하세요.', identifier))
            for run in document.get('runs', []):
                if document['kind'] != 'expert' and (selected[identifier] == revision or revision == WORKING) and not run.get('retention_complete'):
                    issues.append(Issue('RUN_NOT_RETAINED', str(folder / 'jobs' / (run['job_id'] + '.json')),
                        '진행 중이거나 완전하게 보존하지 않은 계산은 작업 사본으로 확정할 수 없습니다.',
                        '계산 종료/취소를 확인하고 원문서를 저장한 뒤 다시 시도하세요.', identifier))
                if run.get('retained_record'):
                    reader.job(document, run)
                if run.get('retained_result'):
                    reader.result(document, run, metadata_only=True)
            if document['kind'] in {'pde', 'simulation'}:
                from .portable_project_physics import inspect_document as inspect_physics
                inspect_physics(reader, document)
            if document['kind'] == 'evaluation':
                from .portable_project_evaluation import inspect_document as inspect_evaluation
                inspect_evaluation(reader, document)
            if document['kind'] == 'report':
                from .portable_project_report import inspect_document
                inspect_document(reader, document, revision)
            from .portable_project_evidence import validate_document_evidence
            validate_document_evidence(reader, document)
            from .portable_research_knowledge import collect_document
            from .portable_research_owner import extra_references, replay, current_folder
            if document['kind'] in {'study', 'expert'}:
                archive_root = (current_folder(reader.owner(identifier)._folder(identifier), document)
                    if virtual_revision(revision) else folder)
                replay(archive_root, document)
            collect_document(reader, document, revision=revision)
            refs = [*document_references(document, include_history=True), *comparison_references(document),
                    *extra_references(document)]
            for typed in refs:
                if typed.value.get('kind') in {'native_pre', 'native_post'}:
                    native_references.append(deepcopy(typed.value))
                    continue
                if (typed.value.get('kind') == 'knowledge'
                        or typed.value.get('paper_id') and not typed.value.get('document_id')):
                    continue  # Exact local/public archive closure was checked above.
                if document['kind'] == 'expert':
                    from .portable_research_owner import inspection_reference
                    typed = inspection_reference(archive_root, document, typed)
                target = typed.document_id
                if document['kind'] == 'report':
                    from .portable_project_report import can_navigate
                    if not can_navigate(typed.value, selected):
                        warnings.append({'code': 'REPORT_FROZEN_ONLY', 'document_id': identifier,
                            'path': '/'.join(str(p) for p in typed.path),
                            'message': '검증된 보고서 보존본은 포함합니다. 이 원자료의 현재 탐색은 연결하지 않습니다.'})
                        continue
                location = identifier + '/' + '/'.join(str(p) for p in typed.path)
                if not target or target not in selected:
                    issues.append(Issue('DOCUMENT_NOT_SELECTED', location,
                        '연결된 원문서가 사본 대상에 없습니다: ' + str(target),
                        '해당 문서를 포함 목록에서 명시적으로 선택하세요. 자동으로 수집하지 않습니다.', identifier))
                    continue
                resolved = reader.resolve(typed)
                exact = resolved['exact_reference']
                if not exact:
                    issues.append(Issue('EXTERNAL_REFERENCE', location, '외부 자료를 사본 내부 자료로 표시할 수 없습니다.',
                                        '지원되는 정확한 저장 원문서를 명시적으로 선택하세요.', identifier))
                    continue
                if exact.get('saved_revision'):
                    queue.append((target, exact['saved_revision']))
                elif exact.get('kind') == 'result':
                    head = reader.revision(target, WORKING if target in reader.included else selected[target])
                    run = reader.run(head, exact['job_id'])
                    if any(run.get(k) != exact[k] for k in ('input_revision', 'input_sha256')):
                        raise ValueError('선택한 사본 시작 개정에 필요한 결과가 없습니다.')
                    for key in ('retained_record', 'retained_result'):
                        if run.get(key):
                            queue.append((target, run[key]['revision']))
        except PortableProjectError as error:
            issues.extend(error.issues)
        except (ValueError, OSError, KeyError, TypeError) as error:
            issues.append(Issue('REVISION_UNAVAILABLE', str(reader.owner(identifier)._folder(identifier) / 'revisions' / revision),
                                str(error), '정확한 저장 원본을 복구하거나 원문서에서 새 저장 개정을 선택하세요.', identifier))
    files = sorted(inventory.values(), key=lambda r: r['path'])
    from .portable_research_knowledge import reviewed, reviewed_literature
    knowledge = reviewed(reader)
    literature = reviewed_literature(reader)
    knowledge_files = {row['path']: row for record in [*knowledge, *literature] for row in record['files']}
    total = sum(row['bytes'] for row in files) + sum(row['bytes'] for row in knowledge_files.values())
    recovery_bytes = sum(row['bytes'] for row in recovery['recovery_files'])
    report_ids = {row['document_id'] for row in summaries if row['kind'] in {'report', 'study', 'expert'}}
    report_archive_files = [row for row in files if row['document_id'] in report_ids]
    # Raw owner archives may also retain an acknowledged layer's saved base.
    # This conservative allowance supplements (never raises) the existing caps.
    report_archive_bytes = sum(row['bytes'] for row in report_archive_files)
    if (len(files) * 2 + len(knowledge_files) * 2 + len(recovery['recovery_files']) + len(report_archive_files) * 2 > MAX_FILES
            or total * 2 + recovery_bytes + report_archive_bytes * 2 > MAX_BYTES):
        issues.append(Issue('SIZE_LIMIT', str(workbench.workspace), '원본 보존본과 작업 사본의 크기 한도를 넘습니다.', '문서 묶음을 명시적으로 나누세요.'))
    from .connection_graph_view import view_inventory
    try:
        view = view_inventory(workbench)
    except (OSError, ValueError, KeyError, TypeError) as error:
        view = None
        issues.append(Issue('VIEW_STATE_UNAVAILABLE', str(workbench.workspace / 'workbench/views/connection.json'),
                            str(error), '프로젝트 배치 파일을 명시적으로 복구한 뒤 다시 확인하세요.'))
    result = {'format': FORMAT, 'status': 'BLOCKED' if issues else 'READY', 'view_state': view,
        'service_session_id': workbench.session_id, 'selections': chosen, 'documents': summaries,
        'draft_policy': draft_policy, 'capsule_boundary': deepcopy(CAPSULE_CONTRACT), **recovery,
        'source_store': str(workbench.workspace), 'pins': pins, 'files': files, 'knowledge': knowledge, 'literature': literature,
        'revisions': [{'document_id': i, 'saved_revision': r} for i, r in sorted(visited)],
        'bytes_to_copy': total * 2 + recovery_bytes + report_archive_bytes * 2, 'warnings': warnings, 'issues': [asdict(i) for i in issues],
        'executed': False, 'engineering_release': 'NOT_RELEASED'}
    if native_references:
        result['_native_references'] = native_references
    result['inspection_sha256'] = canonical_hash(result)
    return result


def inspect_copy(workbench, selections: list[str | dict], *, draft_policy='acknowledged', recovery_archives=None):
    from .portable_project_native import inspect_union
    return inspect_union(workbench, selections, research_inspector=_inspect_research_copy,
                         draft_policy=draft_policy, recovery_archives=recovery_archives)


class _Fork:
    def __init__(self, wb, plan, stage, project_id):
        _research_dependencies()
        self.wb, self.plan, self.stage = wb, plan, stage
        self.reader = AcknowledgedReader(wb, [r['document_id'] for r in plan['documents']]
                                         if plan.get('draft_policy') == 'acknowledged' else ())
        from .portable_recovery_dependencies import seed_dependencies
        seed_dependencies(self.reader, {r['document_id'] for r in plan['documents']}, plan)
        self.documents = {r['document_id']: _PREFIX[r['kind']] + uuid.uuid4().hex for r in plan['documents']}
        self.revisions = {(r['document_id'], r['saved_revision']): 'R' + uuid.uuid4().hex for r in plan['revisions']}
        self.snapshots = {key: self.reader.revision(*key) for key in self.revisions}
        self.input_ids: dict[tuple[str, str], str] = {}
        self.inputs: dict[tuple[str, str], dict] = {}
        self.input_hashes: dict[tuple[str, str], str] = {}
        self.busy_inputs: set[tuple[str, str]] = set()
        self.written: set[tuple[str, str]] = set()
        self.busy_revisions: set[tuple[str, str]] = set()
        self.project_id = project_id
        self.execution_source_scope = (_manifest(wb.workspace)['project_id']
            if (wb.workspace / MANIFEST).is_file() else canonical_hash({'store': str(wb.workspace)}))
        for (identifier, _), document in self.snapshots.items():
            for revision, draft in [(document['input_revision'], document['draft']),
                                    *((r['input_revision'], r['draft']) for r in document.get('runs', []) if document['kind'] != 'expert')]:
                key = (identifier, revision)
                if key in self.inputs and canonical_hash(self.inputs[key]) != canonical_hash(draft):
                    fail('INPUT_ID_CONFLICT', identifier, '같은 원입력 개정에 다른 내용이 있습니다.', '원본 소유 기록을 복구하세요.', identifier)
                self.inputs[key] = deepcopy(draft)
                self.input_ids.setdefault(key, 'I' + uuid.uuid4().hex)

    def revision_path(self, identifier, revision):
        return self.stage / 'workbench' / 'documents' / self.documents[identifier] / 'revisions' / self.revisions[(identifier, revision)]

    def input_hash(self, identifier, revision):
        key = (identifier, revision)
        if key not in self.input_hashes:
            if key in self.busy_inputs:
                fail('REFERENCE_CYCLE', identifier, '입력 식별값의 순환 참조를 자동으로 변환할 수 없습니다.', '참조를 원문서에서 명시적으로 정리하세요.')
            if key not in self.inputs:
                fail('INPUT_NOT_RETAINED', str(key), '정확한 원입력이 보존되지 않았습니다.', '해당 입력의 저장 개정을 포함하세요.')
            self.busy_inputs.add(key)
            try:
                self.input_hashes[key] = canonical_hash(self.draft(identifier, self.inputs[key]))
            finally:
                self.busy_inputs.remove(key)
        return self.input_hashes[key]

    def run_for(self, identifier, job_id):
        rows = [run for (i, _), doc in self.snapshots.items() if i == identifier
                for run in doc.get('runs', []) if run['job_id'] == job_id]
        if not rows or len({(r['input_revision'], r['input_sha256']) for r in rows}) != 1:
            fail('RUN_ID_CONFLICT', identifier + '/' + job_id, '계산의 정확한 원입력이 하나로 정해지지 않습니다.', '올바른 저장 개정을 포함하세요.')
        return rows[0]

    def reference(self, typed):
        ref, target = deepcopy(typed.value), typed.document_id
        if ref.get('kind') in {'native_pre', 'native_post'}:
            from .native_project_contract import project_native_reference
            return project_native_reference(ref, self.native_mapping)
        if ref.get('kind') == 'knowledge':
            return ref  # Exact knowledge IDs/revisions/locators/hashes are never rewritten.
        if ref.get('paper_id') and not target:
            from .portable_research_knowledge import evidence_pin
            return evidence_pin(ref)  # A paper archive is not a document owner ID.
        if target not in self.documents:
            fail('DOCUMENT_NOT_SELECTED', target, '참조 문서가 포함되지 않았습니다.', '포함 목록을 다시 확인하세요.')
        key = ('discussion_id' if ref.get('kind') == 'expert_turn' else
               {'adoption': 'plan_id', 'proposal': 'discussion_id', 'pde': 'pde_document_id'}.get(typed.form, 'document_id'))
        ref[key] = self.documents[target]
        rev_key = 'plan_revision' if typed.form == 'adoption' else 'saved_revision'
        if rev_key in ref:
            ref[rev_key] = self.revisions[(target, ref[rev_key])]
        if ref.get('kind') == 'numerical_candidate_evidence':
            # Only its current navigation ref is mapped. The evidence snapshot
            # remains byte-exact with its original execution source.
            ref['source'] = self.reference(TypedReference((), '후보 원계산', 'result', ref['source']))
        if typed.form == 'adoption':
            if isinstance(ref.get('candidate_evidence'), dict):
                ref['candidate_evidence'] = self.reference(TypedReference((), '채택 증거', 'exact', ref['candidate_evidence']))
            run = self.run_for(target, ref['job_id'])
            ref['input_sha256'] = self.input_hash(target, run['input_revision'])
        elif 'input_revision' in ref and not (ref.get('kind') == 'result' and target.startswith('X')):
            old_revision = ref['input_revision']
            if 'input_sha256' in ref and canonical_hash(self.inputs[(target, old_revision)]) != ref['input_sha256']:
                fail('INPUT_HASH_CONFLICT', target, '참조한 원입력 내용이 다릅니다.', '정확한 원본을 복구하세요.')
            ref['input_revision'] = self.input_ids[(target, old_revision)]
            if 'input_sha256' in ref:
                ref['input_sha256'] = self.input_hash(target, old_revision)
            if typed.form == 'material_input':
                ref['draft'] = self.draft(target, ref['draft'])
        return ref

    def draft(self, identifier, value):
        draft = deepcopy(value)
        kind = next(d['kind'] for (i, _), d in self.snapshots.items() if i == identifier)
        for typed in draft_references(kind, value):
            if kind == 'report':
                from .portable_project_report import can_navigate
                if not can_navigate(typed.value, self.documents, self.native_mapping):
                    continue
            replace_at(draft, typed.path, self.reference(typed))
        from .portable_research_owner import current_draft
        return current_draft(kind, draft)

    def frozen_source(self, value):
        value = deepcopy(value)
        if not isinstance(value, dict) or value.get('kind') not in {'registered_input', 'retained_data_input'}:
            return value
        original = value['document_id']
        value['document_id'] = self.documents[original]
        if value['kind'] == 'retained_data_input':
            revision = value['revision']
            self.write_revision(original, revision)
            value['revision'] = self.revisions[(original, revision)]
            value['revision_sha256'] = file_hash(self.revision_path(original, revision) / 'revision.json')
        return value

    def arguments(self, arguments):
        args = deepcopy(arguments)
        if 'source_ref' in args:
            args['source_ref'] = self.frozen_source(args['source_ref'])
        if 'calibration_sources' in args:
            args['calibration_sources'] = [self.frozen_source(s) for s in args['calibration_sources']]
        for i, experiment in enumerate(args.get('experiments', [])):
            if isinstance(experiment, dict) and isinstance(experiment.get('source'), dict) and 'document_id' in experiment['source']:
                args['experiments'][i]['source'] = self.reference(TypedReference((), '시험 관측', 'observation', experiment['source']))
            source = experiment.get('observation_source', {}).get('data_source') if isinstance(experiment, dict) else None
            if isinstance(source, dict):
                args['experiments'][i]['observation_source']['data_source'] = self.reference(
                    TypedReference((), '보존한 시험 원자료', 'observation', source))
        # Request Plans retain prepared engine arguments, not an unresolved
        # request. Domain-source references outside this supported owner set
        # already block inspection through the draft's typed contracts.
        from .portable_project_evaluation import project_arguments
        return project_arguments(self, args)

    def run(self, identifier, original):
        if identifier.startswith('X'):
            from .portable_research_owner import project_run
            return project_run(self, identifier, original)
        run = deepcopy(original)
        run['draft'] = self.draft(identifier, original['draft'])
        run['input_revision'] = self.input_ids[(identifier, original['input_revision'])]
        run['input_sha256'] = canonical_hash(run['draft'])
        run['arguments'] = self.arguments(original['arguments'])
        for key in ('retained_record', 'retained_result'):
            if run.get(key):
                run[key]['revision'] = self.revisions[(identifier, run[key]['revision'])]
        run['portable_origin'] = {'document_id': identifier, 'job_id': original['job_id'],
            'input_revision': original['input_revision'], 'input_sha256': original['input_sha256'],
            'arguments_sha256': canonical_hash(original['arguments']), 'execution_replayed': False}
        return run

    def write_revision(self, identifier, revision):
        key = (identifier, revision)
        if key in self.written:
            return
        if key in self.busy_revisions:
            fail('REVISION_CYCLE', str(key), '보존 자료의 저장 개정에 순환 의존이 있습니다.', '원문서의 보존 자료를 확인하세요.')
        self.busy_revisions.add(key)
        target = self.revision_path(identifier, revision)
        target.mkdir(parents=True, exist_ok=False)
        # All source paths come from the reviewed exact manifest; no rglob of
        # source stores, adjacent company files, process environments or secrets.
        entries = [r for r in self.plan['files'] if r['document_id'] == identifier and r['saved_revision'] == revision]
        for entry in entries:
            if entry['asset'] != 'revision.json' and not entry.get('archive_only'):
                self.copy_entry(entry, inside(target, entry['asset'], must_exist=False))
        original = self.snapshots[key]
        document = deepcopy(original)
        document.update(id=self.documents[identifier], saved_revision=self.revisions[key], _disk_revision=self.revisions[key],
                        input_revision=self.input_ids[(identifier, original['input_revision'])],
                        session_id='Sportable_' + self.project_id[1:])
        for marker in ('_save_command', '_mutation_command'):
            if marker in document:
                document.setdefault('portable_owner_command_history', []).append(
                    {'authority': 'HISTORY_ONLY', 'source_document_id': identifier,
                     'field': marker, 'record': document.pop(marker)})
        document['draft'] = self.draft(identifier, original['draft'])
        for stack in ('_undo', '_redo'):
            document[stack] = [self.draft(identifier, d) for d in original.get(stack, [])]
        document['runs'] = [self.run(identifier, r) for r in original.get('runs', [])]
        for retained in document.get('retained_inputs', {}).values():
            retained['revision'] = self.revisions[(identifier, retained['revision'])]
        for i, row in enumerate(original.get('adoptions', [])):
            if 'plan_id' in row:
                document['adoptions'][i] = self.reference(TypedReference((), '채택', 'adoption', row))
        for i, comparison in enumerate(original.get('comparisons', [])):
            row = document['comparisons'][i]
            old_retained = comparison.get('retained_revision')
            if not old_retained:
                fail('COMPARISON_NOT_RETAINED', identifier, '저장하지 않은 비교를 포함할 수 없습니다.', '원문서를 저장하세요.')
            row['retained_revision'] = self.revisions[(identifier, old_retained)]
            if old_retained != revision:
                self.write_revision(identifier, old_retained)
                comparison_folder = self.revision_path(identifier, old_retained) / 'comparisons' / check_id(row['id'])
            else:
                comparison_folder = target / 'comparisons' / check_id(row['id'])
                result_path = inside(comparison_folder, 'result.json')
                result = json_file(result_path)
                for label in ('source', 'prediction_source'):
                    source_ref = result.get('binding', {}).get(label)
                    if isinstance(source_ref, dict):
                        result['binding'][label] = self.reference(TypedReference((), '비교', 'curve', source_ref))
                save_json(result_path, result)
                save_json(comparison_folder / 'result.sha256.json', {'sha256': file_hash(result_path)})
            result = read_result(comparison_folder, verify='all')
            row['binding'] = deepcopy(result['binding'])
            row['result_sha256'] = file_hash(comparison_folder / 'result.json')
        for row in document.get('candidate_evidence', []):
            if row.get('retained_revision'):
                row['retained_revision'] = self.revisions[(identifier, row['retained_revision'])]
        for history in document.get('portable_capture_history', []):
            history['revision'] = self.revisions[(identifier, history['revision'])]
        # Old capture publication witnesses are provenance, not new write authority.
        if document.get('_candidate_evidence_publications'):
            document.setdefault('portable_publication_history', []).append(
                {'authority': 'HISTORY_ONLY', 'source_document_id': identifier,
                 'witnesses': document.pop('_candidate_evidence_publications')})
        if document['kind'] == 'data' and (self.plan.get('recovery_archives') or
                any(r.get('portable_data_execution') for r in original['runs'])):
            from .portable_data_execution import write as write_data_execution
            for source_run, run in zip(original['runs'], document['runs']):
                if source_run.get('retention_complete'):
                    write_data_execution(self, identifier, revision, source_run, run, target)
        if document['kind'] == 'numerical':
            from .portable_project_execution import write_execution
            for source_run, run in zip(original['runs'], document['runs']):
                if source_run.get('retention_complete'):
                    write_execution(self, identifier, revision, source_run, run, target)
        if document['kind'] in {'pde', 'simulation'}:
            from .portable_project_physics import write as write_physics
            for source_run, run in zip(original['runs'], document['runs']):
                write_physics(self, identifier, revision, source_run, run, target)
        if document['kind'] == 'evaluation':
            from .portable_project_evaluation import write as write_evaluation
            write_evaluation(self, identifier, revision, original, document, target)
        for run in document['runs']:
            if document['kind'] == 'expert':
                continue  # Origin job and submitted-input files remain byte-exact.
            job_path = target / 'jobs' / (check_id(run['job_id']) + '.json')
            input_path = target / 'inputs' / (run['job_id'] + '.json')
            if job_path.is_file():
                job = json_file(job_path)
                job['arguments'] = deepcopy(run['arguments'])
                job['portable_origin'] = deepcopy(run['portable_origin'])
                save_json(job_path, job)
            if input_path.is_file():
                save_json(input_path, run)
        document['portable_origin'] = {'project_id': self.project_id, 'document_id': identifier,
            'saved_revision': revision, 'input_revision': original['input_revision'],
            'input_sha256': canonical_hash(original['draft']),
            'archive': f'portable/originals/{identifier}/{revision}', 'execution_replayed': False}
        if virtual_revision(revision) or is_acknowledged_container(original):
            document['portable_snapshot'] = {'container_revision': self.revisions[key],
                'layer': original.get('_portable_layer', 'ACKNOWLEDGED_WORKING')}
        if document['kind'] == 'report':
            from .portable_project_report import write_revision as write_report
            write_report(self, identifier, revision, original, document, target)
        if document['kind'] in {'study', 'expert'}:
            from .portable_research_owner import write_revision as write_research
            write_research(self, identifier, revision, original, document, target)
        owner = self.reader.owner(identifier)
        document['_saved_fingerprint'] = owner._fingerprint(document)
        save_json(target / 'document.json', document)
        files = [{'path': p.relative_to(target).as_posix(), 'sha256': file_hash(p)}
                 for p in sorted(target.rglob('*')) if p.is_file() and p.name != 'revision.json']
        save_json(target / 'revision.json', {'id': document['id'], 'revision': document['saved_revision'], 'files': files})
        self.written.add(key)
        self.busy_revisions.remove(key)

    def copy_entry(self, entry, target):
        if entry.get('origin') == 'acknowledged_snapshot':
            import hashlib
            payload = self.reader.payloads[(entry['document_id'], entry['saved_revision'], entry['asset'])]
            if len(payload) != entry['bytes'] or hashlib.sha256(payload).hexdigest() != entry['sha256']:
                fail('SOURCE_CHANGED', entry['path'], '확인한 초안 스냅샷이 바뀌었습니다.', '목록을 다시 확인하세요.')
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(payload)
                stream.flush(); os.fsync(stream.fileno())
        else:
            copy_verified(inside(self.wb.workspace, entry['path']), target, entry)

    def write(self):
        from .portable_research_knowledge import write as write_knowledge
        self.knowledge_revisions = write_knowledge(self)
        for entry in self.plan['files']:
            path = f"portable/originals/{entry['document_id']}/{entry['saved_revision']}/{entry['asset']}"
            self.copy_entry(entry, inside(self.stage, path, must_exist=False))
        for identifier, revision in self.revisions:
            self.write_revision(identifier, revision)
        for selection in self.plan['selections']:
            identifier, revision = selection['document_id'], selection['saved_revision']
            base = load_json(self.revision_path(identifier, revision) / 'document.json') if revision else None
            owner_folder = self.stage / 'workbench' / 'documents' / self.documents[identifier]
            if base:
                path = self.revision_path(identifier, revision)
                save_json(owner_folder / 'document.json', {'id': base['id'], 'revision': base['saved_revision'],
                    'revision_sha256': file_hash(path / 'revision.json'), 'fingerprint': base['_saved_fingerprint']})
            if (identifier, WORKING) in self.snapshots:
                working = load_json(self.revision_path(identifier, WORKING) / 'document.json')
                working.update(saved_revision=base['saved_revision'] if base else None,
                               _disk_revision=base['saved_revision'] if base else None,
                               _saved_fingerprint=base['_saved_fingerprint'] if base else None)
                working['portable_origin']['snapshot_kind'] = 'acknowledged'
                working['portable_origin']['saved_base'] = revision
                # Pending evidence remains pending, with exact bytes where the
                # existing Numerical save hook expects them. No CAPTURE journal
                # is installed in this owner's operational commands directory.
                for row in working.get('candidate_evidence', []):
                    if not row.get('retained_revision'):
                        source = self.revision_path(identifier, WORKING) / 'candidate_evidence' / (row['id'] + '.json')
                        copy_verified(source, owner_folder / 'candidate_evidence' / source.name, fingerprint_file(source))
                if working['kind'] in {'study', 'expert'}:
                    from .portable_research_owner import install_working as install_research
                    install_research(self.revision_path(identifier, WORKING), owner_folder, working)
                if working['kind'] == 'report':
                    from .portable_project_report import install_working
                    install_working(self.revision_path(identifier, WORKING), owner_folder, working)
                save_json(owner_folder / 'working.json', working)
        return [{'source_document_id': i, 'document_id': self.documents[i],
                 'kind': self.snapshots[(i, r or WORKING)]['kind'],
                 'title': self.snapshots[(i, WORKING if (i, WORKING) in self.snapshots else r)]['title'],
                 'source_saved_revision': r, 'saved_revision': self.revisions[(i, r)] if r else None,
                 'acknowledged_revision': self.revisions.get((i, WORKING))}
                for i, r in ((v['document_id'], v['saved_revision']) for v in self.plan['selections'])]



def create_copy(workbench, inspection: dict, destination: str | Path, *, approved: bool,
                command_id: str, session_id: str) -> dict:
    """Create a NEW working folder after rechecking the reviewed generation/files.

    Explicit approval covers only the inventory. It cannot grant access to
    unselected folders. Same-command response-loss retries return the existing
    receipt after verification; no existing copy is overwritten, even if empty.
    """
    if approved is not True:
        raise ValueError('복사할 문서와 보존 파일 목록을 명시적으로 확인하세요.')
    command_id = check_id(command_id)
    if session_id != workbench.session_id or inspection.get('service_session_id') != session_id:
        raise ValueError('서비스가 바뀌었습니다. 원문서와 포함 목록을 다시 읽으세요.')
    if inspection.get('status') != 'READY':
        raise ValueError('누락/오류를 해결하고 포함 목록을 다시 확인하세요.')
    unsigned = {k: deepcopy(v) for k, v in inspection.items() if k != 'inspection_sha256'}
    if canonical_hash(unsigned) != inspection.get('inspection_sha256'):
        raise ValueError('확인한 포함 목록이 변경되었습니다.')
    destination = Path(os.path.abspath(destination))
    no_links(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError('사본의 상위 폴더를 먼저 선택하세요: ' + str(destination.parent))
    # No nested source/destination: movement and source-unavailable testing must
    # not accidentally carry the source service along with the working copy.
    if destination.is_relative_to(workbench.workspace) or workbench.workspace.is_relative_to(destination):
        raise ValueError('원 보관소와 겹치지 않는 새 폴더를 선택하세요.')
    signature = canonical_hash({'inspection': inspection['inspection_sha256'], 'command_id': command_id})
    def existing_receipt():
        if destination.exists():
            marker = destination / MANIFEST
            if marker.is_file():
                prior = json_file(marker)
                if prior.get('command_id') == command_id and prior.get('request_sha256') == signature:
                    checked = verify_project(destination)
                    if checked['status'] != 'READY':
                        raise PortableProjectError([Issue(**i) for i in checked['issues']])
                    return {'status': 'ALREADY_CREATED', 'workspace': str(destination), 'project_id': prior['project_id'],
                            'documents': prior['documents'], 'executed': False, 'engineering_release': 'NOT_RELEASED'}
            raise FileExistsError('기존 폴더는 덮어쓰지 않습니다: ' + str(destination))
        return None

    prior_receipt = existing_receipt()
    if prior_receipt:
        return prior_receipt
    # Shared owner locks protect the selected live generations. Every actual
    # byte is independently rechecked, including after staging, before publish.
    with ExitStack() as locks:
        for index, row in enumerate(inspection['selections']):
            lock = workbench._document_owner(row['document_id'])._lock(row['document_id'])
            # Waiting for the first lock is safe (no other domain lock held).
            # Subsequent locks must not invert an in-flight owner's resolution order.
            if not lock.acquire(blocking=(index == 0)):
                fail('OWNER_BUSY', row['document_id'], '원 도구에서 문서를 처리 중입니다. 사본은 발행하지 않았습니다.',
                     '처리가 끝난 뒤 같은 포함 목록으로 다시 시도하세요.', row['document_id'])
            locks.callback(lock.release)
        if inspection['selections']:
            locks.enter_context(workbench.material_documents._lock('ViewConnectionState'))
        if inspection.get('native_inspections'):
            from .portable_project_native import native_context
            locks.enter_context(native_context(workbench).lock)
        prior_receipt = existing_receipt()  # A concurrent identical call may have completed.
        if prior_receipt:
            return prior_receipt
        fresh = inspect_copy(workbench, inspection['selections'] + inspection.get('native_selections', []), draft_policy=inspection.get('draft_policy', 'saved_only'),
                             recovery_archives=inspection.get('recovery_selections', []))
        if fresh.get('inspection_sha256') != inspection['inspection_sha256']:
            fail('STALE_INSPECTION', str(destination), '포함 자료나 문서 입력/저장 개정이 바뀌었습니다.', '포함 목록을 새로 확인하세요.')
        stage = Path(tempfile.mkdtemp(prefix='.caelab-copy-', dir=destination.parent))
        reserved = False
        try:
            project_id = 'P' + uuid.uuid4().hex
            native = {}
            if inspection.get('native_inspections'):
                from .portable_project_native import native_context, stage_native
                choices = [{'reference': r['native'], 'working_target': r['working_target']}
                           for r in inspection['native_selections']]
                native = stage_native(native_context(workbench), inspection['native_inspections'], stage,
                                      project_id=project_id, local_ids={'selections': choices})
            if inspection['selections']:
                fork = _Fork(workbench, inspection, stage, project_id)
                fork.native_mapping = native.get('native_mapping', [])
                documents = fork.write()
                from .portable_project_recovery import write_archives
                recovery_archives = write_archives(fork)
                from .connection_graph_view import transfer_view
                transfer_view(workbench, stage, fork.documents, inspection.get('view_state'))
            else:
                from types import SimpleNamespace
                fork = SimpleNamespace(knowledge_revisions=[], literature_archives=[], documents={}, revisions={}, input_ids={})
                documents, recovery_archives = [], []
                (stage / 'workbench').mkdir(exist_ok=True)
                (stage / 'portable').mkdir(exist_ok=True)
            immutable = []
            for path in sorted(stage.rglob('*')):
                if not path.is_file():
                    continue
                rel = path.relative_to(stage).as_posix()
                knowledge_asset = rel.startswith('workbench/assistance/knowledge/') and rel != 'workbench/assistance/knowledge/documents.json'
                literature_asset = rel.startswith('workbench/assistance/literature/') and Path(rel).name != 'papers.json'
                if knowledge_asset or literature_asset or rel.startswith(('portable/originals/', 'portable/recovery/', 'portable/recovery-maps/')) or '/revisions/' in rel or '/candidate_evidence/' in rel:
                    immutable.append({'path': rel, **fingerprint_file(path)})
            manifest = {'format': FORMAT, 'project_id': project_id, 'created_utc': utc_now(),
                'command_id': command_id, 'request_sha256': signature,
                'source_store': inspection['source_store'], 'source_inspection_sha256': inspection['inspection_sha256'],
                'documents': documents, 'draft_policy': inspection.get('draft_policy', 'saved_only'),
                'recovery_archives': recovery_archives,
                'knowledge_revisions': fork.knowledge_revisions,
                'literature_archives': fork.literature_archives,
                'knowledge_workspace_id': 'portable:' + project_id if fork.knowledge_revisions else 'local',
                'capsule_boundary': deepcopy(inspection['capsule_boundary']),
                'revision_map': [{'source_document_id': i, 'source_revision': r,
                                  'document_id': fork.documents[i], 'revision': new} for (i, r), new in sorted(fork.revisions.items())],
                'input_map': [{'source_document_id': i, 'source_input_revision': r,
                               'document_id': fork.documents[i], 'input_revision': new,
                               'input_sha256': fork.input_hash(i, r)} for (i, r), new in sorted(fork.input_ids.items())],
                'files': immutable, 'warnings': inspection['warnings'], 'executed': False,
                'engineering_release': 'NOT_RELEASED'}
            if native:
                manifest.update(native, format='caelab.portable-project/2')
            manifest['manifest_sha256'] = canonical_hash(manifest)
            save_json(stage / MANIFEST, manifest)
            checked = verify_project(stage)
            if checked['status'] != 'READY':
                raise PortableProjectError([Issue(**i) for i in checked['issues']])
            last = inspect_copy(workbench, inspection['selections'] + inspection.get('native_selections', []), draft_policy=inspection.get('draft_policy', 'saved_only'),
                             recovery_archives=inspection.get('recovery_selections', []))
            if last.get('inspection_sha256') != inspection['inspection_sha256']:
                fail('SOURCE_CHANGED', str(workbench.workspace), '복사 중 원본 자료가 바뀌었습니다.', '포함 목록부터 다시 확인하세요.')
            # Exclusive directory reservation prevents even a concurrent empty
            # destination from being replaced (POSIX rename alone would not).
            destination.mkdir(exist_ok=False)
            reserved = True
            save_json(destination / '.incomplete.json', {'project_id': project_id, 'state': 'PUBLISHING'})
            for name in ('workbench', 'portable', 'native'):
                if (stage / name).exists():
                    (stage / name).rename(destination / name)
            (stage / MANIFEST).rename(destination / MANIFEST)  # Completion marker LAST.
            (destination / '.incomplete.json').unlink()
            stage.rmdir()
            return {'status': 'CREATED', 'workspace': str(destination), 'project_id': project_id,
                    'documents': documents, 'executed': False, 'engineering_release': 'NOT_RELEASED'}
        except BaseException:
            if stage.exists():
                shutil.rmtree(stage)
            # A publishing failure is intentionally visible/recoverable; never
            # delete a previously existing user's folder or claim it completed.
            if reserved and not (destination / MANIFEST).exists():
                save_json(destination / '.incomplete.json', {'state': 'INCOMPLETE',
                    'message': '발행에 실패했습니다. 원본은 보존되었습니다. 다른 새 폴더로 다시 복사하세요.'})
            raise


def _manifest(folder: Path) -> dict:
    manifest = json_file(folder / MANIFEST)
    if manifest.get('format') not in {FORMAT, 'caelab.portable-project/2'}:
        raise ValueError('지원하는 제품 작업 사본이 아닙니다.')
    native_keys = {'native_contract', 'native_inputs', 'native_projects', 'native_mapping'}
    if manifest['format'] == FORMAT and native_keys.intersection(manifest):
        raise ValueError('Native 기록에는 portable-project/2가 필요합니다.')
    expected = manifest.get('manifest_sha256')
    if canonical_hash({k: v for k, v in manifest.items() if k != 'manifest_sha256'}) != expected:
        fail('MANIFEST_CHANGED', folder / MANIFEST, '사본의 포함/대응 기록이 변경되었습니다.', '원래의 작업 사본 기록을 복구하세요.')
    return manifest


def verify_project(folder: str | Path) -> dict:
    """Verify immutable evidence AND current mutable owner heads, without open()."""
    folder = Path(os.path.abspath(folder))
    issues = []
    no_links(folder)
    if (folder / '.incomplete.json').exists():
        return {'status': 'BLOCKED', 'issues': [asdict(Issue('INCOMPLETE_COPY', str(folder),
                '발행이 끝나지 않은 사본입니다.', '원본에서 다른 새 폴더로 다시 복사하세요.'))], 'executed': False}
    try:
        manifest = _manifest(folder)
        # The existing controller also reads jobs/native command directories.
        # Reject unmanifested links there before handing any tree to an owner.
        count = 0
        for directory, dirs, names in os.walk(folder, followlinks=False):
            for name in (*dirs, *names):
                count += 1
                if count > MAX_FILES * 2:
                    fail('SIZE_LIMIT', folder, '사본 안의 항목 수가 검사 한도를 넘습니다.', '문서를 나누어 보존하세요.')
                path = Path(directory) / name
                no_links(path)
                if path.is_file():
                    relative_name(path.relative_to(folder).as_posix())
        issues = verify_inventory(folder, manifest['files'])
        if manifest.get('recovery_archives'):
            from .portable_project_recovery import verify_archives
            verify_archives(folder, manifest)
        elif manifest.get('recovery_archives') != []:
            raise ValueError('Invalid recovery archive list')
        # Current document heads can evolve through the original owner.save.
        # Do not pin mutable heads to their original export bytes.
        for row in manifest['documents']:
            identifier = check_id(row['document_id'])
            owner_root = folder / 'workbench' / 'documents' / identifier
            pointer_path = owner_root / 'document.json'
            if not pointer_path.exists() and row.get('saved_revision') is None:
                draft = json_file(inside(owner_root, 'working.json'))
                if (draft.get('id') != identifier or draft.get('kind') != row['kind']
                        or draft.get('saved_revision') is not None or draft.get('_disk_revision') is not None):
                    raise ValueError('미저장 문서 초안의 소유자/저장 상태가 다릅니다.')
                if row['kind'] in {'study', 'expert'}:
                    from .portable_research_owner import replay, current_folder
                    replay(current_folder(owner_root, draft), draft)
                if row['kind'] in {'pde', 'simulation'}:
                    from .portable_project_physics import verify_current
                    verify_current(owner_root, draft)
                if row['kind'] == 'evaluation':
                    from .portable_project_evaluation import verify_current
                    verify_current(owner_root, draft)
                if row['kind'] == 'report':
                    from .portable_project_report import verify_current
                    verify_current(owner_root, draft)
                continue
            pointer = json_file(inside(folder, f'workbench/documents/{identifier}/document.json'))
            revision = check_id(pointer['revision'])
            rev_folder = owner_root / 'revisions' / revision
            record_path = inside(rev_folder, 'revision.json')
            if pointer.get('id') != identifier or file_hash(record_path) != pointer.get('revision_sha256'):
                raise ValueError('현재 문서의 저장 개정 발행 기록이 다릅니다.')
            record = json_file(record_path)
            if record.get('id') != identifier or record.get('revision') != revision:
                raise ValueError('현재 저장 개정의 문서 소유자가 다릅니다.')
            for entry in record['files']:
                path = inside(rev_folder, entry['path'])
                if file_hash(path) != entry['sha256']:
                    raise ValueError('현재 문서의 보존 자료가 변경되었습니다: ' + str(path))
            current = json_file(rev_folder / 'document.json')
            if current.get('id') != identifier or current.get('saved_revision') != revision or current.get('kind') != row['kind']:
                raise ValueError('현재 문서 본문과 저장 개정이 다릅니다.')
            working = owner_root / 'working.json'
            if working.exists():
                draft = json_file(working)
                if draft.get('id') != identifier or draft.get('kind') != row['kind']:
                    raise ValueError('복구 초안의 문서 소유자가 다릅니다.')
            if row['kind'] in {'study', 'expert'}:
                from .portable_research_owner import replay, current_folder
                research = draft if working.exists() and draft.get('saved_revision') == revision else current
                replay(current_folder(owner_root, research), research)
            if row['kind'] in {'pde', 'simulation'}:
                from .portable_project_physics import verify_current
                verify_current(owner_root, draft if working.exists() and
                    draft.get('saved_revision') == revision else current)
            if row['kind'] == 'evaluation':
                from .portable_project_evaluation import verify_current
                verify_current(owner_root, draft if working.exists() and
                    draft.get('saved_revision') == revision else current)
            if row['kind'] == 'report':
                from .portable_project_report import verify_current
                verify_current(owner_root, draft if working.exists() and
                    draft.get('saved_revision') == revision else current)
        native = {}
        if manifest['format'] == 'caelab.portable-project/2':
            from .native_project_inputs import NativeOnlyContext
            from .portable_project_native import verify_native
            native = verify_native(NativeOnlyContext(folder, approved_roots={}), manifest)
        return {**native, 'status': 'BLOCKED' if issues else 'READY', 'project_id': manifest['project_id'],
                'documents': manifest['documents'], 'issues': [asdict(i) for i in issues],
                'executed': False, 'engineering_release': 'NOT_RELEASED'}
    except PortableProjectError as error:
        return PortableProjectError(issues + error.issues).as_dict()
    except (ValueError, KeyError, TypeError, OSError) as error:
        return {'status': 'BLOCKED', 'issues': [asdict(i) for i in issues] + [asdict(Issue('PROJECT_UNAVAILABLE', str(folder), str(error),
                '사본의 원래 기록과 필수 자료를 복구하세요. 자동으로 다른 원본을 찾지 않습니다.'))],
                'executed': False, 'engineering_release': 'NOT_RELEASED'}


def open_project(folder: str | Path):
    """Return the EXISTING Workbench on the validated copy, with an empty config.

    Opening does not evaluate. Do not copy source jobs/command journals/provider
    credentials or attach another source controller. The caller owns shutdown().
    """
    checked = verify_project(folder)
    if checked['status'] != 'READY':
        raise PortableProjectError([Issue(**i) for i in checked['issues']])
    if not checked['documents'] and _manifest(Path(folder))['format'] == 'caelab.portable-project/2':
        from .native_project_inputs import NativeOnlyContext
        return NativeOnlyContext(folder, approved_roots={})
    from .workbench import Workbench
    wb = Workbench(folder)
    try:
        for row in checked['documents']:
            wb.document_open(kind=row['kind'], document_id=row['document_id'])
    except BaseException:
        wb.shutdown()
        raise
    return wb


def repair_asset(folder: str | Path, relative: str, replacement: str | Path, *, approved: bool) -> dict:
    """Explicit exact-byte repair; no search, source substitution or hash rebasing.

    A changed existing file is quarantined inside this copy before restoration.
    A user-selected replacement must match the original inventory byte-for-byte.
    """
    if approved is not True:
        raise ValueError('복구에 사용할 동일 원본 파일을 명시적으로 선택하세요.')
    folder, replacement = Path(os.path.abspath(folder)), Path(replacement)
    no_links(folder); no_links(replacement)
    manifest = _manifest(folder)
    relative_name(relative)
    row = next((r for r in manifest['files'] if r['path'] == relative), None)
    if row is None:
        raise ValueError('사본의 보존 파일 목록에 없는 자료는 복구하지 않습니다.')
    if fingerprint_file(replacement) != {'bytes': row['bytes'], 'sha256': row['sha256']}:
        fail('WRONG_REPLACEMENT', replacement, '선택한 파일이 원본 내용과 다릅니다.', '동일한 원본 파일을 선택하세요. 다른 파일로 재연결하지 않습니다.')
    target = inside(folder, relative, must_exist=False)
    if target.exists() and fingerprint_file(target) == {'bytes': row['bytes'], 'sha256': row['sha256']}:
        return {'status': 'ALREADY_PRESENT', 'path': relative, 'executed': False}
    target.parent.mkdir(parents=True, exist_ok=True)
    repair_id = 'K' + uuid.uuid4().hex
    temporary = target.parent / ('.repair-' + repair_id)
    quarantine = None
    try:
        copy_verified(replacement, temporary, row)
        if target.exists():
            quarantine = folder / 'portable' / 'repair-history' / repair_id / 'changed-file'
            quarantine.parent.mkdir(parents=True, exist_ok=False)
            target.rename(quarantine)
        temporary.rename(target)
    except BaseException:
        if quarantine is not None and quarantine.exists() and not target.exists():
            quarantine.rename(target)
        raise
    finally:
        if temporary.exists():
            temporary.unlink()
    save_json(folder / 'portable' / 'repair-history' / repair_id / 'receipt.json',
              {'path': relative, 'sha256': row['sha256'], 'quarantined': quarantine is not None, 'created_utc': utc_now()})
    return {'status': 'REPAIRED', 'path': relative, 'quarantined': quarantine is not None, 'executed': False}


def extract_project(archive: str | Path, destination: str | Path) -> dict:
    destination = extract_archive(archive, destination)
    checked = verify_project(destination)
    if checked['status'] != 'READY':
        raise PortableProjectError([Issue(**i) for i in checked['issues']])
    return {'workspace': str(destination), **checked}


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description='제품 작업 사본: 원본 보존, 새 폴더 생성, 계산 없는 재열기')
    sub = parser.add_subparsers(dest='command', required=True)
    inspect = sub.add_parser('inspect')
    inspect.add_argument('--document', action='append', required=True)
    copy = sub.add_parser('copy')
    copy.add_argument('--document', action='append')
    copy.add_argument('--inspection', type=Path, help='명시적으로 확인한 inspect JSON 응답; 동일 서비스 세션만 허용')
    copy.add_argument('--destination', required=True)
    copy.add_argument('--inventory-confirmed', '--approved-public-files', dest='inventory_confirmed', action='store_true',
                      help='선택한 로컬 문서/보존 파일 목록 확인 (옛 옵션은 호환 alias)')
    copy.add_argument('--command-id', required=True)
    for command_parser in (inspect, copy):
        command_parser.add_argument('--saved-only', action='store_true', help='초안을 제외하고 선택 저장본만 명시적으로 복사')
        source = command_parser.add_mutually_exclusive_group(required=True)
        source.add_argument('--workspace', help='서비스가 실행 중이지 않은 보관소')
        source.add_argument('--service', help='이미 실행 중인 동일 제품 서비스 URL')
    verify = sub.add_parser('verify'); verify.add_argument('folder')
    extract = sub.add_parser('extract'); extract.add_argument('archive'); extract.add_argument('destination')
    repair = sub.add_parser('repair'); repair.add_argument('folder'); repair.add_argument('relative'); repair.add_argument('replacement')
    repair.add_argument('--approve-exact-file', action='store_true')
    args = parser.parse_args(argv)
    if args.command in ('inspect', 'copy'):
        wb = None
        if args.service:
            from .workbench_client import Client
            target = Client(args.service)
        else:
            from .workbench import Workbench
            wb = Workbench(args.workspace)
            target = wb
        try:
            if args.command == 'copy' and args.inspection:
                result = json_file(args.inspection)
            elif args.document:
                result = target.portable_inspect(args.document, draft_policy='saved_only' if args.saved_only else 'acknowledged')
            else:
                parser.error('copy에는 --inspection 또는 --document가 필요합니다.')
            if args.command == 'copy':
                result = target.portable_create(result, args.destination, approved=args.inventory_confirmed,
                    command_id=args.command_id, session_id=result['service_session_id'])
        finally:
            if wb is not None:
                wb.shutdown()
    elif args.command == 'verify':
        result = verify_project(args.folder)
    elif args.command == 'extract':
        result = extract_project(args.archive, args.destination)
    else:
        result = repair_asset(args.folder, args.relative, args.replacement, approved=args.approve_exact_file)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('status') != 'BLOCKED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
