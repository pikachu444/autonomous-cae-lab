"""C1 input-gate regression. Fixtures are NOT actual FE execution evidence."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
from unittest.mock import patch
import pytest

from caelab.workbench import Workbench
from caelab.storage import canonical_hash
from caelab import law_native_fe as fe, material_fe_transfer as transfer
from caelab.law_native_provenance import admitted_guard_paths

FROZEN = Path(__file__).parent/'fixtures/c1-frozen-simulation.json'
SHA = '7e92939e6fd75d64a81849483171846dfc0ca6f4f841f88a5fb7fcf5bb710a91'
FORBIDDEN = ('path', 'command', 'argv', 'module', 'factory', 'script', 'executable',
             'output', 'output_root', 'runtime', 'snapshot_path')


@pytest.fixture
def settings():
    assert FROZEN.stat().st_size == 150563
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest() == SHA
    return json.loads(FROZEN.read_text(encoding='utf-8'))['simulation_draft']['settings']


@pytest.fixture
def wb(tmp_path):
    instance = Workbench(tmp_path/'workspace')
    try:
        yield instance
    finally:
        assert instance.shutdown()['joined']


def _resign_for_adversarial_test(s):
    """Attacker-computable hashes must NOT bypass independent typed validation."""
    record = s['source_receipt'];review = record['review'];source = review['source']
    source.pop('snapshot_sha256', None);source['snapshot_sha256'] = canonical_hash(source)
    review.pop('review_sha256', None);review['review_sha256'] = canonical_hash(review)
    token = json.dumps({'backend': fe.law.FE, 'review_sha256': review['review_sha256'],
                        'source_sha256': source['snapshot_sha256']}, sort_keys=True)
    record['native_property'] = token
    record['applied_target']['current_assignment_property'] = token
    record.pop('assignment_sha256', None);record['assignment_sha256'] = canonical_hash(record)


def test_exact_native_input_two_gates_preserve_all_provenance(settings, wb):
    before = deepcopy(settings)
    # transfer.file_hash is used for live CAS only, not current-code identity.
    with patch.object(transfer, 'file_hash', side_effect=AssertionError('SOURCE_GUARD_READ')):
        first = wb._settings(fe.law.FE, settings)
        second = wb._settings(fe.law.FE, first)
    assert first == second == settings == before and first is not settings
    source = second['source_receipt']['review']['source']
    assert len(source['source_guard']) == 3 and len(source['law_source']['files']) == 10
    assert source['snapshot_sha256'] == '3677ecc567333c5c28c454dd02934b80958cbdabe0005ea036021fd943f75096'
    assert second['source_receipt']['assignment_sha256'] == '469bf171043872392a200187a33abfac5e70e30efee80e8a3b9c0c5936a3717d'
    assert admitted_guard_paths(settings) == frozenset(
        ('source_receipt', 'review', 'source', 'source_guard', i, 'path') for i in range(3))
    assert wb.manager.list() == []


def test_execute_research_run_domain_both_settings_entries(settings, wb, monkeypatch):
    from caelab import research_execution
    calls = [];original = wb._settings
    def observed(backend, value):
        calls.append(deepcopy(value))
        return original(backend, value)
    monkeypatch.setattr(wb, '_settings', observed)
    def adapter_fixture(backend, value, *, output):
        assert backend == fe.law.FE and value == settings
        return {'execution_status': 'SUCCEEDED', 'responses': {}, 'checks': [],
                'diagnostics': {'FE_execution': 'NOT_RUN_CONTROLLED_ROUTING_FIXTURE'}}
    monkeypatch.setattr(research_execution.evaluation, 'run', adapter_fixture)
    result = wb._execute('simulation.run', {'backend': fe.law.FE, 'settings': settings}, 'JC1routing')
    assert len(calls) == 2 and all(v == settings for v in calls)
    assert result['diagnostics']['FE_execution'] == 'NOT_RUN_CONTROLLED_ROUTING_FIXTURE'
    assert wb.manager.list() == []


@pytest.mark.parametrize('section', ('law', 'mesh', 'boundary', 'solver'))
@pytest.mark.parametrize('key', FORBIDDEN)
def test_execution_override_even_with_matching_self_hashed_review_is_rejected(settings, section, key):
    settings[section][key] = '/arbitrary/server/file'
    settings['source_receipt']['review']['interface']['settings'][section][key] = '/arbitrary/server/file'
    _resign_for_adversarial_test(settings)
    with pytest.raises((ValueError, TypeError)):
        Workbench._settings(None, fe.law.FE, settings)


@pytest.mark.parametrize('key', FORBIDDEN)
def test_unknown_provenance_field_is_not_an_execution_escape(settings, key):
    settings['source_receipt'][key] = '/arbitrary/server/file'
    _resign_for_adversarial_test(settings)
    with pytest.raises(ValueError):
        Workbench._settings(None, fe.law.FE, settings)


@pytest.mark.parametrize('backend', ('material.law_native', 'material.mfront.user', 'material.felupe', 'not.registered'))
@pytest.mark.parametrize('key', FORBIDDEN)
def test_other_backend_security_unmodified(backend, key):
    with pytest.raises(ValueError):
        Workbench._settings(None, backend, {'nested': [{key: '/server/override'}]})


def test_other_backend_cannot_borrow_valid_receipt(settings):
    with pytest.raises(ValueError, match='server path'):
        Workbench._settings(None, 'material.felupe', {'source_receipt': settings['source_receipt']})


@pytest.mark.parametrize('mutation', ('guard_path', 'guard_extra', 'missing_guard', 'corrupt_guard',
                                     'changed_actual', 'changed_reviewed_law', 'source_text',
                                     'assignment_target', 'new_selection', 'false_applied'))
def test_corrupt_or_self_rehashed_receipts_do_not_pass(settings, mutation):
    record = settings['source_receipt'];review = record['review'];source = review['source']
    if mutation == 'guard_path':
        source['source_guard'][0]['path'] = r'C:\Windows\System32\cmd.exe'
    elif mutation == 'guard_extra':
        source['source_guard'][0]['module'] = 'arbitrary'
    elif mutation == 'missing_guard':
        source['source_guard'].pop()
    elif mutation == 'corrupt_guard':
        source['source_guard'][0]['sha256'] = 'NOT_A_DIGEST'
    elif mutation == 'changed_actual':
        settings['law']['parameters']['k0'] = 300.
    elif mutation == 'changed_reviewed_law':
        # Matching executable and reviewed settings still differ from saved law.
        settings['law']['parameters']['k0'] = 300.
        review['interface']['settings']['law']['parameters']['k0'] = 300.
    elif mutation == 'source_text':
        row = next(iter(source['law_source']['files'].values()))
        row['text'] += '\n# untrusted self-hashed source change\n'
        row['sha256'] = hashlib.sha256(row['text'].encode()).hexdigest()
    elif mutation == 'assignment_target':
        record['applied_target']['geometry']['brep_sha256'] = '0'*64
    elif mutation == 'new_selection':
        record['selection']['solver_id'] = 'DifferentSolver'
    elif mutation == 'false_applied':
        record['applied'] = False
    _resign_for_adversarial_test(settings)
    with pytest.raises(ValueError):
        Workbench._settings(None, fe.law.FE, settings)


def test_original_receipt_corruption_detected_before_allowing_path(settings):
    settings['source_receipt']['review']['source']['source_guard'][0]['path'] += '.tampered'
    with pytest.raises(ValueError, match='hash'):
        Workbench._settings(None, fe.law.FE, settings)


def test_no_receipt_means_no_path_permission():
    s = fe.default_settings();s['law']['path'] = '/arbitrary/file'
    with pytest.raises(ValueError, match='server path'):
        Workbench._settings(None, fe.law.FE, s)


def test_registered_input_and_table_boundary_unchanged(wb):
    with pytest.raises(ValueError, match='registered data_id'):
        wb._settings('structure.calculix.frozen', {'snapshot_path': '/server/model.json'})
    with pytest.raises(ValueError, match='uploaded data_id'):
        wb._settings('files.table', {'path': '/etc/passwd'})
    with pytest.raises(ValueError):
        wb._settings('material.mfront.user', {'module': 'arbitrary_source_approval'})


def test_changed_current_kernel_blocks_fe_but_cold_assignment_stays_readable(settings):
    record = settings['source_receipt'];actual = transfer.source_identity()
    fake = deepcopy(actual);next(iter(fake['files'].values()))['sha256'] = '0'*64
    with patch.object(transfer, 'source_identity', return_value=fake):
        assert transfer.cold_assignment(record) == record
        with pytest.raises(ValueError, match='INTERFACE_SOURCE_CONFLICT'):
            Workbench._settings(None, fe.law.FE, settings)
