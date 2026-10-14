"""Native report reader/export of the actual retained Co-STORM article."""
from copy import deepcopy
from html import escape

from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)
from apps.research.readable_text import ReadingBrowser, markdown_document, show_markdown


def source_note(reference):
    source = reference.get('source')
    if not source:
        return '원자료를 확인할 수 없음'
    parts = [str(source.get('title') or '선택 원자료')]
    if source.get('job_id'):
        parts += ['계산 ' + str(source['job_id']),
                  '입력 저장본 ' + str(source.get('input_revision', '')),
                  '입력 SHA256 ' + str(source.get('input_sha256', '')),
                  '선택 ' + ', '.join(source.get('selection', source.get('response_selection', [])))]
    else:
        parts += ['자료 ' + str(source.get('document_id', '')),
                  '저장본 ' + str(source.get('revision', '')),
                  '위치 ' + str(source.get('locator', ''))]
    return ' / '.join(parts)


def report_markdown(report, title='토론 보고서'):
    """Exact original citations and archive locators, including unresolved ones."""
    text = '# ' + title + '\n\n' + str(report.get('text', '')) + '\n\n## 인용 자료\n\n'
    for reference in report.get('references', []):
        text += '[' + str(reference['number']) + '] ' + source_note(reference) + '\n\n'
        excerpt = (reference.get('source') or {}).get('text')
        if excerpt:
            text += '\n'.join('> ' + line for line in str(excerpt).splitlines()) + '\n\n'
    if report.get('status') != 'DRAFT':
        text += '원자료가 확인되지 않은 인용이 있습니다. 보고서에서 해당 표시를 확인하세요.\n'
    return text


class ReportView(QWidget):
    source_requested = Signal(object)
    generate_requested = Signal()
    return_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._report, self._title, self._snapshot = None, '토론 보고서', None
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.status = QLabel('토론 내용을 보고서로 작성할 수 있습니다.')
        self.status.setWordWrap(True)
        self.generate = QPushButton('보고서 작성')
        self.generate.clicked.connect(self.generate_requested)
        self.export = QPushButton('내보내기…')
        self.export.clicked.connect(self.choose_export)
        self.back = QPushButton('대화로 돌아가기')
        self.back.clicked.connect(self.return_requested)
        row.addWidget(self.status, 1)
        row.addWidget(self.generate)
        row.addWidget(self.export)
        row.addWidget(self.back)
        layout.addLayout(row)
        self.body = ReadingBrowser()
        self.body.setObjectName('discussionReport')
        self.body.setOpenLinks(False)
        self.body.setOpenExternalLinks(False)
        self.body.anchorClicked.connect(self.open_citation)
        layout.addWidget(self.body, 1)
        self.set_report(None)

    def set_report(self, report, title='토론 보고서'):
        snapshot = (report, title)
        if snapshot == self._snapshot:
            return
        self._snapshot = deepcopy(snapshot)
        self._report, self._title = deepcopy(report), title
        self.export.setEnabled(bool(report))
        if not report:
            self.body.clear()
            self.status.setText('토론 내용을 보고서로 작성할 수 있습니다.')
            return
        links = {str(row['number']): 'source:' + str(index)
                 for index, row in enumerate(report.get('references', [])) if row.get('source')}
        document = show_markdown(self.body, str(report.get('text', '')), links=links)
        # Generated URLs never initiate navigation; only our explicit exact-reference
        # anchors below are actionable in this view.
        citations = '<h2>인용 자료</h2><ol>'
        for index, row in enumerate(report.get('references', [])):
            source = row.get('source')
            label = '[' + str(row['number']) + '] ' + str((source or {}).get('title') or '원자료')
            if source:
                citations += '<li><a href="source:' + str(index) + '">' + escape(label) + '</a></li>'
            else:
                citations += '<li>' + escape(label) + ' — 원자료 없음</li>'
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        cursor.insertHtml(citations + '</ol>')
        self.status.setText('토론 보고서' if report.get('status') == 'DRAFT'
                            else '확인되지 않은 인용이 있습니다.')

    def open_citation(self, url):
        if not self._report or url.scheme() != 'source':
            return
        try:
            index = int(url.path())
            if index < 0:
                return
            reference = self._report['references'][index]
        except (ValueError, IndexError, KeyError):
            return
        if reference.get('source'):
            self.source_requested.emit(deepcopy(reference['source']))

    def export_to(self, path, *, html=False):
        if not self._report:
            raise ValueError('작성된 보고서가 없습니다.')
        text = report_markdown(self._report, self._title)
        if html:
            document = markdown_document(text, self.body.font(), math_images=False)
            text = document.toHtml()
        from .report_pages import atomic_export
        atomic_export(path, lambda temporary: temporary.write_text(text, encoding='utf-8'))
        return str(path)

    def choose_export(self):
        if not self._report:
            return
        path, selected = QFileDialog.getSaveFileName(self, '보고서 내보내기', '토론 보고서.md',
            'Markdown (*.md);;HTML (*.html)')
        if not path:
            return
        try:
            self.export_to(path, html='HTML' in selected)
        except (OSError, ValueError) as error:
            self.status.setText('저장하지 못했습니다. 이전 파일은 유지됩니다: ' + str(error))
