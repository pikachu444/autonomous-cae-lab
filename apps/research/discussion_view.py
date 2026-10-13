"""Readable native discussion turns; identities remain item data, not prose."""
from copy import deepcopy
from html import escape
import math
import re

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QTextBrowser, QVBoxLayout)


def author_label(turn, roles=()):
    if turn.get('author') == 'user':
        return '사용자'
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
        self.setStyleSheet('#turnCard { border: 1px solid #ddddE5; border-radius: 6px; background: palette(base); }')
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
        self.body = QTextBrowser()
        self.body.setObjectName('turnBody')
        self.body.setFrameShape(QFrame.Shape.NoFrame)
        self.body.setOpenLinks(False)
        self.body.setOpenExternalLinks(False)
        self.body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.body.viewport().installEventFilter(self)
        self.sources = deepcopy((turn.get('response') or {}).get('sources') or [])
        text = escape(turn_text(turn))
        # Legacy answer [n] markers have no validated sentence/source mapping.
        # Only the explicit source buttons below address verified references.
        self.body.setHtml('<div style="line-height:145%">' + text.replace('\n', '<br>') + '</div>')
        self.body.anchorClicked.connect(self._citation)
        layout.addWidget(self.body)
        if self.sources:
            citations = QHBoxLayout()
            for index in range(len(self.sources)):
                button = QPushButton('[' + str(index + 1) + ']')
                button.setFlat(True)
                button.setToolTip('출처 읽기 ' + str(index + 1))
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
        if url.scheme() == 'citation':
            self.view.citation_requested.emit(self.identifier, int(url.path()))

    def fit_width(self, width):
        # One transcript scrollbar, full body text. Refit on ordinary resize.
        width = max(220, width)
        self.setFixedWidth(width)
        self.body.document().setTextWidth(max(160, width - 36))
        height = math.ceil(self.body.document().size().height()) + 8
        self.body.setFixedHeight(max(36, height))
        self.layout().activate()
        self.item.setSizeHint(QSize(width, self.sizeHint().height() + 8))

    def selected(self, yes):
        self.setStyleSheet('#turnCard { border: 2px solid #b5a1dd; border-radius: 6px; background: #faf7ff; }'
                           if yes else '#turnCard { border: 1px solid #ddddE5; border-radius: 6px; background: palette(base); }')


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
        self._snapshot = deepcopy(snapshot)
        self._cards.clear()
        self.clear()
        for turn in turns:
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
