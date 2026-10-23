"""Read existing service jobs and their retained results in an independent Qt window.

Run ``python -m apps.research.runner_window --service http://127.0.0.1:PORT``.
Opening, selecting and closing this window never submit or replay a calculation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
import sys
import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QFormLayout, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QMainWindow, QPlainTextEdit, QPushButton,
    QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QToolBar,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from caelab.workbench_client import Client


TERMINAL = {"SUCCEEDED", "FAILED", "PARTIAL_FAILURE", "CANCELLED", "INTERRUPTED", "REJECTED"}
PARENT_OPERATIONS = {"fit", "doe", "optimize", "uq", "sensitivity", "surrogate", "epsilon"}
MAX_SERIES_ROWS = 2000
MAX_LEDGER_ROWS = 200


def text_value(value):
    if value is None:
        return "Not recorded"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def short_value(value, limit=140):
    text = text_value(value)
    return text if len(text) <= limit else text[:limit] + "…"


def candidate_state(row):
    status = row.get("execution_status", "UNKNOWN")
    if row.get("prediction_status") == "PREDICTED" and status != "PREDICTED":
        return "PREDICTED — imported status: " + str(status)
    return status


def actual_candidate(row):
    return (row.get("execution_status") == "SUCCEEDED"
            and row.get("prediction_status") != "PREDICTED")


def request_error(error):
    if hasattr(error, "read"):
        try:
            return text_value(json.loads(error.read()))
        except (ValueError, OSError, UnicodeError):
            pass
    return str(error)


def state_description(job):
    state = job.get("state", job.get("status", "UNKNOWN"))
    descriptions = {
        "QUEUED": "Queued",
        "RUNNING": "Running",
        "CANCEL_REQUESTED": "Cancellation requested — waiting for a safe stop",
        "CLEANUP_PENDING": "Cleanup pending — termination is unconfirmed",
        "CANCELLED": "Cancelled — terminal receipt recorded by the service",
        "INTERRUPTED": "Interrupted — controller tracking was lost; process termination is unconfirmed",
        "PARTIAL_FAILURE": "Finished with partial failures",
        "SUCCEEDED": "Succeeded",
        "FAILED": "Failed",
        "REJECTED": "Rejected",
    }
    description = descriptions.get(state, state)
    if job.get("cleanup_unconfirmed") and state not in {"CLEANUP_PENDING", "INTERRUPTED"}:
        description += " — cleanup is unconfirmed"
    if job.get("cancel_requested") and state in {"SUCCEEDED", "FAILED", "PARTIAL_FAILURE"}:
        description += "; a cancellation request was recorded"
    return description


def wall_time(job):
    start = job.get("started_utc")
    if not start:
        return "Not started" if job.get("state") == "QUEUED" else "Not recorded"
    end = job.get("finished_utc")
    suffix = ""
    if not end and job.get("state") in TERMINAL:
        if job.get("state") != "INTERRUPTED" or not job.get("updated_utc"):
            return "Finish time not recorded"
        end, suffix = job["updated_utc"], " to last update"
    try:
        beginning = datetime.fromisoformat(start.replace("Z", "+00:00"))
        ending = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else datetime.now(timezone.utc)
        if beginning.tzinfo is None or ending.tzinfo is None:
            return "Timestamp timezone not recorded"
        seconds = (ending - beginning).total_seconds()
        if seconds < 0:
            return "Inconsistent timestamps"
        return f"{seconds:.1f} s{suffix}" + (" since start" if not end else "")
    except (ValueError, TypeError):
        return "Invalid recorded timestamps"


def readonly_table(headers):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def table_row(table, row, values):
    for column, value in enumerate(values):
        item = QTableWidgetItem(text_value(value))
        table.setItem(row, column, item)


def fill_tree(tree, mapping):
    tree.clear()
    def append(parent, key, value, depth=0):
        nested = isinstance(value, (dict, list))
        item = QTreeWidgetItem([str(key), f"{len(value)} entries" if nested else text_value(value)])
        parent.addChild(item) if isinstance(parent, QTreeWidgetItem) else parent.addTopLevelItem(item)
        if nested and depth < 10:
            entries = list(value.items()) if isinstance(value, dict) else list(enumerate(value))
            for name, child in entries[:50]:
                append(item, name, child, depth + 1)
            if len(entries) > 50:
                item.addChild(QTreeWidgetItem(["Remaining entries", "Available in the Details tab"]))
        elif nested:
            item.addChild(QTreeWidgetItem(["Nested input", "Available in the Details tab"]))
    for key, value in mapping.items():
        append(tree, key, value)
    tree.expandToDepth(1)


class _Signals(QObject):
    finished = Signal(object, object)


class _Read(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = _Signals()

    def run(self):
        try:
            value = self.function()
        except Exception as error:
            self.signals.finished.emit(None, request_error(error))
        else:
            self.signals.finished.emit(value, None)


class RunnerWindow(QMainWindow):
    """Existing-job consumer; the service remains the execution owner."""

    job_selected = Signal(str)
    open_origin = Signal(str)

    def __init__(self, client, *, job_id=None, poll_interval=2000, on_open_origin=None):
        super().__init__()
        self.client = client
        self.jobs = {}
        self.selected_job_id = None
        self._initial_job_id = job_id
        self._workers, self._pending, self._job_versions = {}, {}, {}
        self._ticket = self._selection_epoch = self._response_epoch = 0
        self._closed = False
        self._poll_interval = poll_interval
        self._input_snapshot = None
        self.result_metadata = None
        self._ledger = []
        self._ledger_kind = None
        self._on_open_origin = on_open_origin
        self._build_ui()
        if on_open_origin is not None:
            self.open_origin.connect(on_open_origin)
        self.timer = QTimer(self)
        self.timer.setInterval(max(1, poll_interval))
        self.timer.timeout.connect(self.refresh)
        if poll_interval > 0:
            self.timer.start()
        self.refresh()

    def _build_ui(self):
        self.setWindowTitle("Runner — existing executions")
        self.resize(1420, 940)
        self.setMinimumSize(900, 650)
        tools = self.menuBar().addMenu("&Tools")
        for kind, label in (("pre", "CAD/FE — FreeCAD…"), ("post", "Post — external result…"),
                            ("data", "Data…"), ("material", "Material…"), ("numerical", "Numerical Plan…"),
                            ("pde", "PDE…"), ("simulation", "Simulation…"), ("evaluation", "Evaluation definition…"),
                            ("study", "Study…"), ("expert", "Expert discussion…")):
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, tool=kind: self.open_tool(tool))
            tools.addAction(action)
        toolbar = QToolBar("Execution records")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.refresh_action = QAction("Refresh", self, shortcut=QKeySequence.Refresh)
        self.refresh_action.triggered.connect(self.refresh)
        toolbar.addAction(self.refresh_action)
        self.result_button = QPushButton("Read retained result")
        self.result_button.clicked.connect(self.read_result)
        toolbar.addWidget(self.result_button)
        self.cancel_button = QPushButton("Request cancellation")
        self.cancel_button.clicked.connect(self.cancel_selected)
        toolbar.addWidget(self.cancel_button)
        self.origin_button = QPushButton("Open source document")
        self.origin_button.clicked.connect(self.open_selected_origin)
        toolbar.addWidget(self.origin_button)
        self.post_button = QPushButton("Open retained field in Post")
        self.post_button.clicked.connect(self.open_selected_post)
        toolbar.addWidget(self.post_button)

        self.study_button = QPushButton('Use selected result in Study')
        self.study_button.clicked.connect(self.open_selected_study)
        toolbar.addWidget(self.study_button)
        root = QWidget()
        layout = QVBoxLayout(root)
        self.message = QLabel("Reading existing service jobs…")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        split = QSplitter(Qt.Orientation.Vertical)
        self.job_table = readonly_table(["Name", "Job ID", "Operation / backend", "State", "Started (UTC)", "Wall time", "Resources", "Results"])
        self.job_table.setObjectName("runnerJobs")
        for column, width in enumerate((160, 240, 230, 160, 185, 130, 140, 100)):
            self.job_table.setColumnWidth(column, width)
        self.job_table.itemSelectionChanged.connect(self._table_selected)
        split.addWidget(self.job_table)
        self.tabs = QTabWidget()

        monitor = QWidget()
        monitor_layout = QVBoxLayout(monitor)
        self.state_label = QLabel("Select an existing job")
        self.state_label.setWordWrap(True)
        self.state_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        monitor_layout.addWidget(self.state_label)
        self.scope_label = QLabel()
        self.scope_label.setWordWrap(True)
        monitor_layout.addWidget(self.scope_label)
        grid = QGridLayout()
        self.monitor_fields = {}
        fields = ("Job ID", "Operation", "Backend", "Phase", "Created UTC", "Started UTC", "Finished UTC", "Wall time",
                  "Resources", "Enforcement", "Host", "Attempt", "Source request", "Input hash", "Result references")
        for index, name in enumerate(fields):
            row, pair = divmod(index, 2)
            label = QLabel()
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(QLabel(name), row, pair * 2)
            grid.addWidget(label, row, pair * 2 + 1)
            self.monitor_fields[name] = label
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        monitor_layout.addLayout(grid)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        monitor_layout.addWidget(self.error_label)
        monitor_layout.addStretch()
        self.tabs.addTab(monitor, "Monitor")

        self.inputs = QTreeWidget()
        self.inputs.setHeaderLabels(["Frozen input", "Recorded value"])
        self.inputs.setColumnWidth(0, 320)
        self.tabs.addTab(self.inputs, "Inputs")
        self.result_panel = QWidget()
        result_layout = QVBoxLayout(self.result_panel)
        self.result_summary = QLabel("Use Read retained result to inspect this job's original output.")
        self.result_summary.setWordWrap(True)
        result_layout.addWidget(self.result_summary)
        controls = QHBoxLayout()
        self.responses = QComboBox()
        self.responses.setMinimumContentsLength(24)
        self.responses.currentIndexChanged.connect(self._response_changed)
        controls.addWidget(QLabel("Response"))
        controls.addWidget(self.responses, 1)
        self.row_start = QSpinBox()
        self.row_start.setRange(0, 2_000_000_000)
        self.row_count = QSpinBox()
        self.row_count.setRange(1, MAX_SERIES_ROWS)
        self.row_count.setValue(MAX_SERIES_ROWS)
        controls.addWidget(QLabel("First row"))
        controls.addWidget(self.row_start)
        controls.addWidget(QLabel("Count"))
        controls.addWidget(self.row_count)
        self.read_rows_button = QPushButton("Read rows")
        self.read_rows_button.clicked.connect(self.read_response)
        controls.addWidget(self.read_rows_button)
        result_layout.addLayout(controls)
        self.response_label = QLabel()
        self.response_label.setWordWrap(True)
        result_layout.addWidget(self.response_label)
        self.result_views = QTabWidget()
        self.figure = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)
        self.result_views.addTab(self.canvas, "Plot")
        self.values = readonly_table(["Original row", "Axis", "Value", "Mask"])
        self.result_views.addTab(self.values, "Values")
        self.response_details = QPlainTextEdit()
        self.response_details.setReadOnly(True)
        self.result_views.addTab(self.response_details, "Response metadata / references")
        result_layout.addWidget(self.result_views, 1)
        self.tabs.addTab(self.result_panel, "Result")

        self.ledger_panel = QWidget()
        ledger_layout = QVBoxLayout(self.ledger_panel)
        self.ledger_label = QLabel()
        self.ledger_label.setWordWrap(True)
        ledger_layout.addWidget(self.ledger_label)
        ledger_controls = QHBoxLayout()
        ledger_controls.addWidget(QLabel("First record"))
        self.ledger_start = QSpinBox()
        self.ledger_start.valueChanged.connect(self._draw_ledger)
        ledger_controls.addWidget(self.ledger_start)
        ledger_controls.addStretch()
        ledger_layout.addLayout(ledger_controls)
        self.ledger_table = readonly_table([])
        self.ledger_table.itemSelectionChanged.connect(self._ledger_selected)
        ledger_layout.addWidget(self.ledger_table, 2)
        self.ledger_details = QPlainTextEdit()
        self.ledger_details.setReadOnly(True)
        ledger_layout.addWidget(self.ledger_details, 1)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.tabs.addTab(self.details, "Details")
        split.addWidget(self.tabs)
        split.setSizes([400, 460])
        layout.addWidget(split, 1)
        self.setCentralWidget(root)
        self._clear_result()
        self._update_actions()

    def _request(self, key, function, accepted, *, relevant=None):
        if key in self._pending or self._closed:
            return False
        self._ticket += 1
        ticket = self._ticket
        worker = _Read(function)
        self._workers[ticket] = worker
        self._pending[key] = ticket
        self._update_actions()
        def finished(value, error):
            self._workers.pop(ticket, None)
            self._pending.pop(key, None)
            if self._closed:
                return
            if relevant is None or relevant():
                if error:
                    self.message.setText("Service request failed: " + error)
                else:
                    accepted(value, ticket)
            self._update_actions()
        worker.signals.finished.connect(finished, Qt.ConnectionType.QueuedConnection)
        QThreadPool.globalInstance().start(worker)
        return True

    def _merge_job(self, job, ticket):
        identifier = job.get("id", job.get("job_id"))
        if identifier and ticket >= self._job_versions.get(identifier, -1):
            self.jobs[identifier] = deepcopy(job)
            self._job_versions[identifier] = ticket
            return True
        return False

    def refresh(self):
        def listed(payload, ticket):
            for job in payload.get("jobs", []):
                self._merge_job(job, ticket)
            self._draw_jobs()
            if self.selected_job_id is None:
                desired = self._initial_job_id or (self._ordered_ids()[0] if self.jobs else None)
                self._initial_job_id = None
                if desired:
                    self.select_job(desired)
            elif self.selected_job_id in self.jobs:
                self._show_job(self.jobs[self.selected_job_id])
            self.message.setText(f"{len(self.jobs)} recorded jobs. Selecting a job does not execute it.")
        self._request("catalog", lambda: self.client.request("/api/workbench"), listed)
        if self.selected_job_id:
            self.refresh_selected()

    def _ordered_ids(self):
        return sorted(self.jobs, key=lambda key: (self.jobs[key].get("created_utc", ""), key), reverse=True)

    def _draw_jobs(self):
        self.job_table.blockSignals(True)
        self.job_table.setRowCount(len(self.jobs))
        selected_row = None
        for row, identifier in enumerate(self._ordered_ids()):
            job = self.jobs[identifier]
            arguments = job.get("arguments", {})
            table_row(self.job_table, row, [arguments.get("label", job.get("operation", "")), identifier,
                job.get("operation", "") + " / " + text_value(arguments.get("backend")), job.get("state", "UNKNOWN"),
                job.get("started_utc"), wall_time(job), short_value(job.get("resources", {})),
                "Retained" if job.get("result_refs") else "None recorded"])
            self.job_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, identifier)
            self.job_table.item(row, 3).setToolTip(state_description(job))
            if identifier == self.selected_job_id:
                selected_row = row
        self.job_table.clearSelection()
        if selected_row is not None:
            self.job_table.selectRow(selected_row)
        self.job_table.blockSignals(False)

    def _table_selected(self):
        rows = self.job_table.selectionModel().selectedRows()
        if rows:
            self.select_job(self.job_table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole))

    def select_job(self, identifier):
        if identifier == self.selected_job_id:
            self.refresh_selected()
            return
        self.selected_job_id = identifier
        self._selection_epoch += 1
        self._clear_result()
        self._draw_jobs()
        self._show_job(self.jobs.get(identifier, {"id": identifier}))
        self.job_selected.emit(identifier)
        self.refresh_selected()

    def refresh_selected(self):
        identifier, epoch = self.selected_job_id, self._selection_epoch
        if not identifier:
            return
        def received(job, ticket):
            if self._merge_job(job, ticket):
                self._draw_jobs()
                self._show_job(self.jobs[identifier])
        self._request(f"status:{identifier}:{epoch}", lambda: self.client.status(identifier), received,
                      relevant=lambda: (identifier, epoch) == (self.selected_job_id, self._selection_epoch))

    def _show_job(self, job):
        arguments = job.get("arguments", {})
        self.state_label.setText(f"{job.get('id', self.selected_job_id)} · {state_description(job)}")
        operation = job.get("operation")
        self.scope_label.setText(
            f"Cancellation targets the whole selected {operation} execution. Candidate-level cancellation is unavailable."
            if operation in PARENT_OPERATIONS else
            "Cancellation targets this selected job. Independent jobs continue.")
        values = {"Job ID": job.get("id"), "Operation": operation, "Backend": arguments.get("backend"),
            "Phase": job.get("phase"), "Created UTC": job.get("created_utc"), "Started UTC": job.get("started_utc"),
            "Finished UTC": job.get("finished_utc"), "Wall time": wall_time(job), "Resources": job.get("resources"),
            "Enforcement": job.get("resource_enforcement"), "Host": job.get("host"), "Attempt": job.get("attempt"),
            "Source request": job.get("request_id"), "Input hash": job.get("request_hash"), "Result references": job.get("result_refs")}
        for name, field in self.monitor_fields.items():
            field.setText(text_value(values[name]))
        error = job.get("error")
        messages = [job.get("message", "")]
        if error:
            messages.append("Recorded error: " + text_value(error))
        self.error_label.setText("\n".join(message for message in messages if message))
        inputs = {"job_id": job.get("id", self.selected_job_id), "operation": operation,
                  "arguments": arguments, "resources": job.get("resources", {}),
                  "request_id": job.get("request_id"), "request_hash": job.get("request_hash")}
        if inputs != self._input_snapshot:
            fill_tree(self.inputs, inputs)
            self._input_snapshot = deepcopy(inputs)
        self._show_details()
        self._update_actions()

    def cancel_selected(self):
        identifier = self.selected_job_id
        if not identifier or self.jobs.get(identifier, {}).get("state") not in {"QUEUED", "RUNNING", "CLEANUP_PENDING"}:
            return
        self.message.setText(f"Sending cancellation request for {identifier}; completion is not yet confirmed.")
        def received(job, ticket):
            self._merge_job(job, ticket)
            self._draw_jobs()
            if self.selected_job_id == identifier:
                self._show_job(self.jobs[identifier])
            self.message.setText(identifier + " · " + state_description(job))
        self._request("cancel:" + identifier, lambda: self.client.cancel(identifier), received)

    def open_selected_origin(self):
        identifier, epoch = self.selected_job_id, self._selection_epoch
        if not identifier:
            return
        self.message.setText("Finding the exact source document…")
        def received(navigation, _ticket):
            origin = navigation.get("origin_document") or {}
            if origin.get("kind") == "material" and self._on_open_origin is not None:
                # Material's existing callback owns its unapplied local edits.
                self.open_origin.emit(identifier)
                return
            from .desktop import open_origin
            def opened(receipt, _ticket):
                self.message.setText("Source document: " + text_value(receipt.get("status")))
            self._request("open-origin:" + identifier,
                          lambda: open_origin(self.client, identifier), opened)
        self._request("navigation-origin:" + identifier, lambda: self.client.job_navigation(identifier), received,
                      relevant=lambda: (identifier, epoch) == (self.selected_job_id, self._selection_epoch))

    def open_selected_study(self):
        identifier, epoch = self.selected_job_id, self._selection_epoch
        if not identifier:
            return
        def opened():
            from .desktop import launch_tool
            navigation=self.client.job_navigation(identifier)
            origin=navigation.get('origin_document') or {}
            if not origin.get('id') or origin.get('kind') in {'pre','post','expert'}:
                raise ValueError('Select a saved research result; native project evidence remains in its source project')
            reference=self.client.document_result_reference(origin['id'],identifier)
            receipt=self.client.result_followup(reference,'study',session_id=origin['session_id'],command_id='C'+uuid.uuid4().hex)
            return launch_tool(self.client,'study',document_id=receipt['document']['id'])
        return self._request('study:'+str(identifier),opened,
            lambda result,ticket:self.message.setText('Opened an independent Study with the exact retained result; no calculation or inference was submitted.'),
            relevant=lambda:self.selected_job_id==identifier and self._selection_epoch==epoch)

    def open_tool(self, tool):
        from .desktop import launch_tool
        self._request("launch-tool:" + tool, lambda: launch_tool(self.client, tool),
                      lambda receipt, _ticket: self.message.setText(tool.title() + ": " + text_value(receipt.get("status"))))

    def open_selected_post(self):
        identifier, epoch = self.selected_job_id, self._selection_epoch
        if not identifier:
            return
        self.message.setText("Finding this job's retained native field…")
        def received(navigation, _ticket):
            post = navigation.get("post_input")
            if not post:
                self.message.setText("This job has no retained VTU/PVD field for Post. Its original responses remain available here.")
                return
            from .desktop import launch_post
            def launched(receipt, _ticket):
                self.message.setText("Post preparation started in a separate helper; any native preparation error will be shown.")
            self._request("open-post:" + identifier,
                          lambda: launch_post(self.client, post["id"], job_id=identifier), launched)
        self._request("navigation-post:" + identifier, lambda: self.client.job_navigation(identifier), received,
                      relevant=lambda: (identifier, epoch) == (self.selected_job_id, self._selection_epoch))

    def _update_actions(self):
        job = self.jobs.get(self.selected_job_id, {})
        state = job.get("state")
        self.refresh_action.setEnabled("catalog" not in self._pending)
        self.result_button.setEnabled(bool(job.get("result_refs")) and not any(key.startswith(f"result:{self.selected_job_id}:") for key in self._pending))
        self.origin_button.setEnabled(bool(job) and not any(key.endswith(":" + str(self.selected_job_id)) and "origin" in key for key in self._pending))
        self.post_button.setEnabled(bool(job.get("result_refs")) and not any(key.endswith(":" + str(self.selected_job_id)) and "post" in key for key in self._pending))
        self.cancel_button.setEnabled(state in {"QUEUED", "RUNNING", "CLEANUP_PENDING"} and "cancel:" + str(self.selected_job_id) not in self._pending)
        operation = job.get("operation")
        self.cancel_button.setText("Cancellation requested" if state == "CANCEL_REQUESTED" else
            "Request owned cleanup retry" if state == "CLEANUP_PENDING" else
            f"Cancel entire {operation}" if operation in PARENT_OPERATIONS else "Request cancellation")

    def _clear_result(self):
        self.result_metadata = None
        self._response_epoch += 1
        self.responses.blockSignals(True)
        self.responses.clear()
        self.responses.blockSignals(False)
        self.values.setRowCount(0)
        self.response_details.clear()
        self.response_label.clear()
        self.read_rows_button.setEnabled(False)
        self.row_start.setEnabled(False)
        self.row_count.setEnabled(False)
        self.result_summary.setText("Use Read retained result to inspect this job's original output.")
        self._ledger, self._ledger_kind = [], None
        index = self.tabs.indexOf(self.ledger_panel)
        if index >= 0:
            self.tabs.removeTab(index)
        self._blank_plot("No retained response selected")

    def _blank_plot(self, message):
        self.axes.clear()
        self.axes.set_axis_off()
        self.axes.text(.5, .5, message, ha="center", va="center", wrap=True, transform=self.axes.transAxes)
        self.canvas.draw_idle()

    def read_result(self):
        identifier, epoch = self.selected_job_id, self._selection_epoch
        if not identifier or not self.jobs.get(identifier, {}).get("result_refs"):
            return
        self.tabs.setCurrentWidget(self.result_panel)
        self.result_summary.setText(f"Reading retained result for {identifier}…")
        def received(result, _ticket):
            self.result_metadata = result
            state = result.get("execution_status", "Not recorded")
            details = [f"{identifier} · result execution: {state}"]
            for key in ("termination_reason", "failure_reason"):
                if result.get(key):
                    details.append(f"{key}: {text_value(result[key])}")
            if state in {"FAILED", "PARTIAL_FAILURE", "REJECTED", "CANCELLED"}:
                details.append("Retained values may be partial; this is not a successful full execution.")
            self.result_summary.setText("\n".join(details))
            self.responses.blockSignals(True)
            self.responses.clear()
            for name, response in result.get("responses", {}).items():
                self.responses.addItem(f"{name} · {response.get('kind', 'unknown')} · {response.get('unit', 'unit not recorded')}", name)
            self.responses.blockSignals(False)
            self._set_ledger(result)
            self._show_details()
            if self.responses.count():
                self._response_changed()
            else:
                self.response_label.setText("No scalar or series response catalog was returned. Recorded metadata and file references are available below and in Details.")
                self.response_details.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
                self.result_views.setCurrentWidget(self.response_details)
                self._blank_plot("No response available in this retained result")
        self._request(f"result:{identifier}:{epoch}", lambda: self.client.result(identifier, selection={"metadata_only": True}), received,
                      relevant=lambda: (identifier, epoch) == (self.selected_job_id, self._selection_epoch))

    def _response_changed(self, *_):
        self._response_epoch += 1
        self.row_start.setValue(0)
        self.read_response()

    def read_response(self):
        name = self.responses.currentData()
        if not self.result_metadata or name is None:
            return
        identifier, epoch = self.selected_job_id, self._selection_epoch
        self._response_epoch += 1
        response_epoch = self._response_epoch
        response = self.result_metadata.get("responses", {}).get(name, {})
        self.values.setRowCount(0)
        self._blank_plot("Reading the selected original response…")
        self.response_details.setPlainText(json.dumps(response, ensure_ascii=False, indent=2))
        kind = response.get("kind")
        self.read_rows_button.setEnabled(kind == "series")
        self.row_start.setEnabled(kind == "series")
        self.row_count.setEnabled(kind == "series")
        if kind not in {"scalar", "series"}:
            self.response_label.setText(f"{name}: {kind or 'unknown'} response. This viewer supports scalar values and one-dimensional series; use the recorded metadata/file references for this field. No field plot is synthesized.")
            self._blank_plot("Full-field display belongs in Post")
            self.result_views.setCurrentWidget(self.response_details)
            return
        start, count = self.row_start.value(), self.row_count.value()
        selection = {"responses": [name]}
        if kind == "series":
            selection["rows"] = [start, start + count]
        self.response_label.setText(f"Reading {name} for {identifier}…")
        def received(result, _ticket):
            selected = result.get("responses", {}).get(name)
            if selected is None:
                self.response_label.setText("The original result did not return this selected response.")
                self._blank_plot("Selected response unavailable")
                return
            self._draw_response(name, selected, start)
        self._request(f"response:{identifier}:{epoch}:{response_epoch}", lambda: self.client.result(identifier, selection=selection), received,
            relevant=lambda: (identifier, epoch, response_epoch) == (self.selected_job_id, self._selection_epoch, self._response_epoch))

    def _draw_response(self, name, response, start):
        self.response_details.setPlainText(json.dumps(response, ensure_ascii=False, indent=2))
        labels = [f"{key}: {text_value(response[key])}" for key in ("component", "location", "frame", "measure", "valid") if key in response]
        unit = response.get("unit", "unit not recorded")
        if response.get("kind") == "scalar":
            self.values.setRowCount(1)
            table_row(self.values, 0, ["scalar", "—", f"{text_value(response.get('value'))} {unit}", "—"])
            self.response_label.setText(f"{name} = {text_value(response.get('value'))} {unit}" + (" · " + " · ".join(labels) if labels else ""))
            self._blank_plot("Scalar value shown in Values")
            self.result_views.setCurrentWidget(self.values)
            return
        values, axes = response.get("value"), response.get("axes", [])
        if not isinstance(values, list) or len(axes) != 1 or not isinstance(axes[0].get("values"), list) or len(values) != len(axes[0]["values"]):
            self.response_label.setText("This response is not a matching one-dimensional series. Its actual metadata is retained; no curve is drawn.")
            self._blank_plot("Unsupported series shape")
            self.result_views.setCurrentWidget(self.response_details)
            return
        axis = axes[0]
        mask = response.get("mask")
        self.values.setRowCount(len(values))
        for row, (coordinate, value) in enumerate(zip(axis["values"], values)):
            included = mask[row] if isinstance(mask, list) and row < len(mask) else "Not supplied"
            table_row(self.values, row, [start + row, f"{text_value(coordinate)} {axis.get('unit', 'unit not recorded')}", f"{text_value(value)} {unit}", included])
        self.response_label.setText(f"{name} · original rows [{start}, {start + len(values)}) · {unit}" + (" · " + " · ".join(labels) if labels else ""))
        try:
            x = [float(value) for value in axis["values"]]
            y = [float(value) for value in values]
            if not all(math.isfinite(value) for value in x + y) or response.get("valid") is False:
                raise ValueError("Invalid retained response")
            if mask is not None and (not isinstance(mask, list) or len(mask) != len(y) or any(type(value) is not bool for value in mask)):
                raise ValueError("Unsupported mask")
        except (TypeError, ValueError, OverflowError):
            self.response_label.setText(self.response_label.text() + " · Invalid values or mask: inspect Values; no curve is drawn.")
            self._blank_plot("Retained invalid values are shown in Values")
            self.result_views.setCurrentWidget(self.values)
            return
        self.axes.clear()
        self.axes.set_axis_on()
        self.axes.plot(x, [value if mask is None or mask[row] else math.nan for row, value in enumerate(y)], marker="o", markersize=3)
        self.axes.set_xlabel(f"{axis.get('name', 'axis name not recorded')} [{axis.get('unit', 'unit not recorded')}]")
        self.axes.set_ylabel(f"{name} [{unit}]")
        self.axes.set_title(" · ".join(labels))
        self.axes.grid(True, alpha=.25)
        self.canvas.draw_idle()
        self.result_views.setCurrentWidget(self.canvas)

    def _set_ledger(self, result):
        self._ledger_kind = next((key for key in ("candidates", "history") if isinstance(result.get(key), list)), None)
        if self._ledger_kind is None:
            return
        self._ledger = result[self._ledger_kind]
        if self.tabs.indexOf(self.ledger_panel) < 0:
            self.tabs.insertTab(self.tabs.indexOf(self.details), self.ledger_panel, "Candidates" if self._ledger_kind == "candidates" else "History")
        self.ledger_start.blockSignals(True)
        self.ledger_start.setRange(0, max(0, len(self._ledger) - 1))
        self.ledger_start.setValue(0)
        self.ledger_start.blockSignals(False)
        self._draw_ledger()

    def _draw_ledger(self, *_):
        start = self.ledger_start.value()
        rows = self._ledger[start:start + MAX_LEDGER_ROWS]
        candidate = self._ledger_kind == "candidates"
        headers = ["Candidate", "Execution / prediction", "Variables", "Valid objective", "Penalty", "Failed / penalized / predicted objective", "Failure", "Scalar responses"] if candidate else list(dict.fromkeys(key for row in rows if isinstance(row, dict) for key in row))[:12]
        self.ledger_table.setColumnCount(len(headers))
        self.ledger_table.setHorizontalHeaderLabels(headers)
        self.ledger_table.setRowCount(len(rows))
        self.ledger_label.setText(f"Returned {self._ledger_kind or 'records'}: {len(self._ledger)}. Showing [{start}, {start + len(rows)}). " +
            ("Valid objectives exclude failed, penalized or predicted evaluations. Cancellation applies to the whole parent execution." if candidate else "Select a row to inspect the complete returned record."))
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            if candidate:
                eligible = actual_candidate(row) and "penalty_applied" not in row
                scalar = {name: f"{text_value(value.get('value'))} {value.get('unit', 'unit not recorded')}" for name, value in row.get("responses", {}).items() if value.get("kind") == "scalar"}
                values = [row.get("candidate_id"), candidate_state(row), short_value(row.get("values")),
                    row.get("objective") if eligible else "—", row.get("penalty_applied", "—"),
                    row.get("objective") if not eligible else "—", row.get("failure_reason", "—"), short_value(scalar)]
            else:
                values = [short_value(row.get(key)) for key in headers]
            table_row(self.ledger_table, index, values)
        self.ledger_details.clear()

    def _ledger_selected(self):
        rows = self.ledger_table.selectionModel().selectedRows()
        if rows:
            index = self.ledger_start.value() + rows[0].row()
            if index < len(self._ledger):
                self.ledger_details.setPlainText(json.dumps(self._ledger[index], ensure_ascii=False, indent=2))

    def _show_details(self):
        self.details.setPlainText(json.dumps({"job": self.jobs.get(self.selected_job_id), "result_metadata": self.result_metadata}, ensure_ascii=False, indent=2))

    def closeEvent(self, event):
        self._closed = True
        self.timer.stop()
        event.accept()

    def showEvent(self, event):
        super().showEvent(event)
        if self._closed:
            self._closed = False
            if self._poll_interval > 0:
                self.timer.start()
            self.refresh()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", default=os.environ.get("CAELAB_SERVICE_URL"))
    parser.add_argument("--job-id")
    args = parser.parse_args(argv)
    if not args.service:
        parser.error("--service or CAELAB_SERVICE_URL must identify the existing local service")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    client = Client(args.service)
    window = RunnerWindow(client, job_id=args.job_id)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
