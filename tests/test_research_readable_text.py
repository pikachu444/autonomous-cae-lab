"""Native display boundaries and lossless copying; no provider execution."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont, QImage, QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from apps.research.readable_text import ReadingBrowser, markdown_document, show_markdown
from apps.research.costorm_report import ReportView, report_markdown
from test_research_expert_ui import ui_owner, open_window


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def fragments(document):
    block = document.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                yield fragment
            iterator += 1
        block = block.next()


def test_markdown_math_copy_code_and_unsupported_original(app):
    source = r'**Measured** \(E=\frac{17}{0.004}\,\text{MPa}\) [17]' + '\n\n' + r'\[\unsupported{[17]}\]'
    source += '\n\n`[17] <a> & \\(x\\)`\n\n```python\na < b && c > d\n[17]\n```'
    browser = ReadingBrowser()
    document = show_markdown(browser, source, links={'17': 'source:0'})
    assert document.source_text == source and len(document.math_sources) == 1
    assert document.math_failures == [r'\[\unsupported{[17]}\]']
    assert '**Measured**' not in browser.toPlainText()
    assert r'\[\unsupported{[17]}\]' in browser.toPlainText()
    assert '<a> &' in browser.toPlainText() and 'a < b && c > d' in browser.toPlainText()
    anchors = [f for f in fragments(document) if f.charFormat().isAnchor()]
    assert [f.text() for f in anchors] == ['[17]']
    browser.selectAll()
    copied = browser.selected_source_text()
    assert r'\(E=\frac{17}{0.004}\,\text{MPa}\)' in copied
    assert '\ufffc' not in copied
    assert any(f.charFormat().fontWeight() > QFont.Weight.Normal for f in fragments(document) if 'Measured' in f.text())
    browser.close()


def test_authored_links_images_html_cannot_read_resources_or_spoof_citations(app, tmp_path):
    local = tmp_path / 'private.png'
    image = QImage(4, 4, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)
    assert image.save(str(local))
    source = '[fake](source:0) [other](citation:0) [remote](https://example.invalid)\n\n'
    source += '![private](' + local.as_uri() + ') ![remote](https://example.invalid/a.png)\n\n'
    source += '<img src="' + local.as_uri() + '"> <b>literal</b>\n\nVerified [17]'
    document = markdown_document(source, QFont(), links={'17': 'source:0'})
    # A forced resource request must remain empty even for an existing file.
    assert not document.resource(QTextDocument.ResourceType.ImageResource, QUrl(local.as_uri()))
    assert not document.resource(QTextDocument.ResourceType.ImageResource, QUrl('https://example.invalid/a.png'))
    assert document.blocked_resources
    assert not any(f.charFormat().isImageFormat() for f in fragments(document))
    assert '<img ' not in document.toHtml() and '<a href="https:' not in document.toHtml()
    anchors = [f for f in fragments(document) if f.charFormat().isAnchor()]
    assert [(f.text(), f.charFormat().anchorHref()) for f in anchors] == [('[17]', 'source:0')]
    assert '<b>literal</b>' in document.toPlainText()


def test_report_exports_original_equations_and_exact_sources(app, tmp_path):
    text = r'**Result** \(\nu\) [17]' + '\n\n' + '\\[\n\\sigma=\\frac{17}{0.004}\\,\\text{MPa}\n\n\\]'
    report = {'status': 'DRAFT', 'text': text, 'references': [{'number': '17',
        'source': {'title': 'Measurement', 'document_id': 'Kexact', 'revision': 3,
                   'locator': 'line:4', 'text': '17 MPa'}}]}
    original = deepcopy(report)
    view = ReportView()
    view.set_report(report)
    assert len(view.body.document().math_sources) == 2
    view.body.selectAll()
    copied = view.body.selected_source_text()
    assert '\\[\n\\sigma' in copied and '\\nu' in copied and '[17]' in copied
    received = []
    view.source_requested.connect(received.append)
    view.open_citation(QUrl('source:0'))
    view.open_citation(QUrl('file:///private'))
    view.open_citation(QUrl('source:-1'))
    assert received == [report['references'][0]['source']]
    md, html = tmp_path / 'report.md', tmp_path / 'report.html'
    view.export_to(md)
    view.export_to(html, html=True)
    assert md.read_text(encoding='utf-8') == report_markdown(report)
    exported = QTextDocument()
    exported.setHtml(html.read_text(encoding='utf-8'))
    assert r'\(\nu\)' in exported.toPlainText() and r'\frac{17}{0.004}' in exported.toPlainText()
    assert 'cae-math:' not in html.read_text(encoding='utf-8')
    assert report == original
    view.close()


def test_clipboard_selection_restores_only_selected_math_and_unicode(app, monkeypatch):
    class Clipboard:
        value = ''
        def setText(self, text):
            self.value = text
    clipboard = Clipboard()
    monkeypatch.setattr(QApplication, 'clipboard', staticmethod(lambda: clipboard))
    browser = ReadingBrowser()
    document = show_markdown(browser, r'한글 😀 before \(E\) after')
    browser.selectAll()
    QTest.keyClick(browser, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert clipboard.value == r'한글 😀 before \(E\) after'
    image = next(f for f in fragments(document) if f.charFormat().isImageFormat())
    cursor = QTextCursor(document)
    cursor.setPosition(image.position())
    cursor.setPosition(image.position() + 1, QTextCursor.MoveMode.KeepAnchor)
    browser.setTextCursor(cursor)
    QTest.keyClick(browser, Qt.Key.Key_Insert, Qt.KeyboardModifier.ControlModifier)
    assert clipboard.value == r'\(E\)'
    browser.close()


def test_math_width_is_bounded_without_erasing_original(app):
    original = r'\[E=\frac{17}{0.004}\,\text{MPa}\]'
    document = markdown_document(original, QFont())
    width, height = next(iter(document.math_sizes.values()))
    document.fit_math_width(width * .9)
    image = next(f.charFormat().toImageFormat() for f in fragments(document) if f.charFormat().isImageFormat())
    assert image.width() == pytest.approx(width * .9) and image.height() == pytest.approx(height * .9)
    document.fit_math_width(width * 2)
    image = next(f.charFormat().toImageFormat() for f in fragments(document) if f.charFormat().isImageFormat())
    assert image.width() == pytest.approx(width)
    document.fit_math_width(width * .5)
    assert document.toPlainText() == original and document.source_text == original
    assert document.math_failures == [original]


def test_report_reading_preserves_composer_selection_and_scroll_without_commands(app, ui_owner):
    owner, manager, calls, _ = ui_owner
    window = open_window(app, owner)
    window.resize(1100, 780)
    window.show()
    displayed = deepcopy(window.document)
    displayed['turns'] = [{'id': 'T' + str(index), 'author': 'material', 'status': 'ANSWERED',
        'text': 'Read this retained discussion. ' * 80, 'response': {'sources': []}}
        for index in range(3)]
    try:
        window._show_document(displayed)
        window.conversation_pages.setTabVisible(1, True)
        app.processEvents()
        window.turns.setCurrentRow(1)
        window.turns.verticalScrollBar().setValue(100)
        window.question.setPlainText('Keep my unsubmitted Korean question: 경계 조건?')
        draft = deepcopy(window.edited_draft())
        card = window.turns._cards['T1']
        cursor = card.body.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(9, QTextCursor.MoveMode.KeepAnchor)
        card.body.setTextCursor(cursor)
        before_operations = list(window.client.operations)
        window.conversation_pages.setCurrentWidget(window.report_view)
        app.processEvents()
        assert window.editor.isHidden() and window.turn_context.isHidden() and window.selected_reply.isHidden()
        window.report_view.back.click()
        for _ in range(3):
            app.processEvents()
        assert not window.editor.isHidden() and not window.turn_context.isHidden()
        assert window.edited_draft() == draft and window.turns.currentRow() == 1
        assert window.turns.verticalScrollBar().value() == 100
        assert card.body.textCursor().selectedText() == 'Read this'
        assert window.client.operations == before_operations and not calls and not manager.list()
    finally:
        window._allow_close = True
        window.close()
