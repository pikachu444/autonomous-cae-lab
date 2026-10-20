"""Local source archive with a reconstructible, optional Haystack BM25 index."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import hashlib
import io
import json
import re
import threading
import uuid

TEXT_EXTENSIONS = frozenset({'.md', '.markdown', '.txt', '.csv', '.dat', '.asc', '.json',
                             '.log', '.sta', '.cvg', '.inp', '.out', '.mess', '.comm'})


def selected_source_refs(context):
    """Exact source pins for a new request; saved legacy drafts remain readable."""
    identifiers = context.get('selected_document_ids', [])
    if (not isinstance(identifiers, list) or len(identifiers) > 32
            or any(not isinstance(item, str) for item in identifiers)
            or len(set(identifiers)) != len(identifiers)):
        raise ValueError('Select at most 32 distinct local sources')
    references = context.get('selected_sources')
    if references is None:
        if identifiers:
            raise ValueError('Review and pin the selected source revisions before a new round')
        return []
    if not isinstance(references, list) or len(references) > 32:
        raise ValueError('Select at most 32 exact local source revisions')
    seen, result = set(), []
    for reference in references:
        if (not isinstance(reference, dict) or set(reference) != {'document_id', 'revision'}
                or not isinstance(reference['document_id'], str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', reference['document_id'])
                or type(reference['revision']) is not int or reference['revision'] < 1
                or reference['document_id'] in seen):
            raise ValueError('Each selected source requires a distinct document and positive exact revision')
        seen.add(reference['document_id'])
        result.append(deepcopy(reference))
    if 'selected_document_ids' in context and set(identifiers) != seen:
        raise ValueError('Selected source identities and revisions differ; review the Sources selection')
    return result


def read_segments(path, *, data=None):
    """Extract one byte snapshot; PDF pages retain extraction limitations."""
    path = Path(path)
    suffix = path.suffix.lower()
    data = path.read_bytes() if data is None else data
    failed = []
    if suffix == '.pdf':
        from pypdf import PdfReader
        segments = []
        for number, page in enumerate(PdfReader(io.BytesIO(data)).pages, 1):
            try:
                text = page.extract_text() or ''
            except Exception as exc:
                failed.append({'page': number, 'reason': type(exc).__name__})
                continue
            if text.strip():
                segments.append({'locator': {'page': number}, 'text': text,
                                 'content_kind': 'extracted_text',
                                 'limitations': ['Tables, formulas and figures are not independently verified.']})
            else:
                failed.append({'page': number, 'reason': 'No extractable text; OCR was not performed.'})
        return segments, failed
    if suffix not in TEXT_EXTENSIONS:
        raise ValueError('Supported sources: PDF, Markdown, CSV and UTF-8 solver text')
    with io.TextIOWrapper(io.BytesIO(data), encoding='utf-8', newline='') as stream:
        text = stream.read()
    if any((ord(char) < 32 and char not in '\t\n\r\f') or 127 <= ord(char) < 160 for char in text):
        raise ValueError('Select plain UTF-8 text; binary/control bytes are not supported')
    if not text.strip():
        raise ValueError('Select a nonempty UTF-8 text source')
    section, start, lines, segments = '', 1, [], []
    def flush(end):
        if ''.join(lines).strip():
            segments.append({'locator': {'section': section, 'line_start': start, 'line_end': end},
                             'text': ''.join(lines), 'content_kind': 'source_text'})
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        if suffix in {'.md', '.markdown'} and re.match(r'^#{1,6}\s', line):
            flush(number - 1)
            section, start, lines = line.lstrip('#').strip(), number, []
        lines.append(line)
    flush(len(text.splitlines()))
    return segments, failed


def _retrieval_chunks(segments):
    """New revisions only: retain exact extracted text and line/page provenance."""
    if not any(len(segment['text'].encode('utf-8')) > 8000 for segment in segments):
        return segments
    from haystack import Document
    from haystack.components.preprocessors import DocumentSplitter
    splitter = DocumentSplitter(split_by='line', split_length=40, split_overlap=0)
    result = []
    for segment in segments:
        text = segment['text']
        if len(text.encode('utf-8')) <= 8000:
            result.append(segment)
            continue
        chunks = splitter.run(documents=[Document(content=text)])['documents']
        if ''.join(chunk.content for chunk in chunks) != text:
            raise ValueError('Source splitting must preserve the complete extracted text')
        for chunk in chunks:
            item = deepcopy(segment)
            item['text'] = chunk.content
            locator = item['locator']
            if 'line_start' in locator:
                locator['line_start'] += text[:chunk.meta['split_idx_start']].count('\n')
                locator['line_end'] = locator['line_start'] + len(chunk.content.splitlines()) - 1
            elif 'page' in locator:
                locator['page_chunk'] = chunk.meta['split_id']
            result.append(item)
    return result


class KnowledgeStore:
    def __init__(self, root, *, source_roots=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.source_roots = [Path(p).resolve() for p in (source_roots or [self.root])]
        self._lock = threading.RLock()
        self._store = None
        self._index_generation = None
        self._manifest = self.root / 'documents.json'
        self._data = json.loads(self._manifest.read_text(encoding='utf-8')) if self._manifest.exists() else {'documents': {}}

    def _reload(self):
        # Another current local owner may revoke after an earlier inspection.
        data = (json.loads(self._manifest.read_text(encoding='utf-8'))
                if self._manifest.exists() else {'documents': {}})
        if data != self._data:
            self._store = None  # A cached index never retains an old local grant.
        self._data = data

    def check_access(self, document_id, revision, *, workspace_id='local', collections=None):
        with self._lock:
            self._reload()
            document = self._data['documents'].get(document_id)
            if not document or not self._allowed(document, workspace_id, collections):
                raise PermissionError('Source is missing, revoked or outside the current access scope')
            if type(revision) is not int or revision < 1 or revision > document['latest_revision']:
                raise ValueError('Unknown exact document revision')
            expected = getattr(self, '_portable_bindings', {}).get((document_id, revision))
            if expected is not None and document.get('portable_revisions', {}).get(str(revision)) != expected:
                raise PermissionError('KNOWLEDGE_ID_COLLISION: 현지의 다른 내용에 대한 권한을 원 frozen 자료에 재사용할 수 없습니다.')
            return {'status': 'PERMITTED', 'document_id': document_id, 'revision': revision}

    def revision_details(self, document_id, revision, *, workspace_id='local', collections=None):
        from ..portable_research_knowledge import revision_details
        return revision_details(self, document_id, revision, workspace_id=workspace_id, collections=collections)

    def _save(self):
        temporary = self._manifest.with_suffix('.tmp')
        temporary.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self._manifest)
        self._store = None

    def _allowed(self, document, workspace_id, collections=None):
        return (not document.get('revoked') and
                (document['access_scope'] == 'public' or workspace_id in document['access_scope']) and
                (collections is None or document['collection'] in collections))

    def ingest(self, source, collection, metadata=None, *, workspace_id='local', document_id=None):
        metadata = deepcopy(metadata or {})
        path = Path(source).resolve()
        if not any(path.is_relative_to(root) for root in self.source_roots):
            raise PermissionError('Source is outside the configured local import roots')
        data = path.read_bytes()
        segments, failed = read_segments(path, data=data)
        segments = _retrieval_chunks(segments)
        with self._lock:
            self._reload()
            document_id = document_id or uuid.uuid4().hex
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', document_id):
                raise ValueError('Invalid document ID')
            old = self._data['documents'].get(document_id)
            if old and not self._allowed(old, workspace_id, [collection]):
                raise PermissionError('Document revision is outside the current access scope')
            scope = metadata.pop('access_scope', deepcopy(old['access_scope']) if old else [workspace_id])
            if scope != 'public' and (not isinstance(scope, list) or workspace_id not in scope):
                raise ValueError('access_scope must be public or include the importing workspace')
            if old and scope != old['access_scope']:
                raise ValueError('Revision cannot silently change document access scope')
            revision = (old['latest_revision'] + 1) if old else 1
            directory = self.root / document_id / str(revision)
            directory.mkdir(parents=True, exist_ok=True)
            (directory / ('original' + path.suffix.lower())).write_bytes(data)
            title = metadata.pop('title', path.name)
            rows = []
            for index, segment in enumerate(segments):
                row = {'document_id': document_id, 'revision': revision, 'title': title,
                       'collection': collection, 'access_scope': scope, 'segment_id': str(index), **segment}
                row['locator']['segment_id'] = str(index)
                rows.append(row)
            archive = {'document_id': document_id, 'revision': revision, 'segments': rows,
                       'metadata': metadata, 'sha256': hashlib.sha256(data).hexdigest(), 'failed_segments': failed}
            (directory / 'segments.json').write_text(json.dumps(archive, ensure_ascii=False), encoding='utf-8')
            self._data['documents'][document_id] = {'latest_revision': revision, 'collection': collection,
                                                  'access_scope': scope, 'title': title, 'revoked': False}
            if old and old.get('portable_revisions'):
                self._data['documents'][document_id]['portable_revisions'] = deepcopy(old['portable_revisions'])
            self._save()
        return {'status': 'INGESTED', 'document_id': document_id, 'revision': revision,
                'segments_read': len(rows), 'failed_segments': failed, 'sha256': archive['sha256']}

    def source(self, document_id, revision=None, locator=None, *, workspace_id='local', collections=None):
        with self._lock:
            self._reload()
            document = self._data['documents'].get(document_id)
            if not document or not self._allowed(document, workspace_id, collections):
                raise PermissionError('Source is missing, revoked or outside the current access scope')
            if revision is None and document.get('portable_revisions'):
                raise ValueError('ARCHIVED_REVISION_REQUIRED: 보존된 문헌은 정확한 개정을 선택하세요.')
            if document.get('portable_revisions') and type(revision) is not int:
                raise ValueError('ARCHIVED_REVISION_REQUIRED: 보존 문헌의 개정은 정확한 정수여야 합니다.')
            revision = document['latest_revision'] if revision is None else int(revision)
            if revision < 1 or revision > document['latest_revision']:
                raise ValueError('Unknown document revision')
            from ..portable_research_knowledge import archived_source
            carried = archived_source(self, document, document_id, revision, locator)
            if carried is not None:
                return carried
            archive = json.loads((self.root / document_id / str(revision) / 'segments.json').read_text(encoding='utf-8'))
            rows = archive['segments']
            if locator:
                rows = [r for r in rows if all(r['locator'].get(k) == v for k, v in locator.items())]
            return {'status': 'AVAILABLE' if rows else 'NO_MATCHING_SEGMENTS', 'document_id': document_id, 'revision': revision,
                    'segments': rows, 'failed_segments': archive['failed_segments'],
                    'title': rows[0]['title'] if rows else document['title'],
                    'collection': document['collection'], 'sha256': archive['sha256']}

    def list(self, *, workspace_id='local', collections=None):
        with self._lock:
            self._reload()
            return {'status': 'OK', 'documents': [dict(document_id=key, **deepcopy(doc))
                for key, doc in self._data['documents'].items() if self._allowed(doc, workspace_id, collections)]}

    def revoke(self, document_id, *, workspace_id='local'):
        with self._lock:
            self._reload()
            document = self._data['documents'].get(document_id)
            if not document or not self._allowed(document, workspace_id):
                raise PermissionError('Document is outside the current access scope')
            document['revoked'] = True
            self._save()
        return {'status': 'REVOKED', 'document_id': document_id}

    def rebuild(self):
        from haystack import Document
        from haystack.document_stores.in_memory import InMemoryDocumentStore
        with self._lock:
            self._reload()
            from ..portable_research_knowledge import _archive
            store = InMemoryDocumentStore(bm25_algorithm='BM25L', shared=False,
                bm25_tokenization_regex=r'(?u)\b\w+\b')
            documents = []
            for document_id, doc in self._data['documents'].items():
                if doc.get('revoked'):
                    continue
                retained = _archive(self, document_id, doc['latest_revision'], doc)
                archive = (retained[1] if retained else json.loads(
                    (self.root / document_id / str(doc['latest_revision']) / 'segments.json').read_text(encoding='utf-8')))
                for row in archive['segments']:
                    documents.append(Document(id=f"{document_id}:{row['revision']}:{row['segment_id']}",
                                              content=row['text'], meta={k: v for k, v in row.items() if k != 'text'}))
            if documents:
                store.write_documents(documents)
            self._store = store
        return {'status': 'INDEXED', 'segments_indexed': len(documents), 'method': 'Haystack BM25L'}

    def search(self, query, collections=None, filters=None, top_k=10, *, workspace_id='local', source_refs=None):
        from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
        if not isinstance(query, str) or not query.strip():
            raise ValueError('A nonempty query is required')
        if not 1 <= int(top_k) <= 100:
            raise ValueError('top_k must be between 1 and 100')
        filters = filters or {}
        if set(filters) - {'document_ids', 'content_kind'}:
            raise ValueError('Only document_ids and content_kind filters are supported')
        with self._lock:
            self._reload()
            allowed = [key for key, doc in self._data['documents'].items()
                       if self._allowed(doc, workspace_id, collections) and
                       ('document_ids' not in filters or key in filters['document_ids'])]
            if not allowed:
                return {'status': 'OK', 'hits': [], 'method': 'Haystack BM25L'}
            if source_refs is None:
                # Explicit search may reuse the index, but not bypass archive integrity.
                from ..portable_research_knowledge import _archive
                for identifier in allowed:
                    doc = self._data['documents'][identifier]
                    _archive(self, identifier, doc['latest_revision'], doc)
                if self._store is None:
                    self.rebuild()
                selected_store = self._store
            else:
                # Reuse the same BM25 implementation for these immutable archived
                # revisions. This temporary view is never a second persisted index.
                from haystack import Document
                from haystack.document_stores.in_memory import InMemoryDocumentStore
                references = selected_source_refs({'selected_sources': source_refs})
                selected_store = InMemoryDocumentStore(bm25_algorithm='BM25L', shared=False,
                    bm25_tokenization_regex=r'(?u)\b\w+\b')
                rows = []
                for reference in references:
                    archive = self.source(**reference, workspace_id=workspace_id, collections=collections)
                    if reference['document_id'] in allowed:
                        rows.extend(archive['segments'])
                if not rows:
                    return {'status': 'OK', 'hits': [], 'method': 'Haystack BM25L'}
                if sum(len(row['text'].encode('utf-8')) for row in rows) > 4 * 1024 * 1024:
                    raise ValueError('Selected retrieval text exceeds 4 MiB; choose fewer sources')
                selected_store.write_documents([Document(
                    id=f"{row['document_id']}:{row['revision']}:{row['segment_id']}",
                    content=row['text'], meta={key: value for key, value in row.items() if key != 'text'})
                    for row in rows])
            conditions = [{'field': 'meta.document_id', 'operator': 'in', 'value': allowed}]
            if 'content_kind' in filters:
                conditions.append({'field': 'meta.content_kind', 'operator': '==', 'value': filters['content_kind']})
            found = InMemoryBM25Retriever(document_store=selected_store, top_k=int(top_k)).run(
                query=query, filters={'operator': 'AND', 'conditions': conditions})['documents']
            hits = [{**deepcopy(doc.meta), 'text': doc.content, 'score': doc.score} for doc in found if doc.score > 0]
        return {'status': 'OK', 'hits': hits, 'method': 'Haystack BM25L'}
