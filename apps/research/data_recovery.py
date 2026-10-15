"""Noncommitting Data editor snapshots; host owns durable recovery authority."""
from copy import deepcopy
from PySide6.QtCore import Qt, QTimer, QItemSelectionModel
from PySide6.QtWidgets import QAbstractItemView, QLineEdit
from caelab.storage import canonical_hash
from .material_recovery import _original


def _mapping_path(name, row, column):
    if (row, column) == (1, 1): return ['mapping', 'columns']
    prefix = ['mapping', 'columns', name] + (['axis'] if row == 0 else [])
    keys = {1: 'name', 2: 'column', 3: 'unit', 4: 'component', 5: 'location',
            6: 'measure', 7: 'frame', 8: 'scale', 9: 'offset'}
    return prefix + [keys[column]]


def data_raw_snapshot(window):
    if window.document is None or window._view_error:
        raise ValueError('편집할 Data 문서를 먼저 여세요. 원래 문서는 보존됩니다.')
    cells, focus_record = [], None
    draft = window.document['draft']; focus = window.focusWidget()
    def add(path, text, position, pending=None):
        nonlocal focus_record
        exists, original = _original(draft, path)
        cell = dict(field_path=path, raw_text=text, original_value=original,
                    position=position, editor_kind='unfinished' if pending else 'cell')
        if not exists: cell['original_exists'] = False
        if pending is not None:
            cell['raw_text'] = pending.text()
            focus_record = dict(field_path=path, cursor=pending.cursorPosition(),
                selection=[pending.selectionStart(), len(pending.selectedText())])
        cells.append(cell)
    pending = next((editor for editor in window.mapping.findChildren(QLineEdit) if editor.isVisible()), None) if window.mapping.state() == QAbstractItemView.State.EditingState else None
    for row in range(window.mapping.rowCount()):
        for column in range(window.mapping.columnCount()):
            item = window.mapping.item(row, column)
            if item is None or not item.flags() & Qt.ItemFlag.ItemIsEditable: continue
            active = pending if (row, column) == (window.mapping.currentRow(), window.mapping.currentColumn()) else None
            add(_mapping_path(window._channel_name, row, column), item.text(),
                dict(table='mapping', row=row, column=column), active)
    for name, path, field in _fields(window):
        add(path, field.text(), {'field': name}, field if focus is field else None)
    raw = dict(cells=cells, local_draft=window.edited_draft(commit=False),
        selection={'channel': window._channel_name, 'tab': window.editor.currentIndex(),
                   'mapping': [[index.row(), index.column()] for index in window.mapping.selectedIndexes()]})
    if focus_record: raw['focus'] = focus_record
    raw['editor_revision'] = 'U' + canonical_hash(raw)
    return raw


def _fields(window):
    yield 'delimiter', ['mapping', 'delimiter'], window.delimiter
    yield 'skip_header', ['mapping', 'skip_header'], window.skip_header
    for key, field in window.test_fields.items(): yield 'test_' + key, ['test_metadata', key], field
    for key, field in window.row_fields.items():
        yield 'row_' + key, ['mapping', 'columns', window._channel_name, 'row_selection', key], field


def restore_data_raw(window, raw):
    """Render a host-verified capsule in a fresh view, without applying anything."""
    from .data_window import view_error
    if (window.document is None or window.local_dirty or window.conflict or window._busy
            or window.mapping.state() == QAbstractItemView.State.EditingState):
        raise ValueError('현재 Data 편집을 마친 뒤 복구 입력을 여세요.')
    if raw.get('focus') and not window.isVisible():
        raise ValueError('미확정 입력을 복구하려면 Data 창을 먼저 표시하세요.')
    candidate = deepcopy(raw.get('local_draft', window.document['draft']))
    if view_error(candidate):
        raise ValueError('복구 입력의 표 구조를 표시할 수 없습니다. 원문을 보존했습니다.')
    def hidden(value):
        value = deepcopy(value)
        for key in ('data_id', 'test_metadata', 'acquisition', 'processing', 'sheet_group'):
            value.pop(key, None)
        for key in ('columns', 'delimiter', 'skip_header'): value.get('mapping', {}).pop(key, None)
        return value
    if hidden(candidate) != hidden(window.document['draft']):
        raise ValueError('복구 입력이 Data 편집 범위 밖의 값을 바꾸려 합니다.')
    name = raw.get('selection', {}).get('channel')
    if name not in candidate['mapping']['columns']:
        raise ValueError('복구할 채널을 찾지 못했습니다. 원문을 보존했습니다.')
    positions, paths = set(), set()
    focus_path = tuple(raw.get('focus', {}).get('field_path', []))
    for cell in raw['cells']:
        path = tuple(cell['field_path']); position = cell['position']
        exists, original = _original(window.document['draft'], path)
        if position.get('table') == 'mapping':
            row, column = position.get('row'), position.get('column')
            if row not in (0, 1) or column not in range(1, 10) or row == 0 and column in range(4, 8):
                raise ValueError('복구할 매핑 셀이 편집 범위 밖에 있습니다.')
            expected = _mapping_path(name, row, column); key = ('mapping', row, column)
        else:
            field = position.get('field'); fields = {key: path for key, path, _ in _fields(window)}
            expected = fields.get(field)
            if expected and expected[:2] == ['mapping', 'columns']: expected = [*expected[:2], name, *expected[3:]]
            key = ('field', field)
        if (list(path) != expected or path in paths or key in positions or not isinstance(cell['raw_text'], str)
                or exists != cell.get('original_exists', True) or original != cell['original_value']):
            raise ValueError('복구 셀의 원래 Data 입력과 현재 문서가 다릅니다.')
        paths.add(path); positions.add(key)
    if focus_path and focus_path not in paths:
        raise ValueError('복구할 편집 위치를 찾지 못했습니다.')
    acknowledged = deepcopy(window.document)
    rendered = deepcopy(acknowledged); rendered['draft'] = candidate
    window._channel_name = name
    window._show_document(rendered)
    window.document = acknowledged
    window._populating = True
    try:
        window.editor.setCurrentIndex(raw.get('selection', {}).get('tab', 0))
        window.mapping.clearSelection()
        for row, column in raw.get('selection', {}).get('mapping', []):
            if (type(row) is int and type(column) is int and 0 <= row < window.mapping.rowCount()
                    and 0 <= column < window.mapping.columnCount()):
                window.mapping.selectionModel().select(window.mapping.model().index(row, column), QItemSelectionModel.SelectionFlag.Select)
        pending = None
        fields = {key: field for key, _, field in _fields(window)}
        for cell in raw['cells']:
            position = cell['position']; active = tuple(cell['field_path']) == focus_path
            if position.get('table') == 'mapping':
                row, column = position['row'], position['column']; item = window.mapping.item(row, column)
                if active:
                    window.editor.show(); window.editor.setCurrentIndex(0)
                    window.mapping.setCurrentCell(row, column); window.mapping.setFocus()
                    window.mapping.scrollToItem(item); window.mapping.editItem(item)
                    pending = window.mapping.findChild(QLineEdit)
                    if pending is None: raise ValueError('미확정 매핑 편집기를 열지 못했습니다. 원문은 보존됩니다.')
                    pending.setText(cell['raw_text'])
                else: item.setText(cell['raw_text'])
            else:
                field = fields[position['field']]; field.setText(cell['raw_text'])
                if active:
                    window.editor.show()
                    window.editor.setCurrentIndex(1 if position['field'].startswith('test_') else 2 if position['field'].startswith('row_') else 0)
                    pending = field
        if pending is not None:
            pending.setFocus(); focus = raw['focus']
            pending.setCursorPosition(min(max(0, focus.get('cursor', 0)), len(pending.text())))
            start, count = focus.get('selection', [-1, 0])
            if start >= 0 and count > 0: pending.setSelection(start, count)
    finally:
        window._populating = False
    window.local_dirty = True
    window.message.setText('보존한 Data 입력을 복구했습니다. 확인 후 설정을 적용하세요.')
    window._update_actions()
    QTimer.singleShot(0, window._reveal_editor_focus)
