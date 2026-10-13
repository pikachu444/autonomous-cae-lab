"""Method-specific editors and retained-result plots for the existing Request Plan.

No jobs, training, adoption or document creation happens while reading this view.
All editor patches flow back through the window's single draft buffer.
"""
from copy import deepcopy
import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QStyledItemDelegate, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from caelab.storage import canonical_hash

DATA = Qt.ItemDataRole.UserRole
METHODS = {'fit','doe','optimize','uq','epsilon','sample_sensitivity','sensitivity','analyze','surrogate'}
ROLES = {'table':'분석 자료','plan':'Sobol 표본','training':'학습 자료','holdout':'검증 자료',
         'model':'저장 모델','candidates':'평가할 표본','batch':'입력 묶음','results':'계산 자료'}
STATE = {'SUCCEEDED':'계산됨','PARTIAL_FAILURE':'일부 실패','FAILED':'실패','REJECTED':'실행 거절',
         'CANCELLED':'취소됨','PREDICTED':'예측','NOT_EVALUATED':'미평가'}
SOURCES = ('ASSUMED','MEASURED_REPORTED','PUBLISHED_REFERENCE','SYNTHETIC')


CHOICE_LABELS = {
    'INDEPENDENT_USER_DECLARED':'독립 분포', 'CORRELATED_NORMAL_USER_DECLARED':'상관 정규분포',
    'ASSUMED':'사용자 가정', 'MEASURED_REPORTED':'측정 자료', 'PUBLISHED_REFERENCE':'공개 문헌', 'SYNTHETIC':'합성 예제',
    'summary':'요약 응답', 'all':'전체 응답', 'linear':'선형', 'log':'로그',
    'fit':'피팅', 'holdout':'검증', 'minimize':'최소화', 'maximize':'최대화',
    'none':'단일 값', 'max':'최댓값', 'min':'최솟값', 'mean':'평균', 'final':'마지막 증분', 'abs_max':'절댓값 최대',
    'uniform':'균등분포', 'normal':'정규분포', 'truncnorm':'절단 정규분포', 'lognormal':'로그정규분포',
    'least_squares':'최소제곱', 'differential_evolution':'차분 진화',
    'thin_plate_spline':'박판 스플라인', 'cubic':'3차', 'quintic':'5차',
    'multiquadric':'다중 이차', 'inverse_multiquadric':'역 다중 이차',
    'inverse_quadratic':'역 이차', 'gaussian':'가우시안',
}


def choice_options(choices):
    """(Visible label, canonical value); unknown values remain editable text."""
    rows=[]
    for value in choices:
        if isinstance(value,(tuple,list)) and len(value)==2:
            rows.append((str(value[0]),deepcopy(value[1])))
        elif type(value) is bool:
            rows.append(('포함' if value else '포함하지 않음',value))
        else:rows.append((CHOICE_LABELS.get(value,str(value)),value))
    return rows


def choice_label(value,choices):
    for label,canonical in choice_options(choices):
        if type(value) is type(canonical) and value==canonical:return label
    from .request_plan_window import value_text
    return '' if value is None else value_text(value)


def choice_value(text,choices):
    for label,canonical in choice_options(choices):
        if text==label:return deepcopy(canonical)
    return text


def objective_label(row):
    if not isinstance(row,dict):return '응답 미지정'
    response=str(row.get('response') or '응답 미지정')
    component=row.get('component')
    if component and component!='scalar':response+=' '+str(component)
    return response+' ['+str(row.get('unit') or '단위 미지정')+'] '+CHOICE_LABELS.get(row.get('direction','minimize'),str(row.get('direction')))


def display_number(value):
    if value is None:return '—'
    if type(value) is bool:return '예' if value else '아니요'
    if type(value) in (int,float):return format(value,'.6g') if math.isfinite(value) else '사용 불가'
    return str(value)


class ResultDisplay(QStyledItemDelegate):
    """Read-only paint formatting. Exact item data, tooltips and stored values remain."""
    def displayText(self,value,locale):
        if str(value)=='null':return '—'
        parsed=number(str(value))
        return display_number(parsed)


def number(text):
    from .request_plan_window import numeric_text
    return numeric_text(text)


def patch(value, path, item):
    for key in path[:-1]:
        if isinstance(value, dict) and key not in value:
            value[key] = {}
        value = value[key]
    value[path[-1]] = item


class MethodDialog(QDialog):
    """Local draft tables: Cancel has no effect on the Plan or service."""
    def __init__(self, window, value, operation):
        super().__init__(window)
        from .request_plan_window import _WorksheetDelegate, value_text
        self.setWindowTitle({'uq':'분포와 상관','epsilon':'목표별 한계값',
            'surrogate':'예측할 점','doe':'직접 지정할 후보'}[operation])
        self.resize(980,580)
        self.original = deepcopy(value)
        self.operation = operation
        self.tables = []
        self.extra = {}
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs,1)
        variables = value.get('variables',[])
        variables = variables if isinstance(variables,list) else []
        self.names = [v.get('id') for v in variables if isinstance(v,dict) and isinstance(v.get('id'),str)]
        def table(title, headers):
            item = QTableWidget(0,len(headers))
            item.setHorizontalHeaderLabels(headers)
            item.setItemDelegate(_WorksheetDelegate(item))
            item.horizontalHeader().setStretchLastSection(True)
            self.tabs.addTab(item,title);self.tables.append(item)
            return item
        def cell(t,row,col,text,path=None,numeric=False,choices=()):
            shown=choice_label(text,choices) if choices else value_text(text)
            item=QTableWidgetItem(shown)
            item.setToolTip(value_text(text))
            item.setData(DATA,dict(path=path,numeric=numeric,choices=choices,shown=shown))
            if path is None:item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            t.setItem(row,col,item)
        if operation=='uq':
            laws=value.get('distributions',{})
            laws=laws if isinstance(laws,dict) else {}
            t=table('변수별 분포',['변수','단위','분포','평균','표준편차','균등분포 하한','균등분포 상한'])
            t.setRowCount(len(variables))
            for i,v in enumerate(variables):
                name=v['id'];law=laws.get(name,{})
                if not isinstance(law,dict):law={}
                cell(t,i,0,name);cell(t,i,1,law.get('unit',v.get('unit','')))
                for j,key in enumerate(('distribution','mean','std','lower','upper'),2):
                    cell(t,i,j,law.get(key,''),('distributions',name,key),j>2,
                        ('uniform','normal','truncnorm','lognormal') if j==2 else ())
            note=QLabel('정규·로그정규 꼬리는 자르지 않습니다. 절단정규는 변수의 평가 범위를 사용합니다.')
            note.setWordWrap(True);layout.addWidget(note)
            matrix=table('정규분포 상관',['변수']+self.names)
            matrix.setRowCount(len(self.names))
            current=value.get('correlation',{})
            current=current if isinstance(current,dict) else {}
            raw=current.get('matrix',[])
            if current and current.get('variables')!=self.names:
                # Do not relabel an AB coefficient as AC after removing/reordering B.
                # Leave the original invalid declaration untouched until explicit
                # removal or a complete new matrix is entered.
                raw=[]
                warning=QLabel('변수가 바뀌었습니다. 기존 상관은 유지되며 실행이 차단됩니다. 새 행렬을 입력하거나 상관을 제거하세요.')
                warning.setWordWrap(True);layout.addWidget(warning)
            for i,name in enumerate(self.names):
                cell(matrix,i,0,name)
                for j in range(len(self.names)):
                    item=raw[i][j] if i<len(raw) and isinstance(raw[i],list) and j<len(raw[i]) else ''
                    cell(matrix,i,j+1,item,('correlation','matrix',i,j),True)
            self.correlation_table=matrix
            self.clear_correlation=False
            clear=QPushButton('상관 제거')
            def clear_matrix():
                self.clear_correlation=True
                for i in range(matrix.rowCount()):
                    for j in range(matrix.rowCount()):matrix.item(i,j+1).setText('')
            clear.clicked.connect(clear_matrix);layout.addWidget(clear)
        elif operation=='epsilon':
            objectives=value.get('objectives',[])
            primary=value.get('primary_index',0)
            secondary=[row for i,row in enumerate(objectives) if i!=primary]
            grid=value.get('threshold_grid',[])
            width=max([len(row) for row in grid if isinstance(row,list)]+[1])
            t=table('한계 조합',['보조 목표','단위']+['한계 '+str(i+1) for i in range(width)])
            t.setRowCount(len(secondary))
            for i,row in enumerate(secondary):
                cell(t,i,0,row.get('response',''));cell(t,i,1,row.get('unit',''))
                for j in range(width):
                    cell(t,i,j+2,grid[i][j] if i<len(grid) and j<len(grid[i]) else '',('threshold_grid',i,j),True)
            self.grid_table=t
            add=QPushButton('한계 열 추가')
            def more():
                col=t.columnCount();t.setColumnCount(col+1);t.setHorizontalHeaderItem(col,QTableWidgetItem('한계 '+str(col-1)))
                for i in range(t.rowCount()):cell(t,i,col,'',('threshold_grid',i,col-2),True)
            add.clicked.connect(more);layout.addWidget(add)
        else:
            key='points' if operation=='surrogate' else 'candidates'
            points=value.get(key,[])
            points=points if isinstance(points,list) else []
            t=table('예측할 점' if key=='points' else '후보 좌표',['점']+[name+' ['+str(v.get('unit',''))+']' for name,v in zip(self.names,variables)])
            t.setRowCount(len(points))
            def add_row(values=None,original=None):
                i=t.rowCount();t.setRowCount(i+1)
                cell(t,i,0,str(i+1));t.item(i,0).setData(DATA,{'original':deepcopy(original)})
                for j,name in enumerate(self.names,1):cell(t,i,j,(values or {}).get(name,''),(key,i,name),True)
            t.setRowCount(0)
            for row in points:add_row(row.get('values',row),row)
            self.points_table=t;self.points_key=key
            actions=QHBoxLayout()
            add=QPushButton('점 추가');remove=QPushButton('선택 제거')
            add.clicked.connect(lambda:add_row())
            remove.clicked.connect(lambda:[t.removeRow(i) for i in sorted({index.row() for index in t.selectedIndexes()},reverse=True)])
            actions.addWidget(add);actions.addWidget(remove);actions.addStretch();layout.addLayout(actions)
        for t in self.tables:
            t.resizeColumnsToContents()
            for col in range(t.columnCount()):t.setColumnWidth(col,max(100,t.columnWidth(col)))
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def value(self):
        result=deepcopy(self.original)
        if hasattr(self,'points_table'):
            rows=[]
            for i in range(self.points_table.rowCount()):
                values={name:number(self.points_table.item(i,j+1).text()) for j,name in enumerate(self.names)}
                old=self.points_table.item(i,0).data(DATA).get('original')
                rows.append({**deepcopy(old),'values':values} if isinstance(old,dict) and 'values' in old else
                            {'values':values} if self.points_key=='candidates' else values)
            result[self.points_key]=rows
            if self.points_key=='candidates':
                refs=result.get('result_refs')
                if isinstance(refs,dict) and 'candidates' in refs:
                    refs.pop('candidates')
                    if not refs:result.pop('result_refs')
                result.pop('count',None)
            return result
        for t in self.tables:
            if t is getattr(self,'correlation_table',None) or t is getattr(self,'grid_table',None):continue
            for i in range(t.rowCount()):
                for j in range(t.columnCount()):
                    item=t.item(i,j);meta=item.data(DATA) or {}
                    if meta.get('path') and item.text()!=meta['shown']:
                        # Empty text is retained if edited; invalid drafts remain repairable.
                        parsed=choice_value(item.text(),meta.get('choices',()))
                        patch(result,meta['path'],number(parsed) if meta['numeric'] and isinstance(parsed,str) else parsed)
                        if meta['path'][0]=='distributions':
                            law=result['distributions'][meta['path'][1]]
                            if 'unit' not in law:law['unit']=t.item(i,1).text()
        if hasattr(self,'correlation_table'):
            t=self.correlation_table
            changed=any(t.item(i,j+1).text()!=t.item(i,j+1).data(DATA)['shown']
                for i in range(t.rowCount()) for j in range(t.rowCount()))
            if self.clear_correlation and all(not t.item(i,j+1).text() for i in range(t.rowCount()) for j in range(t.rowCount())):
                result.pop('correlation',None)
                result['independence']='INDEPENDENT_USER_DECLARED'
            elif changed:
                result['correlation']={'variables':self.names,'matrix':[
                    [number(t.item(i,j+1).text()) for j in range(t.rowCount())] for i in range(t.rowCount())]}
        if hasattr(self,'grid_table'):
            t=self.grid_table
            result['threshold_grid']=[[number(t.item(i,j).text()) for j in range(2,t.columnCount())
                if t.item(i,j).text()!=''] for i in range(t.rowCount())]
        return result


def edit_method(window):
    operation=window.operation.currentData()
    before=window.edited_draft()
    identity=(window.document['id'],window.document['session_id'])
    value=deepcopy(before['request']['inputs'])
    if operation=='surrogate' and not value.get('variables'):
        refs=value.get('result_refs',{})
        ref=refs.get('model',refs.get('training',{}))
        metadata=window._source_metadata.get(canonical_hash(ref),{})
        value['variables']=deepcopy(metadata.get('variables',[]))
    dialog=MethodDialog(window,value,operation)
    if dialog.exec()!=QDialog.DialogCode.Accepted:return
    if identity!=(window.document['id'],window.document['session_id']) or window.edited_draft()!=before:
        window.message.setText('계획이 바뀌었습니다. 현재 편집을 유지했으니 다시 선택하세요.');return
    edited=dialog.value()
    if operation=='surrogate' and 'model' in edited.get('result_refs',{}):edited.pop('variables',None)
    window._edit_structure(lambda current:(current.clear(),current.update(edited)))


def method_settings(operation,value):
    rows=[]
    def add(label,path,default,numeric=False,choices=()):rows.append((label,path,default,numeric,choices))
    if operation in {'uq','sample_sensitivity'}:
        add('표본 수' if operation=='uq' else 'Sobol 기본 표본 수',('count',),128,True)
        add('난수 시드',('seed',),0,True)
    if operation=='uq':
        add('분포 관계',('independence',),'',False,('INDEPENDENT_USER_DECLARED','CORRELATED_NORMAL_USER_DECLARED'))
        add('분포 근거',('source','origin'),'',False,SOURCES)
        add('자료 또는 가정',('source','reference'),'')
    elif operation=='sample_sensitivity':
        add('2차 효과 포함',('second_order',),False,False,(False,True))
    elif operation=='epsilon':
        objectives=value.get('objectives',[])
        choices=tuple((objective_label(row),index) for index,row in enumerate(objectives)) if isinstance(objectives,list) else ()
        add('주 목표',('primary_index',),0,True,choices)
        add('전체 평가 예산',('total_evaluation_budget',),1000,True)
        add('세대 수',('options','max_generations'),40,True)
        add('집단 크기',('options','population_size'),12,True)
        add('난수 시드',('seed',),0,True)
        add('응답 보존',('options','retain_responses'),'summary',False,('summary','all'))
    elif operation=='surrogate' and 'model' not in value.get('result_refs',{}):
        add('RBF 커널',('options','kernel'),'thin_plate_spline',False,
            ('thin_plate_spline','linear','cubic','quintic','multiquadric','inverse_multiquadric','inverse_quadratic','gaussian'))
        add('평활화',('options','smoothing'),0.,True)
        add('형상 계수 (필요한 커널)',('options','epsilon'),1.,True)
        degree={'multiquadric':0,'linear':0,'thin_plate_spline':1,'cubic':1,'quintic':2}.get((value.get('options') if isinstance(value.get('options'),dict) else {}).get('kernel','thin_plate_spline'),0)
        add('다항식 차수',('options','degree'),degree,True)
    return rows


def refresh_extra(window,value,operation):
    # Called while worksheet signals are suppressed, from the one draft buffer.
    extra=method_settings(operation,value)
    if operation in {'uq','epsilon','sample_sensitivity','surrogate','sensitivity','analyze'}:
        window.method_sheet.setRowCount(len(extra))
        for row,(label,path,default,numeric,choices) in enumerate(extra):
            try:setting=window._at_path(value,path)
            except (KeyError,TypeError,IndexError):setting=default
            window._sheet_cell(window.method_sheet,row,0,label)
            window._sheet_cell(window.method_sheet,row,1,setting,path,numeric=numeric,choices=choices)
    visible=operation in {'uq','epsilon','surrogate','doe'}
    window.method_edit.setVisible(visible)
    window.method_edit.setText({'uq':'분포와 상관…','epsilon':'목표별 한계값…','surrogate':'예측할 점…','doe':'후보 직접 지정…'}.get(operation,'방법 설정'))
    summary=''
    if operation=='uq':
        laws=value.get('distributions',{})
        if isinstance(laws,dict):summary=', '.join(name+': '+CHOICE_LABELS.get(law.get('distribution'),str(law.get('distribution','미지정'))) for name,law in laws.items() if isinstance(law,dict))
        summary=summary or '변수별 분포를 지정하세요.'
    elif operation=='epsilon':
        grid=value.get('threshold_grid',[])
        summary='한계 조합 '+str(math.prod(len(row) for row in grid) if grid and all(isinstance(row,list) for row in grid) else 0)+'개'
    elif operation=='surrogate':
        summary='저장 모델 예측' if 'model' in value.get('result_refs',{}) else '학습 자료와 별도 검증 자료를 선택하세요.'
        summary+=' / 예측할 점 '+str(len(value.get('points',[])))+'개'
    elif operation=='sample_sensitivity':
        count=value.get('count');variables=value.get('variables',[])
        if type(count) is int:summary='평가할 표본 '+str(count*(2*len(variables)+2 if value.get('second_order') is True else len(variables)+2))+'개 (SALib 필요)'
    window.method_summary.setText(summary);window.method_summary.setVisible(bool(summary))


def scalar(row,definition):
    from caelab.numerical import _scalar,EvaluationFailed
    try:return _scalar(row,definition)
    except (EvaluationFailed,ValueError,TypeError,KeyError):return None


def selected_row(window,result):
    selected=window.candidates.selectionModel().selectedRows()
    rows=result.get('candidates',result.get('predictions',[]))
    return rows[selected[0].row()] if len(selected)==1 and selected[0].row()<len(rows) else None


def plot(window,result,inputs):
    """Render method result, return False to reuse an existing direct/fit curve."""
    kind=result.get('kind')
    ax=window.figure.add_subplot(111)
    selected=selected_row(window,result)
    def points(axis,xx,yy,ids,**style):
        artist=axis.scatter(xx,yy,picker=5,**style);artist._candidate_ids=ids
        if selected and selected.get('candidate_id') in ids:
            i=ids.index(selected['candidate_id'])
            axis.scatter(xx[i],yy[i],s=100,facecolors='none',edgecolors='#d56c22',linewidths=2)
        return artist
    def empty(message):
        ax.text(.5,.5,message,ha='center',va='center',wrap=True,transform=ax.transAxes);ax.set_axis_off()
    if kind=='uq':
        stats=result.get('probability_statistics',[])
        index=window.method_response.currentIndex()
        stat=stats[max(0,index)] if stats else {}
        definition=stat.get('threshold',{})
        rows=result.get('candidates',[])
        values=[(scalar(row,definition),row.get('candidate_id')) for row in rows]
        values=[(v,i) for v,i in values if v is not None]
        if values:
            values.sort(key=lambda item:item[0])
            points(ax,[v for v,_ in values],[(i+1)/len(values) for i in range(len(values))],[i for _,i in values],s=24)
            ax.set_ylabel('유효 표본 조건부 누적 비율')
            ax.set_xlabel(str(stat.get('response',''))+' ['+str(stat.get('unit',''))+']')
            ax.set_ylim(0,1.05)
        else:empty('이 응답의 유효 표본이 없습니다.')
        window.result_summary.setText('전체 '+str(len(rows))+' / 유효 '+str(stat.get('valid_count',0))+
            ' / 응답 사용 불가 '+str(stat.get('failed_count',0))+
            ' (전체 중 '+display_number(stat.get('failure_fraction'))+')'+
            '  |  q05 / q50 / q95: '+' / '.join(display_number(stat.get('quantiles',{}).get(k)) for k in ('q05','q50','q95'))+
            '  |  유효 표본의 기준 초과 비율: '+display_number(stat.get('exceedance_fraction_valid')))
    elif kind=='epsilon_optimization':
        definitions=inputs.get('objectives',[])
        archive=set(result.get('pareto',{}).get('nondominated_ids',[]))
        if len(definitions)<2:empty('보존된 목표 정의가 없습니다.')
        else:
            groups={'front':[],'feasible':[],'infeasible':[]}
            for row in result.get('candidates',[]):
                x,y=(scalar(row,d) for d in definitions[:2])
                if x is None or y is None:continue
                group='front' if row['candidate_id'] in archive else 'feasible' if row.get('feasible') else 'infeasible'
                groups[group].append((x,y,row['candidate_id']))
            for name,color,marker,label in [('infeasible','#999999','x','제약 위반'),('feasible','#7fa7c3','o','충족'),('front','#276b9d','D','비지배 후보')]:
                data=groups[name]
                if data:points(ax,[x for x,y,i in data],[y for x,y,i in data],[i for x,y,i in data],c=color,marker=marker,label=label)
            ax.set_xlabel(definitions[0]['response']+' ['+definitions[0]['unit']+']')
            ax.set_ylabel(definitions[1]['response']+' ['+definitions[1]['unit']+']')
            if ax.collections:ax.legend()
        children=result.get('children',[])
        dispatch=[row.get('dispatched_evaluations_total') for row in children]
        window.result_summary.setText('한계 조합 '+str(len(children))+' / 비지배 후보 '+str(len(archive))+
            ' / 실제 평가 '+(str(sum(dispatch)) if all(type(v) is int for v in dispatch) else '이전 결과에 미보존'))
    elif result.get('method')=='SALib.sobol':
        names=result.get('sampling',{}).get('problem',{}).get('names',[])
        indices=result.get('indices',{})
        positions=list(range(len(names)))
        for offset,key,label in [(-.18,'S1','1차 효과'),(.18,'ST','총효과')]:
            vals=indices.get(key,[]);ci=indices.get(key+'_conf',[])
            valid=[i for i,v in enumerate(vals) if v is not None and math.isfinite(v)]
            if valid:ax.bar([positions[i]+offset for i in valid],[vals[i] for i in valid],width=.35,label=label,
                yerr=[ci[i] if i<len(ci) and ci[i] is not None else 0 for i in valid])
        ax.set_xticks(positions,names);ax.set_ylabel('Sobol 지수 [1]')
        if ax.containers:ax.legend()
        window.result_summary.setText('matched 표본 '+str(len(result.get('candidate_ids',[])))+'개 / 미정 지수는 값 없음으로 보존')
    elif kind=='surrogate':
        validation=result.get('validation',{})
        mode=window.method_response.currentData()
        if mode=='holdout':
            observed=validation.get('holdout_observed',[]);predicted=validation.get('holdout_prediction',[])
            if len(observed)==len(predicted) and observed:
                ax.scatter(observed,predicted)
                low,high=min(observed+predicted),max(observed+predicted)
                ax.plot([low,high],[low,high],color='#999999',linestyle='--')
                ax.set_xlabel('검증 관측 ['+str(validation.get('unit',''))+']');ax.set_ylabel('예측 ['+str(validation.get('unit',''))+']')
            else:empty('이전 결과에는 검증 관측값이 보존되지 않았습니다.')
        else:
            rows=result.get('predictions',[])
            coords=[];values=[];ids=[]
            for i,row in enumerate(rows):
                response=next(iter(row.get('responses',{}).values()),{})
                if type(response.get('value')) in (int,float) and math.isfinite(response['value']):
                    coords.append(i+1);values.append(response['value']);ids.append(row['candidate_id'])
            if coords:points(ax,coords,values,ids)
            else:empty('예측할 점을 지정하고 명시적으로 실행하세요.')
            ax.set_xlabel('예측점 번호');ax.set_ylabel('예측 ['+str(validation.get('unit',''))+']')
        excluded=validation.get('exclusions',{})
        window.result_summary.setText('검증 RMSE '+display_number(validation.get('rmse'))+' ['+str(validation.get('unit',''))+']'+
            ' / 제외: 학습 '+str(len(excluded.get('training',[])))+', 검증 '+str(len(excluded.get('holdout',[])))+
            ' / 실제 해석 미수행')
    elif result.get('sensitivity'):
        analyses=result['sensitivity']
        index=max(0,window.method_response.currentIndex())
        item=analyses[min(index,len(analyses)-1)]
        coeffs=item.get('coefficients',[])
        if item.get('valid') and coeffs:
            ax.bar([v.get('parameter_id','') for v in coeffs],[v['coefficient'] for v in coeffs])
            ax.set_ylabel('표준화 회귀계수 [1]')
        else:empty(str(item.get('reason') or '회귀 영향도를 계산할 수 없습니다.'))
        window.result_summary.setText('회귀 영향도 / rank '+str(item.get('rank'))+' / condition '+str(item.get('condition_number'))+
            ' / 사용 '+str(len(item.get('sample_ids',[])))+' / 제외 '+str(len(result.get('exclusions',[]))))
    else:
        window.figure.delaxes(ax);return False
    return True


class ConfirmationDialog(QDialog):
    """Two retained values at one exact point; reading cannot create a job."""
    def __init__(self,parent,record):
        super().__init__(parent)
        from .request_plan_window import value_text
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        self.setWindowTitle('예측과 실제 평가')
        self.resize(780,560)
        layout=QVBoxLayout(self)
        definition=record['definition']
        layout.addWidget(QLabel(str(definition['response'])+' ['+str(definition['unit'])+']'))
        table=QTableWidget(3,2)
        table.setHorizontalHeaderLabels(['값','결과'])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for i,(label,key) in enumerate((('저장 예측','predicted'),('실제 평가','actual'),('실제 − 예측','difference'))):
            table.setItem(i,0,QTableWidgetItem(label))
            cell=QTableWidgetItem('사용 불가' if record[key] is None else display_number(record[key]))
            cell.setData(DATA,deepcopy(record[key]));cell.setToolTip(value_text(record[key]))
            table.setItem(i,1,cell)
        table.resizeColumnsToContents();table.setMaximumHeight(150);layout.addWidget(table)
        figure=Figure(figsize=(6,3));canvas=FigureCanvasQTAgg(figure);layout.addWidget(canvas,1)
        ax=figure.add_subplot(111)
        ax.scatter([0],[record['predicted']],marker='x',label='저장 예측')
        if record['actual'] is not None:ax.scatter([0],[record['actual']],marker='o',facecolors='none',edgecolors='#276b9d',label='실제 평가')
        ax.set_xticks([0],['같은 좌표']);ax.set_ylabel('['+definition['unit']+']');ax.legend()
        figure.tight_layout()
        if record['reason']:
            reason=QLabel(record['reason']);reason.setWordWrap(True);layout.addWidget(reason)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject);layout.addWidget(buttons)


def remap_thresholds(before,after):
    """Keep physical objective identity when the primary/rows change in a sheet."""
    old=before.get('objectives',[])
    new=after.get('objectives',[])
    oi=before.get('primary_index',0)
    ni=after.get('primary_index',0)
    if old==new and oi==ni:return
    if not isinstance(old,list) or not isinstance(new,list):return
    valid_old=type(oi) is int and 0<=oi<len(old)
    if old!=new and oi==ni and valid_old:
        original=canonical_hash(old[oi])
        matches=[i for i,row in enumerate(new) if canonical_hash(row)==original]
        ni=matches[0] if len(matches)==1 else ''
        after['primary_index']=ni
    # A temporarily invalid primary cannot safely name any existing secondary.
    old_grid=before.get('threshold_grid',[])
    secondary=[row for i,row in enumerate(old) if i!=oi]
    mapping={}
    if valid_old and isinstance(old_grid,list):
        for row,values in zip(secondary,old_grid):
            key=canonical_hash(row)
            if key in mapping:mapping[key]=None
            else:mapping[key]=deepcopy(values)
    after['threshold_grid']=[deepcopy(mapping.get(canonical_hash(row)) or [])
                            for i,row in enumerate(new) if i!=ni]
