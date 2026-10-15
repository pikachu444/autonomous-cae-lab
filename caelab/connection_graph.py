"""Read-only selected document/revision relationships, not a topology database.

The catalog is made from actual document owners and their typed fields. Fixture
catalog tool keys are not document identities. This module never submits, saves,
opens an owner, runs a provider, or rewrites references while displaying them.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from typing import Any

from .connection_graph_refs import TypedReference, document_references, comparison_references
from .evaluation import file_hash, read_result
from .jobs import TERMINAL
from .portable_project_io import inside, json_file, no_links, fail
from .storage import canonical_hash, check_id, load_json

KIND_LABELS = {'data': '데이터', 'material': '재료', 'numerical': '계산 계획',
               'pde': 'PDE', 'simulation': '해석', 'evaluation': '계산 절차',
               'study': '연구', 'report': '보고서', 'expert': '전문가 대화',
               'pre': '설계', 'post': '후처리'}
STATE_LABELS = {'AVAILABLE': '연결됨', 'NEWER_REVISION': '새 저장 개정 있음',
                'INPUT_CHANGED': '원문서 입력 변경', 'BROKEN': '참조 끊김',
                'EXTERNAL': '외부 자료', 'UNSAVED': '아직 저장하지 않음',
                'UNKNOWN': '확인되지 않음', 'FAILED': '계산 실패', 'PARTIAL_FAILURE': '일부 계산 실패',
                'SUCCEEDED': '성공 결과', 'RUNNING': '계산 중',
                'CANCELLED': '취소됨', 'REJECTED': '실행 거부',
                'INTERRUPTED': '중단됨', 'ACKNOWLEDGED': '받아들인 초안 참조'}


def is_acknowledged_container(document):
    marker = document.get('portable_snapshot', {})
    return (isinstance(marker, dict) and marker.get('layer') in {'ACKNOWLEDGED_WORKING', 'ACKNOWLEDGED_INPUT'}
            and marker.get('container_revision') == document.get('saved_revision'))


def saved_reference(document: dict) -> dict:
    return {'kind': 'document', 'document_kind': document['kind'],
            'document_id': document['id'], 'saved_revision': document['saved_revision'],
            'input_revision': document['input_revision'], 'input_sha256': canonical_hash(document['draft'])}


class SnapshotReader:
    """Read existing owner storage without triggering open()/recovery side effects."""
    def __init__(self, workbench):
        self.wb = workbench
        self.owners = {owner.kind: owner for owner in workbench.research_owners()}
        self._revisions: dict[tuple[str, str], dict] = {}

    def owner(self, identifier: str):
        check_id(identifier)
        owner = self.wb._document_owner(identifier)
        if owner is self.wb.native_commands:
            raise ValueError('현재 연구 문서 owner가 아닌 식별자입니다.')
        return owner

    def identities(self) -> list[str]:
        result: set[str] = set()
        for owner in self.owners.values():
            for name in ('document.json', 'working.json'):
                for path in owner.root.glob('*/' + name):
                    identifier = path.parent.name
                    if identifier.startswith(owner.prefix):
                        check_id(identifier)
                        result.add(identifier)
            with owner._catalog_lock:
                result.update(owner._documents)
        return sorted(result)

    def revision(self, identifier: str, revision: str) -> dict:
        key = (check_id(identifier), check_id(revision))
        if key not in self._revisions:
            owner = self.owner(identifier)
            folder = owner._folder(identifier) / 'revisions' / revision
            no_links(folder)
            record = json_file(folder / 'revision.json')
            if record.get('id') != identifier or record.get('revision') != revision:
                raise ValueError('문서와 저장 개정의 소유자가 다릅니다.')
            # Harden the existing verifier at the copy/navigation boundary.
            names: set[str] = set()
            for entry in record['files']:
                name = entry['path']
                if name.casefold() in names:
                    raise ValueError('저장 자료에 중복 경로가 있습니다.')
                names.add(name.casefold())
                asset = inside(folder, name)
                if file_hash(asset) != entry['sha256']:
                    fail('ASSET_CHANGED', asset, '보존 파일이 원래 내용과 다릅니다.',
                         '동일한 원본 파일을 명시적으로 선택해 복구하세요.', identifier)
            if 'document.json' not in names:
                raise ValueError('저장 개정에 문서 본문이 없습니다.')
            document = owner._verify_revision(identifier, revision)
            if (document.get('id') != identifier or document.get('kind') != owner.kind
                    or document.get('saved_revision') != revision):
                raise ValueError('저장 문서의 식별자/종류/개정이 일치하지 않습니다.')
            self._revisions[key] = document
        return deepcopy(self._revisions[key])

    def current(self, identifier: str) -> dict:
        owner = self.owner(identifier)
        with owner._lock(identifier):
            if identifier in owner._documents:
                return deepcopy(owner._documents[identifier])
            folder = owner._folder(identifier)
            no_links(folder)
            pointer_path, working_path = folder / 'document.json', folder / 'working.json'
            if pointer_path.exists():
                pointer = json_file(pointer_path)
                saved = self.revision(identifier, pointer['revision'])
                path = folder / 'revisions' / pointer['revision'] / 'revision.json'
                if pointer.get('id') != identifier or file_hash(path) != pointer.get('revision_sha256'):
                    raise ValueError('저장 개정의 발행 기록이 다릅니다.')
                working = json_file(working_path) if working_path.exists() else None
                document = working if working and working.get('saved_revision') == pointer['revision'] else saved
            elif working_path.exists():
                document = json_file(working_path)
            else:
                raise FileNotFoundError('원문서가 보관소에 없습니다: ' + identifier)
            if document.get('id') != identifier or document.get('kind') != owner.kind:
                raise ValueError('원문서의 종류/소유자가 다릅니다.')
            return deepcopy(document)

    def matching_input(self, identifier: str, input_revision: str, digest: str,
                       generation: int | None = None) -> dict:
        owner = self.owner(identifier)
        # Only this explicitly referenced owner is searched. Equal saved copies
        # of one input are not competing model mappings; their input is exact.
        paths = sorted((owner._folder(identifier) / 'revisions').glob('*/revision.json'))
        current_revision = self.current(identifier).get('saved_revision')
        paths.sort(key=lambda path: path.parent.name != current_revision)
        for path in paths:
            # Inspect only the typed input header to select candidates. An
            # unrelated, damaged historic result is not the selected input.
            candidate = json_file(path.parent / 'document.json')
            if (not is_acknowledged_container(candidate) and candidate.get('input_revision') == input_revision and canonical_hash(candidate['draft']) == digest
                    and (generation is None or candidate['generation'] == generation)):
                return self.revision(identifier, path.parent.name)
        raise FileNotFoundError('참조한 정확한 입력의 저장 개정이 없습니다. 해당 입력을 저장하거나 명시적으로 다시 연결하세요.')

    def acknowledged_input(self, identifier, input_revision, digest, generation=None):
        current = self.current(identifier)
        def matches(doc):
            return (doc['input_revision'] == input_revision and canonical_hash(doc['draft']) == digest
                    and (generation is None or doc['generation'] == generation))
        if matches(current):
            return current
        for path in sorted((self.owner(identifier)._folder(identifier) / 'revisions').glob('*/document.json')):
            candidate = json_file(path)
            if is_acknowledged_container(candidate) and matches(candidate):
                return self.revision(identifier, path.parent.name)
        # Read only this referenced Material owner's completed acknowledgement.
        # Never replay command receipts or collect application/global settings.
        from .portable_project_drafts import recorded_material_input
        doc, _ = recorded_material_input(self, identifier, input_revision)
        if not matches(doc):
            raise ValueError('이전 acknowledged 입력의 세대/내용이 참조와 다릅니다.')
        return doc

    def run(self, document: dict, job_id: str) -> dict:
        row = next((r for r in document.get('runs', []) if r['job_id'] == check_id(job_id)), None)
        if row is None:
            raise ValueError('이 원문서가 소유한 계산이 아닙니다.')
        return deepcopy(row)

    def job(self, document: dict, run: dict) -> dict:
        ref = run.get('retained_record')
        if ref:
            self.revision(document['id'], ref['revision'])
            folder = self.owner(document['id'])._folder(document['id']) / 'revisions' / ref['revision']
            job = json_file(inside(folder, 'jobs/' + check_id(run['job_id']) + '.json'))
        else:
            job = self.wb.manager.status(run['job_id'])
        if job['id'] != run['job_id'] or job['operation'] != run['operation'] or job['arguments'] != run['arguments']:
            raise ValueError('보존한 계산 기록이 원입력과 다릅니다.')
        return job

    def result(self, document: dict, run: dict, *, metadata_only: bool = False) -> dict:
        ref = run.get('retained_result')
        if not ref:
            raise FileNotFoundError('보존된 응답은 없습니다. 실패/중단 기록은 별도로 남아 있습니다.')
        self.revision(document['id'], ref['revision'])
        folder = self.owner(document['id'])._folder(document['id']) / 'revisions' / ref['revision'] / 'results' / check_id(run['job_id'])
        return read_result(folder, verify='all', selection={'metadata_only': True} if metadata_only else None)

    def resolve(self, typed: TypedReference) -> dict:
        """Availability and recency are independent; stale != broken."""
        ref, form = deepcopy(typed.value), typed.form
        identifier = typed.document_id
        if ref.get('kind') == 'knowledge':
            return {'status': 'EXTERNAL', 'message': '문헌 원문은 해당 도구에서 명시적으로 확인하세요.',
                    'exact_reference': None, 'owner_id': None}
        if ref.get('kind') in {'native_pre', 'native_post'}:
            from .native_project_inputs import context_from_workbench, verify_registered
            verified = verify_registered(context_from_workbench(self.wb), ref, full=True)
            return {'status': 'AVAILABLE', 'message': '검증된 원본 저장 모델', 'exact_reference': verified.reference,
                    'owner_id': ref['document_id'], 'owner_kind': verified.snapshot['native_kind'],
                    'owner_title': verified.receipt['name'], 'reference_basis': 'registered_native_snapshot'}
        current = self.current(identifier)
        exact, saved, run = None, None, None
        if form == 'material_input':
            if current['kind'] != 'material':
                raise ValueError('재료 입력의 원문서가 아닙니다.')
            try:
                saved = self.matching_input(identifier, ref['input_revision'], canonical_hash(ref['draft']), ref['generation'])
                exact = saved_reference(saved)
            except FileNotFoundError:
                self.acknowledged_input(identifier, ref['input_revision'], canonical_hash(ref['draft']), ref['generation'])
                same = (current['input_revision'] == ref['input_revision'] and current['generation'] == ref['generation']
                        and canonical_hash(current['draft']) == canonical_hash(ref['draft']))
                state = 'ACKNOWLEDGED' if same else 'INPUT_CHANGED'
                return {'status': state, 'message': STATE_LABELS[state],
                        'exact_reference': None, 'owner_id': identifier, 'owner_kind': current['kind'],
                        'owner_title': current['title'], 'reference_basis': 'acknowledged_input',
                        'working_reference': {'document_id': identifier, 'input_revision': ref['input_revision'],
                                              'generation': ref['generation'], 'input_sha256': canonical_hash(ref['draft'])}}
        elif form in ('observation', 'result', 'curve') or ref.get('kind') == 'result':
            run = self.run(current, ref['job_id'])
            if any(run.get(k) != ref.get(k) for k in ('input_revision', 'input_sha256')):
                raise ValueError('결과의 원입력 개정이 다릅니다.')
            result = self.result(current, run)
            digest = canonical_hash(result)
            if 'result_sha256' in ref and digest != ref['result_sha256']:
                raise ValueError('저장된 결과 내용이 다릅니다.')
            if form == 'curve' and canonical_hash(result.get('responses', {}).get(ref['response'])) != ref['response_sha256']:
                raise ValueError('비교한 응답 내용이 다릅니다.')
            if form == 'observation' and (current['kind'] != 'data' or ref['response'] not in result.get('responses', {})):
                raise ValueError('선택한 Data 응답이 없습니다.')
            exact = {k: deepcopy(v) for k, v in ref.items() if k in
                     {'document_id', 'job_id', 'input_revision', 'input_sha256', 'response', 'selection'}}
            exact.update(kind='result', result_sha256=digest)
        elif form == 'adoption':
            saved = self.revision(identifier, ref['plan_revision'])
            run = self.run(saved, ref['job_id'])
            if run['input_sha256'] != ref['input_sha256']:
                raise ValueError('채택 기록의 계산 입력이 다릅니다.')
            exact = saved_reference(saved)
        elif form == 'proposal' or ref.get('kind') == 'expert_turn':
            if form == 'proposal':
                # DesktopLinks.discussion_plan stores a job+turn+proposal, NOT
                # a saved_revision field. Resolve those actual contract fields.
                run = self.run(current, ref['job_id'])
                if any(run[k] != ref[k] for k in ('input_revision', 'input_sha256')):
                    raise ValueError('제안의 대화 원입력이 다릅니다.')
                result = self.result(current, run)
                index = ref['proposal_index']
                actions = result.get('proposed_actions', [])
                if type(index) is not int or not 0 <= index < len(actions):
                    raise ValueError('실제 응답에 선택한 제안이 없습니다.')
                action = actions[index]
                if (action.get('status') != 'PLANNED' or action.get('executed') is not False
                        or canonical_hash(action.get('plan')) != ref['proposal_sha256']):
                    raise ValueError('제안의 원래 내용이 다릅니다.')
                saved = self.revision(identifier, run['retained_result']['revision'])
            else:
                saved = self.revision(identifier, ref['saved_revision'])
            turns = saved.get('discussion', {}).get('turns', saved.get('turns', []))
            turn = next((t for t in turns if t['id'] == ref['turn_id']), None)
            if (turn is None or ('turn_sha256' in ref and canonical_hash(turn) != ref['turn_sha256'])
                    or (form == 'proposal' and any(turn.get(k) != ref[k] for k in
                                                  ('job_id', 'input_revision', 'input_sha256')))):
                raise ValueError('정확한 대화 차례가 없습니다.')
            exact = {'kind': 'expert_turn', 'discussion_id': identifier, 'saved_revision': saved['saved_revision'],
                     'turn_id': ref['turn_id'], 'turn_sha256': canonical_hash(turn)}
        elif ref.get('kind') == 'numerical_candidate_evidence':
            from .numerical_candidate_evidence import resolve_candidate_evidence
            resolve_candidate_evidence(self.owner(identifier), ref, consumer='read')
            saved = self.revision(identifier, ref['saved_revision'])
            run = self.run(saved, ref['source']['job_id'])
            exact = ref
        elif ref.get('kind') == 'comparison':
            saved = self.revision(identifier, ref['saved_revision'])
            row = next((r for r in saved.get('comparisons', []) if r['id'] == ref['comparison_id']), None)
            if row is None or row['result_sha256'] != ref['result_sha256']:
                raise ValueError('저장한 비교가 없습니다.')
            self.owner(identifier)._comparison_folder(saved, row)
            exact = ref
        else:
            saved = self.revision(identifier, ref['saved_revision'])
            expected_kind = ref.get('document_kind', ref.get('kind', 'pde' if form == 'pde' else None))
            if ((expected_kind and expected_kind != saved['kind']) or saved['input_revision'] != ref['input_revision']
                    or canonical_hash(saved['draft']) != ref['input_sha256']):
                raise ValueError('정확한 원문서 종류/입력/저장 개정이 다릅니다.')
            exact = saved_reference(saved)
        original_input = run['input_revision'] if run else saved['input_revision']
        state = ('INPUT_CHANGED' if current['input_revision'] != original_input else
                 'NEWER_REVISION' if saved and form != 'material_input' and current.get('saved_revision') != saved['saved_revision'] else 'AVAILABLE')
        return {'status': state, 'message': STATE_LABELS[state], 'exact_reference': exact,
                'owner_id': identifier, 'owner_kind': current['kind'], 'owner_title': current['title'],
                'reference_basis': 'input_identity' if form == 'material_input' else 'stored_reference'}


def build_graph(workbench, document_ids: list[str] | None = None, *, include_history: bool = False,
                maximum_documents: int = 256) -> dict[str, Any]:
    reader = SnapshotReader(workbench)
    from .connection_graph_native import native_snapshots, recorded_jobs
    natives = native_snapshots(workbench)
    if document_ids is not None and (not isinstance(document_ids, list) or not document_ids
                                    or any(not isinstance(v, str) for v in document_ids)):
        raise ValueError('실제 문서를 하나 이상 선택하세요.')
    identifiers = sorted(set(document_ids if document_ids is not None else [*reader.identities(), *natives]))
    if len(identifiers) > maximum_documents:
        raise ValueError('문서를 256개 이하로 선택해 관계를 좁혀 주세요.')
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    documents: dict[str, dict] = {}
    issues: list[dict] = []

    def node(key, label, kind, state='AVAILABLE', **fields):
        row = {'key': key, 'label': label, 'kind': kind, 'status': state,
               'status_label': STATE_LABELS.get(state, state), **fields}
        nodes[key] = row
        return row

    def edge(a, b, role, **fields):
        key = 'edge/' + canonical_hash([a, b, role, fields])[:24]
        if not any(e['key'] == key for e in edges):
            edges.append({'key': key, 'source': a, 'target': b, 'label': role, **fields})

    def add_document(identifier):
        key = 'document/' + identifier
        if key in nodes:
            return
        try:
            if identifier in natives:
                doc = natives[identifier]
                documents[identifier] = doc
                state = 'AVAILABLE' if doc['report_fresh'] else 'UNKNOWN'
                node(key, doc.get('title', KIND_LABELS[doc['kind']]), doc['kind'], state,
                     node_type='document', owner_id=identifier, owner_kind=doc['kind'],
                     exact_reference=None, dirty=doc.get('dirty'),
                     subtitle=KIND_LABELS[doc['kind']] + ' / 마지막 보고 상태',
                     diagnostic={'document_id': identifier, 'generation': doc['generation'],
                                 'connected': doc['connected'], 'report_fresh': doc['report_fresh'],
                                 'saved': doc.get('project', {}).get('saved', doc.get('saved_revision'))})
                return
            doc = reader.current(identifier)
            documents[identifier] = doc
            exact = saved_reference(reader.revision(identifier, doc['saved_revision'])) if doc.get('saved_revision') else None
            dirty = reader.owner(identifier)._fingerprint(doc) != doc.get('_saved_fingerprint')
            node(key, doc['title'], doc['kind'], 'UNSAVED' if not exact else 'AVAILABLE',
                 owner_id=identifier, owner_kind=doc['kind'], node_type='document', exact_reference=exact,
                 dirty=dirty, subtitle=KIND_LABELS.get(doc['kind'], doc['kind']) + (' / 미저장 변경' if dirty else ''),
                 diagnostic={'document_id': identifier, 'generation': doc['generation'],
                             'input_revision': doc['input_revision'], 'saved_revision': doc.get('saved_revision')})
        except (ValueError, KeyError, OSError, TypeError) as error:
            node(key, '열 수 없는 문서', 'document', 'BROKEN', node_type='document', owner_id=identifier,
                 exact_reference=None, diagnostic={'document_id': identifier, 'error': str(error)})
            issues.append({'document_id': identifier, 'message': str(error)})

    for identifier in identifiers:
        check_id(identifier)
        add_document(identifier)
    for identifier in identifiers:
        doc = documents.get(identifier)
        if not doc:
            continue
        source_key = 'document/' + identifier
        if identifier in natives:
            for row in recorded_jobs(workbench, doc):
                node(row['key'], doc.get('title', '설계') + ' 계산 기록', 'result', row['status'],
                     node_type='run', owner_id=identifier, owner_kind=doc['kind'], job_id=row['job_id'],
                     exact_reference=None, subtitle='Pre에 명시적으로 저장한 계산 연결', diagnostic=row)
                edge(source_key, row['key'], '보존 계산 연결', status=row['status'])
            continue
        for typed in (*document_references(doc, include_history=include_history), *comparison_references(doc)):
            target = typed.document_id
            ref_key = 'reference/' + canonical_hash([identifier, list(typed.path)])[:32]
            try:
                resolved = reader.resolve(typed)
            except (ValueError, KeyError, TypeError, OSError) as error:
                resolved = {'status': 'BROKEN', 'exact_reference': None, 'owner_id': target, 'message': str(error)}
            if target and resolved['status'] != 'EXTERNAL' and typed.value.get('kind') not in {'native_pre', 'native_post'}:
                try:
                    add_document(check_id(target))
                except ValueError:
                    pass
            owner = documents.get(target, {})
            label = owner.get('title', resolved.get('owner_title', '외부 자료' if resolved['status'] == 'EXTERNAL' else '찾을 수 없는 원문서'))
            node(ref_key, label, owner.get('kind', resolved.get('owner_kind', 'reference')), resolved['status'],
                 node_type='reference', subtitle=typed.role, consumer_id=identifier, path=list(typed.path),
                 working_reference=resolved.get('working_reference'), owner_id=resolved.get('owner_id'),
                 owner_kind=owner.get('kind', resolved.get('owner_kind')), exact_reference=resolved.get('exact_reference'),
                 diagnostic={'reference': typed.value, 'form': typed.form, 'basis': resolved.get('reference_basis'), 'message': resolved['message']})
            edge(source_key, ref_key, typed.role, status=resolved['status'], path=list(typed.path))
            if target and 'document/' + target in nodes:
                edge(ref_key, 'document/' + target, '원문서', status=resolved['status'])
        for i, run in enumerate(doc.get('runs', [])):
            key = 'run/' + identifier + '/' + run['job_id']
            state, error, exact = run.get('retained_state', 'UNKNOWN'), run.get('retained_error'), None
            try:
                job = reader.job(doc, run)
                state, error = job['state'], job.get('error')
                if run.get('retained_result'):
                    result = reader.result(doc, run)
                    exact = {'kind': 'result', 'document_id': identifier, 'job_id': run['job_id'],
                             'input_revision': run['input_revision'], 'input_sha256': run['input_sha256'],
                             'result_sha256': canonical_hash(result)}
            except (ValueError, KeyError, TypeError, OSError) as failure:
                state = 'BROKEN'
                error = {'message': str(failure), 'recorded_error': error}
            node(key, doc['title'] + f' 계산 {i + 1}', 'result', state, node_type='run',
                 subtitle=STATE_LABELS.get(state, state), owner_id=identifier, owner_kind=doc['kind'],
                 job_id=run['job_id'], exact_reference=exact,
                 diagnostic={'run': run, 'error': error})
            edge(source_key, key, '계산 기록', status=state)
        if doc['kind'] == 'data':
            retained = doc.get('retained_inputs', {})
            data_ids = set(retained) | set(doc.get('unresolved_inputs', []))
            if isinstance(doc['draft'].get('data_id'), str) and doc['draft']['data_id']:
                data_ids.add(doc['draft']['data_id'])
            for data_id in sorted(data_ids):
                state, label, error = 'AVAILABLE', '원자료', None
                try:
                    check_id(data_id)
                    pair = reader.owner(identifier)._retained_source(doc, data_id)
                    if pair is None:
                        state, label = 'EXTERNAL', '보존하지 않은 원자료'
                    else:
                        _, receipt = pair
                        label = receipt['name']
                except (ValueError, KeyError, TypeError, OSError) as failure:
                    state, error = 'BROKEN', str(failure)
                key = 'source/' + identifier + '/' + data_id
                node(key, label, 'source', state, node_type='source', subtitle='Data 원자료',
                     owner_id=identifier, owner_kind='data', exact_reference=None,
                     diagnostic={'data_id': data_id, 'retained': retained.get(data_id), 'error': error})
                edge(key, source_key, '시험 원자료', status=state)
    from .connection_graph_view import attach_anchors, read_view, store_scope
    from .connection_graph_edit import actions_for_node
    for row in nodes.values():
        consumer = documents.get(row.get('consumer_id') or row.get('owner_id'))
        if consumer and consumer.get('kind') in {'pre', 'post'}:
            consumer = None
        row['actions'] = actions_for_node(consumer, row)
    try:
        view = read_view(workbench)
    except (OSError, ValueError, KeyError, TypeError) as error:
        # Damaged cosmetic state must not prevent independent domain reading.
        view = {'error': str(error), 'status': 'UNAVAILABLE'}
    graph = {'format': 'caelab.connection-graph/1', 'service_session_id': workbench.session_id,
            'scope': store_scope(workbench), 'view_state': view,
            'filter_document_ids': deepcopy(document_ids), 'selected_document_ids': identifiers, 'nodes': list(nodes.values()), 'edges': edges,
            'issues': issues, 'read_only': True, 'executed': False, 'engineering_release': 'NOT_RELEASED'}
    return attach_anchors(graph)
