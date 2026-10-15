"""Cold citation reads use retained content only; no model or network calls."""
from copy import deepcopy
import json

import pytest

from apps.research.desktop import open_evidence_reference
from caelab.assist.literature import Literature, archive_digest


def never_fetch(*args, **kwargs):
    pytest.fail('An archived citation must not refetch a replacement source')


class LocalReadClient:
    def __init__(self, library):
        self.library = library

    def request(self, path, payload):
        assert path == '/api/workbench/assist' and payload['operation'] == 'literature.read'
        return self.library.read(**payload['arguments'])


def retained(tmp_path, *, abstract='A controlled public abstract.'):
    library = Literature(tmp_path, fetch=never_fetch)
    paper = library._normalize({'DOI': '10.0000/archive-check', 'title': ['Public source'],
        'author': [{'given': 'A', 'family': 'Researcher'}], 'URL': 'https://example.org/paper',
        'abstract': abstract, 'type': 'journal-article'})
    result = library.read(paper['paper_id'], {'kind': 'abstract'})
    digest = archive_digest(result)
    locator = deepcopy(result['segments'][0]['locator']) if result['segments'] else {'archive_id': digest}
    reference = {key: deepcopy(paper[key]) for key in ('paper_id', 'doi', 'url', 'title', 'authors', 'provider')}
    reference.update(locator=locator, read_status=result['status'],
        read_scope='abstract only; full text not read' if abstract else
            'bibliographic metadata only; abstract/full text not read')
    if abstract:
        reference['text'] = result['segments'][0]['text']
    return result, reference, tmp_path / (digest + '.json')


@pytest.mark.parametrize('abstract', ['A controlled public abstract.', None])
def test_cold_citation_reopens_the_same_archive_without_network(tmp_path, abstract):
    result, reference, path = retained(tmp_path, abstract=abstract)
    client = LocalReadClient(Literature(tmp_path, fetch=never_fetch))
    opened = open_evidence_reference(client, reference)
    assert opened['status'] == 'SOURCE_READ'
    assert opened['source']['paper'] == result['paper']
    assert opened['source']['segments'] == result['segments']
    assert opened['source']['status'] == result['status']


@pytest.mark.parametrize('change', ['text', 'title', 'status', 'locator'])
def test_changed_archive_cannot_be_displayed_as_the_original_source(tmp_path, change):
    result, reference, path = retained(tmp_path)
    if change == 'text':
        result['segments'][0]['text'] = 'A different conclusion.'
    elif change == 'title':
        result['paper']['title'] = 'Another source'
    elif change == 'locator':
        result['segments'][0]['locator']['archive_id'] = '0' * 64
    else:
        result['status'] = 'fulltext'
    path.write_text(json.dumps(result), encoding='utf-8')
    client = LocalReadClient(Literature(tmp_path, fetch=never_fetch))
    with pytest.raises(ValueError, match='archive changed'):
        open_evidence_reference(client, reference)


@pytest.mark.parametrize('key,value', [('title', 'Another title'), ('text', 'Different quoted text'),
    ('read_status', 'fulltext'), ('read_scope', 'full text read')])
def test_citation_cannot_change_the_archived_text_metadata_or_read_scope(tmp_path, key, value):
    result, reference, path = retained(tmp_path)
    reference[key] = value
    client = LocalReadClient(Literature(tmp_path, fetch=never_fetch))
    with pytest.raises(ValueError, match='citation'):
        open_evidence_reference(client, reference)


def test_missing_location_does_not_become_an_empty_successful_source_read(tmp_path):
    result, reference, path = retained(tmp_path)
    reference['locator'] = {'archive_id': reference['locator']['archive_id'], 'page': 99}
    client = LocalReadClient(Literature(tmp_path, fetch=never_fetch))
    with pytest.raises(ValueError, match='location is absent'):
        open_evidence_reference(client, reference)
