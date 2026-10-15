"""C1 metadata is not selected payload evidence. Synthetic adapter, solver0."""
import pytest
from caelab import dynamic_result_store as store
from test_dynamic_r2_integrity import attempt, mutate_same_size


def test_metadata_only_cannot_claim_verified_damaged_selected_frame(attempt):
    _, root = attempt
    catalog = store.read_attempt(root, metadata_only=True)
    frame = root / catalog.index['frames'][1]['artifact']['relative']
    size = frame.stat().st_size
    mutate_same_size(frame)
    assert frame.stat().st_size == size
    with pytest.raises(ValueError):
        store.select_frame(root, 1, metadata_only=True)
    with pytest.raises(ValueError, match='changed'):
        store.select_frame(root, 1)
    assert store.describe_attempt(root)['verification']['unselected_frame_bytes'] == 'DEFERRED'


@pytest.mark.parametrize('verification', ['selected', 'full'])
def test_explicit_false_checks_selected_payload_and_expected_identity(attempt, verification):
    _, root = attempt
    data = store.read_attempt(root, metadata_only=True)
    expected = dict(expected_result=data.verification['result'],
                    expected_job_id=data['job_id'], expected_snapshot_id=data['snapshot_id'],
                    expected_record=store.file_pin(root, root / 'contact_execution.json'),
                    expected_native=data.index['frames'][1]['native'])
    result = store.select_frame(root, 1, metadata_only=False, verification=verification, **expected)
    assert result['frame'] == store.read_attempt(root)['frames'][1]
    assert result['verification']['selected_frame_bytes'] == 'VERIFIED'
    assert result['verification']['unselected_frame_bytes'] == (
        'VERIFIED' if verification == 'full' else 'DEFERRED')
    assert result['verification']['scope'] == (
        'ALL_REFERENCED_BYTES' if verification == 'full' else 'INDEX_AND_TOPOLOGY')
    assert result['qualification'] == 'UNKNOWN'


@pytest.mark.parametrize('option', [True, 1, 0, None, 'false', [], {}])
def test_only_explicit_boolean_false_is_an_allowed_metadata_option(monkeypatch, option):
    monkeypatch.setattr(store, 'read_attempt', lambda *a, **k: pytest.fail('INVALID_OPTION_DID_IO'))
    with pytest.raises(ValueError, match='payload verification'):
        store.select_frame('need-not-exist', 0, metadata_only=option)


@pytest.mark.parametrize('verification', ['selected', 'full'])
@pytest.mark.parametrize('target', ['topology', 'frame'])
def test_same_size_damage_rejected_for_allowed_selection_options(attempt, verification, target):
    _, root = attempt
    data = store.read_attempt(root, metadata_only=True)
    pin = data.index['topology'] if target == 'topology' else data.index['frames'][1]['artifact']
    path = root / pin['relative']; size = path.stat().st_size
    mutate_same_size(path)
    assert path.stat().st_size == size
    with pytest.raises(ValueError, match='changed'):
        store.select_frame(root, 1, metadata_only=False, verification=verification)
    with pytest.raises(ValueError, match='payload verification'):
        store.select_frame(root, 1, metadata_only=True, verification=verification)
    assert store.describe_attempt(root)['verification']['unselected_frame_bytes'] == 'DEFERRED'


def test_metadata_stays_payload_free_and_normal_select_reads_only_selected(monkeypatch, attempt):
    _, root = attempt
    reads, original = [], store._json
    def tracked(folder, pin, *a, **k):
        reads.append(pin['relative'])
        return original(folder, pin, *a, **k)
    monkeypatch.setattr(store, '_json', tracked)
    view = store.describe_attempt(root)
    assert reads == []
    assert view['verification']['scope'] == 'INDEX_ONLY'
    assert view['verification']['unselected_frame_bytes'] == 'DEFERRED'
    selected = store.select_frame(root, 1, metadata_only=False)
    assert reads == ['dynamic-frames/topology.json', 'dynamic-frames/frame0002.json']
    assert 'fields' in selected['frame'] and 'artifact' not in selected['frame']
    assert selected['verification']['selected_frame_bytes'] == 'VERIFIED'


def test_invalid_verification_and_unrecognized_options_remain_rejected(attempt):
    _, root = attempt
    with pytest.raises(ValueError, match='integrity verification'):
        store.select_frame(root, 1, verification='metadata')
    with pytest.raises(TypeError):
        store.select_frame(root, 1, skip_hash=True)
