"""Material host of Numerical's public Plan widget and Pro transport adapter."""
from copy import deepcopy
import uuid

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)


def material_variable_labels(document):
    from .material_window import PARAMETERS, PARAMETER_LABELS
    material = document['draft'].get('material', {}).get('draft', {})
    model = material.get('settings', {}).get('model')
    return {key: PARAMETER_LABELS[key] for key in PARAMETERS.get(model, ())} if material.get('backend') == 'material.felupe' else {}


class PlanPatchDialog(QDialog):
    def __init__(self, preview, document, parent=None):
        super().__init__(parent)
        self.setWindowTitle('피팅 변수 변경 검토')
        self.resize(740, 420)
        layout = QVBoxLayout(self)
        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(['변수', '항목', '현재', '편집'])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table)
        variables = document['draft'].get('variables', [])
        parameter_labels = material_variable_labels(document)
        labels = {'value': '시작값', 'lower': '하한', 'upper': '상한', 'free': '탐색', 'transform': '변환'}
        for item in preview['items']:
            for change in item['changes']:
                path = change['path'].strip('/').split('/')
                variable = variables[int(path[1])] if len(path) == 3 and path[0] == 'variables' and path[1].isdigit() and int(path[1]) < len(variables) else {}
                field = path[-1]
                identifier = variable.get('id', '계획 입력')
                name = parameter_labels.get(identifier, identifier) + (' [' + str(variable['unit']) + ']' if isinstance(variable.get('unit'), str) else '')
                def shown(value):
                    if value is None:
                        return '비어 있음'
                    if isinstance(value, (list, dict)):
                        return '변경됨'
                    if field == 'free':
                        return '탐색' if value is True else '고정' if value is False else str(value)
                    return {'linear': '선형', 'log': '로그'}.get(value, str(value)) if isinstance(value, str) else str(value)
                row = table.rowCount(); table.insertRow(row)
                for column, value in enumerate((name, labels.get(field, '계획 입력'), shown(change['before']), shown(change['after']))):
                    table.setItem(row, column, QTableWidgetItem(str(value)))
        issue = any(item.get('conflict') for item in preview['items'])
        layout.addWidget(QLabel('계획이 변경되었습니다. 편집을 유지하고 다시 읽기 전에 확인하세요.' if issue else document['title']))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).setText('편집 적용')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(not issue)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MaterialPlanPanel(QWidget):
    def __init__(self, material, parent=None):
        super().__init__(parent)
        self.material = material
        self.client = material.client
        self._busy = self._binding = False
        self._worker = None
        self._documents, self._widgets, self._adapters = {}, {}, {}
        self._related_save_receipts = {}
        self._related_save_pending = {}
        self._related_save_unconfirmed = set()
        self._related_save_recovery_context = None
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.plans = QComboBox()
        self.plans.setMinimumContentsLength(16)
        self.plans.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        refresh, create = QPushButton('다시 읽기'), QPushButton('계획 만들기…')
        self.open_button, self.save_button = QPushButton('계획 창 열기'), QPushButton('계획 저장')
        self.related_save_button = QPushButton('함께 저장…')
        self.save_receipt_button = QPushButton('저장 결과…')
        row.addWidget(QLabel('피팅 계획')); row.addWidget(self.plans, 1)
        for button in (refresh, create, self.open_button, self.save_button): row.addWidget(button)
        layout.addLayout(row)
        self.badge, self.message = QLabel(), QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.badge)
        saves = QHBoxLayout(); saves.addWidget(self.related_save_button); saves.addWidget(self.save_receipt_button); saves.addStretch()
        layout.addLayout(saves)
        self.stack = QStackedWidget(); layout.addWidget(self.stack, 1)
        self.empty = QLabel('피팅 계획 없음'); self.stack.addWidget(self.empty)
        layout.addWidget(self.message)
        refresh.clicked.connect(self.refresh_plans)
        create.clicked.connect(material.open_numerical)
        self.open_button.clicked.connect(self.open_plan)
        self.save_button.clicked.connect(self.save_plan)
        self.related_save_button.clicked.connect(self.save_related)
        self.save_receipt_button.clicked.connect(lambda: self.save_related(receipt_id=self._related_save_receipts.get(self.plans.currentData())))
        self.plans.currentIndexChanged.connect(self._selected)
        self.restore_related_save_context(getattr(material, '_related_save_recovery_context', None))

    def _call(self, function, after):
        if self._busy:
            self.message.setText('계획 요청 결과를 기다리는 중입니다. 편집은 보존됩니다.')
            return False
        from .material_window import _Call
        self._busy = True
        self.setEnabled(False)
        worker = self._worker = _Call(function)
        def done(value, error):
            self._busy = False; self._worker = None; self.setEnabled(True)
            if error:
                self.message.setText('계획 요청을 처리하지 못했습니다. 편집은 보존됩니다.')
                self.message.setToolTip(error)
            else:
                after(value)
        worker.signals.finished.connect(done, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def refresh_plans(self):
        material_id = self.material.document['id'] if self.material.document else None
        def received(payload):
            if not self.material.document or self.material.document['id'] != material_id:
                return
            documents = [document for document in payload['documents'] if document.get('kind') == 'numerical'
                         and isinstance(document.get('draft', {}).get('material'), dict)
                         and document['draft']['material'].get('document_id') == material_id]
            present = {document['id'] for document in documents}
            documents += [deepcopy(self._documents[identifier]) for identifier, widget in self._widgets.items()
                          if identifier not in present and widget.has_unapplied_buffer()]
            selected = self.plans.currentData()
            self.plans.blockSignals(True); self.plans.clear()
            for document in documents:
                identifier = document['id']
                if identifier not in self._widgets or not self._widgets[identifier].has_unapplied_buffer():
                    self._documents[identifier] = deepcopy(document)
                self.plans.addItem(document['title'], identifier)
            self.plans.setCurrentIndex(max(0, self.plans.findData(selected)))
            self.plans.blockSignals(False)
            self._restore_related_save_selection()
            self._selected()
        return self._call(self.client.documents, received)

    def _bind(self, identifier, document):
        self._binding = True
        try:
            self._widgets[identifier].bind_owner(self._adapters[identifier], document)
            self._widgets[identifier].set_variable_labels(material_variable_labels(document))
            self._documents[identifier] = deepcopy(document)
        except ValueError as error:
            self.message.setText(str(error))
        finally:
            self._binding = False

    def _selected(self):
        identifier = self.plans.currentData()
        self.open_button.setEnabled(bool(identifier)); self.save_button.setEnabled(bool(identifier))
        self.related_save_button.setEnabled(bool(identifier))
        self.save_receipt_button.setEnabled(identifier in self._related_save_receipts)
        if not identifier:
            self.stack.setCurrentWidget(self.empty)
            self.badge.setText('이 재료의 피팅 계획이 없습니다.'); return
        if identifier not in self._widgets:
            from caelab.plan_variables_api import PlanOwnerAdapter, embed_plan_variables
            from .plan_variables_widget import NumericalPlanVariablesWidget
            adapter = self._adapters[identifier] = PlanOwnerAdapter(self.client, identifier)
            widget = embed_plan_variables(NumericalPlanVariablesWidget, parent=self.stack,
                                          adapter=adapter, document=self._documents[identifier])
            widget.set_variable_labels(material_variable_labels(self._documents[identifier]))
            widget.owner_label.hide()  # The host selector already shows the same title.
            self._widgets[identifier] = widget; self.stack.addWidget(widget)
            widget.patchPreviewRequested.connect(lambda preview, key=identifier: self.review_patch(key, preview))
            widget.ownerActivated.connect(lambda key: self._owner_activated(key))
        self.stack.setCurrentWidget(self._widgets[identifier])
        self._bind(identifier, self._documents[identifier])
        self.update_badge()

    def _owner_activated(self, identifier):
        if self._binding or not identifier:
            return
        document = self._widgets[identifier].document_snapshot()
        if document is not None:
            self._documents[identifier] = document
        self.update_badge()

    def update_badge(self):
        document = self._documents.get(self.plans.currentData())
        if not document or not self.material.document:
            return
        reference = document['draft'].get('material', {})
        self.badge.setText('재료 편집 적용 전' if self.material.local_dirty else
            '현재 재료 입력을 참조' if reference.get('input_revision') == self.material.document['input_revision'] else '이전 재료 입력을 참조')

    def review_patch(self, identifier, preview):
        dialog = PlanPatchDialog(preview, self._documents[identifier], self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        def applied(result):
            widget = self._widgets[identifier]
            if widget.show_patch_result(result):
                outcome = next(item for item in result['outcomes'] if item['document_id'] == identifier)
                self._documents[identifier] = deepcopy(outcome['response']['document'])
            self.update_badge()
        self._call(lambda: self._adapters[identifier].execute(preview), applied)

    def save_plan(self):
        identifier = self.plans.currentData()
        if not identifier:
            return
        if self._widgets[identifier].has_unapplied_buffer():
            self.message.setText('변수 변경을 검토하고 적용한 뒤 계획을 저장하세요.'); return
        document = deepcopy(self._documents[identifier])
        def saved(response):
            self._bind(identifier, response['document'])
            self.message.setText('계획을 저장했습니다.')
        self._call(lambda: self.client.document_command(identifier, 'document.save', {},
            session_id=document['session_id'], expected_generation=document['generation'],
            command_id='C' + uuid.uuid4().hex), saved)

    def open_plan(self):
        if self.plans.currentData():
            from .numerical_window import NumericalWindow
            window = NumericalWindow(self.client, document_id=self.plans.currentData())
            self.material._numerical_windows.append(window); window.show(); window.raise_()

    def save_related(self, *, receipt_id=None):
        identifier = self.plans.currentData()
        if not identifier or self._busy:
            return False
        if receipt_id is None and identifier in self._related_save_unconfirmed:
            receipt_id = self._related_save_receipts[identifier]
        material = self.material
        # Inspect without committing a delegate. Saving cannot discard an invalid
        # or unfinished cell merely because the user chose another document.
        editing = any(table.state() == QAbstractItemView.State.EditingState
                      for table in (material.history, material.coefficients))
        widget = self._widgets[identifier]
        unapplied = editing or material.local_dirty or widget.has_unapplied_buffer() or material.conflict or material._busy
        if receipt_id is None and unapplied:
            self.message.setText('재료와 계획의 셀 편집을 먼저 검토하고 적용하세요. 미확정 입력은 보존됩니다.')
            return False
        from .material_related_save import RelatedSaveDialog
        before_material = deepcopy(material.document)
        before_plan = deepcopy(self._documents[identifier])
        dialog = RelatedSaveDialog(self.client, before_material, before_plan, self, receipt_id=receipt_id,
            pending_preview=self._related_save_pending.get(identifier) if receipt_id else None,
            allow_writes=not unapplied)
        def attempted(preview):
            self._related_save_receipts[identifier] = preview['receipt_id']
            self._related_save_pending[identifier] = deepcopy(preview)
            self._related_save_unconfirmed.add(identifier)
            self.save_receipt_button.setEnabled(True)
        dialog.saveAttempted.connect(attempted)
        from .recovery_focus import RawEditorFocusGuard
        with RawEditorFocusGuard([material]):
            dialog.exec()
        # A saved receipt is evidence about the reviewed input. It must not
        # overwrite a later peer edit or an editor opened while saving.
        if dialog.receipt:
            self._related_save_receipts[identifier] = dialog.receipt['receipt_id']
            self.save_receipt_button.setEnabled(True)
            publication_state = dialog.receipt.get('publication', {}).get('state')
            if dialog.receipt.get('state') != 'UNCONFIRMED' and publication_state not in ('UNKNOWN', 'UPDATING', 'SAVING'):
                self._related_save_unconfirmed.discard(identifier)
            if not dialog.allow_writes:
                return True  # Inspection never rebinds a pending editor.
            def same_base(current, base):
                return (current and all(current.get(key) == base.get(key)
                    for key in ('id', 'session_id', 'generation', 'input_revision', 'draft')))
            for target in dialog.receipt['targets']:
                if target['state'] != 'SAVED': continue
                saved = target['attempts'][-1]['response']['document']
                base = before_material if target['identity']['document_id'] == before_material['id'] else before_plan
                from caelab.related_save import input_identity
                identity = input_identity(base)
                if any(target['identity'][key] != identity[key] for key in
                       ('document_id', 'session_id', 'generation', 'input_revision', 'input_sha256')):
                    continue
                if target['identity']['document_id'] == before_material['id']:
                    if not material.local_dirty and same_base(material.document, before_material):
                        material._show_document(saved, preserve_history=True)
                elif (not widget.has_unapplied_buffer()
                      and same_base(widget.document_snapshot(), before_plan)):
                    publication = dialog.receipt.get('publication', {})
                    if publication.get('state') == 'NOT_REQUESTED':
                        self._bind(identifier, saved)
                    elif publication.get('state') == 'PUBLISHED':
                        final = publication['save_target']['attempts'][-1]['response']['document']
                        self._bind(identifier, final)
            self.update_badge()
        return True

    def has_pending_inputs(self):
        return self._busy or bool(self._related_save_unconfirmed) or any(widget.has_unapplied_buffer() or (widget.document_snapshot() or {}).get('dirty')
                                 for widget in self._widgets.values())

    def related_save_snapshot(self):
        """Noncommitting context, including attempts whose reply was lost."""
        context = deepcopy(self._related_save_recovery_context) or {
            'material_id': self.material.document['id'], 'selected_plan': None, 'plans': {}}
        context['selected_plan'] = self.plans.currentData() or context['selected_plan']
        for identifier, receipt_id in self._related_save_receipts.items():
            context['plans'][identifier] = dict(receipt_id=receipt_id,
                pending_preview=deepcopy(self._related_save_pending.get(identifier)),
                unconfirmed=identifier in self._related_save_unconfirmed)
        return context if context['plans'] else None

    def restore_related_save_context(self, context):
        from .material_save_recovery import checked_context
        context = checked_context(context, self.material.document['id']) if context is not None else None
        if context is None:
            return
        if self._related_save_receipts or self._busy:
            raise ValueError('현재 저장 결과를 유지합니다. 보관한 요청은 새 창에서 여세요.')
        self._related_save_recovery_context = context
        for identifier, item in context['plans'].items():
            self._related_save_receipts[identifier] = item['receipt_id']
            if item['pending_preview'] is not None:
                self._related_save_pending[identifier] = deepcopy(item['pending_preview'])
            if item['unconfirmed']:
                self._related_save_unconfirmed.add(identifier)
        self._restore_related_save_selection()

    def _restore_related_save_selection(self):
        context = self._related_save_recovery_context
        if context is None:
            return
        index = self.plans.findData(context['selected_plan'])
        if index >= 0:
            self.plans.setCurrentIndex(index)
            self.save_receipt_button.setEnabled(self.plans.currentData() in self._related_save_receipts)
            self.message.setText('보관한 저장 요청이 있습니다. 저장 결과에서 원래 결과를 확인하세요.')

    def recovery_ready(self):
        return not self._busy and all(widget.recovery_ready() for widget in self._widgets.values()
                                     if widget.document_snapshot() is not None)

    def recovery_views(self):
        """Independent owner receipts and noncommitting widget callbacks."""
        views=[]
        for widget in self._widgets.values():
            document=widget.document_snapshot()
            if document is not None:
                views.append((document,widget.recovery_snapshot,widget.restore_recovery))
        return views
