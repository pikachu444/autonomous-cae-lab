"""Offscreen existing-job UI checks with retained-record fixtures, not solver evidence."""
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from copy import deepcopy
import hashlib
import threading
import time

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("matplotlib")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from apps.research.runner_window import RunnerWindow


def job(identifier, operation="evaluate", state="SUCCEEDED"):
    return {"id": identifier, "job_id": identifier, "operation": operation,
            "state": state, "arguments": {"backend": "material.felupe",
                "label": "Frozen " + identifier, "settings": {"parameters": {"E": 1234}}},
            "created_utc": "2026-10-11T01:00:00Z", "started_utc": "2026-10-11T01:00:01Z",
            "finished_utc": "2026-10-11T01:00:03Z" if state == "SUCCEEDED" else None,
            "resources": {"threads": 2, "memory_mb": 512},
            "resource_enforcement": {"cpu": "HINT_ONLY", "memory": "HINT_ONLY"},
            "request_id": "original-request-" + identifier, "request_hash": "input-hash-" + identifier,
            "result_refs": ["retained/" + identifier] if state == "SUCCEEDED" else []}


def series(values):
    return {"kind": "series", "unit": "MPa", "value": values,
            "axes": [{"name": "time", "unit": "s", "values": list(range(len(values)))}],
            "mask": [True] * len(values), "component": "xx", "location": "material_point",
            "frame": "laboratory", "measure": "infinitesimal_Cauchy", "valid": True}


class RecordsClient:
    def __init__(self):
        self.jobs = {"JA": job("JA"), "JB": job("JB"), "JF": job("JF", "fit", "RUNNING")}
        self.results = {identifier: {"execution_status": "SUCCEEDED", "responses": {
            "stress_xx": series(values)}, "diagnostics": {"source": "TEST_ONLY_RETAINED_RECORD"}}
            for identifier, values in (("JA", [0., 2., 4., 6.]), ("JB", [0., 9.]))}
        self.calls, self.thread_ids, self.blockers = [], [], {}

    def _read(self, operation, identifier=None, selection=None):
        self.calls.append((operation, identifier, deepcopy(selection)))
        self.thread_ids.append(threading.get_ident())
        blocker = self.blockers.get((operation, identifier))
        if blocker:
            assert blocker.wait(4), "Test did not release the queued service response"

    def job_navigation(self, identifier):
        self._read("navigation", identifier)
        return {"origin_document": {"id":"Dmaterial", "kind":"material", "connected":True}, "post_input":None}

    def request(self, path):
        assert path == "/api/workbench"
        self._read("catalog")
        return {"jobs": deepcopy(list(self.jobs.values()))}

    def status(self, identifier):
        self._read("status", identifier)
        return deepcopy(self.jobs[identifier])

    def result(self, identifier, *, selection):
        self._read("metadata" if selection.get("metadata_only") else "response", identifier, selection)
        result = deepcopy(self.results[identifier])
        if selection.get("metadata_only"):
            for response in result.get("responses", {}).values():
                if response.get("kind") == "series":
                    length = len(response.pop("value"))
                    response["data_ref"] = {"path": "arrays/stress.npy", "sha256": "retained-array-hash", "shape": [length]}
                    response.pop("mask")
                    response["mask_ref"] = {"path": "arrays/mask.npy", "sha256": "retained-mask-hash", "shape": [length]}
                    for axis in response["axes"]:
                        axis.pop("values")
                        axis["data_ref"] = {"path": "arrays/time.npy", "sha256": "retained-axis-hash", "shape": [length]}
            return result
        result["responses"] = {name: value for name, value in result.get("responses", {}).items() if name in selection["responses"]}
        if "rows" in selection:
            start, stop = selection["rows"]
            for response in result["responses"].values():
                response["value"] = response["value"][start:stop]
                response["mask"] = response["mask"][start:stop]
                response["axes"][0]["values"] = response["axes"][0]["values"][start:stop]
        return result

    def cancel(self, identifier):
        self._read("cancel", identifier)
        self.jobs[identifier]["state"] = "CANCEL_REQUESTED"
        self.jobs[identifier]["cancel_requested"] = True
        return deepcopy(self.jobs[identifier])

    def submit(self, *args, **kwargs):
        raise AssertionError("Existing-job navigation must never submit a calculation")


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def until(app, condition):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents()
        if condition():
            return
        QTest.qWait(10)
    raise AssertionError("Queued Runner reply did not arrive")


@pytest.fixture
def runner(app):
    client = RecordsClient()
    origins = []
    viewer = RunnerWindow(client, job_id="JA", poll_interval=0, on_open_origin=origins.append)
    until(app, lambda: viewer.selected_job_id == "JA" and not viewer._pending)
    yield viewer, client, origins
    for blocker in client.blockers.values():
        blocker.set()
    until(app, lambda: not viewer._pending)
    viewer.close()
    app.processEvents()


def select_row(viewer, identifier):
    for row in range(viewer.job_table.rowCount()):
        if viewer.job_table.item(row, 0).data(Qt.ItemDataRole.UserRole) == identifier:
            viewer.job_table.selectRow(row)
            return
    raise AssertionError(identifier)


def test_existing_selection_reads_frozen_inputs_and_bounded_original_rows(runner, app):
    viewer, client, _ = runner
    assert viewer.monitor_fields["Input hash"].text() == "input-hash-JA"
    assert "HINT_ONLY" in viewer.monitor_fields["Enforcement"].text()
    assert viewer.monitor_fields["Host"].text() == "기록 없음"
    assert viewer.job_table.isColumnHidden(1)
    assert viewer.monitor_fields["Input hash"].parentWidget() is viewer.technical_panel
    assert viewer.monitor_fields["Started UTC"].text() == "2026-10-11 01:00:01"
    assert viewer.monitor_fields["Resources"].text() == "CPU 스레드 2, 메모리(MB) 512"
    assert viewer.inputs.findItems("실행 입력", Qt.MatchFlag.MatchExactly)[0].child(2).child(0).child(0).text(1) == "1234"
    assert not [call for call in client.calls if call[0] in {"metadata", "response", "cancel"}]
    viewer.result_button.click()
    until(app, lambda: viewer.values.rowCount() == 4 and not viewer._pending)
    viewer.row_start.setValue(1)
    viewer.row_count.setValue(2)
    viewer.read_rows_button.click()
    until(app, lambda: viewer.values.rowCount() == 2 and not viewer._pending)
    assert client.calls[-1] == ("response", "JA", {"responses": ["stress_xx"], "rows": [1, 3]})
    assert viewer.values.item(0, 0).text() == "1"
    assert viewer.values.item(0, 2).text() == "2.0 MPa"
    assert list(viewer.axes.lines[0].get_ydata()) == [2., 4.]
    assert viewer.axes.get_xlabel() == "시간 [s]"
    assert "미소변형 Cauchy 응력" in viewer.response_label.text()
    assert "infinitesimal_Cauchy" in viewer.response_details.toPlainText()
    assert all(identifier != threading.get_ident() for identifier in client.thread_ids)


@pytest.mark.parametrize("blocked_operation", ["metadata", "response"])
def test_late_result_cannot_replace_another_selected_job(runner, app, blocked_operation):
    viewer, client, _ = runner
    gate = client.blockers[(blocked_operation, "JA")] = threading.Event()
    viewer.result_button.click()
    until(app, lambda: any(call[:2] == (blocked_operation, "JA") for call in client.calls))
    select_row(viewer, "JB")
    until(app, lambda: viewer.selected_job_id == "JB" and not any(key.startswith("status:JB:") for key in viewer._pending))
    viewer.result_button.click()
    until(app, lambda: viewer.values.rowCount() == 2 and "JB" in viewer.result_summary.text())
    gate.set()
    until(app, lambda: not viewer._pending)
    assert viewer.selected_job_id == "JB"
    assert list(viewer.axes.lines[0].get_ydata()) == [0., 9.]
    assert "JB" in viewer.result_summary.text()
    assert viewer.monitor_fields["Input hash"].text() == "input-hash-JB"


def test_parent_cancel_is_request_then_cleanup_then_terminal_and_other_job_stays_live(runner, app):
    viewer, client, _ = runner
    select_row(viewer, "JF")
    until(app, lambda: not viewer._pending)
    assert viewer.cancel_button.text() == "전체 계산 취소"
    assert "개별 후보만 취소할 수는 없습니다" in viewer.scope_label.text()
    viewer.cancel_button.click()
    until(app, lambda: not viewer._pending)
    assert "취소 요청됨" in viewer.state_label.text()
    assert not viewer.cancel_button.isEnabled()
    assert client.jobs["JB"]["state"] == "SUCCEEDED"
    client.jobs["JF"].update(state="CLEANUP_PENDING", cleanup_unconfirmed=True)
    viewer.refresh_action.trigger()
    until(app, lambda: not viewer._pending)
    assert "프로세스 종료 미확인" in viewer.state_label.text()
    assert viewer.cancel_button.text() == "종료 처리 다시 시도"
    client.jobs["JF"].update(state="CANCELLED", cleanup_unconfirmed=False)
    viewer.refresh_action.trigger()
    until(app, lambda: not viewer._pending)
    assert "실행 서비스에서 종료를 확인했습니다" in viewer.state_label.text()
    assert not viewer.cancel_button.isEnabled()
    assert [call[1] for call in client.calls if call[0] == "cancel"] == ["JF"]


def test_partial_candidate_penalty_and_unsupported_field_remain_explicit(runner, app):
    viewer, client, _ = runner
    client.results["JA"] = {"execution_status": "PARTIAL_FAILURE", "failure_reason": "One candidate failed",
        "responses": {"stress_field": {"kind": "field", "unit": "MPa", "component": "xx",
            "data_ref": {"path": "arrays/field.npy", "shape": [8, 3], "sha256": "retained-field-hash"}}},
        "candidates": [
            {"candidate_id": "C0", "execution_status": "SUCCEEDED", "values": {"E": 1234}, "objective": .25},
            {"candidate_id": "C1", "execution_status": "FAILED", "values": {"E": -1}, "objective": 1e6,
             "penalty_applied": 1e6, "failure_reason": "Invalid modulus", "responses": {}},
            {"candidate_id": "C2", "execution_status": "SUCCEEDED", "prediction_status": "PREDICTED",
             "values": {"E": 1200}, "objective": .1, "responses": {}},
        ]}
    viewer.result_button.click()
    until(app, lambda: viewer.ledger_table.rowCount() == 3 and not viewer._pending)
    assert "전체 계산이 완료된 결과가 아닙니다" in viewer.result_summary.text()
    assert viewer.ledger_table.item(0, 3).text() == "0.25"
    assert viewer.ledger_table.item(1, 3).text() == "—"
    assert viewer.ledger_table.item(1, 4).text() == "1000000.0"
    assert viewer.ledger_table.item(1, 5).text() == "1000000.0"
    assert viewer.ledger_table.item(1, 6).text() == "Invalid modulus"
    assert "예측값" in viewer.ledger_table.item(2, 1).text()
    assert viewer.ledger_table.item(2, 3).text() == "—"
    assert viewer.ledger_table.item(2, 5).text() == "0.1"
    assert client.results["JA"]["candidates"][2]["execution_status"] == "SUCCEEDED"
    assert "retained-field-hash" in viewer.response_details.toPlainText()
    assert not viewer.axes.lines and not viewer.read_rows_button.isEnabled()
    assert not any(call[0] == "response" for call in client.calls)


def test_refresh_and_close_reopen_preserve_selection_and_origin_without_submit(runner, app):
    viewer, client, origins = runner
    select_row(viewer, "JB")
    until(app, lambda: not viewer._pending)
    client.jobs["JNEW"] = job("JNEW")
    viewer.refresh_action.trigger()
    until(app, lambda: not viewer._pending)
    assert viewer.selected_job_id == "JB"
    assert viewer.job_table.item(viewer.job_table.currentRow(), 1).text() == "JB"
    viewer.origin_button.click()
    until(app, lambda: not viewer._pending)
    assert origins == ["JB"]
    viewer.close()
    client.jobs["JB"]["state"] = "INTERRUPTED"
    viewer.show()
    until(app, lambda: not viewer._pending and "추적 중단" in viewer.state_label.text())
    assert viewer.selected_job_id == "JB"
    assert "프로세스 종료 미확인" in viewer.state_label.text()
    assert not any(call[0] == "cancel" for call in client.calls)


def test_late_cancel_does_not_replace_selected_job_message(runner, app):
    viewer, client, _ = runner
    select_row(viewer, "JF")
    until(app, lambda: not viewer._pending)
    gate = client.blockers[("cancel", "JF")] = threading.Event()
    viewer.cancel_button.click()
    until(app, lambda: any(call[:2] == ("cancel", "JF") for call in client.calls))
    select_row(viewer, "JB")
    until(app, lambda: not any(key.startswith("status:JB:") for key in viewer._pending))
    message = viewer.message.text()
    gate.set()
    until(app, lambda: not viewer._pending)
    assert viewer.message.text() == message
    assert viewer.selected_job_id == "JB"
    assert viewer.state_label.text() == "완료"
    assert client.jobs["JF"]["state"] == "CANCEL_REQUESTED"


def test_reopening_drops_prior_result_read_without_resubmitting(runner, app):
    viewer, client, _ = runner
    gate = client.blockers[("metadata", "JA")] = threading.Event()
    viewer.read_result()
    until(app, lambda: any(call[:2] == ("metadata", "JA") for call in client.calls))
    viewer.close()
    viewer.show()
    gate.set()
    until(app, lambda: not viewer._workers)
    assert viewer.result_metadata is None
    assert viewer.result_button.isEnabled()
    viewer.read_result()
    until(app, lambda: viewer.values.rowCount() == 4 and not viewer._pending)
    assert viewer.selected_job_id == "JA"
    assert not any(call[0] == "cancel" for call in client.calls)


def test_late_origin_launch_receipt_does_not_replace_selected_job_message(runner, app, monkeypatch):
    from apps.research import desktop
    viewer, client, _ = runner
    client.job_navigation = lambda identifier: {"origin_document": {"kind": "simulation", "id": "DA"}}
    started, gate = threading.Event(), threading.Event()
    launched = []
    def open_origin(client, identifier):
        launched.append(identifier)
        started.set()
        assert gate.wait(4)
        return {"status": "launched"}
    monkeypatch.setattr(desktop, "open_origin", open_origin)
    viewer.origin_button.click()
    until(app, started.is_set)
    select_row(viewer, "JB")
    until(app, lambda: not any(key.startswith("status:JB:") for key in viewer._pending))
    message = viewer.message.text()
    gate.set()
    until(app, lambda: not viewer._pending)
    assert launched == ["JA"]
    assert viewer.message.text() == message
    assert viewer.selected_job_id == "JB"


@pytest.mark.parametrize("status, message", [
    ("LAUNCH_REQUESTED", "선택한 작업의 원본 입력 열기를 요청했습니다."),
    ("ACTIVATED", "선택한 작업의 원본 입력을 열었습니다."),
])
def test_origin_launch_request_is_distinct_from_shown_document(runner, app, monkeypatch, status, message):
    from apps.research import desktop
    viewer, client, _ = runner
    client.job_navigation = lambda identifier: {"origin_document": {"kind": "simulation", "id": "DA"}}
    monkeypatch.setattr(desktop, "open_origin", lambda client, identifier: {"status": status})
    viewer.origin_button.click()
    until(app, lambda: not viewer._pending)
    assert viewer.message.text() == message


class MonitorClient(RecordsClient):
    def __init__(self):
        super().__init__()
        self.logs={identifier:{'stdout':f'{identifier} start\nWARNING native warning\nERROR native failure\nend\n',
                               'stderr':f'{identifier} original stderr\n'} for identifier in self.jobs}
        self.executions=[{'id':'Eretained','label':'CalculiX','status':'FAILED',
            'started_utc':'2026-10-11T01:00:01Z','finished_utc':'2026-10-11T01:00:03Z','return_code':201}]

    def job_monitor(self,identifier,*,log=None,offset=0,limit=65536):
        self._read('monitor',identifier,{'log':log,'offset':offset,'limit':limit})
        sources=self.logs[identifier]
        if log is not None and log not in sources:raise ValueError('The selected log is not available in this job catalog')
        catalog=[{'id':key,'label':key,'bytes':len(text.encode())} for key,text in sources.items()]
        selected=None
        if sources:
            key=log or next(iter(sources));raw=sources[key].encode();chunk=raw[offset:offset+limit]
            selected={'id':key,'text':chunk.decode(),'offset':offset,'next_offset':offset+len(chunk),
                      'total_bytes':len(raw),'truncated':offset+len(chunk)<len(raw),
                      'chunk_sha256':hashlib.sha256(chunk).hexdigest()}
        return {'job_id':identifier,'state':self.jobs[identifier]['state'],'phase':'FINISHED','progress':None,
            'executions':deepcopy(self.executions),'logs':catalog,'selected_log':selected,
            'errors':[deepcopy(self.jobs[identifier]['error'])] if self.jobs[identifier].get('error') else [],'warnings':[]}


@pytest.fixture
def monitor_runner(app):
    client=MonitorClient();viewer=RunnerWindow(client,job_id='JA',poll_interval=0)
    until(app,lambda:viewer.selected_job_id=='JA' and not viewer._pending)
    yield viewer,client
    for gate in client.blockers.values():gate.set()
    until(app,lambda:not viewer._workers)
    viewer.close();app.processEvents()


def test_monitor_shows_actual_execution_code_and_searches_the_unchanged_raw_log(monitor_runner,app):
    viewer,client=monitor_runner;before=deepcopy(client.logs)
    assert viewer.progress_table.item(0,0).text()=='CalculiX'
    assert viewer.progress_table.item(0,4).text()=='201'
    assert '보고되지 않았습니다' in viewer.progress_summary.text() and '%' not in viewer.progress_summary.text()
    assert viewer.log_text.toPlainText()==client.logs['JA']['stdout']
    viewer.log_error.click();assert viewer.log_text.textCursor().selectedText()=='ERROR'
    viewer.log_warning.click();assert viewer.log_text.textCursor().selectedText()=='WARNING'
    viewer.log_search.setText('native');viewer.log_next.click()
    assert viewer.log_text.textCursor().selectedText()=='native'
    selected=viewer.log_text.textCursor().selectionStart()
    viewer.refresh_selected();until(app,lambda:not viewer._pending)
    assert viewer.log_text.textCursor().selectionStart()==selected
    assert viewer.log_text.textCursor().selectedText()=='native'
    assert client.logs==before and not any(call[0] in {'cancel','metadata','response'} for call in client.calls)


def test_windows_log_line_endings_keep_raw_chunk_and_selection_on_poll(monitor_runner,app):
    viewer,client=monitor_runner
    raw='CalculiX start\r\nWARNING native warning\r\nend\n'
    client.logs['JA']['stdout']=raw
    viewer.log_refresh.click();until(app,lambda:not viewer._pending)
    assert viewer._monitor['selected_log']['text']==raw
    assert viewer.log_text.toPlainText()==raw.replace('\r\n','\n')
    viewer.log_search.setText('native');viewer.find_log()
    selection=viewer.log_text.textCursor().selectionStart()
    viewer.refresh_selected();until(app,lambda:not viewer._pending)
    assert viewer.log_text.textCursor().selectedText()=='native'
    assert viewer.log_text.textCursor().selectionStart()==selection
    assert viewer._monitor['selected_log']['text']==raw
    assert client.logs['JA']['stdout']==raw


@pytest.mark.parametrize('refused',[False,True])
def test_log_switch_does_not_show_the_previous_log_under_a_new_selector(monitor_runner,app,refused):
    viewer,client=monitor_runner;reader=client.job_monitor
    gate=threading.Event();started=threading.Event()
    def delayed(identifier,**options):
        payload=reader(identifier,**options)
        if options.get('log')=='stderr':
            started.set();assert gate.wait(4)
            if refused:raise ValueError('Controlled stderr read refusal')
        return payload
    client.job_monitor=delayed
    try:
        assert viewer._monitor['selected_log']['id']=='stdout'
        viewer.log_source.setCurrentIndex(viewer.log_source.findData('stderr'))
        until(app,started.is_set)
        assert viewer.log_source.currentData()=='stderr'
        assert viewer.log_text.toPlainText()=='' and viewer._monitor['selected_log'] is None
        assert viewer.log_note.toolTip()=='' and not viewer.log_next.isEnabled()
        assert not viewer.log_earlier.isEnabled() and not viewer.log_later.isEnabled()
        if refused:
            gate.set();until(app,lambda:not viewer._pending)
            assert viewer.log_text.toPlainText()=='' and '이전에 읽은' not in viewer.log_note.text()
        viewer.log_source.setCurrentIndex(viewer.log_source.findData('stdout'))
        until(app,lambda:(viewer._monitor or {}).get('selected_log') is not None)
        viewer.log_search.setText('native');viewer.find_log()
        gate.set();until(app,lambda:not viewer._pending)
        assert viewer.log_source.currentData()=='stdout'
        assert viewer._monitor['selected_log']['id']=='stdout'
        assert viewer.log_text.toPlainText()==client.logs['JA']['stdout']
        assert viewer.log_text.textCursor().selectedText()=='native'
    finally:
        gate.set()


def test_late_log_reply_cannot_replace_a_different_selected_job(monitor_runner,app):
    viewer,client=monitor_runner
    gate=client.blockers[('monitor','JA')]=threading.Event()
    count=sum(call[:2]==('monitor','JA') for call in client.calls)
    viewer.log_refresh.click()
    until(app,lambda:sum(call[:2]==('monitor','JA') for call in client.calls)>count)
    viewer.select_job('JB');until(app,lambda:viewer.log_text.toPlainText()==client.logs['JB']['stdout'])
    gate.set();until(app,lambda:not viewer._pending)
    assert viewer.selected_job_id=='JB' and viewer.log_text.toPlainText()==client.logs['JB']['stdout']


def test_bounded_log_navigation_and_a_later_missing_log_do_not_keep_old_content(monitor_runner,app):
    viewer,client=monitor_runner
    raw='first\n'+'x'*70000+'\nlast\n';client.logs['JA']={'stdout':raw}
    viewer.log_refresh.click();until(app,lambda:not viewer._pending)
    assert viewer.log_text.toPlainText()==raw[:65536] and viewer.log_later.isEnabled()
    viewer.log_later.click();until(app,lambda:not viewer._pending)
    assert viewer.log_text.toPlainText()==raw[65536:] and viewer.log_earlier.isEnabled()
    viewer.log_earlier.click();until(app,lambda:not viewer._pending)
    assert viewer.log_text.toPlainText()==raw[:65536]
    client.logs['JA']={};client.executions=[]
    viewer.refresh_selected();until(app,lambda:not viewer._pending)
    assert viewer.log_text.toPlainText()==raw[:65536] and '이전에 읽은' in viewer.log_note.text()
    viewer.log_refresh.click();until(app,lambda:not viewer._pending)
    assert viewer.log_text.toPlainText()=='' and not viewer.log_source.isEnabled()
    assert not viewer.log_error.isEnabled() and not viewer.log_later.isEnabled()
    assert viewer.progress_table.item(0,1).text()=='아직 보고되지 않음'
    original_reader=client.job_monitor
    def limited(*args,**kwargs):
        return {**original_reader(*args,**kwargs),'catalog_truncated':True}
    client.job_monitor=limited
    viewer.log_refresh.click();until(app,lambda:not viewer._pending)
    assert '읽기 한도' in viewer.log_note.text() and '아직 제공되지' not in viewer.log_note.text()


def test_scalar_and_spatial_results_use_their_own_work_surface_without_a_blank_plot(runner,app):
    viewer,client,_=runner
    client.results['JA']={'execution_status':'SUCCEEDED','responses':{
        'energy':{'kind':'scalar','unit':'mJ','value':12.5}}}
    viewer.result_button.click();until(app,lambda:viewer.values.rowCount()==1 and not viewer._pending)
    assert viewer.values.item(0,2).text()=='12.5 mJ'
    assert viewer.result_views.currentWidget() is viewer.values
    assert viewer.result_views.maximumHeight()==170 and viewer.row_range_panel.isHidden()
    client.results['JA']={'execution_status':'SUCCEEDED','responses':{
        'stress':{'kind':'field','unit':'MPa','location':'native_integration_point'}}}
    viewer.result_button.click();until(app,lambda:not viewer._pending)
    assert viewer.result_views.isHidden() and not viewer.field_open_button.isHidden()
    assert viewer.field_open_button.isEnabled() and '공간 결과' in viewer.response_label.text()
    assert '원 적분점' in viewer.response_label.text()
    viewer.show();app.processEvents()
    assert viewer.response_controls.y()-viewer.result_summary.geometry().bottom()<30
    assert viewer.field_open_button.y()-viewer.response_label.geometry().bottom()<30
    client.results['JA']['responses']={'사용자 응력':{
        'kind':'field','unit':'MPa','location':'calculix_export_nodes'}}
    viewer.result_button.click();until(app,lambda:not viewer._pending)
    assert viewer.responses.currentData()=='사용자 응력' and '사용자 응력' in viewer.response_label.text()
    assert '내보낸 절점값' in viewer.response_label.text() and 'calculix_export_nodes' not in viewer.response_label.text()
    assert 'calculix_export_nodes' in viewer.response_label.toolTip()
    assert 'calculix_export_nodes' in viewer.response_details.toPlainText()
    client.results['JA']={'execution_status':'SUCCEEDED','prediction_status':'PREDICTED',
        'responses':{'energy':{'kind':'scalar','unit':'mJ','value':.1}}}
    viewer.result_button.click();until(app,lambda:not viewer._pending)
    assert '예측값 (실제 평가 결과 아님)' in viewer.result_summary.text()
