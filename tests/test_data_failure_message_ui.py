"""Retained Data failure presentation; no import, processing or owner mutation."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import time

import pytest
from PySide6.QtWidgets import QApplication
from apps.research.appearance import apply_appearance
from apps.research.data_window import DataWindow, display


@pytest.fixture(scope='module')
def app():
    value=QApplication.instance() or QApplication([])
    apply_appearance(value)
    return value


def close(window, app):
    window._allow_close=True
    window.close();window.deleteLater();app.processEvents()


@pytest.mark.parametrize('error,expected',[
    ({'code':'ValueError','message':'Missing or invalid table column: 9','retryable':False},
        '원자료 열 ‘9’의 지정과 가져오기 설정을 확인하세요.'),
    ({'message':'Missing or invalid table column: stress_raw'},
        '원자료 열 ‘stress_raw’의 지정과 가져오기 설정을 확인하세요.'),
    ({'code':'OtherError','message':'Original unknown failure: unchanged','retryable':True},
        'Original unknown failure: unchanged'),
    ('Unknown engine message','Unknown engine message'),
])
def test_known_unknown_raw_error_preserved_and_tooltip_reset(app,error,expected):
    class NoCommands:
        def __getattr__(self,name):raise AssertionError('Failure rendering must not call '+name)
    window=DataWindow(NoCommands(),auto_open=False,poll_interval=0)
    try:
        window.document={'id':'Tfailure','generation':2,'runs':[{'job_id':'Jfailure','input_generation':1}]}
        window._selected_job='Jfailure'
        receipt={'status':{'state':'FAILED','error':deepcopy(error)}}
        before=deepcopy(receipt);key=window._result_key();window._results[key]=receipt
        window._draw_result(receipt,key)
        assert window.result_label.text()=='가져오기 실패 / 이전 원본 또는 설정의 데이터 · '+expected
        assert window.result_label.toolTip()==display(error)
        assert json.loads(window.details.toPlainText())['selected_result']['status']['error']==error
        assert receipt==before and window._results[key]==before
        assert window._selected_job=='Jfailure'
        # Switching to a result without an error must not retain the old tooltip.
        clean={'status':{'state':'SUCCEEDED'}}
        window._draw_result(clean,key)
        assert window.result_label.toolTip()==''
        window._draw_result(receipt,key);window._clear_result()
        assert window.result_label.toolTip()==''
    finally:close(window,app)


def test_same_c2_failed_result_http_normal_narrow_readonly(app,tmp_path,monkeypatch):
    from examples.s1_windows_transfer import local_service
    from caelab.storage import canonical_hash
    evidence=Path(__file__).resolve().parents[1]/'_workspace/b83-portable/data-c2-finish-a/cold.json'
    if not evidence.exists():pytest.skip('Actual retained C2 portable case is private evidence')
    source=Path(json.loads(evidence.read_text(encoding='utf-8'))['second_receipt']['workspace'])
    if not source.exists():pytest.skip('Actual retained C2 store is unavailable')
    source_files={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (source/'workbench/documents').rglob('working.json')}
    store=tmp_path/'store';shutil.copytree(source,store)
    calls=[]
    def forbidden(*a,**k):calls.append((a,k));raise AssertionError('Read-only failure view cannot submit or mutate')
    with local_service(store) as (wb,client):
        jobs=deepcopy(wb.manager.list())
        monkeypatch.setattr(wb,'submit',forbidden);monkeypatch.setattr(wb.manager,'submit',forbidden)
        for owner in wb.research_owners():monkeypatch.setattr(owner,'submit',forbidden)
        monkeypatch.setattr(client,'document_command',forbidden)
        catalog=client.documents()['documents']
        doc=client.document_open(kind='data',document_id=next(d['id'] for d in catalog if d['kind']=='data'))
        failed=next(r for r in doc['runs'] if r.get('retained_state')=='FAILED')
        assert failed['retained_error']['message']=='Missing or invalid table column: 9'
        window=DataWindow(client,auto_open=False,poll_interval=0)
        try:
            window.show();window.open_document(document_id=doc['id'])
            deadline=time.monotonic()+50
            while time.monotonic()<deadline:
                app.processEvents()
                if window.document and not window._busy and not window._result_pending:break
                time.sleep(.01)
            assert window.document and not window._busy
            window._selected_job=failed['job_id'];window.refresh_result()
            while time.monotonic()<deadline:
                app.processEvents()
                if window._result_key() in window._results and not window._busy:break
                time.sleep(.01)
            key=window._result_key();receipt=deepcopy(window._results[key])
            window._draw_cached_result();app.processEvents()
            assert '원자료 열 ‘9’' in window.result_label.text()
            assert '"code"' not in window.result_label.text()
            assert json.loads(window.result_label.toolTip())==failed['retained_error']
            assert window._results[key]==receipt
            for w,h,name in [(1400,900,'retained-failure-normal.png'),(1000,730,'retained-failure-narrow.png')]:
                window.resize(w,h);window.result_label.setFocus();app.processEvents()
                assert window.grab().save(str(tmp_path/name))
            assert client.document_read(doc['id'])==doc
            assert wb.manager.list()==jobs and not calls
            assert window._selected_job==failed['job_id']
            (tmp_path/'receipt.json').write_text(json.dumps({'status':'PASS','qt_platform':app.platformName(),
                'same_document':doc['id'],'same_failed_job':failed['job_id'],
                'receipt_sha256':canonical_hash(receipt),'same_error':failed['retained_error'],
                'cached_result_unchanged':True,'document_unchanged':True,'selection_unchanged':True,
                'new_commands':0,'new_jobs':0,'new_import_processing_fit_solver_provider':0,
                'product_sha256':hashlib.sha256(Path('apps/research/data_window.py').read_bytes()).hexdigest()},ensure_ascii=False,indent=2),encoding='utf-8')
        finally:
            # Wait only for this window's reads before disposing its widgets.
            deadline=time.monotonic()+20
            while window._busy and time.monotonic()<deadline:app.processEvents();time.sleep(.01)
            close(window,app)
    for relative,sha in source_files.items():
        assert hashlib.sha256((source/relative).read_bytes()).hexdigest()==sha
