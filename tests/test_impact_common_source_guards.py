"""Exact source diagnostics and law-assignment guards; no converter or solver."""
from copy import deepcopy

import pytest

from caelab.impact_model import parse_inp, validate_settings
from caelab.impact_reference_bindings import KEY, accept_review, review, snapshot
from caelab.impact_source import SourceError
from caelab.storage import canonical_hash
from examples.impact.cohesive_model import settings


def test_flat_error_retains_compiled_and_physical_line():
    spans = [{'flat_line': 1, 'count': 2, 'file': 'part.inc', 'source_line': 20}]
    with pytest.raises(SourceError) as failure:
        parse_inp('*NODE\n1,not-a-number,0,0\n', spans)
    assert failure.value.file == 'part.inc'
    assert failure.value.line == 21
    assert failure.value.flat_line == 2


def test_law117_assignment_change_requires_explicit_source_review():
    original = settings()
    original['responses'] = []
    original[KEY] = snapshot(original)
    validate_settings(original)
    changed = deepcopy(original)
    changed['source']['text'] = changed['source']['text'].replace(
        '2,5,6,7,8,9,10,11,12', '4,5,6,7,8,9,10,11,12')
    with pytest.raises(SourceError, match='대응이 바뀌'):
        validate_settings(changed)
    report = review(changed)
    assert report['changed']
    law_row = next(row for row in report['after'] if row['selection'] == ['cohesive', 0, 'material'])
    assert law_row['source']['members'] == [{'association': 'CELLS', 'native_id': 4}]
    accepted = accept_review(changed, expected_definition_sha256=canonical_hash(changed),
                             expected_review_sha256=report['review_sha256'], acknowledged=True)
    validate_settings(accepted)
    assert original[KEY] != accepted[KEY]
    assert original['source']['text'] != accepted['source']['text']
