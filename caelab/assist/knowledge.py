"""Local source archive with a reconstructible, optional Haystack BM25 index."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import re
import threading
import uuid


def read_segments(path):
    """Extract supported source text; PDF pages retain extraction limitations."""
    path = Path(path)
    suffix = path.suffix.lower()
    failed = []
    if suffix == '.pdf':
        from pypdf import PdfReader
        segments = []
        for number, page in enumerate(PdfReader(path).pages, 1):
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
    if suffix not in {'.md', '.markdown', '.txt', '.csv'}:
        raise ValueError('Supported sources: PDF, Markdown, UTF-8 text and CSV')
    text = path.read_text(encoding='utf-8')
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
        segments, failed = read_segments(path)
        data = path.read_bytes()
        with self._lock:
            document_id = document_id or uuid.uuid4().hex
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', document_id):
                raise ValueError('Invalid document ID')
            old = self._data['documents'].get(document_id)
            if old and not self._allowed(old, workspace_id, [collection]):
                raise PermissionError('Document revision is outside the current access scope')
            scope = metadata.pop('access_scope', [workspace_id])
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
            self._save()
        return {'status': 'INGESTED', 'document_id': document_id, 'revision': revision,
                'segments_read': len(rows), 'failed_segments': failed, 'sha256': archive['sha256']}

    def source(self, document_id, revision=None, locator=None, *, workspace_id='local', collections=None):
        with self._lock:
            document = self._data['documents'].get(document_id)
            if not document or not self._allowed(document, workspace_id, collections):
                raise PermissionError('Source is missing, revoked or outside the current access scope')
            revision = document['latest_revision'] if revision is None else int(revision)
            if revision < 1 or revision > document['latest_revision']:
                raise ValueError('Unknown document revision')
            archive = json.loads((self.root / document_id / str(revision) / 'segments.json').read_text(encoding='utf-8'))
            rows = archive['segments']
            if locator:
                rows = [r for r in rows if all(r['locator'].get(k) == v for k, v in locator.items())]
            return {'status': 'AVAILABLE', 'document_id': document_id, 'revision': revision,
                    'segments': rows, 'failed_segments': archive['failed_segments']}

    def list(self, *, workspace_id='local', collections=None):
        with self._lock:
            return {'status': 'OK', 'documents': [dict(document_id=key, **deepcopy(doc))
                for key, doc in self._data['documents'].items() if self._allowed(doc, workspace_id, collections)]}

    def revoke(self, document_id, *, workspace_id='local'):
        with self._lock:
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
            store = InMemoryDocumentStore(bm25_algorithm='BM25L', shared=False,
                bm25_tokenization_regex=r'(?u)\b\w+\b')
            documents = []
            for document_id, doc in self._data['documents'].items():
                if doc.get('revoked'):
                    continue
                archive = json.loads((self.root / document_id / str(doc['latest_revision']) / 'segments.json').read_text(encoding='utf-8'))
                for row in archive['segments']:
                    documents.append(Document(id=f"{document_id}:{row['revision']}:{row['segment_id']}",
                                              content=row['text'], meta={k: v for k, v in row.items() if k != 'text'}))
            if documents:
                store.write_documents(documents)
            self._store = store
        return {'status': 'INDEXED', 'segments_indexed': len(documents), 'method': 'Haystack BM25L'}

    def search(self, query, collections=None, filters=None, top_k=10, *, workspace_id='local'):
        from haystack.components.retrievers.in_memory import InMemoryBM25Retriever
        if not isinstance(query, str) or not query.strip():
            raise ValueError('A nonempty query is required')
        if not 1 <= int(top_k) <= 100:
            raise ValueError('top_k must be between 1 and 100')
        filters = filters or {}
        if set(filters) - {'document_ids', 'content_kind'}:
            raise ValueError('Only document_ids and content_kind filters are supported')
        with self._lock:
            allowed = [key for key, doc in self._data['documents'].items()
                       if self._allowed(doc, workspace_id, collections) and
                       ('document_ids' not in filters or key in filters['document_ids'])]
            if not allowed:
                return {'status': 'OK', 'hits': [], 'method': 'Haystack BM25L'}
            if self._store is None:
                self.rebuild()
            conditions = [{'field': 'meta.document_id', 'operator': 'in', 'value': allowed}]
            if 'content_kind' in filters:
                conditions.append({'field': 'meta.content_kind', 'operator': '==', 'value': filters['content_kind']})
            found = InMemoryBM25Retriever(document_store=self._store, top_k=int(top_k)).run(
                query=query, filters={'operator': 'AND', 'conditions': conditions})['documents']
            hits = [{**deepcopy(doc.meta), 'text': doc.content, 'score': doc.score} for doc in found if doc.score > 0]
        return {'status': 'OK', 'hits': hits, 'method': 'Haystack BM25L'}
