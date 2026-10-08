"""Create explicitly synthetic review documents, without asserting UI validation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import math
from pathlib import Path
from PySide6.QtWidgets import QApplication
from desktop import MainWindow, EXT, write_document

app=QApplication([])
root=Path(__file__).resolve().parent/'examples'
root.mkdir(exist_ok=True)
names={'pre':'박판 인장 · 모델과 시험 데이터','runner':'박판 인장 · 실행 검토','post':'온도장과 외부 응답 · 결과 검토','opt':'브래킷 · 변수와 설계 후보','expert':'충격 응답 차이 · 전문가 공동 검토','workbench':'재료·구조 연구 프로젝트'}
docs={}
for kind in ('pre','runner','post','opt','expert'):
    win=MainWindow(kind)
    ws=win.workspace
    if kind=='runner':
        d=ws.document();d['data']['source_revision']=1;d['source_ref']={'id':'review-pre','kind':'pre','revision':1,'path':'pre.caeprep'}
        d['data']['runs']=[
            {'id':'R001','status':'succeeded','progress':100,'residuals':[math.exp(-i/3.4) for i in range(1,25)],'source_revision':1,'log':['설계 시연 로그 · 실제 솔버 호출 없음','입력 r1 고정','검증: 재료·구간·경계조건 존재','시연 반복 1: 잔차 0.745','시연 반복 12: 잔차 0.029','완료: 24 반복 · 시연 결과']},
            {'id':'R002','status':'cancelled','progress':42,'residuals':[math.exp(-i/3.4) for i in range(1,11)],'source_revision':1,'log':['설계 시연 로그','사용자 중단 · 완료된 10개 반복 보존']},
            {'id':'R003','status':'failed','progress':0,'residuals':[],'source_revision':1,'log':['설계 시연 실패 사례','입력 검사 실패: 경계 영역 참조 누락','전처리에서 영역을 다시 배정한 후 새 실행을 만드세요.']},
        ];d['data']['selected_run']=0;ws.set_document(d)
    if kind=='opt':
        ws._message=lambda *args:None
        ws.generate()
    doc=ws.document();doc.update(id='review-'+kind,name=names[kind],revision=0,schema=1)
    path=root/f'{kind}.{EXT[kind]}'
    docs[kind]=write_document(path,doc)
    win.deleteLater()
nodes=[{'id':docs[k]['id'],'kind':k,'name':names[k],'revision':1,'latest':1,'path':f'{k}.{EXT[k]}','content_hash':docs[k]['content_hash'],'state':'최신'} for k in ('pre','runner','post','opt','expert')]
links=[{'from':'review-pre','to':'review-runner','input_revision':1},{'from':'review-runner','to':'review-post','input_revision':1},{'from':'review-pre','to':'review-opt','input_revision':1},{'from':'review-expert','to':'review-opt','input_revision':1}]
write_document(root/'workbench.caeproject',{'id':'review-workbench','kind':'workbench','name':names['workbench'],'revision':0,'schema':1,'nodes':nodes,'links':links,'selected':'review-pre'})
print('Created six synthetic review examples with local revision history.')
