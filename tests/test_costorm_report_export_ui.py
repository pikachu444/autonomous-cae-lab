"""Retained discussion report export; no provider or calculation."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from copy import deepcopy
from pathlib import Path

import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from apps.research.costorm_report import ReportView


@pytest.mark.parametrize('html', [False, True])
def test_partial_export_failure_preserves_previous_file_and_retained_report(tmp_path, monkeypatch, html):
    app = QApplication.instance() or QApplication([])
    report = {'text': '관측값을 다시 확인해야 한다.[3]', 'status': 'INCOMPLETE_CITATIONS',
              'references': [{'number': '3', 'source': None}]}
    view = ReportView()
    view.set_report(report, '원자료 검토')
    assert view.body.document().find('인용 자료').block().text() == '인용 자료'
    original = deepcopy(view._report)
    target = tmp_path / ('report.html' if html else 'report.md')
    target.write_text('이전 출력', encoding='utf-8')
    write_text = Path.write_text
    def fail_after_write(path, text, **kwargs):
        write_text(path, text[:20], **kwargs)
        raise OSError('Explicit partial-output failure fixture')
    try:
        monkeypatch.setattr(Path, 'write_text', fail_after_write)
        with pytest.raises(OSError, match='partial-output'):
            view.export_to(target, html=html)
        assert target.read_text(encoding='utf-8') == '이전 출력'
        assert view._report == original
        assert list(tmp_path.glob('.cae-report-*')) == []
        monkeypatch.undo()
        view.export_to(target, html=html)
        assert '관측값을 다시 확인해야 한다.' in target.read_text(encoding='utf-8')
        assert '원자료를 확인할 수 없음' in target.read_text(encoding='utf-8')
        assert view._report == original
    finally:
        view.close()
        app.processEvents()
