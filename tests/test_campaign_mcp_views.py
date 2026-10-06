"""The optional compact research view preserves every nonduplicate observation."""
from copy import deepcopy
from openscience.mcp_server import _compact_optimization_record


def test_compact_view_preserves_raw_signed_feedback_invalid_and_unknown():
    row = {'index': 1, 'values': {'x': 2}, 'model_experiment_id': 'E-original',
           'model_result_sha256': 'a' * 64, 'objective': {'value': -3, 'unit': 'N',
           'valid': False, 'reason': 'unqualified'}, 'feedback': {'objective': None},
           'unknown': ['physical'], 'decision': 'NOT_RELEASED',
           'model_settings': {'x': 2}, 'model_declaration': {'scope': 'UNKNOWN'}}
    original = {'status': 'COMPLETED_REVIEW_REQUIRED', 'decision': 'NOT_RELEASED',
                'evaluations': [row], 'incumbent': row, 'plan_sha256': 'b' * 64}
    retained = deepcopy(original)
    value = _compact_optimization_record(original)
    for key in ('evaluations',):
        assert value[key] == [{k: v for k, v in row.items()
                               if k not in ('model_settings', 'model_declaration')}]
    assert value['incumbent'] == value['evaluations'][0]
    assert value['plan_sha256'] == retained['plan_sha256']
    value['evaluations'][0]['objective']['value'] = 999
    assert original == retained


def test_compact_pending_read_keeps_frozen_plan_and_null_incumbent():
    original = {'status': 'PLANNED', 'decision': 'NOT_RELEASED',
                'plan': {'model_template': {'x': 1}}, 'evaluations': [], 'incumbent': None}
    value = _compact_optimization_record(original)
    assert value['plan'] == original['plan'] and value['incumbent'] is None
    assert value['view']['kind'] == 'VERIFIED_RETAINED_RECORD_COMPACT_VIEW'
