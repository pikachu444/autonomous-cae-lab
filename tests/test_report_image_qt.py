"""Real Qt preview/PDF/Markdown integration tests; never substitute fake Qt.

Public synthetic PNG + saved Report owner. No ParaView, provider or physics run.
A module-level skip means NONE of these Qt paths ran on that host. Set
QT_QPA_PLATFORM=offscreen for headless Qt (Windows desktop may use its default).
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import base64
import re
import shutil
from types import SimpleNamespace

import pytest
pytest.importorskip('PySide6', reason='Real Qt/PDF rendering is NOT_RUN: PySide6 is not installed')
from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont, QTextDocument
from PySide6.QtWidgets import QApplication

from apps.research import report_pages
from caelab import report_image as images
from caelab.report_document import default_draft
from report_image_fixture import fixture
from test_report_image_core import owner, command


@pytest.fixture(scope='module')
def qapp():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def report(tmp_path):
    f = fixture(tmp_path/'합성 Post 계약 자료')
    store = owner(tmp_path/'연구 보관소'); doc = store.open()
    binding = store.capture_image(doc['id'], f['command'])
    asset = store.content(doc['id'], [binding])['assets'][0]
    draft = images.apply_binding(default_draft(), binding, asset['content'])
    draft['sections'][0].update(title='3D 고정 이미지', text='실제 native 렌더가 아닌 공개 합성 PNG 테스트')
    # A Study asset is passed through the same semantic block renderer.
    study = {'id': 'Astudy', 'reference': {'kind': 'document'}, 'source_status': 'AVAILABLE',
             'content': {'kind': 'document', 'document': {'kind': 'study', 'draft': {
                 'question': '강성의 영향을 분리하는가?',
                 'hypotheses': [{'statement': '가설: 경계 조건의 영향'}],
                 'decisions': [{'statement': '판단: 공학 승인 보류', 'status': 'UNKNOWN'}],
                 'next_observations': [{'question': '다음 연구: 시험 위치 확인'}]}}}}
    draft['sections'].insert(0, {'id': 'Estudy', 'title': 'Study 판단', 'text': '원판단 유지',
        'include': True, 'table': True, 'curve': True, 'asset': {'id': 'Astudy'}})
    return SimpleNamespace(f=f, store=store, doc=doc, binding=binding,
                           assets={binding['id']: asset, 'Astudy': study}, draft=draft)


def image_formats(document):
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and fragment.charFormat().isImageFormat():
                yield fragment.charFormat().toImageFormat()
            iterator += 1
        block = block.next()


def test_real_qt_resource_and_study_body_are_both_present(qapp, report):
    page = report_pages.compose(report.draft, report.assets, QFont())
    text = page.toPlainText()
    assert '판단: 공학 승인 보류' in text and '다음 연구: 시험 위치 확인' in text
    assert text.index('Study 판단') < text.index('3D 고정 이미지')
    image = page.resource(QTextDocument.ResourceType.ImageResource, QUrl('report-image:0'))
    assert not image.isNull() and (image.width(), image.height()) == (4, 3)
    assert image.pixelColor(0, 0).getRgb()[:3] == (60, 90, 120)
    formats = list(image_formats(page)); assert len(formats) == 1
    assert formats[0].width()/formats[0].height() == pytest.approx(4/3)


def test_qt_width_visibility_include_and_order(qapp, report):
    report.draft['sections'][-1]['image'] = {'show': True, 'width_percent': 50}
    page = report_pages.compose(report.draft, report.assets, QFont())
    assert list(image_formats(page))[0].width() == pytest.approx(257.5)
    report.draft['sections'].reverse()
    page = report_pages.compose(report.draft, report.assets, QFont())
    assert page.toPlainText().index('3D 고정 이미지') < page.toPlainText().index('Study 판단')
    report.draft['sections'][0]['image']['show'] = False
    assert not list(image_formats(report_pages.compose(report.draft, report.assets, QFont())))
    report.draft['sections'][0]['include'] = False
    assert '3D 고정 이미지' not in report_pages.compose(report.draft, report.assets, QFont()).toPlainText()


def test_saved_reopened_report_original_png_survives_markdown_and_pdf(qapp, report, tmp_path):
    # Save the real image binding, not the deliberately tiny Study display fixture.
    draft = deepcopy(report.draft); draft['sections'] = [draft['sections'][-1]]
    doc = command(report.store, report.doc, 'report.update', {'draft': draft})
    doc = command(report.store, doc, 'document.save')
    original = report.f['png'].read_bytes()
    shutil.rmtree(report.f['source'].parent)
    fresh = owner(tmp_path/'연구 보관소'); reopened = fresh.open(document_id=doc['id'])
    asset = fresh.content(doc['id'], [report.binding])['assets'][0]
    assert asset['source_status'] == 'UNAVAILABLE'
    assets = {report.binding['id']: asset}
    page = report_pages.compose(reopened['draft'], assets, QFont())
    assert '원자료 확인 불가' in page.toPlainText()
    md = report_pages.markdown(reopened['draft'], assets)
    encoded = re.search(r'src="data:image/png;base64,([^"]+)"', md).group(1)
    assert base64.b64decode(encoded) == original
    path = tmp_path/'보고서 출력.pdf'
    report_pages.atomic_export(path, lambda temporary: report_pages.pdf_document(page, temporary))
    data = path.read_bytes()
    assert data.startswith(b'%PDF-') and re.search(rb'/Subtype\s*/Image', data)
    # This checks actual PDF embedding, not byte-identical PNG compression in PDF.


def test_qt_export_failure_does_not_replace_previous_file(qapp, report, tmp_path):
    path = tmp_path/'원 보고서.pdf'; previous = b'PREVIOUS_OUTPUT'; path.write_bytes(previous)
    def fail(temporary):
        temporary.write_bytes(b'partial PDF')
        raise OSError('scripted output failure')
    with pytest.raises(OSError): report_pages.atomic_export(path, fail)
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob('.cae-report-*'))


def test_real_report_window_local_undo_and_last_good_preview(qapp, report, monkeypatch):
    from apps.research import report_window
    # No transport/native call is made. This uses the actual scoped Qt window.
    window = report_window.ReportWindow(SimpleNamespace(), auto_open=False)
    window.document = deepcopy(report.doc)
    draft = deepcopy(report.draft); draft['sections'] = [draft['sections'][-1]]
    window.draft = deepcopy(draft); window.assets = deepcopy(report.assets); window.populate()
    changed = deepcopy(draft); changed['sections'][0]['image'] = {'show': True, 'width_percent': 50}
    try:
        window.changed(changed); window.undo(); assert window.draft == draft
        window.redo(); assert window.draft == changed
        page = window._page
        def fail(*args): raise ValueError('scripted render failure')
        monkeypatch.setattr(report_window, 'compose', fail)
        window.render()
        assert window._page is page and window._page_stale
        assert window.draft == changed
        assert '이전 미리보기' in window.message.text()
    finally:
        window._closed = True; window.hide(); window.deleteLater(); qapp.processEvents()
