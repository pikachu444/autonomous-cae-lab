"""Native Markdown and bounded math display, with no authored resource loading.

Documents retain their source text. This is typesetting, not expression evaluation.
HTML exports can request literal equations instead of nonportable memory images.
"""
from functools import lru_cache
from io import BytesIO
import re
import uuid

from PySide6.QtCore import QByteArray, QRegularExpression, QUrl
from PySide6.QtGui import QColor, QImage, QKeySequence, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextImageFormat
from PySide6.QtWidgets import QApplication, QMenu, QTextBrowser
from matplotlib.font_manager import FontProperties
from matplotlib.mathtext import math_to_image


_MATH = re.compile(
    r'(?P<ds>\\{1,2})\[(?P<display>.*?)(?P=ds)\]|'
    r'(?P<ins>\\{1,2})\((?P<inline>.*?)(?P=ins)\)|'
    r'(?<!\\)\$\$(?P<dollars_display>.*?)\$\$|'
    r'(?<![\\$])\$(?!\s)(?P<dollars_inline>[^\n$]+?)(?<!\s)\$(?!\$)', re.S)


class ReadingDocument(QTextDocument):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.source_text = ''
        self.math_sources = {}
        self.math_sizes = {}
        self.math_failures = []
        self.blocked_resources = []

    def loadResource(self, resource_type, name):
        # Never delegate authored URLs to QTextBrowser or its local-file loader.
        self.blocked_resources.append(name.toString())
        return QByteArray()

    def fit_math_width(self, width):
        changes = []
        block = self.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                formatting = fragment.charFormat()
                if formatting.isImageFormat():
                    image = formatting.toImageFormat()
                    name = image.name()
                    if name in self.math_sizes:
                        changes.append((fragment.position(), fragment.length(), image, name))
                iterator += 1
            block = block.next()
        for position, length, image, name in reversed(changes):
            original_width, original_height = self.math_sizes[name]
            scale = min(1, max(1, width) / original_width)
            cursor = QTextCursor(self)
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            if scale >= .85:
                image.setWidth(original_width * scale)
                image.setHeight(original_height * scale)
                cursor.setCharFormat(image)
            else:
                # Long expressions remain legible as exact source, rather than
                # clipping or shrinking values below the ordinary reading size.
                formatting = QTextCharFormat()
                formatting.setFontFixedPitch(True)
                cursor.insertText(self.math_sources[name], formatting)
                self.math_failures.append(self.math_sources[name])


class ReadingBrowser(QTextBrowser):
    def selected_source_text(self):
        selected = self.textCursor()
        parts = []
        sources = getattr(self.document(), 'math_sources', {})
        cursor = QTextCursor(self.document())
        position = selected.selectionStart()
        while position < selected.selectionEnd():
            cursor.setPosition(position)
            cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
            formatting = cursor.charFormat()
            text = cursor.selectedText()
            if formatting.isImageFormat():
                text = sources.get(formatting.toImageFormat().name(), text)
            parts.append(text.replace('\u2029', '\n').replace('\u2028', '\n'))
            position = cursor.position()
        return ''.join(parts)

    def copy(self):
        if self.textCursor().hasSelection():
            # setText lets Qt own the clipboard data. Returning a Python-owned
            # QMimeData from the Qt virtual can outlive its wrapper on Windows.
            QApplication.clipboard().setText(self.selected_source_text())

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy()
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        action = menu.addAction('복사', self.copy)
        action.setEnabled(self.textCursor().hasSelection())
        action.setShortcut(QKeySequence.StandardKey.Copy)
        menu.addAction('모두 선택', self.selectAll)
        menu.exec(event.globalPos())
        menu.deleteLater()


def _code_ranges(text):
    ranges, fence, start, offset = [], None, 0, 0
    for line in text.splitlines(keepends=True):
        match = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if fence is None and match:
            fence, start = match.group(1), offset
        elif fence and match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
            ranges.append((start, offset + len(line)))
            fence = None
        elif fence is None and line.startswith('    '):
            ranges.append((offset, offset + len(line)))
        offset += len(line)
    if fence is not None:
        ranges.append((start, len(text)))
    ranges.extend((match.start(), match.end()) for match in re.finditer(r'(`+)([^`]*?)\1', text, re.S))
    return ranges


@lru_cache(maxsize=128)
def _math_png(expression, points):
    stream = BytesIO()
    # Blank lines in display math are TeX whitespace; no symbol/value rewriting.
    expression = ' '.join(expression.splitlines())
    try:
        math_to_image('$' + expression + '$', stream, prop=FontProperties(size=points),
                      dpi=192, format='png', color='#1c2c3d')
    except (ValueError, RuntimeError, RecursionError):
        return None
    return stream.getvalue()


def _strip_authored_links(document):
    spans = []
    block = document.begin()
    while block.isValid():
        fragment = block.begin()
        while not fragment.atEnd():
            value = fragment.fragment()
            if value.isValid() and value.charFormat().isImageFormat():
                formatting = value.charFormat().toImageFormat()
                alt = formatting.property(QTextFormat.Property.ImageAltText) or '이미지'
                spans.append((value.position(), value.length(), str(alt)))
            if value.isValid() and value.charFormat().isAnchor():
                spans.append((value.position(), value.length(), value.charFormat()))
            fragment += 1
        block = block.next()
    for position, length, formatting in reversed(spans):
        cursor = QTextCursor(document)
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
        if isinstance(formatting, str):
            cursor.insertText('[' + formatting + ' — 이미지 표시 안 함]', QTextCharFormat())
            continue
        formatting.setAnchor(False)
        formatting.setAnchorHref('')
        formatting.setFontUnderline(False)
        formatting.setForeground(QColor('#1c2c3d'))
        cursor.setCharFormat(formatting)


def markdown_document(text, font, *, links=None, parent=None, math_images=True):
    """Only ``links`` supplied by an owner may create actionable citations."""
    text = str(text)
    document = ReadingDocument(parent)
    document.source_text = text
    document.setDefaultFont(font)
    document.setDocumentMargin(8)
    protected = _code_ranges(text)
    nonce, formulas, offset, parts = uuid.uuid4().hex, [], 0, []
    for match in _MATH.finditer(text):
        if any(start < match.end() and end > match.start() for start, end in protected):
            continue
        token = 'CAEMATH' + nonce + str(len(formulas)) + 'END'
        expression = next(match.group(key) for key in ('display', 'inline', 'dollars_display', 'dollars_inline')
                          if match.group(key) is not None)
        display = match.group('display') is not None or match.group('dollars_display') is not None
        parts.extend((text[offset:match.start()], '\n\n' + token + '\n\n' if display else token))
        formulas.append((token, match.group(0), expression, display))
        offset = match.end()
    parts.append(text[offset:])
    features = QTextDocument.MarkdownFeature.MarkdownDialectGitHub | QTextDocument.MarkdownFeature.MarkdownNoHTML
    document.setMarkdown(''.join(parts), features)
    _strip_authored_links(document)
    for index, (token, original, expression, display) in enumerate(formulas):
        cursor = document.find(token)
        if cursor.isNull():
            continue
        points = max(12 if display else 10, font.pointSizeF())
        png = _math_png(expression, points) if math_images and len(expression) <= 2000 and index < 128 else None
        if png:
            image = QImage.fromData(png, 'PNG')
            image.setDevicePixelRatio(2)
            name = QUrl('cae-math:' + nonce + str(index))
            document.addResource(QTextDocument.ResourceType.ImageResource, name, image)
            formatting = QTextImageFormat()
            formatting.setName(name.toString())
            formatting.setWidth(image.width() / 2)
            formatting.setHeight(image.height() / 2)
            formatting.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignMiddle)
            formatting.setToolTip(original)
            cursor.insertImage(formatting)
            document.math_sources[name.toString()] = original
            document.math_sizes[name.toString()] = (image.width() / 2, image.height() / 2)
        else:
            formatting = cursor.charFormat()
            formatting.setFontFixedPitch(True)
            cursor.insertText(original, formatting)
            if math_images:
                document.math_failures.append(original)
    expression = QRegularExpression(r'\[(\d+)\]')
    cursor = document.find(expression)
    while not cursor.isNull():
        number = cursor.selectedText()[1:-1]
        destination = (links or {}).get(number)
        is_code = cursor.charFormat().fontFixedPitch() or cursor.blockFormat().nonBreakableLines()
        if destination and not is_code:
            formatting = cursor.charFormat()
            formatting.setAnchor(True)
            formatting.setAnchorHref(destination)
            formatting.setForeground(QColor('#205e9d'))
            formatting.setFontUnderline(True)
            cursor.setCharFormat(formatting)
        elif number in (links or {}) and destination is None and not is_code:
            cursor.insertText('[' + number + '] (원자료 없음)')
        cursor = document.find(expression, cursor.selectionEnd())
    block = document.begin()
    while block.isValid():
        cursor = QTextCursor(block)
        formatting = cursor.blockFormat()
        formatting.setLineHeight(125, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
        cursor.setBlockFormat(formatting)
        block = block.next()
    document.setUndoRedoEnabled(False)
    return document


def show_markdown(browser, text, *, links=None):
    document = markdown_document(text, browser.font(), links=links, parent=browser)
    browser.setDocument(document)
    browser._reading_document = document  # Retain the Python loadResource override.
    return document
