"""Dedicated law view on existing Material owner/editor, curve and Plan surfaces."""
from copy import deepcopy
import traceback
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QInputDialog,QLabel
from caelab.material_document import diagnostics
from plugins.material_point import law_native as law
from .simulation_window import SimulationWindow

LABELS={law.dp.MODEL:'압력 의존 DP', 'neo_hooke':'압축성 Neo-Hooke',
        'single_branch_maxwell':'단일 분기 Maxwell'}


def default_draft(_backend=law.POINT,model=law.dp.MODEL):
    return {'backend':law.POINT,'settings':law.default_settings(model)}


def support(draft):
    try:return {'declaration':law.declaration(draft['settings']), 'limitations':[
        '실측 재료·강도·파손·공학 승인은 미확인입니다.', 'FE 계산은 별도 명시 적용 후 FELUPE Hex8 시편 경로입니다.']}
    except (ValueError,KeyError,TypeError):return {'limitations':['미완성 입력은 저장할 수 있으나 계산은 차단합니다.']}


class LawNativeMaterialWindow(SimulationWindow):
    document_kind,tool_label='material','재료 법칙'
    model_backends=(law.POINT,)
    model_default,model_diagnostics,model_support=map(staticmethod,(default_draft,diagnostics,support))
    settings_sections=[(label,('settings',name)) for name,label in [
        ('model','법칙'),('parameters','계수와 단위'),('stress_unit','응력 단위'),('time_unit','시간 단위'),
        ('time','시간 이력'),('deformation_gradient','변형구배 이력'),('initial_state','수락된 초기 상태'),
        ('boundary_control','횡응력·구속 조건'),('tangent_probe','독립 접선 검사')]]

    def __init__(self,client,**kwargs):
        new=kwargs.get('auto_open',True) and not kwargs.get('document_id')
        if new:kwargs['auto_open']=False
        from .desktop import launch_tool,open_document_result
        kwargs.setdefault('runner_open',lambda job:launch_tool(client,'runner',job_id=job))
        kwargs.setdefault('result_open',lambda doc,job,**kw:open_document_result(client,doc,job,**kw))
        super().__init__(client,**kwargs)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self._law_windows=[]
        self.plan_action.setText('다시험 피팅 계획…')
        self.new_action.setText('새 재료 법칙…');self.open_action.setText('재료 열기…')
        menu=self.menuBar().addMenu('재료 법칙')
        for title,handler in [('새 법칙 문서…',self.new_document),('혼합 제어 조건…',self.configure_control),
                              ('혼합 제어 수렴과 수락 상태…',self.open_control_result),('독립 접선 결과…',self.open_constitutive),
                              ('저장 재료를 FE에 전달…',self.open_transfer)]:
            action=QAction(title,self);action.triggered.connect(handler);menu.addAction(action)
        index=self.backend.findData(law.POINT)
        if index>=0:
            self.backend.blockSignals(True);self.backend.setItemText(index,'재료 법칙 · 직접 평가');self.backend.blockSignals(False)
        if new:self.open_document(title=LABELS[law.dp.MODEL],draft=default_draft())

    def _call(self,function,accepted):
        # Retain the inherited scheduling/actions; localize only the error view.
        def requested():
            try:return function(),None
            except Exception as error:return None,error
        def finished(value):
            result,error=value
            if error is None:accepted(result)
            else:
                from .law_native_transfer_dialog import law_error_text
                cause='원 오류: '+str(error)+'\n'+''.join(traceback.format_exception(type(error),error,error.__traceback__))
                self.messages.setPlainText(cause+'\n'+self.messages.toPlainText())
                self.message.setText(law_error_text(error)+' 편집 내용은 보존합니다.')
        return super()._call(requested,finished)

    def field_label(self,path):
        names={'E':'탄성계수 E','nu':'포아송비 ν','alpha':'압력 계수 α','beta':'팽창 계수 β',
            'k0':'초기 항복 절편 k₀','H':'경화계수 H','K0':'평형 체적탄성계수 K₀','G0':'평형 전단계수 G₀',
            'K1':'branch 체적계수 K₁','G1':'branch 전단계수 G₁','tau':'이완 시간 τ [s]',
            'mu':'전단계수 μ','lmbda':'Lamé λ','time':'물리 시간 [s]','time_unit':'시간 단위',
            'stress_unit':'응력 단위','model':'법칙','deformation_gradient':'변형구배 F',
            'plastic_strain_kelvin':'소성 변형률 · Kelvin6','viscous_strain_kelvin':'점성 변형률 · Kelvin6',
            'strain_kelvin':'전체 변형률 · Kelvin6','kappa':'누적 등가 편차 소성변형률 κ',
            'stored_energy':'저장 에너지 밀도','dissipated_energy':'누적 소산 에너지 밀도',
            'work':'누적 일 밀도','steps':'섭동 크기 h','increment':'검사 증분 (0부터)',
            'stress_components':'지정할 물리 응력 성분','atol':'절대 응력 오차','rtol':'상대 응력 오차'}
        return names[path[-1]] if path[-1] in names else super().field_label(path)

    def _show_support(self,draft=None,checks=None,details=None):
        current=draft if draft is not None else self._draft
        super()._show_support(current,checks,support(current))
        model=current.get('settings',{}).get('model');unit=current.get('settings',{}).get('stress_unit','?')
        equations={law.dp.MODEL:'f = q − αp − (k₀ + Hκ), g = q − βp; p = −trσ/3',
            'neo_hooke':'ψ = μ(tr(FᵀF)/2 − ln J) + λ(ln J)²/2',
            'single_branch_maxwell':'σ = C₀ε + C₁(ε − εᵛ), ε̇ᵛ = (ε − εᵛ)/τ'}
        self.equation.setText(equations.get(model,'법칙을 선택하세요.'));self.equation.show()
        self.space.setText('P / F · 물리 9성분' if model=='neo_hooke' else '미소변형 Cauchy / Kelvin6 · 전단 ×√2')
        self.space.show();self.plan_button.setText('다시험 피팅 · 검증 계획')
        self.evaluate_button.setText('재료점 직접 평가')
        self.support.setText(f'계수·응력·에너지 밀도 단위: {unit} / 시간: s. '+
            '평가와 접선 검사는 FE 실행이나 공학 승인이 아닙니다. 압축·구속 holdout을 별도 지정하세요.')

    def _refresh_issue_summary(self):
        super()._refresh_issue_summary()
        from .law_native_transfer_dialog import law_error_text
        text=self.issue_summary.text()
        self.issue_summary.setTextFormat(Qt.TextFormat.PlainText)
        for row in getattr(self,'_input_checks',[]):
            original=str(row.get('message',''))
            if original:text=text.replace(original,law_error_text(original))
        self.issue_summary.setText(text)

    def _show_document(self,document,*,preserve_draft=None):
        first=self.document is None or self.document['id']!=document['id']
        super()._show_document(document,preserve_draft=preserve_draft)
        for path,item in self._nodes.items():
            if path and path[0]=='settings' and len(path)>2:
                item.setText(0,self.field_label(path))
        if first and ('settings','parameters') in self._nodes:
            self.tree.setCurrentItem(self._nodes[('settings','parameters')])

    def _add_fields(self,form,value,path):
        if path==('settings','model') and isinstance(value,str) and value in LABELS:
            form.addRow('법칙',QLabel(LABELS[value]));return
        super()._add_fields(form,value,path)
        if path[:2]==('settings','parameters') and path in self.fields:
            label=form.labelForField(self.fields[path][0])
            if label is not None:
                settings=self._draft['settings']
                unit=law.parameter_unit(settings['model'],path[-1],settings['stress_unit'])
                text=self.field_label(path);suffix=' ['+unit+']'
                label.setText(text if text.endswith(suffix) else text+suffix)

    def new_document(self):
        labels=list(LABELS.values())
        chosen,ok=QInputDialog.getItem(self,'새 재료 법칙','기존 문서는 보존하고 새 법칙을 엽니다.',labels,0,False)
        if ok:
            model=list(LABELS)[labels.index(chosen)]
            self._abandon(lambda:self.open_document(title=chosen,draft=default_draft(model=model)))

    def _draw_domain(self,path=None):
        ax=self.domain_axes;ax.clear();ax.set_aspect('auto')
        try:
            s=law.validate_settings(self.edited_draft()['settings']);F=np.asarray(s['deformation_gradient'])
            for i,j,label in [(0,0,'xx'),(1,1,'yy'),(2,2,'zz'),(0,1,'xy'),(0,2,'xz'),(1,2,'yz')]:
                ax.plot(s['time'],F[:,i,j]-(1 if i==j else 0),marker='o',label=label)
            ax.set_xlabel('시간 [s]');ax.set_ylabel('F − I [1]');ax.set_title('명시한 변형 이력 · 응력 제어는 별도 조건')
            ax.legend(ncol=3);self._model_graph_available=True
        except (ValueError,KeyError,TypeError):
            ax.text(.5,.5,'미완성 입력 · 원문을 보존하며 계산만 차단합니다.',ha='center');ax.set_axis_off()
            self._model_graph_available=False
        self.domain_canvas.draw_idle();self._update_actions()

    def configure_control(self):
        if not self.document or self._busy or self.conflict:return
        from .material_control_gui import MixedControlDialog
        document=deepcopy(self.document);draft=self.edited_draft()
        identity=lambda d:(d['id'],d['session_id'],d['generation'])
        polling=self.timer.isActive();self.timer.stop()
        try:
            dialog=MixedControlDialog(self.client,draft['settings'],self)
            if dialog.exec()!=dialog.DialogCode.Accepted:return
            if identity(self.document)!=identity(document):
                self.message.setText('열린 재료가 바뀌었습니다. 원 문서를 다시 열어 조건을 확인하세요.');return
            if dialog.result_settings!=draft['settings']:
                draft['settings']=deepcopy(dialog.result_settings)
                self._show_document(document,preserve_draft=draft);self.local_dirty=True
                self._update_actions()
            self.message.setText('혼합 제어 조건을 초안에 반영했습니다. 변경 적용 후 저장하거나 평가하세요.')
        finally:
            if polling:self.timer.start()

    def open_control_result(self):
        if not self.document or not self._selected_job or self._busy:return False
        from .material_control_gui import MixedControlResultDialog
        identity=(self.document['id'],self.document['session_id'],self._selected_job)
        def read():
            from caelab.storage import canonical_hash
            document=self.client.document_read(identity[0])
            run=next(r for r in document['runs'] if r['job_id']==identity[2])
            if canonical_hash(run['draft'])!=run['input_sha256']:
                raise ValueError('선택한 실행의 원 입력이 다릅니다.')
            return self.client.document_result(identity[0],identity[2]),deepcopy(run['draft']['settings'])
        def opened(value):
            if not self.document or (self.document['id'],self.document['session_id'],self._selected_job)!=identity:return
            window=MixedControlResultDialog(value[0],value[1],self)
            self._law_windows.append(window);window.show()
        return self._call(read,opened)

    def open_constitutive(self):
        jobs=[self._selected_job] if self._selected_job else []
        if not self.document or len(jobs)!=1:self.message.setText('보존할 계산 결과 하나를 선택하세요.');return
        from .constitutive_inspection_window import ConstitutiveInspectionWindow
        window=ConstitutiveInspectionWindow(self.client,self.document['id'],jobs[0],self)
        self._law_windows.append(window);window.show()

    def open_numerical_plan(self):
        if not self.document or self._busy or self.conflict:return False
        if self.local_dirty or self.document.get('diagnostics'):
            self.message.setText('재료 입력을 수정하고 변경 적용한 뒤 피팅 계획을 여세요.');return False
        from .numerical_window import NumericalWindow
        window=NumericalWindow(self.client,material_document=deepcopy(self.document))
        self._law_windows.append(window);window.show();window.raise_()
        return window

    def open_transfer(self):
        if not self.document or self.local_dirty or self.conflict or self.document.get('dirty') or not self.document.get('saved_revision'):
            self.message.setText('재료의 변경을 적용하고 저장한 뒤 전달하세요. 미저장 편집은 자동 채택하지 않습니다.');return
        from .law_native_transfer_dialog import LawNativeTransferDialog
        window=LawNativeTransferDialog(self.client,deepcopy(self.document),self)
        self._law_windows.append(window);window.show()
