"""Bounded, explicit presentation of frozen condition selections for research.

The complete catalog stays in the immutable child record and canonical read.
This is a summary projection, never a catalog used for new execution/admission.
"""
from copy import deepcopy


FULL_SELECTION_LIMIT = 64
_REFERENCE_KEYS = frozenset(('selection_id', 'surface_a', 'surface_b'))


def condition_catalog_summary(catalog, declaration, catalog_revision, record_ref):
    selections = catalog.get('selections')
    if not isinstance(selections, list) or len(selections) <= FULL_SELECTION_LIMIT:
        return deepcopy(catalog), None
    indexed = {}
    for selection in selections:
        if not isinstance(selection, dict) or not isinstance(selection.get('id'), str):
            raise ValueError('Frozen catalog contains an invalid selection')
        identifier = selection['id']
        if identifier in indexed:
            raise ValueError('Frozen catalog contains duplicate selections')
        indexed[identifier] = selection
    referenced = set()

    def visit(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in _REFERENCE_KEYS:
                    if not isinstance(child, str) or child not in indexed:
                        raise ValueError('Frozen declaration references a missing catalog selection')
                    referenced.add(child)
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(declaration)
    # No silent empty/single-region representation of an unrecognized contract.
    if not referenced:
        return deepcopy(catalog), None
    projected = deepcopy(catalog)
    projected['selections'] = [deepcopy(row) for row in selections if row['id'] in referenced]
    projection = {'scope': 'DECLARATION_REFERENCED_SELECTIONS_ONLY',
        'source_catalog_revision': catalog_revision, 'source_record_ref': record_ref,
        'source_selection_count': len(selections), 'returned_selection_count': len(referenced),
        'omitted_selection_count': len(selections) - len(referenced),
        'complete_catalog_available_in': 'CANONICAL_EXPERIMENT_INSPECTION_AND_CHILD_RECORD',
        'execution_catalog': False}
    return projected, projection
