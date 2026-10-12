"""Bounded Report/Acquisition Qt checks; no live device or production execution.

Use existing PySide6:
  py -3.13 qt_complete_acceptance.py --source . --output C:/Review/complete-check
No package installation, provider, solver, device or external service is used.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
from unittest.mock import patch

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source",type=Path,required=True)
parser.add_argument("--output",type=Path,required=True)
parser.add_argument("--cold",choices=["report","acquisition"])
parser.add_argument("--file",type=Path)
args=parser.parse_args()
os.environ["QT_QPA_PLATFORM"]="offscreen"
sys.path.insert(0,str(args.source.resolve()))
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLineEdit,QComboBox,QDialog,QDialogButtonBox,QFileDialog,QMessageBox
import PySide6
import prototype_state as state
import qt_prototype as prototype
app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)
prototype.configure_application_fonts(app)
app.setStyle("Fusion");app.setStyleSheet(prototype.STYLE)
errors=[]
sys.excepthook=lambda kind,value,tb:errors.append("".join(traceback.format_exception(kind,value,tb)))
args.output.mkdir(parents=True,exist_ok=True)

def pump():
    app.processEvents();QTest.qWait(10);app.processEvents()

def edit_line(editor,value):
    editor.setFocus();QTest.keyClick(editor,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(editor,value);QTest.keyClick(editor,Qt.Key.Key_Return);pump()

def edit_cell(table,row,column,value):
    window=table.window();window.raise_();window.activateWindow();pump()
    table.scrollToItem(table.item(row,column))
    table.setCurrentCell(row,column);table.setFocus();QTest.keyClick(table,Qt.Key.Key_F2);pump()
    editor=app.focusWidget();assert isinstance(editor,QLineEdit),"Engineering text delegate missing"
    edit_line(editor,value)

def ordinary_save(window,path):
    window.raise_();window.activateWindow();window.setFocus();pump()
    with patch.object(QFileDialog,"getSaveFileName",return_value=(str(path),"Review document (*.json)")):
        QTest.keyClick(window,Qt.Key.Key_S,Qt.KeyboardModifier.ControlModifier);pump()
    assert path.exists(),"Ordinary Ctrl+S did not write the review document"
    return json.loads(path.read_text(encoding="utf-8"))

def modal(action,edit,accept=True):
    failures=[];visited=[]
    def fill():
        dialog=app.activeModalWidget()
        try:
            assert isinstance(dialog,QDialog),"Expected native Qt dialog"
            edit(dialog);visited.append(True)
            buttons=dialog.findChild(QDialogButtonBox)
            target=QDialogButtonBox.StandardButton.Ok if accept else QDialogButtonBox.StandardButton.Cancel
            QTest.mouseClick(buttons.button(target),Qt.MouseButton.LeftButton)
        except Exception:
            failures.append(traceback.format_exc())
            if dialog:dialog.reject()
    timer=QTimer();timer.setSingleShot(True)
    def timeout():
        failures.append("Dialog timeout")
        if app.activeModalWidget():app.activeModalWidget().reject()
    timer.timeout.connect(timeout);timer.start(4000);QTimer.singleShot(0,fill)
    try:action()
    finally:timer.stop()
    pump();assert visited and not failures,str(failures)

def cold(tool,path):
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),"--source",str(args.source.resolve()),
        "--output",str(args.output.resolve()),"--cold",tool,"--file",str(path.resolve())],
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+"\n"+result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])

if args.cold:
    session=state.ReviewSession();key=session.open_document(args.file)
    hub=prototype.DesktopHub(session);window=hub.open(key);window.resize(1440,900);pump()
    raw=json.loads(args.file.read_text(encoding="utf-8"))["document"]["draft"]
    assert window.data==raw
    if args.cold=="report":
        assert window.data["study_document"]["saved"]["question"]
        assert window.data["sections"]==raw["sections"]
        assert any(s["kind"]=="curve" for s in window.pages())
        assert window.data["evidence"]
    else:
        assert window.data["sample_rate"]==500.0
        assert window.data["time_offset"]==-1.2e-5
        assert window.current_channel()["unit"]=="kN"
        assert window.curve.series[0]["x"][0]==-1.2e-5
        assert window.data["stop_ack"]=="NOT_RECEIVED"
        assert not session.jobs
    window.grab().save(str(args.output/(args.cold+"-cold.png")))
    assert not errors,errors
    print(json.dumps({"tool":args.cold,"cold_reopen":"PASS","callback_errors":errors}))
    raise SystemExit(0)

workspace=Path(tempfile.mkdtemp(prefix="caelab-completion-",dir=args.output))
results=[];hubs=[]
def run(name,function):
    start=len(errors)
    try:
        details=function()
        assert len(errors)==start,errors[start:]
        results.append({"name":name,"status":"PASS","details":details})
    except Exception:
        results.append({"name":name,"status":"FAIL","trace":traceback.format_exc(),"callback_errors":errors[start:]})

def report_check():
    session=state.ReviewSession(workspace/"report");hub=prototype.DesktopHub(session);hubs.append(hub)
    window=hub.open("report");window.resize(1440,900);pump()
    source=state.clone(session.doc("study")["saved"])
    window.section_list.setCurrentRow(0);pump()
    edit_line(window.heading,"Test question")
    window.text_editor.setFocus();QTest.keyClick(window.text_editor,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(window.text_editor,"How much of the displacement comes from the fixture?");pump()
    original=[s["id"] for s in window.data["sections"]]
    window.move_section(1);pump()
    moved=[s["id"] for s in window.data["sections"]]
    assert moved[1]=="question" and moved!=original
    window.undo(False);pump();assert [s["id"] for s in window.data["sections"]]==original
    window.undo(True);pump();assert [s["id"] for s in window.data["sections"]]==moved
    assert [window.section_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(window.section_list.count())]==moved
    window.section_list.setCurrentRow(1);window.section_list.setFocus()
    QTest.keyClick(window.section_list,Qt.Key.Key_Space);pump()
    assert next(s for s in window.data["sections"] if s["id"]=="question")["enabled"] is False
    window.tabs.setCurrentIndex(1);pump();assert window.output_dock.isVisible()
    pdf=workspace/"Report preview.pdf";window.export_to(pdf)
    content=pdf.read_bytes();assert content.startswith(b"%PDF-") and b"%%EOF" in content[-256:]
    window.output_format.setCurrentText("Markdown");pump()
    markdown=workspace/"Report preview.md";window.export_to(markdown)
    text=markdown.read_text(encoding="utf-8")
    assert "0.31" in text and "NOT_EVALUATED" in text and "F05" not in text
    assert "Selection: Gauge / t = 0.04 s" in text and "Study: " in text and "Result: " in text
    rid=window.data["evidence"][0]["ref"];retained=session.results.pop(rid)
    try:
        try:window.export_to(workspace/"Missing.md")
        except state.ReviewError:pass
        else:raise AssertionError("Missing evidence export was accepted under Block export")
        window.missing_policy.setCurrentText("Include unavailable placeholder");pump()
        window.export_to(workspace/"Unavailable.md")
        assert "Evidence unavailable" in (workspace/"Unavailable.md").read_text(encoding="utf-8")
    finally:session.results[rid]=retained
    path=workspace/"Clamp report.json";ordinary_save(window,path)
    assert session.doc("study")["saved"]==source,"Report editing changed its Study"
    window.grab().save(str(args.output/"report-preview.png"))
    reopened=cold("report",path)
    return {"pdf_bytes":len(content),"sections":moved,"cold":reopened,"source_unchanged":True}

def report_selection_check():
    session=state.ReviewSession(workspace/"report-selection");hub=prototype.DesktopHub(session);hubs.append(hub)
    window=hub.open("report");window.resize(1440,900);study=hub.open("study");pump()
    rid="fixture-result-clamp";records=[]
    def saved_time(time):
        payload=state.clone(study.data);payload["evidence"][0]["locator"]="Gauge / t ="+str(time)+" s"
        session.change("study",payload,"Select exact retained evidence");study.refresh()
        ordinary_save(study,workspace/"Selected Study.json")
        assert window.load_study() is True
        window.section_list.setCurrentRow(0);window.tabs.setCurrentIndex(1);pump()
    for time,expected in ((0,0),(.02,.2294),(.04,.31)):
        saved_time(time)
        section=next(s for s in window.data["sections"] if s["id"]=="evidence-0")
        assert abs(section["rows"][0][1]-expected)<1e-12
        window.page_move(1);window.page_move(1);pump()
        assert window.preview.section["id"]=="curve-0"
        assert window.selected_section()["id"]=="curve-0"
        assert window.preview.section["cursor_x"]==time
        post=window.open_source();pump()
        assert post.data["time"]==time and post.data["array"]=="Displacement" and post.data["association"]=="POINTS"
        assert abs(session.post_frame(post.key)["value"]-expected)<1e-12
        assert post.data["gauge"]=={"a":"Gauge left","b":"Gauge right","direction":"X"}
        assert abs(float(post.measure.item(0,1).text())-expected)<1e-6
        window.output_format.setCurrentText("Review PDF")
        assert not window.page_layout_errors()
        pdf=workspace/("Frame "+str(time)+".pdf");window.export_to(pdf)
        assert pdf.read_bytes().startswith(b"%PDF-")
        window.output_format.setCurrentText("Markdown")
        markdown=workspace/("Frame "+str(time)+".md");window.export_to(markdown)
        content=markdown.read_text(encoding="utf-8")
        assert "| Displacement | "+str(section["rows"][0][1])+" | mm |" in content
        assert "Selection: Gauge / t ="+str(time)+" s" in content
        assert "Study: "+study.document["id"] in content and "Result: "+rid in content
        assert "F05" not in content
        records.append({"time":time,"value":section["rows"][0][1],"pdf_bytes":pdf.stat().st_size})
    saved_time(.03)
    section=next(s for s in window.data["sections"] if s["id"]=="evidence-0")
    assert section["unavailable"] and not any(s["id"]=="curve-0" for s in window.data["sections"])
    window.section_list.setCurrentRow(1);pump()
    try:window.open_source()
    except state.ReviewError:pass
    else:raise AssertionError("Missing .03 frame was replaced with another frame")
    try:window.export_to(workspace/"Absent frame.md")
    except state.ReviewError:pass
    else:raise AssertionError("Unavailable frame passed Block export")
    saved_time(.02)
    window.section_list.setCurrentRow(0);window.tabs.setCurrentIndex(0);pump()
    window.text_editor.setPlainText("Retain this edited question and local notes.");pump()
    before=state.clone(window.data);seen=[]
    def cancel_replace():
        message=app.activeModalWidget()
        if isinstance(message,QMessageBox):
            seen.append(message.windowTitle());QTest.mouseClick(message.button(QMessageBox.StandardButton.Cancel),Qt.MouseButton.LeftButton)
        elif message:message.reject()
    QTimer.singleShot(0,cancel_replace)
    assert window.load_study() is False and seen and window.data==before
    path=workspace/"Selected frame report.json";ordinary_save(window,path)
    reopened=cold("report",path)
    restored=state.ReviewSession();key=restored.open_document(path);other=prototype.DesktopHub(restored);hubs.append(other)
    review=other.open(key);review.section_list.setCurrentRow(1);pump()
    opened=review.open_source();assert opened.data["time"]==.02
    assert abs(restored.post_frame(opened.key)["value"]-.2294)<1e-12
    def history(dialog):
        choice=next(c for c in dialog.findChildren(QComboBox) if c.findText("Historical F05 check")>=0)
        choice.setCurrentText("Historical F05 check")
    modal(window.add_section,history)
    historical=window.selected_section()
    assert historical["source"]["kind"]=="history"
    assert historical["rows"]==[["F05",3.32295e-6,1e-6,"FAIL"]]
    window.output_format.setCurrentText("Markdown");window.export_to(workspace/"History.md")
    text=(workspace/"History.md").read_text(encoding="utf-8")
    assert "F05" in text and "Historical Task1" in text and "NOT_EVALUATED" in text
    normal=next(s for s in window.pages() if s["id"]=="question")
    assert not window.preview.layout_issues("Short title",normal)
    oversized=state.clone(normal);oversized["text"]="W"*500
    assert window.preview.layout_issues("Short title",oversized)
    oversized=state.clone(normal);oversized["source_note"]="locator "*1000
    assert window.preview.layout_issues("Short title",oversized)
    assert not session.jobs
    return {"frames":records,"absent_frame":"UNAVAILABLE","edited_replace_cancel":"PRESERVED",
            "historical_f05":"EXPLICIT_ONLY","cold":reopened}

def acquisition_check():
    session=state.ReviewSession(workspace/"acquisition");hub=prototype.DesktopHub(session);hubs.append(hub)
    window=hub.open("acquisition");window.resize(1440,900);pump()
    initial=state.clone(window.current_channel())
    def cancel_edit(dialog):
        editor=dialog.findChild(QLineEdit,"channelName");editor.setFocus()
        QTest.keyClick(editor,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier);QTest.keyClicks(editor,"Discarded")
    modal(lambda:window.channel_dialog(False),cancel_edit,False)
    assert window.current_channel()==initial,"Cancel changed the channel"
    def change_channel(dialog):
        editor=dialog.findChild(QLineEdit,"channelName")
        editor.setText("Force display")
        unit=dialog.findChild(QComboBox,"channelUnit");unit.setCurrentText("kN")
    modal(lambda:window.channel_dialog(False),change_channel)
    assert window.current_channel()["unit"]=="kN"
    assert abs(window.curve.series[0]["y"][-1]-.195)<1e-12
    edit_cell(window.settings,0,1,"1e")
    assert window.data["sample_rate"]=="1e" and window.check_plan() is False
    path=workspace/"Tension acquisition.json";saved=ordinary_save(window,path)
    assert saved["document"]["draft"]["sample_rate"]=="1e"
    edit_cell(window.settings,0,1,"5e2")
    edit_cell(window.settings,2,1,"-1.2e-5")
    assert window.check_plan() is True
    assert window.curve.series[0]["x"][0]==-1.2e-5
    window.curve_selection(["A78","A79","A80","A81","A82","A83","A84","A85"]);pump()
    selected=[window.samples.item(i.row(),0).text() for i in window.samples.selectionModel().selectedRows()]
    assert set(selected)==window.curve.selected_ids and len(selected)==8
    window.show_connection_loss();pump()
    assert window.tabs.currentIndex()==1 and window.data["stop_ack"]=="NOT_RECEIVED"
    actions={a.text():a for a in window.toolbar.actions()}
    for title in ("Connect","Start acquisition","Stop acquisition"):assert not actions[title].isEnabled()
    assert not session.jobs and window.data["allowed_control"]=="NONE"
    ordinary_save(window,path);window.grab().save(str(args.output/"acquisition-connection.png"))
    reopened=cold("acquisition",path)
    return {"unit":"kN","sample_rate":window.data["sample_rate"],"time_offset":window.data["time_offset"],
            "selected_ids":selected,"stop_ack":"NOT_RECEIVED","cold":reopened}

run("Report sections, native preview, output and cold reopen",report_check)
run("Report exact frame, page source, guarded replacement and explicit history",report_selection_check)
run("Acquisition channel, numeric draft, trace, unavailable live and cold reopen",acquisition_check)
record={"scope":"QT_OFFSCREEN_ONLY","python":sys.version.split()[0],"pyside":PySide6.__version__,
        "platform":sys.platform,"checks":results,"callback_errors":errors,"solver_executed":False,
        "provider_executed":False,"device_executed":False,"native_os_input_verified":False}
(args.output/"complete-results.json").write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(record,ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors and all(r["status"]=="PASS" for r in results) else 1)
