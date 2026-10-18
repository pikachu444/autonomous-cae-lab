"""Exact retained packet selection and Qt signals, with no Core or solver."""
from copy import deepcopy
from types import SimpleNamespace
import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from apps.research.appearance import apply_appearance
from apps.research.impact_history_view import ImpactHistoryView
from caelab.impact_responses import select_history
from test_impact_history_selection import snapshot


@pytest.fixture(scope='module')
def app():
    value=QApplication.instance() or QApplication([]);apply_appearance(value);return value


def close(view,app):
    view.close();view.deleteLater();app.processEvents()


def test_exact_selection_signals_row_focus_and_no_mutation(app,monkeypatch,tmp_path):
    from caelab.workbench_client import Client
    def forbidden(*a,**k):raise AssertionError('Retained dialog cannot construct a Core client')
    monkeypatch.setattr(Client,'__init__',forbidden)
    original=snapshot();before=deepcopy(original);view=ImpactHistoryView(original)
    try:
        view.show();app.processEvents()
        assert not view.start.isEditable() and not view.end.isEditable()
        view.start.setCurrentIndex(view.start.findData(.1));app.processEvents()
        request={'response':'force','start_s':.1,'end_s':.4,'side':'native','transform':'identity'}
        expected=select_history(original,request)
        assert view.selected==expected
        assert '순간 힘' in view.meaning.text() and '선택 밖' in view.message.text()
        view.table.setFocus();view.table.selectRow(1);QTest.keyClick(view.table,Qt.Key.Key_Up)
        assert '선택 원행 1' in view.selection_label.text()
        view._pick(SimpleNamespace(artist=view.figure.axes[0].lines[0],ind=[1]))
        assert view.table.currentRow()==1 and '선택 원행 2' in view.selection_label.text()
        assert list(view._point_artist.get_offsets()[0])==[.4,expected['rows'][1]['selected_value']]
        sent=[];view.study_requested.connect(lambda p:sent.append(('study',p)))
        view.plan_requested.connect(lambda p:sent.append(('plan',p)))
        QTest.mouseClick(view.study_button,Qt.MouseButton.LeftButton)
        QTest.mouseClick(view.plan_button,Qt.MouseButton.LeftButton)
        assert [p for _,p in sent]==[expected,expected]
        sent[0][1]['rows'][0]['value']=999
        selected=view.selected;selected['rows'][0]['value']=888
        assert view.selected==expected and original==before
        view.end.setCurrentIndex(0);app.processEvents()
        assert view.selected is None and not view.study_button.isEnabled()
        assert '순서' in view.message.text()
        view.end.setCurrentIndex(view.end.count()-1);assert view.selected==expected
    finally:close(view,app)


def test_native_impulse_and_explicit_integral_have_distinct_units_and_gaps(app,tmp_path):
    value=snapshot();native=deepcopy(value['result']['responses']['force'])
    native['measure']='native_cumulative_contact_impulse';native['unit']='N s'
    native['metadata']['selection']['quantity']='native_impulse'
    native['raw_samples']['transformed_values']=[0.,2.,1.]
    value['result']['responses']['native_J']=native
    view=ImpactHistoryView(value)
    try:
        view.show();view.start.setCurrentIndex(1)
        view.transform.setCurrentIndex(1);app.processEvents()
        assert view.selected['selection']['request']['transform']=='sample_trapezoid'
        assert view.selected['response']['unit']=='N s'
        assert view.selected['response']['value'][0]==0.
        assert '원 누적 충격량 관측이 아닙니다' in view.meaning.text()
        assert view.table.item(0,2).text()=='0'
        view.channel.setCurrentIndex(view.channel.findData('native_J'));app.processEvents()
        assert view.transform.currentData()=='identity' and not view.transform.model().item(1).isEnabled()
        assert '원 접촉쌍 누적 충격량' in view.meaning.text()
        assert view.selected['response']['raw_samples']['transformed_values']==[2.,1.]
        for w,h,name in [(1180,850,'synthetic-native-normal.png'),(800,700,'synthetic-native-narrow.png')]:
            view.resize(w,h);app.processEvents();assert view.grab().save(str(tmp_path/name))
    finally:close(view,app)
    value=snapshot();raw=value['result']['responses']['force']['raw_samples']
    raw['calculation_valid'][1]=False
    raw['quality_reasons']=['','원 표본 누락','']
    before=deepcopy(value);view=ImpactHistoryView(value)
    try:
        view.show();view.transform.setCurrentIndex(1);app.processEvents()
        assert view.selected['response']['raw_samples']['transformed_values']==[0.,None,None]
        assert view.table.item(1,2).text()=='기록 없음' and view.table.item(1,5).text()=='제외'
        assert view.figure.axes[0].lines[0].get_ydata()[1]!=view.figure.axes[0].lines[0].get_ydata()[1]
        assert value==before
        view.start.setCurrentIndex(2);app.processEvents()
        assert view.selected is None and '둘 이상' in view.message.text()
    finally:close(view,app)


def test_empty_and_invalid_source_close_without_packets(app):
    value=snapshot();value['result']['responses']={};view=ImpactHistoryView(value)
    try:
        view.show();app.processEvents()
        assert view.selected is None and not view.plan_button.isEnabled()
        assert '보존 이력이 없습니다' in view.message.text()
        view.reject();assert value['result']['responses']=={}
    finally:close(view,app)
    invalid=snapshot();invalid['source']['input_sha256']='invalid'
    view=ImpactHistoryView(invalid)
    try:
        view.show();app.processEvents()
        assert view.selected is None and not view.plan_button.isEnabled()
        assert '정확한 저장 신원' in view.message.text()
    finally:close(view,app)


def test_readback_status_keeps_original_failure_cancel_and_actual_state(app,tmp_path,monkeypatch):
    from caelab.workbench_client import Client
    def forbidden(*a,**k):raise AssertionError('Status display cannot construct a Core client')
    monkeypatch.setattr(Client,'__init__',forbidden)
    for state,label in [('FAILED','실패'),('CANCELLED','취소')]:
        value=snapshot();value['result'].update(operation='impact.reprocess',execution_status='SUCCEEDED',
            source_execution_status=state,solver_execution='NOT_PERFORMED')
        before=deepcopy(value);view=ImpactHistoryView(value)
        try:
            view.show();view.resize(800,715);app.processEvents()
            assert '보존 결과 재읽기: 읽기 완료' in view.status.text()
            assert '원 계산: '+label in view.status.text()
            assert '새 솔버 계산: 미실행' in view.status.text()
            assert '보존 해석: 완료' not in view.status.text()
            assert '공학 적합성: 미확인' in view.status.text()
            assert view.selected['source_execution_status']==state
            assert view.selected['execution_status']=='SUCCEEDED'
            assert value==before
            if state=='FAILED':assert view.grab().save(str(tmp_path/'readback-source-failed-narrow.png'))
        finally:close(view,app)
    path=Path(__file__).resolve().parents[1]/'_workspace/impact-history-selection-20261018/read-owner-01/snapshot.json'
    if not path.exists():return
    original_bytes=path.read_bytes();value=json.loads(original_bytes);before=deepcopy(value)
    view=ImpactHistoryView(value)
    try:
        view.show();view.resize(800,715)
        view.channel.setCurrentIndex(view.channel.findData('PAIR_force_FNZ'));app.processEvents()
        assert '보존 결과 재읽기: 읽기 완료 / 원 계산: 완료 / 새 솔버 계산: 미실행' in view.status.text()
        assert '공학 적합성: 미확인' in view.status.text() and view.table.rowCount()==150
        assert view.selected==select_history(value,view.selected['selection']['request'])
        assert value==before and path.read_bytes()==original_bytes
        assert view.grab().save(str(tmp_path/'actual-readback-narrow.png'))
    finally:close(view,app)


def test_actual_retained150_exact_tail_support_signals_and_render(app,tmp_path,monkeypatch):
    import hashlib
    from caelab.workbench_client import Client
    path=Path(__file__).resolve().parents[1]/'_workspace/impact-history-selection-20261018/read-owner-01/snapshot.json'
    if not path.exists():pytest.skip('Actual retained snapshot is private evidence')
    before_file=hashlib.sha256(path.read_bytes()).hexdigest()
    original=json.loads(path.read_text(encoding='utf-8'));before=deepcopy(original)
    def forbidden(*a,**k):raise AssertionError('Actual retained reader cannot instantiate a Core client')
    monkeypatch.setattr(Client,'__init__',forbidden)
    view=ImpactHistoryView(original)
    try:
        view.show();view.channel.setCurrentIndex(view.channel.findData('PAIR_force_FNZ'));app.processEvents()
        assert view.table.rowCount()==150
        times=original['result']['responses']['PAIR_force_FNZ']['raw_samples']['transformed_axis']
        assert view.end.currentData()==times[-1] and times[-1]!=.003
        view.start.setCurrentIndex(1);app.processEvents()
        expected=select_history(original,{'response':'PAIR_force_FNZ','start_s':times[1],
            'end_s':times[-1],'side':'native','transform':'identity'})
        assert view.selected==expected
        assert any(r['support_crosses_selection'] for r in view.selected['rows'])
        assert view.selected['selection']['semantics']['conversion_kind']=='DERIVED_SECANT'
        assert view.selected['selection']['semantics']['display_scale_from_native'] is None
        assert '원 누적 충격량 차이 [N s] / 실제 원 구간 시간 [s]' in view.meaning.text()
        assert '→ 표시 N (배율' not in view.meaning.text()
        for w,h,name in [(1180,850,'actual-mean-force-normal.png'),(800,715,'actual-mean-force-narrow.png')]:
            view.resize(w,h);app.processEvents();assert view.grab().save(str(tmp_path/name))
        view.table.selectRow(12);view.table.setFocus();QTest.keyClick(view.table,Qt.Key.Key_Down)
        assert view.table.currentRow()==13
        view.transform.setCurrentIndex(1);app.processEvents()
        assert view.table.currentRow()==13
        integral=view.selected
        assert integral['response']['unit']=='N s' and not integral['response']['metadata']['exact_solver_impulse']
        assert integral['selection']['semantics']['conversion_kind']=='DERIVED_SAMPLE_TRAPEZOID'
        assert integral['selection']['semantics']['display_scale_from_native'] is None
        for w,h,name in [(1180,850,'actual-sample-integral-normal.png'),(800,715,'actual-sample-integral-narrow.png')]:
            view.resize(w,h);app.processEvents()
            rect=view.table.visualItemRect(view.table.item(view.table.currentRow(),0))
            assert rect.bottom()<=view.table.viewport().height() and rect.top()>=0
            assert view.grab().save(str(tmp_path/name))
        view.channel.setCurrentIndex(view.channel.findData('PAIR_native_impulse_FNZ'));app.processEvents()
        assert view.transform.currentData()=='identity'
        exact=view.selected
        assert exact==select_history(original,exact['selection']['request'])
        view.study_requested.connect(lambda p: packets.append(p))
        view.plan_requested.connect(lambda p: packets.append(p))
        packets=[]
        QTest.mouseClick(view.study_button,Qt.MouseButton.LeftButton)
        QTest.mouseClick(view.plan_button,Qt.MouseButton.LeftButton)
        assert packets==[exact,exact]
        for w,h,name in [(1180,850,'actual-native-impulse-normal.png'),(800,715,'actual-native-impulse-narrow.png')]:
            view.resize(w,h);app.processEvents();assert view.grab().save(str(tmp_path/name))
        # Simulate a stale/impossible endpoint; the reader must reject, not clamp.
        view.end.addItem('요청 끝 .003 (보존 표본 없음)',.003);view.end.setCurrentIndex(view.end.count()-1)
        app.processEvents();assert view.selected is None and '실제 표본' in view.message.text()
        assert not view.plan_button.isEnabled()
        assert view.grab().save(str(tmp_path/'actual-invalid-endpoint.png'))
        view.end.setCurrentIndex(view.end.findData(times[-1]));app.processEvents()
        assert view.selected==exact
        view.channel.setCurrentIndex(view.channel.findData('global_6'));app.processEvents()
        assert '초기 질량과 구별' in view.meaning.text()
        assert 'Mg' in view.meaning.text() and 'kg' in view.meaning.text()
        assert view.grab().save(str(tmp_path/'actual-current-mass-narrow.png'))
        assert original==before and hashlib.sha256(path.read_bytes()).hexdigest()==before_file
        (tmp_path/'receipt.json').write_text(json.dumps({'status':'PASS','qt_platform':app.platformName(),
            'source':original['source'],'snapshot_sha256':before_file,'actual_pair_samples':150,
            'actual_tail_s':times[-1],'same_packet_two_signals':True,'snapshot_unchanged':True,
            'new_core_commands':0,'new_jobs_native_provider':0},ensure_ascii=False,indent=2),encoding='utf-8')
    finally:close(view,app)
