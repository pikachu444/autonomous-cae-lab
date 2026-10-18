"""Raw Numerical editor views over the existing recovery capsule API."""
from copy import deepcopy

from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtWidgets import QApplication, QAbstractItemView, QComboBox, QLineEdit, QTreeWidget

from caelab.related_save_recovery import validate_raw
from caelab.storage import canonical_hash
from .material_recovery import _original, _line_focus, _check_line_focus, _restore_line_focus
from .numerical_editing import PlanTable

DATA = Qt.ItemDataRole.UserRole


class RecoveryPlanTable(PlanTable):
    """Retain the accepted clipboard text with the existing bounded paste."""
    def paste_cells(self):
        text = QApplication.clipboard().text()
        accepted = super().paste_cells()
        if accepted:
            self.raw_paste = dict(raw_text=text, committed=False, anchor=[self.currentRow(), self.currentColumn()])
        return accepted


def _request(window):
    return hasattr(window, '_request_buffer')


def _tables(window):
    if _request(window):
        return [(name, getattr(window, name)) for name in ('variable_sheet', 'response_sheet', 'method_sheet')]
    return [('experiments', window.experiments)]


def _targets(window):
    """Reuse the typed editor's paths; positions are view-local, never owners."""
    if _request(window):
        yield ('request', 'purpose'), window.purpose, None, {'field': 'purpose'}
        yield ('request', 'budget', 'evaluations'), window.evaluations, None, {'field': 'evaluations'}
    else:
        for name, path in [('budget', ('budget',)), ('count', ('count',)), ('seed', ('seed',)),
                           ('penalty', ('failure_penalty',)), ('mode', ('mode',)), ('method', ('method',))]:
            yield path, getattr(window, name), None, {'field': name}
    for name, table in _tables(window):
        for row in range(table.rowCount()):
            for column in range(table.columnCount()):
                item = table.item(row, column)
                if item is None or not item.flags() & Qt.ItemFlag.ItemIsEditable:
                    continue
                if _request(window):
                    binding = item.data(DATA) or {}
                    if not binding.get('path'): continue
                    path = ('request', 'inputs', *binding['path'])
                else:
                    key = {0: 'id', 1: 'role', 4: 'response', 5: 'weight', 6: 'scale'}.get(column)
                    if key is None: continue
                    path = ('experiments', row, key)
                yield path, table, item, {'table': name, 'row': row, 'column': column}
    tree = window.inputs if _request(window) else window.operation_options.inputs
    prefix = ('request', 'inputs') if _request(window) else ('operation_options',)
    def visit(item):
        if item is None: return
        binding = item.data(0, DATA) or {}
        if binding.get('kind') not in {'object', 'list'} and binding.get('path'):
            yield (*prefix, *binding['path']), tree, item, {'tree': 'inputs', 'path': list(binding['path'])}
        for row in range(item.childCount()): yield from visit(item.child(row))
    yield from visit(tree.topLevelItem(0))


def _live(widget, item):
    if item is None: return None
    if widget.state() != QAbstractItemView.State.EditingState or widget.currentItem() is not item:
        return None
    return next((editor for kind in (QComboBox, QLineEdit) for editor in widget.findChildren(kind)
                 if editor.isVisible()), None)


def _text(widget, item):
    live = _live(widget, item)
    source = live if live is not None else widget
    if isinstance(source, QComboBox): return source.currentText(), live
    if isinstance(source, QLineEdit): return source.text(), live
    return item.text(1) if isinstance(widget, QTreeWidget) else item.text(), live


def numerical_raw_snapshot(window):
    if window.document is None or window._view_error:
        raise ValueError('계획 입력을 먼저 여세요. 원래 문서는 유지됩니다.')
    cells = {}; focus = None; selections = {}; paste = {}
    variable = None
    if not _request(window):
        variable = window.variable_editor.recovery_snapshot()
        cells = {tuple(cell['field_path']): deepcopy(cell) for cell in variable['cells']}
        if variable.get('focus'):
            f = variable['focus']
            focus = dict(field_path=f['field_path'], cursor=f['cursor'],
                         selection=[f['selection_start'], f['selection_length']])
    for path, widget, item, position in _targets(window):
        text, live = _text(widget, item)
        # A worksheet and its typed tree share one path. Preserve the active
        # editor; otherwise the worksheet's exact text takes precedence.
        if path in cells and live is None: continue
        exists, original = _original(window.document['draft'], path)
        cells[path] = dict(field_path=list(path), raw_text=text, original_value=original,
                           original_exists=exists, position=position,
                           editor_kind='unfinished' if live is not None else 'cell')
        line = live.lineEdit() if isinstance(live, QComboBox) else live
        if line is None and item is None and widget.hasFocus() and isinstance(widget, QLineEdit): line = widget
        if line is not None: focus = dict(field_path=list(path), **_line_focus(line))
    for name, table in _tables(window):
        selections[name] = [[index.row(), index.column()] for index in table.selectedIndexes()]
        if getattr(table, 'raw_paste', None): paste[name] = deepcopy(table.raw_paste)
    if variable is not None: selections['plan_variables'] = variable
    if _request(window):
        selections.update(input_tab=window.input_tabs.currentIndex(), work_page=window.work_pages.currentIndex())
    raw = dict(cells=list(cells.values()), local_draft=window.edited_draft(commit=False), selection=selections)
    if focus is not None: raw['focus'] = focus
    if paste: raw['paste'] = paste
    raw['editor_revision'] = 'E' + canonical_hash(raw)
    return raw


def recovery_ready(window):
    return (not window._busy and not window._callbacks
            and not getattr(window, '_pending_adoption', None)
            and not getattr(window, '_incoming_review', False)
            and (window.document is None or getattr(window, 'variable_editor', None) is None
                 or window.variable_editor.recovery_ready()))


def restore_numerical_raw(window, raw):
    if (window.document is None or window.local_dirty or window.conflict or not recovery_ready(window)
            or any(view.state() == QAbstractItemView.State.EditingState for view in window.editor.findChildren(QAbstractItemView))):
        raise ValueError('현재 계획 편집을 먼저 보관하거나 해결하세요.')
    if raw.get('focus') and not window.isVisible():
        raise ValueError('미확정 입력을 복구하려면 계획 창을 먼저 표시하세요.')
    acknowledged = deepcopy(window.document)
    validate_raw(raw, acknowledged['draft'])
    candidate = deepcopy(raw.get('local_draft', acknowledged['draft']))
    editable = {'request', 'method_inputs', 'method_model_sources', 'model_source', 'source'} if _request(window) else {
        'material', 'mode', 'method', 'budget', 'count', 'seed', 'failure_penalty', 'variables', 'experiments', 'operation_options'}
    def protected(draft): return {key: value for key, value in draft.items() if key not in editable}
    if protected(candidate) != protected(acknowledged['draft']):
        raise ValueError('보관한 원문이 이 계획 편집 범위 밖의 값을 바꾸려 합니다.')
    if _request(window) and window._shape_error(candidate):
        raise ValueError('보관한 계획의 입력 구조를 표시할 수 없습니다.')
    focus = raw.get('focus') or {}; path = tuple(focus.get('field_path', ()))
    cell_by_path = {tuple(cell['field_path']): cell for cell in raw['cells']}
    if path:
        if path not in cell_by_path: raise ValueError('보관한 편집 위치를 찾지 못했습니다.')
        _check_line_focus(cell_by_path[path]['raw_text'], focus)
    visible = deepcopy(acknowledged); visible['draft'] = candidate
    try:
        window._show_document(visible)
        window.document = acknowledged
        if window._view_error: raise ValueError('보관한 계획의 표 구조를 표시할 수 없습니다.')
        variable = raw.get('selection', {}).get('plan_variables')
        if variable is not None:
            validate_raw(variable, acknowledged['draft'])
            if (variable.get('local_draft', {}).get('variables') != candidate.get('variables')
                    or any(cell_by_path.get(tuple(cell['field_path'])) != cell for cell in variable['cells'])):
                raise ValueError('보관한 계획 변수 원문과 표시할 입력이 다릅니다.')
        variable_paths = {tuple(cell['field_path']) for cell in variable.get('cells', [])} if variable else set()
        if not _request(window):
            window.variable_editor.reset_view(window.variable_editor._adapter, acknowledged)
        targets = {}
        for target_path, widget, item, position in _targets(window):
            targets[(target_path, canonical_hash(position))] = (widget, item)
        for target_path, cell in cell_by_path.items():
            if target_path not in variable_paths and (target_path, canonical_hash(cell['position'])) not in targets:
                raise ValueError('보관한 원문의 입력 위치가 현재 편집 표와 다릅니다.')
        window._populating = True
        if _request(window): window._sheet_populating = True
        try:
            pending = None
            if _request(window):
                window.work_pages.setCurrentIndex(raw.get('selection', {}).get('work_page', 0))
                window.input_tabs.setCurrentIndex(raw.get('selection', {}).get('input_tab', 0))
            for target_path, cell in cell_by_path.items():
                if target_path in variable_paths: continue
                widget, item = targets[(target_path, canonical_hash(cell['position']))]
                if item is None:
                    if isinstance(widget, QComboBox): widget.setCurrentText(cell['raw_text'])
                    else: widget.setText(cell['raw_text'])
                    if target_path == path: pending = widget
                elif cell.get('editor_kind') == 'unfinished':
                    if _request(window):
                        window.work_pages.setCurrentIndex(0)
                        window.input_tabs.setCurrentWidget(window.advanced_scroll if isinstance(widget, QTreeWidget) else window.sheet)
                    widget.setCurrentItem(item); widget.scrollToItem(item)
                    widget.editItem(item, 1) if isinstance(widget, QTreeWidget) else widget.editItem(item)
                    pending = _live(widget, item)
                    if pending is None: raise ValueError('미확정 편집기를 열지 못했습니다. 보관 원문은 유지됩니다.')
                    if isinstance(pending, QComboBox): pending.setEditText(cell['raw_text'])
                    else: pending.setText(cell['raw_text'])
                elif isinstance(widget, QTreeWidget): item.setText(1, cell['raw_text'])
                else: item.setText(cell['raw_text'])
            for name, table in _tables(window):
                table.raw_paste = deepcopy(raw.get('paste', {}).get(name))
                table.clearSelection()
                for row, column in raw.get('selection', {}).get(name, []):
                    if 0 <= row < table.rowCount() and 0 <= column < table.columnCount():
                        table.selectionModel().select(table.model().index(row, column), QItemSelectionModel.SelectionFlag.Select)
            if variable is not None and not _request(window):
                window.variable_editor.restore_recovery(variable)
            if pending is not None:
                line = pending.lineEdit() if isinstance(pending, QComboBox) else pending
                if not _request(window) and line in (window.budget, window.count, window.seed, window.penalty):
                    window.settings_toggle.setChecked(True)
                line.setFocus(); _restore_line_focus(line, focus)
        finally:
            window._populating = False
            if _request(window): window._sheet_populating = False
        window.local_dirty = True
        window._reset_draft_history(force=True)
        window._update_actions()
        window.message.setText('보관한 계획 원문을 복구했습니다. 내용을 확인한 뒤 명시적으로 적용하세요.')
    except (ValueError, TypeError, KeyError, IndexError):
        if not _request(window):
            window.variable_editor.reset_view(window.variable_editor._adapter, acknowledged)
        window._show_document(acknowledged)
        window.document = acknowledged; window.local_dirty = False
        raise
