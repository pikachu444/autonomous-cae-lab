"""Actual Qt/PDF tests when installed. All inputs and native replies are scripted.

A module-level skip means no C1 widget or PDF test ran on that host. No fake Qt.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
from pathlib import Path
import re
from types import SimpleNamespace

import pytest
pytest.importorskip('PySide6', reason='C1 real Qt/PDF is NOT_RUN without PySide6')
from PySide6.QtCore import QThreadPool, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from apps.research import report_pages
from apps.research.report_image_origin_dialog import ReportImageOriginDialog
from caelab import report_image as images
from report_image_fixture import fixture
from test_report_image_axis_c1 import declared_fixture, comparison_from_frozen
from test_report_image_core import owner
from test_report_image_origin_c1 import setup


@pytest.fixture(scope='module')
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.mark.parametrize('kind,label', [('physical', '물리시간 0.25 [s]'), ('static', '정적 단계 2 / 증분 9'),
    ('load', '정적 하중 매개변수 0.25 [1]'), ('model', '무차원 모델시간 0.25 [1]'),
    ('unknown', '축 의미 미제공 0.25'), ('frozen', '고정 관측: 정적 하중 매개변수 0.25')])
def test_same_axis_caption_reaches_qt_preview_markdown_and_pdf(qapp, tmp_path, kind, label):
    if kind == 'static':
        f = declared_fixture(tmp_path/'post', {'time': None, 'static': {'step': 2, 'increment': 9, 'load_parameter': .25}}, has_time=False)
    elif kind == 'frozen':
        f = fixture(tmp_path/'post')
        comparison_from_frozen(f, {'unit': '1', 'semantics': 'STATIC_LOAD_PARAMETER', 'value': .25})
    else:
        unit, semantics = {'physical': ('s', 'physical_time'), 'load': ('1', 'STATIC_LOAD_PARAMETER'),
            'model': ('1', 'DIMENSIONLESS_MODEL_TIME'), 'unknown': (None, None)}[kind]
        f = declared_fixture(tmp_path/'post', {'time': {'unit': unit, 'semantics': semantics, 'values': [.25]}})
    store = owner(tmp_path/'report'); doc = store.open(); binding = store.capture_image(doc['id'], f['command'])
    asset = store.content(doc['id'], [binding])['assets'][0]
    draft = images.apply_binding(doc['draft'], binding, asset['content'])
    draft['sections'][0]['text'] = 'Study 판단: 아직 미확인, 원값 검토 후 다음 연구 결정.'
    assets = {binding['id']: asset}
    page = report_pages.compose(draft, assets, QFont())
    assert label in page.toPlainText() and '실제 시각' not in page.toPlainText()
    assert label in report_pages.markdown(draft, assets)
    assert 'Study 판단' in page.toPlainText()
    pdf = tmp_path/'축 의미 보존.pdf'
    report_pages.atomic_export(pdf, lambda path: report_pages.pdf_document(page, path))
    assert pdf.read_bytes().startswith(b'%PDF-')
    assert re.search(rb'/Subtype\s*/Image', pdf.read_bytes())
    # No optional PDF extractor dependency is imposed; native glyph inspection
    # remains an explicit Windows acceptance item, not inferred from a header.


def test_origin_dialog_separates_retained_image_from_source_open_and_poll(qapp, setup, monkeypatch):
    s = setup; asset = s.store.content(s.doc['id'], [s.binding])['assets'][0]
    dialog = ReportImageOriginDialog(s.client, s.doc['id'], s.binding, asset)
    # Execute functions synchronously here to isolate actual widgets from worker
    # timing. The lifecycle test below covers real queued _Read delivery.
    def call(function):
        try: dialog.finished_read(function(), None)
        except Exception as error: dialog.finished_read(None, str(error))
    monkeypatch.setattr(dialog, '_call', call)
    before = deepcopy(s.doc['draft']); native = s.client.native; s.client.native = None
    dialog.show(); QTest.mouseClick(dialog.open_button, Qt.MouseButton.LeftButton)
    assert len(s.calls['spawn']) == 1 and '미완료' in dialog.message.text()
    QTest.mouseClick(dialog.poll_button, Qt.MouseButton.LeftButton)
    assert len(s.calls['spawn']) == 1 and '확인하지 못' in dialog.message.text()
    s.client.native = native
    QTest.mouseClick(dialog.poll_button, Qt.MouseButton.LeftButton)
    assert len(s.calls['activate']) == 1 and 'Properties' in dialog.message.text()
    assert s.store.read(s.doc['id'])['draft'] == before
    dialog.reject()


def test_origin_close_abandons_delivery_not_native_request_or_report(qapp, setup):
    import threading
    s = setup; asset = s.store.content(s.doc['id'], [s.binding])['assets'][0]
    dialog = ReportImageOriginDialog(s.client, s.doc['id'], s.binding, asset)
    entered, release = threading.Event(), threading.Event()
    def delayed():
        entered.set(); release.wait(3)
        return {'status': 'LAUNCH_UNCONFIRMED', 'message': 'late response must not replace the Report'}
    dialog.session.open = delayed
    dialog.show(); dialog.open_original()
    assert entered.wait(2)
    previous = dialog.message.text(); workers = list(dialog._workers)
    dialog.reject(); release.set()
    assert all(worker.completed.wait(3) for worker in workers)
    qapp.processEvents()
    assert dialog.result() == QDialog.DialogCode.Rejected and dialog.message.text() == previous
    assert s.store.read(s.doc['id']) == s.doc
