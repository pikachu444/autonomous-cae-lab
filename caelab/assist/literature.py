"""Thin Crossref metadata discovery and explicitly reported public source reads."""
from __future__ import annotations
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from io import BytesIO
import ipaddress
import json
import hashlib
from pathlib import Path
import re
import socket
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.hidden = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.hidden += 1
        if tag in {'p', 'div', 'section', 'h1', 'h2', 'h3', 'br'}:
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in {'script', 'style'} and self.hidden:
            self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value):
    parser = _Text()
    parser.feed(value or '')
    return unescape(''.join(parser.parts)).strip()


def _public_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Only public HTTPS source URLs are supported')
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('Source URL resolves to a nonpublic address')


def fetch_url(url, *, max_bytes=16 * 1024 * 1024):
    _public_url(url)
    # Check redirected destination before following, as links are untrusted metadata.
    from urllib.request import HTTPRedirectHandler, build_opener
    class PublicRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, message, headers, newurl):
            _public_url(newurl)
            return super().redirect_request(request, fp, code, message, headers, newurl)
    request = Request(url, headers={'User-Agent': 'Autonomous-CAE-Lab/0.1 (public research)',
                                    'Accept': 'application/json, application/pdf, text/html, application/xml, text/plain'})
    with build_opener(PublicRedirect()).open(request, timeout=20) as response:
        content = response.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise ValueError('Public source exceeds the configured size bound')
        return content, response.headers.get_content_type(), response.url


class Literature:
    def __init__(self, root=None, *, fetch=None):
        self.fetch = fetch or fetch_url
        self.root = Path(root).resolve() if root else None
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
        cache = self.root / 'papers.json' if self.root else None
        self._papers = json.loads(cache.read_text(encoding='utf-8')) if cache and cache.exists() else {}

    def _persist(self):
        if self.root:
            (self.root / 'papers.json').write_text(json.dumps(self._papers, ensure_ascii=False), encoding='utf-8')

    def _archive(self, result, raw=None):
        if self.root:
            digest = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            for segment in result['segments']:
                segment['locator']['archive_id'] = digest
            (self.root / (digest + '.json')).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
            if raw is not None:
                (self.root / (digest + '.source')).write_bytes(raw)
        return result

    def _normalize(self, item):
        doi = item.get('DOI', '').lower()
        identifier = 'doi:' + doi if doi else item.get('URL')
        if not identifier:
            return None
        issued = item.get('published', item.get('issued', {})).get('date-parts', [[None]])
        paper = {'paper_id': identifier, 'doi': doi or None, 'title': '; '.join(item.get('title', [])),
                 'authors': [' '.join(filter(None, [a.get('given'), a.get('family')])) for a in item.get('author', [])],
                 'year': issued[0][0], 'url': item.get('URL'), 'provider': 'crossref',
                 'version': item.get('type'), 'abstract': plain_text(item.get('abstract')) or None,
                 'fulltext_candidates': [{'url': link['URL'], 'content_type': link.get('content-type'),
                                         'version': link.get('content-version')} for link in item.get('link', []) if link.get('URL')],
                 'licenses': item.get('license', []), 'retrieved_at': datetime.now(timezone.utc).isoformat()}
        self._papers[identifier] = paper
        self._persist()
        return paper

    def search(self, query, providers=None, filters=None, *, top_k=10):
        providers = ['crossref'] if providers is None else providers
        if providers != ['crossref']:
            raise ValueError('Only the configured Crossref provider is installed')
        if not isinstance(query, str) or not query.strip() or not 1 <= int(top_k) <= 100:
            raise ValueError('A query and top_k between 1 and 100 are required')
        filters = filters or {}
        if set(filters) - {'from_year', 'until_year', 'type'}:
            raise ValueError('Unsupported Crossref filter')
        parameters = {'query.bibliographic': query, 'rows': int(top_k)}
        clauses = []
        for key, value in filters.items():
            if key == 'type':
                clauses.append('type:' + str(value))
            else:
                clauses.append(('from-pub-date:' if key == 'from_year' else 'until-pub-date:') + str(int(value)))
        if clauses:
            parameters['filter'] = ','.join(clauses)
        try:
            data, _, _ = self.fetch('https://api.crossref.org/works?' + urlencode(parameters))
            payload = json.loads(data)
            found = [self._normalize(item) for item in payload['message']['items']]
            # Same DOI is one work; preserve Crossref's actual version/type metadata.
            papers = list({p['paper_id']: p for p in found if p}.values())
            return {'status': 'OK', 'papers': papers, 'provider': 'crossref'}
        except Exception as exc:
            return {'status': 'UNAVAILABLE', 'papers': [], 'provider': 'crossref',
                    'error': type(exc).__name__, 'detail': str(exc)}

    def read(self, paper_id, locator=None):
        if locator and locator.get('archive_id'):
            archive_id = locator['archive_id']
            if not self.root or not re.fullmatch(r'[a-f0-9]{64}', archive_id):
                raise ValueError('Invalid or unavailable literature archive')
            result = json.loads((self.root / (archive_id + '.json')).read_text(encoding='utf-8'))
            if result['paper_id'] != paper_id:
                raise ValueError('Literature archive belongs to another paper')
            selected = {key: value for key, value in locator.items() if key != 'archive_id'}
            result['segments'] = [s for s in result['segments'] if all(s['locator'].get(k) == v for k, v in selected.items())]
            return result
        paper = self._papers.get(paper_id)
        if paper is None and paper_id.startswith('doi:'):
            try:
                data, _, _ = self.fetch('https://api.crossref.org/works/' + quote(paper_id[4:], safe=''))
                paper = self._normalize(json.loads(data)['message'])
            except Exception as exc:
                return {'status': 'access_unavailable', 'paper_id': paper_id, 'segments': [],
                        'error': type(exc).__name__, 'detail': str(exc)}
        if paper is None:
            raise ValueError('Unknown paper ID; first search or supply a DOI identifier')
        locator = locator or {}
        if set(locator) - {'url', 'page', 'kind'}:
            raise ValueError('Supported locators: fulltext candidate URL, PDF page, kind=abstract')
        failures = []
        if locator.get('kind') != 'abstract':
            candidates = paper['fulltext_candidates']
            if locator.get('url'):
                candidates = [c for c in candidates if c['url'] == locator['url']]
                if not candidates:
                    raise ValueError('URL is not an identified fulltext candidate')
            for candidate in candidates:
                try:
                    data, mime, retrieved_url = self.fetch(candidate['url'])
                    if mime == 'application/pdf' or data.startswith(b'%PDF-'):
                        from pypdf import PdfReader
                        pages = PdfReader(BytesIO(data)).pages
                        selected = [int(locator['page'])] if 'page' in locator else list(range(1, len(pages) + 1))
                        rows = []
                        for number in selected:
                            if not 1 <= number <= len(pages):
                                raise ValueError('Requested page does not exist')
                            text = pages[number - 1].extract_text() or ''
                            if text.strip():
                                rows.append({'locator': {'page': number, 'url': retrieved_url}, 'text': text,
                                             'content_kind': 'extracted_text'})
                            else:
                                failures.append({'url': retrieved_url, 'page': number, 'reason': 'No extractable text'})
                    elif mime in {'text/plain', 'text/html', 'application/xml', 'text/xml', 'application/xhtml+xml'}:
                        raw = data.decode('utf-8')
                        # HTML landing pages are not verified fulltext merely because HTTP succeeded.
                        if mime in {'text/html', 'application/xhtml+xml', 'application/xml', 'text/xml'} and not re.search(
                                r'<(?:article\b|[^>]*class=["\'][^"\']*full[-_]?text)', raw, re.I):
                            raise ValueError('Retrieved HTML does not identify article fulltext')
                        text = raw if mime == 'text/plain' else plain_text(raw)
                        rows = [{'locator': {'url': retrieved_url}, 'text': text, 'content_kind': 'source_text'}] if text.strip() else []
                    else:
                        raise ValueError('Unsupported fulltext content type: ' + mime)
                    if rows:
                        return self._archive({'status': 'fulltext', 'paper_id': paper_id, 'paper': paper, 'segments': rows,
                                'read_scope': 'extracted text only', 'table_figure_status': 'unverified',
                                'access_failures': failures}, data)
                except Exception as exc:
                    failures.append({'url': candidate['url'], 'reason': str(exc), 'error': type(exc).__name__})
        rows = [{'locator': {'kind': 'abstract'}, 'text': paper['abstract'], 'content_kind': 'abstract'}] if paper['abstract'] else []
        return self._archive({'status': 'abstract_only' if rows else 'metadata_only', 'paper_id': paper_id,
                'paper': paper, 'segments': rows, 'fulltext_access': 'unavailable', 'access_failures': failures,
                'table_figure_status': 'unverified'})

    def import_paper(self, paper_id, knowledge, collection, *, workspace_id='local', locator=None):
        result = self.read(paper_id, locator)
        if not result['segments']:
            return {**result, 'import_status': 'NOT_IMPORTED'}
        # Store fetched source text, never an AI summary. Explicit call is the import intent.
        path = knowledge.root / ('literature-' + __import__('hashlib').sha256(paper_id.encode()).hexdigest() + '.txt')
        path.write_text('\n\n'.join(s['text'] for s in result['segments']), encoding='utf-8')
        ingested = knowledge.ingest(path, collection, {'title': result['paper']['title'], 'paper_id': paper_id,
                                   'read_status': result['status'], 'source_locators': [s['locator'] for s in result['segments']]},
                                   workspace_id=workspace_id)
        return {**ingested, 'read_status': result['status'], 'import_status': 'IMPORTED'}
