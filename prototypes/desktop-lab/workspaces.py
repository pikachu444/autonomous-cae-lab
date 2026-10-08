"""Native, editable engineering workspaces for the desktop planning prototype.

The numerical runs and initial values in this module are explicitly demonstrations.
Imported CSV and OBJ values remain distinct from demonstration data in the document.
"""

from __future__ import annotations

import copy
import csv
import json
import math
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QColor, QBrush, QPen, QPainter, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QTableWidget, QTableWidgetItem, QLabel, QPushButton,
    QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit, QFileDialog, QMessageBox,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QFormLayout, QGroupBox,
    QHeaderView, QAbstractItemView, QPlainTextEdit, QCheckBox, QInputDialog,
)
import pyqtgraph as pg
from table_import import map_table_file


def _header(table, labels):
    table.setColumnCount(len(labels))
    table.setHorizontalHeaderLabels(labels)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)


def _table_item(value, editable=False):
    item = QTableWidgetItem(str(value))
    if not editable:
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _button(label, callback):
    button = QPushButton(label)
    button.clicked.connect(callback)
    return button


def _chart(lines, x_title="X", y_title="Y"):
    view = pg.PlotWidget(background="#ffffff")
    view.showGrid(x=True, y=True, alpha=.18)
    view.setLabel("bottom", x_title); view.setLabel("left", y_title)
    view.getPlotItem().setMenuEnabled(False)
    palette = ["#1762a7", "#d47435", "#22927f", "#895bb6"]
    if len(lines) > 1: view.addLegend()
    for index, (name, points) in enumerate(lines):
        view.plot([float(p[0]) for p in points], [float(p[1]) for p in points],
                  pen=pg.mkPen(palette[index % len(palette)], width=2), name=name)
    return view


def _scatter_chart(points, x_title, y_title):
    view = pg.PlotWidget(background="#ffffff")
    view.showGrid(x=True, y=True, alpha=.18)
    view.setLabel("bottom", x_title); view.setLabel("left", y_title)
    view.getPlotItem().setMenuEnabled(False)
    series = pg.ScatterPlotItem(x=[float(p[0]) for p in points], y=[float(p[1]) for p in points],
                                size=10, pen=pg.mkPen("#ffffff", width=1), brush=pg.mkBrush("#1762a7"))
    view.addItem(series)
    return view, series


class Workspace(QWidget):
    kind = ""
    defaults = {}

    def __init__(self, document, changed, open_tool):
        super().__init__()
        self._changed = changed
        self._open_tool = open_tool
        self._doc = {}
        self._loading = False
        self.set_document(document or {})

    def set_document(self, document):
        self._doc = copy.deepcopy(document or {})
        self._doc["kind"] = self.kind
        self._dirty = False
        self._doc.setdefault("data", {})
        for key, value in self.defaults.items():
            self._doc["data"].setdefault(key, copy.deepcopy(value))
        if hasattr(self, "refresh"):
            self.refresh()

    def document(self):
        return copy.deepcopy(self._doc)

    def persist_setting(self,key,value):
        if self._loading or self.data.get(key)==value:return
        before=self.document();self.data[key]=value;self._dirty=True;self._changed('설정 편집',before)

    @property
    def data(self):
        return self._doc["data"]

    def mutate(self, reason, edit):
        if self._loading:
            return
        before = self.document()
        edit()
        self._dirty = True
        self.refresh()
        self._changed(reason, before)

    def tool_actions(self):
        return []

    def _message(self, title, message):
        QMessageBox.information(self, title, message)


class RunnerWorkspace(Workspace):
    kind = "runner"
    defaults = {"case_name": "검토 케이스 A", "source_revision": None, "backend": "시연 솔버", "iterations": 24, "runs": [], "selected_run": None}
    statuses = {"queued": "대기", "running": "실행 중", "succeeded": "완료", "cancelled": "중단", "failed": "실패"}

    def __init__(self, document, changed, open_tool):
        super().__init__(document, changed, open_tool)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout(); top.addWidget(QLabel("케이스"))
        self.case_name = QLineEdit(); top.addWidget(self.case_name, 2)
        self.case_name.textEdited.connect(lambda text:self.persist_setting('case_name',text))
        top.addWidget(QLabel("실행기")); self.backend = QComboBox(); self.backend.addItems(["시연 솔버"]); top.addWidget(self.backend, 2)
        top.addWidget(QLabel("반복 횟수")); self.iterations = QSpinBox(); self.iterations.setRange(5, 200); top.addWidget(self.iterations)
        self.iterations.valueChanged.connect(lambda value:self.persist_setting('iterations',value))
        top.addWidget(_button("입력 검증", self.validate)); top.addWidget(_button("실행 제출", self.submit))
        root.addLayout(top)
        splitter = QSplitter(Qt.Orientation.Vertical)
        upper = QSplitter()
        self.tree = QTreeWidget(); self.tree.setHeaderLabels(["케이스 / 실행"])
        self.tree.itemSelectionChanged.connect(self._selected)
        upper.addWidget(self.tree)
        central = QWidget(); c = QVBoxLayout(central)
        self.queue = QTableWidget(); _header(self.queue, ["실행 ID", "상태", "진행", "최종 잔차"])
        self.queue.itemSelectionChanged.connect(self._queue_selected)
        c.addWidget(self.queue, 1)
        self.plot = QWidget(); c.addWidget(self.plot, 2)
        upper.addWidget(central)
        side = QWidget(); s = QVBoxLayout(side)
        s.addWidget(QLabel("실행 제어"))
        s.addWidget(_button("선택 실행 중단", self.cancel))
        s.addWidget(_button("선택 실행 재시도", self.retry))
        s.addWidget(_button("후처리에서 결과 열기", self.open_result))
        self.details = QLabel(); self.details.setWordWrap(True); s.addWidget(self.details)
        s.addStretch(); upper.addWidget(side); upper.setSizes([200, 820, 240])
        splitter.addWidget(upper)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); splitter.addWidget(self.log)
        splitter.setSizes([570, 150]); root.addWidget(splitter)
        self.timer = QTimer(self); self.timer.setInterval(180); self.timer.timeout.connect(self._tick)
        self.refresh()
        if any(r["status"] in ("queued", "running") for r in self.data["runs"]): self.timer.start()

    def tool_actions(self):
        return [("케이스 검증", "validate", self.validate, "F7"), ("실행 제출", "run", self.submit, "F5"),
                ("실행 중단", "stop", self.cancel, ""), ("결과 열기", "post", self.open_result, "")]

    def tool_menus(self):
        return {"케이스": ["케이스 검증"], "실행": ["실행 제출", "실행 중단"], "결과": ["결과 열기"]}

    def refresh(self):
        if not hasattr(self, "tree"): return
        self._loading = True; d = self.data
        self.case_name.setText(d["case_name"]); self.iterations.setValue(d["iterations"])
        self.tree.clear(); case = QTreeWidgetItem([d["case_name"]]); self.tree.addTopLevelItem(case)
        self.queue.setRowCount(len(d["runs"]))
        for i, run in enumerate(d["runs"]):
            item = QTreeWidgetItem([f"{run['id']} · {self.statuses.get(run['status'], run['status'])}"])
            item.setData(0, Qt.ItemDataRole.UserRole, i); case.addChild(item)
            values = [run["id"], self.statuses.get(run["status"], run["status"]), f"{run['progress']}%", f"{run['residuals'][-1]:.3g}" if run["residuals"] else "—"]
            for col, val in enumerate(values): self.queue.setItem(i, col, _table_item(val))
        case.setExpanded(True)
        index = d.get("selected_run")
        selected = d["runs"][index] if isinstance(index, int) and index < len(d["runs"]) else None
        parent = self.plot.parentWidget().layout()
        parent.replaceWidget(self.plot, new := _chart([(selected["id"], list(enumerate(selected["residuals"], 1)))] if selected else [], "반복 횟수", "잔차"))
        self.plot.deleteLater(); self.plot = new
        self.details.setText((f"{selected['id']}\n{self.statuses.get(selected['status'], selected['status'])}\n입력 버전: {selected.get('source_revision') or '현재 스냅샷'}\n시연 실행" if selected else "실행을 선택하면 상세 상태가 보입니다."))
        self.log.setPlainText("\n".join(selected["log"]) if selected else "선택한 실행이 없습니다.")
        if selected: self.queue.selectRow(index)
        self._loading = False

    def _selected(self):
        if self._loading: return
        item = self.tree.currentItem(); index = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if isinstance(index, int) and self.data.get("selected_run") != index:
            before = self.document(); self.data["selected_run"] = index; self.refresh(); self._changed("실행 선택", before)

    def _queue_selected(self):
        if self._loading: return
        index = self.queue.currentRow()
        if index >= 0 and self.data.get("selected_run") != index:
            before = self.document(); self.data["selected_run"] = index; self.refresh(); self._changed("실행 선택", before)

    def validate(self):
        return self._validate(show=True)

    def _validate(self, show):
        errors = []
        if not self.case_name.text().strip(): errors.append("케이스 이름이 필요합니다")
        if self.iterations.value() < 5: errors.append("반복 횟수는 5 이상이어야 합니다")
        if show or errors: self._message("케이스 검증", "시연 실행을 제출할 수 있습니다." if not errors else "; ".join(errors))
        return not errors

    def submit(self):
        if not self._validate(show=False): return
        def edit():
            d = self.data; d["case_name"] = self.case_name.text().strip(); d["iterations"] = self.iterations.value()
            index = len(d["runs"]) + 1
            d["runs"].append({"id": f"R{index:03d}", "status": "queued", "progress": 0, "residuals": [], "log": ["대기 · 시연 실행기"], "source_revision": d.get("source_revision")})
            d["selected_run"] = len(d["runs"]) - 1
        self.mutate("시연 실행 제출", edit); self.timer.start()

    def _tick(self):
        active = [r for r in self.data["runs"] if r["status"] in ("queued", "running")]
        if not active: self.timer.stop(); return
        def edit():
            for run in active:
                if run["status"] == "queued": run["status"] = "running"; run["log"].append("실행 시작")
                iteration = len(run["residuals"]) + 1
                residual = math.exp(-iteration / 4.8) * (1 + .07 * math.sin(iteration))
                run["residuals"].append(residual)
                run["progress"] = min(100, round(100 * iteration / self.data["iterations"]))
                if iteration % 4 == 0: run["log"].append(f"반복 {iteration}: 잔차 {residual:.5f}")
                if iteration >= self.data["iterations"]:
                    run["status"] = "succeeded"; run["log"].append("완료 · 시연 결과")
        edit(); self._dirty = True; self.refresh(); self._changed("시연 실행 진행", None)

    def cancel(self):
        index = self.data.get("selected_run")
        if index is None: return
        run = self.data["runs"][index]
        if run["status"] not in ("queued", "running"): return
        self.mutate("실행 중단", lambda: (run.__setitem__("status", "cancelled"), run["log"].append("사용자 중단")))

    def retry(self):
        index = self.data.get("selected_run")
        if index is None or self.data["runs"][index]["status"] not in ("cancelled", "failed"): return
        self.submit()

    def open_result(self):
        index = self.data.get("selected_run")
        if index is None: return
        run = self.data["runs"][index]
        if run["status"] != "succeeded":
            self._message("결과 없음", "완료된 실행을 선택하세요."); return
        points = [[i + 1, value] for i, value in enumerate(run["residuals"])]
        self._open_tool("post", {"kind": "post", "name": f"{run['id']} 결과", "data": {"source": run["id"], "source_type": "demo_run", "points": points, "field": [], "component": "잔차", "unit": "—", "x_name": "반복", "x_unit": "회", "frame": 0, "selection": None, "compare": None}})


class PostWorkspace(Workspace):
    kind = "post"
    defaults = {"source": "검토용 온도장", "source_type": "demo", "points": [[x, round(math.sin(x / 2) + .2 * x, 4)] for x in range(20)],
                "field": [[round(22 + 5 * math.sin(i / 2) + 3 * math.cos(j / 2), 2) for i in range(10)] for j in range(7)],
                "component": "온도", "unit": "°C", "x_name": "시간", "x_unit": "s", "frame": 0, "frame_count": 5, "selection": None, "compare": None, "legend": "자동"}
    demo_units = {"온도": "°C", "변위": "mm", "응력": "MPa"}

    def __init__(self, document, changed, open_tool):
        super().__init__(document, changed, open_tool)
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(); self.tree = QTreeWidget(); self.tree.setHeaderLabels(["결과 객체"])
        self.tree.itemSelectionChanged.connect(self._tree_selected); splitter.addWidget(self.tree)
        center = QWidget(); c = QVBoxLayout(center)
        bar = QHBoxLayout(); bar.addWidget(QLabel("성분"))
        self.component = QComboBox(); bar.addWidget(self.component)
        bar.addWidget(QLabel("프레임")); self.frame = QSpinBox(); self.frame.setRange(0, 99); bar.addWidget(self.frame)
        bar.addWidget(QLabel("범례")); self.legend = QComboBox(); self.legend.addItems(["자동", "고정 0–50", "중앙 기준"]); bar.addWidget(self.legend)
        self.apply_view_button = _button("표시 적용", self._apply_view); bar.addWidget(self.apply_view_button); c.addLayout(bar)
        self.tabs = QTabWidget()
        self.scene = QGraphicsScene(); self.field_view = QGraphicsView(self.scene); self.field_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.field_view.viewport().installEventFilter(self)
        self.tabs.addTab(self.field_view, "필드·셀")
        self.plot = QWidget(); self.tabs.addTab(self.plot, "응답 곡선")
        c.addWidget(self.tabs); splitter.addWidget(center)
        side = QWidget(); s = QVBoxLayout(side); s.addWidget(QLabel("선택 값·출처"))
        self.info = QLabel(); self.info.setWordWrap(True); s.addWidget(self.info)
        s.addWidget(_button("응답 CSV 가져오기", self.import_csv))
        s.addWidget(_button("두 번째 CSV 비교", self.import_compare))
        s.addWidget(_button("곡선 CSV 내보내기", self.export_csv))
        s.addStretch(); self.provenance = QLabel(); self.provenance.setWordWrap(True); s.addWidget(self.provenance)
        splitter.addWidget(side); splitter.setSizes([205, 830, 250]); root.addWidget(splitter)
        self.refresh()

    def tool_actions(self):
        return [("응답 가져오기", "import", self.import_csv, "Ctrl+I"),
                ("결과 비교", "compare", self.import_compare, ""),
                ("곡선 내보내기", "export", self.export_csv, "Ctrl+E")]

    def tool_menus(self):
        return {"결과": ["응답 가져오기", "곡선 내보내기"], "분석": ["결과 비교"]}

    def refresh(self):
        if not hasattr(self, "tree"): return
        self._loading = True; d = self.data
        has_field = bool(d["field"])
        self.tree.clear(); result = QTreeWidgetItem([f"결과 · {d['source']}"]); self.tree.addTopLevelItem(result)
        if has_field:
            field = QTreeWidgetItem([f"필드 · {d['component']}"]); result.addChild(field)
        curve = QTreeWidgetItem([f"응답 · {len(d['points'])}개 표본"]); result.addChild(curve)
        if d.get("compare"): result.addChild(QTreeWidgetItem([f"비교 · {d['compare']['source']}"]))
        result.setExpanded(True)
        self.component.clear()
        self.component.addItems(list(self.demo_units) if d["source_type"] == "demo" and has_field else [d["component"]])
        self.component.setCurrentText(d["component"])
        self.frame.setRange(0, max(0, d.get("frame_count", 1) - 1 if has_field else 0))
        self.frame.setValue(d["frame"]); self.legend.setCurrentText(d["legend"])
        for control in (self.component, self.frame, self.legend, self.apply_view_button):
            control.setEnabled(has_field)
        self._draw_field()
        lines = [(d["source"], d["points"])]
        if d.get("compare"): lines.append((d["compare"]["source"], d["compare"]["points"]))
        active_tab=self.tabs.currentIndex()
        self.tabs.removeTab(1)
        self.plot.deleteLater(); self.plot = _chart(lines, f"{d['x_name']} [{d['x_unit']}]", d["component"] + " [" + d["unit"] + "]")
        self.tabs.addTab(self.plot, "응답 곡선")
        self.tabs.setTabText(0, "필드·셀" if has_field else "필드 없음")
        self.tabs.setTabEnabled(0, has_field)
        self.tabs.setCurrentIndex(1 if not has_field else active_tab)
        selected = d.get("selection")
        field = self._field_values()
        if has_field:
            self.info.setText(f"셀 {selected[0]},{selected[1]} · {field[selected[1]][selected[0]]:g} {d['unit']}" if selected and field else "필드 셀을 선택하면 값이 표시됩니다.")
        elif d["points"]:
            xs = [point[0] for point in d["points"]]; ys = [point[1] for point in d["points"]]
            self.info.setText(f"응답 곡선 · {len(xs)}개 표본\n{d['x_name']}: {min(xs):.5g}–{max(xs):.5g} {d['x_unit']}\n{d['component']}: {min(ys):.5g}–{max(ys):.5g} {d['unit']}")
        else:
            self.info.setText("응답 곡선 표본이 없습니다.")
        source_type = {"demo": "시연 필드", "demo_run": "시연 실행 결과", "csv": "가져온 CSV"}.get(d["source_type"], d["source_type"])
        self.provenance.setText(f"출처: {d['source']}\n형식: {source_type}")
        self._loading = False

    def _field_values(self):
        d = self.data; field = d["field"]
        if not field or d["source_type"] != "demo": return field
        frame = d["frame"]
        if d["component"] == "변위": return [[round((v - 20) * .015 * (frame + 1), 4) for v in row] for row in field]
        if d["component"] == "응력": return [[round(v * 4 * (1 + .1 * frame), 3) for v in row] for row in field]
        return [[round(v + 2 * frame, 3) for v in row] for row in field]

    def _draw_field(self):
        scene = self.scene; scene.clear(); field = self._field_values()
        if not field:
            return
        values = [v for row in field for v in row]; low, high = min(values), max(values)
        if self.data["legend"] == "고정 0–50": low, high = 0, 50
        elif self.data["legend"] == "중앙 기준":
            extent = max(abs(low), abs(high)); low, high = -extent, extent
        for y, row in enumerate(field):
            for x, value in enumerate(row):
                t = max(0.0, min(1.0, (value - low) / (high - low or 1)))
                color = QColor.fromHsvF(.59 * (1 - t), .72, .94)
                selected = self.data.get("selection") == [x, y]
                rect = scene.addRect(x * 44, y * 44, 43, 43,
                                     QPen(QColor("#173f6d") if selected else QColor("#ffffff"), 3 if selected else 1), QBrush(color))
                rect.setData(0, (x, y)); rect.setToolTip(f"셀 {x},{y}: {value:g} {self.data['unit']}")
        scene.setSceneRect(scene.itemsBoundingRect())

    def eventFilter(self, obj, event):
        if hasattr(self, "field_view") and obj is self.field_view.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            item = self.field_view.itemAt(event.position().toPoint())
            if item and item.data(0) is not None:
                xy = item.data(0)
                self.mutate("결과 셀 선택", lambda: self.data.__setitem__("selection", list(xy)))
                return True
        return super().eventFilter(obj, event)

    def _tree_selected(self):
        if self._loading: return
        item = self.tree.currentItem()
        if item and item.text(0).startswith("응답"): self.tabs.setCurrentIndex(1)
        elif item and item.text(0).startswith("필드"): self.tabs.setCurrentIndex(0)

    def _apply_view(self):
        component = self.component.currentText()
        unit = self.demo_units.get(component, self.data["unit"]) if self.data["source_type"] == "demo" else self.data["unit"]
        self.mutate("결과 표시 적용", lambda: self.data.update(component=component, unit=unit, frame=self.frame.value(), legend=self.legend.currentText()))

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "응답 CSV 가져오기", "", "CSV 파일 (*.csv *.txt);;모든 파일 (*)")
        if not path: return
        try: mapped = map_table_file(self, path)
        except (OSError, ValueError) as exc: self._message("가져오기 실패", str(exc)); return
        if mapped is None: return
        self.mutate("결과 CSV 가져오기", lambda: self.data.update(source=Path(path).name, source_path=path, source_type="csv", points=mapped.points,
                    x_name=mapped.x_name, x_unit=mapped.x_unit, component=mapped.y_name, unit=mapped.y_unit,
                    csv_mapping={"delimiter": mapped.delimiter, "header": mapped.has_header, "x_column": mapped.x_column, "y_column": mapped.y_column},
                    field=[], frame=0, frame_count=1, compare=None))

    def import_compare(self):
        path, _ = QFileDialog.getOpenFileName(self, "비교할 응답 CSV", "", "CSV 파일 (*.csv *.txt);;모든 파일 (*)")
        if not path: return
        try: mapped = map_table_file(self, path)
        except (OSError, ValueError) as exc: self._message("비교 실패", str(exc)); return
        if mapped is None: return
        units = [mapped.x_unit, mapped.y_unit]
        if any(a != "—" and b != "—" and a != b for a, b in zip((self.data["x_unit"], self.data["unit"]), units)):
            self._message("단위 불일치", f"현재 축 [{self.data['x_unit']}, {self.data['unit']}]과 비교 파일 [{units[0]}, {units[1]}]의 단위가 다릅니다."); return
        self.mutate("결과 CSV 비교", lambda: self.data.__setitem__("compare", {"source": Path(path).name, "source_path": path, "points": mapped.points,
                    "x_name": mapped.x_name, "x_unit": mapped.x_unit, "component": mapped.y_name, "unit": mapped.y_unit,
                    "csv_mapping": {"delimiter": mapped.delimiter, "header": mapped.has_header, "x_column": mapped.x_column, "y_column": mapped.y_column}}))
        self.tabs.setCurrentIndex(1)

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "곡선 CSV 내보내기", f"{self.data['source']}.csv", "CSV 파일 (*.csv)")
        if not path: return
        try:
            with open(path, "w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file); writer.writerow([f"{self.data['x_name']} [{self.data['x_unit']}]", f"{self.data['component']} [{self.data['unit']}]"]); writer.writerows(self.data["points"])
        except OSError as exc: self._message("내보내기 실패", str(exc)); return
        self._message("내보내기 완료", path)


class OptWorkspace(Workspace):
    kind = "opt"
    defaults = {"study_name": "브래킷 설계 연구", "budget": 12, "variables": [{"name": "두께", "low": 1.0, "high": 5.0, "unit": "mm"}, {"name": "폭", "low": 8.0, "high": 24.0, "unit": "mm"}],
                "objectives": [{"name": "질량", "sense": "min", "unit": "kg"}, {"name": "처짐", "sense": "min", "unit": "mm"}],
                "constraints": [{"name": "응력", "limit": 250, "unit": "MPa"}], "candidates": [], "selected": None, "source_type": "demo",
                "workflow": {"case_ref": "현재 케이스 스냅샷", "evaluator": "시연 평가기", "result_channel": "응답"}, "selected_node": "Evaluator"}
    node_labels = {"Variables": "변수", "Case input": "케이스 입력", "Evaluator": "평가기", "Result mapping": "결과 매핑", "Objectives": "목적·제약"}

    def __init__(self, document, changed, open_tool):
        document = copy.deepcopy(document or {})
        if document.get("proposal") and not document.get("data"):
            document["data"] = {
                "study_name": document.get("name", "자문 제안 검토"), "budget": 12,
                "variables": [{"name": "재료 변수 그룹", "low": 0.0, "high": 1.0, "unit": "—"},
                              {"name": "접촉 변수 그룹", "low": 0.0, "high": 1.0, "unit": "—"}],
                "objectives": [{"name": "시험·해석 차이", "sense": "min", "unit": "—"}],
                "constraints": [], "candidates": [], "selected": None, "source_type": "proposal",
                "workflow": {"case_ref": "케이스 미연결", "evaluator": "평가기 미연결", "result_channel": "응답 미선택"},
                "selected_node": "Variables", "proposal_draft": True,
            }
        super().__init__(document, changed, open_tool)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout(); bar.addWidget(QLabel("연구")); self.study = QLineEdit(); bar.addWidget(self.study, 2)
        self.study.textEdited.connect(lambda text:self.persist_setting('study_name',text))
        bar.addWidget(QLabel("DOE 예산")); self.budget = QSpinBox(); self.budget.setRange(2, 1000); bar.addWidget(self.budget)
        self.budget.valueChanged.connect(lambda value:self.persist_setting('budget',value))
        bar.addWidget(_button("연구 검증", self.validate)); bar.addWidget(_button("시연 DOE 생성", self.generate)); root.addLayout(bar)
        splitter = QSplitter(); self.tree = QTreeWidget(); self.tree.setHeaderLabels(["연구 객체"])
        self.tree.itemSelectionChanged.connect(self._tree_selected); splitter.addWidget(self.tree)
        self.tabs = QTabWidget()
        flow_page = QWidget(); flow_layout = QVBoxLayout(flow_page)
        self.scene = QGraphicsScene(); self.workflow = QGraphicsView(self.scene); self.workflow.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.workflow.viewport().installEventFilter(self)
        flow_layout.addWidget(self.workflow, 1)
        flow_layout.addWidget(QLabel("포트 계약 · ParameterSet → CaseRef → RunRef → Response"))
        self.flow_table = QTableWidget(); _header(self.flow_table, ["단계", "입력 형식", "출력 형식", "연결 값"])
        flow_layout.addWidget(self.flow_table, 1)
        self.tabs.addTab(flow_page, "평가 절차")
        design = QWidget(); dl = QVBoxLayout(design)
        design_tabs = QTabWidget(); dl.addWidget(design_tabs)
        variable_page = QWidget(); variable_layout = QVBoxLayout(variable_page)
        self.variables = QTableWidget(); _header(self.variables, ["변수", "하한", "상한", "단위"])
        self.variables.cellChanged.connect(self._variable_edit); variable_layout.addWidget(self.variables)
        row = QHBoxLayout(); row.addWidget(_button("변수 추가", self.add_variable)); row.addWidget(_button("선택 변수 삭제", self.remove_variable)); variable_layout.addLayout(row)
        design_tabs.addTab(variable_page, "변수")
        objective_page = QWidget(); objective_layout = QVBoxLayout(objective_page)
        self.objectives = QTableWidget(); _header(self.objectives, ["목적 응답", "방향 min/max", "단위"])
        self.objectives.cellChanged.connect(self._objective_edit); objective_layout.addWidget(self.objectives)
        row = QHBoxLayout(); row.addWidget(_button("목적 추가", self.add_objective)); row.addWidget(_button("선택 목적 삭제", self.remove_objective)); objective_layout.addLayout(row)
        design_tabs.addTab(objective_page, "목적")
        constraint_page = QWidget(); constraint_layout = QVBoxLayout(constraint_page)
        self.constraints = QTableWidget(); _header(self.constraints, ["제약 응답", "상한", "단위"])
        self.constraints.cellChanged.connect(self._constraint_edit); constraint_layout.addWidget(self.constraints)
        row = QHBoxLayout(); row.addWidget(_button("제약 추가", self.add_constraint)); row.addWidget(_button("선택 제약 삭제", self.remove_constraint)); constraint_layout.addLayout(row)
        design_tabs.addTab(constraint_page, "제약")
        self.tabs.addTab(design, "설계 공간")
        candidates = QWidget(); cl = QVBoxLayout(candidates)
        self.candidate_table = QTableWidget(); _header(self.candidate_table, ["후보", "두께", "폭", "질량", "처짐", "응력", "상태"])
        self.candidate_table.itemSelectionChanged.connect(self._candidate_selected); cl.addWidget(self.candidate_table, 2)
        self.pareto = QWidget(); cl.addWidget(self.pareto, 3)
        self.tabs.addTab(candidates, "후보·Pareto")
        if self._doc.get("proposal"):
            proposal_page = QWidget(); proposal_layout = QVBoxLayout(proposal_page)
            proposal_layout.addWidget(QLabel("자문 제안 · 원문 근거와 연결 상태"))
            self.proposal_view = QPlainTextEdit(); self.proposal_view.setReadOnly(True)
            proposal_layout.addWidget(self.proposal_view)
            self.tabs.addTab(proposal_page, "제안·근거")
        splitter.addWidget(self.tabs)
        side = QWidget(); s = QVBoxLayout(side); s.addWidget(QLabel("연구 속성"))
        self.detail = QLabel(); self.detail.setWordWrap(True); s.addWidget(self.detail)
        self.proposal_summary = QLabel(); self.proposal_summary.setWordWrap(True); s.addWidget(self.proposal_summary)
        workflow_form = QGroupBox("절차 매핑"); form = QFormLayout(workflow_form)
        self.case_ref = QLineEdit(); form.addRow("케이스 참조", self.case_ref)
        self.evaluator = QLineEdit(); form.addRow("평가기", self.evaluator)
        self.result_channel = QLineEdit(); form.addRow("응답 채널", self.result_channel)
        s.addWidget(workflow_form); s.addWidget(_button("절차 매핑 적용", self._apply_workflow))
        s.addWidget(_button("후보 CSV 가져오기", self.import_csv))
        s.addWidget(_button("전처리에서 후보 열기", self.open_pre))
        s.addStretch(); self.provenance = QLabel(); self.provenance.setWordWrap(True); s.addWidget(self.provenance)
        splitter.addWidget(side); splitter.setSizes([210, 820, 250]); root.addWidget(splitter)
        self.refresh()

    def tool_actions(self):
        return [("연구 검증", "validate", self.validate, "F7"),
                ("시연 DOE 생성", "run", self.generate, "F5"),
                ("후보 가져오기", "import", self.import_csv, "Ctrl+I"),
                ("전처리에서 열기", "pre", self.open_pre, "")]

    def tool_menus(self):
        return {"연구": ["연구 검증", "시연 DOE 생성"], "탐색": ["후보 가져오기", "전처리에서 열기"]}

    def refresh(self):
        if not hasattr(self, "tree"): return
        self._loading = True; d = self.data
        self.study.setText(d["study_name"]); self.budget.setValue(d["budget"])
        self.case_ref.setText(d["workflow"]["case_ref"]); self.evaluator.setText(d["workflow"]["evaluator"]); self.result_channel.setText(d["workflow"]["result_channel"])
        self.tree.clear(); root = QTreeWidgetItem([d["study_name"]]); self.tree.addTopLevelItem(root)
        if self._doc.get("proposal"):
            proposal_item = QTreeWidgetItem(["자문 제안 · 근거"])
            proposal_item.setData(0, Qt.ItemDataRole.UserRole, "proposal")
            root.addChild(proposal_item)
        workflow = QTreeWidgetItem(["평가 절차"]); root.addChild(workflow)
        for label in ["파라미터 집합", "케이스 입력", "평가기", "결과 매핑"]: workflow.addChild(QTreeWidgetItem([label]))
        variable_root = QTreeWidgetItem(["변수"]); root.addChild(variable_root)
        for variable in d["variables"]: variable_root.addChild(QTreeWidgetItem([variable["name"]]))
        objective_root = QTreeWidgetItem(["목적·제약"]); root.addChild(objective_root)
        for item in d["objectives"] + d["constraints"]: objective_root.addChild(QTreeWidgetItem([item["name"]]))
        candidate_root = QTreeWidgetItem([f"후보 · {len(d['candidates'])}"]); root.addChild(candidate_root)
        selected_index = d.get("selected")
        selected_item = None
        for i, candidate in enumerate(d["candidates"]):
            item = QTreeWidgetItem([candidate["id"]]); item.setData(0, Qt.ItemDataRole.UserRole, i); candidate_root.addChild(item)
            if i == selected_index: selected_item = item
        root.setExpanded(True); candidate_root.setExpanded(True)
        if selected_item is not None:
            self.tree.setCurrentItem(selected_item)
            self.tree.scrollToItem(selected_item)
        self.variables.setRowCount(len(d["variables"]))
        for i, variable in enumerate(d["variables"]):
            for j, key in enumerate(("name", "low", "high", "unit")): self.variables.setItem(i, j, _table_item(variable[key], True))
        self.objectives.setRowCount(len(d["objectives"]))
        for i, objective in enumerate(d["objectives"]):
            for j, key in enumerate(("name", "sense", "unit")): self.objectives.setItem(i, j, _table_item(objective[key], True))
        self.constraints.setRowCount(len(d["constraints"]))
        for i, constraint in enumerate(d["constraints"]):
            for j, key in enumerate(("name", "limit", "unit")): self.constraints.setItem(i, j, _table_item(constraint[key], True))
        variable_names = [v["name"] for v in d["variables"]]
        objective_names = [o["name"] for o in d["objectives"]]
        constraint_names = [c["name"] for c in d["constraints"]]
        candidate_keys = ["id", *variable_names, *objective_names, *constraint_names, "status"]
        _header(self.candidate_table, ["후보", *variable_names, *objective_names, *constraint_names, "상태"])
        self.candidate_table.setRowCount(len(d["candidates"]))
        for i, candidate in enumerate(d["candidates"]):
            values = [candidate.get(key, "—") for key in candidate_keys]
            if values[-1] == "feasible": values[-1] = "적합"
            elif values[-1] == "constraint": values[-1] = "제약 위반"
            elif values[-1] == "imported": values[-1] = "가져옴"
            for j, value in enumerate(values): self.candidate_table.setItem(i, j, _table_item(value))
        self._draw_workflow()
        workflow_rows = [
            ("변수", "설계 범위", "ParameterSet", f"{len(d['variables'])}개 변수"),
            ("케이스 입력", "ParameterSet", "CaseRef", d["workflow"]["case_ref"]),
            ("평가기", "CaseRef", "RunRef", d["workflow"]["evaluator"]),
            ("결과 매핑", "RunRef", "Response", d["workflow"]["result_channel"]),
            ("목적·제약", "Response", "스칼라 / 적합성", f"목적 {len(d['objectives'])}개, 제약 {len(d['constraints'])}개"),
        ]
        self.flow_table.setRowCount(len(workflow_rows))
        for row, values in enumerate(workflow_rows):
            for col, value in enumerate(values): self.flow_table.setItem(row, col, _table_item(value))
        plot_keys = objective_names[:2]
        plot_candidates = [c for c in d["candidates"] if len(plot_keys) == 2 and all(isinstance(c.get(key), (float, int)) for key in plot_keys)]
        plot_points = [(c[plot_keys[0]], c[plot_keys[1]]) for c in plot_candidates]
        parent = self.pareto.parentWidget().layout()
        new, series = _scatter_chart(plot_points, plot_keys[0] if plot_keys else "목적 1", plot_keys[1] if len(plot_keys) > 1 else "목적 2")
        series.sigClicked.connect(lambda _item, points, _event: self._pareto_selected(points[0].pos(), plot_candidates, plot_keys) if points else None)
        selected = d.get("selected")
        candidate = d["candidates"][selected] if isinstance(selected, int) and 0 <= selected < len(d["candidates"]) else None
        if candidate and len(plot_keys) == 2 and candidate in plot_candidates:
            new.plot([candidate[plot_keys[0]]], [candidate[plot_keys[1]]], pen=None,
                     symbol="o", symbolSize=17, symbolBrush=pg.mkBrush("#e0792d"),
                     symbolPen=pg.mkPen("#713b17", width=2))
        parent.replaceWidget(self.pareto, new)
        self.pareto.deleteLater(); self.pareto = new
        node = d.get("selected_node")
        if self.tabs.currentIndex() == 0 and node:
            node_details = {"Variables": f"범위 지정 변수 {len(d['variables'])}개",
                            "Case input": d["workflow"]["case_ref"],
                            "Evaluator": d["workflow"]["evaluator"],
                            "Result mapping": d["workflow"]["result_channel"],
                            "Objectives": f"목적 {len(d['objectives'])}개 / 제약 {len(d['constraints'])}개"}
            self.detail.setText(f"{self.node_labels.get(node, node)}\n{node_details.get(node, '')}")
        else:
            if candidate:
                status = {"feasible": "적합", "constraint": "제약 위반", "imported": "가져옴"}.get(candidate.get("status"), candidate.get("status", "미정"))
                lines = [f"후보 {candidate.get('id', '미지정')}", f"상태: {status}"]
                for variable in d["variables"]:
                    name = variable["name"]; lines.append(f"변수 {name}: {candidate.get(name, '—')} {variable['unit']}")
                for objective in d["objectives"]:
                    name = objective["name"]; direction = "최소" if objective["sense"] == "min" else "최대"
                    lines.append(f"목적 {name} ({direction}): {candidate.get(name, '—')} {objective['unit']}")
                for constraint in d["constraints"]:
                    name = constraint["name"]
                    lines.append(f"제약 {name}: {candidate.get(name, '—')} {constraint['unit']} · 상한 {constraint['limit']} {constraint['unit']}")
                self.detail.setText("\n".join(lines))
            else:
                self.detail.setText("후보를 선택하면 응답과 제약을 볼 수 있습니다.")
        source_label = {"demo": "시연 후보 값", "proposal": "자문 제안 · 미검증 초안", "csv": "가져온 후보 값"}
        self.provenance.setText(source_label.get(d["source_type"], d["source_type"]))
        proposal = self._doc.get("proposal")
        self.proposal_summary.setVisible(bool(proposal))
        if proposal:
            self.proposal_summary.setText(f"자문 제안: {proposal.get('status', '검토 초안')}\n변수 범위·목적·예산은 편집 가능한 검토값이며 실제 케이스/평가기와 연결되지 않았습니다.")
            self.proposal_view.setPlainText(self._proposal_evidence_text())
        if candidate: self.candidate_table.selectRow(selected)
        self._loading = False

    def _proposal_evidence_text(self):
        proposal = self._doc.get("proposal", {})
        ref = self._doc.get("source_ref", {})
        message_ids = proposal.get("message_ids", [])
        lines = [f"상태: {proposal.get('status', '검토 초안')}",
                 f"제안 원문: {proposal.get('rationale', '')}",
                 f"자문 문서: {ref.get('id') or '미지정'} · 버전 {ref.get('revision') if ref.get('revision') is not None else '로컬 스냅샷'}",
                 f"발언 ID: {', '.join(message_ids) if message_ids else '없음'}", ""]
        source_path = ref.get("path")
        if not source_path:
            return "\n".join(lines + ["자문 원문 파일 경로가 없어 발언 내용을 확인할 수 없습니다. 제안 문구와 ID만 보존했습니다."])
        path = Path(source_path)
        candidates = [path]
        if ref.get("id") and ref.get("revision") is not None:
            candidates.insert(0, path.parent / ".history" / str(ref["id"]) / f"{ref['revision']}.json")
        source = None
        for candidate in candidates:
            try: loaded = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError): continue
            if loaded.get("id") == ref.get("id") and loaded.get("revision") == ref.get("revision"):
                source = loaded; break
        if source is None:
            return "\n".join(lines + ["지정한 ID·버전의 자문 원문을 찾지 못했습니다. 최신 문서로 자동 대체하지 않았습니다."])
        messages = {message.get("id"): message for message in source.get("messages", [])}
        evidence = {item.get("id"): item for item in source.get("evidence", [])}
        lines.append("자문 발언 원문")
        for mid in message_ids:
            message = messages.get(mid)
            if not message:
                lines.append(f"{mid}: 원문에서 찾지 못함"); continue
            lines.append(f"{mid} · {message.get('role', '발언자')}\n{message.get('text', '')}")
            for evidence_id in message.get("evidence", []):
                item = evidence.get(evidence_id)
                if item: lines.append(f"  근거 {evidence_id} · {item.get('title', '')}: {item.get('text', '')}")
        return "\n\n".join(lines)

    def _draw_workflow(self):
        self.scene.clear()
        names = ["Variables", "Case input", "Evaluator", "Result mapping", "Objectives"]
        captions = [f"변수 {len(self.data['variables'])}개", self.data["workflow"]["case_ref"],
                    self.data["workflow"]["evaluator"], self.data["workflow"]["result_channel"],
                    f"목적 {len(self.data['objectives'])}개"]
        for i, name in enumerate(names):
            x, y = 20 + i * 153, 55 + (i % 2) * 34
            selected = self.data.get("selected_node") == name
            rect = self.scene.addRect(x, y, 127, 62, QPen(QColor("#1b6498") if selected else QColor("#8799a8"), 2 if selected else 1), QBrush(QColor("#dbeaf6") if selected else QColor("#f3f6f8")))
            rect.setData(0, name)
            text = self.scene.addText(self.node_labels.get(name, name)); text.setDefaultTextColor(QColor("#163d5e")); text.setPos(x + 8, y + 5); text.setData(0, name)
            caption_font = QFont(); caption_font.setPointSize(9)
            caption_value = QFontMetrics(caption_font).elidedText(captions[i], Qt.TextElideMode.ElideRight, 108)
            caption = self.scene.addText(caption_value, caption_font); caption.setDefaultTextColor(QColor("#546b7d")); caption.setPos(x + 8, y + 29); caption.setData(0, name)
            if i: self.scene.addLine(x - 26, y + 30, x, y + 30, QPen(QColor("#58758b"), 2))
        self.scene.setSceneRect(0, 0, 800, 190)

    def eventFilter(self, obj, event):
        if hasattr(self, "workflow") and obj is self.workflow.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            item = self.workflow.itemAt(event.position().toPoint())
            if item and item.data(0):
                name = item.data(0)
                self.mutate("평가 단계 선택", lambda: self.data.__setitem__("selected_node", name))
                return True
        return super().eventFilter(obj, event)

    def _apply_workflow(self):
        values = {"case_ref": self.case_ref.text().strip(), "evaluator": self.evaluator.text().strip(), "result_channel": self.result_channel.text().strip()}
        if not all(values.values()):
            self._message("절차 매핑", "케이스 참조, 평가기, 응답 채널이 모두 필요합니다."); return
        self.mutate("절차 매핑 편집", lambda: self.data.__setitem__("workflow", values))

    def _tree_selected(self):
        if self._loading: return
        item = self.tree.currentItem(); index = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if index == "proposal" and hasattr(self, "proposal_view"):
            self.tabs.setCurrentWidget(self.proposal_view.parentWidget())
            return
        if isinstance(index, int) and self.data.get("selected") != index:
            before = self.document(); self.data["selected"] = index; self.tabs.setCurrentIndex(2); self.refresh(); self._changed("후보 선택", before)

    def _candidate_selected(self):
        if self._loading: return
        index = self.candidate_table.currentRow()
        if index >= 0 and self.data.get("selected") != index:
            before = self.document(); self.data["selected"] = index; self.refresh(); self._changed("후보 선택", before)

    def _pareto_selected(self, point, plotted, keys):
        for candidate in plotted:
            if abs(candidate[keys[0]] - point.x()) < 1e-6 and abs(candidate[keys[1]] - point.y()) < 1e-6:
                index = self.data["candidates"].index(candidate)
                self.mutate("후보 선택", lambda: self.data.__setitem__("selected", index))
                return

    def _variable_edit(self, row, col):
        if self._loading: return
        key = ("name", "low", "high", "unit")[col]
        value = self.variables.item(row, col).text().strip()
        if key in ("low", "high"):
            try: value = float(value)
            except ValueError: self.refresh(); return
            if not math.isfinite(value): self.refresh(); return
        self.mutate("설계 변수 편집", lambda: self.data["variables"][row].__setitem__(key, value))

    def add_variable(self):
        name, ok = QInputDialog.getText(self, "변수 추가", "변수 이름")
        if ok and name.strip(): self.mutate("설계 변수 추가", lambda: self.data["variables"].append({"name": name.strip(), "low": 0.0, "high": 1.0, "unit": "—"}))

    def remove_variable(self):
        row = self.variables.currentRow()
        if row >= 0: self.mutate("설계 변수 삭제", lambda: self.data["variables"].pop(row))

    def _objective_edit(self, row, col):
        if self._loading: return
        key = ("name", "sense", "unit")[col]
        value = self.objectives.item(row, col).text().strip()
        if key == "sense" and value not in ("min", "max"): self._message("목적 방향", "min 또는 max를 입력하세요."); self.refresh(); return
        self.mutate("목적 응답 편집", lambda: self.data["objectives"][row].__setitem__(key, value))

    def _constraint_edit(self, row, col):
        if self._loading: return
        key = ("name", "limit", "unit")[col]
        value = self.constraints.item(row, col).text().strip()
        if key == "limit":
            try: value = float(value)
            except ValueError: self._message("제약 상한", "숫자를 입력하세요."); self.refresh(); return
            if not math.isfinite(value): self._message("제약 상한", "유한한 숫자를 입력하세요."); self.refresh(); return
        self.mutate("제약 편집", lambda: self.data["constraints"][row].__setitem__(key, value))

    def add_objective(self):
        name, ok = QInputDialog.getText(self, "목적 추가", "응답 이름")
        if ok and name.strip(): self.mutate("목적 추가", lambda: self.data["objectives"].append({"name": name.strip(), "sense": "min", "unit": "—"}))

    def remove_objective(self):
        row = self.objectives.currentRow()
        if row >= 0: self.mutate("목적 삭제", lambda: self.data["objectives"].pop(row))

    def add_constraint(self):
        name, ok = QInputDialog.getText(self, "제약 추가", "응답 이름")
        if ok and name.strip(): self.mutate("제약 추가", lambda: self.data["constraints"].append({"name": name.strip(), "limit": 1.0, "unit": "—"}))

    def remove_constraint(self):
        row = self.constraints.currentRow()
        if row >= 0: self.mutate("제약 삭제", lambda: self.data["constraints"].pop(row))

    def validate(self):
        errors = []
        if not self.study.text().strip(): errors.append("연구 이름이 필요합니다")
        for variable in self.data["variables"]:
            if variable["low"] >= variable["high"]: errors.append(f"{variable['name']}: 하한은 상한보다 작아야 합니다")
            if not math.isfinite(variable["low"]) or not math.isfinite(variable["high"]): errors.append(f"{variable['name']}: 유한한 범위가 필요합니다")
        if not self.data["variables"]: errors.append("변수가 최소 1개 필요합니다")
        if not self.data["objectives"]: errors.append("목적이 최소 1개 필요합니다")
        names = [item["name"] for section in ("variables", "objectives", "constraints") for item in self.data[section]]
        if any(not name for name in names): errors.append("변수와 응답 이름을 입력하세요")
        if len(names) != len(set(names)): errors.append("변수와 응답 이름은 서로 달라야 합니다")
        if not all(self.data["workflow"].values()): errors.append("절차 매핑이 비어 있습니다")
        if self.data.get("proposal_draft"):
            if self.data["workflow"].get("case_ref") == "케이스 미연결": errors.append("자문 초안에 실제 케이스 참조를 연결하세요")
            if self.data["workflow"].get("evaluator") == "평가기 미연결": errors.append("자문 초안에 평가기를 연결하세요")
        self._message("연구 검증", "시연 DOE를 생성할 수 있습니다." if not errors else "\n".join(errors))
        return not errors

    def generate(self):
        if not self.validate(): return
        def edit():
            d = self.data; d["study_name"] = self.study.text().strip(); d["budget"] = self.budget.value(); d["source_type"] = "demo"
            candidates = []
            for i in range(d["budget"]):
                values = {}
                fractions = []
                for j, variable in enumerate(d["variables"]):
                    fraction = ((i + 1) * (0.6180339887 + j * 0.17320508)) % 1
                    fractions.append(fraction)
                    values[variable["name"]] = round(variable["low"] + (variable["high"] - variable["low"]) * fraction, 4)
                a = fractions[0] if fractions else .5
                b = fractions[1] if len(fractions) > 1 else .5
                responses = [round(.5 + 8 * a + 4 * b, 4), round(12 / (1 + 4 * a + 2 * b), 4)]
                for j, objective in enumerate(d["objectives"]):
                    values[objective["name"]] = responses[j] if j < 2 else round((j + 1) * (a + b + .25), 4)
                for j, constraint in enumerate(d["constraints"]):
                    values[constraint["name"]] = round(420 / (1 + 2 * a + b + j), 4)
                feasible = all(values[c["name"]] <= c["limit"] for c in d["constraints"])
                candidates.append({"id": f"C{i + 1:03d}", **values, "status": "feasible" if feasible else "constraint"})
            d["candidates"] = candidates; d["selected"] = 0
        self.mutate("시연 DOE 생성", edit); self.tabs.setCurrentIndex(2)

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "후보 CSV 가져오기", "", "CSV 파일 (*.csv)")
        if not path: return
        try:
            with open(path, encoding="utf-8-sig", newline="") as file: rows = list(csv.DictReader(file))
            required = tuple(v["name"] for v in self.data["variables"]) + tuple(o["name"] for o in self.data["objectives"]) + tuple(c["name"] for c in self.data["constraints"])
            if not rows or any(key not in rows[0] for key in required): raise ValueError("필요한 CSV 열: " + ", ".join(required))
            candidates = []
            for i, row in enumerate(rows):
                values = {key: float(row[key]) for key in required}
                if not all(math.isfinite(value) for value in values.values()): raise ValueError(f"{i + 2}행에 NaN/무한대가 있습니다")
                candidates.append({"id": row.get("id") or f"C{i + 1:03d}", **values, "status": row.get("status") or "imported"})
        except (OSError, ValueError) as exc: self._message("가져오기 실패", str(exc)); return
        self.mutate("후보 CSV 가져오기", lambda: self.data.update(candidates=candidates, selected=0, source_type="csv", source_path=path))
        self.tabs.setCurrentIndex(2)

    def open_pre(self):
        index = self.data.get("selected")
        if index is None: return
        candidate = self.data["candidates"][index]
        saved_ref = bool(self._doc.get("path")) and not self._dirty and self._doc.get("revision", 0) > 0
        document = {"kind": "pre", "name": f"{candidate['id']} 입력", "data": {
                    "candidate": candidate, "parameter_units": {v["name"]: v["unit"] for v in self.data["variables"]},
                    "source_study": {"id": self._doc.get("id"),
                                     "path": self._doc.get("path") if saved_ref else None,
                                     "revision": self._doc.get("revision") if saved_ref else None,
                                     "mode": "saved_revision" if saved_ref else "local_snapshot"}}}
        self._open_tool("pre", document)


def create_workspace(kind, document, changed, open_tool):
    """Create the requested workspace. Aliases match shell and document naming."""
    normalized = str(kind).lower().replace("-", "_")
    from native_pre import NativePreWorkspace
    classes = {"pre": NativePreWorkspace, "preprocessor": NativePreWorkspace,
               "runner": RunnerWorkspace, "run": RunnerWorkspace,
               "post": PostWorkspace, "postprocessor": PostWorkspace,
               "opt": OptWorkspace, "optimization": OptWorkspace}
    try: cls = classes[normalized]
    except KeyError as exc: raise ValueError(f"Unknown workspace kind: {kind}") from exc
    return cls(document, changed, open_tool)
