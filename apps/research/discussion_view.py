"""Readable native discussion turns; identities remain item data, not prose."""
from copy import deepcopy
import math

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QVBoxLayout)
from apps.research.readable_text import ReadingBrowser, show_markdown


def author_label(turn, roles=()):
    if turn.get('author') == 'user':
        return '사용자'
    protocol_labels = {'Default Background Researcher': '배경 조사',
        'Background discussion moderator': '진행자', 'Background discussion expert': '배경 토론',
        'General Knowledge Provider': '자료 검토', 'Moderator': '진행자'}
    if turn.get('protocol') == 'costorm' and turn.get('author') in protocol_labels:
        return protocol_labels[turn['author']]
    role = next((row for row in roles if row.get('id') == turn.get('author')), {})
    return str(role.get('label', role.get('name', role.get('title', turn.get('author', 'Participant')))))


def turn_text(turn):
    text = turn.get('text')
    if isinstance(text, str) and text:
        return text
    response = turn.get('response') or {}
    return str(response.get('reason') or response.get('error') or
               ('No response returned (' + str(turn.get('status', 'UNKNOWN')) + ').'))


class _TurnCard(QFrame):
    def __init__(self, view, item, turn, roles):
        super().__init__(view)
        self.view, self.item, self.identifier = view, item, turn['id']
        self.setObjectName('turnCard')
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet('#turnCard { border: 1px solid #ccd8e4; border-radius: 6px; background: palette(base); }')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        heading = QHBoxLayout()
        self.author = QLabel(author_label(turn, roles))
        font = self.author.font(); font.setBold(True); self.author.setFont(font)
        heading.addWidget(self.author)
        heading.addStretch()
        topic = (turn.get('topic') or {}).get('title', '')
        if topic:
            name = QLabel(topic)
            name.setToolTip(topic)
            name.setWordWrap(True)
            heading.addWidget(name)
        self.reply = QPushButton('답글')
        self.reply.setFlat(True)
        self.reply.clicked.connect(lambda: view.reply_requested.emit(self.identifier))
        heading.addWidget(self.reply)
        layout.addLayout(heading)
        self.body = ReadingBrowser()
        self.body.setObjectName('turnBody')
        self.body.setFrameShape(QFrame.Shape.NoFrame)
        self.body.setOpenLinks(False)
        self.body.setOpenExternalLinks(False)
        self.body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.body.viewport().installEventFilter(self)
        self.sources = deepcopy((turn.get('response') or {}).get('sources') or [])
        links = {}
        declared = (turn.get('response') or {}).get('citations')
        if isinstance(declared, list):
            # Co-STORM uses global KB citation numbers. They are not source-list
            # positions; preserve the explicit number -> exact source mapping.
            citation_rows = []
            source_index = 0
            for row in declared:
                number = str(row['number'])
                available = bool(row.get('source'))
                index = source_index if available else None
                if available:
                    source_index += 1
                links[number] = 'citation:' + str(index) if index is not None else None
                citation_rows.append((number, index))
        else:
            # Legacy answers have no validated sentence/source number mapping.
            citation_rows = [(str(index + 1), index) for index in range(len(self.sources))]
        self._citation_indices = {index for _, index in citation_rows if index is not None}
        show_markdown(self.body, turn_text(turn), links=links)
        self.body.anchorClicked.connect(self._citation)
        layout.addWidget(self.body)
        if citation_rows:
            citations = QHBoxLayout()
            for number, index in citation_rows:
                button = QPushButton('[' + number + ']' + (' 원자료 없음' if index is None else ''))
                button.setFlat(True)
                button.setEnabled(index is not None)
                button.setToolTip('출처 읽기 ' + number if index is not None else '확인된 원자료가 없습니다.')
                if index is not None:
                    button.clicked.connect(lambda checked=False, index=index:
                                           view.citation_requested.emit(self.identifier, index))
                citations.addWidget(button)
            citations.addStretch()
            layout.addLayout(citations)
        if turn.get('status') not in ('AUTHORED', 'ANSWERED', 'SUCCEEDED'):
            label = QLabel(str(turn.get('status', 'UNKNOWN')))
            layout.addWidget(label)
        self.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            self.view.setCurrentItem(self.item)
        return super().eventFilter(watched, event)

    def _citation(self, url):
        if url.scheme() != 'citation':
            return
        try:
            index = int(url.path())
        except ValueError:
            return
        if index in self._citation_indices and 0 <= index < len(self.sources):
            self.view.citation_requested.emit(self.identifier, index)

    def fit_width(self, width):
        # One transcript scrollbar, full body text. Refit on ordinary resize.
        width = max(220, width)
        self.setFixedWidth(width)
        document = self.body.document()
        document.setTextWidth(max(160, width - 36))
        document.fit_math_width(max(128, width - 68))
        height = math.ceil(self.body.document().size().height()) + 8
        self.body.setFixedHeight(max(36, height))
        self.layout().activate()
        self.item.setSizeHint(QSize(width, self.sizeHint().height() + 8))

    def selected(self, yes):
        self.setStyleSheet('#turnCard { border: 2px solid #7196bb; border-radius: 6px; background: #f4f8fd; }'
                           if yes else '#turnCard { border: 1px solid #ccd8e4; border-radius: 6px; background: palette(base); }')


class ConversationList(QListWidget):
    citation_requested = Signal(str, int)
    reply_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(8)
        self._cards, self._snapshot = {}, None
        self.currentItemChanged.connect(self._selection_changed)

    def set_turns(self, turns, roles=()):
        snapshot = (turns, roles)
        if snapshot == self._snapshot:
            return  # Polling must not destroy selection, text selection or scroll.
        current = self.currentItem()
        selected = current.data(Qt.ItemDataRole.UserRole) if current else None
        scroll = self.verticalScrollBar()
        previous_ids = set(self._cards)
        following = not self.count() or scroll.value() >= scroll.maximum() - 24
        position = scroll.value()
        # Keep unchanged cards, including their text selection, when new turns
        # arrive or the currently running last turn receives another update.
        prefix = 0
        if self._snapshot is not None and self._snapshot[1] == roles:
            for before, after in zip(self._snapshot[0], turns):
                if before != after:
                    break
                prefix += 1
        self._snapshot = deepcopy(snapshot)
        while self.count() > prefix:
            item = self.item(prefix)
            card = self._cards.pop(item.data(Qt.ItemDataRole.UserRole))
            self.takeItem(prefix)
            card.deleteLater()
        for turn in turns[prefix:]:
            item = QListWidgetItem(str(turn.get('author', 'Participant')) + '\n' + turn_text(turn))
            item.setData(Qt.ItemDataRole.UserRole, turn['id'])
            item.setData(Qt.ItemDataRole.AccessibleTextRole,
                         author_label(turn, roles) + ': ' + turn_text(turn))
            self.addItem(item)
            card = _TurnCard(self, item, turn, roles)
            self._cards[turn['id']] = card  # Explicit Qt/Python lifetime.
            self.setItemWidget(item, card)
            if turn['id'] == selected:
                self.setCurrentItem(item)
        self._fit()
        added = bool(turns and turns[-1]['id'] not in previous_ids)
        if self.count() and (not self.currentItem() or (following and added)):
            self.setCurrentRow(self.count() - 1)
        # A long answer opens at its author, not at an anonymous last paragraph.
        # Unchanged polls return above; ordinary reading retains its position.
        target = self.currentItem().data(Qt.ItemDataRole.UserRole) if self.currentItem() else None
        snapshot = self._snapshot
        def restore_scroll():
            if self._snapshot is not snapshot:
                return
            if following and added and target in self._cards:
                self.scrollToItem(self._cards[target].item, QAbstractItemView.ScrollHint.PositionAtTop)
            else:
                scroll.setValue(position)
        QTimer.singleShot(0, restore_scroll)

    def _selection_changed(self, current, previous):
        for item, selected in ((previous, False), (current, True)):
            if item is not None:
                card = self._cards.get(item.data(Qt.ItemDataRole.UserRole))
                if card:
                    card.selected(selected)

    def _fit(self):
        width = self.viewport().width() - 20
        for card in self._cards.values():
            card.fit_width(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()
