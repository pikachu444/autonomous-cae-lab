"""Separate preview/draft/apply/freeze operations using current registered Pre owner.

No new service route/store or auto-run. Exact command IDs recover a lost reply;
closing the dialog never cancels or replays a possibly applied native operation.
"""
from copy import deepcopy
import json,re,traceback,uuid
from PySide6.QtCore import Qt,QTimer,QThreadPool
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,QLabel,
    QPushButton,QPlainTextEdit,QMessageBox,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView)
from caelab.storage import canonical_hash
from caelab.law_native_fe import default_settings
from caelab.workbench_client import WorkbenchHTTPError
from .material_window import _Call,error_message

_WORKERS=set()


def law_error_text(error):
    """Task guidance only; the unmodified cause stays in existing details."""
    if isinstance(error,(list,tuple)):
        return '\n'.join(dict.fromkeys(law_error_text(item) for item in error))
    raw=getattr(error,'service_message',None) or error_message(error)
    text=raw.lower()
    if 'uniaxial fe pair requires explicit zero yy/zz point stress controls' in text:
        return '자유 횡변형 시편에는 재료의 횡응력·구속 조건에서 yy와 zz 응력 이력을 모두 0으로 명시하세요. 변경 적용·저장 후 다시 검토하세요.'
    if text.startswith('dp: e,k0>0;'):
        return 'DP 계수 조건: '+raw.partition(':')[2].strip()+'. 계수와 단위에서 해당 값을 수정하세요.'
    scale=re.fullmatch(r'(E|k0|H|K0|G0|K1|G1|mu|lmbda): exceeds admitted ([0-9.eE+-]+) MPa scale',raw)
    if scale:return scale[1]+' 계수의 절댓값은 '+scale[2]+' MPa 이하여야 합니다. 계수 값과 응력 단위를 확인하세요.'
    for prefix,label,action in (
        ('SLS tau requires ','이완 시간 τ 조건: ','계수와 단위에서 τ를 수정하세요.'),
        ('SLS moduli require ','SLS 체적·전단 계수 조건: ','계수와 단위에서 K₀, G₀, K₁, G₁을 확인하세요.'),
        ('Small FE mesh requires ','메시 요소 수 조건: ','Hex8 체적 요소 수를 확인하세요.'),
        ('FE mesh requires ','메시 절점 수 조건: ','구속되지 않은 내부 절점을 포함하도록 메시를 준비하세요.'),
    ):
        if raw.startswith(prefix):return label+raw[len(prefix):]+'\n'+action
    if 'hex8 connectivity must contain eight distinct existing zero-based nodes' in text:
        return 'Hex8 요소마다 서로 다른 기존 절점 8개를 0부터 시작하는 번호로 연결하세요. 메시 연결성을 확인하세요.'
    for words,message in (
        (('interface_source_conflict',), '설치된 법칙 원문이 저장된 재료와 다릅니다. 법칙 버전을 확인하고 다시 검토하세요.'),
        (('source_conflict','source revision','saved material changed'), '저장 재료의 원문이나 입력이 바뀌었습니다. 편집본을 보관하고 재료를 다시 저장한 뒤 검토하세요.'),
        (('assignment_stale','target_conflict','generation','문서가 바뀌어'), '해석 대상이나 저장 상태가 바뀌었습니다. 대상 다시 읽기 후 계수 변환을 다시 검토하세요.'),
        (('law_native_interface_required',), '이 재료는 기존 탄성 카드로 내보낼 수 없습니다. FELUPE 시편의 FE 입력 고정을 사용하세요.'),
        (('calculix solver','ccxtools','native context solver'), '전처리에서 이 해석에 속한 CalculiX 해석기 설정을 선택하세요. 시편 계산에는 FELUPE를 사용합니다.'),
        (('jacobian','ordering'), 'Hex8 절점 순서와 요소 Jacobian 방향이 선언한 SMESH 순서와 다릅니다. 메시의 연결·요소 방향을 확인하세요. 자동 보정하지 않습니다.'),
        (('hex8','hexahedron8'), '선형 Hex8 체적 메시를 선택하세요. 다른 요소를 자동 변환하지 않습니다.'),
        (('whole-solid','multibody','전체 솔리드'), '하나의 전체 솔리드 영역과 그 영역의 메시를 선택하세요. 부분 영역은 자동 재할당하지 않습니다.'),
        (('saved_revision','saved material','saved revision','먼저 저장'), '재료의 변경을 적용하고 저장한 뒤 다시 전달하세요. 미저장 입력은 자동 채택하지 않습니다.'),
        (('모두 선택','exact analysis','incomplete native'), '해석·재료·전체 솔리드 영역·Hex8 메시·해석기 설정을 모두 선택하세요.'),
        (('law_native_version_unsupported','law_native_proxy_unsupported'), '지원하는 FreeCAD 1.1.4와 재료·해석기 설정인지 확인하세요. 원 할당은 그대로 보존합니다.'),
        (('constraint','native loads','dynamic/contact'), '기존 하중·구속·접촉 조건을 확인하세요. 별도 시편 해석을 준비한 뒤 다시 검토하세요.'),
    ):
        if any(word in text for word in words):return message
    # Only known domain sentences may remain verbatim; service IDs/trace do not.
    if (raw.startswith(('Physical times must','History requires','FE maximum iterations',
            'Fixed force tolerance','SLS physical strain','SLS admits physical strain',
            'All four bulk/shear','DP time must','DP initial time/kappa',
            'Nonpositive det(F)','This Neo-Hooke FE pair','Small-strain law outside',
            'Probe h must','Explicit Pa/kPa/MPa/GPa','Uniaxial pair','Uniaxial initial',
            'Uniaxial origin','Free-lateral public pair','Affine FE boundary'))
            and '\n' not in raw and not re.search(r'HTTP|Traceback|0x[0-9a-f]+|[0-9a-f]{64}',raw)):
        return '물리 입력 조건: '+raw+'\n해당 계수·이력·시편 조건을 수정한 뒤 다시 검토하세요.'
    return '요청을 완료하지 못했습니다. 입력과 대상 상태를 확인하세요. 원인과 수치·단위는 기술 상세에서 확인할 수 있습니다.'


class LawNativeTransferDialog(QDialog):
    def __init__(self,client,material,parent=None):
        super().__init__(parent);self.client=client;self.material=deepcopy(material)
        self.target=None;self.review=None;self.preview_command=None;self.pending=None;self._busy=False;self._closed=False
        self._children=[];self.frozen=None
        from .appearance import apply_appearance
        from PySide6.QtWidgets import QApplication
        apply_appearance(QApplication.instance())
        self.setWindowTitle('저장 재료를 FE에 할당');self.resize(960,800)
        layout=QVBoxLayout(self)
        title=QLabel(material['title']);title.setProperty('appearanceRole','section');layout.addWidget(title)
        self.note=QLabel('FreeCAD의 해석과 전체 솔리드 영역을 선택하세요. 계산에는 FELUPE Hex8 시편을 사용합니다.')
        self.note.setTextFormat(Qt.TextFormat.PlainText)
        self.note.setWordWrap(True);layout.addWidget(self.note)
        form=QFormLayout();self.docs=QComboBox();form.addRow('전처리 문서',self.docs);self.fields={}
        for key,label in [('analysis_id','해석'),('material_id','재료'),('region_id','전체 솔리드 영역'),
                          ('mesh_id','Hex8 메시'),('solver_id','해석기 설정')]:
            box=QComboBox();self.fields[key]=box;form.addRow(label,box)
        self.boundary=QComboBox();self.boundary.addItem('전체 표면의 명시 F 이력','affine_boundary')
        self.boundary.addItem('축방향 인장/압축 · 횡응력 0','uniaxial_zero_lateral');form.addRow('시편 조건',self.boundary)
        layout.addLayout(form)
        buttons=QHBoxLayout();self.actions={}
        for name,caption,callback in [('refresh','대상 다시 읽기',self.refresh),('read','저장 할당 읽기',self.read_assignment),
            ('preview','계수 변환 검토',self.preview)]:
            b=QPushButton(caption);b.clicked.connect(callback);buttons.addWidget(b);self.actions[name]=b
        buttons.addStretch();layout.addLayout(buttons)
        self.summary_title=QLabel('저장된 계수의 원값과 적용값을 검토하세요.');layout.addWidget(self.summary_title)
        self.summary_title.setTextFormat(Qt.TextFormat.PlainText);self.summary_title.setWordWrap(True)
        self.summary=QTableWidget(0,5)
        self.summary.setHorizontalHeaderLabels(['계수','원값','원단위','적용값','적용단위'])
        self.summary.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.summary.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.summary.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.summary.verticalHeader().hide();layout.addWidget(self.summary,1)
        layout.addWidget(QLabel('전달 메모'))
        self.raw=QPlainTextEdit();self.raw.setPlaceholderText('미완성 입력과 전달 메모를 그대로 보관합니다.')
        self.raw.setMaximumHeight(70);layout.addWidget(self.raw)
        buttons=QHBoxLayout()
        for name,caption,callback in [('save','전달 초안 저장',self.save_draft),('apply','검토 내용 적용',self.apply),
            ('freeze','FE 입력 고정',self.freeze),('open','해석에서 열기',self.open_simulation)]:
            b=QPushButton(caption);b.clicked.connect(callback);buttons.addWidget(b);self.actions[name]=b
        self.actions['apply'].setProperty('appearanceRole','primary');layout.addLayout(buttons)
        self.details_toggle=QPushButton('기술 상세');self.details_toggle.setCheckable(True)
        layout.addWidget(self.details_toggle)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMaximumHeight(150);self.detail.hide()
        self.details_toggle.toggled.connect(self.detail.setVisible);layout.addWidget(self.detail)
        row=QHBoxLayout();self.recover=QPushButton('동일 명령 결과 재조회');self.recover.clicked.connect(self.recover_pending)
        close=QPushButton('닫기');close.clicked.connect(self.reject);row.addWidget(self.recover);row.addWidget(close);layout.addLayout(row)
        self.timer=QTimer(self);self.timer.setInterval(300);self.timer.timeout.connect(self.poll)
        self.docs.currentIndexChanged.connect(self.read_target)
        for box in self.fields.values():box.currentIndexChanged.connect(self.invalidate)
        self.boundary.currentIndexChanged.connect(self.invalidate)
        self.update_actions();self.refresh()

    def _call(self,fn,success,failure=None):
        if self._busy or self._closed:return
        def invoke():
            try:return fn(),None
            except Exception as error:return None,error
        self._busy=True;self.update_actions();work=_Call(invoke);_WORKERS.add(work)
        def done(result,error):
            _WORKERS.discard(work)
            if self._closed:return
            self._busy=False
            if error is None:result,error=result
            if error:
                if failure:failure(error)
                else:self.show_error(error)
            else:
                try:success(result)
                except Exception as issue:self.show_error(issue)
            self.update_actions()
        work.signals.finished.connect(done,Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(work)

    def show_error(self,error,context=''):
        self.note.setText((context+'\n' if context else '')+law_error_text(error))
        detail=''.join(traceback.format_exception(type(error),error,error.__traceback__)) if isinstance(error,BaseException) else str(error)
        self.detail.appendPlainText(detail)

    def update_actions(self):
        free=not self._busy and self.pending is None
        for name,button in self.actions.items():button.setEnabled(free)
        for name in ('read','save','preview','freeze'):self.actions[name].setEnabled(free and self.target is not None)
        self.actions['apply'].setEnabled(free and self.review is not None and self.review.get('status')=='READY_FOR_EXPLICIT_APPLY')
        self.actions['open'].setEnabled(free and self.frozen is not None)
        self.recover.setEnabled(not self._busy and self.pending is not None)
        self.recover.setText('같은 요청으로 복구' if self.pending and self.pending.get('unconfirmed') else '동일 명령 결과 재조회')
        self.docs.setEnabled(free);self.boundary.setEnabled(free)
        for box in self.fields.values():box.setEnabled(free)

    def invalidate(self,*_):
        self.review=None;self.preview_command=None;self.frozen=None;self.summary.setRowCount(0)
        self.summary_title.setText('대상과 시편 조건을 확인한 뒤 계수 변환을 검토하세요.')
        self.update_actions()

    def refresh(self):
        def done(payload):
            previous=self.docs.currentData();self.docs.blockSignals(True);self.docs.clear()
            for d in payload['documents']:
                if d.get('kind')=='pre' and d.get('connected'):
                    self.docs.addItem(d['title'],d['id'])
            if self.docs.findData(previous)>=0:self.docs.setCurrentIndex(self.docs.findData(previous))
            self.docs.blockSignals(False)
            if not self.docs.count():
                self.target=None
                for box in self.fields.values():box.clear()
                self.invalidate();self.note.setText('연결된 FreeCAD 문서가 없습니다. 전처리에서 시편을 연 뒤 대상을 다시 읽으세요.')
                return
            QTimer.singleShot(0,self.read_target)
        self._call(self.client.documents,done)

    def read_target(self,*_):
        identifier=self.docs.currentData()
        if not identifier:return
        def done(d):
            self.target=d;self.invalidate();objects=d.get('objects',[])
            selectors={'analysis_id':lambda x:'Analysis' in x['type'],
                'material_id':lambda x:'Material' in x['type'],
                'mesh_id':lambda x:'Mesh' in x['type'], 'solver_id':lambda x:'Solver' in x['type']}
            for key,box in self.fields.items():
                old=box.currentData();box.blockSignals(True);box.clear()
                rows=d.get('fem',{}).get('regions',[]) if key=='region_id' else [x for x in objects if selectors[key](x)]
                for x in rows:box.addItem(x.get('label',x.get('name',x['id'])),x['id'])
                if box.findData(old)>=0:box.setCurrentIndex(box.findData(old))
                box.blockSignals(False)
            self.note.setText('대상 문맥을 읽었습니다. 대상·시편 조건을 선택하고 검토하세요. native 하중이 있으면 차단됩니다.')
        self._call(lambda:self.client.document_read(identifier),done)

    def selection(self):
        s={key:box.currentData() for key,box in self.fields.items()}
        if not self.target or any(not v for v in s.values()):raise ValueError('정확한 해석·재료·영역·메시·native 문맥을 모두 선택하세요.')
        return s

    def submit(self,op,args,done):
        try:
            args={'selection':self.selection(),**args};d=deepcopy(self.target)
        except ValueError as error:self.show_error(error);return
        cid='C'+uuid.uuid4().hex
        self.pending={'id':cid,'operation':op,'done':done,'unconfirmed':False,
            'service_session_id':d.get('service_session_id'),
            'request':{'identifier':d['id'],'operation':op,'arguments':deepcopy(args),
                'session_id':d['session_id'],'expected_generation':d['generation'],'command_id':cid}}
        self.update_actions();self._send_pending()

    def _send_pending(self):
        if not self.pending or self._busy:return
        request=deepcopy(self.pending['request'])
        def queued(result):
            self.pending['unconfirmed']=False
            self.timer.start();self.handle_status(result)
        def failed(error):
            self.timer.stop()
            if isinstance(error,WorkbenchHTTPError) and error.code in (400,403,404,409,422):
                if not self.pending['unconfirmed']:self._reject_pending(error)
                else:self._resolve_rejected_retry(error)
            else:
                self.pending['unconfirmed']=True
                self.show_error(error,'적용 여부가 미확인입니다. 「같은 요청으로 복구」를 눌러 확인하세요. 원 요청과 메모는 보존합니다.')
        self._call(lambda:self.client.document_command(**request),queued,failed)

    def _reject_pending(self,error):
        self.pending=None;self.invalidate()
        self.show_error(error,'요청이 거절되어 등록되지 않았습니다. 적용하지 않았으며 전달 메모는 보존합니다.')

    def _resolve_rejected_retry(self,rejection):
        pending=self.pending
        def unknown(error):
            self.show_error(error,'원 요청의 등록 여부가 아직 미확정입니다. 같은 요청으로 복구하세요. 미적용을 추정하지 않습니다.')
        def found(status):
            self.pending['unconfirmed']=False;self.timer.start();self.handle_status(status)
        def missing(error):
            if not (isinstance(error,WorkbenchHTTPError) and error.code==404
                    and error.service_message=='Native command ID has not been registered in this service'):
                unknown(error);return
            def same_service(target):
                if pending.get('service_session_id') and target.get('service_session_id')==pending['service_session_id']:
                    self.target=target;self._reject_pending(rejection)
                else:unknown('서비스가 바뀌어 이전 명령의 미등록을 확정할 수 없습니다.')
            self._call(lambda:self.client.document_read(pending['request']['identifier']),same_service,unknown)
        # An absent status alone is inconclusive; this follows an exact-POST rejection.
        self._call(lambda:self.client.command_status(pending['id']),found,missing)

    def recover_pending(self):
        if self.pending and self.pending.get('unconfirmed'):self._send_pending()
        else:self.poll()

    def handle_status(self,status):
        if not self.pending or status.get('command_id')!=self.pending['id']:return
        state=status.get('state')
        if state not in ('SUCCEEDED','FAILED','CANCELLED','INTERRUPTED'):return
        current=self.pending;self.pending=None;self.timer.stop()
        if state!='SUCCEEDED':
            self.invalidate()
            self.detail.setPlainText(json.dumps(status,ensure_ascii=False,indent=2))
            label={'FAILED':'실패','CANCELLED':'취소','INTERRUPTED':'중단'}[state]
            cause=status.get('outcome',{}).get('error') or status.get('error') or ''
            self.note.setText('요청 '+label+': 원 결과와 오류를 보존했습니다. 다시 적용하지 않았습니다.\n'+law_error_text(cause));return
        owner_response=status.get('outcome',{}).get('result',{})
        payload=owner_response.get('result',{})
        if status.get('final_generation') is not None:self.target['generation']=status['final_generation']
        self.detail.setPlainText(json.dumps(payload,ensure_ascii=False,indent=2))
        review=payload.get('review') or (payload.get('assignment') or {}).get('review')
        if isinstance(review,dict):self.show_review(review)
        current['done'](payload,current['id']);self.update_actions()

    def show_review(self,review):
        mapping=review.get('mapping',[]);self.summary.setRowCount(len(mapping))
        for row,entry in enumerate(mapping):
            for column,key in enumerate(('coefficient','source_value','source_unit','target_value','target_unit')):
                value=entry.get(key,'');text=format(value,'.10g') if type(value) in (int,float) else str(value)
                item=QTableWidgetItem(text);item.setToolTip('저장된 재료 계수에서 변환한 값')
                self.summary.setItem(row,column,item)
        self.summary_title.setText('검토 완료: 저장 재료 → FELUPE 시편 (mm, MPa, s)' if review.get('status')=='READY_FOR_EXPLICIT_APPLY'
            else '적용 차단:\n'+law_error_text(review.get('errors',[])))

    def poll(self):
        if self.pending and not self._busy:
            cid=self.pending['id']
            def failed(error):
                self.timer.stop();self.pending['unconfirmed']=True
                self.show_error(error,'적용 여부를 확인하지 못했습니다. 「같은 요청으로 복구」를 눌러 확인하세요. 미적용을 추정하지 않습니다.')
            self._call(lambda:self.client.command_status(cid),self.handle_status,failed)

    def read_assignment(self):
        def done(payload,cid):
            drafts=payload.get('drafts',[])
            if drafts and not self.raw.document().isModified():
                raw=drafts[-1]['raw']
                text=raw.get('editor_raw_text') if isinstance(raw,dict) and set(raw)=={'editor_raw_text'} else None
                self.raw.setPlainText(text if isinstance(text,str) else json.dumps(raw,ensure_ascii=False,indent=2))
            self.note.setText('저장 할당·초안을 읽었습니다. 현재 미저장 메모는 덮어쓰지 않습니다. source·solver 실행은 없습니다.')
        self.submit('pre.fem.law_read',{},done)

    def save_draft(self,checked=False,*,after=None):
        text=self.raw.toPlainText()
        try:
            raw=json.loads(text)
            if not isinstance(raw,dict):raw={'editor_raw_text':text}
        except ValueError:
            raw={'editor_raw_text':text} # Save literal unfinished JSON; never parse it as a coefficient/card.
        def done(payload,cid):
            if self.raw.toPlainText()==text:self.raw.document().setModified(False)
            self.note.setText('전달 초안만 저장했습니다. 적용·계산하지 않았습니다.')
            if after and not self.raw.document().isModified():after()
        self.submit('pre.fem.law_save',{'raw':raw},done)

    def preview(self):
        source={'document_id':self.material['id'],'saved_revision':self.material['saved_revision'],
                'input_sha256':canonical_hash(self.material['draft'])}
        settings=default_settings();settings['boundary']['mode']=self.boundary.currentData()
        # Public specimen has origin 0. A translated native mesh is an explicit
        # unsupported GUI setting here, not an automatically guessed frame.
        options={'solver':settings['solver'],'boundary':settings['boundary'],'purpose':'CONSTITUTIVE_SPECIMEN'}
        def done(payload,cid):
            self.review=payload['review'];self.preview_command=cid
            if self.review['status']=='READY_FOR_EXPLICIT_APPLY':self.note.setText('검토 준비됨 · 아직 적용하지 않았습니다.')
            else:
                self.note.setText('검토가 차단되어 적용할 수 없습니다. 아래 조건을 수정한 뒤 다시 검토하세요.')
                self.detail.appendPlainText(json.dumps(self.review['errors'],ensure_ascii=False,indent=2))
        self.submit('pre.fem.law_preview',{'source':source,'options':options},done)

    def apply(self):
        if not self.review:return
        if QMessageBox.question(self,'명시 적용','표시한 저장 법칙·계수·초기 상태를 이 해석/영역에 적용할까요? 계산은 하지 않습니다.')!=QMessageBox.StandardButton.Yes:return
        self.submit('pre.fem.law_apply',{'review_command_id':self.preview_command},
            lambda p,c:self.note.setText('native transaction에 적용했습니다. 기존 탄성 카드 우회 실행은 차단됩니다.'))

    def freeze(self):
        def done(payload,cid):
            self.frozen=deepcopy(payload['simulation_draft']);self.note.setText('FE 입력을 고정했습니다. 별도 Simulation에서 명시 계산하세요.')
        self.submit('pre.fem.law_freeze',{},done)

    def open_simulation(self):
        if self.frozen is None:return
        frozen=deepcopy(self.frozen)
        def done(document):
            from .simulation_window import SimulationWindow
            window=SimulationWindow(self.client,auto_open=False);window._opened(document)
            self._children.append(window);window.show();self.note.setText('기존 Simulation owner를 열었습니다. 계산은 자동 시작하지 않습니다.')
        self._call(lambda:self.client.document_open(kind='simulation',title=self.material['title']+' · FE 시편',draft=frozen),done)

    def _finish_close(self):
        self._closed=True;self.timer.stop();super().reject()

    def reject(self):
        if self.pending or self._busy:
            self.note.setText('명령의 적용 여부를 먼저 동일 명령으로 재조회하세요. Esc/닫기로 적용을 취소했다고 표시하지 않습니다.');return
        if self.raw.document().isModified():
            answer=QMessageBox.question(self,'전달 초안 보존','미저장 전달 원문을 저장하고 닫을까요?',
                QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
            if answer==QMessageBox.StandardButton.Save:self.save_draft(after=self._finish_close);return
            if answer!=QMessageBox.StandardButton.Discard:return
        self._finish_close()
