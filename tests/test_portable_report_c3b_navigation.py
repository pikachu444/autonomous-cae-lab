"""A frozen report stays readable when its current source cannot be verified."""
from copy import deepcopy

import pytest

from caelab.portable_project import open_project
from test_portable_report_c3b import publish, report_assets, row_of, sample, store
from test_portable_report_c3b_gui_contract import host, method


@pytest.mark.parametrize('fault', ['missing', 'changed'])
def test_current_source_failure_does_not_advertise_verified_navigation(tmp_path, monkeypatch, fault):
    with store(tmp_path / 'original') as original:
        case = sample(original, tmp_path)
        _, made = publish(original, [case['report']['id'], case['material']['id']], tmp_path / 'copy')
    wb = open_project(tmp_path / 'copy')
    try:
        report = wb.document_read(row_of(made, 'report')['document_id'])
        healthy = report_assets(wb, report)[0]
        assert healthy['navigation_status'] == 'VERIFIED_TYPED_SOURCE'
        resolve = wb.report_documents.resolve_reference

        def unavailable(reference):
            if fault == 'missing':
                raise ValueError('현재 원자료를 읽을 수 없습니다.')
            current = deepcopy(resolve(reference))
            current['document']['draft']['settings']['parameters']['E'] += 1
            return current

        with monkeypatch.context() as patch:
            patch.setattr(wb.report_documents, 'resolve_reference', unavailable)
            row = report_assets(wb, report)[0]
        assert row['source_status'] == 'UNAVAILABLE'
        assert row['snapshot_status'] == 'AVAILABLE'
        assert row['navigation_status'] == 'SOURCE_UNAVAILABLE'
        assert row['navigation_reference'] is None
        assert row['content'] == healthy['content'] and row['reference'] == healthy['reference']
        assert report_assets(wb, report)[0]['navigation_reference'] == healthy['navigation_reference']
        assert wb.document_read(report['id']) == report and wb.manager.list() == []
    finally:
        assert wb.shutdown()['joined']


def test_unavailable_current_source_rechecks_without_opening_a_window():
    current = host()
    current.draft['sections'][0]['asset'] = {'id': 'Aold', 'reference': {'kind': 'post_image'}}
    current.document['portable_report_assets'] = {'Aold': {}}
    current.assets['Aold'] = {'navigation_reference': None, 'navigation_status': 'SOURCE_UNAVAILABLE'}
    method('open_source')(current)
    assert ('read',) in current.calls
    assert not current._source_windows
