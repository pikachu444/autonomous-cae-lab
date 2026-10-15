"""Qt relationship commands and project-local layout resume for ConnectionWindow.

Small dialogs choose typed references; domain editors and saved-reference viewers
remain the existing independent windows. No QWidget values are copied into a Plan.
"""
from __future__ import annotations
from copy import deepcopy
from contextlib import contextmanager
import json
import uuid

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QMessageBox, QPlainTextEdit, QVBoxLayout)

from caelab.connection_graph_view import default_state, merge_bindings


def _source_identity(token):
    return {k: token.get(k) for k in ('document_id', 'basis', 'saved_revision', 'job_id', 'response')}


class RelationSelectionDialog(QDialog):
    def __init__(self, catalog, action, *, port=None, prior_source=None, parent=None):
        super().__init__(parent)
        self.catalog, self.action = catalog, action
        self.setWindowTitle({'add': '연결 추가', 'repair': '원본 참조 복구', 'unlink': '연결 해제'}[action])
        self.resize(720, 370)
        layout = QVBoxLayout(self)
        title = QLabel('대상 문서: ' + catalog['target_title']); title.setWordWrap(True)
        layout.addWidget(title)
        form = QFormLayout()
        self.port = QComboBox(); self.port.setAccessibleName('변경할 연결 항목')
        for row in catalog['ports']:
            if action == 'add' and row['current_reference'] is not None:
                continue
            if action != 'add' and row['current_reference'] is None:
                continue
            self.port.addItem(row['label'], deepcopy(row))
        form.addRow('연결 항목', self.port)
        self.source = QComboBox(); self.source.setAccessibleName('정확한 저장 개정 또는 결과 선택')
        self.source.setMinimumContentsLength(28)
        self.source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        form.addRow('원본', self.source)
        layout.addLayout(form)
        self.meaning = QLabel(); self.meaning.setWordWrap(True)
        layout.addWidget(self.meaning)
        self.problem = QLabel(); self.problem.setWordWrap(True)
        layout.addWidget(self.problem)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('영향 확인')
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._prior_source = prior_source
        self.port.currentIndexChanged.connect(self._port_changed)
        if port:
            for index in range(self.port.count()):
                if self.port.itemData(index)['port'] == port:
                    self.port.setCurrentIndex(index)
                    break
        self._port_changed()

    def _port_changed(self, *_):
        port = self.port.currentData()
        self.source.clear()
        if not port:
            self.meaning.setText('변경 가능한 연결 항목이 없습니다. 해당 문서의 원도구에서 입력 행을 선언하세요.')
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return
        self.meaning.setText(port['meaning'])
        self.source.setEnabled(self.action != 'unlink')
        if self.action == 'unlink':
            self.source.addItem('현재 연결을 해제합니다. 원본 문서와 결과는 보존합니다.', None)
        else:
            for row in self.catalog['sources']:
                token = row['selection']
                if token['document_kind'] not in port['source_kinds'] or token['basis'] not in port['source_bases']:
                    continue
                if port['form'] == 'observation' and 'response' not in token:
                    continue
                if port['form'] == 'result' and 'response' in token:
                    continue
                self.source.addItem(row['label'], deepcopy(token))
            if self._prior_source:
                for index in range(self.source.count()):
                    if _source_identity(self.source.itemData(index)) == _source_identity(self._prior_source):
                        self.source.setCurrentIndex(index)
                        break
        ready = self.action == 'unlink' or self.source.count() > 0
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ready)
        self.problem.setText('원본과 저장본을 선택한 뒤 연결 조건과 단위를 확인합니다.' if ready else
                             '허용되는 보존 원본이 없습니다. 원도구에서 정확한 자료를 보존한 뒤 다시 읽으세요.')

    def request(self):
        port = self.port.currentData()
        if port is None:
            raise ValueError('연결 항목을 선택하세요.')
        return {'target': deepcopy(self.catalog['target']), 'port': port['port'], 'action': self.action,
                'source': deepcopy(self.source.currentData()) if self.action != 'unlink' else None}


class RelationImpactDialog(QDialog):
    def __init__(self, proposal, *, read_only=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle('연결 영향 확인')
        self.resize(720, 480)
        layout = QVBoxLayout(self)
        impact = proposal['impact']
        caption = QLabel('대상: ' + impact['target_title'] + '\n' + impact['meaning']); caption.setWordWrap(True)
        layout.addWidget(caption)
        current = impact['current_reference']
        saved = impact['saved_reference']
        new = impact['proposed_reference']
        text = ('현재 초안 연결: ' + impact.get('current_reference_display', '있음' if current is not None else '없음') + '\n'
                '저장본 연결: ' + impact.get('saved_reference_display', '있음' if saved is not None else '없음') + '\n'
                '저장본 연결과 현재 초안: ' + ('같음' if saved == current else '다름 — 저장본은 유지됩니다') + '\n')
        if proposal.get('source_title'):
            text += '선택한 원본: ' + proposal['source_title'] + '\n'
        if not read_only:
            text += '반영할 연결: ' + impact.get('proposed_reference_display', '명시 해제' if new is None else '선택한 정확한 입력/결과') + '\n'
        text += ('\n보존되는 계산 기록: ' + str(impact['existing_results_preserved']) + '\n'
                 '현재 입력과 달라지는 기존 결과: ' + str(impact['results_becoming_noncurrent']) + '\n'
                 '계수·시험 조건·단위·필드 매핑은 변경하지 않습니다. 새 계산은 실행하지 않습니다.\n')
        if impact.get('availability'):
            text += '\n현재 참조 상태: ' + impact['availability'] + '\n'
        if impact['dependent_documents']:
            text += '\n이 문서를 참조하는 문서 (자동 변경 없음):\n' + '\n'.join(r['title'] for r in impact['dependent_documents'])
        if impact['diagnostics_after']:
            text += '\n\n원도구에서 해결할 입력 진단:\n' + '\n'.join(r['message'] for r in impact['diagnostics_after'])
        self.content = QPlainTextEdit(text); self.content.setReadOnly(True)
        layout.addWidget(self.content, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close if read_only else
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        if read_only:
            self.buttons.button(QDialogButtonBox.StandardButton.Close).setText('닫기')
        else:
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('확인한 연결 반영')
            self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        # Exact IDs/hashes remain available as diagnostics, not primary controls.
        self.proposal = deepcopy(proposal)


class ConnectionWorkflowMixin:
    def _init_workflows(self, persist_view):
        self._persist_view = persist_view
        self._layout = default_state()
        self._view_base, self._view_keys = None, {}
        self._layout_dirty = self._view_failed = False
        self._layout_serial = 0
        self._view_pending = None
        self._close_after_view = False
        self._workflow_operation = None
        self._link_pending, self._link_choice = None, None
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(700)
        self._layout_timer.timeout.connect(self.save_layout)

    def _workflow_menus(self, file_menu, view_menu):
        relation_menu = self.menuBar().addMenu('연결(&L)')
        self.add_link_action = self._action(relation_menu, '연결 추가…', lambda: self.edit_relation('add'), 'Ctrl+L')
        self.repair_link_action = self._action(relation_menu, '원본 참조 복구…', lambda: self.edit_relation('repair'), 'Ctrl+R')
        self.unlink_action = self._action(relation_menu, '연결 해제…', lambda: self.edit_relation('unlink'), 'Ctrl+Delete')
        self.impact_action = self._action(relation_menu, '연결 영향 보기…', self.read_link_impact, 'Alt+I')
        relation_menu.addSeparator()
        self.cancel_link_action = self._action(relation_menu, '연결 선택 취소', self.cancel_relation, 'Escape')
        self.retry_link_action = self._action(relation_menu, '같은 연결 요청 결과 확인', self.retry_relation)
        self.recheck_link_action = self._action(relation_menu, '현재 자료로 연결 다시 확인…', self.recheck_relation)
        self.layout_save_action = self._action(view_menu, '이 프로젝트의 배치 저장', self.save_layout, 'Ctrl+S')
        self.layout_reload_action = self._action(view_menu, '배치 충돌 확인 / 다시 읽기…', self.resolve_layout)
        self.saved_only_action = self._action(file_menu, '저장본만 새 사본으로…', self.prepare_saved_only_copy)

    def _workflow_actions(self, usable, row):
        commands = row.get('actions', {})
        for action, key in ((self.add_link_action, 'add'), (self.repair_link_action, 'repair'),
                            (self.unlink_action, 'unlink'), (self.impact_action, 'impact')):
            action.setEnabled(usable and commands.get(key, {}).get('enabled', False))
        self.cancel_link_action.setEnabled(usable and self._link_choice is not None and self._link_pending is None)
        self.retry_link_action.setEnabled(usable and self._link_pending is not None)
        self.recheck_link_action.setEnabled(usable and self._link_choice is not None)
        self.layout_save_action.setEnabled(usable and self._persist_view and self._view_base is not None)
        self.layout_reload_action.setEnabled(usable and self._persist_view)
        self.saved_only_action.setEnabled(usable and bool(self.checked_documents()))

    @contextmanager
    def _workflow_modal(self):
        self._layout_timer.stop()
        self._modal_depth = getattr(self, '_modal_depth', 0) + 1
        try:
            yield
        finally:
            self._modal_depth -= 1
            if not self._modal_depth and self._layout_dirty and not self._view_failed:
                self._layout_timer.start()

    def edit_relation(self, action):
        row = self.rows.get(self.selected_key, {})
        command = row.get('actions', {}).get(action, {})
        if not command.get('enabled'):
            return False
        target = command.get('target_id')
        self._link_choice = {'target_id': target, 'action': action, 'port': command.get('port'), 'source': None}
        return self._call(lambda: self.client.connection_catalog(target), self._choose_relation)

    def _choose_relation(self, catalog):
        choice = self._link_choice
        dialog = RelationSelectionDialog(catalog, choice['action'], port=choice.get('port'),
                                          prior_source=choice.get('source'), parent=self)
        with self._workflow_modal():
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if not accepted:
            self.cancel_relation()
            return
        request = dialog.request()
        self._link_choice.update(port=request['port'], source=deepcopy(request['source']))
        self._workflow_operation = 'relation-preview'
        self._call(lambda: self.client.connection_preview(**request), self._review_relation)

    def _review_relation(self, proposal):
        self._workflow_operation = None
        dialog = RelationImpactDialog(proposal, parent=self)
        with self._workflow_modal():
            accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if not accepted:
            self.cancel_relation()
            return
        self._link_pending = {'proposal': deepcopy(proposal), 'confirmed': True, 'command_id': 'C' + uuid.uuid4().hex}
        self.retry_relation()

    def retry_relation(self):
        if self._link_pending is None:
            return False
        request = deepcopy(self._link_pending)
        self._workflow_operation = 'relation-apply'
        return self._call(lambda: self.client.connection_apply(**request), self._relation_applied, writing=True)

    def _relation_applied(self, receipt):
        self._workflow_operation = None
        if self._link_choice and self._link_choice['action'] == 'unlink':
            self.selected_key = 'document/' + self._link_choice['target_id']
        self._link_pending, self._link_choice = None, None
        self.message.setText('선택 문서의 초안 연결을 변경했습니다. 저장본과 결과는 그대로이며 계산하지 않았습니다.')
        self.refresh()

    def recheck_relation(self):
        if self._link_choice is None:
            return False
        # A stale refusal has no effect. For response loss, the existing owner
        # receipt should be checked using retry first, never a silent new command.
        if self._link_pending is not None:
            answer = QMessageBox.question(self, '원문서에서 다시 확인',
                '먼저 같은 요청 결과 확인으로 이전 명령의 결과를 확인하세요.\n현재 초안으로 새 변경 내용을 검토할까요? 새 반영에는 다시 확인이 필요합니다.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return False
            self._link_pending = None
        return self._call(lambda: self.client.connection_catalog(self._link_choice['target_id']), self._choose_relation)

    def cancel_relation(self):
        if self._writing or self._link_pending is not None:
            self.message.setText('이미 보낸 명령은 취소로 되돌리지 않습니다. 같은 요청 결과 확인을 사용하세요.')
            return False
        self._link_choice = None
        self.message.setText('연결 선택을 취소했습니다. 문서 참조를 변경하지 않았습니다.')
        self._actions()
        return True

    def read_link_impact(self):
        row = self.rows.get(self.selected_key, {})
        command = row.get('actions', {}).get('repair', {})
        if not command.get('port'):
            return self.show_relations()
        return self._call(lambda: self.client.connection_impact(command['target_id'], command['port']),
                          lambda result: RelationImpactDialog(result, read_only=True, parent=self).exec())

    def prepare_saved_only_copy(self):
        chosen = self.checked_documents()
        if chosen:
            self._call(lambda: self.client.portable_inspect(chosen, draft_policy='saved_only'), self._review_copy)

    def _load_graph_view(self, graph, initial):
        view = graph.get('view_state')
        if initial and view and 'state' in view:
            self._view_base = deepcopy(view)
            self._layout = deepcopy(view['state'])
        self._layout, self._view_keys = merge_bindings(graph, self._layout)
        if initial and self._view_base and self._view_base['revision']:
            for key, view_key in self._view_keys.items():
                if view_key in self._layout['positions']:
                    self.positions[key] = QPointF(*self._layout['positions'][view_key])
                if view_key == self._layout['selected']:
                    self.selected_key = key
            self.search.setText(self._layout['filter'])
            self.tabs.setCurrentIndex(self._layout['panel']['tab'])
            self.document_dock.setVisible(self._layout['panel']['document_visible'])
            self.resizeDocks([self.document_dock], [self._layout['panel']['document_width']], Qt.Orientation.Horizontal)
            return set(self._layout['checked_documents'])
        return None

    def _mark_layout(self, *_):
        if not self._persist_view or self._populating or self._closed or self._view_base is None:
            return
        self._layout_dirty = True
        self._layout_serial += 1
        if not self._view_failed:
            self._layout_timer.start()

    def _layout_snapshot(self):
        state = deepcopy(self._layout)
        for key, view_key in self._view_keys.items():
            position = self.positions.get(key)
            if position is not None:
                state['positions'][view_key] = [position.x(), position.y()]
        state['selected'] = self._view_keys.get(self.selected_key)
        state['checked_documents'] = self.checked_documents()
        state['filter'] = self.search.text()
        state['graph_documents'] = deepcopy((self.graph or {}).get('filter_document_ids'))
        state['panel'] = {'tab': self.tabs.currentIndex(), 'document_visible': not self.document_dock.isHidden(),
                          'document_width': max(180, min(640, self.document_dock.width())),
                          'zoom': max(.25, min(2.5, self.view.transform().m11()))}
        return state

    def save_layout(self, *_):
        if not self._persist_view or self._view_base is None or self._closed:
            return False
        if self._busy or getattr(self, '_modal_depth', 0):
            if not self._view_failed:
                self._layout_timer.start()
            return False
        self._layout_timer.stop()
        if self._view_pending is None:
            self._view_pending = {'state': self._layout_snapshot(), 'scope': self._view_base['scope'],
                'expected_revision': self._view_base['revision'], 'expected_sha256': self._view_base['state_sha256'],
                'command_id': 'C' + uuid.uuid4().hex}
            self._view_saving_serial = self._layout_serial
        request = deepcopy(self._view_pending)
        self._workflow_operation = 'view-save'
        return self._call(lambda: self.client.connection_view_save(**request), self._view_saved, writing=True)

    def _view_saved(self, receipt):
        self._view_base = deepcopy(receipt)
        self._view_pending = None
        self._view_failed = False
        self._workflow_operation = None
        self._layout_dirty = self._layout_serial != self._view_saving_serial
        if self._layout_dirty:
            self._layout_timer.start()
        elif self._close_after_view:
            self._close_after_view = False
            self.close()
        else:
            self.message.setText('이 프로젝트의 배치와 선택을 저장했습니다. 문서 입력/결과는 변경하지 않았습니다.')

    def resolve_layout(self):
        self._layout_timer.stop()
        local = self._layout_snapshot()
        answer = QMessageBox.question(self, '프로젝트 배치 다시 읽기',
            '현재 창의 배치와 선택을 유지할까요?\n예: 서버 개정만 확인하고 내 배치를 유지합니다. 이후 배치 저장으로 반영합니다.\n아니요: 서버 배치로 되돌립니다.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        def loaded(value):
            self._view_base = deepcopy(value)
            self._view_pending = None
            self._view_failed = False
            if answer == QMessageBox.StandardButton.Yes:
                self._layout = local
                self._layout_dirty = True
                # No automatic overwrite of the other window's layout.
                self.message.setText('내 배치와 선택을 유지했습니다. 배치 저장으로 명시적으로 반영하세요.')
            else:
                self._layout = deepcopy(value['state'])
                self.positions = {}
                self.selected_key = None
                graph = deepcopy(self.graph)
                graph['view_state'] = value
                self.graph = None
                self.set_graph(graph)
                self._layout_dirty = False
                self._layout_timer.stop()
        return self._call(self.client.connection_view_read, loaded)

    def _workflow_error(self):
        if self._workflow_operation == 'view-save':
            self._view_failed = True
            self._close_after_view = False
            self._layout_timer.stop()
        self._workflow_operation = None
        # Do not discard a selected source/port or uncertain owner command ID.

    def _layout_close_guard(self, event):
        if self._persist_view and self._layout_dirty:
            event.ignore()
            self._close_after_view = True
            if self._view_failed:
                self._close_after_view = False
                answer = QMessageBox.question(self, '화면 배치 저장 실패',
                    '문서 입력과 결과는 각 도구에 보존되어 있습니다.\n화면 배치만 저장하지 않고 닫을까요? 아니요를 선택하면 현재 배치와 선택을 유지합니다.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if answer == QMessageBox.StandardButton.Yes:
                    self._layout_dirty = False
                    self._layout_timer.stop()
                    return False
                self.message.setText('배치와 선택을 유지했습니다. 배치 충돌 확인 또는 같은 저장 재시도를 사용하세요.')
            else:
                self.save_layout()
            return True
        self._layout_timer.stop()
        return False
