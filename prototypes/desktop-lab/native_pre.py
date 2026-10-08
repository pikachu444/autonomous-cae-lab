"""Object-centric native preprocessor workspace for design review."""
from __future__ import annotations

import copy
import math
from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QPointF
from PySide6.QtGui import QColor, QBrush, QPen, QPolygonF, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QTableWidget, QLabel, QPushButton, QComboBox,
    QDoubleSpinBox, QLineEdit, QFileDialog, QGraphicsView, QGraphicsScene,
    QFormLayout, QGroupBox, QHeaderView, QStackedWidget, QPlainTextEdit,
    QMessageBox, QInputDialog,
)
import pyqtgraph as pg

from workspaces import Workspace, _chart, _header, _table_item, _button
from table_import import map_table_file


def plate_mesh(nx=12, ny=6):
    vertices = [[float(i), float(j), 0.0] for j in range(ny + 1) for i in range(nx + 1)]
    def vertex(i, j): return j * (nx + 1) + i + 1
    faces = [[vertex(i, j), vertex(i + 1, j), vertex(i + 1, j + 1), vertex(i, j + 1)]
             for j in range(ny) for i in range(nx)]
    return {"vertices": vertices, "faces": faces, "source": "12 × 6 plate · demonstration mesh",
            "sets": {"왼쪽 고정": [j * nx for j in range(ny)],
                     "오른쪽 하중": [j * nx + nx - 1 for j in range(ny)],
                     "상단 경계": [(ny - 1) * nx + i for i in range(nx)]}}


class NativePreWorkspace(Workspace):
    kind = "pre"
    defaults = {
        "source": "검토용 응답 곡선", "source_type": "demo",
        "points": [[x / 2, round(15 + 11 * math.sin(x / 5) + x * .55, 3)] for x in range(25)],
        "x_name": "변위", "x_unit": "mm", "y_name": "하중", "y_unit": "N",
        "intervals": [], "selection": None, "mesh": plate_mesh(),
        "material": {"name": "구조용 강", "law": "선형 탄성", "E_GPa": 210.0, "poisson": .30, "rho": 7850.0},
        "condition": {"name": "인장 하중", "magnitude": 120.0, "unit": "N", "target": "set:오른쪽 하중"},
        "bc_by_set": {"왼쪽 고정": {"type": "고정", "value": 0.0, "unit": "mm"},
                      "오른쪽 하중": {"type": "하중", "value": 120.0, "unit": "N"}},
        "face_assignments": {},
        "material_point": {"law": "선형 탄성", "history": [[0.0, 0.0, 0.0], [0.5, .001, 210.0], [1.0, .002, 420.0]]},
        "pde": {"equation": "-∇·(E∇u) = f", "weak_form": "∫Ω E∇u·∇v dΩ = ∫Ω fv dΩ + ∫Γₙ tv dΓ",
                "region": "전체 메시", "bc_expression": "u = 0 on 왼쪽 고정"},
    }

    def set_document(self, document):
        self._doc = copy.deepcopy(document or {})
        self._doc["kind"] = self.kind
        self._doc.setdefault("data", {})
        self._dirty = False
        for key, value in self.defaults.items():
            self._doc["data"].setdefault(key, copy.deepcopy(value))
        d = self.data
        d["mesh"].setdefault("sets", {})
        d.setdefault("x_name", "X"); d.setdefault("x_unit", "—")
        d.setdefault("y_name", "응답"); d.setdefault("y_unit", "—")
        d.setdefault("bc_by_set", {}); d.setdefault("face_assignments", {})
        for key, value in self.defaults["material"].items(): d["material"].setdefault(key, value)
        d.setdefault("material_point", self.defaults["material_point"].copy())
        d.setdefault("pde", self.defaults["pde"].copy())
        if hasattr(self, "tree"): self.refresh()

    def __init__(self, document, changed, open_tool):
        super().__init__(document, changed, open_tool)
        root = QHBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(); root.addWidget(split)
        self.tree = QTreeWidget(); self.tree.setHeaderLabels(["객체 / 영역"])
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        split.addWidget(self.tree)
        self.tabs = QTabWidget(); split.addWidget(self.tabs)
        curve = QWidget(); cv = QVBoxLayout(curve)
        strip = QHBoxLayout(); self.curve_title = QLabel(); strip.addWidget(self.curve_title, 1)
        strip.addWidget(_button("CSV 가져오기", self.import_csv)); strip.addWidget(_button("선택 점으로 구간", self.add_interval))
        cv.addLayout(strip)
        self.chart = QWidget(); cv.addWidget(self.chart, 3)
        self.points = QTableWidget(); _header(self.points, ["변위 [mm]", "하중 [N]"])
        self.points.cellChanged.connect(self._point_edited)
        self.points.itemSelectionChanged.connect(self._point_selected)
        cv.addWidget(self.points, 2)
        self.tabs.addTab(curve, "곡선·구간")
        mesh_page = QWidget(); mv = QVBoxLayout(mesh_page)
        mesh_top = QHBoxLayout(); self.mesh_label = QLabel(); mesh_top.addWidget(self.mesh_label, 1)
        mesh_top.addWidget(_button("OBJ 가져오기", self.import_obj)); mv.addLayout(mesh_top)
        self.scene = QGraphicsScene(); self.mesh_view = QGraphicsView(self.scene)
        self.mesh_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.mesh_view.viewport().installEventFilter(self)
        mv.addWidget(self.mesh_view)
        self.mesh_legend = QLabel("파랑: 고정 경계   주황: 하중 경계   진한 윤곽: 선택 면")
        mv.addWidget(self.mesh_legend)
        self.tabs.addTab(mesh_page, "메시·영역")
        mp = QWidget(); mpv = QVBoxLayout(mp)
        mpv.addWidget(QLabel("재료점 이력 · 시간, 변형률, 응력 값을 편집하고 저장합니다."))
        self.history = QTableWidget(); _header(self.history, ["시간 [s]", "변형률 [—]", "응력 [MPa]"])
        self.history.cellChanged.connect(self._history_edited); mpv.addWidget(self.history)
        row = QHBoxLayout(); row.addWidget(_button("이력 행 추가", self._add_history)); row.addWidget(_button("선택 행 삭제", self._remove_history)); mpv.addLayout(row)
        self.tabs.addTab(mp, "재료점 이력")
        pde_page = QWidget(); pv = QVBoxLayout(pde_page)
        form = QFormLayout()
        self.equation = QLineEdit(); form.addRow("지배 방정식", self.equation)
        self.weak_form = QPlainTextEdit(); self.weak_form.setMaximumHeight(100); form.addRow("약형식", self.weak_form)
        self.pde_region = QComboBox(); form.addRow("적용 영역", self.pde_region)
        self.bc_expression = QLineEdit(); form.addRow("경계식", self.bc_expression)
        pv.addLayout(form); pv.addWidget(_button("PDE 식·경계 저장", self._apply_pde)); pv.addStretch()
        self.tabs.addTab(pde_page, "PDE 식·약형식")
        self.inspector = QStackedWidget(); split.addWidget(self.inspector)
        self._build_inspector()
        split.setSizes([215, 810, 270])
        self.refresh()

    def tool_actions(self):
        return [("데이터 가져오기", "import", self.import_csv, "Ctrl+I"),
                ("메시 가져오기", "import", self.import_obj, ""),
                ("구간 정의", "add", self.add_interval, ""),
                ("재료·조건", "edit", self.show_material, ""),
                ("입력 검증", "validate", self.validate, "F7"),
                ("실행기로", "run", self.send_runner, "")]

    def tool_menus(self):
        return {"선택": ["구간 정의"], "재료": ["재료·조건"],
                "조건": ["입력 검증"], "작업": ["데이터 가져오기", "메시 가져오기", "실행기로"]}

    def _page(self, title):
        page = QWidget(); layout = QVBoxLayout(page)
        heading = QLabel(title); heading.setProperty("section", True); layout.addWidget(heading)
        self.inspector.addWidget(page)
        return page, layout

    def _build_inspector(self):
        page, layout = self._page("선택 속성")
        self.overview = QLabel(); self.overview.setWordWrap(True); layout.addWidget(self.overview); layout.addStretch()
        self.diagnostic = QLabel(); self.diagnostic.setWordWrap(True); layout.addWidget(self.diagnostic)
        page, layout = self._page("곡선 점")
        form = QFormLayout(); self.point_x = QDoubleSpinBox(); self.point_y = QDoubleSpinBox()
        for field in (self.point_x, self.point_y): field.setRange(-1e9, 1e9); field.setDecimals(5)
        form.addRow("X", self.point_x); form.addRow("Y", self.point_y); layout.addLayout(form)
        layout.addWidget(_button("선택 점 적용", self._apply_point)); layout.addStretch()
        page, layout = self._page("선택 구간")
        form = QFormLayout(); self.interval_a = QDoubleSpinBox(); self.interval_b = QDoubleSpinBox(); self.interval_weight = QDoubleSpinBox()
        for field in (self.interval_a, self.interval_b, self.interval_weight): field.setRange(-1e9, 1e9); field.setDecimals(5)
        form.addRow("시작 X", self.interval_a); form.addRow("끝 X", self.interval_b); form.addRow("가중치", self.interval_weight)
        layout.addLayout(form); layout.addWidget(_button("구간 적용", self._apply_interval)); layout.addWidget(_button("구간 삭제", self._delete_interval)); layout.addStretch()
        page, layout = self._page("메시 면 · 배정")
        form = QFormLayout(); self.face_id = QLabel(); form.addRow("면 ID", self.face_id)
        self.face_material = QComboBox(); self.face_material.addItems(["기본 재료", "미배정"]); form.addRow("재료", self.face_material)
        self.face_bc = QComboBox(); self.face_bc.addItems(["영역 경계 따름", "고정", "하중", "자유"]); form.addRow("경계 조건", self.face_bc)
        layout.addLayout(form); layout.addWidget(_button("선택 면에 배정", self._apply_face)); layout.addStretch()
        page, layout = self._page("명명된 영역 · 조건")
        form = QFormLayout(); self.set_name = QLabel(); form.addRow("영역", self.set_name)
        self.set_bc = QComboBox(); self.set_bc.addItems(["자유", "고정", "하중", "변위"]); form.addRow("조건", self.set_bc)
        self.set_value = QDoubleSpinBox(); self.set_value.setRange(-1e9, 1e9); self.set_value.setDecimals(4); form.addRow("크기", self.set_value)
        self.set_unit = QComboBox(); self.set_unit.addItems(["N", "kN", "mm", "MPa", "—"]); form.addRow("단위", self.set_unit)
        layout.addLayout(form); layout.addWidget(_button("영역 조건 배정", self._apply_set)); layout.addStretch()
        page, layout = self._page("재료 · 구성 법칙")
        form = QFormLayout(); self.mat_name = QLineEdit(); form.addRow("재료명", self.mat_name)
        self.law = QComboBox(); self.law.addItems(["선형 탄성", "Neo-Hookean", "사용자 정의"]); form.addRow("구성 법칙", self.law)
        self.elastic = QDoubleSpinBox(); self.elastic.setRange(.00001, 1e6); self.elastic.setDecimals(4); form.addRow("E [GPa]", self.elastic)
        self.poisson = QDoubleSpinBox(); self.poisson.setRange(-.99, .499); self.poisson.setDecimals(4); form.addRow("ν", self.poisson)
        self.rho = QDoubleSpinBox(); self.rho.setRange(0, 1e8); self.rho.setDecimals(2); form.addRow("ρ [kg/m³]", self.rho)
        layout.addLayout(form); layout.addWidget(_button("재료 적용", self._apply_material)); layout.addStretch()
        page, layout = self._page("하중 조건")
        form = QFormLayout(); self.cond_name = QLineEdit(); form.addRow("조건명", self.cond_name)
        self.cond_value = QDoubleSpinBox(); self.cond_value.setRange(-1e9, 1e9); self.cond_value.setDecimals(4); form.addRow("크기", self.cond_value)
        self.cond_unit = QComboBox(); self.cond_unit.addItems(["N", "kN", "Pa", "MPa", "mm"]); form.addRow("단위", self.cond_unit)
        self.cond_target = QComboBox(); form.addRow("대상 영역", self.cond_target)
        layout.addLayout(form); layout.addWidget(_button("하중 조건 적용", self._apply_condition)); layout.addStretch()
        page, layout = self._page("곡선 채널 · 단위")
        form = QFormLayout()
        self.x_name = QLineEdit(); form.addRow("X 이름", self.x_name)
        self.x_unit = QLineEdit(); form.addRow("X 단위", self.x_unit)
        self.y_name = QLineEdit(); form.addRow("응답 이름", self.y_name)
        self.y_unit = QLineEdit(); form.addRow("응답 단위", self.y_unit)
        layout.addLayout(form); layout.addWidget(_button("채널·단위 적용", self._apply_channel)); layout.addStretch()
        page, layout = self._page("전달된 후보 · 원문 값")
        self.candidate_note = QLabel("후보 파라미터는 검토용으로 전달됐습니다. 현재 판 메시와 곡선은 별도의 시연 예제이며 후보 값이 모델에 적용되지 않았습니다.")
        self.candidate_note.setWordWrap(True); self.candidate_note.setProperty("note", True); layout.addWidget(self.candidate_note)
        self.candidate_table = QTableWidget(); _header(self.candidate_table, ["변수", "값", "단위"])
        self.candidate_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); layout.addWidget(self.candidate_table)
        self.candidate_source = QLabel(); self.candidate_source.setWordWrap(True); layout.addWidget(self.candidate_source)

    def refresh(self):
        if not hasattr(self, "tree"): return
        self._loading = True; d = self.data; selection = d.get("selection")
        self.tree.clear()
        dataset = QTreeWidgetItem([f"데이터셋 · {d['source']}"]); self.tree.addTopLevelItem(dataset)
        channel = QTreeWidgetItem([f"채널 · {d['y_name']} [{d['y_unit']}] · {len(d['points'])}점"])
        channel.setData(0, Qt.ItemDataRole.UserRole, ["channel", 0]); dataset.addChild(channel)
        interval_root = QTreeWidgetItem([f"구간 · {len(d['intervals'])}"]); self.tree.addTopLevelItem(interval_root)
        for i, interval in enumerate(d["intervals"]):
            item = QTreeWidgetItem([f"I{i + 1:02d} · {interval[0]:g}–{interval[1]:g} {d['x_unit']}"])
            item.setData(0, Qt.ItemDataRole.UserRole, ["interval", i]); interval_root.addChild(item)
        model = QTreeWidgetItem(["모델"]); self.tree.addTopLevelItem(model)
        mesh = d["mesh"]
        mesh_item = QTreeWidgetItem([f"메시 · {len(mesh['vertices'])}절점 / {len(mesh['faces'])}면"])
        mesh_item.setData(0, Qt.ItemDataRole.UserRole, ["mesh", 0]); model.addChild(mesh_item)
        faces_group = QTreeWidgetItem([f"면 · {len(mesh['faces'])}개 (현재 선택 면)"])
        mesh_item.addChild(faces_group)
        if selection and selection[0] == "face" and 0 <= selection[1] < len(mesh["faces"]):
            face_index = selection[1]
            face_item = QTreeWidgetItem([f"F{face_index + 1:03d} · 노드 " + ", ".join(map(str, mesh["faces"][face_index]))])
            face_item.setData(0, Qt.ItemDataRole.UserRole, ["face", face_index])
            faces_group.addChild(face_item)
            mesh_item.setExpanded(True); faces_group.setExpanded(True)
        sets = QTreeWidgetItem([f"명명된 영역 · {len(mesh['sets'])}"]); model.addChild(sets)
        for name, faces in mesh["sets"].items():
            item = QTreeWidgetItem([f"{name} · {len(faces)}면"])
            item.setData(0, Qt.ItemDataRole.UserRole, ["set", name]); sets.addChild(item)
        material = QTreeWidgetItem([f"재료 · {d['material']['name']}"])
        material.setData(0, Qt.ItemDataRole.UserRole, ["material", 0]); self.tree.addTopLevelItem(material)
        condition = QTreeWidgetItem([f"조건 · {d['condition']['name']}"])
        condition.setData(0, Qt.ItemDataRole.UserRole, ["condition", 0]); self.tree.addTopLevelItem(condition)
        mp = QTreeWidgetItem(["재료점 이력"]); mp.setData(0, Qt.ItemDataRole.UserRole, ["mp", 0]); self.tree.addTopLevelItem(mp)
        pde = QTreeWidgetItem(["PDE 식·약형식"]); pde.setData(0, Qt.ItemDataRole.UserRole, ["pde", 0]); self.tree.addTopLevelItem(pde)
        self.tree.addTopLevelItem(QTreeWidgetItem(["진단"])); dataset.setExpanded(True); model.setExpanded(True); sets.setExpanded(True); interval_root.setExpanded(True)
        if d.get("candidate"):
            candidate_item = QTreeWidgetItem([f"후보 · {d['candidate'].get('id', '외부')}"])
            candidate_item.setData(0, Qt.ItemDataRole.UserRole, ["candidate", 0])
            self.tree.addTopLevelItem(candidate_item)
        if selection and selection[0] != "point":
            def find(item):
                if item.data(0, Qt.ItemDataRole.UserRole) == selection: return item
                for child_index in range(item.childCount()):
                    found = find(item.child(child_index))
                    if found: return found
                return None
            for top_index in range(self.tree.topLevelItemCount()):
                found = find(self.tree.topLevelItem(top_index))
                if found:
                    self.tree.setCurrentItem(found)
                    if selection[0] == "face": self.tree.scrollToItem(found)
                    break
        demo_note = " · 시연 모델 · 후보 미적용" if d.get("candidate") else ""
        self.curve_title.setText(f"{d['source']}{demo_note}   ·   {d['x_name']} [{d['x_unit']}] → {d['y_name']} [{d['y_unit']}]")
        self.x_name.setText(d["x_name"]); self.x_unit.setText(d["x_unit"])
        self.y_name.setText(d["y_name"]); self.y_unit.setText(d["y_unit"])
        self.points.setHorizontalHeaderLabels([f"{d['x_name']} [{d['x_unit']}]", f"{d['y_name']} [{d['y_unit']}]"])
        self.points.setRowCount(len(d["points"]))
        for i, point in enumerate(d["points"]):
            for col, value in enumerate(point): self.points.setItem(i, col, _table_item(value, True))
        layout = self.chart.parentWidget().layout()
        new = _chart([(d["source"], d["points"])], f"{d['x_name']} [{d['x_unit']}]", f"{d['y_name']} [{d['y_unit']}]")
        new.scene().sigMouseClicked.connect(lambda event, plot=new: self._plot_clicked(event, plot))
        if selection and selection[0] == "point" and selection[1] < len(d["points"]):
            x, y = d["points"][selection[1]]
            new.plot([float(x)], [float(y)], pen=None, symbol="o", symbolSize=12,
                     symbolBrush=pg.mkBrush("#e0792d"), symbolPen=pg.mkPen("#803500"))
            self.points.selectRow(selection[1])
        layout.replaceWidget(self.chart, new); self.chart.deleteLater(); self.chart = new
        self._draw_mesh()
        self.mesh_label.setText(f"{mesh['source']}   ·   {len(mesh['faces'])}면 / {len(mesh['sets'])}영역")
        history = d["material_point"]["history"]
        self.history.setRowCount(len(history))
        for row, values in enumerate(history):
            for col, value in enumerate(values): self.history.setItem(row, col, _table_item(value, True))
        self.equation.setText(d["pde"]["equation"]); self.weak_form.setPlainText(d["pde"]["weak_form"])
        self.pde_region.clear(); self.pde_region.addItems(["전체 메시", *mesh["sets"].keys()]); self.pde_region.setCurrentText(d["pde"]["region"])
        self.bc_expression.setText(d["pde"]["bc_expression"])
        self.cond_target.clear(); self.cond_target.addItems(["곡선", *mesh["sets"].keys()])
        target = d["condition"].get("target", "curve")
        self.cond_target.setCurrentText(target[4:] if target.startswith("set:") else "곡선")
        if d.get("candidate"):
            candidate = d["candidate"]; units = d.get("parameter_units", {})
            self.candidate_table.setRowCount(len(units))
            for row, (name, unit) in enumerate(units.items()):
                for col, value in enumerate((name, candidate.get(name, "—"), unit)):
                    self.candidate_table.setItem(row, col, _table_item(value))
            study = d.get("source_study", {})
            mode = "저장된 버전" if study.get("mode") == "saved_revision" else "로컬 스냅샷"
            self.candidate_source.setText(f"원본 연구 ID: {study.get('id') or '미지정'}\n출처: {mode}\n버전: {study.get('revision') if study.get('revision') is not None else '고정하지 않음'}")
        self._show_selection()
        self._loading = False

    def _draw_mesh(self):
        self.scene.clear(); mesh = self.data["mesh"]
        vertices, faces = mesh["vertices"], mesh["faces"]
        selected = self.data.get("selection")
        if not faces:
            self.scene.addText("메시가 없습니다. OBJ 파일을 가져오세요."); return
        box = [v[0] for v in vertices], [v[1] for v in vertices]
        width = max(box[0]) - min(box[0]) or 1; height = max(box[1]) - min(box[1]) or 1
        scale = min(600 / width, 330 / height)
        origin_x, origin_y = min(box[0]), max(box[1])
        def point(vertex_id):
            vertex = vertices[vertex_id - 1]
            return QPointF((vertex[0] - origin_x) * scale, (origin_y - vertex[1]) * scale)
        sets = mesh.get("sets", {})
        boundary_map = self.data["bc_by_set"]
        fixed = set(sets.get("왼쪽 고정", [])) if boundary_map.get("왼쪽 고정", {}).get("type") == "고정" else set()
        loaded = set(sets.get("오른쪽 하중", [])) if boundary_map.get("오른쪽 하중", {}).get("type") == "하중" else set()
        selected_set_faces = set(sets.get(selected[1], [])) if selected and selected[0] == "set" else set()
        for index, face in enumerate(faces[:3000]):
            try: polygon = QPolygonF([point(vertex_id) for vertex_id in face])
            except IndexError: continue
            assignment = self.data["face_assignments"].get(str(index), {})
            boundary = assignment.get("bc")
            if boundary == "고정" or index in fixed: fill = QColor("#d9e8f6")
            elif boundary == "하중" or index in loaded: fill = QColor("#ffe3c7")
            else: fill = QColor("#f7f9fb")
            emphasized = selected == ["face", index] or index in selected_set_faces
            pen = QPen(QColor("#125b9a") if emphasized else QColor("#8da3b4"), 2.6 if emphasized else .9)
            item = self.scene.addPolygon(polygon, pen, QBrush(fill)); item.setData(0, ["face", index])
            item.setToolTip(f"면 F{index + 1:03d} · 노드 " + ", ".join(map(str, face)))
        if fixed:
            left = self.scene.addText("고정  u=0"); left.setDefaultTextColor(QColor("#145b9e")); left.setPos(-10, -34)
        if loaded:
            bc = boundary_map["오른쪽 하중"]
            right = self.scene.addText(f"→ 하중 {bc['value']:g} {bc['unit']}")
            right.setDefaultTextColor(QColor("#c05d11")); right.setPos(width * scale - 90, -34)
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-25, -30, 25, 25))
        # Keep scene coordinates at a fixed pixel scale. fitInView on a hidden
        # tab uses its temporary viewport size and makes the mesh jump on click.
        self.mesh_view.resetTransform()

    def eventFilter(self, obj, event):
        if hasattr(self, "mesh_view") and obj is self.mesh_view.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            item = self.mesh_view.itemAt(event.position().toPoint())
            if item and isinstance(item.data(0), list) and item.data(0)[0] == "face":
                self._select(item.data(0)); self.tabs.setCurrentIndex(1); return True
        return super().eventFilter(obj, event)

    def _plot_clicked(self, event, plot):
        if not plot.getPlotItem().sceneBoundingRect().contains(event.scenePos()): return
        point = plot.getPlotItem().vb.mapSceneToView(event.scenePos())
        points = self.data["points"]
        if not points: return
        index = min(range(len(points)), key=lambda i: abs(points[i][0] - point.x()) + abs(points[i][1] - point.y()))
        self._select(["point", index]); self.tabs.setCurrentIndex(0)

    def _select(self, selection):
        if self._loading or self.data.get("selection") == selection: return
        before = self.document(); self.data["selection"] = selection; self._dirty = True
        self.refresh(); self._changed("대상 선택", before)

    def _tree_selected(self):
        if self._loading: return
        item = self.tree.currentItem(); selection = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if selection:
            self._select(selection)
            if selection[0] in ("mesh", "set", "face"): self.tabs.setCurrentIndex(1)
            elif selection[0] == "mp": self.tabs.setCurrentIndex(2)
            elif selection[0] == "pde": self.tabs.setCurrentIndex(3)
            elif selection[0] in ("point", "interval", "channel"): self.tabs.setCurrentIndex(0)

    def _point_selected(self):
        if not self._loading and self.points.currentRow() >= 0: self._select(["point", self.points.currentRow()])

    def _show_selection(self):
        selection = self.data.get("selection")
        d = self.data
        if not selection:
            self.inspector.setCurrentIndex(0)
            candidate_note = "\n\n전달 후보가 있습니다. 기본 판·곡선은 시연 모델이며 후보 값은 아직 적용되지 않았습니다." if d.get("candidate") else ""
            self.overview.setText(f"데이터: {len(d['points'])}점\n메시: {len(d['mesh']['faces'])}면\n영역: {len(d['mesh']['sets'])}개\n\n트리·표·메시에서 대상을 선택하세요.{candidate_note}")
            return
        kind, key = selection
        if kind == "point" and 0 <= key < len(d["points"]):
            self.inspector.setCurrentIndex(1)
            self.point_x.setValue(d["points"][key][0]); self.point_y.setValue(d["points"][key][1])
        elif kind == "interval" and 0 <= key < len(d["intervals"]):
            self.inspector.setCurrentIndex(2); interval = d["intervals"][key]
            self.interval_a.setValue(interval[0]); self.interval_b.setValue(interval[1]); self.interval_weight.setValue(interval[2])
        elif kind == "face" and 0 <= key < len(d["mesh"]["faces"]):
            self.inspector.setCurrentIndex(3); self.face_id.setText(f"F{key + 1:03d}")
            assigned = d["face_assignments"].get(str(key), {})
            self.face_material.setCurrentText(assigned.get("material", "기본 재료"))
            self.face_bc.setCurrentText(assigned.get("bc", "영역 경계 따름"))
        elif kind == "set" and key in d["mesh"]["sets"]:
            self.inspector.setCurrentIndex(4); self.set_name.setText(f"{key} · {len(d['mesh']['sets'][key])}면")
            bc = d["bc_by_set"].get(key, {"type": "자유", "value": 0, "unit": "—"})
            self.set_bc.setCurrentText(bc["type"]); self.set_value.setValue(bc["value"]); self.set_unit.setCurrentText(bc["unit"])
        elif kind == "material":
            self.inspector.setCurrentIndex(5); mat = d["material"]
            self.mat_name.setText(mat["name"]); self.law.setCurrentText(mat["law"])
            self.elastic.setValue(mat["E_GPa"]); self.poisson.setValue(mat["poisson"]); self.rho.setValue(mat["rho"])
        elif kind == "condition":
            self.inspector.setCurrentIndex(6); cond = d["condition"]
            self.cond_name.setText(cond["name"]); self.cond_value.setValue(cond["magnitude"]); self.cond_unit.setCurrentText(cond["unit"])
        elif kind == "channel":
            self.inspector.setCurrentIndex(7)
        elif kind == "candidate" and d.get("candidate"):
            self.inspector.setCurrentIndex(8)
        else:
            self.inspector.setCurrentIndex(0)
            if kind == "mp": self.overview.setText(f"구성 법칙: {d['material_point']['law']}\n이력: {len(d['material_point']['history'])}행")
            elif kind == "pde": self.overview.setText(f"식: {d['pde']['equation']}\n영역: {d['pde']['region']}")
            else: self.overview.setText(f"{len(d['mesh']['faces'])}면 / {len(d['mesh']['sets'])}영역")

    def _point_edited(self, row, col):
        if self._loading: return
        item = self.points.item(row, col)
        try:
            value = float(item.text())
            if not math.isfinite(value): raise ValueError()
        except (AttributeError, ValueError):
            self.diagnostic.setText(f"P{row + 1:02d}: 유한한 숫자를 입력하세요."); self.refresh(); return
        if col == 0 and ((row > 0 and value <= self.data["points"][row - 1][0]) or
                         (row + 1 < len(self.data["points"]) and value >= self.data["points"][row + 1][0])):
            self.diagnostic.setText(f"P{row + 1:02d}: X는 앞뒤 점 사이여야 합니다."); self.refresh(); return
        self.mutate("곡선 점 편집", lambda: self.data["points"][row].__setitem__(col, value))

    def _apply_point(self):
        selection = self.data.get("selection")
        if not selection or selection[0] != "point": return
        index = selection[1]; x, y = self.point_x.value(), self.point_y.value()
        points = self.data["points"]
        if (index > 0 and x <= points[index - 1][0]) or (index + 1 < len(points) and x >= points[index + 1][0]):
            self.diagnostic.setText("점 X는 앞뒤 점 사이여야 합니다."); return
        self.mutate("선택 점 속성 적용", lambda: self.data["points"].__setitem__(index, [x, y]))

    def add_interval(self):
        selection = self.data.get("selection")
        index = selection[1] if selection and selection[0] == "point" else self.points.currentRow()
        points = self.data["points"]
        if index < 0 or index >= len(points) - 1:
            self.diagnostic.setText("연속된 두 점 중 첫 점을 선택하세요."); return
        a, b = points[index][0], points[index + 1][0]
        def edit():
            self.data["intervals"].append([a, b, 1.0]); self.data["selection"] = ["interval", len(self.data["intervals"]) - 1]
        self.mutate("구간 정의", edit)

    def _apply_interval(self):
        selection = self.data.get("selection")
        if not selection or selection[0] != "interval": return
        a, b, w = self.interval_a.value(), self.interval_b.value(), self.interval_weight.value()
        if a >= b or w < 0:
            self.diagnostic.setText("구간 시작은 끝보다 작고 가중치는 0 이상이어야 합니다."); return
        self.mutate("구간 속성 적용", lambda: self.data["intervals"].__setitem__(selection[1], [a, b, w]))

    def _delete_interval(self):
        selection = self.data.get("selection")
        if not selection or selection[0] != "interval": return
        def edit():
            self.data["intervals"].pop(selection[1]); self.data["selection"] = None
        self.mutate("구간 삭제", edit)

    def _apply_face(self):
        selection = self.data.get("selection")
        if not selection or selection[0] != "face": return
        index = selection[1]
        assignment = {"material": self.face_material.currentText(), "bc": self.face_bc.currentText()}
        self.mutate("메시 면 배정", lambda: self.data["face_assignments"].__setitem__(str(index), assignment))

    def _apply_channel(self):
        values = {"x_name": self.x_name.text().strip(), "x_unit": self.x_unit.text().strip(),
                  "y_name": self.y_name.text().strip(), "y_unit": self.y_unit.text().strip()}
        if not all(values.values()):
            self.diagnostic.setText("축 이름과 단위를 모두 입력하세요. 미정 단위는 '—'로 표시하세요."); return
        self.mutate("곡선 채널·단위 편집", lambda: self.data.update(values))

    def _apply_set(self):
        selection = self.data.get("selection")
        if not selection or selection[0] != "set": return
        name = selection[1]
        condition = {"type": self.set_bc.currentText(), "value": self.set_value.value(), "unit": self.set_unit.currentText()}
        if condition["type"] == "고정" and (condition["value"] != 0 or condition["unit"] not in ("mm", "—")):
            self.diagnostic.setText("고정 조건은 값 0과 변위 단위 mm로 지정하세요."); return
        if condition["type"] == "하중" and condition["unit"] not in ("N", "kN"):
            self.diagnostic.setText("하중 조건의 단위는 N 또는 kN이어야 합니다."); return
        self.mutate("영역 조건 배정", lambda: self.data["bc_by_set"].__setitem__(name, condition))

    def show_material(self):
        self._select(["material", 0]); self.tabs.setCurrentIndex(2)

    def _apply_material(self):
        name = self.mat_name.text().strip()
        if not name:
            self.diagnostic.setText("재료명을 입력하세요."); return
        material = {"name": name, "law": self.law.currentText(), "E_GPa": self.elastic.value(),
                    "poisson": self.poisson.value(), "rho": self.rho.value()}
        if material["E_GPa"] <= 0 or material["rho"] <= 0:
            self.diagnostic.setText("탄성계수 E와 밀도 ρ는 양수여야 합니다."); return
        def edit():
            self.data["material"] = material
            self.data["material_point"]["law"] = material["law"]
        self.mutate("구성 법칙·재료 적용", edit)

    def _apply_condition(self):
        name = self.cond_name.text().strip()
        if not name:
            self.diagnostic.setText("조건명을 입력하세요."); return
        target_name = self.cond_target.currentText()
        target = f"set:{target_name}" if target_name != "곡선" else "curve"
        condition = {"name": name, "magnitude": self.cond_value.value(), "unit": self.cond_unit.currentText(), "target": target}
        def edit():
            self.data["condition"] = condition
            if target.startswith("set:"):
                self.data["bc_by_set"][target_name] = {"type": "하중", "value": condition["magnitude"], "unit": condition["unit"]}
        self.mutate("하중 조건 적용", edit)

    def _history_edited(self, row, col):
        if self._loading: return
        item = self.history.item(row, col)
        try:
            value = float(item.text())
            if not math.isfinite(value): raise ValueError()
        except (AttributeError, ValueError):
            self.diagnostic.setText(f"이력 {row + 1}행: 유한한 숫자를 입력하세요."); self.refresh(); return
        self.mutate("재료점 이력 편집", lambda: self.data["material_point"]["history"][row].__setitem__(col, value))

    def _add_history(self):
        history = self.data["material_point"]["history"]
        time = history[-1][0] + 1 if history else 0.0
        self.mutate("재료점 이력 행 추가", lambda: history.append([time, 0.0, 0.0]))

    def _remove_history(self):
        row = self.history.currentRow()
        if row >= 0: self.mutate("재료점 이력 행 삭제", lambda: self.data["material_point"]["history"].pop(row))

    def _apply_pde(self):
        equation, weak = self.equation.text().strip(), self.weak_form.toPlainText().strip()
        if not equation or not weak:
            self.diagnostic.setText("지배 방정식과 약형식을 모두 입력하세요."); return
        pde = {"equation": equation, "weak_form": weak, "region": self.pde_region.currentText(), "bc_expression": self.bc_expression.text().strip()}
        self.mutate("PDE 식·약형식 저장", lambda: self.data.__setitem__("pde", pde))

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "곡선 CSV 가져오기", "", "CSV 파일 (*.csv *.txt);;모든 파일 (*)")
        if not path: return
        try: mapped = map_table_file(self, path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "CSV 가져오기 실패", str(exc)); return
        if mapped is None: return
        def edit():
            self.data.update(source=Path(path).name, source_path=path, source_type="csv",
                             points=mapped.points, intervals=[], selection=["channel", 0],
                             x_name=mapped.x_name, y_name=mapped.y_name,
                             x_unit=mapped.x_unit, y_unit=mapped.y_unit,
                             csv_mapping={"delimiter": mapped.delimiter, "header": mapped.has_header,
                                          "x_column": mapped.x_column, "y_column": mapped.y_column})
        self.mutate("CSV 곡선 가져오기", edit); self.tabs.setCurrentIndex(0)

    def import_obj(self):
        path, _ = QFileDialog.getOpenFileName(self, "OBJ 메시 가져오기", "", "OBJ 파일 (*.obj)")
        if not path: return
        try:
            vertices, faces = [], []
            for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
                parts = line.split()
                if parts[:1] == ["v"] and len(parts) >= 4:
                    vertex = [float(parts[1]), float(parts[2]), float(parts[3])]
                    if not all(math.isfinite(value) for value in vertex): raise ValueError("좌표에 NaN/무한대가 있습니다")
                    vertices.append(vertex)
                elif parts[:1] == ["f"] and len(parts) >= 4:
                    face = [int(token.split("/")[0]) for token in parts[1:]]
                    if len(set(face)) < 3: raise ValueError("면마다 서로 다른 절점이 3개 이상 필요합니다")
                    if any(vertex <= 0 for vertex in face): raise ValueError("음수/상대 인덱스 OBJ 면은 지원하지 않습니다")
                    faces.append(face)
            if not vertices or not faces: raise ValueError("정점과 다각형 면이 필요합니다")
            if any(vertex > len(vertices) for face in faces for vertex in face): raise ValueError("면에서 존재하지 않는 정점을 참조합니다")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "OBJ 가져오기 실패", str(exc)); return
        def edit():
            self.data["mesh"] = {"vertices": vertices, "faces": faces, "source": path, "sets": {}}
            self.data["face_assignments"] = {}; self.data["bc_by_set"] = {}; self.data["selection"] = None
        self.mutate("OBJ 메시 가져오기", edit); self.tabs.setCurrentIndex(1)

    def validate(self):
        d = self.data; errors = []
        xs = [point[0] for point in d["points"]]
        if len(xs) < 2 or any(b <= a for a, b in zip(xs, xs[1:])): errors.append("곡선 X는 엄격하게 증가해야 합니다")
        if d["material"]["E_GPa"] <= 0 or not -.99 < d["material"]["poisson"] < .5: errors.append("재료 E와 ν 범위를 확인하세요")
        if d["material"]["rho"] <= 0: errors.append("재료 밀도 ρ는 양수여야 합니다")
        if any(not d[key].strip() for key in ("x_name", "x_unit", "y_name", "y_unit")): errors.append("곡선 축 이름·단위를 확인하세요")
        if not d["mesh"]["faces"]: errors.append("메시 면이 없습니다")
        for i, interval in enumerate(d["intervals"], 1):
            if interval[0] >= interval[1] or interval[2] < 0: errors.append(f"구간 I{i:02d}의 범위/가중치 오류")
        times = [row[0] for row in d["material_point"]["history"]]
        if any(b <= a for a, b in zip(times, times[1:])): errors.append("재료점 시간은 증가해야 합니다")
        if not d["pde"]["equation"] or not d["pde"]["weak_form"]: errors.append("PDE 식과 약형식을 입력하세요")
        if d["pde"]["region"] not in ("전체 메시", *d["mesh"]["sets"].keys()): errors.append("PDE 적용 영역을 다시 선택하세요")
        if d["condition"].get("target", "curve").startswith("set:") and d["condition"]["target"][4:] not in d["mesh"]["sets"]:
            errors.append("하중 조건의 대상 영역이 없습니다")
        self.diagnostic.setText("검증 통과 · 시연 실행기에 전달할 수 있습니다." if not errors else "입력 오류\n" + "\n".join(errors))
        if errors: self.inspector.setCurrentIndex(0)
        return not errors

    def send_runner(self):
        if not self.validate(): return
        saved_ref = bool(self._doc.get("path")) and not self._dirty and self._doc.get("revision", 0) > 0
        source_ref = {"id": self._doc.get("id"), "path": self._doc.get("path") if saved_ref else None,
                      "revision": self._doc.get("revision") if saved_ref else None,
                      "mode": "saved_revision" if saved_ref else "local_snapshot"}
        self._open_tool("runner", {"kind": "runner", "name": f"{self._doc.get('name', '전처리')} 케이스",
                                   "data": {"case_name": self._doc.get("name", "케이스 A"),
                                            "source_revision": source_ref["revision"], "source_ref": source_ref,
                                            "input_pre": self.document()}})
