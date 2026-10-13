"""Material Research editor; the loopback service owns all document commands.

Run with ``python -m apps.research.material_window --service http://127.0.0.1:PORT``.
No solver, document store or job controller is constructed in this process.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import math
import os
import sys
import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QFormLayout, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QPlainTextEdit, QSplitter, QTableWidget, QTableWidgetItem,
    QTabWidget, QToolBar, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from caelab.workbench_client import Client


STRESS_COMPONENTS = tuple("stress_" + component for component in ("xx", "yy", "zz", "xy", "xz", "yz"))
TERMINAL = {"SUCCEEDED", "FAILED", "REJECTED", "PARTIAL_FAILURE", "CANCELLED", "INTERRUPTED"}
PARAMETERS = {"linear_elastic": ("E", "nu"), "neo_hooke": ("mu", "lmbda")}


def edited_number(text):
    """Preserve invalid text for the owner; never invent a zero or JSON NaN."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return text
    return value if math.isfinite(value) else text


def display_value(value):
    return str(value) if not isinstance(value, (dict, list)) else json.dumps(value, ensure_ascii=False)


def draft_view_error(draft):
    """Check only the table shape; numerical validation belongs to the owner."""
    settings = draft.get("settings")
    if draft.get("backend") != "material.felupe" or not isinstance(settings, dict):
        return "This draft has no supported Material settings object."
    model = settings.get("model")
    if not isinstance(model, str) or model not in PARAMETERS:
        return "This draft has an unsupported or missing material law."
    parameters = settings.get("parameters")
    if not isinstance(parameters, dict) or set(parameters) != set(PARAMETERS[model]):
        return "This draft has a different coefficient structure."
    if not {"stress_unit", "time_unit"} <= settings.keys():
        return "This draft is missing explicit unit fields."
    times, gradients = settings.get("time"), settings.get("deformation_gradient")
    if (not isinstance(times, list) or not isinstance(gradients, list) or len(times) != len(gradients)
            or any(not isinstance(matrix, list) or len(matrix) != 3 or
                   any(not isinstance(row, list) or len(row) != 3 for row in matrix) for matrix in gradients)):
        return "This draft cannot fit the time and 3×3 history table."
    return None


def edited_cell(table, row, column):
    item = table.item(row, column)
    text = item.text() if item else ""
    metadata = item.data(Qt.ItemDataRole.UserRole) if item else None
    original = metadata["original"] if isinstance(metadata, dict) and "original" in metadata else ""
    # Untouched invalid JSON values must not turn into strings during another edit.
    return deepcopy(original) if text == display_value(original) else edited_number(text)


def error_message(error):
    # HTTP failures carry the service's domain/conflict explanation.
    if hasattr(error, "read"):
        try:
            payload = json.loads(error.read().decode("utf-8"))
            return json.dumps(payload, ensure_ascii=False)
        except (ValueError, OSError, UnicodeError):
            pass
    return str(error)


class _Signals(QObject):
    finished = Signal(object, object)


class _Call(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = _Signals()

    def run(self):
        try:
            result = self.function()
        except Exception as error:
            self.signals.finished.emit(None, error_message(error))
        else:
            self.signals.finished.emit(result, None)


class MaterialWindow(QMainWindow):
    """A view and unapplied edit buffer, never a second document owner."""

    def __init__(self, client, *, document_id=None, title="Material study", poll_interval=1500,
                 auto_open=True):
        super().__init__()
        self.client = client
        self.document = None
        self.local_dirty = False
        self.conflict = False
        self._populating = False
        self._busy = False
        self._foreground_busy = False
        self._draft_problem = None
        self._worker = None
        self._allow_close = False
        self._result_cache = {}
        self._job_status = {}
        self._result_errors = {}
        self._runner = None
        self._numerical_windows = []
        self._native_material_windows = []
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(poll_interval)
        self.timer.timeout.connect(self.refresh_document)
        if poll_interval > 0:
            self.timer.start()
        if auto_open:
            self.open_document(document_id=document_id, title=title)

    def _build_ui(self):
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        self.setWindowTitle("Material Research")
        self.resize(1440, 900)
        self.setMinimumSize(840, 600)
        files = self.menuBar().addMenu("파일(&F)")
        self.new_action = QAction("새 재료…", self, shortcut=QKeySequence.New)
        self.open_action = QAction("열기…", self, shortcut=QKeySequence.Open)
        self.save_action = QAction("저장", self, shortcut=QKeySequence.Save)
        close_action = QAction("닫기", self, shortcut=QKeySequence.Close)
        for action in (self.new_action, self.open_action, self.save_action, close_action):
            files.addAction(action)
        self.new_action.triggered.connect(self.new_document)
        native_law = QAction('다른 재료 모델…', self)
        native_law.triggered.connect(self.new_native_law)
        files.insertAction(self.open_action, native_law)
        self.open_action.triggered.connect(self.choose_document)
        self.save_action.triggered.connect(self.save_document)
        close_action.triggered.connect(self.close)
        edit = self.menuBar().addMenu("편집(&E)")
        self.undo_action = QAction("실행 취소", self, shortcut=QKeySequence.Undo)
        self.redo_action = QAction("다시 실행", self, shortcut=QKeySequence.Redo)
        self.undo_action.triggered.connect(lambda: self.command("document.undo"))
        self.redo_action.triggered.connect(lambda: self.command("document.redo"))
        edit.addActions([self.undo_action, self.redo_action])
        windows = self.menuBar().addMenu("도구(&T)")
        self.runner_action = QAction("실행 관리…", self)
        self.runner_action.triggered.connect(self.open_runner)
        windows.addAction(self.runner_action)
        self.numerical_action = QAction("재료 피팅…", self)
        self.numerical_action.triggered.connect(self.open_numerical)
        windows.addAction(self.numerical_action)
        self.constitutive_action=QAction('구성식 증분…',self)
        self.constitutive_action.triggered.connect(self.open_constitutive)
        windows.addAction(self.constitutive_action)
        toolbar = QToolBar("Material commands", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addActions([self.new_action, self.open_action, self.save_action])
        toolbar.addSeparator()
        toolbar.addActions([self.undo_action, self.redo_action])
        self.apply_button = QPushButton("입력 적용")
        self.run_button = QPushButton("계산 실행")
        self.run_button.setProperty('appearanceRole', 'primary')
        self.apply_button.clicked.connect(self.apply_inputs)
        self.run_button.clicked.connect(self.evaluate)
        toolbar.addWidget(self.apply_button)
        toolbar.addWidget(self.run_button)
        toolbar.addSeparator()
        self.identity_label = QLabel("문서 여는 중")
        self.identity_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        toolbar.addWidget(self.identity_label)

        root = QWidget()
        outer = QVBoxLayout(root)
        self.message = QLabel("재료 문서를 여는 중…")
        self.message.setWordWrap(True)
        outer.addWidget(self.message)
        conflict_row = QHBoxLayout()
        self.reload_button = QPushButton("최신 내용 다시 읽기")
        self.copy_button = QPushButton("편집 내용을 새 문서로 보관")
        self.reload_button.clicked.connect(self.reload_remote)
        self.copy_button.clicked.connect(self.copy_edits)
        for button in (self.reload_button, self.copy_button):
            button.hide()
            conflict_row.addWidget(button)
        conflict_row.addStretch()
        outer.addLayout(conflict_row)

        main = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(main, 1)
        self.editor = QWidget()
        left = QVBoxLayout(self.editor)
        left.setContentsMargins(0, 0, 6, 0)
        form = QFormLayout()
        self.model = QComboBox()
        self.model.addItem("선형 탄성 (미소변형 Cauchy 응력)", "linear_elastic")
        self.model.addItem("Neo-Hooke (제1 Piola 응력)", "neo_hooke")
        self.stress_unit = QLineEdit()
        self.time_unit = QLineEdit()
        form.addRow("재료 모델", self.model)
        form.addRow("응력 및 탄성계수 단위", self.stress_unit)
        form.addRow("시간 단위", self.time_unit)
        left.addLayout(form)
        self.model.currentIndexChanged.connect(self._model_changed)
        self.stress_unit.textEdited.connect(self._edited)
        self.time_unit.textEdited.connect(self._edited)
        left.addWidget(QLabel("변형 이력 (지정한 변형구배 F)"))
        self.history = QTableWidget(0, 10)
        self.history.setObjectName("materialHistory")
        self.history.setHorizontalHeaderLabels(["Time", "F11", "F12", "F13", "F21", "F22", "F23", "F31", "F32", "F33"])
        self.history.horizontalHeader().setDefaultSectionSize(68)
        self.history.setAlternatingRowColors(True)
        self.history.itemChanged.connect(self._edited)
        left.addWidget(self.history, 3)
        row_buttons = QHBoxLayout()
        add_row = QPushButton("행 추가")
        remove_row = QPushButton("선택 행 삭제")
        add_row.clicked.connect(self.add_state)
        remove_row.clicked.connect(self.remove_states)
        row_buttons.addWidget(add_row)
        row_buttons.addWidget(remove_row)
        left.addLayout(row_buttons)
        self.protocol_label = QLabel()
        self.protocol_label.setWordWrap(True)
        left.addWidget(self.protocol_label)
        left.addWidget(QLabel("재료 계수"))
        self.coefficients = QTableWidget(0, 3)
        self.coefficients.setObjectName("materialCoefficients")
        self.coefficients.setHorizontalHeaderLabels(["계수", "값", "단위"])
        self.coefficients.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.coefficients.itemChanged.connect(self._edited)
        left.addWidget(self.coefficients, 2)
        main.addWidget(self.editor)

        right = QSplitter(Qt.Orientation.Vertical)
        plot_panel = QWidget()
        plot_layout = QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_controls = QHBoxLayout()
        plot_controls.addWidget(QLabel("응력 성분"))
        self.response = QComboBox()
        self.response.addItems(STRESS_COMPONENTS)
        self.response.currentTextChanged.connect(self._draw_results)
        plot_controls.addWidget(self.response)
        plot_controls.addStretch()
        plot_layout.addLayout(plot_controls)
        self.figure = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)
        plot_layout.addWidget(self.canvas, 1)
        right.addWidget(plot_panel)
        output = QWidget()
        output_layout = QVBoxLayout(output)
        output_layout.setContentsMargins(0, 0, 0, 0)
        run_controls = QHBoxLayout()
        run_controls.addWidget(QLabel("계산 결과"))
        run_controls.addStretch()
        self.runner_button = QPushButton("실행 관리에서 열기")
        self.runner_button.clicked.connect(self.open_runner)
        run_controls.addWidget(self.runner_button)
        output_layout.addLayout(run_controls)
        self.runs = QTableWidget(0, 4)
        self.runs.setObjectName("materialRuns")
        self.runs.setHorizontalHeaderLabels(["계산", "진행 상태", "계산에 쓴 입력", "현재 입력과 비교"])
        self.runs.setToolTip("Ctrl 또는 Shift를 누르고 여러 계산을 선택하면 같은 단위와 응력 정의의 결과를 비교합니다.")
        self.runs.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.runs.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.runs.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.runs.itemSelectionChanged.connect(self._selection_changed)
        output_layout.addWidget(self.runs, 1)
        self.result_notice = QLabel()
        self.result_notice.setWordWrap(True)
        self.result_notice.hide()
        output_layout.addWidget(self.result_notice)
        self.result_tabs = QTabWidget()
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.values = QTableWidget(0, 3)
        self.values.setHorizontalHeaderLabels(["계산", "축 값", "응력"])
        self.values.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.values.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.result_tabs.addTab(self.values, "계산값")
        self.result_tabs.addTab(self.diagnostics, "진단 상세")
        output_layout.addWidget(self.result_tabs, 1)
        right.addWidget(output)
        right.setSizes([520, 270])
        main.addWidget(right)
        main.setSizes([485, 930])
        self.setCentralWidget(root)
        self._draw_results()
        self._update_actions()

    def _call(self, function, success, *, background=False):
        if self._busy:
            if not background:
                self.message.setText("A service request is in progress. Your edits are retained; try again when it finishes.")
            return False
        self._busy = True
        self._foreground_busy = not background
        if not background:
            self.editor.setEnabled(False)
        self._update_actions()
        worker = _Call(function)
        self._worker = worker

        def finished(result, error):
            self._busy = False
            self._foreground_busy = False
            self._worker = None
            self.editor.setEnabled(True)
            if error:
                self.message.setText("Service request failed; edits retained. " + error)
                self.diagnostics.appendPlainText(error)
                # A refused mutation may be a stale-generation conflict.
                if not background:
                    QTimer.singleShot(0, self.refresh_document)
            else:
                success(result)
            self._update_actions()

        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def open_document(self, *, document_id=None, title="Material study", draft=None):
        return self._call(lambda: self.client.document_open(kind="material", title=title,
                         draft=draft, document_id=document_id), self._opened)

    def _opened(self, document):
        from caelab.material_document import NATIVE_LAWS
        if document['draft'].get('backend') in NATIVE_LAWS:
            from .native_material_window import NativeMaterialWindow
            window = NativeMaterialWindow(self.client, auto_open=False)
            self._native_material_windows.append(window)
            window._opened(document); window.show()
            self.message.setText('Opened the same Material owner in its native law/protocol editor.')
            return
        self.document = deepcopy(document)
        self.local_dirty = self.conflict = False
        self._result_cache.clear()
        self._job_status.clear()
        self._result_errors.clear()
        self._show_document(document)
        self.message.setText("재료 계수와 변형 이력을 입력하고, 입력 적용 후 계산 실행을 누르세요.")
        QTimer.singleShot(0, self.refresh_results)

    def _show_document(self, document, *, prefer_job=None):
        self.document = deepcopy(document)
        self._populating = True
        self._draft_problem = draft_view_error(document["draft"])
        if self._draft_problem:
            self.model.setCurrentIndex(-1)
            self.stress_unit.clear()
            self.time_unit.clear()
            self.coefficients.setRowCount(0)
            self.history.setRowCount(0)
        else:
            settings = document["draft"]["settings"]
            self.model.setCurrentIndex(self.model.findData(settings["model"]))
            self.stress_unit.setText(display_value(settings["stress_unit"]))
            self.time_unit.setText(display_value(settings["time_unit"]))
            self._populate_coefficients(settings["parameters"])
            self.history.setRowCount(len(settings["time"]))
            for row, time in enumerate(settings["time"]):
                gradient = settings["deformation_gradient"][row]
                for column, value in enumerate([time] + [item for vector in gradient for item in vector]):
                    item = QTableWidgetItem(display_value(value))
                    item.setData(Qt.ItemDataRole.UserRole, {"original": deepcopy(value)})
                    self.history.setItem(row, column, item)
        self._populating = False
        self._update_protocol_label()
        self._populate_runs(prefer_job=prefer_job)
        self._show_diagnostics()
        self._draw_results()
        self._update_actions()

    def _populate_coefficients(self, values):
        self.coefficients.setRowCount(2)
        for row, name in enumerate(PARAMETERS[self.model.currentData()]):
            for column, value in enumerate((name, values.get(name, ""), "1" if name == "nu" else self.stress_unit.text())):
                item = QTableWidgetItem(display_value(value))
                item.setData(Qt.ItemDataRole.UserRole, {"original": deepcopy(value)})
                if column != 1:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.coefficients.setItem(row, column, item)

    def _model_changed(self):
        if self._populating:
            return
        self._populating = True
        # Changing a law does not silently translate or invent its coefficients.
        self._populate_coefficients({})
        self._populating = False
        self._edited()

    def _edited(self, *_):
        if self._populating:
            return
        self.local_dirty = True
        self._update_protocol_label()
        self._update_actions()
        self._draw_results()

    def _update_protocol_label(self):
        if self._draft_problem:
            self.protocol_label.setText(self._draft_problem + " The original draft is preserved in Diagnostics. Save or use the owner's Undo/another client to repair it.")
            return
        fixed_lateral = self.history.rowCount() > 0 and all(
            self.history.item(row, column) is not None and
            edited_number(self.history.item(row, column).text()) == value
            for row in range(self.history.rowCount())
            for column, value in ((2, 0), (3, 0), (4, 0), (5, 1), (6, 0), (7, 0), (8, 0), (9, 1)))
        self.protocol_label.setText(
            ("Constrained lateral strain: F22 = F33 = 1; shear components = 0. "
             if fixed_lateral else "All nine deformation-gradient components are prescribed. ") +
            "This is not a free tensile boundary solve or yield/physical qualification.")

    def edited_draft(self):
        self._commit_cell_editor()
        draft = deepcopy(self.document["draft"])
        if self._draft_problem:
            return draft
        settings = draft["settings"]
        settings["model"] = self.model.currentData()
        for key, field in (("stress_unit", self.stress_unit), ("time_unit", self.time_unit)):
            if field.text() != display_value(settings[key]):
                settings[key] = field.text()
        settings["parameters"] = {self.coefficients.item(row, 0).text():
                                  edited_cell(self.coefficients, row, 1)
                                  for row in range(self.coefficients.rowCount())}
        settings["time"], settings["deformation_gradient"] = [], []
        for row in range(self.history.rowCount()):
            values = [edited_cell(self.history, row, column) for column in range(10)]
            settings["time"].append(values[0])
            settings["deformation_gradient"].append([values[1:4], values[4:7], values[7:10]])
        return draft

    def add_state(self):
        self._populating = True
        row = self.history.rowCount()
        self.history.insertRow(row)
        for column, value in enumerate([""] + [1 if i == j else 0 for i in range(3) for j in range(3)]):
            self.history.setItem(row, column, QTableWidgetItem(str(value)))
        self._populating = False
        self._edited()

    def remove_states(self):
        for row in sorted({item.row() for item in self.history.selectedIndexes()}, reverse=True):
            self.history.removeRow(row)
        self._edited()

    def command(self, operation, arguments=None, *, after=None):
        self._commit_cell_editor()
        if not self.document or self.conflict:
            return False
        if self.local_dirty and operation != "material.update":
            self.message.setText("Apply the edited inputs first; the service command must not silently ignore them.")
            return False
        document = deepcopy(self.document)

        def accepted(receipt):
            self.local_dirty = self.conflict = False
            job = receipt.get("job")
            self._show_document(receipt["document"], prefer_job=job.get("job_id", job.get("id")) if job else None)
            self.message.setText("Applied through the document owner: " + operation)
            if after:
                after()
            elif job:
                QTimer.singleShot(0, self.refresh_results)

        return self._call(lambda: self.client.document_command(document["id"], operation, arguments or {},
                         session_id=document["session_id"], expected_generation=document["generation"],
                         command_id="C" + uuid.uuid4().hex), accepted)

    def apply_inputs(self, *, after=None):
        return self.command("material.update", {"draft": self.edited_draft()}, after=after)

    def save_document(self, *, after=None):
        self._commit_cell_editor()
        if self.local_dirty:
            return self.apply_inputs(after=lambda: self.command("document.save", after=after))
        return self.command("document.save", after=after)

    def evaluate(self):
        # Requiring Apply makes the submitted generation visible and explicit.
        return self.command("material.evaluate")

    def refresh_document(self):
        if not self.document or self._busy:
            return
        identifier = self.document["id"]

        def refreshed(remote):
            changed = (remote["session_id"], remote["generation"]) != (self.document["session_id"], self.document["generation"])
            editing = self.local_dirty or any(table.state() == QAbstractItemView.State.EditingState
                                              for table in (self.history, self.coefficients))
            if changed and editing:
                self.conflict = True
                self.message.setText("Conflict: the service document changed while you were editing. Your cells are preserved. Reload the service version or keep these edits as a new document.")
            elif not self.conflict and not editing:
                self._show_document(remote)
            self._update_actions()
            QTimer.singleShot(0, self.refresh_results)

        self._call(lambda: self.client.document_read(identifier), refreshed, background=True)

    def reload_remote(self):
        answer = QMessageBox.question(self, "Reload service version", "Discard only this window's unapplied cells and reload the service document?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Yes:
            self._call(lambda: self.client.document_read(self.document["id"]), self._opened)

    def copy_edits(self):
        self.open_document(title=self.document["title"] + " — local edits", draft=self.edited_draft())

    def _selected_jobs(self):
        return [self.runs.item(row, 0).data(Qt.ItemDataRole.UserRole)
                for row in sorted({index.row() for index in self.runs.selectedIndexes()})]

    def open_numerical(self):
        self._commit_cell_editor()
        if self.local_dirty or self.conflict:
            self.message.setText("재료 편집을 적용한 뒤 피팅을 여세요. 계획의 시작값과 범위는 재료 계수와 별도로 편집합니다.")
            return
        if self.document:
            from .numerical_window import NumericalWindow
            window = NumericalWindow(self.client, material_document=deepcopy(self.document))
            self._numerical_windows.append(window)
            window.show()
            window.raise_()
            return window

    def open_runner(self):
        from .runner_window import RunnerWindow
        selected = self._selected_jobs()
        identifier = selected[0] if len(selected) == 1 else None
        if self._runner is None:
            self._runner = RunnerWindow(self.client, job_id=identifier, on_open_origin=self.open_run_origin)
        elif identifier:
            self._runner.select_job(identifier)
        self._runner.show()
        self._runner.raise_()

    def open_run_origin(self, job_id):
        """Navigate to retained input ownership without adopting or resubmitting it."""
        if self.document and any(run["job_id"] == job_id for run in self.document.get("runs", [])):
            self._populate_runs(prefer_job=job_id)
            self._selection_changed()
            self.show()
            self.raise_()
            return
        def open_origin():
            def found(payload):
                document = next((item for item in payload["documents"] if item.get("kind") == "material"
                                 and any(run["job_id"] == job_id for run in item.get("runs", []))), None)
                if document is None:
                    self.message.setText("This job has no linked Material document in this service.")
                    self.show()
                    self.raise_()
                    return
                self.local_dirty = self.conflict = False
                self._result_cache.clear()
                self._job_status.clear()
                self._result_errors.clear()
                self._show_document(document, prefer_job=job_id)
                self.message.setText("Opened the origin document; the selected run retains its submitted inputs.")
                self.show()
                self.raise_()
                QTimer.singleShot(0, self.refresh_results)
            self._call(self.client.documents, found)
        self._leave(open_origin)

    def _populate_runs(self, *, prefer_job=None):
        selected = [prefer_job] if prefer_job else self._selected_jobs()
        self.runs.blockSignals(True)
        runs = self.document.get("runs", []) if self.document else []
        self.runs.setRowCount(len(runs))
        for row, run in enumerate(runs):
            identifier = run["job_id"]
            state = self._job_status.get(identifier, {}).get("state", "상태 확인 중")
            state = {'SUCCEEDED': '완료', 'FAILED': '실패', 'REJECTED': '실행 거부',
                     'PARTIAL_FAILURE': '일부 실패', 'CANCELLED': '취소됨', 'INTERRUPTED': '중단됨',
                     'QUEUED': '대기 중', 'RUNNING': '계산 중', 'SAVED': '저장됨'}.get(state, state)
            stale = not run.get("is_current_input", run["input_generation"] == self.document["generation"]) or self.local_dirty
            texts = (f"계산 {row + 1}", state, f"입력 {run['input_generation']}",
                     "입력이 달라짐" if stale else "현재 입력과 같음")
            for column, value in enumerate(texts):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, identifier)
                item.setToolTip(f"실행 ID: {identifier}\n입력 해시: {run.get('input_sha256', '')}")
                self.runs.setItem(row, column, item)
        self.runs.clearSelection()
        if not selected and runs:
            selected = [runs[-1]["job_id"]]
        for row, run in enumerate(runs):
            if run["job_id"] in selected:
                for column in range(self.runs.columnCount()):
                    self.runs.item(row, column).setSelected(True)
        self.runs.blockSignals(False)

    def _selection_changed(self):
        self.runner_button.setEnabled(len(self._selected_jobs()) == 1)
        self._draw_results()
        self._show_diagnostics()
        self.refresh_results()

    def refresh_results(self):
        if self._busy or not self.document:
            return
        identifiers = self._selected_jobs()
        if not identifiers:
            return
        pending = [identifier for identifier in identifiers if identifier not in self._result_cache]
        if not pending:
            return
        document_id = self.document["id"]
        runs = {run["job_id"]: deepcopy(run) for run in self.document.get("runs", [])}

        def read():
            results = []
            for identifier in pending:
                retained = runs.get(identifier, {})
                if retained.get("retention_complete"):
                    status = {"state": retained.get("retained_state", "SAVED"),
                              "result_refs": [retained["retained_result"]] if retained.get("retained_result") else [],
                              "error": retained.get("retained_error"),
                              "source": "saved document"}
                else:
                    status = self.client.status(identifier)
                result, error = None, None
                if status.get("result_refs") or status.get("state") == "SUCCEEDED":
                    try:
                        result = self.client.document_result(document_id, identifier, selection=list(STRESS_COMPONENTS))
                    except Exception as exc:
                        error = error_message(exc)
                results.append((identifier, status, result, error))
            return results

        def received(rows):
            for identifier, status, result, error in rows:
                self._job_status[identifier] = status
                if result is not None:
                    self._result_cache[identifier] = result
                if error:
                    self._result_errors[identifier] = error
            self._populate_runs()
            self._draw_results()
            self._show_diagnostics()

        self._call(read, received, background=True)

    def _draw_results(self, *_):
        self.axes.clear()
        self._plot_errors = {}
        self.values.setRowCount(0)
        component = self.response.currentText()
        expected_axis = None
        for identifier in self._selected_jobs():
            result = self._result_cache.get(identifier, {})
            response = result.get("responses", {}).get(component)
            if not response:
                continue
            axes = response.get("axes", [])
            values = response.get("value", [])
            if len(axes) != 1 or len(axes[0].get("values", [])) != len(values):
                self._plot_errors[identifier] = "Response has no matching one-dimensional axis; not plotted."
                continue
            signature = (axes[0].get("name"), axes[0].get("unit"), response.get("unit"),
                         response.get("measure", response.get("stress_measure")), response.get("component"),
                         response.get("location"), response.get("frame"))
            if expected_axis is not None and signature != expected_axis:
                self._plot_errors[identifier] = "Unit, axis, stress measure, component, location or frame differs; no implicit conversion or overlay."
                continue
            expected_axis = signature
            run = next((item for item in self.document.get("runs", []) if item["job_id"] == identifier), {})
            generation = run.get("input_generation", "?")
            stale = self.local_dirty or not run.get("is_current_input", generation == self.document["generation"])
            number = next(index + 1 for index, item in enumerate(self.document['runs']) if item['job_id'] == identifier)
            label = f"Run {number}" + (" (earlier input)" if stale else "")
            try:
                times = [float(value) for value in axes[0]["values"]]
                numbers = [float(value) for value in values]
                if not all(math.isfinite(value) for value in times + numbers):
                    raise ValueError("nonfinite response")
            except (ValueError, TypeError):
                self._plot_errors[identifier] = "Invalid response values are not drawn as a successful curve."
                continue
            self.axes.plot(times, numbers, marker="o", markersize=3, label=label)
            for time, value in zip(times, numbers):
                row = self.values.rowCount()
                self.values.insertRow(row)
                for column, text in enumerate((f"계산 {number}", f"{time:.12g} {signature[1]}", f"{value:.12g} {signature[2]}")):
                    self.values.setItem(row, column, QTableWidgetItem(text))
        if self.axes.lines:
            self.axes.set_xlabel(f"{expected_axis[0]} [{expected_axis[1]}]")
            self.axes.set_ylabel(f"{component} [{expected_axis[2]}]")
            self.axes.set_title(expected_axis[3] or "Actual retained response")
            self.axes.legend(fontsize=8)
            self.axes.grid(True, alpha=.25)
        else:
            self.axes.text(.5, .5, "No retained response selected\nApply inputs and run once, or select an existing run.",
                           ha="center", va="center", transform=self.axes.transAxes)
            self.axes.set_axis_off()
        self.canvas.draw_idle()
        self._show_diagnostics()

    def _show_diagnostics(self):
        if not self.document:
            return
        content = {"document_diagnostics": self.document.get("diagnostics", []), "selected_runs": []}
        if self._draft_problem:
            content.update(table_view_diagnostic=self._draft_problem, preserved_draft=self.document["draft"])
        for identifier in self._selected_jobs():
            content["selected_runs"].append({"job_id": identifier, "status": self._job_status.get(identifier),
                "diagnostics": self._result_cache.get(identifier, {}).get("diagnostics"),
                "checks": self._result_cache.get(identifier, {}).get("checks"),
                "read_error": self._result_errors.get(identifier), "plot_error": self._plot_errors.get(identifier)})
        self.diagnostics.setPlainText(json.dumps(content, ensure_ascii=False, indent=2))
        unreadable = any(self._result_errors.get(identifier) or self._plot_errors.get(identifier)
                         for identifier in self._selected_jobs())
        blocked = any(item.get('blocks_evaluation') for item in self.document.get('diagnostics', []))
        self.result_notice.setText('일부 결과를 읽거나 겹쳐 그릴 수 없습니다. 진단 상세에서 원인을 확인하세요.'
            if unreadable else '입력에 문제가 있어 계산할 수 없습니다. 진단 상세에서 원인을 확인하세요.'
            if blocked else '')
        self.result_notice.setVisible(unreadable or blocked)

    def _update_actions(self):
        present = self.document is not None
        enabled = present and not self._busy and not self.conflict
        self.editor.setEnabled(present and not self._foreground_busy and not self._draft_problem)
        self.apply_button.setEnabled(enabled and self.local_dirty and not self._draft_problem)
        blocked = present and any(item.get("blocks_evaluation") for item in self.document.get("diagnostics", []))
        self.run_button.setEnabled(enabled and not self.local_dirty and not self._draft_problem and not blocked)
        self.save_action.setEnabled(enabled)
        self.undo_action.setEnabled(enabled and not self.local_dirty and self.document.get("can_undo", False))
        self.redo_action.setEnabled(enabled and not self.local_dirty and self.document.get("can_redo", False))
        self.new_action.setEnabled(not self._busy)
        self.open_action.setEnabled(not self._busy)
        self.runner_button.setEnabled(len(self._selected_jobs()) == 1)
        self.reload_button.setVisible(self.conflict)
        self.copy_button.setVisible(self.conflict)
        self.reload_button.setEnabled(not self._busy)
        self.copy_button.setEnabled(not self._busy)
        if present:
            dirty = self.local_dirty or self.document.get("dirty", False)
            self.setWindowTitle(f"Material Research — {self.document['title']}" + (" *" if dirty else ""))
            self.identity_label.setText("입력 적용 필요" if self.local_dirty else
                "저장하지 않은 변경" if dirty else "새 문서" if self.document.get('saved_revision') is None else "저장됨")
            self.identity_label.setToolTip(f"Document: {self.document['id']}\nOwner session: {self.document['session_id']}")

    def _leave(self, continuation):
        self._commit_cell_editor()
        if self._busy:
            self.message.setText("Wait for the current document request before leaving. Running solver jobs remain service-owned.")
            return
        if not self.document or not (self.local_dirty or self.document.get("dirty")):
            continuation()
            return
        question = QMessageBox(self)
        question.setWindowTitle("Unsaved material document")
        question.setText("Save this document before leaving?")
        question.setInformativeText("Keep draft sends unapplied cells to the shared owner but does not save a document revision. Running jobs continue independently.")
        save = question.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        keep = question.addButton("Keep service draft", QMessageBox.ButtonRole.DestructiveRole)
        question.addButton(QMessageBox.StandardButton.Cancel)
        question.exec()
        if question.clickedButton() == save:
            self.save_document(after=continuation)
        elif question.clickedButton() == keep:
            if self.conflict:
                self.message.setText("Resolve the remote conflict or keep edits as a new document before leaving.")
            elif self.local_dirty:
                self.apply_inputs(after=continuation)
            else:
                continuation()

    def _commit_cell_editor(self):
        focus = QApplication.focusWidget()
        if focus and any(table.isAncestorOf(focus) for table in (self.history, self.coefficients)):
            focus.clearFocus()

    def new_document(self):
        def create():
            title, accepted = QInputDialog.getText(self, "New material document", "Title", text="Material study")
            if accepted and title.strip():
                self.open_document(title=title.strip())
        self._leave(create)

    def open_constitutive(self):
        jobs=self._selected_jobs()
        if not self.document or len(jobs)!=1:
            self.message.setText('계산 결과 하나를 선택하세요.');return
        from .constitutive_inspection_window import ConstitutiveInspectionWindow
        window=ConstitutiveInspectionWindow(self.client,self.document['id'],jobs[0],self)
        self._native_material_windows.append(window);window.show()

    def new_native_law(self):
        from caelab.material_document import NATIVE_LAWS
        from caelab.simulation_document import default_draft
        labels=['탄성 재료점 (MFront)','유한변형 SVK','Maxwell 점탄성','사용자 MFront 법칙']
        selected, accepted = QInputDialog.getItem(self, '새 구성식', '구성식', labels, 0, False)
        if accepted:
            backend=NATIVE_LAWS[labels.index(selected)]
            self._call(lambda: self.client.document_open(kind='material', title=selected,
                       draft=default_draft(backend)), self._opened)

    def choose_document(self):
        def choose():
            def listed(payload):
                documents = [item for item in payload["documents"] if item.get("kind") == "material"]
                labels = [f"{item['title']} — {item['id']}" for item in documents]
                if not labels:
                    self.message.setText("No saved material documents are available.")
                    return
                label, accepted = QInputDialog.getItem(self, "Open material document", "Document", labels, editable=False)
                if accepted:
                    self.open_document(document_id=documents[labels.index(label)]["id"])
            self._call(self.client.documents, listed)
        self._leave(choose)

    def closeEvent(self, event):
        if self._allow_close:
            self.timer.stop()
            event.accept()
            return
        event.ignore()
        def leave():
            self._allow_close = True
            self.close()
        self._leave(leave)

    def showEvent(self, event):
        self._allow_close = False
        if self.timer.interval() > 0:
            self.timer.start()
        super().showEvent(event)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", default=os.environ.get("CAELAB_SERVICE_URL"))
    parser.add_argument("--document-id")
    parser.add_argument("--title", default="Material study")
    args = parser.parse_args(argv)
    if not args.service:
        parser.error("--service or CAELAB_SERVICE_URL must identify an existing local service")
    client = Client(args.service)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    document = client.document_read(args.document_id) if args.document_id else None
    from caelab.material_document import NATIVE_LAWS
    if document and document.get('kind') == 'material' and document['draft'].get('backend') in NATIVE_LAWS:
        from .native_material_window import NativeMaterialWindow
        window = NativeMaterialWindow(client, auto_open=False)
        window._opened(document)
    else:
        window = MaterialWindow(client, document_id=args.document_id, title=args.title)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
