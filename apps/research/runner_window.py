"""Read existing service jobs and their retained results in an independent Qt window.

Run ``python -m apps.research.runner_window --service http://127.0.0.1:PORT``.
Opening, selecting and closing never submit work. Explicit result readback creates
a separate service job without replaying a calculation.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QComboBox, QFormLayout, QGridLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMainWindow, QPlainTextEdit, QPushButton,
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


def operation_label(operation):
    return {"run": "실행", "evaluate": "계산", "fit": "재료 피팅", "doe": "실험계획",
            "optimize": "최적화", "uq": "불확실성 분석", "sensitivity": "민감도 분석",
            "surrogate": "대리모델", "epsilon": "다목적 최적화", "experts.ask": "전문가 질문",
            "experts.discuss": "전문가 토론", "data.import": "데이터 가져오기",
            "remote.run":"원격 제출", "remote.reconnect":"원격 상태 확인", "remote.cancel":"원격 취소",
            "remote.collect":"원격 결과 회수", "dynamic.reprocess": "동해석 결과 다시 읽기"}.get(operation, "등록된 작업" if operation else "기록 없음")


def backend_label(backend):
    names = {"structure.codeaster.frozen": "Code_Aster 사용자 모델 해석", "structure.calculix.contact": "CalculiX 구조 해석", "structure.calculix.frozen": "CalculiX 고정 입력 해석",
        "structure.calculix.native": "CalculiX 구조 해석", "structure.calculix.design": "CalculiX 설계 해석",
        "structure.calculix.shell": "CalculiX 셸 해석", "structure.calculix.beam": "CalculiX 빔 해석",
        "material.felupe": "FElupe 재료 계산", "files.table": "표 파일 읽기",
        "explicit.openradioss": "OpenRadioss 명시 해석", "explicit.opencourant.model": "OpenCourant 충격 해석",
        "damage.rainflow": "피로 평가", "pde.scipy.ode": "SciPy 상미분방정식",
        "pde.fenicsx.nonlinear": "FEniCSx 비선형 방정식", "pde.fenicsx.transient": "FEniCSx 시간 의존 방정식",
        "pde.fenicsx.vector": "FEniCSx 벡터 방정식", "pde.fenicsx.coupled": "FEniCSx 연성 방정식",
        "pde.fenicsx.imported": "FEniCSx 가져온 메시 방정식", "pde.fenicsx.dimensioned": "FEniCSx 차원 약형 방정식",
        "material.mfront.hyperelastic": "MFront 초탄성 재료", "material.mfront.viscoelastic": "MFront 점탄성 재료",
        "material.mfront.inverse": "MFront 재료 역추정", "material.mfront.user": "MFront 사용자 재료",
        "structural.code_aster.plasticity": "Code_Aster 소성 해석", "structural.code_aster.geometric_nonlinearity": "Code_Aster 기하 비선형 해석",
        "structural.code_aster.contact_patch": "Code_Aster 접촉 패치 해석", "fixture.cadquery": "CadQuery 형상 계산", "fixture.assembly": "조립 형상 계산",
        "scipy.latin_hypercube": "라틴 초입방 표본화", "scipy.differential_evolution": "차분 진화 탐색"}
    if backend in names:
        return names[backend]
    if isinstance(backend, str):
        for prefix, label in (("pde.fenicsx", "FEniCSx 방정식 계산"), ("material.mfront", "MFront 재료 계산"),
                              ("structural.code_aster", "Code_Aster 구조 해석"), ("fixture.freecad", "FreeCAD 형상 계산"),
                              ("fixture.calculix", "CalculiX 형상 해석")):
            if backend.startswith(prefix):
                return label
    return "등록된 계산 엔진" if backend else None


def timestamp_label(value):
    if not value:
        return "기록 없음"
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return value + " (시간대 미기록)"
        return stamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return "시각 기록 확인 필요"


def post_result_label(native):
    arrays = [row for row in (native.get("native_metadata") or {}).get("arrays", []) if isinstance(row, dict)]
    measures = {row.get("measure") for row in arrays}
    if "cauchy_stress_at_native_integration_point" in measures:
        title = "적분점 응력"
        arrays = [row for row in arrays if row.get("measure") == "cauchy_stress_at_native_integration_point"]
    elif "displacement" in measures and "nodal_reaction" in measures:
        title = "변위와 반력"
        arrays = [row for row in arrays if row.get("measure") in {"displacement", "nodal_reaction"}]
    else:
        title = native.get("name") or Path(native.get("path") or "공간 결과").name
    units = list(dict.fromkeys(row["units"] for row in arrays
                              if isinstance(row.get("units"), str) and row["units"] and row["units"] != "1"))
    return title + (" (" + ", ".join(units) + ")" if units else "")


def resource_label(resources):
    if not resources:
        return "기록 없음"
    if not isinstance(resources, dict):
        return text_value(resources)
    names = {"threads": "CPU 스레드", "memory_mb": "메모리(MB)"}
    return ", ".join(f"{names.get(key, key)} {value}" for key, value in resources.items())


def text_value(value):
    if value is None:
        return "기록 없음"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def short_value(value, limit=140):
    text = text_value(value)
    return text if len(text) <= limit else text[:limit] + "…"


def candidate_state(row):
    status = row.get("execution_status", "UNKNOWN")
    if row.get("prediction_status") == "PREDICTED" and status != "PREDICTED":
        return "예측값 (가져온 실행 상태: " + state_description({"state": status}) + ")"
    return "예측값" if status == "PREDICTED" else state_description({"state": status})


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
        "QUEUED": "대기 중",
        "RUNNING": "실행 중",
        "CANCEL_REQUESTED": "취소 요청됨 — 안전하게 멈출 수 있는 지점까지 대기 중",
        "CLEANUP_PENDING": "종료 처리 중 — 프로세스 종료 미확인",
        "CANCELLED": "취소 완료 — 실행 서비스에서 종료를 확인했습니다",
        "INTERRUPTED": "추적 중단 — 프로세스 종료 미확인",
        "PARTIAL_FAILURE": "일부 계산 실패",
        "SUCCEEDED": "완료",
        "FAILED": "실패",
        "REJECTED": "실행 거절",
        "UNKNOWN": "상태 미확인",
    }
    description = descriptions.get(state, "상태 확인 필요")
    if job.get("cleanup_unconfirmed") and state not in {"CLEANUP_PENDING", "INTERRUPTED"}:
        description += " — 프로세스 종료 미확인"
    if job.get("cancel_requested") and state in {"SUCCEEDED", "FAILED", "PARTIAL_FAILURE"}:
        description += " (실행 중 취소 요청이 있었습니다)"
    return description


def wall_time(job):
    start = job.get("started_utc")
    if not start:
        return "시작 전" if job.get("state") == "QUEUED" else "기록 없음"
    end = job.get("finished_utc")
    suffix = ""
    if not end and job.get("state") in TERMINAL:
        if job.get("state") != "INTERRUPTED" or not job.get("updated_utc"):
            return "종료 시각 미기록"
        end, suffix = job["updated_utc"], " (마지막 갱신까지)"
    try:
        beginning = datetime.fromisoformat(start.replace("Z", "+00:00"))
        ending = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else datetime.now(timezone.utc)
        if beginning.tzinfo is None or ending.tzinfo is None:
            return "시간대 미기록"
        seconds = (ending - beginning).total_seconds()
        if seconds < 0:
            return "시각 순서 확인 필요"
        return f"{seconds:.1f} s{suffix}" + (" (시작 후)" if not end else "")
    except (ValueError, TypeError):
        return "시각 기록 확인 필요"


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
    labels = {"operation": "작업 종류", "arguments": "실행 입력", "resources": "실행 자원",
        "backend": "계산 엔진", "label": "작업 이름", "settings": "계산 설정", "parameters": "매개변수",
        "threads": "CPU 스레드", "memory_mb": "메모리(MB)", "execution": "실행 설정", "workers": "동시 작업 수"}
    arguments = mapping.get("arguments") or {}
    native_reference = arguments.get("backend") in {"structure.calculix.contact", "structure.calculix.frozen", "structure.calculix.shell", "structure.calculix.beam", "structure.codeaster.frozen"}
    def append(parent, key, value, depth=0, path=()):
        if (not path and key in {"job_id", "request_id", "request_hash"} or
                path == ("arguments",) and key == "origin" and isinstance(value, dict) and "document_id" in value or
                path == ("arguments",) and mapping.get("operation") == "dynamic.reprocess" and key in {"source_job_id", "source_record"} or
                path == ("arguments", "settings") and key == "data_id" and native_reference):
            return
        nested = isinstance(value, (dict, list))
        shown = (f"{len(value)}개 항목" if nested else operation_label(value) if not path and key == "operation" else
                 backend_label(value) if path == ("arguments",) and key == "backend" else text_value(value))
        named_field = (not path and key in {"operation", "arguments", "resources"} or
            path == ("arguments",) and key in {"backend", "label", "settings", "execution"} or
            path == ("arguments", "settings") and key == "parameters" or
            path in {("resources",), ("arguments", "execution")} and key in {"threads", "memory_mb", "workers"})
        item = QTreeWidgetItem([labels.get(key, str(key)) if named_field else str(key), shown])
        parent.addChild(item) if isinstance(parent, QTreeWidgetItem) else parent.addTopLevelItem(item)
        if nested and depth < 10:
            entries = list(value.items()) if isinstance(value, dict) else list(enumerate(value))
            for name, child in entries[:50]:
                append(item, name, child, depth + 1, path + (key,))
            if len(entries) > 50:
                item.addChild(QTreeWidgetItem(["나머지 항목", "기술 상세에서 전체 원문 확인"]))
        elif nested:
            item.addChild(QTreeWidgetItem(["하위 입력", "기술 상세에서 전체 원문 확인"]))
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
        from .appearance import apply_appearance,configure_plot_fonts
        apply_appearance(QApplication.instance())
        configure_plot_fonts()
        self.client = client
        self.jobs = {}
        self.selected_job_id = None
        self._initial_job_id = job_id
        self._workers, self._pending, self._job_versions = {}, {}, {}
        self._ticket = self._selection_epoch = self._response_epoch = 0
        self._window_epoch = 0
        self._closed = False
        self._poll_interval = poll_interval
        self._input_snapshot = None
        self.result_metadata = None
        self._ledger = []
        self._ledger_kind = None
        self._on_open_origin = on_open_origin
        self._readback_requests = {}
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
        self.setWindowTitle("Runner — 실행 관리")
        self.resize(1420, 900)
        self.setMinimumSize(900, 650)
        tools = self.menuBar().addMenu("도구(&T)")
        for kind, label in (("pre", "CAD 및 전처리…"), ("post", "후처리…"),
                            ("data", "데이터…"), ("material", "재료…"), ("numerical", "수치 연구…"),
                            ("pde", "방정식…"), ("simulation", "해석…"), ("evaluation", "계산 절차…"),
                            ("study", "연구 기록…"), ("report", "보고서…"), ("expert", "전문가 토론…")):
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, tool=kind: self.open_tool(tool))
            tools.addAction(action)
        tools.addSeparator()
        remote_action = QAction('원격 실행…', self)
        remote_action.triggered.connect(self.open_remote_execution)
        tools.addAction(remote_action)
        toolbar = QToolBar("실행 작업")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.refresh_action = QAction("새로 고침", self, shortcut=QKeySequence.Refresh)
        self.refresh_action.triggered.connect(self.refresh)
        toolbar.addAction(self.refresh_action)
        self.result_button = QPushButton("결과 보기")
        self.result_button.clicked.connect(self.read_result)
        toolbar.addWidget(self.result_button)
        self.cancel_button = QPushButton("실행 취소")
        self.cancel_button.clicked.connect(self.cancel_selected)
        toolbar.addWidget(self.cancel_button)
        self.contact_steps_button = QPushButton('계산 단계…')
        self.contact_steps_button.clicked.connect(self.open_contact_steps)
        toolbar.addWidget(self.contact_steps_button)
        self.origin_button = QPushButton("입력 문서 열기")
        self.origin_button.clicked.connect(self.open_selected_origin)
        toolbar.addWidget(self.origin_button)
        self.post_button = QPushButton("후처리에서 열기")
        self.post_button.clicked.connect(self.open_selected_post)
        toolbar.addWidget(self.post_button)

        self.study_button = QPushButton('연구 기록에 추가…')
        self.study_button.clicked.connect(self.open_selected_study)
        toolbar.addWidget(self.study_button)
        root = QWidget()
        layout = QVBoxLayout(root)
        self.message = QLabel("실행 목록을 읽고 있습니다…")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        split = QSplitter(Qt.Orientation.Vertical)
        self.job_table = readonly_table(["작업", "실행 ID", "계산 방법", "상태", "시작 (UTC)", "경과 시간", "자원", "결과"])
        self.job_table.setObjectName("runnerJobs")
        for column, width in enumerate((190, 240, 200, 110, 185, 100, 140, 85)):
            self.job_table.setColumnWidth(column, width)
        self.job_table.setColumnHidden(1, True)
        self.job_table.itemSelectionChanged.connect(self._table_selected)
        split.addWidget(self.job_table)
        self.tabs = QTabWidget()

        monitor = QWidget()
        monitor_layout = QVBoxLayout(monitor)
        self.state_label = QLabel("위 목록에서 작업을 선택하세요.")
        self.state_label.setWordWrap(True)
        self.state_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        monitor_layout.addWidget(self.state_label)
        self.scope_label = QLabel()
        self.scope_label.setWordWrap(True)
        monitor_layout.addWidget(self.scope_label)
        grid = QGridLayout()
        technical_grid = QGridLayout()
        technical_panel = self.technical_panel = QWidget()
        technical_layout = QVBoxLayout(technical_panel)
        technical_layout.addLayout(technical_grid)
        self.monitor_fields = {}
        fields = ("Job ID", "Operation", "Backend", "Phase", "Created UTC", "Started UTC", "Finished UTC", "Wall time",
                  "Resources", "Enforcement", "Host", "Attempt", "Source request", "Input hash", "Result references")
        captions = dict(zip(fields, ("실행 ID", "작업 종류", "계산 엔진", "진행 단계", "등록 (UTC)",
            "시작 (UTC)", "종료 (UTC)", "경과 시간", "자원", "자원 제한 적용", "실행 컴퓨터",
            "실행 회차", "입력 요청", "입력 식별값", "저장 결과 참조")))
        technical = {"Job ID", "Enforcement", "Source request", "Input hash", "Result references"}
        normal_index = technical_index = 0
        for name in fields:
            destination = technical_grid if name in technical else grid
            index = technical_index if name in technical else normal_index
            row, pair = divmod(index, 2)
            label = QLabel()
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            destination.addWidget(QLabel(captions[name]), row, pair * 2)
            destination.addWidget(label, row, pair * 2 + 1)
            self.monitor_fields[name] = label
            if name in technical:
                technical_index += 1
            else:
                normal_index += 1
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        monitor_layout.addLayout(grid)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        monitor_layout.addWidget(self.error_label)
        self.readback_panel = QWidget()
        readback_layout = QVBoxLayout(self.readback_panel)
        readback_layout.setContentsMargins(0, 8, 0, 0)
        self.readback_label = QLabel()
        self.readback_label.setWordWrap(True)
        readback_layout.addWidget(self.readback_label)
        readback_actions = QHBoxLayout()
        self.reprocess_button = QPushButton("결과 다시 읽기")
        self.reprocess_button.setProperty("appearanceRole", "primary")
        self.reprocess_button.setToolTip("보존된 원 출력을 별도 작업으로 읽습니다. 새 솔버 계산은 시작하지 않습니다.")
        self.reprocess_button.clicked.connect(self.reprocess_selected)
        readback_actions.addWidget(self.reprocess_button)
        self.source_job_button = QPushButton("원 실행 선택")
        self.source_job_button.clicked.connect(self.select_readback_source)
        readback_actions.addWidget(self.source_job_button)
        readback_actions.addStretch()
        readback_layout.addLayout(readback_actions)
        monitor_layout.addWidget(self.readback_panel)
        monitor_layout.addStretch()
        self.tabs.addTab(monitor, "진행 상황")

        self.inputs = QTreeWidget()
        self.inputs.setHeaderLabels(["실행에 사용한 입력", "저장된 값"])
        self.inputs.setColumnWidth(0, 320)
        self.tabs.addTab(self.inputs, "입력")
        self.result_panel = QWidget()
        result_layout = QVBoxLayout(self.result_panel)
        self.result_summary = QLabel("결과 보기를 누르면 선택한 실행의 저장 결과를 읽습니다.")
        self.result_summary.setWordWrap(True)
        result_layout.addWidget(self.result_summary)
        self.response_controls = QWidget()
        controls = QHBoxLayout(self.response_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        self.responses = QComboBox()
        self.responses.setMinimumContentsLength(24)
        self.responses.currentIndexChanged.connect(self._response_changed)
        controls.addWidget(QLabel("결과 항목"))
        controls.addWidget(self.responses, 1)
        self.row_start = QSpinBox()
        self.row_start.setRange(0, 2_000_000_000)
        self.row_count = QSpinBox()
        self.row_count.setRange(1, MAX_SERIES_ROWS)
        self.row_count.setValue(MAX_SERIES_ROWS)
        controls.addWidget(QLabel("시작 행"))
        controls.addWidget(self.row_start)
        controls.addWidget(QLabel("행 수"))
        controls.addWidget(self.row_count)
        self.read_rows_button = QPushButton("읽기")
        self.read_rows_button.clicked.connect(self.read_response)
        controls.addWidget(self.read_rows_button)
        result_layout.addWidget(self.response_controls)
        self.response_label = QLabel()
        self.response_label.setWordWrap(True)
        result_layout.addWidget(self.response_label)
        self.readback_result_actions = QWidget()
        readback_result_actions = QHBoxLayout(self.readback_result_actions)
        readback_result_actions.setContentsMargins(0, 0, 0, 0)
        self.readback_post_button = QPushButton("시간별 공간 결과 열기")
        self.readback_post_button.clicked.connect(self.open_selected_post)
        readback_result_actions.addWidget(self.readback_post_button)
        self.readback_details_button = QPushButton("기술 상세 보기")
        self.readback_details_button.clicked.connect(lambda: self.tabs.setCurrentWidget(self.technical_panel))
        readback_result_actions.addWidget(self.readback_details_button)
        readback_result_actions.addStretch()
        result_layout.addWidget(self.readback_result_actions)
        self.result_views = QTabWidget()
        self.figure = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)
        self.result_views.addTab(self.canvas, "그래프")
        self.values = readonly_table(["원본 행", "축", "값", "사용 여부"])
        self.result_views.addTab(self.values, "계산값")
        self.response_details = QPlainTextEdit()
        self.response_details.setReadOnly(True)
        self.result_views.addTab(self.response_details, "응답 기술 상세")
        result_layout.addWidget(self.result_views, 1)
        result_layout.addStretch()
        self.tabs.addTab(self.result_panel, "결과")

        self.ledger_panel = QWidget()
        ledger_layout = QVBoxLayout(self.ledger_panel)
        self.ledger_label = QLabel()
        self.ledger_label.setWordWrap(True)
        ledger_layout.addWidget(self.ledger_label)
        ledger_controls = QHBoxLayout()
        ledger_controls.addWidget(QLabel("시작 기록"))
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
        technical_layout.addWidget(self.details, 1)
        self.tabs.addTab(technical_panel, "기술 상세")
        split.addWidget(self.tabs)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 2)
        split.setSizes([260, 600])
        layout.addWidget(split, 1)
        self.setCentralWidget(root)
        self._clear_result()
        self._update_actions()

    def _request(self, key, function, accepted, *, relevant=None, failed=None):
        if key in self._pending or self._closed:
            return False
        self._ticket += 1
        ticket = self._ticket
        window_epoch = self._window_epoch
        worker = _Read(function)
        self._workers[ticket] = worker
        self._pending[key] = ticket
        self._update_actions()
        def finished(value, error):
            self._workers.pop(ticket, None)
            if self._pending.get(key) == ticket:
                self._pending.pop(key, None)
            if self._closed or window_epoch != self._window_epoch:
                return
            if relevant is None or relevant():
                if error:
                    if failed is not None:
                        failed(error)
                    else:
                        self.message.setText("서비스 요청 실패: " + error)
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
            self.message.setText(f"저장된 실행 {len(self.jobs)}개" if self.jobs else
                "아직 실행한 작업이 없습니다. 도구 메뉴에서 작업할 프로그램을 열어 계산을 시작하세요.")
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
            table_row(self.job_table, row, [arguments.get("label") or operation_label(job.get("operation")), identifier,
                backend_label(arguments.get("backend")) or operation_label(job.get("operation")), state_description(job),
                timestamp_label(job.get("started_utc")), wall_time(job), resource_label(job.get("resources", {})),
                "저장됨" if job.get("result_refs") else "없음"])
            self.job_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, identifier)
            self.job_table.item(row, 0).setToolTip("실행 ID: " + identifier)
            self.job_table.item(row, 3).setToolTip(state_description(job))
            self.job_table.item(row, 4).setToolTip(timestamp_label(job.get("started_utc")))
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
        self.message.setText("선택한 작업: " + (self.jobs.get(identifier, {}).get("arguments", {}).get("label")
            or operation_label(self.jobs.get(identifier, {}).get("operation"))))
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
        self.state_label.setText(state_description(job))
        self.state_label.setToolTip("실행 ID: " + str(job.get('id', self.selected_job_id)))
        operation = job.get("operation")
        self.scope_label.setText(
            "실행 취소는 선택한 전체 계산에 적용됩니다. 개별 후보만 취소할 수는 없습니다."
            if operation in PARENT_OPERATIONS else
            "실행 취소는 선택한 작업에만 적용됩니다.")
        values = {"Job ID": job.get("id"), "Operation": operation_label(operation),
            "Backend": "보존 출력 읽기" if operation == "dynamic.reprocess" else backend_label(arguments.get("backend")),
            "Phase": {"FINISHED": "종료", "RUNNING": "실행 중", "QUEUED": "대기 중", "CALCULATING": "계산 중",
                "CLEANUP": "종료 처리 중", "AWAITING_SAFE_STOP": "안전한 중단 대기", "REQUIRES_CONFIRMATION": "상태 확인 필요"}.get(
                    job.get("phase"), "진행 단계 확인 필요" if job.get("phase") else None),
            "Created UTC": timestamp_label(job.get("created_utc")), "Started UTC": timestamp_label(job.get("started_utc")),
            "Finished UTC": timestamp_label(job.get("finished_utc")), "Wall time": wall_time(job), "Resources": resource_label(job.get("resources")),
            "Enforcement": job.get("resource_enforcement"), "Host": job.get("host"), "Attempt": job.get("attempt"),
            "Source request": job.get("request_id"), "Input hash": job.get("request_hash"), "Result references": job.get("result_refs")}
        for name, field in self.monitor_fields.items():
            field.setText(text_value(values[name]))
        error = job.get("error")
        messages = [job.get("message", "")]
        if error:
            messages.append("실행 오류: " + text_value(error.get("message", error) if isinstance(error, dict) else error))
        self.error_label.setText("\n".join(message for message in messages if message))
        inputs = {"job_id": job.get("id", self.selected_job_id), "operation": operation,
                  "arguments": arguments, "resources": job.get("resources", {}),
                  "request_id": job.get("request_id"), "request_hash": job.get("request_hash")}
        if inputs != self._input_snapshot:
            fill_tree(self.inputs, inputs)
            self._input_snapshot = deepcopy(inputs)
        self._show_details()
        self._update_actions()

    def select_readback_source(self):
        source = self.jobs.get(self.selected_job_id, {}).get("arguments", {}).get("source_job_id")
        if source:
            self.select_job(source)

    def reprocess_selected(self):
        identifier, epoch = self.selected_job_id, self._selection_epoch
        job = self.jobs.get(identifier, {})
        if not self._can_reprocess(job) or "readback:" + str(identifier) in self._pending:
            return
        request = self._readback_requests.setdefault(identifier, {
            "request_id": "dynamic-readback:" + uuid.uuid4().hex})
        self.message.setText("보존된 원 출력을 확인하고 별도 읽기 작업을 등록하고 있습니다…")
        def submit():
            if "arguments" not in request:
                request["arguments"] = self.client.dynamic_reprocess_request(identifier)
            return self.client.submit("dynamic.reprocess", request["arguments"], request_id=request["request_id"])
        def received(derived, ticket):
            derived_id = derived.get("id", derived.get("job_id"))
            if (not derived_id or derived_id == identifier or derived.get("operation") != "dynamic.reprocess"
                    or derived.get("arguments") != request.get("arguments")
                    or derived.get("request_id") != request["request_id"]):
                if (identifier, epoch) == (self.selected_job_id, self._selection_epoch):
                    self.message.setText("읽기 작업의 원 실행이 다릅니다. 새로 고침으로 등록 상태를 확인하세요.")
                return
            self._readback_requests.pop(identifier, None)
            self._merge_job(derived, ticket)
            self._draw_jobs()
            # A late registration stays in the list, but never changes a newer selection.
            if (identifier, epoch) == (self.selected_job_id, self._selection_epoch):
                self.select_job(derived_id)
                self.message.setText("별도 결과 읽기 작업을 등록했습니다. 원 실행 상태는 보존됩니다.")
        def failed(error):
            if "arguments" not in request:
                self._readback_requests.pop(identifier, None)
            if (identifier, epoch) == (self.selected_job_id, self._selection_epoch):
                self.message.setText("결과 읽기 요청을 확인하지 못했습니다: " + error +
                    ("\n‘같은 읽기 요청 확인’으로 동일 요청의 등록 여부를 확인할 수 있습니다." if "arguments" in request else ""))
        self._request("readback:" + identifier, submit, received, failed=failed)

    @staticmethod
    def _can_reprocess(job):
        return (job.get("operation") == "run"
            and job.get("arguments", {}).get("backend") == "structure.calculix.contact"
            and job.get("state") in {"SUCCEEDED", "FAILED", "CANCELLED", "INTERRUPTED", "PARTIAL_FAILURE"}
            and not job.get("cleanup_unconfirmed"))

    def cancel_selected(self):
        identifier, epoch = self.selected_job_id, self._selection_epoch
        if not identifier or self.jobs.get(identifier, {}).get("state") not in {"QUEUED", "RUNNING", "CLEANUP_PENDING"}:
            return
        self.message.setText("선택한 작업의 취소를 요청하고 있습니다. 아직 종료가 확인되지 않았습니다.")
        def received(job, ticket):
            self._merge_job(job, ticket)
            self._draw_jobs()
            if self.selected_job_id == identifier:
                self._show_job(self.jobs[identifier])
            self.message.setText(state_description(job))
        self._request("cancel:" + identifier, lambda: self.client.cancel(identifier), received,
                      relevant=lambda: (identifier, epoch) == (self.selected_job_id, self._selection_epoch))

    def open_remote_execution(self):
        from .remote_execution_dialog import show_remote
        show_remote(self)

    def open_contact_steps(self):
        identifier,epoch=self.selected_job_id,self._selection_epoch
        if not identifier: return
        def done(result,ticket):
            if not result.get('executed_setup'):
                self.message.setText('선택한 실행에는 접촉 단계 기록이 없습니다.')
                return
            from .contact_run_dialog import ContactRunDialog
            dialog=ContactRunDialog(self,identifier,result)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self._contact_run_dialog=dialog
            dialog.show()
        self._request('contact-steps:'+identifier,lambda:self.client.result(identifier,
            selection={'responses':[],'include_executed_setup':True}),
            done,relevant=lambda:(identifier,epoch)==(self.selected_job_id,self._selection_epoch))

    def open_selected_origin(self):
        selected, epoch = self.selected_job_id, self._selection_epoch
        if not selected:
            return
        job = self.jobs.get(selected, {})
        identifier = job.get("arguments", {}).get("source_job_id") if job.get("operation") == "dynamic.reprocess" else selected
        self.message.setText("선택한 실행의 입력 문서를 찾고 있습니다…")
        def received(navigation, _ticket):
            origin = navigation.get("origin_document") or {}
            if origin.get("kind") == "material" and self._on_open_origin is not None:
                # Material's existing callback owns its unapplied local edits.
                self.open_origin.emit(identifier)
                return
            from .desktop import open_origin
            def opened(receipt, _ticket):
                self.message.setText("선택한 실행의 입력 문서를 열었습니다." if receipt.get("status") in {"ACTIVATED", "SHOWN"}
                    else "선택한 실행의 입력 문서 열기를 요청했습니다.")
            self._request("open-origin:" + selected,
                          lambda: open_origin(self.client, identifier), opened,
                          relevant=lambda: (selected, epoch) == (self.selected_job_id, self._selection_epoch))
        self._request("navigation-origin:" + selected, lambda: self.client.job_navigation(identifier), received,
                      relevant=lambda: (selected, epoch) == (self.selected_job_id, self._selection_epoch))

    def open_selected_study(self):
        identifier, epoch = self.selected_job_id, self._selection_epoch
        if not identifier:
            return
        def opened():
            from .desktop import launch_tool
            navigation=self.client.job_navigation(identifier)
            origin=navigation.get('origin_document') or {}
            if not origin.get('id') or origin.get('kind') in {'pre','post','expert'}:
                raise ValueError('저장된 연구 결과를 선택하세요. CAD와 후처리 실행 근거는 원 프로젝트에서 확인할 수 있습니다.')
            reference=self.client.document_result_reference(origin['id'],identifier)
            receipt=self.client.result_followup(reference,'study',session_id=origin['session_id'],command_id='C'+uuid.uuid4().hex)
            return launch_tool(self.client,'study',document_id=receipt['document']['id'])
        return self._request('study:'+str(identifier),opened,
            lambda result,ticket:self.message.setText('선택한 저장 결과를 독립 연구 기록에 연결했습니다. 새 계산이나 추론은 요청하지 않았습니다.'),
            relevant=lambda:self.selected_job_id==identifier and self._selection_epoch==epoch)

    def open_tool(self, tool):
        from .desktop import launch_tool
        names = {"pre": "CAD 및 전처리", "post": "후처리", "data": "데이터", "material": "재료", "numerical": "수치 연구",
            "pde": "방정식", "simulation": "해석", "evaluation": "계산 절차", "study": "연구 기록", "report": "보고서", "expert": "전문가 토론"}
        def opened(receipt, _ticket):
            state = {"ACTIVATED": "열었습니다.", "SHOWN": "열었습니다.", "LAUNCH_REQUESTED": "열기를 요청했습니다.",
                "FAILED": "열지 못했습니다.", "REJECTED": "열기 요청이 거절되었습니다."}.get(receipt.get("status"), "열기 상태를 확인하세요.")
            self.message.setText(names.get(tool, "프로그램") + " " + state)
            self.message.setToolTip(json.dumps(receipt, ensure_ascii=False, indent=2))
        self._request("launch-tool:" + tool, lambda: launch_tool(self.client, tool),
                      opened)

    def open_selected_post(self):
        identifier, epoch = self.selected_job_id, self._selection_epoch
        if not identifier:
            return
        self.message.setText("선택한 실행의 저장된 공간 결과를 찾고 있습니다…")
        current = lambda: (identifier, epoch) == (self.selected_job_id, self._selection_epoch)
        def open_post(input_id):
            if self._closed or not current():
                return
            from .desktop import launch_post
            def launched(receipt, _ticket):
                self.message.setText("선택한 실행의 후처리 열기를 요청했습니다. 준비 중 오류는 별도 창에 표시됩니다.")
            self._request("open-post:" + identifier,
                          lambda: launch_post(self.client, input_id, job_id=identifier), launched, relevant=current)
        def received(navigation, _ticket):
            inputs = []
            for post in [navigation.get("post_input"), *(navigation.get("post_inputs") or [])]:
                if isinstance(post, dict) and isinstance(post.get("id"), str) and post["id"] and post["id"] not in inputs:
                    inputs.append(post["id"])
            if not inputs:
                self.message.setText("후처리로 열 수 있는 저장된 공간 결과가 없습니다. 원래 응답은 결과 보기에서 읽을 수 있습니다.")
                return
            if len(inputs) == 1:
                open_post(inputs[0])
                return
            def choices_read(records, _ticket):
                labels = [post_result_label(record) for record in records]
                if len(set(labels)) != len(labels):
                    labels = [f"{index + 1}. {label}" for index, label in enumerate(labels)]
                dialog = QInputDialog(self)
                dialog.setWindowTitle("후처리 결과 열기")
                dialog.setLabelText("열 결과를 선택하세요.")
                dialog.setComboBoxItems(labels)
                dialog.setComboBoxEditable(False)
                dialog.setOkButtonText("열기")
                dialog.setCancelButtonText("취소")
                accepted = dialog.exec()
                selected = dialog.findChild(QComboBox).currentIndex()
                dialog.deleteLater()
                if not accepted:
                    if current():
                        self.message.setText("후처리 열기를 취소했습니다.")
                    return
                if 0 <= selected < len(inputs):
                    open_post(inputs[selected])
            def read_choices():
                records = [self.client.native_input(input_id) for input_id in inputs]
                if any(record.get("id") != input_id for input_id, record in zip(inputs, records)):
                    raise ValueError("등록한 결과를 확인할 수 없습니다. 결과 목록을 다시 여세요.")
                return records
            self._request("post-choices:" + identifier, read_choices, choices_read, relevant=current)
        self._request("navigation-post:" + identifier, lambda: self.client.job_navigation(identifier), received,
                      relevant=current)

    def _update_actions(self):
        job = self.jobs.get(self.selected_job_id, {})
        state = job.get("state")
        self.refresh_action.setEnabled("catalog" not in self._pending)
        self.result_button.setEnabled(bool(job.get("result_refs")) and not any(key.startswith(f"result:{self.selected_job_id}:") for key in self._pending))
        self.origin_button.setEnabled(bool(job) and not any(key.endswith(":" + str(self.selected_job_id)) and "origin" in key for key in self._pending))
        self.post_button.setEnabled(bool(job.get("result_refs")) and not any(key.endswith(":" + str(self.selected_job_id)) and "post" in key for key in self._pending))
        self.cancel_button.setEnabled(state in {"QUEUED", "RUNNING", "CLEANUP_PENDING"} and "cancel:" + str(self.selected_job_id) not in self._pending)
        operation = job.get("operation")
        is_source = operation == "run" and job.get("arguments", {}).get("backend") == "structure.calculix.contact"
        is_readback = operation == "dynamic.reprocess"
        self.origin_button.setText("원 입력 문서 열기" if is_readback else "입력 문서 열기")
        self.readback_panel.setVisible(is_source or is_readback)
        self.reprocess_button.setVisible(is_source)
        self.source_job_button.setVisible(is_readback)
        pending_readback = "readback:" + str(self.selected_job_id) in self._pending
        self.reprocess_button.setEnabled(self._can_reprocess(job) and not pending_readback)
        uncertain = self.selected_job_id in self._readback_requests
        self.reprocess_button.setText("등록 중…" if pending_readback else "같은 읽기 요청 확인" if uncertain else "결과 다시 읽기")
        if is_readback:
            source = self.jobs.get(job.get("arguments", {}).get("source_job_id"), {})
            self.readback_label.setText("보존된 출력을 읽는 별도 작업입니다. 원 실행: " +
                (source.get("arguments", {}).get("label") or "원 구조 해석") + " / " + (state_description(source) if source else "상태 조회 필요") +
                "\n솔버 계산은 다시 실행하지 않습니다. 결과 읽기 완료는 원 계산의 성공이나 공학적 승인을 뜻하지 않습니다.")
            self.readback_label.setToolTip("원 실행 ID: " + str(job.get("arguments", {}).get("source_job_id")))
        elif is_source:
            self.readback_label.setText("원 실행의 입력과 상태를 확인한 뒤, 보존된 동해석 출력을 별도 작업으로 다시 읽을 수 있습니다."
                "\n원 실패와 취소 기록은 유지됩니다. 원 출력이 없거나 변경되었으면 서비스가 요청을 거절합니다." if self._can_reprocess(job)
                else "원 프로세스가 종료된 뒤 결과를 다시 읽을 수 있습니다. 프로세스 종료가 미확인인 작업은 먼저 종료 상태를 확인하세요.")
        self.cancel_button.setText("취소 요청됨" if state == "CANCEL_REQUESTED" else
            "종료 처리 다시 시도" if state == "CLEANUP_PENDING" else
            "전체 계산 취소" if operation in PARENT_OPERATIONS else "실행 취소")

    def _clear_result(self):
        self.result_metadata = None
        self._response_epoch += 1
        self.responses.blockSignals(True)
        self.responses.clear()
        self.responses.blockSignals(False)
        self.values.setRowCount(0)
        self.response_details.clear()
        self.response_label.clear()
        self.response_controls.show()
        self.result_views.show()
        self.readback_result_actions.hide()
        self.read_rows_button.setEnabled(False)
        self.row_start.setEnabled(False)
        self.row_count.setEnabled(False)
        self.result_summary.setText("결과 보기를 누르면 선택한 실행의 저장 결과를 읽습니다.")
        self._ledger, self._ledger_kind = [], None
        index = self.tabs.indexOf(self.ledger_panel)
        if index >= 0:
            self.tabs.removeTab(index)
        self._blank_plot("위 목록에서 작업을 선택한 뒤 ‘결과 보기’를 누르세요.")

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
        self.result_summary.setText("선택한 실행의 저장 결과를 읽고 있습니다…")
        def received(result, _ticket):
            self.result_metadata = result
            state = result.get("execution_status", "UNKNOWN")
            job = self.jobs.get(identifier, {})
            label = job.get('arguments', {}).get('label') or operation_label(job.get('operation'))
            details = [label + ' 결과: ' + state_description({'state': state})]
            if job.get("operation") == "dynamic.reprocess":
                source_state = result.get("source_execution_status", result.get("source_job_state", "UNKNOWN"))
                details.append("원 계산: " + state_description({"state": source_state}) +
                    " — 새 솔버 계산 없이 보존 출력을 읽은 결과입니다. 공학적 승인은 확인되지 않았습니다.")
            self.result_summary.setToolTip('실행 ID: ' + identifier)
            for key in ("termination_reason", "failure_reason"):
                if result.get(key):
                    details.append(("종료 사유" if key == "termination_reason" else "실패 사유") + ": " + text_value(result[key]))
            if state in {"FAILED", "PARTIAL_FAILURE", "REJECTED", "CANCELLED"}:
                details.append("일부 결과만 남아 있을 수 있습니다. 전체 계산이 완료된 결과가 아닙니다.")
            self.result_summary.setText("\n".join(details))
            self.responses.blockSignals(True)
            self.responses.clear()
            for name, response in result.get("responses", {}).items():
                self.responses.addItem(f"{name} [{response.get('unit', '단위 미기록')}]", name)
            self.responses.blockSignals(False)
            self._set_ledger(result)
            self._show_details()
            if self.responses.count():
                self._response_changed()
            elif job.get("operation") == "dynamic.reprocess":
                self.response_controls.hide()
                self.result_views.hide()
                self.readback_result_actions.show()
                post = bool(result.get("post_input"))
                self.readback_post_button.setEnabled(post)
                reference = (result.get("retained_attempt") or {}).get("dynamic_result") or {}
                count = reference.get("frame_count")
                lines = [f"보존된 시간 출력: {count}개" if type(count) is int and count >= 0 else "보존된 시간 출력 수는 기록되지 않았습니다."]
                lines.append("시간별 공간 결과를 열어 출력 단계와 물리시간을 확인하세요." if post else
                    "이 읽기 작업에 등록된 공간 결과가 없습니다. 원 실행의 입력과 오류를 확인하세요.")
                diagnostics = result.get("diagnostics") or {}
                readback = diagnostics.get("readback") or {}
                for name in ("recovery", "dynamic_readback"):
                    if isinstance(readback.get(name), str):
                        lines.append("결과 읽기 오류: " + readback[name])
                registration = diagnostics.get("post_registration") or {}
                if registration.get("status") == "FAILED":
                    lines.append("후처리 등록 실패: " + str(registration.get("message") or "원 기록을 확인하세요."))
                lines.append("원 출력 참조와 상세 진단은 ‘기술 상세 보기’에서 확인할 수 있습니다.")
                self.response_label.setText("\n\n".join(lines))
            else:
                self.response_label.setText("표시할 단일 값이나 곡선이 없습니다. 저장된 파일 참조와 원 기록은 기술 상세에서 확인하세요.")
                self.response_details.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
                self.result_views.setCurrentWidget(self.canvas)
                self._blank_plot("이 결과에는 표시할 단일 값이나 곡선이 없습니다.")
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
        self._blank_plot("선택한 원 결과를 읽고 있습니다…")
        self.response_details.setPlainText(json.dumps(response, ensure_ascii=False, indent=2))
        kind = response.get("kind")
        self.read_rows_button.setEnabled(kind == "series")
        self.row_start.setEnabled(kind == "series")
        self.row_count.setEnabled(kind == "series")
        if kind not in {"scalar", "series"}:
            self.response_label.setText(f"{name}: 단일 값이나 1차원 곡선으로 표시할 수 없는 결과입니다. 공간 결과는 후처리에서 열고 원 참조는 응답 기술 상세에서 확인하세요.")
            self._blank_plot("공간 분포 결과는 후처리에서 확인하세요.")
            self.result_views.setCurrentWidget(self.canvas)
            return
        start, count = self.row_start.value(), self.row_count.value()
        selection = {"responses": [name]}
        if kind == "series":
            selection["rows"] = [start, start + count]
        self.response_label.setText(f"선택한 실행의 {name} 결과를 읽고 있습니다…")
        def received(result, _ticket):
            selected = result.get("responses", {}).get(name)
            if selected is None:
                self.response_label.setText("원 결과에 선택한 항목이 없습니다. 다른 항목을 선택하거나 기술 상세에서 원 기록을 확인하세요.")
                self._blank_plot("선택한 결과 항목을 읽을 수 없습니다.")
                return
            self._draw_response(name, selected, start)
        self._request(f"response:{identifier}:{epoch}:{response_epoch}", lambda: self.client.result(identifier, selection=selection), received,
            relevant=lambda: (identifier, epoch, response_epoch) == (self.selected_job_id, self._selection_epoch, self._response_epoch))

    def _draw_response(self, name, response, start):
        self.response_details.setPlainText(json.dumps(response, ensure_ascii=False, indent=2))
        captions = {'component': '성분', 'location': '위치', 'frame': '좌표계', 'measure': '물리량 정의', 'valid': '유효성'}
        meanings = {'material_point': '재료점', 'material_cartesian': '재료 직교좌표',
                    'laboratory': '실험실 좌표', 'infinitesimal_Cauchy': '미소변형 Cauchy 응력',
                    'true': '유효', 'false': '유효하지 않음'}
        labels = [captions[key] + ': ' + meanings.get(text_value(response[key]), text_value(response[key]))
                  for key in captions if key in response]
        unit = response.get("unit", "단위 미기록")
        if response.get("kind") == "scalar":
            self.values.setRowCount(1)
            table_row(self.values, 0, ["단일 값", "—", f"{text_value(response.get('value'))} {unit}", "—"])
            self.response_label.setText(f"{name} = {text_value(response.get('value'))} {unit}" + ("\n" + ", ".join(labels) if labels else ""))
            self._blank_plot("단일 값은 계산값 표에서 확인하세요.")
            self.result_views.setCurrentWidget(self.values)
            return
        values, axes = response.get("value"), response.get("axes", [])
        if not isinstance(values, list) or len(axes) != 1 or not isinstance(axes[0].get("values"), list) or len(values) != len(axes[0]["values"]):
            self.response_label.setText("축과 값이 대응하는 1차원 계열이 아니므로 곡선을 그리지 않았습니다. 원 기록은 응답 기술 상세에 보존됩니다.")
            self._blank_plot("축과 값의 배열 크기를 확인하세요.")
            self.result_views.setCurrentWidget(self.canvas)
            return
        axis = axes[0]
        mask = response.get("mask")
        self.values.setRowCount(len(values))
        for row, (coordinate, value) in enumerate(zip(axis["values"], values)):
            included = (("사용" if mask[row] else "제외") if type(mask[row]) is bool else "유효성 값 확인 필요") if isinstance(mask, list) and row < len(mask) else "유효성 미기록"
            table_row(self.values, row, [start + row, f"{text_value(coordinate)} {axis.get('unit', '단위 미기록')}", f"{text_value(value)} {unit}", included])
        self.response_label.setText(f"원본 행 {start} 이상 {start + len(values)} 미만 ({len(values)}행)" + ("\n" + ", ".join(labels) if labels else ""))
        try:
            if mask is not None and (not isinstance(mask, list) or len(mask) != len(values) or any(type(value) is not bool for value in mask)):
                raise ValueError("Unsupported mask")
            x = [float(value) for value in axis["values"]]
            y = [math.nan if mask is not None and not mask[row] else float(value) for row, value in enumerate(values)]
            if not all(math.isfinite(value) for value in x) or response.get("valid") is False:
                raise ValueError("Invalid retained response")
            if any(not math.isfinite(value) for row, value in enumerate(y) if mask is None or mask[row]):
                raise ValueError("Invalid retained response")
        except (TypeError, ValueError, OverflowError):
            self.response_label.setText(self.response_label.text() + "\n값 또는 유효성 표시를 확인하세요. 곡선을 그리지 않았습니다.")
            self._blank_plot("원값 표에서 잘못된 값과 유효성을 확인하세요.")
            self.result_views.setCurrentWidget(self.values)
            return
        if mask is not None and not any(mask):
            self.response_label.setText(self.response_label.text() + "\n이 구간에 표시할 유효 표본이 없습니다. 원값은 표에 남아 있습니다.")
            self._blank_plot("유효 표본 없음")
            self.result_views.setCurrentWidget(self.values)
            return
        if mask is not None and not all(mask):
            self.response_label.setText(self.response_label.text() + f"\n제외 표본 {mask.count(False)}개는 빈 구간으로 표시합니다. 원값과 유효성은 표에서 확인하세요.")
        self.axes.clear()
        self.axes.set_axis_on()
        self.axes.plot(x, y, marker="o", markersize=3)
        axis_name = {'time': '시간', 'strain': '변형률', 'displacement': '변위'}.get(axis.get('name'), axis.get('name', '축 이름 미기록'))
        self.axes.set_xlabel(f"{axis_name} [{axis.get('unit', '단위 미기록')}]")
        self.axes.set_ylabel(f"{name} [{unit}]")
        self.axes.set_title("")
        self.axes.grid(True, alpha=.25)
        self.canvas.draw_idle()
        self.result_views.setCurrentWidget(self.canvas)

    def _set_ledger(self, result):
        self._ledger_kind = next((key for key in ("candidates", "history") if isinstance(result.get(key), list)), None)
        if self._ledger_kind is None:
            return
        self._ledger = result[self._ledger_kind]
        if self.tabs.indexOf(self.ledger_panel) < 0:
            self.tabs.insertTab(self.tabs.indexOf(self.technical_panel), self.ledger_panel, "계산 후보" if self._ledger_kind == "candidates" else "계산 이력")
        self.ledger_start.blockSignals(True)
        self.ledger_start.setRange(0, max(0, len(self._ledger) - 1))
        self.ledger_start.setValue(0)
        self.ledger_start.blockSignals(False)
        self._draw_ledger()

    def _draw_ledger(self, *_):
        start = self.ledger_start.value()
        rows = self._ledger[start:start + MAX_LEDGER_ROWS]
        candidate = self._ledger_kind == "candidates"
        keys = [key for key in dict.fromkeys(key for row in rows if isinstance(row, dict) for key in row)
                if key not in {"job_id", "request_id", "request_hash", "candidate_id"}][:12]
        captions = {"iteration": "반복", "generation": "세대", "objective": "목적함수", "best_objective": "최선 목적함수",
            "execution_status": "실행 상태", "prediction_status": "예측 여부", "values": "변수 값", "failure_reason": "실패 사유",
            "penalty_applied": "벌점", "time_s": "시간 [s]", "elapsed_s": "경과 시간 [s]", "evaluations": "평가 횟수"}
        headers = ["후보", "실행 상태 / 예측", "변수", "유효 목적함수", "벌점", "실패 / 벌점 / 예측 목적함수", "실패 사유", "단일 값 결과"] if candidate else [captions.get(key, key) for key in keys]
        self.ledger_table.setColumnCount(len(headers))
        self.ledger_table.setHorizontalHeaderLabels(headers)
        self.ledger_table.setRowCount(len(rows))
        self.ledger_label.setText(f"{'후보' if candidate else '계산 이력'} {len(self._ledger)}개 중 {start + 1 if rows else 0}–{start + len(rows)}번째 기록. " +
            ("실패·벌점·예측 평가는 유효 목적함수에서 제외합니다. 취소는 전체 계산에 적용됩니다." if candidate else "행을 선택하면 저장된 값을 확인할 수 있습니다. 전체 원문은 기술 상세에 보존됩니다."))
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            if candidate:
                eligible = actual_candidate(row) and "penalty_applied" not in row
                scalar = {name: f"{text_value(value.get('value'))} {value.get('unit', '단위 미기록')}" for name, value in row.get("responses", {}).items() if value.get("kind") == "scalar"}
                variables = row.get("values")
                variables = ", ".join(f"{name} = {text_value(value)}" for name, value in variables.items()) if isinstance(variables, dict) else text_value(variables)
                values = [f"후보 {start + index + 1}", candidate_state(row), short_value(variables),
                    row.get("objective") if eligible else "—", row.get("penalty_applied", "—"),
                    row.get("objective") if not eligible else "—", row.get("failure_reason", "—"), short_value(", ".join(f"{name} = {value}" for name, value in scalar.items()) or "없음")]
            else:
                values = [(state_description({"state": row.get(key)}) if row.get(key) is not None else "기록 없음") if key == "execution_status" else
                    "예측값" if key == "prediction_status" and row.get(key) == "PREDICTED" else short_value(row.get(key)) for key in keys]
            table_row(self.ledger_table, index, values)
            if candidate:
                self.ledger_table.item(index, 0).setToolTip("원 후보 식별값: " + str(row.get("candidate_id", "기록 없음")))
        self.ledger_details.clear()

    def _ledger_selected(self):
        rows = self.ledger_table.selectionModel().selectedRows()
        if rows:
            index = self.ledger_start.value() + rows[0].row()
            if index < len(self._ledger):
                current = rows[0].row()
                self.ledger_details.setPlainText("\n".join(self.ledger_table.horizontalHeaderItem(column).text() + ": " + self.ledger_table.item(current, column).text()
                    for column in range(self.ledger_table.columnCount()) if self.ledger_table.item(current, column)) +
                    "\n\n전체 원문과 식별값은 기술 상세에서 확인하세요.")

    def _show_details(self):
        self.details.setPlainText(json.dumps({"job": self.jobs.get(self.selected_job_id), "result_metadata": self.result_metadata}, ensure_ascii=False, indent=2))

    def closeEvent(self, event):
        self._closed = True
        self._window_epoch += 1
        self._pending.clear()
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
