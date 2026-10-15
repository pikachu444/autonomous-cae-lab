"""Read-only derivative/iteration evidence in existing Numerical result windows."""
from PySide6.QtWidgets import QLabel,QSplitter,QTabWidget,QVBoxLayout,QWidget,QTableWidgetItem
from PySide6.QtCore import Qt
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .runner_window import readonly_table
from .numerical_methods import display_number
from .shared_binding_dialog import LABELS
from .appearance import configure_plot_fonts


class GradientEvidence(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        configure_plot_fonts()
        layout=QVBoxLayout(self)
        self.summary=QLabel('선형 adjoint 결과 또는 독립 미분 검사를 선택하세요. 이 화면은 계산하지 않습니다.')
        self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.gradients=readonly_table(['후보','응답','설계 변수','실제 미분값','단위','사용 상태'])
        self.gradients.setObjectName('actualAdjointGradients');self.tabs.addTab(self.gradients,'미분값')
        self.inputs=readonly_table(['변수','공유 값','단위','분야 입력','실제 적용값'])
        self.inputs.setObjectName('sharedAppliedInputs');self.tabs.addTab(self.inputs,'적용 입력')
        checks=QWidget();box=QVBoxLayout(checks)
        self.checks=readonly_table(['방향','h','R0','R1','R0 차수','R1 차수'])
        self.checks.setObjectName('actualTaylorRemainders');self.checks.setMaximumHeight(180)
        self.figure=Figure(constrained_layout=True);self.canvas=FigureCanvasQTAgg(self.figure)
        self.axes=self.figure.add_subplot(111)
        split=QSplitter(Qt.Orientation.Vertical);split.addWidget(self.canvas);split.addWidget(self.checks)
        split.setStretchFactor(0,3);split.setStretchFactor(1,1);box.addWidget(split)
        self.tabs.addTab(checks,'독립 Taylor 검사')
        self.residuals=readonly_table(['후보','원문제 잔차','수반 잔차','자유도 수','전치계 풀이 수','차분 대체 호출 수'])
        self.residuals.setObjectName('adjointResiduals');self.tabs.addTab(self.residuals,'계산 잔차')
        self.chains=readonly_table(['목적과 제약','설계 변수','물리 미분','변수 좌표 미분','정규화 미분값','단위'])
        self.chains.setObjectName('adjointChainRule');self.tabs.addTab(self.chains,'목적과 제약 미분')

    @staticmethod
    def rows(table,rows):
        table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):
                item=QTableWidgetItem(display_number(value));item.setToolTip(str(value));table.setItem(i,j,item)
        table.resizeColumnsToContents()

    def set_result(self,result,*,eligible=True,parent=None):
        context=parent if parent is not None else result
        verification=context.get('gradient_verification')
        checked=verification is not None
        verification=verification if isinstance(verification,dict) else {}
        state=verification.get('status')
        parent_status=context.get('parent_execution_status',context.get('execution_status'))
        candidates=result.get('candidates')
        candidates=candidates if isinstance(candidates,list) else [result]
        gs=[];bound=[];residuals=[];chains=[];admitted=[];purposes=[]
        for i,row in enumerate(candidates):
            label='후보 '+str(i+1) if len(candidates)>1 else '선택 결과'
            purpose=context.get('candidate_purpose',row.get('purpose'))
            admission=context.get('candidate_gradient_admission',row.get('gradient_admission'))
            candidate_status=context.get('candidate_execution_status',row.get('execution_status'))
            valid=(eligible and parent_status in (None,'SUCCEEDED') and context.get('execution_status') in (None,'SUCCEEDED')
                and row.get('execution_status')=='SUCCEEDED' and candidate_status in (None,'SUCCEEDED')
                and (not checked or state=='PASS') and admission is None and purpose in (None,'optimization'))
            admitted.append(valid);purposes.append(purpose)
            usage='최적화 사용 가능' if valid else '독립 검사 전용' if purpose=='gradient_verification' else '최적화 사용 불가'
            for response,gradient in (row.get('gradients') or {}).items():
                for name,g in gradient.items():
                    gs.append((label,{'mean_temperature':'평균 온도'}.get(response,response),LABELS.get(name,name),g.get('value'),g.get('unit'),usage))
            for name,g in (row.get('derivatives') or {}).items():
                response=g.get('response')
                gs.append((label,{'mean_temperature':'평균 온도'}.get(response,response),LABELS.get(name,name),g.get('value'),g.get('unit'),usage))
            definitions=[('목적',row.get('objective_gradient') or {})]+[
                ('제약 '+str(i+1)+' '+c['operator']+' '+str(c['limit'])+' '+c['response_unit'],c)
                for i,c in enumerate(row.get('constraint_gradients') or [])]
            for title,definition in definitions:
                for c in definition.get('components',[]):
                    chains.append((title,c['id'],c['physical'],c['dx_dz'],c['value'],definition['unit']))
            for b in row.get('input_bindings',[]):
                for t in b.get('targets',[]):
                    bound.append((b.get('label',b['id']),b.get('value'),b.get('unit'),row.get('stage_names',{}).get(t['stage'],'분야 입력')+' / '+LABELS.get(t['input_id'],t['input_id']),t.get('applied_value')))
            receipt=row.get('gradient_provenance',{}).get('adjoint_receipt') or row.get('diagnostics',{}).get('adjoint')
            if receipt:
                residuals.append((label,receipt.get('primal_relative_residual'),receipt.get('adjoint_relative_residual'),
                    receipt.get('free_dofs'),receipt.get('adjoint_solve_calls'),receipt.get('finite_difference_calls')))
        self.rows(self.gradients,gs);self.rows(self.inputs,bound);self.rows(self.residuals,residuals);self.rows(self.chains,chains)
        directions=verification.get('directions',[])
        self.axes.clear();table=[]
        for i,row in enumerate(directions):
            samples=row.get('taylor',[])
            if not isinstance(samples,list):continue
            for sample in samples:table.append((i+1,sample.get('h'),sample.get('R0'),sample.get('R1'),sample.get('R0_order'),sample.get('R1_order')))
            for key in ('R0','R1'):
                valid_samples=[s for s in samples if type(s.get(key)) in (int,float) and s[key]>0]
                if valid_samples:self.axes.loglog([s['h'] for s in valid_samples],[s[key] for s in valid_samples],marker='o',label='p'+str(i+1)+' '+key)
        self.rows(self.checks,table)
        self.axes.set_xlabel('정규화 설계 좌표 변화량 h');self.axes.set_ylabel('목적함수 나머지 절댓값')
        if directions:self.axes.legend()
        self.canvas.draw_idle()
        if gs:
            states={'FAILED':'실패','CANCELLED':'취소','REJECTED':'실행 거절','PARTIAL_FAILURE':'일부 실패',
                'RUNNING':'실행 중','QUEUED':'대기 중','CANCEL_REQUESTED':'취소 요청'}
            self.summary.setText('보존된 이산 수반법(adjoint) 미분값입니다. 단위와 잔차를 함께 확인하세요. '+
                ('독립 검사: '+{'PASS':'통과','FAIL':'실패','INCOMPLETE':'미완료','RUNNING':'진행 중','CANCELLED':'취소'}.get(state,'미확인') if checked else '독립 검사 없음')+
                (' / 원 최적화 실행: '+states.get(parent_status,'미완료') if parent_status not in (None,'SUCCEEDED') else '')+
                (' / 원 후보 실행: '+states.get(context['candidate_execution_status'],'미완료') if context.get('candidate_execution_status') not in (None,'SUCCEEDED') else '')+
                (' / 독립 검사에 사용한 자료이며 최적화 후보가 아닙니다.' if 'gradient_verification' in purposes else '')+
                (' / 표시한 원값은 최적화에 사용할 수 없습니다.' if not any(admitted) else
                 ' / 사용 불가로 표시한 행은 최적화에 사용할 수 없습니다.' if not all(admitted) else ''))
        elif result:
            self.summary.setText('이 결과에 사용 가능한 adjoint가 없습니다. 비선형 Picard·DE 결과를 전체 연성 미분으로 표시하지 않습니다.')
        else:self.summary.setText('결과를 읽으면 실제 미분값·공유 입력·독립 검사·잔차를 표시합니다. 계산은 시작하지 않습니다.')
