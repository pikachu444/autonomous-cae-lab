"""Material owner view for the existing MFront law/protocol declarations.

Uses the same typed document editor and stored response reader as Simulation.
FELUPE's direct table editor is retained separately; there is no new numerical
law, FE-card emulation, independent owner or automatic backend fallback here.
"""
from copy import deepcopy

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QInputDialog,QDialog,QVBoxLayout,QHBoxLayout,QPlainTextEdit,
    QFileDialog,QDialogButtonBox,QLabel,QLineEdit,QPushButton,QComboBox,QMessageBox)
from PySide6.QtGui import QAction

from caelab.material_document import NATIVE_LAWS, diagnostics
from caelab.simulation_document import default_draft, support_details
from .simulation_window import SimulationWindow


class NativeMaterialWindow(SimulationWindow):
    document_kind, tool_label = 'material', '재료'
    model_backends = NATIVE_LAWS
    settings_sections=SimulationWindow.settings_sections+[(label,('settings',key)) for key,label in (
        ('source','법칙 원문'),('behaviour','법칙 이름'),('action','작업'),('interface','인터페이스'),
        ('hypothesis','공간 가정'),('properties','물성'),('external','외부 상태'),('initial_internal','초기 내부 상태'),
        ('probe','독립 섭동'),('stress_unit','응력 단위'),('strain_unit','변형률 단위'),('time_unit','시간 단위'))]
    model_default, model_diagnostics, model_support = map(staticmethod, (default_draft, diagnostics, support_details))

    def __init__(self, client, **kwargs):
        new_native = kwargs.get('auto_open', True) and not kwargs.get('document_id')
        if new_native:
            kwargs['auto_open'] = False
        from .desktop import launch_tool, open_document_result, open_domain_plan
        kwargs.setdefault('runner_open', lambda job: launch_tool(client, 'runner', job_id=job))
        kwargs.setdefault('result_open', lambda doc, job, **kw: open_document_result(client, doc, job, **kw))
        kwargs.setdefault('plan_open', lambda doc, **kw: open_domain_plan(client, doc, **kw))
        super().__init__(client, **kwargs)
        self.new_action.setText('새 구성식…')
        self.open_action.setText('재료 열기…')
        self.plan_button.setText('수치 계산 계획')
        self._other_material_windows = []
        for index,key in enumerate(self.model_backends):
            label={'material.mfront':'탄성 재료점','material.mfront.hyperelastic':'유한변형 SVK',
                   'material.mfront.viscoelastic':'Maxwell 점탄성','material.mfront.user':'사용자 MFront 법칙'}.get(key,key)
            found=self.backend.findData(key)
            if found>=0:self.backend.setItemText(found,label)
        self.constitutive_action=QAction('구성식 증분…',self)
        self.constitutive_action.triggered.connect(self.open_constitutive)
        law_menu=self.menuBar().addMenu('구성식');law_menu.addAction(self.constitutive_action)
        self.source_action=QAction('법칙 원문…',self)
        self.source_action.triggered.connect(self.edit_law_source);law_menu.addAction(self.source_action)
        self.build_inputs_action=QAction('빌드 선언으로 입력 준비…',self)
        self.build_inputs_action.triggered.connect(self.prepare_law_inputs);law_menu.addAction(self.build_inputs_action)
        if new_native:
            self.open_document(draft=self.model_default(NATIVE_LAWS[0]))

    def _show_support(self, draft=None, checks=None, details=None):
        if details is None and self.document:
            details = self.document.get('material_support', {})
        super()._show_support(draft, checks, details)
        self.support.setText('재료점의 응력·접선·적분 상태. FE 연결 및 공학 승인과는 별개입니다.')
        self.plan_button.setText('수치 계산 계획')
        current=draft if draft is not None else self._draft
        if current.get('backend')=='material.mfront.user':
            self.equation.setText('사용자 미소변형 법칙 / generic');self.equation.show()
            self.space.setText('물리 텐서 변형률 → Kelvin 적분 / Pa, 1, s');self.space.show()
            self.evaluate_button.setText('빌드만 실행' if current.get('settings',{}).get('action')=='build' else '빌드하고 평가')
            self.support.setText('원문별 로컬 빌드 허용 필요. FE 내보내기는 아직 지원하지 않습니다.')
        else:
            self.evaluate_button.setText('모델 평가')

    @staticmethod
    def field_label(path):
        labels={'source':'법칙 원문','behaviour':'법칙 이름','action':'작업','interface':'인터페이스',
                'hypothesis':'공간 가정','stress_unit':'응력 단위','strain_unit':'변형률 단위','time_unit':'시간 단위',
                'properties':'물성','external':'외부 상태','initial_internal':'초기 내부 상태',
                'history':'변형 이력','probe':'독립 섭동','time':'시간 [s]','strain':'변형률 xx yy zz xy xz yz',
                'value':'값','unit':'단위','name':'이름','increment':'증분','component':'성분','steps':'섭동 크기'}
        labels.update({'case':'시험 종류','temperature_k':'온도 [K]','dt_s':'증분 시간 [s]',
                       'young_modulus_mpa':'탄성계수 [MPa]','fd_steps':'섭동 크기',
                       'relaxation_time_s':'이완 시간 [s]','strain_kelvin':'Kelvin 변형률'})
        key=path[-1]
        if isinstance(key,int):
            parent=next((x for x in reversed(path[:-1]) if isinstance(x,str)),'')
            return labels.get(parent,SimulationWindow.field_label(path[:-1]))+' '+str(key+1)
        return labels.get(key,SimulationWindow.field_label(path))

    def _add_fields(self,form,value,path):
        if path==('settings','source') and self._draft.get('backend')=='material.mfront.user':
            from caelab.user_material import source_hash
            button=QPushButton('법칙 원문 편집…');button.clicked.connect(self.edit_law_source);form.addRow(button)
            label=QLabel(str(len(value.encode('utf-8')))+' bytes / UTF-8' if isinstance(value,str) else '원문 형식 확인')
            if isinstance(value,str):label.setToolTip('현재 원문 버전 확인값: '+source_hash(value))
            form.addRow(label);return
        if path==('settings','action') and self._draft.get('backend')=='material.mfront.user':
            combo=QComboBox();combo.addItem('빌드만','build');combo.addItem('빌드하고 평가','evaluate')
            if combo.findData(value)<0:combo.addItem(str(value),value)
            combo.setCurrentIndex(combo.findData(value))
            def changed():
                self._draft['settings']['action']=combo.currentData();self.local_dirty=True
                self._show_support(draft=self._draft,checks=self.model_diagnostics(self._draft));self._update_actions()
            combo.currentIndexChanged.connect(changed);form.addRow(combo);return
        return super()._add_fields(form,value,path)

    def evaluate(self):
        if not self.document or self._busy or self.conflict or self.local_dirty:return False
        draft=deepcopy(self.edited_draft())
        if draft.get('backend')!='material.mfront.user':return super().evaluate()
        if self.model_diagnostics(draft):return False
        owner=(self.document['id'],self.document['session_id'],self.document['generation'])
        def unchanged():
            return (self.document is not None and owner==(self.document['id'],self.document['session_id'],
                self.document['generation']) and self.edited_draft()==draft and not self.conflict and not self.local_dirty)
        def review(context):
            if not unchanged():return
            from .material_build_dialog import MaterialBuildDialog
            timer=getattr(self,'timer',None);active=bool(timer and timer.isActive())
            if timer:timer.stop()
            try:
                dialog=MaterialBuildDialog(self.client,context,draft['settings'],self)
                accepted=dialog.exec()==QDialog.DialogCode.Accepted and dialog.approved
                if accepted and unchanged():
                    self.command('material.evaluate')
                elif accepted:
                    self.message.setText('원문 빌드는 허용했습니다. 편집 내용이 바뀌어 계산하지 않았습니다.')
            finally:
                if active:timer.start()
        return self._call(lambda:self.client.request('/api/workbench/material-build-context'),review)

    def _draw_domain(self,path=None):
        settings=self.edited_draft().get('settings',{})
        history=settings.get('history') if isinstance(settings,dict) else None
        if self._draft.get('backend')!='material.mfront.user' or not isinstance(history,list):
            return super()._draw_domain(path)
        import math
        valid=all(isinstance(row,dict) and type(row.get('time')) in (int,float)
            and math.isfinite(row['time']) and isinstance(row.get('strain'),list) and len(row['strain'])==6
            and all(type(x) in (int,float) and math.isfinite(x) for x in row['strain']) for row in history)
        axes=self.domain_axes;axes.clear();axes.set_aspect('auto')
        self._model_graph_available=bool(valid and len(history)>1)
        if self._model_graph_available:
            for index,label in enumerate(('xx','yy','zz','xy','xz','yz')):
                axes.plot([r['time'] for r in history],[r['strain'][index] for r in history],marker='o',label=label)
            axes.set_xlabel('시간 [s]');axes.set_ylabel('물리 텐서 변형률 [1]')
            axes.set_title('지정한 변형 이력');axes.legend(ncol=3)
        else:axes.set_axis_off()
        self.domain_canvas.draw_idle();self._update_actions()

    def edit_law_source(self):
        if not self.document or self._busy:return
        draft=deepcopy(self.edited_draft())
        opened_document=deepcopy(self.document)
        if draft.get('backend')!='material.mfront.user':
            self.message.setText('새 구성식에서 사용자 MFront 법칙을 선택하세요.');return
        dialog=QDialog(self);dialog.setWindowTitle('법칙 원문');dialog.resize(850,650)
        layout=QVBoxLayout(dialog);name=QLineEdit(str(draft['settings'].get('behaviour','')))
        layout.addWidget(QLabel('MFront behaviour 이름'));layout.addWidget(name)
        source=QPlainTextEdit(str(draft['settings'].get('source','')));layout.addWidget(source,1)
        note=QLabel('원문 저장은 빌드하지 않습니다. 빌드는 로컬 운영자가 허용한 원문만 실행합니다.');layout.addWidget(note)
        load=QPushButton('파일 열기…');layout.addWidget(load)
        def choose():
            path,_=QFileDialog.getOpenFileName(dialog,'법칙 원문',filter='MFront (*.mfront);;UTF-8 text (*.txt)')
            if not path:return
            try:
                from pathlib import Path
                data=Path(path).read_bytes()
                if len(data)>48*1024:raise ValueError('원문은 최대 48 KiB입니다.')
                source.setPlainText(data.decode('utf-8'))
            except (OSError,UnicodeError,ValueError) as error:QMessageBox.warning(dialog,'원문 읽기',str(error))
        load.clicked.connect(choose)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        # Keep the captured generation until its edit is resolved. Modal Qt
        # loops still deliver queued HTTP replies, so pausing the timer alone
        # is not the conflict guard.
        timer=getattr(self,'timer',None);active=bool(timer and timer.isActive())
        if timer:timer.stop()
        try:
            if dialog.exec()!=QDialog.DialogCode.Accepted:return
            current=deepcopy(self.edited_draft())
            old_settings=draft['settings'];current_settings=current.get('settings',{})
            same_owner=self.document and (self.document['id'],self.document['session_id'])==(
                opened_document['id'],opened_document['session_id'])
            safe_merge=(same_owner and current.get('backend')=='material.mfront.user'
                and all(current_settings.get(k)==old_settings.get(k) for k in ('source','behaviour')))
            if safe_merge:
                current['settings']['source']=source.toPlainText();current['settings']['behaviour']=name.text()
                self.local_dirty=True;self._show_document(self.document,preserve_draft=current)
            else:
                # Retain this modal edit against its ORIGINAL generation.
                # Existing reload/copy conflict operations decide what to keep.
                draft['settings']['source']=source.toPlainText();draft['settings']['behaviour']=name.text()
                self.local_dirty=True;self.conflict=True
                self._show_document(opened_document,preserve_draft=draft)
                self.message.setText('같은 원문이 다른 곳에서 바뀌었습니다. 편집본을 보관한 뒤 저장 버전과 비교하세요.')
                self._update_actions()
        finally:
            if active:timer.start()

    def prepare_law_inputs(self):
        if not self.document or self._busy or not self._selected_job:
            self.message.setText('완료된 빌드 결과를 선택하세요.');return
        draft=deepcopy(self.edited_draft());opened=deepcopy(self.document);job=self._selected_job
        if draft.get('backend')!='material.mfront.user':
            self.message.setText('사용자 MFront 법칙에서 빌드 결과를 선택하세요.');return
        def reviewed(view):
            if (not self.document or (self.document['id'],self.document['session_id'])!=(opened['id'],opened['session_id'])
                    or self._selected_job!=job or self.edited_draft()!=draft):return
            from .material_law_inputs_dialog import MaterialLawInputsDialog
            try:dialog=MaterialLawInputsDialog(draft['settings'],view.get('build'),self)
            except ValueError as error:self.message.setText(str(error));return
            timer=getattr(self,'timer',None);active=bool(timer and timer.isActive())
            if timer:timer.stop()
            try:
                if dialog.exec()!=QDialog.DialogCode.Accepted:return
                prepared=dialog.edited_settings();current=deepcopy(self.edited_draft())
                keys=('source','behaviour','properties','external','initial_internal','action')
                same=self.document and (self.document['id'],self.document['session_id'])==(opened['id'],opened['session_id'])
                same=bool(same and current.get('backend')==draft['backend'] and all(
                    current.get('settings',{}).get(k)==draft['settings'].get(k) for k in keys))
                target=current if same else deepcopy(draft)
                for key in ('properties','external','initial_internal','action'):target['settings'][key]=prepared[key]
                self.local_dirty=True
                if not same:self.conflict=True
                self._show_document(self.document if same else opened,preserve_draft=target)
                self.message.setText('입력 초안에 반영했습니다. 값·단위와 변형 이력을 확인한 뒤 적용하고 평가하세요.'
                    if same else '다른 편집과 겹쳐 초안을 보관했습니다. 저장 버전과 비교하세요.')
                self._update_actions()
            finally:
                if active:timer.start()
        return self._call(lambda:self.client.constitutive_inspect(opened['id'],job,0),reviewed)

    def open_constitutive(self):
        if not self.document or not self._selected_job:
            self.message.setText('계산 결과를 선택하세요.');return
        from .constitutive_inspection_window import ConstitutiveInspectionWindow
        window=ConstitutiveInspectionWindow(self.client,self.document['id'],self._selected_job,self)
        self._other_material_windows.append(window);window.show()

    def _opened(self, document):
        # The shared Material file picker may return the other supported editor
        # family. Preserve the actual same M owner and open its existing editor.
        if document['draft'].get('backend') == 'material.felupe':
            from .material_window import MaterialWindow
            window = MaterialWindow(self.client, auto_open=False)
            self._other_material_windows.append(window)
            window._opened(document); window.show()
            return
        super()._opened(document)

    def new_document(self):
        labels=['탄성 (MFront)','유한변형 SVK','시간 의존 Maxwell','사용자 MFront 법칙']
        choice, accepted = QInputDialog.getItem(self, '새 구성식', '구성식', labels, 0, False)
        backend=NATIVE_LAWS[labels.index(choice)] if accepted else None
        if accepted:
            self._abandon(lambda: self.open_document(draft=self.model_default(backend)))
