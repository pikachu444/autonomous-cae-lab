"""Original saved/ack/raw reader and explicit current-owner resume dialog.

No fake RecoveryReadDialog identity, no old recovery/discard calls. Commands use
small reviewed buffer tokens; original arrays are read only through existing
Data/owner archive readers. Existing editors render the returned raw packet.
"""
from copy import deepcopy
from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from shiboken6 import isValid
from caelab.portable_recovery_resume import buffer_token
from .connection_window_recovery import stamp, STATE


def _at(draft,path):
    try:
        for key in path: draft=draft[key]
        return draft
    except (KeyError,IndexError,TypeError): return '기록 없음'


def _text(value):
    if value is None: return '미지정'
    if isinstance(value,(dict,list)): return str(value)
    return str(value)


def _table(headings):
    table=QTableWidget(0,len(headings)); table.setHorizontalHeaderLabels(headings)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return table


def _fill(table,rows):
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c,value in enumerate(row):
            item=QTableWidgetItem(_text(value)); item.setToolTip(_text(value)); table.setItem(r,c,item)


def domain_rows(document):
    """Known engineering fields only; never dump internal identities into menus."""
    draft=document['draft']; kind=document['kind']; rows=[]
    if kind=='material':
        settings=draft.get('settings',{})
        for key,label in (('model','재료 법칙'),('stress_unit','응력 단위'),('time_unit','시간 단위')):
            rows.append((label,settings.get(key,'')))
        rows.extend(('계수 '+key,value) for key,value in settings.get('parameters',{}).items())
        rows.extend(('시간 '+str(i+1),value) for i,value in enumerate(settings.get('time',[])))
        rows.extend(('변형구배 '+str(i+1),value) for i,value in enumerate(settings.get('deformation_gradient',[])))
    elif kind=='numerical':
        for row in draft.get('variables',[]):
            name=row.get('name',row.get('label','변수'))
            rows.extend((str(name)+' / '+label,row.get(key,'')) for key,label in
                (('value','값'),('lower','하한'),('upper','상한'),('unit','단위'),('active','사용')))
    else:
        for name,row in draft.get('mapping',{}).get('columns',{}).items():
            for key,label in (('column','원 열'),('unit','단위'),('component','성분'),('scale','배율'),('offset','오프셋')):
                rows.append((name+' / '+label,row.get(key,'')))
            axis=row.get('axis',{})
            rows.extend((name+' / 축 '+label,axis.get(key,'')) for key,label in
                (('name','이름'),('column','열'),('unit','단위'),('scale','배율'),('offset','오프셋')))
            calibration=row.get('calibration',{})
            rows.extend((name+' / 보정 '+key,calibration[key]) for key in
                ('a','b','x0','input_unit','output_unit','coefficient_input_unit','x0_unit') if key in calibration)
        rows.extend(('시험 '+key,value) for key,value in draft.get('test_metadata',{}).items())
    return rows


def cell_label(cell, document):
    path=cell['field_path']
    if len(path)>=3 and path[:2]==['settings','parameters']:
        return '재료 계수 / '+str(path[2])
    if len(path)>=4 and path[:2]==['mapping','columns']:
        channel={'stress':'응력','strain':'변형률','time':'시간'}.get(path[2],str(path[2]))
        field={'column':'원 열','unit':'단위','component':'성분','scale':'배율','offset':'오프셋'}.get(path[-1],str(path[-1]))
        return channel+' / '+field
    if len(path)>=3 and path[0]=='variables' and document:
        variable=document['draft'].get('variables',[])
        if type(path[1]) is int and 0<=path[1]<len(variable):
            name=variable[path[1]].get('name','변수')
            field={'value':'값','lower':'하한','upper':'상한','unit':'단위','active':'사용'}.get(path[2],str(path[2]))
            return str(name)+' / '+field
    pos=cell.get('position',{}); label=pos.get('table','입력')
    if type(pos.get('row')) is int: label+=' '+str(pos['row']+1)+'행'
    if type(pos.get('column')) is int: label+=' '+str(pos['column']+1)+'열'
    return label


class PortableRecoveryReadDialog(QDialog):
    def __init__(self,client,document,records,*,current,restore,parent=None):
        super().__init__(parent)
        self.client=client; self.document=deepcopy(document); self.records=deepcopy(records)
        self.current=current; self.restore=restore
        self._busy=False; self._worker=None; self._closed=False; self._serial=0
        self.layers=self.saved=self.pending=None
        self.setWindowTitle('이동 사본의 원 편집 자료'); self.resize(960,680)
        layout=QVBoxLayout(self)
        title=QLabel(document['title']); title.setProperty('appearanceRole','section'); title.setWordWrap(True)
        layout.addWidget(title)
        note=QLabel('원 저장본·당시 반영 문서·미확정 원문을 따로 읽습니다. 원 복구·삭제 권한은 없습니다.')
        note.setWordWrap(True); layout.addWidget(note)
        self.choice=QComboBox()
        for row in records:
            self.choice.addItem(stamp(row.get('created_utc'))+' / '+STATE.get(row['state'],'원문 확인 필요'))
        layout.addWidget(self.choice)
        self.tabs=QTabWidget(); layout.addWidget(self.tabs,1)
        self.cells=_table(['원문 위치','원 저장값','당시 반영값','미확정 원문'])
        self.tabs.addTab(self.cells,'미확정 입력')
        self.context=_table(['입력 항목','원 저장값','당시 반영값'])
        self.tabs.addTab(self.context,'문서와 단위')
        self.receipts=_table(['문서','관련 저장 결과','시도 결과'])
        self.tabs.addTab(self.receipts,'부분 저장 기록')
        source_page=QWidget(); source_layout=QVBoxLayout(source_page)
        self.source_choice=QComboBox(); source_layout.addWidget(self.source_choice)
        self.source_button=QPushButton('선택한 원 입력 파일 읽기'); source_layout.addWidget(self.source_button)
        self.source_text=QPlainTextEdit(); self.source_text.setReadOnly(True); source_layout.addWidget(self.source_text)
        self.tabs.addTab(source_page,'원 측정 자료')
        result_page=QWidget(); result_layout=QVBoxLayout(result_page)
        self.job_choice=QComboBox(); result_layout.addWidget(self.job_choice)
        self.job_button=QPushButton('선택한 원 결과 읽기'); result_layout.addWidget(self.job_button)
        self.result_table=_table(['배열 / 항목','원값']); result_layout.addWidget(self.result_table)
        self.tabs.addTab(result_page,'원 결과')
        self.message=QLabel(); self.message.setWordWrap(True); layout.addWidget(self.message)
        buttons=QHBoxLayout(); layout.addLayout(buttons)
        self.resume_button=QPushButton('현재 편집기로 이어가기…')
        self.resume_button.setProperty('appearanceRole','primary')
        self.close_button=QPushButton('닫기')
        buttons.addWidget(self.resume_button); buttons.addWidget(self.close_button)
        self.choice.currentIndexChanged.connect(self.read)
        self.source_button.clicked.connect(self.read_source); self.job_button.clicked.connect(self.read_result)
        self.resume_button.clicked.connect(self.resume); self.close_button.clicked.connect(self.reject)
        self._buttons(); QTimer.singleShot(0,self.read)

    def _record(self):
        i=self.choice.currentIndex()
        return self.records[i] if 0<=i<len(self.records) else None

    def _buttons(self):
        ok=not self._busy
        ready=self.layers and self.layers['state']=='STORED' and self.layers['verification']=='VERIFIED'
        self.choice.setEnabled(ok and self.pending is None)
        self.resume_button.setEnabled(bool(ok and ready))
        self.resume_button.setText('같은 이어가기 요청 확인 / 재시도' if self.pending else '현재 편집기로 이어가기…')
        self.close_button.setEnabled(ok)
        self.source_button.setEnabled(ok and self.source_choice.count()>0)
        self.job_button.setEnabled(ok and self.job_choice.count()>0)

    def _call(self,function,after):
        if self._busy or self._closed: return False
        from .data_window import _Read
        self._busy=True; self._buttons(); serial=self._serial
        worker=self._worker=_Read(function)
        def done(value,error):
            if not isValid(self) or self._closed or serial!=self._serial: return
            self._busy=False; self._worker=None
            try:
                if error: raise ValueError(str(error))
                after(value)
            except (ValueError,KeyError,TypeError,RuntimeError) as failure:
                self.message.setText('원문과 현재 입력을 유지합니다.\n'+str(failure))
                self.message.setToolTip(str(failure))
            self._buttons()
        worker.signals.finished.connect(done,Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker); return True

    def read(self,*_):
        record=self._record()
        if record is None or self._busy: return
        self.layers=self.saved=None; self.pending=None; self._serial+=1
        aid=record['selection']['archive_id']
        def load():
            layers=self.client.portable_recovery_read(aid)
            saved=None
            if layers['verification']=='VERIFIED' and layers['capsule']['acknowledged'].get('saved_reference'):
                saved=self.client.portable_recovery_read(aid,facet='saved')['document']
            return layers,saved
        def loaded(payload):
            self.layers,self.saved=payload
            cap=self.layers['capsule']; ack=cap['acknowledged']; doc=ack.get('document')
            rows=[]
            for cell in cap['raw']['cells']:
                location=cell_label(cell,doc)
                rows.append((location,_at((self.saved or {}).get('draft',{}),cell['field_path']),
                    _at((doc or {}).get('draft',{}),cell['field_path']),cell['raw_text']))
            _fill(self.cells,rows)
            saved=dict(domain_rows(self.saved)) if self.saved else {}
            _fill(self.context,[(label,saved.get(label,'기록 없음'),value) for label,value in domain_rows(doc)] if doc else [])
            titles={s['document_id']:s.get('title','관련 문서') for s in ack.get('saved_sources',[])}
            # Receipt response documents contain the owner titles even on a
            # partial save. Do not substitute a different Plan's state.
            for r in ack.get('owner_commands',[]):
                d=r.get('snapshot',{}).get('response',{}).get('document')
                if isinstance(d,dict): titles[d['id']]=d.get('title','관련 문서')
            titles[cap['identity']['document_id']]=(doc or self.document)['title']
            result=[]
            for receipt in ack.get('related_save_receipts',[]):
                for i,t in enumerate(receipt['snapshot']['targets']):
                    identity=t['identity']; name=titles.get(identity['document_id'],
                        ('재료' if identity['kind']=='material' else '계획')+' '+str(i+1))
                    states={'SAVED':'저장됨','FAILED':'저장 실패','BLOCKED':'미적용 입력 / 보류','PENDING':'미결'}
                    result.append((name,states.get(t['state'],t['state']),
                        ' / '.join(states.get(a.get('state'),a.get('state','미결')) for a in t.get('attempts',[])) or '시도 없음'))
            _fill(self.receipts,result)
            self.source_choice.clear(); self.job_choice.clear()
            for i,source in enumerate(ack.get('data_inputs',[])):
                self.source_choice.addItem(source.get('receipt',{}).get('name','원 입력 '+str(i+1)),source['data_id'])
            for i,job in enumerate(ack.get('jobs',[])):
                self.job_choice.addItem('원 실행 '+str(i+1)+' / '+job['state_at_review'],job)
            self.source_text.clear(); self.result_table.setRowCount(0)
            self.message.setText(('당시 되돌리기 '+str(len(doc.get('_undo',[])))+'개 / 다시하기 '+str(len(doc.get('_redo',[])))+'개. '
                if doc else '당시 전체 문서가 없는 보관본입니다. 현재 문서로 대체하지 않습니다. ')+
                '원문을 읽는 것만으로 적용·저장·계산하지 않습니다.')
        self._call(load,loaded)

    def read_source(self):
        source=self.source_choice.currentData(); row=self._record()
        if source and row:
            self._call(lambda:self.client.portable_recovery_read(row['selection']['archive_id'],facet='source-preview',
                selection={'data_id':source}),lambda result:self.source_text.setPlainText(result['text']))

    def read_result(self):
        job=self.job_choice.currentData(); row=self._record()
        if not job or not row: return
        def loaded(value):
            result=value.get('result'); rows=[('원 상태',value['job']['state_at_review'])]
            if result:
                # Existing read_result already verified every array. This is a
                # read-only table, not an evaluator or reconstructed success.
                for name,response in result.get('responses',{}).items():
                    rows.append((name+' / 단위',response.get('unit','')))
                    rows.append((name+' / 성분',response.get('component','')))
                    for axis in response.get('axes',[]):
                        rows.append((name+' / '+axis.get('name','축')+' ['+axis.get('unit','')+']',axis.get('values')))
                    data=response.get('values')
                    if hasattr(data,'tolist'): data=data.tolist()
                    rows.append((name+' / 원값',data))
                for key,array in result.get('arrays',{}).items():
                    data=array.tolist() if hasattr(array,'tolist') else array
                    rows.append((key,data))
                for key in ('message','error','status','units'):
                    if key in result: rows.append((key,result[key]))
            else: rows.append(('결과','당시 발행한 결과 없음'))
            _fill(self.result_table,rows)
        self._call(lambda:self.client.portable_recovery_read(row['selection']['archive_id'],facet='job',
            selection={'job_id':job['job_id'],'include_result':job['result_at_review']=='PUBLISHED'}),loaded)

    def resume(self):
        if self._busy or not self.layers: return False
        if self.pending is not None:
            try: return self._send_pending()
            except (ValueError,RuntimeError) as error:
                self.message.setText(str(error)); return False
        try:
            identity,raw=self.current(); token=buffer_token(raw)
        except (ValueError,RuntimeError) as error:
            self.message.setText(str(error)); return False
        aid=self._record()['selection']['archive_id']
        def reviewed(review):
            current_identity,current_raw=self.current()
            if identity!=current_identity or token!=buffer_token(current_raw):
                raise ValueError('검토 중 현재 편집이 바뀌었습니다.')
            answer=QMessageBox.question(self,'현재 사본에서 이어가기',
                '선택한 원문의 당시 반영 입력을 현재 사본에 명시 적용하고, 미확정 셀은 편집기에만 복구합니다.\n'
                '현재 편집기 내용을 바꿀까요? 원 복구·삭제 권한은 사용하지 않으며 계산·저장은 시작하지 않습니다.\n'
                '복구 후 닫을 때는 현재 사본의 「편집 원문 보관」을 사용하세요.',
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)
            if answer!=QMessageBox.StandardButton.Yes: return
            self.pending=deepcopy(review); self._send_pending()
        return self._call(lambda:self.client.portable_recovery_preview(aid,target_identity=identity,buffer=token),reviewed)

    def _send_pending(self):
        review=deepcopy(self.pending)
        identity,raw=self.current(); token=buffer_token(raw)
        if token!=review['buffer'] or identity!=review['target_identity']:
            raise ValueError('현재 편집이 바뀌었습니다. 이전 요청을 새 편집 원문으로 재사용하지 않습니다.')
        def resumed(packet):
            live,raw=self.current()
            if (live!=review['target_identity'] or buffer_token(raw)!=review['buffer']
                    or packet.get('state')!='BUFFER_READY' or packet.get('archive_id')!=review['archive_id']
                    or packet.get('capsule_sha256')!=review['capsule_sha256']
                    or packet.get('current_command_id')!=review['command_id']):
                raise ValueError('늦게 도착한 응답을 현재 편집기에 덮어쓰지 않았습니다.')
            self.restore(packet); self.pending=None; self.accept()
        return self._call(lambda:self.client.portable_recovery_resume(review,approved=True,overwrite_approved=True,
            live_buffer=token,command_id=review['command_id']),resumed)

    def reject(self):
        if self._busy: return
        self._closed=True; self._serial+=1; super().reject()

    def closeEvent(self,event):
        if self._busy: event.ignore(); return
        self._closed=True; self._serial+=1; super().closeEvent(event)
