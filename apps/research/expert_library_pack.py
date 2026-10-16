"""Official bundled document selection over the current Client; no local owner."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QThreadPool
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QPlainTextEdit, QDialogButtonBox)

COLLECTIONS = {'public':'공개 자료', 'project-current':'현재 프로젝트 자료',
    'pre-freecad-fem':'FreeCAD FEM', 'mesh-gmsh':'Gmsh 메시', 'post-paraview':'ParaView 결과',
    'materials':'재료', 'testing':'시험'}


def collection_label(name):
    return COLLECTIONS.get(name, name)


def official_markdown(payload):
    """Only the two verified bundled Markdown originals have a known format."""
    from caelab.research_knowledge_pack import load_pack
    try:
        pack=load_pack()
        assets={row['path']:row['sha256'] for row in pack['assets']}
        return bool(payload.get('segments')) and all(row.get('content_kind')=='source_text' for row in payload['segments']) and any(row['availability']=='BUNDLED' and Path(row['file']).suffix.lower() in {'.md','.markdown'}
                   and assets[row['file']]==payload.get('sha256') for row in pack['documents'])
    except (OSError,ValueError,KeyError,TypeError):return False


class OfficialDocumentsDialog(QDialog):
    """Review pinned text/licenses and existing jobs before explicit ingestion."""
    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client=client
        self._closed=self._busy=False
        self._workers=[];self.rows={};self.jobs={};self.results={};self.references=[]
        self._queue=[];self._active=None;self.pack=None
        self.setWindowTitle('공식 자료 가져오기')
        self.resize(940,690);self.setMinimumSize(700,500)
        layout=QVBoxLayout(self)
        self.notice=QLabel('함께 제공된 원문과 배포 조건을 확인해 현재 보관함에 가져옵니다. 외부 다운로드는 하지 않습니다.')
        self.notice.setWordWrap(True);layout.addWidget(self.notice)
        self.table=QTreeWidget();self.table.setHeaderLabels(['자료','문서 범위','상태'])
        self.table.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.table.header().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.table.header().setSectionResizeMode(2,QHeaderView.ResizeMode.ResizeToContents)
        self.table.currentItemChanged.connect(self.show_details)
        self.table.itemChanged.connect(self.controls)
        layout.addWidget(self.table,3)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);layout.addWidget(self.details,2)
        actions=QHBoxLayout()
        self.import_button=QPushButton('선택 자료 가져오기');self.import_button.setProperty('appearanceRole','primary')
        self.import_button.clicked.connect(self.start_import)
        self.check_button=QPushButton('기존 작업 확인');self.check_button.clicked.connect(self.refresh_jobs)
        source_details=QPushButton('출처 상세…');source_details.clicked.connect(self.source_details)
        actions.addWidget(self.import_button);actions.addWidget(self.check_button);actions.addWidget(source_details);actions.addStretch()
        layout.addLayout(actions)
        self.message=QLabel('자료 목록을 확인하는 중…');self.message.setWordWrap(True);layout.addWidget(self.message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.return_button=buttons.addButton('가져온 문헌 선택',QDialogButtonBox.ButtonRole.AcceptRole)
        self.return_button.setProperty('appearanceRole','primary')
        self.return_button.clicked.connect(self.choose_imported)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('문헌 목록으로 돌아가기')
        buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.poll=QTimer(self);self.poll.setInterval(300);self.poll.timeout.connect(self.refresh_jobs)
        QTimer.singleShot(0,self.load)

    def call(self,function,accepted):
        if self._busy or self._closed:return False
        from .expert_window import _Call
        self._busy=True;self.controls()
        worker=_Call(function);self._workers.append(worker)
        def done(value,error):
            self._workers.remove(worker);self._busy=False
            if self._closed:return
            if error:
                self._queue=[];self.poll.stop()
                self.message.setText('처리 결과를 확인하지 못했습니다. 기존 작업 확인으로 같은 요청을 확인하세요.')
                self.message.setToolTip(str(error))
            else:
                try:accepted(value)
                except Exception as failure:
                    self._queue=[];self.poll.stop()
                    self.message.setText('자료를 확인하지 못했습니다. 기존 작업과 원문 상태를 확인하세요.')
                    self.message.setToolTip(str(failure))
            self.controls()
        worker.signals.finished.connect(done,Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker);return True

    def controls(self):
        ready=not self._busy and self.pack is not None and not self._active and not self._queue
        self.import_button.setEnabled(ready);self.table.setEnabled(not self._busy and not self._active)
        self.check_button.setEnabled(not self._busy and self.pack is not None)
        if hasattr(self,'return_button'):
            self.return_button.setEnabled(not self._busy and bool(self.selected_imported()))

    def read_jobs(self,pack,digest):
        jobs=self.client.request('/api/workbench')['jobs']
        ids={'official-pack-'+entry['id']+'-'+digest[:16] for entry in pack['documents']}
        results={job['id']:self.client.result(job['id']) for job in jobs
                 if job.get('request_id') in ids and job.get('operation')=='knowledge.ingest' and job['state']=='SUCCEEDED'}
        return jobs,results

    def load(self):
        def read():
            from caelab.research_knowledge_pack import PACK,load_pack
            pack=load_pack();digest=sha256(PACK.read_bytes()).hexdigest()
            return pack,digest,*self.read_jobs(pack,digest)
        def loaded(value):
            self.pack,self.digest,jobs,results=value
            for entry in self.pack['documents']:
                bundled=entry['availability']=='BUNDLED'
                item=QTreeWidgetItem([entry.get('library_title',entry['title']),
                    '제공 원문' if bundled else '공식 링크만 제공','확인 전' if bundled else '본문 미포함'])
                item.setData(0,Qt.ItemDataRole.UserRole,entry['id']);item.setToolTip(0,entry['title'])
                if bundled:
                    item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0,Qt.CheckState.Checked)
                else:item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsUserCheckable)
                self.table.addTopLevelItem(item);self.rows[entry['id']]=(entry,item)
            self.table.setCurrentItem(self.table.topLevelItem(0))
            self.show_jobs(jobs,results)
        return self.call(read,loaded)

    def request_id(self,entry):
        # Same contract as the shipped CLI; an old import is never uploaded again.
        return 'official-pack-'+entry['id']+'-'+self.digest[:16]

    def show_details(self,*_):
        item=self.table.currentItem()
        if item is None:return
        entry=self.rows[item.data(0,Qt.ItemDataRole.UserRole)][0]
        version=entry['document_version']
        if len(version)>24:version='보존된 문서 판본' if entry['availability']=='BUNDLED' else '판본 확인 필요'
        installed=entry.get('installed_version_observed') or '확인 전'
        if entry['id']=='impact-inievo':installed='문서와 실행본의 대응 확인 필요'
        scope={'freecad-fem':'FEM 작업 순서 원문. 그림과 연결된 문서는 미포함. 설치판과의 일치는 확인이 필요합니다.',
            'freecad-gmsh-mesh':'FreeCAD의 Gmsh 메시 명령 원문. 그림과 연결된 예제는 미포함. Gmsh 전체 매뉴얼이 아닙니다.',
            'paraview-basic':'튜토리얼 원문. 그림과 데이터셋은 미포함. 문서와 설치판의 버전이 다릅니다.'}.get(entry['id'],
            '공식 링크만 제공합니다. 본문을 보관하거나 읽은 자료가 아닙니다.')
        self.details.setPlainText('\n'.join([entry.get('library_title',entry['title']),
            '문서 버전: '+version,'설치본: '+str(installed),
            '배포 조건: '+(entry['license']['name'] if entry['availability']=='BUNDLED' else '본문 배포 허가 미확인'),
            '출처: '+entry['application']+' 공식 문서',
            '원문 범위: '+scope]))
        self.details.setToolTip('원문에 기록된 버전: '+entry['document_version']+'\n'+
            entry.get('read_scope',entry.get('scope',''))+'\n'+'\n'.join(entry.get('limitations',[])))

    def source_details(self):
        from PySide6.QtWidgets import QMessageBox
        item=self.table.currentItem()
        if item is None:return
        entry=self.rows[item.data(0,Qt.ItemDataRole.UserRole)][0]
        QMessageBox.information(self,'출처와 배포 조건','\n'.join([entry['title'],
            '원문 주소: '+entry['official_url'],'문서 판본: '+entry['document_version'],
            '배포 조건: '+entry['license']['name'],
            '배포 근거: '+entry['license'].get('basis_url',entry['license'].get('url','')),
            '원문 범위: '+entry.get('read_scope',entry.get('scope','')),
            *entry.get('limitations',[])]))

    def readable(self,entry,result):
        if result is None or entry['availability']!='BUNDLED':return False
        expected=next(v for v in self.pack['assets'] if v['path']==entry['file'])
        return (result.get('sha256')==expected['sha256'] and not result.get('failed_segments')
                and bool(result.get('segments_read')))

    def selected_imported(self):
        refs=[]
        for entry,item in self.rows.values():
            if item.checkState(0)!=Qt.CheckState.Checked:continue
            job=self.jobs.get(self.request_id(entry));result=self.results.get(job['id']) if job else None
            if self.readable(entry,result):refs.append({key:result[key] for key in ('document_id','revision')})
        return refs

    def choose_imported(self):
        self.references=self.selected_imported()
        if self.references:self.accept()

    def show_jobs(self,jobs,results):
        self.results=results
        self.jobs={job.get('request_id'):job for job in jobs if job.get('operation')=='knowledge.ingest'}
        pending=False
        for entry,item in self.rows.values():
            job=self.jobs.get(self.request_id(entry))
            if job is None:continue
            state=job['state']
            labels={'SUCCEEDED':'보관 완료' if self.readable(entry,results.get(job['id'])) else '원문 추출 확인 필요',
                'FAILED':'가져오기 실패','CANCELLED':'취소됨',
                'REJECTED':'접수 거절',
                'INTERRUPTED':'이전 작업 확인 필요','PARTIAL_FAILURE':'일부 처리 실패',
                'CLEANUP_PENDING':'작업 종료 확인 필요'}
            item.setText(2,labels.get(state,'가져오는 중'))
            item.setToolTip(2,str(job.get('error') or ''))
            if state not in {'SUCCEEDED','FAILED','CANCELLED','INTERRUPTED','PARTIAL_FAILURE','CLEANUP_PENDING','REJECTED'}:pending=True
        self.message.setText('보관된 자료는 다시 반입하지 않습니다. 가져온 원문은 문헌 목록에서 읽고 선택하세요.')
        if pending:self.poll.start()
        else:self.poll.stop()

    def refresh_jobs(self):
        if self._busy:return
        active=self._active
        def read():
            jobs,results=self.read_jobs(self.pack,self.digest)
            job=next((j for j in jobs if active and j.get('request_id')==self.request_id(self.rows[active][0])),None)
            return jobs,results,job
        def checked(value):
            jobs,results,job=value;self.show_jobs(jobs,results)
            if active and job:
                if job['state']=='SUCCEEDED':
                    entry=self.rows[active][0]
                    result=results.get(job['id'])
                    if not self.readable(entry,result):
                        self._active=None;self._queue=[]
                        self.rows[active][1].setText(2,'원문 추출 확인 필요')
                        self.message.setText('일부 본문을 확인하지 못했습니다. 기존 작업과 추출 범위를 확인하세요.');return
                    self.references.append({k:result[k] for k in ('document_id','revision')})
                    self._active=None;QTimer.singleShot(0,self.next_import)
                elif job['state'] in {'FAILED','CANCELLED','INTERRUPTED','PARTIAL_FAILURE','CLEANUP_PENDING','REJECTED'}:
                    self._active=None;self._queue=[]
                    self.message.setText('가져오지 못한 자료가 있습니다. 완료한 원문과 기존 작업은 유지됩니다.')
            elif active:
                self._active=None;self._queue=[]
                self.message.setText('접수된 작업을 찾지 못했습니다. 같은 자료를 다시 선택하면 같은 요청으로 확인합니다.')
        return self.call(read,checked)

    def start_import(self):
        self._queue=[name for name,(entry,item) in self.rows.items()
            if entry['availability']=='BUNDLED' and item.checkState(0)==Qt.CheckState.Checked]
        self.next_import()

    def next_import(self):
        if self._closed or self._active or self._busy:return
        if not self._queue:self.controls();return
        name=self._queue.pop(0);entry=self.rows[name][0];request_id=self.request_id(entry)
        prior=self.jobs.get(request_id)
        if prior:
            if prior['state']=='SUCCEEDED' and self.readable(entry,self.results.get(prior['id'])):
                QTimer.singleShot(0,self.next_import);return
            self._queue=[];self._active=name;self.refresh_jobs();return
        self._active=name
        pending=getattr(self.client,'_official_import_requests',None)
        if pending is None:pending=self.client._official_import_requests={}
        def submit():
            # Check again immediately before upload; another dialog may have imported.
            jobs=self.client.request('/api/workbench')['jobs']
            existing=next((job for job in jobs if job.get('request_id')==request_id),None)
            if existing:return existing
            if request_id not in pending:
                from caelab.research_knowledge_pack import PACK,load_pack
                load_pack()  # Revalidate originals AND all license notices before mutation.
                source=PACK.parent/entry['file'];raw=source.read_bytes()
                expected=next(v for v in self.pack['assets'] if v['path']==entry['file'])
                if sha256(raw).hexdigest()!=expected['sha256']:raise ValueError('공식 원문이 목록과 다릅니다.')
                upload=self.client.upload(source.name,raw)
                pending[request_id]={'data_id':upload['id'],'collection':entry['collection'],
                    'metadata':{'title':entry.get('library_title',entry['title']),'official_document':deepcopy(entry)}}
            return self.client.submit('knowledge.ingest',deepcopy(pending[request_id]),request_id=request_id)
        def submitted(job):
            self.jobs[request_id]=job;self.poll.start()
            self.message.setText('선택한 원문을 현재 보관함에 가져오는 중…')
        if not self.call(submit,submitted):self._active=None

    def done(self,result):
        self._closed=True;self.poll.stop()
        for worker in self._workers:worker.abandon()
        super().done(result)
