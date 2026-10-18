"""Persist exact Case A sources and an explicit UNKNOWN material judgment."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
import uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from apps.research.study_window import StudyWindow
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from caelab.workbench_client import Client
from caelab.storage import canonical_hash,load_json,save_json
from caelab.study_document import diagnostics


def wait(app,predicate):
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise TimeoutError('Study retained source Qt/HTTP')


def save(client,doc):
    return client.document_command(doc['id'],'document.save',{},session_id=doc['session_id'],
        expected_generation=doc['generation'],command_id='C'+uuid.uuid4().hex)['document']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execution',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--post-references',type=Path);parser.add_argument('--cold',type=Path)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    receipt=load_json(args.execution/'execution.json');store=Path(receipt['store'])
    sources=('tests/check_case_a_study_windows.py','apps/research/study_window.py',
             'apps/research/reference_content.py',
             'caelab/study_document.py','caelab/native_project_inputs.py',
             'caelab/native_post_dependencies.py')
    pins={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}');app=QApplication([]);window=None
    try:
        jobs=client.request('/api/workbench')['jobs'];assert len(jobs)==10
        if args.cold:
            prior=load_json(args.cold/'study.json')
            doc=client.document_open(kind='study',document_id=prior['document_id'])
            assert canonical_hash(doc['draft'])==prior['draft_sha256']
            assert doc['saved_revision']==prior['saved_revision'] and doc['session_id']!=prior['session_id']
        else:
            assert args.post_references is not None
            post=load_json(args.post_references);evidence=[]
            labels={'tension_unload':'인장과 변위 복귀','compression_unload':'압축과 변위 복귀',
                    'transverse_strain_confinement':'보류한 횡변위 구속 시험'}
            for name,label in labels.items():
                for suffix,kind,location in (('_DP_FE','simulation','실제 Gauss 적분점'),
                                             ('_J2_reduction_point','material','J2 환원 재료점')):
                    record=next(c for c in receipt['cases'] if c['name']==name+suffix)
                    source=client.document_open(kind=kind,document_id=record['document_id'])
                    reference=client.document_result_reference(source['id'],record['job_id'])
                    reference={'kind':'result',**reference}
                    evidence.append(dict(id='E'+str(len(evidence)+1),label=label+' · '+location,
                        kind='result',reference=reference,note='같은 합성 입력의 보존 결과. 실제 재료의 보정·적합성 판정과 구분합니다.'))
                reference=post[name];assert reference['kind']=='native_post'
                evidence.append(dict(id='E'+str(len(evidence)+1),label=label+' · CalculiX J2 후처리',
                    kind='native_post',reference=reference,
                    note='같은 1 mm 형상의 보존 장면. S/E/PEEQ는 절점 외삽·평균이며 DP 적분점과 같은 점이 아닙니다.'))
            draft=dict(question='같은 시편의 J2와 DP 응답 차이가 실제 재료 선택을 뒷받침하는가?',
                hypotheses=[dict(id='H1',title='실제 재료에 맞는 법칙',
                    statement='인장·압축·횡구속의 실측 관측량과 재료·지그 효과를 구분해야 법칙을 선택할 수 있습니다.',status='UNKNOWN')],
                evidence=evidence,decisions=[dict(id='D1',title='재료 선택은 미확인',
                    statement='원 합성 응답과 출력 위치의 차이를 보존했습니다. 인장·압축의 변위 복귀 중 역항복과 구속 시험 마지막 DP 증분의 탄성 복귀를 구분합니다. 보류한 합성 경계이력은 독립 실험 검증이 아니며 실제 재료와 설계 적합성은 판단하지 않습니다.',
                    hypothesis_ids=['H1'],supporting=[e['id'] for e in evidence],conflicting=[],status='UNKNOWN')],
                next_observations=[dict(id='O1',question='같은 gauge와 관측 측도의 실측 압축·구속압 시험으로 물성 및 지그 효과를 분리할 수 있는가?',
                    hypothesis_ids=['H1'],evidence_ids=[e['id'] for e in evidence],status='PLANNED',
                    note='원행·구속압 부호·온도·속도·불확실성을 보존할 다음 관측입니다. 자동 실행하지 않습니다.')],engineering_release='NOT_RELEASED')
            assert not diagnostics(draft)
            doc=client.document_open(kind='study',title='같은 시편의 J2·DP 비교',draft=draft)
            doc=save(client,doc)
        checks=client.study_references(doc['id'])
        assert len(checks['references'])==9 and all(r['status']=='AVAILABLE' for r in checks['references']),checks
        window=StudyWindow(client,document_id=doc['id'],poll_interval=60000);window.show()
        wait(app,lambda:window.document is not None and not window._busy)
        window.check_references();wait(app,lambda:len(window._reference_checks)==9 and not window._busy)
        # A reference check schedules a separate content read. Its completion
        # alone does not mean the selected result has finished rendering.
        def content_ready(kind):
            payload=window.reading.payload or {}
            return (not window._busy and not window._callbacks and window._content_pending is None
                and payload.get('status')=='AVAILABLE' and payload.get('kind')==kind)
        wait(app,lambda:content_ready('result'))
        # The first retained channel may be a field. Choose the actual series
        # through the existing channel selector and read action.
        index=window.reading.channel.findData('ip0_pressure');assert index>=0
        window.reading.channel.setCurrentIndex(index);window.reading.channel.setFocus()
        window.reading.read.click()
        wait(app,lambda:content_ready('result') and bool(window.reading.axes.lines))
        for prefix,kind,index in (('study','result',0),('native-post','native_post',2)):
            window.evidence.selectRow(index);window.evidence.setFocus();app.processEvents()
            wait(app,lambda:content_ready(kind))
            assert window._selected==('evidence','E'+str(index+1))
            for width,height in ((1440,900),(1000,720)):
                window.resize(width,height);app.processEvents()
                assert window.width()==width
                if kind=='result':window.reading.canvas.draw();app.processEvents()
                assert window.grab().save(str(args.output/f'{prefix}-{width}.png'))
        after=client.document_read(doc['id']);assert after['draft']==doc['draft']
        assert client.request('/api/workbench')['jobs']==jobs
        assert pins=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
        save_json(args.output/'study.json',dict(status='PASS',document_id=doc['id'],session_id=doc['session_id'],
            saved_revision=doc['saved_revision'],draft_sha256=canonical_hash(doc['draft']),references=checks,
            source_files=pins,cold=bool(args.cold),jobs_before=10,jobs_after=10,new_jobs=0,
            rendered_kinds=['result','native_post'],
            preview_response='ip0_pressure',saved_reference_selection_unchanged=True,
            claim='Actual Qt rendering and exact HTTP references; no physical OS input claim',
            engineering_release='UNKNOWN/NOT_RELEASED'))
    finally:
        if window is not None:window._allow_close=True;window.close();app.processEvents()
        server.shutdown();server.server_close();service.shutdown();thread.join(5)


if __name__=='__main__':main()
