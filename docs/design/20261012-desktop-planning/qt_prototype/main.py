"""Standalone planning artifact. No product import, provider, optimizer or solver."""
import csv
import base64
import hashlib
import io
import json
import math
import os
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import uuid

from PySide6.QtCore import QFile, QIODevice, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QUndoCommand, QUndoStack
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHeaderView, QLabel, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QProgressBar,
    QSpinBox, QTableWidget, QTableWidgetItem, QSplitter, QWidget, QDockWidget,
)
from matplotlib import rcParams
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector

HERE = Path(__file__).resolve().parent
DISCLAIMER = "DEMO · SIMULATED UI · 물리 타당성 미검증"
EDIT_KEYS = ("active_source", "mapping", "selection", "source_contexts", "coefficients", "revision")


def stable(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def coefficient_text(value):
    return f"{value:g}" if type(value) in (int, float) else value


def numeric_coefficients(coefficients):
    if not isinstance(coefficients, dict) or set(coefficients) != {"E", "b"}:
        raise ValueError("계수 형식 오류")
    values = {}
    for key, draft in coefficients.items():
        try:
            value = float(draft)
        except (ValueError, TypeError):
            raise ValueError(f"계수 {key}: 유한 숫자로 수정하세요. 입력 초안은 보존됩니다.") from None
        if type(draft) is bool or not math.isfinite(value) or (key == "E" and value <= 0):
            raise ValueError(f"계수 {key}: {'0보다 큰 유한 숫자' if key == 'E' else '유한 숫자'}로 수정하세요. 입력 초안은 보존됩니다.")
        values[key] = value
    return values


def source_numeric_data(source, mapping):
    if not source:
        raise ValueError("시험 없음: CSV 열기 또는 데모 시험 열기를 선택하세요.")
    if mapping["x"] == mapping["y"]:
        raise ValueError("열 매핑 오류: 변형률과 응력에 서로 다른 열을 선택하세요.")
    if mapping["x_unit"] not in ("1", "%") or mapping["y_unit"] not in ("Pa", "kPa", "MPa"):
        raise ValueError("지원하지 않는 단위: 변형률 1 또는 %, 응력 Pa / kPa / MPa로 수정하세요.")
    try:
        xi, yi = source["headers"].index(mapping["x"]), source["headers"].index(mapping["y"])
        x = [float(row[xi]) / (100 if mapping["x_unit"] == "%" else 1) for row in source["rows"]]
        y = [float(row[yi]) * {"Pa": 1e-6, "kPa": .001, "MPa": 1}[mapping["y_unit"]] for row in source["rows"]]
    except (ValueError, IndexError):
        raise ValueError("숫자 또는 매핑 오류: 원파일의 결측·비수치 값과 열 이름을 확인해 다시 가져오세요.") from None
    if not all(math.isfinite(v) for v in x + y):
        raise ValueError("NaN / 무한값은 동정할 수 없습니다. 원파일을 수정해 다시 가져오세요.")
    if any(b <= a for a, b in zip(x, x[1:])):
        raise ValueError("이 시제품은 증가하는 변형률 축만 지원합니다. 열 매핑 또는 원파일을 수정하세요.")
    return x, y


def result_input_hash(result):
    retained = {key: result[key] for key in ("context", "source_sha256", "input_coefficients", "revision", "x", "observed")}
    return hashlib.sha256(stable(retained).encode("utf-8")).hexdigest()


class UiLoader(QUiLoader):
    def __init__(self, window):
        super().__init__()
        self.window = window

    def createWidget(self, class_name, parent=None, name=""):
        if class_name == "QMainWindow" and parent is None:
            self.window.setObjectName(name)
            return self.window
        return super().createWidget(class_name, parent, name)


class Edit(QUndoCommand):
    def __init__(self, window, label, after):
        super().__init__("Material: " + label)
        self.window = window
        self.before = {k: deepcopy(window.doc[k]) for k in EDIT_KEYS}
        self.after = deepcopy(after)

    def apply(self, state):
        self.window.doc.update(deepcopy(state))
        self.window.refresh()

    def redo(self):
        self.apply(self.after)

    def undo(self):
        self.apply(self.before)


class MaterialPrototype(QMainWindow):
    def __init__(self):
        super().__init__()
        ui_file = QFile(str(HERE / "material.ui"))
        if not ui_file.open(QIODevice.ReadOnly):
            raise OSError("material.ui를 열 수 없습니다")
        loader = UiLoader(self)
        if not loader.load(ui_file):
            raise RuntimeError(loader.errorString())
        ui_file.close()
        for kind, names in (
            (QLabel, "banner stateLabel diagnostic sourceLabel targetLabel"),
            (QComboBox, "xColumn xUnit yColumn yUnit"),
            (QSpinBox, "firstRow lastRow"),
            (QTableWidget, "dataTable coefficientTable"),
            (QListWidget, "testList resultsList"),
            (QPushButton, "fitButton cancelButton adoptButton"),
            (QProgressBar, "progress"), (QSplitter, "workSplitter"),
            (QDockWidget, "testDock"),
        ):
            for name in names.split():
                setattr(self, name, self.findChild(kind, name))
        self.doc = {
            "format": "caelab-planning-demo-1", "disclaimer": DISCLAIMER,
            "sources": [], "active_source": None,
            "mapping": {"x": "", "y": "", "x_unit": "1", "y_unit": "MPa"},
            "selection": [1, 1], "source_contexts": {}, "coefficients": {"E": 1.0, "b": 0.0},
            "revision": 0, "results": [], "selected_result": None,
        }
        self.path = None
        self.saved_fingerprint = stable(self.doc)
        self.updating = False
        self.displayed_source_id = None
        self.running_id = None
        self.inject_failure = False
        self.fit_starts = 0
        self.revision_serial = 0
        self.undo_stack = QUndoStack(self)
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.advance)
        self.build_menu()
        self.banner.setStyleSheet("background:#f5e5b9; color:#403214; padding:8px; font-weight:600;")
        self.stateLabel.setStyleSheet("font-weight:600; padding:4px;")
        self.diagnostic.setMinimumHeight(38)
        self.testDock.setMinimumWidth(300)
        self.testDock.setMaximumWidth(520)
        self.dataTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.coefficientTable.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.coefficientTable.setColumnCount(3)
        self.coefficientTable.setHorizontalHeaderLabels(["계수", "현재값", "단위"])
        self.coefficientTable.setRowCount(2)
        self.coefficientTable.verticalHeader().hide()
        rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
        rcParams["axes.unicode_minus"] = False
        self.figure = Figure(layout="constrained", facecolor="white")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes, self.residual_axes = self.figure.subplots(2, 1, sharex=True, gridspec_kw={"height_ratios": [3, 1]})
        layout = self.findChild(QWidget, "plotHost").layout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(NavigationToolbar2QT(self.canvas, self))
        layout.addWidget(self.canvas)
        self.span = None
        for combo in (self.xColumn, self.yColumn):
            combo.currentTextChanged.connect(self.mapping_changed)
        for combo in (self.xUnit, self.yUnit):
            combo.currentTextChanged.connect(self.mapping_changed)
        self.firstRow.valueChanged.connect(self.range_changed)
        self.lastRow.valueChanged.connect(self.range_changed)
        self.dataTable.itemSelectionChanged.connect(self.table_selected)
        self.coefficientTable.itemChanged.connect(self.coefficient_changed)
        self.testList.currentRowChanged.connect(self.source_selected)
        self.resultsList.currentRowChanged.connect(self.result_selected)
        self.fitButton.clicked.connect(self.start_fit)
        self.cancelButton.clicked.connect(self.cancel_fit)
        self.adoptButton.clicked.connect(self.confirm_adopt)
        self.workSplitter.setSizes([540, 230])
        self.refresh()

    def build_menu(self):
        file_menu = self.menuBar().addMenu("파일(&F)")
        toolbar = self.addToolBar("주요 작업")
        toolbar.setObjectName("mainToolbar")
        for label, shortcut, callback in (
            ("CSV 열기…", "Ctrl+I", self.open_csv_dialog),
            ("문서 열기…", "Ctrl+O", self.open_document_dialog),
            ("저장", "Ctrl+S", self.save_dialog),
            ("다른 이름으로 저장…", "Ctrl+Shift+S", lambda: self.save_dialog(True)),
            ("데모 시험 열기", "", lambda: self.safe_load_csv(HERE / "demo_test.csv")),
        ):
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            file_menu.addAction(action)
            if shortcut in ("Ctrl+I", "Ctrl+S"):
                toolbar.addAction(action)
        edit_menu = self.menuBar().addMenu("편집(&E)")
        undo = self.undo_stack.createUndoAction(self, "되돌리기")
        undo.setShortcut("Ctrl+Z")
        redo = self.undo_stack.createRedoAction(self, "다시 실행")
        redo.setShortcut("Ctrl+Shift+Z")
        edit_menu.addAction(undo)
        edit_menu.addAction(redo)
        view_menu = self.menuBar().addMenu("창(&W)")
        view_menu.addAction(self.testDock.toggleViewAction())
        view_menu.addAction("기본 배치 복원", self.restore_layout)
        demo_menu = self.menuBar().addMenu("데모 상태(&D)")
        fail = demo_menu.addAction("다음 시뮬레이션 실패")
        fail.setCheckable(True)
        fail.toggled.connect(lambda value: setattr(self, "inject_failure", value))
        self.failure_action = fail

    def restore_layout(self):
        self.testDock.setFloating(False)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.testDock)
        self.testDock.show()
        self.workSplitter.setSizes([540, 230])

    @property
    def dirty(self):
        return stable(self.doc) != self.saved_fingerprint

    def source(self):
        return next((s for s in self.doc["sources"] if s["id"] == self.doc["active_source"]), None)

    def context(self):
        return {k: deepcopy(self.doc[k]) for k in ("active_source", "mapping", "selection")}

    def edit(self, label, **changes):
        state = {k: deepcopy(self.doc[k]) for k in EDIT_KEYS}
        if all(state.get(k) == v for k, v in changes.items()):
            return
        state.update(changes)
        if state["active_source"]:
            state["source_contexts"][state["active_source"]] = {
                "mapping": deepcopy(state["mapping"]), "selection": deepcopy(state["selection"])}
        self.revision_serial += 1
        state["revision"] = self.revision_serial
        self.undo_stack.push(Edit(self, label, state))

    def load_csv(self, path):
        path = Path(path)
        raw_bytes = path.read_bytes()
        raw = raw_bytes.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(raw))
        rows = list(reader)
        if len(rows) < 2 or len(rows[0]) < 2:
            raise ValueError("CSV: 머리글과 2개 이상의 열, 자료 행이 필요합니다.")
        headers, values = rows[0], rows[1:]
        if len(set(headers)) != len(headers) or any(not h.strip() for h in headers):
            raise ValueError("CSV: 빈 열 이름 또는 중복 이름을 고친 후 다시 여세요.")
        if any(len(row) != len(headers) for row in values):
            raise ValueError("CSV: 행마다 열 수가 다릅니다. 원파일 구분자를 확인하세요.")
        if len(values) > 10000:
            raise ValueError("이 시제품은 10,000행 이하만 표시합니다.")
        source = {"id": str(uuid.uuid4()), "name": path.name, "path": str(path.resolve()),
                  "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                  "raw_bytes_base64": base64.b64encode(raw_bytes).decode(),
                  "raw_text": raw, "headers": headers, "rows": values}
        self.doc["sources"].append(source)
        self.edit("시험 가져오기", active_source=source["id"],
                  mapping={"x": headers[0], "y": headers[1], "x_unit": "1", "y_unit": "MPa"},
                  selection=[1, len(values)])
        self.diagnostic.setText("원자료를 문서에 복사했습니다. 열·단위를 확인하고 동정 구간을 선택하세요.")

    def safe_load_csv(self, path):
        try:
            self.load_csv(path)
        except (OSError, ValueError, UnicodeError) as exc:
            self.show_error(str(exc))

    def open_csv_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "시험 CSV 열기", str(HERE), "CSV (*.csv)")
        if path:
            self.safe_load_csv(path)

    def mapping_changed(self, *_):
        if not self.updating:
            self.edit("열·단위 수정", mapping={"x": self.xColumn.currentText(), "y": self.yColumn.currentText(),
                      "x_unit": self.xUnit.currentText(), "y_unit": self.yUnit.currentText()})

    def range_changed(self, *_):
        if not self.updating:
            first, last = self.firstRow.value(), self.lastRow.value()
            self.edit("동정 구간 수정", selection=[first, max(first, last)])

    def table_selected(self):
        if self.updating:
            return
        rows = sorted({index.row() + 1 for index in self.dataTable.selectedIndexes()})
        if rows:
            self.edit("표 구간 선택", selection=[rows[0], rows[-1]])

    def plot_selected(self, lower, upper):
        try:
            x, _ = self.numeric_data()
        except ValueError:
            return
        rows = [i + 1 for i, value in enumerate(x) if lower <= value <= upper]
        if rows:
            self.edit("곡선 구간 선택", selection=[min(rows), max(rows)])

    def coefficient_changed(self, item):
        if self.updating or item.column() != 1:
            return
        try:
            value = float(item.text())
            if not math.isfinite(value) or (item.row() == 0 and value <= 0):
                raise ValueError
        except ValueError:
            value = item.text()
        coefficients = deepcopy(self.doc["coefficients"])
        coefficients[("E", "b")[item.row()]] = value
        self.edit("계수 수정", coefficients=coefficients)

    def source_selected(self, row):
        if self.updating or row < 0:
            return
        source = self.doc["sources"][row]
        context = self.doc["source_contexts"].get(source["id"], {
            "mapping": {"x": source["headers"][0], "y": source["headers"][1], "x_unit": "1", "y_unit": "MPa"},
            "selection": [1, len(source["rows"])]})
        self.edit("보존 시험 선택", active_source=source["id"],
                  mapping=deepcopy(context["mapping"]), selection=deepcopy(context["selection"]))

    def result_selected(self, row):
        if not self.updating:
            self.doc["selected_result"] = self.doc["results"][row]["id"] if row >= 0 else None
            self.refresh()

    def selected_result(self):
        return next((r for r in self.doc["results"] if r["id"] == self.doc["selected_result"]), None)

    def numeric_data(self):
        return source_numeric_data(self.source(), self.doc["mapping"])

    def readiness(self):
        try:
            self.numeric_data()
            lo, hi = self.doc["selection"]
            if hi - lo < 2:
                raise ValueError("구간 오류: 최소 3개 행을 선택하세요.")
            numeric_coefficients(self.doc["coefficients"])
            return True, "준비됨 · 열·단위 확인 완료 · DEMO 동정만 가능"
        except ValueError as exc:
            return False, str(exc)

    def start_fit(self):
        ready, reason = self.readiness()
        if not ready or self.running_id:
            self.diagnostic.setText(reason)
            return False
        x, y = self.numeric_data()
        lo, hi = self.doc["selection"]
        result = {"id": str(uuid.uuid4()), "label": DISCLAIMER,
                  "status": "running", "context": self.context(), "source_sha256": self.source()["sha256"],
                  "input_coefficients": deepcopy(self.doc["coefficients"]), "revision": self.doc["revision"],
                  "x": x[lo - 1:hi], "observed": y[lo - 1:hi], "progress": 0,
                  "message": "고정 데모 값을 기다리는 UI 상태 시뮬레이션"}
        result["input_sha256"] = result_input_hash(result)
        self.doc["results"].append(result)
        self.doc["selected_result"] = result["id"]
        self.running_id = result["id"]
        self.running_failure = self.inject_failure
        self.fit_starts += 1
        self.progress.setValue(0)
        self.timer.start()
        self.refresh()
        return True

    def advance(self):
        result = next(r for r in self.doc["results"] if r["id"] == self.running_id)
        result["progress"] = min(100, result["progress"] + 10)
        self.refresh_progress()
        if result["progress"] < 100:
            return
        self.timer.stop()
        result = next(r for r in self.doc["results"] if r["id"] == self.running_id)
        self.running_id = None
        if self.running_failure:
            result.update(status="failed", message="DEMO 강제 실패: 입력/이전 결과는 보존됨. 실패 주입을 해제하고 새 실행하세요.")
        else:
            # Fixed coefficients deliberately do not estimate a material from the observations.
            coefficients = {"E": 2.4, "b": .02}
            predicted = [coefficients["E"] * x + coefficients["b"] for x in result["x"]]
            residual = [p - y for p, y in zip(predicted, result["observed"])]
            result.update(status="complete", coefficients=coefficients, predicted=predicted, residual=residual,
                          rmse=math.sqrt(sum(v * v for v in residual) / len(residual)),
                          message="SIMULATED UI: 고정 E=2.4 MPa, b=0.02 MPa. 실제 모델 동정 아님.")
        self.refresh()

    def cancel_fit(self):
        if not self.running_id:
            return
        self.timer.stop()
        result = next(r for r in self.doc["results"] if r["id"] == self.running_id)
        result.update(status="cancelled", message="DEMO 취소됨 · 결과를 생성하지 않았습니다. 입력과 이전 결과는 보존됨.")
        self.running_id = None
        self.refresh()

    def can_adopt(self):
        result = self.selected_result()
        return bool(result and result["status"] == "complete" and self.readiness()[0]
                    and self.result_matches_input(result) and not self.running_id)

    def result_matches_input(self, result):
        source = self.source()
        return bool(source and result["context"] == self.context()
                    and result["source_sha256"] == source["sha256"]
                    and result["input_coefficients"] == self.doc["coefficients"])

    def refresh_progress(self):
        result = next((r for r in self.doc["results"] if r["id"] == self.running_id), None) or self.selected_result()
        if not result:
            self.progress.setValue(0)
            self.progress.setFormat("DEMO 실행 없음")
            return
        status = {"running": "진행 중", "complete": "완료", "failed": "실패", "cancelled": "취소", "interrupted": "중단"}[result["status"]]
        self.progress.setValue(result.get("progress", 100 if result["status"] in ("complete", "failed") else 0))
        self.progress.setFormat(f"DEMO {status} · %p%" if result["status"] == "running" else f"DEMO {status} · 종료")

    def confirm_adopt(self):
        if not self.can_adopt():
            return
        result = self.selected_result()
        changes = "\n".join(f"{key}: {coefficient_text(self.doc['coefficients'][key])} → {value:g} MPa" for key, value in result["coefficients"].items())
        answer = QMessageBox.question(self, "Material 계수 채택 · DEMO", DISCLAIMER + "\n" + changes + "\n새 개정으로 채택할까요? Ctrl+Z로 되돌릴 수 있습니다.")
        if answer == QMessageBox.Yes:
            self.adopt()

    def adopt(self):
        if not self.can_adopt():
            raise ValueError("현재 자료·매핑·구간과 일치하는 완료 후보만 채택할 수 있습니다.")
        self.edit("후보 계수 채택 · DEMO", coefficients=deepcopy(self.selected_result()["coefficients"]))

    def refresh(self):
        self.updating = True
        source = self.source()
        headers = source["headers"] if source else []
        for combo, key in ((self.xColumn, "x"), (self.yColumn, "y")):
            combo.clear()
            combo.addItems(headers)
            combo.setCurrentText(self.doc["mapping"][key])
        self.xUnit.setCurrentText(self.doc["mapping"]["x_unit"])
        self.yUnit.setCurrentText(self.doc["mapping"]["y_unit"])
        count = len(source["rows"]) if source else 1
        for spin, value in zip((self.firstRow, self.lastRow), self.doc["selection"]):
            spin.setMaximum(count)
            spin.setValue(value)
        self.testList.clear()
        for index, saved in enumerate(self.doc["sources"]):
            self.testList.addItem(saved["name"] + f" · {len(saved['rows'])}행")
            if source and saved["id"] == source["id"]:
                self.testList.setCurrentRow(index)
        self.sourceLabel.setText(f"{source['name']} · 원자료 보존됨" if source else "시험 없음 · CSV를 열어 시작")
        source_id = source["id"] if source else None
        rebuild_table = self.displayed_source_id != source_id
        if rebuild_table:
            self.dataTable.clear()
            self.dataTable.setRowCount(len(source["rows"]) if source else 0)
            self.dataTable.setColumnCount(len(headers) + 1)
            self.dataTable.setHorizontalHeaderLabels(["원 행"] + headers)
            self.displayed_source_id = source_id
        if source and rebuild_table:
            for row, values in enumerate(source["rows"]):
                for col, value in enumerate([str(row + 1)] + values):
                    self.dataTable.setItem(row, col, QTableWidgetItem(value))
        if source:
            lo, hi = self.doc["selection"]
            from PySide6.QtCore import QItemSelection, QItemSelectionModel
            selection = QItemSelection(self.dataTable.model().index(lo - 1, 0), self.dataTable.model().index(hi - 1, len(headers)))
            selected_rows = sorted({index.row() + 1 for index in self.dataTable.selectedIndexes()})
            if selected_rows != list(range(lo, hi + 1)):
                self.dataTable.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        for row, key in enumerate(("E", "b")):
            for col, text in enumerate((key, coefficient_text(self.doc['coefficients'][key]), "MPa")):
                item = QTableWidgetItem(text)
                if col != 1:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                else:
                    try:
                        numeric_coefficients({"E": self.doc["coefficients"][key] if key == "E" else 1, "b": self.doc["coefficients"][key] if key == "b" else 0})
                    except ValueError as exc:
                        item.setBackground(QColor("#f9d8d3"))
                        item.setToolTip(str(exc))
                self.coefficientTable.setItem(row, col, item)
        self.resultsList.clear()
        for index, result in enumerate(self.doc["results"]):
            item = QListWidgetItem(f"DEMO #{index + 1} · {result['status']} · 편집 v{result['revision']}")
            item.setToolTip(result["message"] + "\n" + result["id"])
            self.resultsList.addItem(item)
            if result["id"] == self.doc["selected_result"]:
                self.resultsList.setCurrentRow(index)
        ready, reason = self.readiness()
        adopt_ready = self.can_adopt()
        self.fitButton.setEnabled(ready and not self.running_id)
        self.cancelButton.setEnabled(bool(self.running_id))
        self.adoptButton.setEnabled(adopt_ready)
        result = self.selected_result()
        self.stateLabel.setText(f"시안 편집 v{self.doc['revision']} · {'수정됨' if self.dirty else '저장됨'}\n현재 입력: {reason}")
        target = next((index + 1 for index, r in enumerate(self.doc["results"]) if result and r["id"] == result["id"]), None)
        self.targetLabel.setText(f"선택 후보 DEMO #{target} · {result['status']}\n{'채택 가능' if adopt_ready else '채택 차단'}" if result else "선택 후보 없음 · 채택 차단")
        self.refresh_progress()
        result_message = (result["message"] + (" · 현재 입력과 다름: 원 후보만 비교 / 채택 차단" if not self.result_matches_input(result) else "")) if result else ""
        self.diagnostic.setText(reason + ("\n" + result_message if result_message else "") if not ready else result_message or reason)
        self.setWindowTitle(f"Material — {self.path.name if self.path else '새 연구'}{' *' if self.dirty else ''} — DEMO")
        self.statusBar().showMessage("SIMULATED UI · 표는 원자료 / 곡선은 변형률 1, 응력 MPa로 환산 · 물리 미검증")
        self.plot()
        self.updating = False

    def plot(self):
        if self.span:
            self.span.disconnect_events()
        self.axes.clear()
        self.residual_axes.clear()
        try:
            x, y = self.numeric_data()
            self.axes.plot(x, y, ".-", color="#4b6278", label="현재 관측")
            lo, hi = self.doc["selection"]
            self.axes.axvspan(x[lo - 1], x[hi - 1], alpha=.16, color="#34759e", label="선택 구간")
        except ValueError:
            self.axes.text(.5, .5, "CSV 열기 → 열·단위 지정 → 구간 선택", ha="center", transform=self.axes.transAxes)
        result = self.selected_result()
        if result and result["status"] == "complete":
            self.axes.plot(result["x"], result["observed"], "o", ms=4, color="#1d617d", label="후보 원 관측")
            self.axes.plot(result["x"], result["predicted"], "-", color="#bc6c22", label="SIMULATED UI 예측")
            self.residual_axes.plot(result["x"], result["residual"], ".-", color="#bc6c22")
            self.residual_axes.set_title(f"DEMO RMSE {result['rmse']:.5f} MPa · 오차 = 예측 - 관측", fontsize=9)
        self.axes.set_title("관측·예측 비교 · DEMO / SIMULATED UI / 물리 미검증", fontsize=11)
        self.axes.set_ylabel("응력 [MPa]")
        self.residual_axes.set_ylabel("오차 [MPa]")
        self.residual_axes.set_xlabel("변형률 [1]")
        self.residual_axes.axhline(0, color="#84919a", linewidth=.8)
        for axis in (self.axes, self.residual_axes):
            axis.grid(alpha=.18)
        if self.axes.get_legend_handles_labels()[0]:
            self.axes.legend(loc="upper left", fontsize=8)
        self.span = SpanSelector(self.axes, self.plot_selected, "horizontal", useblit=False,
                                 props={"alpha": .2, "facecolor": "#34759e"}, interactive=False)
        self.canvas.draw_idle()

    def show_error(self, message):
        self.diagnostic.setText(message)
        QMessageBox.warning(self, "작업 실패 · 복구", message)

    def save(self, path):
        path = Path(path)
        payload = deepcopy(self.doc)
        payload["revision_serial"] = self.revision_serial
        payload["layout"] = {"geometry": bytes(self.saveGeometry().toBase64()).decode(),
                             "state": bytes(self.saveState().toBase64()).decode(),
                             "splitter": self.workSplitter.sizes()}
        text = stable(payload)
        # Same-directory temporary file and replace preserve the previous save on write failure.
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
                temp_path = stream.name
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
        self.path = path
        self.saved_fingerprint = stable(self.doc)
        self.refresh()

    def save_dialog(self, save_as=False):
        path = str(self.path) if self.path and not save_as else ""
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "데모 연구 저장", str(HERE / "research.demo.json"), "Demo research (*.demo.json)")
        if path:
            try:
                self.save(path)
            except (OSError, ValueError) as exc:
                self.show_error(f"저장 실패: {exc}. 이전 저장본은 유지됩니다. 다른 경로로 다시 저장하세요.")
                return False
            return True
        return False

    def load_document(self, path):
        candidate = json.loads(Path(path).read_text(encoding="utf-8"))
        validate_document(candidate)
        layout = candidate.pop("layout", {})
        # A process cannot resume a QTimer; keep its interrupted input record, without inventing a result.
        interrupted = False
        for result in candidate["results"]:
            if result["status"] == "running":
                result.update(status="interrupted", message="DEMO 실행 중 저장본: 프로세스 종료로 중단됨. 새 실행하세요.")
                interrupted = True
        self.timer.stop()
        self.running_id = None
        self.undo_stack.clear()
        self.displayed_source_id = None
        if candidate["active_source"]:
            candidate["source_contexts"][candidate["active_source"]] = {
                "mapping": deepcopy(candidate["mapping"]), "selection": deepcopy(candidate["selection"])}
        self.doc = candidate
        self.revision_serial = candidate.pop("revision_serial", max([candidate["revision"]] + [r["revision"] for r in candidate["results"]]))
        self.path = Path(path)
        self.saved_fingerprint = stable(self.doc) if not interrupted else "interrupted-save"
        from PySide6.QtCore import QByteArray
        if layout:
            self.restoreGeometry(QByteArray.fromBase64(layout.get("geometry", "").encode()))
            self.restoreState(QByteArray.fromBase64(layout.get("state", "").encode()))
            self.workSplitter.setSizes(layout.get("splitter", [540, 230]))
        self.refresh()

    def may_replace_document(self):
        if self.running_id:
            warning = QMessageBox(self)
            warning.setWindowTitle("실행 중인 로컬 DEMO 시뮬레이션")
            warning.setText("닫거나 다른 문서로 바꾸면 이 창의 로컬 DEMO 타이머가 중단됩니다. 제품 계산 작업이 아닙니다.")
            keep = warning.addButton("계속 보기", QMessageBox.RejectRole)
            warning.addButton("DEMO 중단 후 계속", QMessageBox.AcceptRole)
            warning.setDefaultButton(keep)
            warning.exec()
            if warning.clickedButton() == keep or warning.clickedButton() is None:
                return False
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "수정한 연구", "수정 내용을 저장할까요?", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        return self.save_dialog() if answer == QMessageBox.Save else answer == QMessageBox.Discard

    def open_document_dialog(self):
        if not self.may_replace_document():
            return
        path, _ = QFileDialog.getOpenFileName(self, "데모 연구 다시 열기", str(HERE), "Demo research (*.demo.json)")
        if path:
            try:
                self.load_document(path)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.show_error(f"재열기 실패: {exc}. 현재 연구는 유지됩니다. 올바른 데모 저장본을 선택하세요.")

    def closeEvent(self, event):
        if self.may_replace_document():
            self.timer.stop()
            event.accept()
        else:
            event.ignore()


def validate_document(doc):
    """Reject malformed files before replacing the current editable document."""
    if not isinstance(doc, dict) or doc.get("format") != "caelab-planning-demo-1" or doc.get("disclaimer") != DISCLAIMER:
        raise ValueError("지원하지 않는 시제품 파일 형식")
    stable(doc)  # Also rejects non-finite JSON numbers.
    doc.setdefault("source_contexts", {})  # Earlier provisional saves had only an active-source context.
    assert_keys = set(EDIT_KEYS) | {"sources", "results", "selected_result"}
    if not assert_keys.issubset(doc):
        raise ValueError("필수 문서 항목 누락")
    sources = doc["sources"]
    if not isinstance(sources, list) or not isinstance(doc["results"], list):
        raise ValueError("자료/결과 목록 오류")
    ids = set()
    for source in sources:
        headers, rows = source["headers"], source["rows"]
        if source["id"] in ids or len(set(headers)) != len(headers) or len(headers) < 2:
            raise ValueError("자료 ID/열 이름 오류")
        ids.add(source["id"])
        if not rows or len(rows) > 10000 or any(len(row) != len(headers) for row in rows):
            raise ValueError("원자료 행 오류")
        raw_bytes = base64.b64decode(source["raw_bytes_base64"], validate=True)
        if hashlib.sha256(raw_bytes).hexdigest() != source["sha256"] or raw_bytes.decode("utf-8-sig") != source["raw_text"]:
            raise ValueError("보존 원자료 hash 불일치")
        parsed = list(csv.reader(io.StringIO(source["raw_text"])))
        if parsed != [headers] + rows:
            raise ValueError("보존 원자료와 표 불일치")
        if not isinstance(source["name"], str) or not isinstance(source["path"], str):
            raise ValueError("자료 이름/경로 오류")
    if doc["active_source"] is not None and doc["active_source"] not in ids:
        raise ValueError("활성 자료 참조 없음")
    mapping = doc["mapping"]
    if set(mapping) != {"x", "y", "x_unit", "y_unit"} or not all(isinstance(v, str) for v in mapping.values()):
        raise ValueError("열 매핑 형식 오류")
    selected = doc["selection"]
    active = next((s for s in sources if s["id"] == doc["active_source"]), None)
    if len(selected) != 2 or not all(type(v) is int for v in selected) or not (1 <= selected[0] <= selected[1] <= (len(active["rows"]) if active else 1)):
        raise ValueError("행 선택 범위 오류")
    if type(doc["revision"]) is not int or doc["revision"] < 0:
        raise ValueError("개정 오류")
    coefficients = doc["coefficients"]
    if set(coefficients) != {"E", "b"} or not all(isinstance(v, str) or (type(v) in (int, float) and math.isfinite(v)) for v in coefficients.values()):
        raise ValueError("계수 형식 오류")
    contexts = doc["source_contexts"]
    if not isinstance(contexts, dict):
        raise ValueError("시험별 편집 맥락 오류")
    for source_id, context in contexts.items():
        saved_source = next((s for s in sources if s["id"] == source_id), None)
        if not saved_source or not isinstance(context, dict):
            raise ValueError("시험별 편집 맥락의 자료 참조 없음")
        source_mapping, source_selection = context["mapping"], context["selection"]
        if set(source_mapping) != {"x", "y", "x_unit", "y_unit"} or not all(isinstance(v, str) for v in source_mapping.values()):
            raise ValueError("시험별 열 매핑 형식 오류")
        if len(source_selection) != 2 or not all(type(v) is int for v in source_selection) or not (1 <= source_selection[0] <= source_selection[1] <= len(saved_source["rows"])):
            raise ValueError("시험별 행 선택 범위 오류")
    result_ids = set()
    for result in doc["results"]:
        if result["id"] in result_ids or result["status"] not in ("complete", "running", "cancelled", "failed", "interrupted") or result["label"] != DISCLAIMER:
            raise ValueError("결과 ID/상태 오류")
        result_ids.add(result["id"])
        if result["context"]["active_source"] not in ids or type(result["revision"]) is not int or not isinstance(result["message"], str):
            raise ValueError("결과 입력 참조 오류")
        context = result["context"]
        if set(context) != {"active_source", "mapping", "selection"} or result["revision"] < 0:
            raise ValueError("결과 입력 맥락 오류")
        source = next(s for s in sources if s["id"] == context["active_source"])
        if result["source_sha256"] != source["sha256"]:
            raise ValueError("결과 출발 원자료 hash 불일치")
        result_mapping, result_selection = context["mapping"], context["selection"]
        if not isinstance(result_mapping, dict) or set(result_mapping) != {"x", "y", "x_unit", "y_unit"} or not all(isinstance(v, str) for v in result_mapping.values()):
            raise ValueError("결과 열 매핑 형식 오류")
        if not isinstance(result_selection, list) or len(result_selection) != 2 or not all(type(v) is int for v in result_selection) or not (1 <= result_selection[0] <= result_selection[1] <= len(source["rows"])) or result_selection[1] - result_selection[0] < 2:
            raise ValueError("결과 행 선택 범위 오류")
        numeric_coefficients(result["input_coefficients"])
        if result["input_sha256"] != result_input_hash(result):
            raise ValueError("결과 출발 입력 hash 불일치")
        x, observed = source_numeric_data(source, result_mapping)
        lo, hi = result_selection
        if result["x"] != x[lo - 1:hi] or result["observed"] != observed[lo - 1:hi]:
            raise ValueError("결과 보존 관측과 출발 원자료/매핑/구간 불일치")
        if "progress" in result and (type(result["progress"]) is not int or not 0 <= result["progress"] <= 100):
            raise ValueError("결과 진행 상태 오류")
        if len(result["x"]) != len(result["observed"]) or not result["x"] or not all(type(v) in (int, float) and math.isfinite(v) for v in result["x"] + result["observed"]):
            raise ValueError("결과 곡선 오류")
        if result["status"] == "complete":
            if set(result["coefficients"]) != {"E", "b"} or not all(type(v) in (int, float) and math.isfinite(v) for v in result["coefficients"].values()) or result["coefficients"]["E"] <= 0:
                raise ValueError("결과 계수 오류")
            if len(result["predicted"]) != len(result["x"]) or len(result["residual"]) != len(result["x"]) or not all(type(v) in (int, float) and math.isfinite(v) for v in result["predicted"] + result["residual"]) or type(result["rmse"]) not in (int, float) or result["rmse"] < 0:
                raise ValueError("완료 결과 출력 오류")
    if doc["selected_result"] is not None and doc["selected_result"] not in result_ids:
        raise ValueError("선택 후보 참조 없음")
    if "revision_serial" in doc and (type(doc["revision_serial"]) is not int or doc["revision_serial"] < max([doc["revision"]] + [r["revision"] for r in doc["results"]])):
        raise ValueError("시안 편집 번호 오류")
    layout = doc.get("layout", {})
    if not isinstance(layout, dict) or any(not isinstance(layout.get(k, ""), str) for k in ("geometry", "state")) or ("splitter" in layout and (not isinstance(layout["splitter"], list) or not all(type(v) is int and v >= 0 for v in layout["splitter"]))):
        raise ValueError("창 배치 형식 오류")


def configure_font(app):
    # Windows offscreen plugin has an empty system font database; use the installed font explicitly.
    font = Path("C:/Windows/Fonts/malgun.ttf")
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))
    app.setFont(QFont("Malgun Gothic", 10))


def main():
    app = QApplication(sys.argv)
    configure_font(app)
    window = MaterialPrototype()
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if path.suffix.lower() == ".csv":
            window.safe_load_csv(path)
        else:
            try:
                window.load_document(path)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                window.show_error(str(exc))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
