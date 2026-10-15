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
         'model':'저장 모델','candidates':'평가할 표본','batch':'입력 묶음','results':'계산 자료',
         'baseline':'기준 N 분석','refined':'확장 2N 분석'}
STATE = {'SUCCEEDED':'계산됨','PARTIAL_FAILURE':'일부 실패','FAILED':'실패','REJECTED':'실행 거절',
         'CANCELLED':'취소됨','PREDICTED':'예측','NOT_EVALUATED':'미평가'}
SOURCES = ('ASSUMED','MEASURED_REPORTED','PUBLISHED_REFERENCE','SYNTHETIC')


CHOICE_LABELS = {
    'INDEPENDENT_USER_DECLARED':'독립 분포', 'CORRELATED_NORMAL_USER_DECLARED':'상관 정규분포',
    'JOINT_USER_DECLARED':'명시 결합분포',
    'ASSUMED':'사용자 가정', 'MEASURED_REPORTED':'측정 자료', 'PUBLISHED_REFERENCE':'공개 문헌', 'SYNTHETIC':'합성 예제',
    'summary':'요약 응답', 'all':'전체 응답', 'linear':'선형', 'log':'로그',
    'fit':'피팅', 'holdout':'검증', 'minimize':'최소화', 'maximize':'최대화',
    'none':'단일 값', 'max':'최댓값', 'min':'최솟값', 'mean':'평균', 'final':'마지막 증분', 'abs_max':'절댓값 최대',
    'uniform':'균등분포', 'normal':'정규분포', 'truncnorm':'절단 정규분포', 'lognormal':'로그정규분포',
    'least_squares':'최소제곱', 'differential_evolution':'차분 진화',
    'slsqp_adjoint':'선형 이산 adjoint (SLSQP)', 'native_integral':'유한요소 적분 평균', 'nodal_max':'절점 최댓값',
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
    reduction=row.get('reduction')
    if reduction and reduction!='none':response+=' '+CHOICE_LABELS.get(reduction,str(reduction))
    location=row.get('location')
    if isinstance(location,str) and location and location!='model':response+=' ('+location+')'
    return response+' ['+str(row.get('unit') or '단위 미지정')+'] '+CHOICE_LABELS.get(row.get('direction','minimize'),str(row.get('direction')))


def refresh_retained_labels(window, references):
    """Read exact source names asynchronously; never replace an edited buffer."""
    from PySide6.QtCore import QTimer
    cache=window.__dict__.setdefault('_retained_source_labels',{})
    for row,(role,reference) in enumerate(references.items()):
        if not isinstance(reference,dict):
            window._set_cell(window.pinned_sources,row,0,ROLES.get(role,role),False)
            window._set_cell(window.pinned_sources,row,1,'원자료 선택을 확인하세요',False)
            continue
        label,reason=cache.get(canonical_hash(reference),('자료 이름 확인 중',''))
        window._set_cell(window.pinned_sources,row,0,ROLES.get(role,role),False)
        window._set_cell(window.pinned_sources,row,1,label,False)
        window.pinned_sources.item(row,1).setToolTip(reason+'\n진단 정보\n'+'\n'.join(
            str(key)+': '+str(value) for key,value in reference.items()))
    if (not references or all(canonical_hash(ref) in cache for ref in references.values())
            or getattr(window,'_retained_labels_scheduled',False)):
        return
    window._retained_labels_scheduled=True
    def current_context():
        if not window.document:return None
        return (window.document['id'],window.document['session_id'],
                canonical_hash(window.edited_draft(commit=False)))
    def drain():
        from shiboken6 import isValid
        if not isValid(window) or window._closed:return
        if window._busy or window._callbacks:
            QTimer.singleShot(40,drain);return
        context=current_context()
        current=window.edited_draft(commit=False)['request']['inputs'].get('result_refs',{})
        if not isinstance(current,dict):
            window._retained_labels_scheduled=False;return
        refs={canonical_hash(ref):deepcopy(ref) for ref in current.values() if isinstance(ref,dict) and canonical_hash(ref) not in cache}
        if not refs:
            window._retained_labels_scheduled=False;return
        def read():
            result={}
            for key,ref in refs.items():
                try:
                    from caelab.research_operations import validate_result_reference
                    validate_result_reference(ref)
                    document=window.client.document_read(ref['document_id'])
                    if window.client.document_result_reference(ref['document_id'],ref['job_id'])!=ref:
                        raise ValueError('선택한 저장 결과의 입력 또는 내용이 바뀌었습니다.')
                    runs=document.get('runs',[])
                    index=next(i for i,run in enumerate(runs) if run.get('job_id')==ref['job_id'])
                    request=runs[index].get('draft',{}).get('request',{})
                    purpose=request.get('purpose') or '저장 결과'
                    result[key]=(document['title']+' / 계산 '+str(index+1)+' / '+purpose,'')
                except Exception as error:
                    result[key]=('원자료 읽기 실패',str(error)+' 저장 결과를 다시 선택하세요.')
            return result
        def accepted(result):
            cache.update(result);window._retained_labels_scheduled=False
            if current_context()==context:window._refresh_input_summary()
            else:
                current=window.edited_draft(commit=False)['request']['inputs'].get('result_refs',{})
                refresh_retained_labels(window,current if isinstance(current,dict) else {})
        window._call(read,accepted,background=True)
    QTimer.singleShot(0,drain)


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
            item.setData(DATA,dict(path=path,numeric=numeric,choices=choices,shown=shown,value=deepcopy(text)))
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
            from .numerical_extension_widgets import JointDistributionEditor
            self.joint_editor=JointDistributionEditor(value,variables,self)
            self.tabs.addTab(self.joint_editor,'결합분포')
            # Existing callers address this table; its cells still preserve exact text.
            self.correlation_table=self.joint_editor.matrix
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
                    from .request_plan_window import CHOICE_DATA
                    selected=item.data(CHOICE_DATA)
                    explicit=isinstance(selected,dict) and selected.get('label')==item.text()
                    if meta.get('path') and (item.text()!=meta['shown'] or explicit):
                        # Exact combo itemData is separate from typed unknown text.
                        parsed=deepcopy(selected['value']) if explicit else choice_value(item.text(),meta.get('choices',()))
                        patch(result,meta['path'],number(parsed) if meta['numeric'] and isinstance(parsed,str) else parsed)
                        if meta['path'][0]=='distributions':
                            law=result['distributions'][meta['path'][1]]
                            if 'unit' not in law:law['unit']=t.item(i,1).text()
        if hasattr(self,'joint_editor'):
            result=self.joint_editor.apply(result)
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
    if operation=='surrogate' and 'search' in value:
        from .numerical_extension_widgets import SurrogateSearchDialog
        dialog=SurrogateSearchDialog(value,window)
    else:
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
        add('분포 관계',('independence',),'',False,('INDEPENDENT_USER_DECLARED','CORRELATED_NORMAL_USER_DECLARED','JOINT_USER_DECLARED'))
        add('분포 근거',('source','origin'),'',False,SOURCES)
        add('자료 또는 가정',('source','reference'),'')
    elif operation=='surrogate' and 'search' in value:
        add('예측 탐색 세대 수',('search','options','max_generations'),5,True)
        add('예측 탐색 집단 크기',('search','options','population_size'),8,True)
        add('난수 시드',('search','seed'),0,True)
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
        add('이웃 수',('options','neighbors'),None,True,(('전역',None),))
    return rows


def refresh_search_sheet(window,value,operation):
    """Use the existing worksheet for the selected archive's nested search."""
    search=value.get('search') if operation=='surrogate' else None
    active=isinstance(search,dict)
    widgets=(window.variables_button,window.variable_domains_button,window.remove_variable_button,window.remove_response_button)
    if active:
        if not hasattr(window,'_search_hidden_controls'):
            window._search_hidden_controls=[(widget,widget.isHidden()) for widget in widgets]
        for widget in widgets:widget.hide()
    else:
        for widget,hidden in window.__dict__.pop('_search_hidden_controls',[]):widget.setHidden(hidden)
        return
    variables=search.get('variables',[])
    variables=variables if isinstance(variables,list) else []
    window.variable_sheet.setRowCount(len(variables))
    for row,variable in enumerate(variables):
        if not isinstance(variable,dict):continue
        for column,key in enumerate(('id','id','value','lower','upper','unit','transform')):
            path=('search','variables',row,key) if key in {'value','lower','upper'} else None
            window._sheet_cell(window.variable_sheet,row,column,variable.get(key),path,numeric=key in {'value','lower','upper'})
    definitions=[('목표',search.get('objective',{}),('search','objective'))]
    constraints=search.get('constraints',[])
    if isinstance(constraints,list):definitions.extend(('제약',d,('search','constraints',i)) for i,d in enumerate(constraints))
    window.response_sheet.setRowCount(len(definitions))
    for row,(label,definition,path) in enumerate(definitions):
        if not isinstance(definition,dict):continue
        window._sheet_cell(window.response_sheet,row,0,label)
        window._sheet_cell(window.response_sheet,row,1,definition.get('response'))
        window._sheet_cell(window.response_sheet,row,2,definition.get('reduction'),choices=tuple(CHOICE_LABELS))
        key='direction' if label=='목표' else 'operator'
        window._sheet_cell(window.response_sheet,row,3,definition.get(key),path+(key,),
            choices=('minimize','maximize') if label=='목표' else ('<=','>='))
        window._sheet_cell(window.response_sheet,row,4,definition.get('limit'),
            path+('limit',) if label=='제약' else None,numeric=True)
        window._sheet_cell(window.response_sheet,row,5,definition.get('unit'))


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
    if operation=='surrogate' and 'search' in value:
        window.method_edit.setText('저장 모델 예측 탐색…')
    summary=''
    if operation=='uq':
        laws=value.get('distributions',{})
        if isinstance(laws,dict):summary=', '.join(name+': '+CHOICE_LABELS.get(law.get('distribution'),str(law.get('distribution','미지정'))) for name,law in laws.items() if isinstance(law,dict))
        summary=summary or '변수별 분포를 지정하세요.'
    elif operation=='epsilon':
        grid=value.get('threshold_grid',[])
        summary='한계 조합 '+str(math.prod(len(row) for row in grid) if grid and all(isinstance(row,list) for row in grid) else 0)+'개'
    elif operation=='surrogate':
        if 'search' in value:
            summary='저장 모델로 추천점 탐색 / 실제 해석 미수행'
        else:
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
            indexes = [selector.currentData() for selector in (window.pareto_x, window.pareto_y)]
            x_index, y_index = [index if type(index) is int and 0 <= index < len(definitions) else default
                                for default, index in enumerate(indexes)]
            x_definition, y_definition = definitions[x_index], definitions[y_index]
            groups={'front':[],'feasible':[],'infeasible':[]}
            for row in result.get('candidates',[]):
                x,y=(scalar(row,d) for d in (x_definition, y_definition))
                if x is None or y is None:continue
                group='front' if row['candidate_id'] in archive else 'feasible' if row.get('feasible') else 'infeasible'
                groups[group].append((x,y,row['candidate_id']))
            for name,color,marker,label in [('infeasible','#999999','x','제약 위반'),('feasible','#7fa7c3','o','충족'),('front','#276b9d','D','비지배 후보')]:
                data=groups[name]
                if data:points(ax,[x for x,y,i in data],[y for x,y,i in data],[i for x,y,i in data],c=color,marker=marker,label=label)
            ax.set_xlabel(objective_label(x_definition))
            ax.set_ylabel(objective_label(y_definition))
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
        # Keep exact point identity in item data; the primary table uses task names.
        rows=result.get('candidates',result.get('predictions',[]))
        window.candidates.blockSignals(True)
        for index,row in enumerate(rows):
            item=window.candidates.item(index,0)
            if item is None:continue
            item.setData(Qt.ItemDataRole.UserRole,row.get('candidate_id'))
            item.setToolTip(str(row.get('candidate_id','')));item.setText('예측점 '+str(index+1))
            if result.get('surrogate_operation')=='search' and row.get('execution_status')=='PREDICTED':
                column=window.candidates.columnCount()-3
                item=window.candidates.item(index,column)
                item.setText(display_number(row.get('objective')));item.setToolTip(str(row.get('objective')))
                condition=('예측 충족' if row.get('predicted_feasible') else '예측 위반')
                if row.get('out_of_range'):condition+=' / 학습 범위 밖'
                window.candidates.item(index,column+1).setText(condition)
                window.candidates.horizontalHeaderItem(column).setText('예측 목적값 ['+str(result.get('response',{}).get('unit',''))+']')
        window.candidates.resizeColumnsToContents()
        window.candidates.blockSignals(False)
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
            ' / 실제 해석 미수행'+(' / 국소 계수 계산' if result.get('local_coefficients_computed') else ''))
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
