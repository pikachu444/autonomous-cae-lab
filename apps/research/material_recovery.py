"""JSON-only view snapshots. No owner mutations, requests or editor commits."""
from copy import deepcopy
from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtWidgets import QAbstractItemView, QLineEdit
from caelab.storage import canonical_hash


def _original(draft, path):
    value = draft
    try:
        for key in path: value = value[key]
    except (KeyError, IndexError, TypeError):
        return False, None
    return True, deepcopy(value)


def _line_focus(line):
    return dict(cursor=line.cursorPosition(), selection=[line.selectionStart(), line.selectionLength()])


def _check_line_focus(text, focus):
    length = len(text.encode('utf-16-le')) // 2
    cursor = focus.get('cursor', 0); start, count = focus.get('selection', [-1, 0])
    if (type(cursor) is not int or not 0 <= cursor <= length
            or type(start) is not int or type(count) is not int or count < 0
            or not (start == -1 and count == 0 or 0 <= start <= start + count <= length)):
        raise ValueError('복구할 원문 커서와 선택 범위를 확인하세요.')


def _restore_line_focus(line, focus):
    _check_line_focus(line.text(), focus)
    cursor = focus.get('cursor', 0); start, count = focus.get('selection', [-1, 0])
    line.setCursorPosition(cursor)
    if start >= 0 and count > 0:
        line.setSelection(start + count, -count) if cursor == start else line.setSelection(start, count)


def material_raw_snapshot(window):
    """Snapshot the acknowledged base separately from pending widget text."""
    if window.document is None:
        raise ValueError('재료 문서를 먼저 여세요.')
    cells, focus_record = [], None
    focus = window.focusWidget()
    draft = window.document['draft']
    def cell(path, raw, position, *, pending=None):
        nonlocal focus_record
        exists, original = _original(draft, path)
        entry = dict(field_path=list(path), raw_text=raw, original_value=original,
                     position=position, editor_kind='unfinished' if pending is not None else 'cell')
        if not exists: entry['original_exists'] = False
        if pending is not None:
            entry['raw_text'] = pending.text()
            focus_record = dict(field_path=list(path), **_line_focus(pending))
        cells.append(entry)
    for table, name in ((window.coefficients, '재료 계수'), (window.history, '변형 이력')):
        pending = next((editor for editor in table.findChildren(QLineEdit) if editor.isVisible()), None) if table.state() == QAbstractItemView.State.EditingState else None
        for row in range(table.rowCount()):
            columns = [1] if table is window.coefficients else range(table.columnCount())
            for column in columns:
                item = table.item(row, column)
                if item is None: continue
                if table is window.coefficients:
                    metadata = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                    path = ['settings', 'parameters', metadata['parameter']]
                elif column == 0: path = ['settings', 'time', row]
                elif column < 10:
                    path = ['settings', 'deformation_gradient', row, (column - 1) // 3, (column - 1) % 3]
                else:
                    path = ['settings', 'boundary_control', 'stress_components', window._target_components[column - 10], row]
                active = pending if (row, column) == (table.currentRow(), table.currentColumn()) else None
                cell(path, item.text(), dict(table=name, row=row, column=column), pending=active)
    for key, field in (('stress_unit', window.stress_unit), ('time_unit', window.time_unit)):
        cell(['settings', key], field.text(), {'field': key}, pending=field if focus is field else None)
    cell(['settings', 'model'], str(window.model.currentData()), {'field': 'model'})
    raw = dict(cells=cells, local_draft=window.edited_draft(commit=False),
               selection={'history': [[index.row(), index.column()] for index in window.history.selectedIndexes()],
                          'coefficients': [[index.row(), index.column()] for index in window.coefficients.selectedIndexes()]})
    if focus_record is not None: raw['focus'] = focus_record
    raw['editor_revision'] = 'U' + canonical_hash(raw)
    return raw


def restore_material_raw(window, raw):
    """Restore a host-verified capsule into a fresh view; never apply to owner."""
    from .material_window import draft_view_error, display_value
    if window.document is None or window.local_dirty or window.conflict or window._busy:
        raise ValueError('현재 재료 편집을 마친 뒤 복구 입력을 여세요.')
    if raw.get('focus') and not window.isVisible():
        raise ValueError('미확정 셀을 복구하려면 재료 창을 먼저 표시하세요.')
    candidate = deepcopy(raw.get('local_draft', window.document['draft']))
    if draft_view_error(candidate):
        raise ValueError('복구 입력의 표 구조를 표시할 수 없습니다. 보존한 입력을 유지했습니다.')
    def hidden(value):
        value = deepcopy(value)
        for key in ('model', 'stress_unit', 'time_unit', 'parameters', 'time', 'deformation_gradient', 'boundary_control'):
            value.get('settings', {}).pop(key, None)
        return value
    if hidden(candidate) != hidden(window.document['draft']):
        raise ValueError('복구 입력이 재료 편집 범위 밖의 값을 바꾸려 합니다. 원문을 보존했습니다.')
    allowed = {}
    settings = candidate['settings']
    for parameter in settings['parameters']:
        allowed[('settings', 'parameters', parameter)] = ('coefficients', parameter, 1)
    for row in range(len(settings['time'])):
        allowed[('settings', 'time', row)] = ('history', row, 0)
        for column in range(1, 10):
            allowed[('settings', 'deformation_gradient', row, (column - 1) // 3, (column - 1) % 3)] = ('history', row, column)
        for offset, component in enumerate(settings.get('boundary_control', {}).get('stress_components', {})):
            allowed[('settings', 'boundary_control', 'stress_components', component, row)] = ('history', row, 10 + offset)
    for field in ('stress_unit', 'time_unit', 'model'):
        allowed[('settings', field)] = (field, None, None)
    seen = set()
    for cell in raw.get('cells', []):
        path = tuple(cell['field_path'])
        exists, value = _original(window.document['draft'], path)
        if (path not in allowed or path in seen or not isinstance(cell.get('raw_text'), str)
                or exists != cell.get('original_exists', True) or value != cell['original_value']):
            raise ValueError('복구 셀의 원래 문서와 현재 재료가 다릅니다. 입력을 보존했습니다.')
        if path == ('settings', 'model') and cell['raw_text'] != str(settings['model']):
            raise ValueError('복구할 재료 모델과 입력 표가 다릅니다.')
        seen.add(path)
    focus_path = tuple(raw.get('focus', {}).get('field_path', []))
    if focus_path and focus_path not in seen:
        raise ValueError('복구할 편집 셀을 찾을 수 없습니다.')
    if focus_path:
        _check_line_focus(next(cell['raw_text'] for cell in raw['cells'] if tuple(cell['field_path']) == focus_path), raw['focus'])
    window._local_undo.append(deepcopy(window.edited_draft(commit=False)))
    window._local_redo.clear()
    window._restore_inputs(candidate)
    coefficient_rows = {window.coefficients.item(row, 0).data(Qt.ItemDataRole.UserRole)['parameter']: row
                        for row in range(window.coefficients.rowCount())}
    pending = None
    window._populating = True
    try:
        for table, key in ((window.history, 'history'), (window.coefficients, 'coefficients')):
            table.clearSelection()
            for row, column in raw.get('selection', {}).get(key, []):
                if (type(row) is int and type(column) is int and 0 <= row < table.rowCount()
                        and 0 <= column < table.columnCount()):
                    table.selectionModel().select(table.model().index(row, column), QItemSelectionModel.SelectionFlag.Select)
        for cell in raw['cells']:
            path = tuple(cell['field_path']); target, row, column = allowed[path]
            if target == 'model': continue
            if target in ('stress_unit', 'time_unit'):
                field = getattr(window, target); field.setText(cell['raw_text'])
                if path == focus_path: pending = field
                continue
            table = getattr(window, target)
            row = coefficient_rows[row] if target == 'coefficients' else row
            if path != focus_path:
                table.item(row, column).setText(cell['raw_text'])
            else:
                table.setCurrentCell(row, column); table.setFocus()
                table.scrollToItem(table.item(row, column))
                table.editItem(table.item(row, column))
                pending = table.findChild(QLineEdit)
                if pending is not None: pending.setText(cell['raw_text'])
                else: table.item(row, column).setText(cell['raw_text'])
        if pending is not None:
            pending.setFocus()
            _restore_line_focus(pending, raw['focus'])
    finally:
        window._populating = False
    window.local_dirty = candidate != window.document['draft'] or any(
        cell['raw_text'] != display_value(cell['original_value']) for cell in raw['cells'])
    window._local_snapshot = window.edited_draft(commit=False)
    window._update_actions()
    window.message.setText('보존한 재료 입력을 복구했습니다. 확인 후 입력을 적용하세요.')
