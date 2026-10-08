"""Conversation and system-linking workspaces for the native design review."""
from __future__ import annotations
import copy
import html
import json
from pathlib import Path
import uuid

from PySide6.QtCore import Qt, Signal, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QPen, QBrush, QPainter, QFont, QPainterPath
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QSplitter,QLabel,QTreeWidget,
    QTreeWidgetItem,QTabWidget,QScrollArea,QFrame,QPushButton,QPlainTextEdit,QTextBrowser,
    QComboBox,QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QGraphicsView,
    QGraphicsScene,QGraphicsRectItem,QGraphicsSimpleTextItem,QGraphicsPathItem,
    QFileDialog,QMessageBox,QDialog,QDialogButtonBox,QFormLayout,QListWidget,QInputDialog)

ISSUES=[('root','충격시험과 해석의 피크 차이'),('rate','속도 의존 재료 응답'),('contact','접촉·구속과 지그 영향'),('signal','계측·필터·시간 정렬'),('evidence','추가 근거와 구분 실험')]
COLORS={'진행자':'#476b84','재료 전문가':'#326c9b','시험 전문가':'#8a6142','수치해석 전문가':'#516c52','사용자':'#66528b'}
ROLES=list(COLORS)

def section(text):
    w=QLabel(text);w.setProperty('section',True);return w

def panel(title):
    w=QWidget();l=QVBoxLayout(w);l.setContentsMargins(0,0,0,0);l.setSpacing(5);l.addWidget(section(title));return w,l

def default_expert(doc):
    d=copy.deepcopy(doc)
    d.setdefault('name','충격 응답 차이 원인 검토')
    d.setdefault('mode','관찰');d.setdefault('paused',False);d.setdefault('selected_message','m4');d.setdefault('draft','')
    d.setdefault('scope','공개 자료와 이 세션에 직접 추가한 관측. 회사 파일 외부 전송 없음.')
    d.setdefault('topic','충격 응답의 차이를 구분하는 공동 검토')
    d.setdefault('issues',ISSUES)
    d.setdefault('messages',[
      {'id':'m1','role':'사용자','issue':'root','text':'시험과 해석의 최대 하중 차이가 약 18%입니다. 해석의 초기 강성은 비슷하지만 피크 이후 하중이 더 빨리 떨어집니다. 재료, 접촉, 신호 처리 중 무엇부터 구분해야 할까요?','evidence':[]},
      {'id':'m2','role':'진행자','issue':'root','reply':'m1','text':'세 가지 가설을 분리하겠습니다. 같은 시험의 원 신호와 처리 신호를 먼저 대조하고, 속도 변화와 지그 조건이 피크 및 곡선 형태에 미치는 영향을 별도로 확인합니다. 현재 관측만으로 원인을 확정하지 않습니다.','evidence':['obs1']},
      {'id':'m3','role':'시험 전문가','issue':'signal','reply':'m1','text':'피크 차이를 재료 계수로 맞추기 전에 하중 채널의 영점, 필터 조건, 시간 정렬을 확인해야 합니다. 원본과 처리된 곡선을 함께 보존하고 같은 유효 구간에서 비교하는 절차를 제안합니다.','evidence':['obs1','plan1']},
      {'id':'m4','role':'재료 전문가','issue':'rate','reply':'m3','text':'초기 강성이 일치한다는 관측은 탄성계수만 바꾸는 접근을 지지하지 않습니다. 하중 속도를 달리한 시험에서 차이가 어떻게 변하는지 먼저 비교하면 속도 의존성과 접촉 가설을 구분하는 데 도움이 됩니다. 온도·형상·필터 조건을 고정한 비교가 필요합니다.','evidence':['obs1','plan1']},
      {'id':'m5','role':'수치해석 전문가','issue':'contact','reply':'m4','text':'접촉 강성·마찰·경계조건은 피크 이후 곡선에도 영향을 줄 수 있습니다. 에너지와 접촉력 이력을 함께 확인하고, 재료 계수와 접촉 계수를 동시에 맞추기 전에 한 그룹씩 변경한 평가 절차를 구성하겠습니다.','evidence':['plan1']},
    ])
    d.setdefault('evidence',[
      {'id':'obs1','title':'초기 관측 · 사용자 제공','source':'이 세션의 예제 질문','text':'설계 검토용 가상 사례. 최대 하중 차이 18%, 초기 강성 유사, 피크 이후 해석 하중이 더 빠르게 감소. 실제 시험 또는 해석 결과를 가져온 것이 아닙니다.'},
      {'id':'plan1','title':'구분 실험 계획 · 검토 초안','source':'세션 내 제안, 실행 전','text':'① 원본/처리 신호와 단위를 확인\n② 공통 시간 구간과 이벤트 정렬을 고정\n③ 속도 1×/2×, 온도·형상·필터 고정 비교\n④ 재료/접촉 변수 그룹을 분리한 DOE\n이 계획은 시연 발언에서 생성된 검토 초안이며 실제 계산은 수행되지 않았습니다.'},
    ])
    return d

class Turn(QFrame):
    selected=Signal(str)
    replied=Signal(str)
    def __init__(self,m,index,active=False,reply_label=''):
        super().__init__();self.mid=m['id'];self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f'Turn {{background:{"#edf5fc" if active else "white"}; border:1px solid {"#72a3ca" if active else "#e0e6ec"}; border-radius:3px;}}')
        l=QVBoxLayout(self);l.setContentsMargins(13,9,13,10);l.setSpacing(5)
        head=QHBoxLayout();role=QLabel(f'{m["role"]}');role.setStyleSheet(f'font-weight:600;color:{COLORS.get(m["role"],"#476b84")};');head.addWidget(role)
        info=QLabel(f'발언 {index+1}');info.setStyleSheet('color:#6c7d8c;font-size:11px');head.addWidget(info)
        if m.get('reply'):
            reply=QPushButton(reply_label+'에 대한 응답');reply.setStyleSheet('QPushButton {border:0;background:transparent;color:#3b709a;font-size:11px;padding:0;min-height:14px;}');reply.clicked.connect(lambda:self.replied.emit(m['reply']));head.addWidget(reply)
        head.addStretch();l.addLayout(head)
        body=QLabel(m['text']);body.setWordWrap(True);body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);body.setStyleSheet('line-height:1.5;font-size:13px;');l.addWidget(body)
        if m.get('evidence'):
            ev=QPushButton(f'연결된 근거 {len(m["evidence"])}개 보기');ev.setStyleSheet('QPushButton {text-align:left;border:0;background:transparent;color:#3b709a;font-size:11px;padding:0;min-height:14px;}');ev.clicked.connect(lambda:self.selected.emit(m['id']));l.addWidget(ev)
    def mousePressEvent(self,event):self.selected.emit(self.mid);super().mousePressEvent(event)

class ExpertWorkspace(QWidget):
    def __init__(self,doc,changed,open_tool):
        super().__init__();self.d=default_expert(doc);self.change=changed;self.open_tool=open_tool;self.busy=False;self.build()
    def document(self):
        if hasattr(self,'composer'):self.d['draft']=self.composer.toPlainText()
        return copy.deepcopy(self.d)
    def set_document(self,doc):
        self.d=default_expert(doc);self.rebuild()
    def rebuild(self):
        layout=self.layout()
        if layout:
            while layout.count():
                item=layout.takeAt(0)
                if item.widget():item.widget().deleteLater()
            QWidget().setLayout(layout)
        self.build()
    def build(self):
        root=QVBoxLayout(self);root.setContentsMargins(6,5,6,4);root.setSpacing(5)
        header=QHBoxLayout();title=QLabel(self.d['topic']);title.setStyleSheet('font-size:15px;font-weight:600;');header.addWidget(title);header.addStretch();tag=QLabel('설계 시연 · LLM 미연결');tag.setProperty('note',True);header.addWidget(tag);root.addLayout(header)
        split=QSplitter();root.addWidget(split,1)
        left,ll=panel('세션과 논점 지도');split.addWidget(left)
        session=QLabel(self.d.get('name','새 자문'));session.setWordWrap(True);session.setContentsMargins(7,3,7,3);ll.addWidget(session)
        self.issue_tree=QTreeWidget();self.issue_tree.setHeaderLabels(['논점','발언']);self.issue_tree.setColumnWidth(0,200);ll.addWidget(self.issue_tree,1)
        self.issue_items={};r=QTreeWidgetItem([self.d['issues'][0][1],'']);r.setData(0,Qt.ItemDataRole.UserRole,'root');self.issue_tree.addTopLevelItem(r);self.issue_items['root']=r
        for key,label in self.d['issues'][1:]:
            count=sum(m['issue']==key for m in self.d['messages']);item=QTreeWidgetItem([label,str(count)]);item.setData(0,Qt.ItemDataRole.UserRole,key);r.addChild(item);self.issue_items[key]=item
        r.setExpanded(True);self.issue_tree.itemClicked.connect(self.select_issue)
        ll.addWidget(section('참여자 · 현재 관점'))
        for role in ROLES[:-1]:
            lbl=QLabel(f'{role}  /  '+{'진행자':'논점 조정','재료 전문가':'속도·온도·재료법칙','시험 전문가':'계측·관측·재현성','수치해석 전문가':'접촉·수렴·에너지'}[role]);lbl.setStyleSheet(f'color:{COLORS[role]};padding:4px 7px;');ll.addWidget(lbl)
        self.phase=QLabel();self.phase.setWordWrap(True);self.phase.setContentsMargins(7,8,7,8);ll.addWidget(self.phase)
        center=QWidget();cl=QVBoxLayout(center);cl.setContentsMargins(0,0,0,0);cl.setSpacing(5);split.addWidget(center)
        self.tabs=QTabWidget();cl.addWidget(self.tabs,1)
        conversation=QWidget();cv=QVBoxLayout(conversation);cv.setContentsMargins(0,0,0,0);self.scroll=QScrollArea();self.scroll.setWidgetResizable(True);cv.addWidget(self.scroll);self.tabs.addTab(conversation,'대화')
        self.article=QTextBrowser();self.tabs.addTab(self.article,'결론·실행 제안');self.tabs.currentChanged.connect(lambda i:self.render_article() if i==1 else None)
        controls=QHBoxLayout();self.mode=QLabel();controls.addWidget(self.mode);controls.addStretch();self.next=QPushButton('다음 발언 관찰');self.next.clicked.connect(self.observe);controls.addWidget(self.next);self.take=QPushButton('내 차례로 참여');self.take.clicked.connect(self.take_turn);controls.addWidget(self.take);cl.addLayout(controls)
        self.composer=QPlainTextEdit();self.composer.setPlaceholderText('추가 관측, 반론 또는 다음에 확인할 질문을 입력하세요.');self.composer.setMaximumHeight(84);self.composer.setPlainText(self.d.get('draft',''));self.composer.textChanged.connect(self.draft_changed);cl.addWidget(self.composer)
        foot=QHBoxLayout();self.reply=QLabel('선택한 발언에 이어서 참여');foot.addWidget(self.reply);foot.addStretch();send=QPushButton('발언 보내기');send.setProperty('primary',True);send.clicked.connect(self.send);foot.addWidget(send);cl.addLayout(foot)
        right,rl=panel('선택한 발언의 근거');split.addWidget(right);self.sources=QListWidget();self.sources.setMaximumHeight(160);self.sources.itemClicked.connect(self.show_evidence);rl.addWidget(self.sources);self.evidence=QTextBrowser();rl.addWidget(self.evidence,1)
        rl.addWidget(section('진행과 다음 행동'));self.summary=QLabel('관측 확인 → 가설 분리 → 구분 실험 → 결과 검토');self.summary.setWordWrap(True);self.summary.setContentsMargins(7,6,7,6);rl.addWidget(self.summary)
        proposal=QPushButton('DOE 계획을 최적화에서 열기');proposal.clicked.connect(self.propose);rl.addWidget(proposal)
        if self.d.get('custom_topic'):
            proposal.setEnabled(False);proposal.setToolTip('새 질문에 대한 실행 제안은 아직 생성되지 않았습니다.')
        scope=QLabel('자료 범위: '+self.d['scope']);scope.setWordWrap(True);scope.setStyleSheet('font-size:11px;color:#586d7d;padding:6px;');rl.addWidget(scope)
        split.setSizes([250,820,300]);split.setCollapsible(1,False)
        self.render_turns();self.state_labels();self.select_message(self.d.get('selected_message','m1'),False)
    def tool_actions(self):return [('새 질문…','add',self.new_question,None),('자료 추가…','import',self.add_evidence,'Ctrl+I'),('일시정지 / 이어가기','pause',self.toggle_pause,'F6'),('다음 발언 관찰','play',self.observe,'F7'),('내 차례로 참여','edit',self.take_turn,'F8'),('결론 정리','check',self.conclude,None)]
    def tool_menus(self):return {'세션':['새 질문…'],'자료':['자료 추가…'],'대화':['일시정지 / 이어가기','다음 발언 관찰','내 차례로 참여'],'결론':['결론 정리']}
    def new_question(self):
        text,ok=QInputDialog.getMultiLineText(self,'새 자문 질문','관측과 확인하려는 문제를 입력하세요. 현재 세션은 보존하고 새 창으로 엽니다.')
        if not ok or not text.strip():return
        self.open_tool('expert',{'name':text.strip()[:32],'topic':text.strip()[:60],'issues':[['root','검토 질문'],['rate','가설과 원인'],['contact','계산 모델'],['signal','관측과 측정'],['evidence','추가 근거']],
            'messages':[{'id':'m1','role':'사용자','issue':'root','text':text.strip(),'evidence':[]}],'evidence':[],'selected_message':'m1','custom_topic':True})
    def draft_changed(self):
        self.d['draft']=self.composer.toPlainText();self.change('입력 초안 변경')
    def render_turns(self):
        content=QWidget();l=QVBoxLayout(content);l.setContentsMargins(9,8,9,8);l.setSpacing(7);self.turns={}
        for i,m in enumerate(self.d['messages']):
            reply_label=next((f'{other["role"]} 발언 {j+1}' for j,other in enumerate(self.d['messages']) if other['id']==m.get('reply')),'이전 발언')
            turn=Turn(m,i,m['id']==self.d.get('selected_message'),reply_label);turn.selected.connect(self.select_message);turn.replied.connect(lambda mid:self.select_message(mid,True));self.turns[m['id']]=turn;l.addWidget(turn)
        l.addStretch();self.scroll.setWidget(content)
    def state_labels(self):
        self.mode.setText('현재: '+('일시정지' if self.d['paused'] else self.d['mode'])+'   ·   시연 발언을 한 단계씩 진행합니다')
        self.phase.setText(f'관측·가설 검토 단계\n발언 {len(self.d["messages"])}개 · 논점 {len(self.d["issues"])-1}개\n사용자 개입 후 진행자가 다음 발언을 조정합니다.')
        for key,item in self.issue_items.items():item.setText(1,str(sum(m['issue']==key for m in self.d['messages'])))
        self.next.setEnabled(not self.d['paused']);self.take.setEnabled(True)
    def select_message(self,mid,scroll_to=False):
        self.d['selected_message']=mid;m=next((m for m in self.d['messages'] if m['id']==mid),self.d['messages'][0])
        for key,w in self.turns.items():w.setStyleSheet(f'Turn {{background:{"#edf5fc" if key==mid else "white"};border:1px solid {"#72a3ca" if key==mid else "#e0e6ec"};border-radius:3px;}}')
        self.issue_tree.setCurrentItem(self.issue_items[m['issue']]);number=self.d['messages'].index(m)+1;self.reply.setText(f'{m["role"]}의 발언 {number}에 이어서 참여')
        self.sources.clear()
        for ev in self.d['evidence']:
            if ev['id'] in m.get('evidence',[]):self.sources.addItem(ev['title']);self.sources.item(self.sources.count()-1).setData(Qt.ItemDataRole.UserRole,ev['id'])
        if self.sources.count():self.sources.setCurrentRow(0);self.show_evidence(self.sources.item(0))
        else:self.evidence.setPlainText('이 발언에는 외부 근거가 첨부되지 않았습니다. 사용자 관측 또는 검토 초안으로 구분하세요.')
        if scroll_to and mid in self.turns:self.scroll.ensureWidgetVisible(self.turns[mid])
    def select_issue(self,item,*_):
        key=item.data(0,Qt.ItemDataRole.UserRole);matches=[m for m in self.d['messages'] if m['issue']==key]
        if matches:self.select_message(matches[-1]['id'],True)
    def show_evidence(self,item):
        key=item.data(Qt.ItemDataRole.UserRole);ev=next(x for x in self.d['evidence'] if x['id']==key)
        self.evidence.setHtml(f'<h3>{html.escape(ev["title"])}</h3><p style="color:#597083">{html.escape(ev["source"])}</p><p>{html.escape(ev["text"]).replace(chr(10),"<br>")}</p>')
    def take_turn(self):
        before=self.document();self.d['mode']='참여';self.d['paused']=True;self.state_labels();self.composer.setFocus();self.change('참여 모드 · 다음 발언을 멈추고 관측을 입력합니다',before)
    def toggle_pause(self):
        before=self.document();self.d['paused']=not self.d['paused'];self.d['mode']='관찰' if not self.d['paused'] else '참여';self.state_labels();self.change('대화 진행 상태 변경',before)
    def send(self):
        text=self.composer.toPlainText().strip()
        if not text:return
        before=self.document();mid='m'+uuid.uuid4().hex[:7];selected=next((m for m in self.d['messages'] if m['id']==self.d['selected_message']),self.d['messages'][0])
        self.d['messages'].append({'id':mid,'role':'사용자','text':text,'issue':selected['issue'],'reply':selected['id'],'evidence':[]});self.d['selected_message']=mid;self.d['draft']='';self.composer.clear();self.d['mode']='참여';self.d['paused']=True;self.render_turns();self.state_labels();self.select_message(mid,True);self.change('사용자 발언 저장 · 이어가기 후 다음 발언을 관찰하세요',before)
    def observe(self):
        if self.d['paused']:return
        before=self.document();last=self.d['messages'][-1]
        if self.d.get('custom_topic'):
            role='진행자';text='질문과 관측 “'+last['text'][:180]+'”를 기록했습니다. 이 시안에서는 실제 전문가 모델이 연결되지 않았으므로 원인이나 해결책을 생성하지 않습니다. 자료를 추가하고 논점을 선택하여 대화·근거 연결과 사용자 참여 흐름을 검토할 수 있습니다. [대화 흐름 시연]';issue=last['issue']
        elif last['role']=='사용자':role='진행자';text='추가 관측 “'+last['text'][:180]+'”를 이번 비교의 조건으로 기록했습니다. 이 조건을 고정해 속도·접촉·신호 처리 가설을 하나씩 구분하는 계획을 검토하겠습니다. [시연 응답: 실제 모델 추론 아님]';issue=last['issue']
        else:
            role=['시험 전문가','재료 전문가','수치해석 전문가'][len(self.d['messages'])%3];issue={'시험 전문가':'signal','재료 전문가':'rate','수치해석 전문가':'contact'}[role]
            text={'시험 전문가':'원본과 필터 후 채널을 같은 단위·이벤트 기준으로 겹쳐 확인하는 작업을 먼저 제안합니다. 신호를 바꾼 결과와 물리 모델을 바꾼 결과를 혼합하지 않겠습니다.','재료 전문가':'현재는 속도 의존 계수를 확정할 근거가 부족합니다. 여러 속도의 관측을 독립 확인용으로 남기고, 학습에 사용한 곡선과 구분해 비교하겠습니다.','수치해석 전문가':'접촉 및 경계조건 변수 그룹을 분리하고, 수렴·에너지 점검을 통과한 실행만 후보 비교에 넣는 절차를 제안합니다.'}[role]+' [시연 발언]'
        mid='m'+uuid.uuid4().hex[:7];self.d['messages'].append({'id':mid,'role':role,'text':text,'issue':issue,'reply':last['id'],'evidence':[] if self.d.get('custom_topic') else ['plan1']});self.d['selected_message']=mid;self.render_turns();self.state_labels();self.select_message(mid,True);self.change('다음 시연 발언 추가',before)
    def render_article(self):
        obs=[m['text'] for m in self.d['messages'] if m['role']=='사용자']
        if self.d.get('custom_topic'):
            self.article.setHtml('<h2>세션 기록</h2><h3>사용자 관측</h3><ul>'+''.join('<li>'+html.escape(x)+'</li>' for x in obs)+'</ul><p>실제 모델과 계산 근거가 없어 원인 결론 및 실행 제안은 아직 생성되지 않았습니다.</p>');return
        self.article.setHtml('<h2>결론과 실행 제안 · 검토 초안</h2><p>현재 근거로 단일 원인을 확정하지 않습니다. 아래는 세션 관측과 제안을 묶은 시연 문서입니다.</p><h3>사용자가 제공한 관측</h3><ul>'+''.join('<li>'+html.escape(x)+'</li>' for x in obs)+'</ul><h3>우선 확인할 작업</h3><ol><li>원본/처리 신호와 단위·시간 정렬 확인</li><li>속도·온도·지그 조건을 고정한 구분 실험</li><li>재료/접촉 변수 그룹을 분리한 DOE 계획 검토</li><li>새 결과를 근거로 추가한 뒤 논점 재검토</li></ol><h3>보류</h3><p>원인 확정, 최종 재료 계수, 실제 계산 결과와 모델 생성 답변은 아직 없습니다.</p>')
    def conclude(self):self.render_article();self.tabs.setCurrentIndex(1)
    def add_evidence(self):
        path,_=QFileDialog.getOpenFileName(self,'근거 텍스트 추가','','텍스트 (*.txt *.md *.csv)')
        if not path:return
        try:text=Path(path).read_text(encoding='utf-8-sig')
        except Exception as e:QMessageBox.warning(self,'파일 읽기 실패',str(e));return
        before=self.document();ev={'id':'ev'+uuid.uuid4().hex[:6],'title':Path(path).name,'source':str(Path(path).resolve()),'text':text[:30000]};self.d['evidence'].append(ev)
        selected=next(m for m in self.d['messages'] if m['id']==self.d['selected_message']);selected.setdefault('evidence',[]).append(ev['id']);self.select_message(selected['id']);self.change('로컬 근거 추가 · 외부 전송 없음',before)
    def propose(self):
        self.open_tool('opt',{'name':'자문에서 제안한 구분 실험','source_ref':{k:self.d.get(k) for k in ('id','kind','revision','path')},'proposal':{'status':'검토 초안','rationale':'재료/접촉 변수 그룹을 분리하고 속도조건 고정. 실제 실행 전 범위 검토.','message_ids':[m['id'] for m in self.d['messages']]}})

APPNAMES={'pre':'전처리','runner':'솔버 실행기','post':'후처리','opt':'최적화','expert':'전문가 자문'}
PORTS={'pre':['모델 / 실험 데이터','재료·조건','검증된 입력'],'runner':['고정 입력','실행 설정','결과'],'post':['결과 / ASCII','분석·비교','추출'],'opt':['평가 절차','변수·목적·제약','후보 / 연구 결과'],'expert':['관측·근거','토론 세션','실행 제안']}

class Cell(QGraphicsRectItem):
    def __init__(self,workspace,node,row,x,y,text):
        super().__init__(0,0,215,33);self.ws=workspace;self.node=node;self.row=row;self.setPos(x,y);self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable);self.setPen(QPen(QColor('#9fafbd')));self.setBrush(QColor('white'))
        self.label=QGraphicsSimpleTextItem(text,self);self.label.setPos(9,8);self.label.setBrush(QColor('#263f52'));self.setToolTip(f'{APPNAMES[node["kind"]]} · {text}\n두 번 클릭하여 정확한 문서 버전 열기')
    def mousePressEvent(self,event):super().mousePressEvent(event);self.ws.select_node(self.node['id'],self.row)
    def mouseDoubleClickEvent(self,event):self.ws.open_node(self.node['id']);super().mouseDoubleClickEvent(event)

class WorkbenchWorkspace(QWidget):
    def __init__(self,doc,changed,open_tool):
        super().__init__();self.d=copy.deepcopy(doc);self.d.setdefault('nodes',[]);self.d.setdefault('links',[]);self.d.setdefault('selected',None);self.change=changed;self.open_tool=open_tool;self.cells={};self.build()
    def document(self):return copy.deepcopy(self.d)
    def node_path(self,node):
        p=Path(node.get('path',''))
        return p if p.is_absolute() else Path(self.d.get('path',__file__)).resolve().parent/p
    def set_document(self,doc):self.d=copy.deepcopy(doc);self.render()
    def tool_actions(self):return [('문서 등록…','import',self.register,'Ctrl+I'),('시스템 추가','add',self.add_selected,None),('선택 시스템 열기','open',self.open_selected,'Return'),('연결 만들기…','link',self.connect_nodes,None),('파일 위치 다시 연결…','import',self.relink,None),('변경 영향 확인','refresh',self.check_stale,'F5'),('연결 검증','check',self.validate,None)]
    def tool_menus(self):return {'프로젝트':['문서 등록…','시스템 추가','선택 시스템 열기'],'연결':['연결 만들기…','파일 위치 다시 연결…','변경 영향 확인','연결 검증']}
    def build(self):
        root=QVBoxLayout(self);root.setContentsMargins(5,5,5,3);root.setSpacing(5);split=QSplitter();root.addWidget(split,1)
        left,ll=panel('도구 상자');split.addWidget(left);self.toolbox=QListWidget()
        for k,v in APPNAMES.items():self.toolbox.addItem(v);self.toolbox.item(self.toolbox.count()-1).setData(Qt.ItemDataRole.UserRole,k)
        self.toolbox.setCurrentRow(0);self.toolbox.itemDoubleClicked.connect(lambda _:self.add_selected());self.toolbox.setMaximumHeight(170);ll.addWidget(self.toolbox)
        add=QPushButton('선택 도구를 독립 실행');add.clicked.connect(lambda:self.open_tool(self.toolbox.currentItem().data(Qt.ItemDataRole.UserRole)));ll.addWidget(add)
        ll.addWidget(section('프로젝트 문서'));self.tree=QTreeWidget();self.tree.setHeaderLabels(['시스템 / 버전']);self.tree.itemClicked.connect(self.tree_select);ll.addWidget(self.tree,1)
        center=QSplitter(Qt.Orientation.Vertical);split.addWidget(center);canvas,cl=panel('프로젝트 연결도 · 셀을 두 번 클릭하여 프로그램 열기')
        self.scene=QGraphicsScene();self.view=QGraphicsView(self.scene);self.view.setRenderHint(QPainter.RenderHint.Antialiasing);self.view.setBackgroundBrush(QColor('#f8fafc'));cl.addWidget(self.view,1);center.addWidget(canvas)
        table,tl=panel('객체와 고정 버전');self.objects=QTableWidget(0,5);self.objects.setHorizontalHeaderLabels(['시스템','연결한 버전','현재 파일','상태','문서']);self.objects.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents);self.objects.horizontalHeader().setStretchLastSection(True);self.objects.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);self.objects.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);self.objects.cellClicked.connect(self.table_select);tl.addWidget(self.objects);center.addWidget(table);center.setSizes([580,190])
        right,rl=panel('선택 셀 속성');split.addWidget(right);self.properties=QTableWidget(0,2);self.properties.setHorizontalHeaderLabels(['속성','값']);self.properties.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);self.properties.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers);rl.addWidget(self.properties)
        rl.addWidget(section('연결과 갱신'));self.details=QTextBrowser();rl.addWidget(self.details,1);open_btn=QPushButton('고정 버전을 프로그램에서 열기');open_btn.clicked.connect(self.open_selected);rl.addWidget(open_btn);new_btn=QPushButton('최신 버전을 별도 창에서 열기');new_btn.clicked.connect(self.open_latest);rl.addWidget(new_btn)
        self.diagnostics=QLabel();self.diagnostics.setWordWrap(True);self.diagnostics.setContentsMargins(5,5,5,5);root.addWidget(self.diagnostics);split.setSizes([230,975,270]);self.render()
    def render(self):
        self.scene.clear();self.cells={};self.tree.clear();self.objects.setRowCount(len(self.d['nodes']));positions={}
        for i,n in enumerate(self.d['nodes']):
            x=35+(i%3)*285;y=45+(i//3)*245;positions[n['id']]=(x,y)
            title=self.scene.addRect(x,y,215,34,QPen(QColor('#557b9b')),QBrush(QColor('#dbe8f3')));title.setZValue(1)
            label=self.scene.addSimpleText(f'{chr(65+i)}  {APPNAMES[n["kind"]]}');label.setPos(x+9,y+8);label.setBrush(QColor('#204a6d'));label.setZValue(2)
            for j,t in enumerate(PORTS[n['kind']]):
                cell=Cell(self,n,j,x,y+34+j*33,f'{j+1}   {t}');self.scene.addItem(cell);self.cells[(n['id'],j)]=cell
            note=self.scene.addSimpleText(f'r{n.get("revision",0)}   '+n.get('state','未保存').replace('未保存','미저장'));note.setPos(x+4,y+140);note.setBrush(QColor('#9a5b17' if n.get('state')=='갱신 필요' else '#567185'))
            item=QTreeWidgetItem([f'{APPNAMES[n["kind"]]} / r{n.get("revision",0)}']);item.setData(0,Qt.ItemDataRole.UserRole,n['id']);self.tree.addTopLevelItem(item)
            for c,val in enumerate([APPNAMES[n['kind']],f'r{n.get("revision",0)}',f'r{n.get("latest",n.get("revision",0))}',n.get('state','미저장'),Path(n.get('path','')).name]):self.objects.setItem(i,c,QTableWidgetItem(str(val)))
        for link in self.d['links']:
            if link['from'] not in positions or link['to'] not in positions:continue
            a=positions[link['from']];b=positions[link['to']];start=QPointF(a[0]+215,a[1]+116);end=QPointF(b[0],b[1]+50);path=QPainterPath(start);path.cubicTo(start+QPointF(55,0),end-QPointF(55,0),end);line=self.scene.addPath(path,QPen(QColor('#8965a5'),2));line.setZValue(2);line.setToolTip('고정 입력/출력 연결 · 변경 영향 확인')
        self.scene.setSceneRect(0,0,max(900,880),max(420,((len(self.d['nodes'])+2)//3)*245+70))
        if not self.d['nodes']:
            text=self.scene.addText('프로젝트에 연결할 문서를 등록하세요.\n\n왼쪽 도구를 독립 실행하여 저장한 후 «문서 등록»으로 추가할 수 있습니다.\n이 연결도 없이도 각 프로그램에서 모든 단독 작업을 시작할 수 있습니다.');text.setPos(45,60);text.setDefaultTextColor(QColor('#486176'))
        self.diagnostics.setText(f'프로젝트: 시스템 {len(self.d["nodes"])}개 · 연결 {len(self.d["links"])}개 | 이전 결과는 고정 버전으로 보존됩니다. 새 계산은 자동 시작하지 않습니다.')
        if self.d.get('selected'):self.select_node(self.d['selected'])
    def register(self):
        from desktop import DATA
        paths,_=QFileDialog.getOpenFileNames(self,'독립 앱의 저장 문서 등록',str(DATA),'CAE 문서 (*.caeprep *.caerun *.caepost *.caestudy *.caechat)')
        if not paths:return
        from desktop import read_document
        before=self.document()
        for path in paths:
            try:doc=read_document(path)
            except Exception as e:QMessageBox.warning(self,'등록 실패',str(e));continue
            existing=next((n for n in self.d['nodes'] if n['id']==doc['id']),None)
            if existing:
                try:self.relink_path(existing,path)
                except Exception as e:QMessageBox.warning(self,'다시 연결 실패',str(e))
                continue
            from desktop import content_hash
            self.d['nodes'].append({'id':doc['id'],'kind':doc['kind'],'path':str(Path(path).resolve()),'revision':doc['revision'],'latest':doc['revision'],'name':doc.get('name'),'content_hash':doc.get('content_hash',content_hash(doc)),'state':'최신'})
        self.render();self.change('독립 문서 등록',before)
    def relink_path(self,node,path):
        from desktop import read_document,content_hash
        p=Path(path).resolve();current=read_document(p)
        if current.get('id')!=node['id'] or current.get('kind')!=node['kind']:
            raise ValueError('선택한 문서는 등록된 문서와 ID 또는 종류가 다릅니다. 올바른 문서를 선택하세요.')
        history=p.parent/'.history'/node['id']/f'{node["revision"]}.json'
        pinned=read_document(history)
        if pinned.get('id')!=node['id'] or pinned.get('revision')!=node['revision'] or pinned.get('kind')!=node['kind']:
            raise ValueError('고정 버전 기록이 일치하지 않습니다. 문서와 .history 폴더를 함께 옮기세요.')
        if node.get('content_hash') and content_hash(pinned)!=node['content_hash']:
            raise ValueError('고정 버전의 내용이 등록 당시와 다릅니다. 원래 버전 기록을 복구하세요.')
        node['path']=str(p);node['latest']=current['revision'];node['state']='갱신 필요' if content_hash(current)!=content_hash(pinned) else ('표시만 변경' if current['revision']!=node['revision'] else '최신')
    def relink(self):
        node=next((n for n in self.d['nodes'] if n['id']==self.d.get('selected')),None)
        if not node:QMessageBox.information(self,'파일 위치 다시 연결','먼저 프로젝트의 문서를 선택하세요.');return
        path,_=QFileDialog.getOpenFileName(self,'같은 문서의 새 위치 선택',str(self.node_path(node).parent),'CAE 문서 (*.caeprep *.caerun *.caepost *.caestudy *.caechat)')
        if not path:return
        before=self.document()
        try:self.relink_path(node,path)
        except Exception as e:QMessageBox.warning(self,'다시 연결 실패',str(e));return
        self.render();self.change('문서 위치 복구 · 고정 버전과 연결 보존',before)
    def add_selected(self):
        kind=self.toolbox.currentItem().data(Qt.ItemDataRole.UserRole);self.open_tool(kind)
        self.diagnostics.setText(f'{APPNAMES[kind]}을 독립 창으로 열었습니다. 문서를 저장한 뒤 «문서 등록»으로 연결하세요.')
    def table_select(self,row,col):self.select_node(self.d['nodes'][row]['id'])
    def tree_select(self,item,*_):self.select_node(item.data(0,Qt.ItemDataRole.UserRole))
    def select_node(self,nid,row=0):
        node=next((x for x in self.d['nodes'] if x['id']==nid),None)
        if not node:return
        self.d['selected']=nid
        for index in range(self.tree.topLevelItemCount()):
            item=self.tree.topLevelItem(index)
            if item.data(0,Qt.ItemDataRole.UserRole)==nid:
                self.tree.blockSignals(True);self.tree.setCurrentItem(item);self.tree.blockSignals(False)
                self.objects.blockSignals(True);self.objects.selectRow(index);self.objects.blockSignals(False)
                break
        for (id,j),cell in self.cells.items():cell.setBrush(QColor('#cfe5f8' if id==nid and row==j else 'white'))
        props=[('프로그램',APPNAMES[node['kind']]),('선택 셀',PORTS[node['kind']][row]),('고정 버전',f'r{node["revision"]}'),('현재 파일',f'r{node.get("latest",node["revision"])}'),('상태',node.get('state','')),
               ('문서',node.get('name','')),('ID',node['id'][:12])]
        self.properties.setRowCount(len(props))
        for r,(k,v) in enumerate(props):self.properties.setItem(r,0,QTableWidgetItem(k));self.properties.setItem(r,1,QTableWidgetItem(str(v)))
        links=[l for l in self.d['links'] if nid in (l['from'],l['to'])]
        self.details.setPlainText(f'파일 위치\n{self.node_path(node)}\n\n연결 {len(links)}개\n'+('입력 파일이 변경되었습니다. 이 프로젝트의 고정 버전과 이전 결과는 유지됩니다. 최신 파일을 별도 창에서 검토하고 새 실행을 시작하세요.' if node.get('state')=='갱신 필요' else '프로젝트는 정확한 문서 ID와 저장 버전을 참조합니다.'))
    def open_node(self,nid,latest=False):
        node=next((n for n in self.d['nodes'] if n['id']==nid),None)
        if node:self.open_tool(node['kind'],str(self.node_path(node)),None if latest else node['revision'])
    def open_selected(self):self.open_node(self.d.get('selected'))
    def open_latest(self):self.open_node(self.d.get('selected'),True)
    def connect_nodes(self):
        if len(self.d['nodes'])<2:QMessageBox.information(self,'연결','저장한 문서 두 개 이상을 먼저 등록하세요.');return
        dlg=QDialog(self);dlg.setWindowTitle('출력 → 입력 연결');l=QFormLayout(dlg);a=QComboBox();b=QComboBox()
        for n in self.d['nodes']:
            text=APPNAMES[n['kind']]+' / '+str(n.get('name',''))+f' r{n["revision"]}';a.addItem(text,n['id']);b.addItem(text,n['id'])
        b.setCurrentIndex(1);l.addRow('출력 문서',a);l.addRow('입력 문서',b);note=QLabel('지원 연결: 전처리→실행기/최적화, 실행기→후처리, 최적화→실행기/후처리, 전문가→최적화');note.setWordWrap(True);l.addRow(note);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dlg.accept);buttons.rejected.connect(dlg.reject);l.addRow(buttons)
        if dlg.exec()!=QDialog.DialogCode.Accepted:return
        src=next(n for n in self.d['nodes'] if n['id']==a.currentData());dst=next(n for n in self.d['nodes'] if n['id']==b.currentData())
        allowed={('pre','runner'),('pre','opt'),('runner','post'),('opt','runner'),('opt','post'),('expert','opt')}
        if (src['kind'],dst['kind']) not in allowed:QMessageBox.warning(self,'호환되지 않는 연결','이 문서의 출력과 선택한 입력의 종류가 맞지 않습니다.');return
        if any(l['from']==src['id'] and l['to']==dst['id'] for l in self.d['links']):return
        before=self.document();self.d['links'].append({'from':src['id'],'to':dst['id'],'input_revision':src['revision']});self.render();self.change('고정 문서 연결 추가',before)
    def check_stale(self):
        from desktop import read_document, content_hash
        before=self.document()
        for n in self.d['nodes']:
            try:
                p=self.node_path(n);doc=read_document(p);n['latest']=doc['revision']
                if doc.get('id')!=n['id'] or doc.get('kind')!=n['kind']:raise ValueError('등록된 문서와 일치하지 않습니다')
                pinned=read_document(p.parent/'.history'/n['id']/f'{n["revision"]}.json')
                if pinned.get('id')!=n['id'] or pinned.get('revision')!=n['revision']:raise ValueError('고정 버전 기록이 일치하지 않습니다')
                current_hash=content_hash(doc);pinned_hash=n.get('content_hash',content_hash(pinned))
                n['state']='갱신 필요' if current_hash!=pinned_hash else ('표시만 변경' if doc['revision']!=n['revision'] else '최신')
            except Exception:n['state']='파일 없음'
        stale={n['id'] for n in self.d['nodes'] if n['state'] in ('갱신 필요','파일 없음')}
        for _ in self.d['nodes']:
            for link in self.d['links']:
                if link['from'] in stale:
                    stale.add(link['to'])
                    for n in self.d['nodes']:
                        if n['id']==link['to'] and n['state'] in ('최신','표시만 변경'):n['state']='상위 입력 변경'
        self.render();self.change('현재 파일과 고정 버전 비교 · 자동 실행 없음',before)
    def validate(self):
        missing=[n.get('name',n['id']) for n in self.d['nodes'] if not self.node_path(n).is_file()]
        self.diagnostics.setText('연결 검증: '+('파일 위치를 다시 연결하세요: '+', '.join(missing) if missing else f'문서 {len(self.d["nodes"])}개 경로 존재. 연결 {len(self.d["links"])}개. 실제 계산 가능 여부는 각 실행기에서 검사합니다.'))

def create_workspace(kind,document,changed,open_tool):
    return ExpertWorkspace(document,changed,open_tool) if kind=='expert' else WorkbenchWorkspace(document,changed,open_tool)
