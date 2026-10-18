"""Material host of Numerical's public Plan widget and Pro transport adapter."""
from copy import deepcopy
import uuid

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QSplitter, QMessageBox)


def material_variable_labels(document):
    from .material_window import PARAMETERS, PARAMETER_LABELS
    material = document['draft'].get('material', {}).get('draft', {})
    model = material.get('settings', {}).get('model')
    return {key: PARAMETER_LABELS[key] for key in PARAMETERS.get(model, ())} if material.get('backend') == 'material.felupe' else {}


def _plan_identity(document):
    from caelab.storage import canonical_hash
    return (document['id'],document['session_id'],document['generation'],document['input_revision'],canonical_hash(document['draft']))


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
        self._related_save_material_id = material.document['id']
        self._related_save_selection_pending = False
        self._pending_observation = self._staged_observation = None
        self._source_titles = {}
        self._trial_results = {}
        self._drawn_trial = None
        self._trial_plot_active = False
        self._observation_material_id = None
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
        row.addWidget(refresh)
        layout.addLayout(row)
        self.badge, self.message = QLabel(), QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.badge)
        saves = QHBoxLayout()
        for button in (create,self.open_button,self.save_button,self.related_save_button,self.save_receipt_button):saves.addWidget(button)
        saves.addStretch()
        layout.addLayout(saves)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.stack = QStackedWidget(); split.addWidget(self.stack)
        self.empty = QLabel('피팅 계획 없음'); self.stack.addWidget(self.empty)
        trials = QWidget(); trial_layout = QVBoxLayout(trials); trial_layout.setContentsMargins(0,0,0,0)
        trial_layout.addWidget(QLabel('선택한 계획의 시험'))
        self.trials = QTableWidget(0,4)
        self.trials.setHorizontalHeaderLabels(['시험','용도','관측','모델 응답'])
        self.trials.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.trials.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.trials.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.trials.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.trials.itemSelectionChanged.connect(lambda:self.show_trial(force=True))
        self.trials.itemClicked.connect(lambda item:self.show_trial(force=True))
        trial_layout.addWidget(self.trials)
        self.observation_button = QPushButton('전달받은 시험 등록…')
        self.observation_button.hide(); self.observation_button.clicked.connect(self.review_observation)
        trial_layout.addWidget(self.observation_button)
        split.addWidget(trials); split.setSizes([500,650]); layout.addWidget(split,1)
        layout.addWidget(self.message)
        refresh.clicked.connect(self.refresh_plans)
        create.clicked.connect(material.create_numerical)
        self.open_button.clicked.connect(self.open_plan)
        self.save_button.clicked.connect(self.save_plan)
        self.related_save_button.clicked.connect(self.save_related)
        self.save_receipt_button.clicked.connect(lambda: self.save_related(receipt_id=self._related_save_receipts.get(self.plans.currentData())))
        self.plans.currentIndexChanged.connect(self._selected)
        from .material_save_recovery import context_for
        self.restore_related_save_context(context_for(material, material.document['id']))

    def _call(self, function, after, *, failed=None):
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
                if failed:failed(error)
            else:
                after(value)
        worker.signals.finished.connect(done, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def refresh_plans(self):
        material_id = self.material.document['id'] if self.material.document else None
        if material_id != self._related_save_material_id:
            from .material_save_recovery import context_for, remember_context
            remember_context(self.material, self.related_save_snapshot())
            for widget in self._widgets.values():
                widget.detach_owner(); self.stack.removeWidget(widget); widget.deleteLater()
            self._widgets.clear(); self._documents.clear(); self._adapters.clear()
            self._related_save_receipts.clear(); self._related_save_pending.clear(); self._related_save_unconfirmed.clear()
            self._related_save_recovery_context = None
            self._related_save_selection_pending = False
            self._related_save_material_id = material_id
            self.restore_related_save_context(context_for(self.material, material_id))
        def received(payload):
            if not self.material.document or self.material.document['id'] != material_id:
                return
            self._drawn_trial=None
            self._source_titles = {document['id']:document['title'] for document in payload['documents']}
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
            self._restore_related_save_selection(final=True)
            self._selected()
            if self._pending_observation:
                self.review_observation()
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
            self.trials.setRowCount(0)
            self.show_trial(force=True)
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
            router = self.material.undo_router
            router.register_target(widget, undo=widget.undo, redo=widget.redo,
                can_undo=widget.undo_button.isEnabled, can_redo=widget.redo_button.isEnabled,
                label=lambda key=identifier:self._documents[key]['title'])
            widget.activityChanged.connect(router.refresh)
        self.stack.setCurrentWidget(self._widgets[identifier])
        self._bind(identifier, self._documents[identifier])
        self.update_badge()

    def receive_observation(self, source):
        if self._staged_observation:
            self.message.setText('앞선 시험 등록 결과를 먼저 확인하세요. 전달받은 자료는 바꾸지 않았습니다.')
            return False
        self._pending_observation = deepcopy(source)
        self._observation_material_id = self.material.document['id']
        self.observation_button.show()
        if not self._busy:self.review_observation()
        return True

    def review_observation(self):
        if self._busy:return False
        if self._observation_material_id != self.material.document['id']:
            self.message.setText('전달받은 시험의 대상 재료가 바뀌었습니다. 원래 재료를 열어 등록 결과를 확인하세요.')
            return False
        if self._staged_observation:return self._apply_observation()
        source = deepcopy(self._pending_observation)
        if not source:return False
        identifier = self.plans.currentData()
        if not identifier:
            if QMessageBox.question(self, '피팅 계획 만들기', '이 재료에 연결된 계획이 없습니다. 전달받은 시험을 등록할 새 피팅 계획을 만들까요?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel) != QMessageBox.StandardButton.Yes:
                return False
            from caelab.numerical_document import from_material_document
            draft = from_material_document(self.material.document)
            return self._call(lambda:self.client.document_open(kind='numerical',title='재료 피팅',draft=draft),
                lambda document:self.refresh_plans())
        widget = self._widgets[identifier]
        if widget.has_unapplied_buffer():
            self.message.setText('선택 계획의 변수 편집을 적용하거나 실행 취소한 뒤 시험을 등록하세요.')
            return False
        base = deepcopy(self._documents[identifier])
        material_identity = (self.material.document['id'],self.material.document['session_id'],self.material.document['generation'])
        def read():
            from caelab.storage import canonical_hash
            current = self.client.document_read(identifier)
            if _plan_identity(current) != _plan_identity(base):
                raise ValueError('선택 계획이 다른 창에서 변경되었습니다. 다시 읽은 뒤 시험을 등록하세요.')
            data = self.client.document_read(source['document_id'])
            exact = self.client.document_result_reference(source['document_id'],source['job_id'])
            for key in ('document_id','job_id','input_revision','input_sha256'):
                if exact.get(key) != source.get(key):raise ValueError('전달받은 시험과 저장한 자료 입력이 다릅니다.')
            result = self.client.document_result(source['document_id'],source['job_id'])
            if canonical_hash(result) != exact['result_sha256']:
                raise ValueError('전달받은 시험의 저장 결과가 다릅니다.')
            observation = result.get('responses',{}).get(source['response'],{})
            if result.get('execution_status') != 'SUCCEEDED' or observation.get('kind') != 'series':
                raise ValueError('저장한 시험에 사용할 관측이 없습니다.')
            return current,result,data['title']
        def reviewed(payload):
            current,result,title = payload
            if (source != self._pending_observation or identifier != self.plans.currentData() or
                    material_identity != (self.material.document['id'],self.material.document['session_id'],self.material.document['generation']) or
                    self.material.local_dirty or self.material.conflict):
                self.message.setText('검토할 재료나 계획이 변경되었습니다. 전달받은 시험을 다시 등록하세요.')
                return
            from .material_test_dialog import ExperimentDialog
            dialog = ExperimentDialog(current['draft']['material']['draft']['settings'],result,self,selected=source['response'])
            dialog._buttons.button(QDialogButtonBox.StandardButton.Ok).setText('시험 등록')
            if dialog.exec() != QDialog.DialogCode.Accepted:return
            if (identifier != self.plans.currentData() or widget.has_unapplied_buffer() or
                    material_identity != (self.material.document['id'],self.material.document['session_id'],self.material.document['generation']) or
                    self.material.local_dirty or self.material.conflict):
                self.message.setText('검토 중 입력이 변경되었습니다. 시험을 다시 등록하세요.')
                return
            value = dialog.value
            if value['name'] != source['response']:
                self.message.setText('Data에서 전달한 관측과 선택한 관측이 다릅니다. Data에서 다시 선택하세요.')
                return
            draft = deepcopy(current['draft'])
            index = 1
            while 'Test'+str(index) in {trial['id'] for trial in draft['experiments']}:index += 1
            trial = dict(id='Test'+str(index),role=value['role'],source=deepcopy(source),response=value['response'],
                settings=deepcopy(value['settings']),weight=value['weight'],scale=value['scale'])
            from .finite_measure_gui import copy_trial_extensions
            copy_trial_extensions(trial,value)
            if value['kinematics'] is not None:trial['kinematics']=deepcopy(value['kinematics'])
            draft['experiments'].append(trial)
            self._staged_observation = dict(document=current,draft=draft,command_id='C'+uuid.uuid4().hex)
            self._source_titles[source['document_id']] = title
            self._apply_observation()
        return self._call(read,reviewed)

    def _apply_observation(self):
        staged = deepcopy(self._staged_observation)
        if not staged or self._busy:return False
        if self._observation_material_id != self.material.document['id']:
            self.message.setText('시험을 검토한 원래 재료를 열어 등록 결과를 확인하세요.')
            return False
        base = staged['document']
        self.observation_button.setText('시험 등록 결과 확인')
        def apply():
            response = self.client.document_command(base['id'],'numerical.update',{'draft':staged['draft']},
                session_id=base['session_id'],expected_generation=base['generation'],command_id=staged['command_id'])
            return response,self.client.document_read(base['id'])
        def applied(payload):
            response,current = payload
            accepted = response['document']
            if (accepted['draft'] != staged['draft'] or _plan_identity(accepted) != _plan_identity(current)):
                self.message.setText('등록 뒤 계획이 변경되었습니다. 이전 시험과 편집을 보존했습니다. 계획을 다시 읽어 확인하세요.')
                return
            self._staged_observation = self._pending_observation = None
            self.observation_button.hide(); self.observation_button.setText('전달받은 시험 등록…')
            self._bind(base['id'],accepted); self.update_badge()
            self.message.setText('선택한 계획에 시험을 등록했습니다. 계획 저장 후 계산을 실행할 수 있습니다.')
        return self._call(apply,applied)

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
        selected=self.trials.currentRow()
        experiments = document['draft'].get('experiments',[])
        self.trials.blockSignals(True)
        self.trials.setRowCount(len(experiments))
        for row,trial in enumerate(experiments):
            source=trial['source']
            values=(self._source_titles.get(source.get('document_id'),'시험 '+str(row+1)),
                {'fit':'피팅','holdout':'별도 확인'}.get(trial['role'],trial['role']),source['response'],trial['response'])
            for column,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip(str(source));self.trials.setItem(row,column,item)
        if experiments:self.trials.selectRow(max(0,min(selected,len(experiments)-1)))
        self.trials.blockSignals(False)
        self.show_trial()
        self.badge.setText('재료 편집 적용 전' if self.material.local_dirty else
            '현재 재료 입력을 참조' if reference.get('input_revision') == self.material.document['input_revision'] else '이전 재료 입력을 참조')

    def show_trial(self, *, force=False):
        document=self._documents.get(self.plans.currentData())
        row=self.trials.currentRow()
        if self._busy or self._pending_observation or self._staged_observation:return
        if not document or row<0 or not document.get('runs'):
            empty_key=(_plan_identity(document) if document else None,'NO_RESULT')
            if force or self._trial_plot_active and self._drawn_trial!=empty_key:
                self._clear_trial_plot('선택한 시험의 저장된 계산 결과가 없습니다.')
                self._drawn_trial=empty_key
            return
        experiments=document['draft'].get('experiments',[])
        if row>=len(experiments):return
        trial_id=experiments[row]['id']
        run=deepcopy(document['runs'][-1]);job=run['job_id']
        frozen=next((trial for trial in run.get('draft',{}).get('experiments',[]) if trial.get('id')==trial_id),None)
        key=(_plan_identity(document),job,run.get('input_revision'),run.get('input_sha256'),trial_id)
        if key==self._drawn_trial and not force:return
        self.material._result_view_serial += 1
        view_serial=self.material._result_view_serial
        self._clear_trial_plot('선택한 시험의 저장 결과를 읽는 중입니다…')
        self._drawn_trial=key
        if frozen is None:
            self._clear_trial_plot('이 실행에는 선택한 시험이 없습니다. 원래 실행을 Numerical에서 확인하세요.')
            self._drawn_trial=key
            return
        def draw(result):
            if (self.material._result_view_serial!=view_serial or
                    self.material._active_result_view!='plan'):return
            current=self._documents.get(self.plans.currentData())
            live_row=self.trials.currentRow()
            if (not current or _plan_identity(current)!=key[0] or live_row<0 or
                    live_row>=len(current['draft'].get('experiments',[])) or
                    current['draft']['experiments'][live_row]['id']!=trial_id or
                    not current.get('runs') or current['runs'][-1]['job_id']!=job or
                    current['runs'][-1].get('input_sha256')!=run.get('input_sha256')):
                self.show_trial(force=True)
                return
            self._trial_results[(document['id'],job)]=deepcopy(result)
            curve=next((curve for curve in result.get('curves',[]) if curve.get('experiment_id')==trial_id),None)
            if result.get('kind')!='fit' or curve is None:
                self._clear_trial_plot('선택한 실행에 이 시험의 곡선이 없습니다. 실패 내용은 Numerical에서 확인하세요.')
                self._drawn_trial=key
                return
            self._drawn_trial=key
            from .numerical_window import plot_fit_trial, fit_trial_status
            observed=curve.get('observations',{})
            axes=observed.get('axes',[])
            if len(axes)!=1:
                self._clear_trial_plot('선택 시험의 축을 곡선으로 표시할 수 없습니다. Numerical에서 원 결과를 확인하세요.')
                self._drawn_trial=key
                return
            figure=self.material.figure;figure.clear()
            self.material._active_result_view='plan'
            self.material.material_results_panel.hide()
            blocked=self.material.response.blockSignals(True)
            self.material.response.setCurrentIndex(self.material.response.findData(frozen['response']))
            self.material.response.blockSignals(blocked);self.material.response.setEnabled(False)
            prediction_ax,residual_ax=plot_fit_trial(figure,result,curve)
            name=self._source_titles.get(frozen['source'].get('document_id'),'시험 '+str(row+1))
            stale=run.get('draft')!=document['draft']
            state=fit_trial_status(result,curve,include_reason=False)
            prediction_ax.set_title(('이전 계획 입력 / ' if stale else '')+document['title']+' / '+name+' / '+('별도 확인' if frozen.get('role')=='holdout' else '피팅')+' / '+state,fontsize=10)
            self.message.setText(fit_trial_status(result,curve))
            self.material.canvas.draw_idle()
        result=self._trial_results.get((document['id'],job))
        if result is not None:draw(result)
        else:
            def failed(error):
                if (self.material._result_view_serial==view_serial and self.material._active_result_view=='plan' and
                        self.plans.currentData()==document['id']):
                    self._clear_trial_plot('선택한 시험 결과를 읽지 못했습니다. 다시 읽기를 누르세요.')
            self._call(lambda:self.client.document_result(document['id'],job),draw,failed=failed)

    def _clear_trial_plot(self, message):
        self.material._active_result_view='plan'
        self._trial_plot_active=True
        self._drawn_trial=None
        self.material.figure.clear()
        self.material.axes=self.material.figure.add_subplot(111)
        self.material.axes.text(.5,.5,message,ha='center',va='center',transform=self.material.axes.transAxes,wrap=True)
        self.material.axes.set_axis_off()
        self.material.material_results_panel.hide()
        self.material.canvas.draw_idle()

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
            # A successful immutable save can change only saved metadata while
            # a local delegate stays open. Do not repaint or commit that editor.
            for target in dialog.receipt['targets']:
                if target['state'] != 'SAVED': continue
                saved = target['attempts'][-1]['response']['document']
                if target['identity']['document_id'] == before_material['id']:
                    from .material_save_recovery import saved_metadata
                    refreshed = saved_metadata(material.document, saved,
                        previous_saved_revision=target['identity']['saved_revision'])
                    if refreshed is not None:
                        material.document = refreshed
                elif callable(getattr(widget, 'refresh_saved_metadata', None)):
                    if widget.refresh_saved_metadata(saved, previous_saved_revision=target['identity']['saved_revision']):
                        self._documents[identifier] = widget.document_snapshot()
            if not dialog.allow_writes:
                self.message.setText('저장 결과를 읽었습니다. 편집 원문은 유지됩니다.')
                if material.message.text() == '저장 결과를 먼저 확인하세요. 창과 편집 원문은 유지됩니다.':
                    material.message.setText('저장 결과를 읽었습니다. 편집 원문은 유지됩니다.')
                return True  # Inspection never rebinds a pending editor.
            def same_base(current, base, incoming_saved_revision):
                return (current and all(current.get(key) == base.get(key)
                    for key in ('id', 'session_id', 'generation', 'input_revision', 'draft'))
                    and current.get('saved_revision') in (base.get('saved_revision'), incoming_saved_revision))
            for target in dialog.receipt['targets']:
                if target['state'] != 'SAVED': continue
                saved = target['attempts'][-1]['response']['document']
                base = before_material if target['identity']['document_id'] == before_material['id'] else before_plan
                if base.get('saved_revision') not in (target['identity']['saved_revision'], saved.get('saved_revision')):
                    continue
                from caelab.related_save import input_identity
                identity = input_identity(base)
                if any(target['identity'][key] != identity[key] for key in
                       ('document_id', 'session_id', 'generation', 'input_revision', 'input_sha256')):
                    continue
                if target['identity']['document_id'] == before_material['id']:
                    if not material.local_dirty and same_base(material.document, before_material, saved.get('saved_revision')):
                        material._show_document(saved, preserve_history=True)
                elif (not widget.has_unapplied_buffer()
                      and same_base(widget.document_snapshot(), before_plan, saved.get('saved_revision'))):
                    publication = dialog.receipt.get('publication', {})
                    if publication.get('state') == 'NOT_REQUESTED':
                        self._bind(identifier, saved)
                    elif publication.get('state') == 'PUBLISHED':
                        final = publication['save_target']['attempts'][-1]['response']['document']
                        self._bind(identifier, final)
            self.update_badge()
        return True

    def has_pending_inputs(self):
        return self._busy or bool(self._staged_observation) or bool(self._related_save_unconfirmed) or any(widget.has_unapplied_buffer() or (widget.document_snapshot() or {}).get('dirty')
                                 for widget in self._widgets.values())

    def has_unconfirmed_save(self):
        return bool(self._related_save_unconfirmed)

    def related_save_snapshot(self):
        """Noncommitting context, including attempts whose reply was lost."""
        context = deepcopy(self._related_save_recovery_context) or {
            'material_id': self._related_save_material_id, 'selected_plan': None, 'plans': {}}
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
        self._related_save_selection_pending = True
        for identifier, item in context['plans'].items():
            self._related_save_receipts[identifier] = item['receipt_id']
            if item['pending_preview'] is not None:
                self._related_save_pending[identifier] = deepcopy(item['pending_preview'])
            if item['unconfirmed']:
                self._related_save_unconfirmed.add(identifier)
        self._restore_related_save_selection()

    def _restore_related_save_selection(self, *, final=False):
        context = self._related_save_recovery_context
        if context is None or not self._related_save_selection_pending:
            return
        index = self.plans.findData(context['selected_plan'])
        if index >= 0:
            self._related_save_selection_pending = False
            self.plans.setCurrentIndex(index)
            self.save_receipt_button.setEnabled(self.plans.currentData() in self._related_save_receipts)
            self.message.setText('보관한 저장 요청이 있습니다. 저장 결과에서 원래 결과를 확인하세요.')
        elif final:
            self._related_save_selection_pending = False

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
