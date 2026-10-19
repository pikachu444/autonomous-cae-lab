"""Material host of Numerical's public Plan widget and Pro transport adapter."""
from copy import deepcopy
import uuid

from PySide6.QtCore import Qt, QThreadPool, QTimer, QItemSelectionModel
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QSplitter, QMessageBox, QTabWidget, QInputDialog, QToolButton, QMenu, QPlainTextEdit)


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
        labels = {'value': '시작값', 'lower': '하한', 'upper': '상한', 'free': '탐색', 'transform': '변환',
                  'unit':'단위','id':'계수 이름','model':'재료 법칙','material':'재료 연결'}
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
                    return {'linear': '선형', 'log': '로그','linear_elastic':'선형 탄성','neo_hooke':'Neo-Hooke'}.get(value, str(value)) if isinstance(value, str) else str(value)
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
    def __init__(self, material, parent=None, *, compact=False):
        super().__init__(parent)
        self.compact=compact
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
        self._pending_plan_command = None
        self._request_rejection = None
        self._adoption_owner = None
        self._adoption_timer=QTimer(self)
        self._adoption_timer.setInterval(100)
        self._adoption_timer.timeout.connect(self._sync_adoption_request)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8,8,8,8)
        self.material_context=QLabel();self.material_context.hide()
        row=QHBoxLayout()
        self.plans=QComboBox();self.plans.setMinimumContentsLength(12)
        self.plans.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        row.addWidget(QLabel('피팅 계획'));row.addWidget(self.plans,1)
        self.more_button=QToolButton();self.more_button.setText('관리')
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(self.more_button);self.more_button.setMenu(menu);row.addWidget(self.more_button)
        layout.addLayout(row)
        self.open_button,self.save_button=QPushButton('Numerical에서 열기'),QPushButton('계획 저장')
        self.related_save_button,self.save_receipt_button=QPushButton('함께 저장…'),QPushButton('저장 결과…')
        for title,callback in (('다시 읽기',self.refresh_plans),('계획 만들기…',self.create_plan),
                ('선택 시험 제거…',self.remove_trial),('피팅 모델로 설정…',self.bind_current_material)):
            menu.addAction(title,callback)
        for button in (self.open_button,self.save_button,self.related_save_button,self.save_receipt_button):
            menu.addAction(button.text(),button.click);button.hide()
        self.badge,self.message=QLabel(),QLabel()
        self.badge.setWordWrap(True);self.message.setWordWrap(True)
        self.badge.hide()  # The exact relationship remains in the context tooltip.
        self.retry_command_button=QPushButton('요청 다시 확인')
        self.retry_command_button.hide();self.retry_command_button.clicked.connect(self.retry_plan_command)
        layout.addWidget(self.retry_command_button)
        self.content_splitter=split=QSplitter(Qt.Orientation.Vertical if compact else Qt.Orientation.Horizontal)
        trials=QWidget();trial_layout=QVBoxLayout(trials);trial_layout.setContentsMargins(0,0,0,0)
        trial_layout.addWidget(QLabel('시험'))
        commands=QHBoxLayout()
        self.data_button=QPushButton('시험 데이터 열기…')
        self.data_button.clicked.connect(self.prepare_data)
        self.add_trial_button,self.edit_trial_button=QPushButton('시험 추가…'),QPushButton('조건 편집…')
        commands.addWidget(self.data_button);commands.addWidget(self.add_trial_button);commands.addWidget(self.edit_trial_button)
        self.add_trial_button.clicked.connect(self.add_trial);self.edit_trial_button.clicked.connect(self.edit_trial)
        trial_layout.addLayout(commands)
        self.trials=QTableWidget(0,4)
        self.trials.setHorizontalHeaderLabels(['시험','용도','관측','모델 응답'])
        self.trials.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.trials.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.trials.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.trials.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.trials.hideColumn(2);self.trials.hideColumn(3)
        self.trials.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.trials.setColumnWidth(1,94)
        self.trials.setStyleSheet('QTableWidget::item:selected { background: #2769a4; color: white; }')
        self.trials.setMinimumHeight(118);self.trials.setMaximumHeight(220)
        self.trials.itemSelectionChanged.connect(lambda:self.show_trial(force=True))
        self.trials.currentCellChanged.connect(lambda row,*_:self._whole_trial_row(row))
        self.trials.itemClicked.connect(lambda item:self.show_trial(force=True))
        trial_layout.addWidget(self.trials)

        self.observation_button=QPushButton('전달받은 시험 등록…')
        self.observation_button.hide();self.observation_button.clicked.connect(self.review_observation)
        trial_layout.addWidget(self.observation_button)
        split.addWidget(trials)
        coefficients=QWidget();coefficient_layout=QVBoxLayout(coefficients);coefficient_layout.setContentsMargins(0,0,0,0)
        mode=QHBoxLayout();mode.addWidget(QLabel('재료 계수'))
        self.coefficient_mode=QComboBox();self.coefficient_mode.addItem('피팅 시작값과 범위')
        mode.addWidget(self.coefficient_mode,1);coefficient_layout.addLayout(mode)
        law=QHBoxLayout();law.addWidget(QLabel('재료 모델'))
        label=material.model_form.labelForField(material.model)
        material.model_form.removeWidget(material.model)
        if label:
            material.model_form.removeWidget(label);label.deleteLater()
        law.addWidget(material.model,1);coefficient_layout.addLayout(law)
        self.bind_material_button=QPushButton('피팅 모델로 설정…')
        self.bind_material_button.clicked.connect(self.bind_current_material)
        law.addWidget(self.bind_material_button)
        self.coefficient_tabs=QTabWidget();self.coefficient_tabs.tabBar().hide()
        self.stack=QStackedWidget();self.empty=QLabel('계획을 만들거나 선택하세요.')
        self.stack.addWidget(self.empty);self.coefficient_tabs.addTab(self.stack,'시작값과 범위')
        self.coefficient_mode.currentIndexChanged.connect(self.coefficient_tabs.setCurrentIndex)
        coefficient_layout.addWidget(self.coefficient_tabs,1)
        split.addWidget(coefficients);split.setStretchFactor(0,0);split.setStretchFactor(1,1)
        split.setSizes([240,360]);layout.addWidget(split,1)
        self.fit_button=QPushButton('피팅 실행');self.fit_button.clicked.connect(self.run_fit);self.fit_button.hide()
        self.fit_output=QTabWidget()
        self.runtime_output=QPlainTextEdit();self.runtime_output.setReadOnly(True)
        self.runtime_output.setPlainText('시험과 시작값을 확인한 뒤 상단의 피팅 실행을 누르세요.')
        self.fit_output.addTab(self.runtime_output,'실행 출력')
        self.fit_progress=QTableWidget(0,3)
        self.fit_progress.setHorizontalHeaderLabels(['후보','상태','잔차 제곱합 [1]'])
        self.fit_progress.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.fit_progress.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.fit_output.addTab(self.fit_progress,'진행')
        final=QWidget();final_layout=QVBoxLayout(final)
        self.final_notice=QLabel('저장된 피팅 결과를 선택하세요.');self.final_notice.setWordWrap(True)
        final_layout.addWidget(self.final_notice)
        self.final_parameters=QTableWidget(0,4)
        self.final_parameters.setHorizontalHeaderLabels(['계수','현재 재료','최종 피팅','단위'])
        self.final_parameters.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.final_parameters.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        final_layout.addWidget(self.final_parameters,1)
        self.review_final_button=QPushButton('최종 계수 검토·채택…')
        self.review_final_button.clicked.connect(self.review_final);final_layout.addWidget(self.review_final_button)
        self.fit_output.addTab(final,'피팅 계수')
        layout.addWidget(self.message)
        self.open_button.clicked.connect(self.open_plan);self.save_button.clicked.connect(self.save_plan)
        self.related_save_button.clicked.connect(self.save_related)
        self.save_receipt_button.clicked.connect(lambda:self.save_related(receipt_id=self._related_save_receipts.get(self.plans.currentData())))
        self.plans.currentIndexChanged.connect(self._selected)
        from .material_save_recovery import context_for
        self.restore_related_save_context(context_for(material,material.document['id']))

    def prepare_data(self):
        from .data_window import DataWindow
        window=DataWindow(self.client)
        self.material.__dict__.setdefault('_data_windows',[]).append(window)
        window.show()
        self.message.setText('Data에서 파일의 열·단위를 확인하고 가져온 뒤, 이 창의 시험 추가를 누르세요.')

    def _whole_trial_row(self,row):
        if row<0:return
        previous=self.trials.blockSignals(True)
        self.trials.selectionModel().select(self.trials.model().index(row,0),
            QItemSelectionModel.SelectionFlag.ClearAndSelect|QItemSelectionModel.SelectionFlag.Rows)
        self.trials.blockSignals(previous)

    def bind_current_material(self):
        document=self._documents.get(self.plans.currentData())
        if (not document or self._busy or self.has_pending_plan_request() or self.material.local_dirty
                or self.material.conflict or self._widgets[document['id']].has_unapplied_buffer()):
            self.message.setText('재료와 시작값의 편집을 먼저 적용하세요.');return
        from caelab.numerical_document import from_material_document
        replacement=from_material_document(self.material.document)
        draft=deepcopy(document['draft']);draft.update(material=replacement['material'],variables=replacement['variables'])
        document=deepcopy(document)
        changes=[dict(path='/material',before=document['draft']['material'],after=draft['material'])]
        before=document['draft'].get('variables',[])
        for row,variable in enumerate(draft['variables']):
            old=before[row] if row<len(before) else {}
            for key,value in variable.items():
                if old.get(key)!=value:changes.append(dict(path='/variables/'+str(row)+'/'+key,before=old.get(key),after=value))
        dialog=PlanPatchDialog({'items':[{'changes':changes}]},document,self)
        dialog.setWindowTitle('현재 재료 연결과 시작값 변경 검토')
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        if not self._same_plan(document):
            self.message.setText('검토 중 계획이나 시작값이 바뀌었습니다. 다시 검토하세요.');return
        def applied(receipt):
            if self._same_plan(document):self._bind(document['id'],receipt['document']);self.update_badge()
        self._submit_plan_command(document,'numerical.update',{'draft':draft},applied)

    def remove_trial(self):
        document=self._editable_plan();row=self.trials.currentRow()
        if not document or not 0<=row<len(document['draft'].get('experiments',[])):return
        if QMessageBox.question(self,'시험 제거','선택한 시험을 계획에서 제거할까요? 원자료와 저장된 결과는 유지됩니다.',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Yes:return
        experiments=deepcopy(document['draft']['experiments']);experiments.pop(row)
        self._replace_trials(document,experiments)

    def create_plan(self):
        self.material._commit_cell_editor()
        if self.material.local_dirty or self.material.conflict:
            self.message.setText('현재 재료의 편집을 먼저 적용하세요.');return
        name,ok=QInputDialog.getText(self,'피팅 계획 만들기','계획 이름')
        if not ok or not name.strip():return
        from caelab.numerical_document import from_material_document
        material=deepcopy(self.material.document)
        self._call(lambda:self.client.document_open(kind='numerical',title=name,
            draft=from_material_document(material)),lambda _:self.refresh_plans())

    def _editable_plan(self):
        document=self._documents.get(self.plans.currentData())
        if (self._busy or self.has_pending_plan_request() or not document or self.material.conflict or self.material.local_dirty
                or self._widgets[document['id']].has_unapplied_buffer()):
            self.message.setText('재료와 시작값의 편집을 먼저 검토하고 적용하세요. 원문은 유지됩니다.')
            return None
        return deepcopy(document)

    def _same_plan(self, document):
        current=self._documents.get(self.plans.currentData())
        return bool(current and _plan_identity(current)==_plan_identity(document)
            and not self._widgets[current['id']].has_unapplied_buffer()
            and self.material.document and current['draft']['material']['document_id']==self.material.document['id'])

    def _replace_trials(self, document, experiments):
        if not self._same_plan(document):
            self.message.setText('계획이나 시작값이 바뀌었습니다. 시험을 다시 선택하세요.');return
        draft=deepcopy(document['draft']);draft['experiments']=experiments
        def applied(receipt):
            if not self._same_plan(document):
                self.message.setText('시험 적용을 확인했습니다. 이후 편집은 보존했습니다. 다시 읽어 확인하세요.');return
            self._bind(document['id'],receipt['document']);self.update_badge()
        self._submit_plan_command(document,'numerical.update',{'draft':draft},applied)

    def has_pending_plan_request(self):
        owner=self._adoption_owner
        return bool(self._pending_plan_command is not None or owner and
            (owner._adoption_receipt or owner._pending_adoption or owner._callbacks or owner._busy and not owner._busy_background))

    def _submit_plan_command(self, document, operation, arguments, applied):
        if self._pending_plan_command:return False
        self._request_rejection=None
        self._pending_plan_command=dict(document=deepcopy(document),operation=operation,
            arguments=deepcopy(arguments),command_id='C'+uuid.uuid4().hex)
        self._plan_command_applied=applied
        return self.retry_plan_command()

    def retry_plan_command(self):
        pending=deepcopy(self._pending_plan_command)
        if not pending and self._adoption_owner and self._adoption_owner._adoption_receipt:
            self._adoption_timer.start()
            return self._adoption_owner.retry_adoption_receipt()
        if not pending or self._busy:return False
        document=pending['document']
        from caelab.storage import canonical_hash
        from caelab.workbench_client import WorkbenchHTTPError
        digest=canonical_hash(dict(document_id=document['id'],operation=pending['operation'],
            arguments=pending['arguments'],session_id=document['session_id'],expected_generation=document['generation']))
        expected=dict(document_id=document['id'],command_id=pending['command_id'],request_hash=digest,outcome='REJECTED')
        def send():
            try:
                receipt=self.client.document_command(document['id'],pending['operation'],pending['arguments'],
                    session_id=document['session_id'],expected_generation=document['generation'],command_id=pending['command_id'])
                if (not isinstance(receipt,dict) or receipt.get('command_id')!=pending['command_id']
                        or receipt.get('document',{}).get('id')!=document['id']):
                    raise ValueError('The acknowledgement did not identify the original owner and request.')
                return receipt,None
            except WorkbenchHTTPError as error:
                if getattr(error,'command_rejection',None)!=expected:raise
                return None,error.service_message
        def confirmed(outcome):
            if self._pending_plan_command!=pending:return
            self._pending_plan_command=None;self.retry_command_button.hide()
            receipt,rejection=outcome
            if rejection is not None:
                self._request_rejection=rejection
                self.message.setText('요청이 접수 전에 거절됐습니다. 입력을 수정한 뒤 다시 실행하세요.')
                self.message.setToolTip(rejection)
                self.runtime_output.setPlainText('요청 거절\n'+rejection)
            else:self._plan_command_applied(receipt)
        def unknown(error):
            self.retry_command_button.show()
            self.message.setText('요청 결과를 확인하지 못했습니다. 원래 요청을 다시 확인하세요. 편집과 요청은 유지됩니다.')
        return self._call(send,confirmed,failed=unknown)

    def add_trial(self):
        document=self._editable_plan()
        if not document:return
        def listed(payload):
            rows=[row for row in payload['documents'] if row.get('kind')=='data' and row.get('runs')]
            if not rows:
                self.message.setText('시험 데이터 열기에서 파일과 열·단위를 확인하고 가져오기를 실행하세요.');return
            labels=[str(i+1)+': '+row['title'] for i,row in enumerate(rows)]
            label,ok=QInputDialog.getItem(self,'시험 추가','준비한 시험 자료',labels,0,False)
            if not ok:return
            data=rows[labels.index(label)];runs=data['runs']
            run_labels=['가져오기 '+str(i+1) for i in range(len(runs))]
            label,ok=QInputDialog.getItem(self,'시험 추가','사용할 가져오기',run_labels,len(runs)-1,False)
            if not ok:return
            run=runs[run_labels.index(label)]
            source=dict(document_id=data['id'],job_id=run['job_id'],
                input_revision=run['input_revision'],input_sha256=run['input_sha256'])
            self._call(lambda:self.client.document_result(data['id'],run['job_id']),
                lambda result:self._trial_dialog(document,source,result))
        self._call(self.client.documents,listed)

    def edit_trial(self):
        document=self._editable_plan();row=self.trials.currentRow()
        if not document or not 0<=row<len(document['draft'].get('experiments',[])):return
        experiment=deepcopy(document['draft']['experiments'][row])
        # The existing reader preserves processed-channel selection and its source hashes.
        from .numerical_window import NumericalWindow
        reader=NumericalWindow(self.client,auto_open=False,poll_interval=0)
        self.material._numerical_windows.append(reader)
        self._call(lambda:reader._read_trial_source(experiment)['result'],
            lambda result:self._trial_dialog(document,experiment['source'],result,row))

    def _trial_dialog(self, document, source, result, row=None):
        if not self._same_plan(document):
            self.message.setText('계획이나 선택이 바뀌어 시험 설정을 열지 않았습니다.');return
        if result.get('execution_status')!='SUCCEEDED':
            self.message.setText('성공한 가져오기 결과를 선택하세요. 원래 실패 결과는 유지됩니다.');return
        from .material_test_dialog import ExperimentDialog
        experiments=deepcopy(document['draft']['experiments'])
        old=experiments[row] if row is not None else None
        settings=old['settings'] if old else document['draft']['material']['draft']['settings']
        dialog=ExperimentDialog(settings,result,self,**({'experiment':old} if old else {}))
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        value=dialog.value
        if old and old.get('selection',{}).get('sample_policy') and value['name']!=old['source']['response']:
            self.message.setText('구간을 적용한 시험의 응답은 유지하세요. 다른 응답은 새 시험으로 추가하세요.');return
        if old is None:
            i=1
            while 'Test'+str(i) in {item['id'] for item in experiments}:i+=1
            trial=dict(id='Test'+str(i),source=deepcopy(source))
        else:trial=deepcopy(old)
        trial.update(role=value['role'],settings=value['settings'],response=value['response'],
            weight=value['weight'],scale=value['scale'])
        trial['source']['response']=value['name']
        from .finite_measure_gui import copy_trial_extensions
        copy_trial_extensions(trial,value)
        if value['kinematics'] is not None:trial['kinematics']=value['kinematics']
        else:trial.pop('kinematics',None)
        if old is None:experiments.append(trial)
        else:experiments[row]=trial
        self._replace_trials(document,experiments)

    def run_fit(self):
        document=self._editable_plan()
        if not document:return
        if document['draft'].get('mode')!='fit':
            self.message.setText('피팅 계획을 선택하세요. 다른 종류의 계산을 피팅으로 실행하지 않습니다.');return
        def started(receipt):
            if self._same_plan(document):self._bind(document['id'],receipt['document'])
            self.message.setText('피팅을 실행했습니다. 다시 읽기로 진행 상태와 보존된 결과를 확인하세요.')
            self.update_badge()
        self._submit_plan_command(document,'numerical.run',{},started)

    def evaluate_trial(self):
        from caelab.storage import canonical_hash
        document=deepcopy(self._documents.get(self.plans.currentData()));row=self.trials.currentRow()
        if self._busy or self.has_pending_plan_request() or self.material.local_dirty or self.material.conflict:
            self.message.setText('현재 재료 편집과 요청 결과를 먼저 확인하세요. 시작값 편집은 유지됩니다.');return False
        if not document or not 0<=row<len(document['draft'].get('experiments',[])):return False
        trial=document['draft']['experiments'][row]
        source=dict(document_id=document['id'],input_revision=document['input_revision'],
            input_sha256=canonical_hash(document['draft']),experiment_id=trial['id'])
        material=deepcopy(self.material.document)
        def started(receipt):
            current=self.material.document
            if not current or (current['id'],current['session_id'],current['generation'])!=(material['id'],material['session_id'],material['generation']):
                self.message.setText('평가 접수를 확인했습니다. 현재 재료가 바뀌어 원래 결과를 유지했습니다.');return
            draft=deepcopy(self.material.edited_draft())
            late=draft!=material['draft']
            self.material._active_result_view='material'
            job=receipt.get('job',{})
            self.material.output_stack.setCurrentIndex(0)
            self.material._show_document(receipt['document'],prefer_job=job.get('id',job.get('job_id')),
                edit_draft=draft if late else None,preserve_history=late)
            self.material.local_dirty=late
            self.message.setText('현재 계수로 선택 시험의 평가를 시작했습니다. 피팅 시작값과 현재 재료 입력은 바뀌지 않습니다.')
            QTimer.singleShot(0,self.material.refresh_results)
        return self._submit_plan_command(material,'material.evaluate',{'trial':source},started)

    def _show_final_parameters(self):
        from .material_window import PARAMETER_LABELS, display_value
        document=self._documents.get(self.plans.currentData())
        runs=document.get('runs',[]) if document else []
        result=self._trial_results.get((document['id'],runs[-1]['job_id']),{}) if runs else {}
        parameters=result.get('parameters') or {}
        current=(self.material.edited_draft().get('settings') or {}).get('parameters',{})
        self.final_parameters.setRowCount(len(parameters))

        for row,(name,value) in enumerate(parameters.items()):
            unit=result.get('parameter_units',{}).get(name,'미제공')
            for column,number in enumerate((PARAMETER_LABELS.get(name,name),current.get(name,'미제공'),value,unit)):
                shown=format(number,'.8g') if type(number) in (int,float) else display_value(number)
                item=QTableWidgetItem(shown);item.setToolTip(display_value(number));self.final_parameters.setItem(row,column,item)
        state=result.get('execution_status')
        states={'SUCCEEDED':'완료','FAILED':'실패','REJECTED':'거절','CANCELLED':'취소됨'}
        self.runtime_output.setPlainText('피팅 '+states.get(state,'결과 없음')+'\n'+
            ('선택 시험의 곡선은 최종 피팅 계수로 계산한 결과입니다.\n' if state=='SUCCEEDED' else '')+
            ('피팅에 쓰지 않은 별도 확인 시험은 계수 최적화에서 제외됩니다.\n' if any(e.get('role')=='holdout' for e in result.get('curves',[])) else '')+
            ('현재 재료 계수는 명시적으로 채택하기 전까지 유지됩니다.'))
        if self._request_rejection:
            self.runtime_output.setPlainText('요청 거절\n'+self._request_rejection)
        candidates=result.get('candidates',[]);self.fit_progress.setRowCount(len(candidates))
        for row,candidate in enumerate(candidates):
            for column,value in enumerate(('후보 '+str(row+1),states.get(candidate.get('execution_status'),'미확인'),
                    candidate.get('objective') if candidate.get('execution_status')=='SUCCEEDED' else '미제공')):
                self.fit_progress.setItem(row,column,QTableWidgetItem(str(value)))
        self.final_notice.setText('저장된 최종 피팅 계수 / 현재 재료에 자동 반영하지 않습니다.' if state=='SUCCEEDED'
            else '성공한 최종 피팅 결과가 없습니다. 부분 출력과 실패는 곡선 상태에서 확인하세요.')
        self.review_final_button.setEnabled(bool(parameters and state=='SUCCEEDED'))

    def review_final(self):
        document=self._editable_plan()
        if not document or not document.get('runs'):return
        job=document['runs'][-1]['job_id'];result=self._trial_results.get((document['id'],job),{})
        candidate=(result.get('final_candidate_detail') or {}).get('candidate_id')
        if not candidate:
            self.message.setText('최종 후보의 정확한 계산 근거가 없습니다. Numerical에서 보존 상태를 확인하세요.');return
        # Reuse the existing evidence/preview/CAS adoption path without showing
        # the full Numerical workspace or copying parameters into Material.
        from .numerical_window import NumericalWindow
        owner=NumericalWindow(self.client,auto_open=False,poll_interval=0)
        owner._material_adoption_helper=True
        self._adoption_owner=owner
        self.material._numerical_windows.append(owner)
        owner._show_document(deepcopy(document),prefer_job=job)
        owner._result_cache[job]=deepcopy(result);owner._draw_result()
        for row in range(owner.candidates.rowCount()):
            item=owner.candidates.item(row,0)
            if (item.data(Qt.ItemDataRole.UserRole) or item.text())==candidate:owner.candidates.selectRow(row);break
        original=owner._adopt_fit_detail
        def adopt(reference):
            if not self._same_plan(document) or self.material.local_dirty or self.material.conflict:
                self.message.setText('현재 재료나 계획이 바뀌었습니다. 편집을 적용하고 다시 검토하세요.');return False
            result=original(reference)
            self._adoption_timer.start()
            return result
        owner._adopt_fit_detail=adopt
        owner.open_candidate_detail()

    def _sync_adoption_request(self):
        owner=self._adoption_owner
        if not owner:self._adoption_timer.stop();return
        self.message.setText(owner.message.text())
        self.message.setToolTip(owner.message.toolTip())
        self.retry_command_button.setVisible(owner._adoption_receipt is not None)
        self.retry_command_button.setEnabled(owner.retry_adoption_button.isEnabled())
        if not self.has_pending_plan_request():
            self._adoption_timer.stop()
            self.material.refresh_document()

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
            self.material._update_actions()
            if getattr(self,'_refresh_plans_after',False) and not self._busy:
                self._refresh_plans_after=False
                QTimer.singleShot(0,self.refresh_plans)
        worker.signals.finished.connect(done, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def refresh_plans(self):
        if self._busy:
            self._refresh_plans_after=True
            return False
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

    def _coefficient_labels(self, document):
        labels=material_variable_labels(document)
        if not self.compact:return labels
        units={item['id']:item.get('unit','미제공') for item in document['draft'].get('variables',[])}
        return {key:label+' ['+str(units.get(key,'미제공'))+']' for key,label in labels.items()}

    @staticmethod
    def _parameter_summary(result):
        names={'E':'E','nu':'ν','mu':'μ','lmbda':'λ'}
        units=result.get('parameter_units',{})
        return ', '.join(names.get(key,key)+'='+
            (format(value,'.6g') if type(value) in (int,float) else str(value))+
            (' '+str(units.get(key,'미제공')) if units.get(key)!='1' else '')
            for key,value in (result.get('parameters') or {}).items())

    def _bind(self, identifier, document):
        self._binding = True
        try:
            self._widgets[identifier].bind_owner(self._adapters[identifier], document)
            self._widgets[identifier].set_variable_labels(self._coefficient_labels(document))
            if self.compact:self._widgets[identifier].owner_label.setText('계획 시작값과 탐색 범위')
            self._documents[identifier] = deepcopy(document)
        except ValueError as error:
            self.message.setText(str(error))
        finally:
            self._binding = False

    def _selected(self):
        identifier = self.plans.currentData()
        previous=getattr(self,'_shown_plan_id',None)
        self._shown_plan_id=identifier
        if identifier and previous is None:self.coefficient_mode.setCurrentIndex(1)
        self.open_button.setEnabled(bool(identifier)); self.save_button.setEnabled(bool(identifier))
        self.related_save_button.setEnabled(bool(identifier))
        self.save_receipt_button.setEnabled(identifier in self._related_save_receipts)
        if not identifier:
            self.stack.setCurrentWidget(self.empty)
            self.trials.setRowCount(0)
            self.coefficient_mode.setCurrentIndex(0)
            self.show_trial(force=True)
            self.badge.setText('이 재료의 피팅 계획이 없습니다.'); return
        if identifier not in self._widgets:
            from caelab.plan_variables_api import PlanOwnerAdapter, embed_plan_variables
            from .plan_variables_widget import NumericalPlanVariablesWidget
            adapter = self._adapters[identifier] = PlanOwnerAdapter(self.client, identifier)
            widget = embed_plan_variables(NumericalPlanVariablesWidget, parent=self.stack,
                                          adapter=adapter, document=self._documents[identifier])
            widget.set_variable_labels(self._coefficient_labels(self._documents[identifier]))
            if self.compact:
                widget.owner_label.setText('계획 시작값과 탐색 범위')
                header=widget.table.horizontalHeader()
                header.moveSection(header.visualIndex(1),5)
                widget.table.hideColumn(1);widget.table.hideColumn(6)
                header.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
                for column,width in ((2,60),(3,60),(4,60),(5,45)):
                    widget.table.setColumnWidth(column,width)
                widget.table.setHorizontalHeaderLabels(['계수','단위','값','하한','상한','피팅','변환'])

            widget.owner_label.setVisible(self.compact)  # Compact heading distinguishes Plan inputs from material coefficients.
            self._widgets[identifier] = widget; self.stack.addWidget(widget)
            widget.owner_history_allowed=lambda:not self.has_pending_plan_request()
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
        self.show_trial(force=True)

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
            self.material_context.clear()
            return
        reference = document['draft'].get('material', {})
        if self.compact:
            settings=reference.get('draft',{}).get('settings',{})
            index=self.material.model.findData(settings.get('model'))
            name=self.material.model.itemText(index) if index>=0 else str(settings.get('model','미지정'))
            text='계획의 재료: '+name+' ['+str(settings.get('stress_unit','미지정'))+']'
            self.material_context.setText(text)
            self.material_context.setToolTip(text+'\n현재 재료의 계수와 계획 시작값은 별도로 편집합니다.')
        selected=self.trials.currentRow()
        experiments = document['draft'].get('experiments',[])
        self.trials.blockSignals(True)
        self.trials.setRowCount(len(experiments))
        for row,trial in enumerate(experiments):
            source=trial['source']
            values=(self._source_titles.get(source.get('document_id'),'시험 '+str(row+1)),
                {'fit':'피팅','holdout':'별도 확인'}.get(trial['role'],trial['role']),source['response'],trial['response'])
            for column,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip(value+'\n'+str(source));self.trials.setItem(row,column,item)
        if experiments:self.trials.selectRow(max(0,min(selected,len(experiments)-1)))
        self.trials.blockSignals(False)
        if self.material._active_result_view=='plan':self.show_trial()
        self._show_final_parameters()
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
            curves=[curve for curve in result.get('curves',[]) if curve.get('experiment_id')==trial_id
                or curve.get('observation_source',{}).get('parent_experiment_id')==trial_id]
            if result.get('kind')!='fit' or not curves:
                self._clear_trial_plot('선택한 실행에 이 시험의 곡선이 없습니다. 실패 내용은 Numerical에서 확인하세요.')
                self._drawn_trial=key
                return
            self._drawn_trial=key
            from .numerical_window import plot_fit_trial, fit_trial_status
            axes=[curve.get('observations',{}).get('axes',[]) for curve in curves]
            if any(len(item)!=1 for item in axes):
                self._clear_trial_plot('선택 시험의 축을 곡선으로 표시할 수 없습니다. Numerical에서 원 결과를 확인하세요.')
                self._drawn_trial=key
                return
            figure=self.material.figure;figure.clear()
            self.material._active_result_view='plan'
            self.material.output_stack.setCurrentWidget(self.fit_output)
            blocked=self.material.response.blockSignals(True)
            self.material.response.setCurrentIndex(self.material.response.findData(frozen['response']))
            self.material.response.blockSignals(blocked);self.material.response.setEnabled(False)
            pair=None;signature=None
            for curve in curves:
                observation=curve.get('observations',{});axis=observation['axes'][0]
                candidate_signature=(axis.get('name'),axis.get('unit'),observation.get('unit'),observation.get('measure'),observation.get('component'))
                if signature is not None and signature!=candidate_signature:
                    self._clear_trial_plot('시험 그룹의 축·단위·물리량이 달라 같은 곡선으로 표시할 수 없습니다. 원 결과를 확인하세요.')
                    self._drawn_trial=key;return
                signature=candidate_signature
                role='별도 확인' if curve.get('role')=='holdout' else '피팅'
                pair=plot_fit_trial(figure,result,curve,show_residual=self.material.curve_view.currentData(),
                    axes_pair=pair,observation_label='관측 ('+role+')',prediction_label='최종 예측 ('+role+')')
            prediction_ax,residual_ax=pair
            name=self._source_titles.get(frozen['source'].get('document_id'),'시험 '+str(row+1))
            stale=run.get('draft')!=document['draft']
            state='\n'.join(fit_trial_status(result,curve,include_reason=False) for curve in curves)
            prediction_ax.set_title('')
            self.material.curve_context.setText(('최종 피팅 계수: '+self._parameter_summary(result) if result.get('execution_status')=='SUCCEEDED' else '보존한 피팅 출력')+' / '+
                ('별도 확인 시험' if frozen.get('role')=='holdout' else '피팅 시험')+
                (' / 이전 계획 입력' if stale else ''))
            self.material.curve_context.setToolTip(name+'\n'+document['title']+'\n'+state)
            self._show_final_parameters()
            self.message.setText(' / '.join(dict.fromkeys(fit_trial_status(result,curve) for curve in curves)))
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
        self.material.output_stack.setCurrentWidget(self.fit_output)
        self.material.canvas.draw_idle()

    def review_patch(self, identifier, preview):
        if self.has_pending_plan_request():
            self.message.setText('원래 요청 결과를 먼저 확인하세요. 시작값 편집은 보존했습니다.');return
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
        if self.has_pending_plan_request():
            self.message.setText('원래 요청 결과를 먼저 확인하세요.');return
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
        return self._busy or self.has_pending_plan_request() or bool(self._staged_observation) or bool(self._related_save_unconfirmed) or any(widget.has_unapplied_buffer() or (widget.document_snapshot() or {}).get('dirty')
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
