"""Read-only derivative/iteration evidence in existing Numerical result windows."""
from PySide6.QtWidgets import QLabel,QSplitter,QTabWidget,QVBoxLayout,QWidget,QTableWidgetItem
from PySide6.QtCore import Qt
from matplotlib.figure import Figure
from matplotlib.ticker import LogFormatter
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from .runner_window import readonly_table
from .numerical_methods import display_number
from .shared_binding_dialog import LABELS
from .appearance import configure_plot_fonts


class _TaylorLogFormatter(LogFormatter):
    """Plain engineering exponents, without mathtext or a font-dependent minus."""
    @staticmethod
    def fix_minus(text):
        return text.replace('\N{MINUS SIGN}', '-')


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
        self.verification_summary=QLabel();self.verification_summary.setWordWrap(True);box.addWidget(self.verification_summary)
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
        fd=QWidget();fd_box=QVBoxLayout(fd)
        self.fd_summary=QLabel('보존된 원 잔차 FD 진단이 없습니다.');self.fd_summary.setWordWrap(True);fd_box.addWidget(self.fd_summary)
        self.fd_stencils=readonly_table(['계수','차분법','활성 경계','h','h/2','차분 차이','원 허용값','방향 일관성'])
        self.fd_stencils.setObjectName('ordinaryResidualFD');fd_box.addWidget(self.fd_stencils)
        self.tabs.addTab(fd,'원 잔차 FD')
        from .derivative_support_widgets import DerivativeSupport
        self.support=DerivativeSupport(self);self.tabs.addTab(self.support,'방법과 지원 범위')

    @staticmethod
    def rows(table,rows):
        table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):
                item=QTableWidgetItem(display_number(value));item.setToolTip(str(value));table.setItem(i,j,item)
        table.resizeColumnsToContents()

    def set_result(self,result,*,eligible=True,parent=None,submitted=None):
        from caelab import linear_adjoint_contract
        from .numerical_methods import CHOICE_LABELS
        describe_methods=getattr(linear_adjoint_contract,'describe_methods',None)
        describe_result=getattr(linear_adjoint_contract,'describe_result_method',None)
        declared=describe_result(result) if callable(describe_result) else None
        source_method=(submitted or {}).get('method')
        timing=result.get('timing') or {}
        method_note=('보존 결과의 방법: '+str(declared['label'])+'. ' if declared else '원 결과의 미분법 선언은 미제공 상태입니다. ')
        if source_method:method_note+='원 제출 방법: '+str(CHOICE_LABELS.get(source_method,source_method))+'. '
        if result:
            method_note+='실제 평가 '+display_number(timing.get('dispatched_evaluations_total',timing.get('model_calls')))+'회 / 명시 예산 '+display_number(timing.get('max_evaluations'))+'회. '
        self.support.set_descriptor({'derivative_methods':describe_methods() if callable(describe_methods) else []},message=method_note+
            '아래 표는 방법별 선언 범위입니다. 현재 입력의 지원 여부는 계획의 미분법 지원 확인에서 별도로 읽습니다.')
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
        limits=verification.get('thresholds') or {}
        lines=[]
        if directions:
            lines.append('독립 방향 '+str(len(directions))+'개 / 검사 평가 '+display_number(verification.get('verification_model_calls'))+'회. '+
                '원 차수 R0 '+display_number(limits.get('first_order'))+', R1 '+display_number(limits.get('taylor_order'))+'.')
            for i,direction in enumerate(directions):
                lines.append('방향 '+str(i+1)+' 차이 '+display_number(direction.get('absolute_mismatch'))+
                    ' / 원 허용값 '+display_number(direction.get('tolerance'))+' '+
                    {'PASS':'통과','FAIL':'실패','INCOMPLETE':'미완료'}.get(direction.get('status'),'미확인'))
        self.verification_summary.setText('  '.join(lines))
        self.verification_summary.setToolTip(str(limits))
        self.axes.clear();table=[]
        for i,row in enumerate(directions):
            samples=row.get('taylor',[])
            if not isinstance(samples,list):continue
            for sample in samples:table.append((i+1,sample.get('h'),sample.get('R0'),sample.get('R1'),sample.get('R0_order'),sample.get('R1_order')))
            for key in ('R0','R1'):
                valid_samples=[s for s in samples if type(s.get(key)) in (int,float) and s[key]>0]
                if valid_samples:self.axes.loglog([s['h'] for s in valid_samples],[s[key] for s in valid_samples],marker='o',label='p'+str(i+1)+' '+key)
        self.rows(self.checks,table)
        if self.axes.get_xscale()=='log':
            for axis in (self.axes.xaxis,self.axes.yaxis):
                axis.set_major_formatter(_TaylorLogFormatter())
                axis.set_minor_formatter(_TaylorLogFormatter())
        self.axes.set_xlabel('정규화 설계 좌표 변화량 h');self.axes.set_ylabel('목적함수 나머지 절댓값')
        if directions:self.axes.legend()
        self.canvas.draw_idle()
        analysis=result.get('experiment_analysis') or {}
        ordinary=analysis.get('ordinary_jacobian') or {}
        plan=analysis.get('evaluation_plan') or ordinary.get('evaluation_plan') or {}
        halving=ordinary.get('step_halving') or {}
        directional={row.get('parameter'):row for row in (ordinary.get('directional_consistency') or {}).get('parameters',[])}
        differences=halving.get('column_max_difference',[]);limits=halving.get('limits',[])
        fd_rows=[]
        for i,stencil in enumerate(plan.get('stencils',[])):
            h=stencil.get('encoded_step');name=stencil.get('parameter')
            fd_rows.append((name,{'central_quadratic':'중앙 2차','one_sided_quadratic':'한쪽 2차'}.get(stencil.get('difference'),stencil.get('difference')),
                {-1:'하한',0:'내부',1:'상한'}.get(stencil.get('active_bound'),'미제공'),h,h/2 if type(h) in (int,float) else None,
                differences[i] if isinstance(differences,list) and i<len(differences) else None,
                limits[i] if isinstance(limits,list) and i<len(limits) else None,
                {'CONSISTENT':'일관됨','INCONSISTENT':'불일치','ONE_SIDED_BOUND_SCOPE':'경계 한쪽 범위'}.get(directional.get(name,{}).get('status'),'미제공')))
        self.rows(self.fd_stencils,fd_rows)
        if analysis:
            timing=result.get('timing') or {}
            self.fd_summary.setText('ordinary-residual FD 최종점 진단. optimizer Jacobian이나 adjoint로 대체하지 않습니다. '+
                '실제 평가 '+display_number(timing.get('model_calls'))+'회 / 사용 예산 '+display_number(timing.get('budget_used'))+
                '회 / 원 계획 '+display_number(plan.get('model_evaluations'))+'회. '+
                'h/h2 일관성: '+{True:'통과',False:'실패'}.get(halving.get('stable'),'미제공')+
                '. 별도 확인 시험 평가 '+display_number(analysis.get('holdout_evaluations'))+'회. 공학 적합성은 미확인입니다.')
        else:self.fd_summary.setText('보존된 원 잔차 FD 진단이 없습니다.')
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
        elif result.get('kind')=='experiment_identification':
            heading=('보존된 ordinary-residual FD 진단입니다. ' if ordinary.get('kind')=='ordinary_residual_jacobian' else
                '최종점 진단 요청 결과입니다. 원 잔차 FD 미분값은 미제공 상태입니다. ')
            self.summary.setText(heading+'원 잔차 FD 탭에서 h/h2·활성 경계·원 허용값을 확인하세요. '+
                '선형 adjoint나 최적화 실행 결과로 표시하지 않습니다. '+
                ('원 진단 실패: '+str(result.get('failure_reason') or result.get('identification',{}).get('reason','미제공'))
                 if result.get('execution_status')!='SUCCEEDED' else '통계 신뢰구간·전역 유일성·공학 승인은 미확인입니다.'))
        elif (submitted or {}).get('method')=='differential_evolution':
            self.summary.setText('이 실행에 선택한 방법은 차분 진화(DE)입니다. 실제 후보와 원 평가 예산을 사용하며 adjoint 미분값은 제공하지 않습니다.')
        elif result:
            self.summary.setText('이 결과에 사용 가능한 adjoint가 없습니다. 비선형 Picard·DE 결과를 전체 연성 미분으로 표시하지 않습니다.')
        else:self.summary.setText('결과를 읽으면 실제 미분값·공유 입력·독립 검사·잔차를 표시합니다. 계산은 시작하지 않습니다.')
