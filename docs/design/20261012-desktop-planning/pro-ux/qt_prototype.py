"""Independent native Qt desktop planning prototype. No production execution.

Run: py -3.13 qt_prototype.py --tool cad
Only PySide6 already present on the user's machine is required.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import sys
from pathlib import Path

try:
    from PySide6.QtCore import Qt, QTimer, QSize, QItemSelection, QItemSelectionModel
    from PySide6.QtGui import QAction, QKeySequence, QFont, QFontDatabase, QFontInfo, QColor, QTextCursor
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QDockWidget, QVBoxLayout, QHBoxLayout,
        QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem, QTableWidgetItem,
        QLabel, QComboBox, QPushButton, QToolBar, QFileDialog, QDialog,
        QDialogButtonBox, QMessageBox, QLineEdit, QPlainTextEdit, QFormLayout,
        QDoubleSpinBox, QSpinBox, QCheckBox, QSlider, QListWidget, QListWidgetItem,
        QAbstractItemView, QMenu, QHeaderView, QStackedWidget, QSizePolicy,
    )
except ImportError:
    raise SystemExit("PySide6 is not available in this interpreter. Use the existing Windows Python 3.13 / PySide6 6.9.1 environment. Nothing was installed.")

from prototype_state import (ReviewSession, ReviewError, TOOL_NAMES, METHODS, HERE, clone, digest,
                             RESPONSE_ROLES, EVALUATORS, VARIABLE_BINDINGS, METHOD_INPUTS, method_sheet, binding_ids)
from qt_widgets import make_table, CurveView, EngineeringView, NodeView, BLUE, TEAL, ORANGE, RED

STYLE = """
QWidget { color: #263442; font-size: 10pt; }
QMainWindow, QDialog { background: #f3f5f7; }
QToolBar { background: #f7f8fa; border: 0; border-bottom: 1px solid #cad3dc; spacing: 5px; padding: 3px; }
QToolButton { padding: 4px 8px; }
QDockWidget::title { background: #e7ecf1; padding: 5px 8px; text-align: left; }
QTableView, QTreeView, QListView { background: white; alternate-background-color: #f6f8fa; gridline-color: #e0e6eb; selection-background-color: #dcebf6; selection-color: #173f5b; }
QHeaderView::section { background: #edf1f5; padding: 5px; border: 0; border-right: 1px solid #d7dfe6; border-bottom: 1px solid #d7dfe6; }
QPushButton { min-height: 23px; padding: 3px 10px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { min-height: 24px; background: white; }
QTabWidget::pane { border: 1px solid #cbd5dd; }
QTabBar::tab { padding: 7px 16px; background: #e9eef3; }
QTabBar::tab:selected { background: white; border-bottom: 2px solid #286998; }
QSplitter::handle { background: #d7dfe6; }
QStatusBar { background: #eaf0f5; border-top: 1px solid #cbd5dd; }
QPlainTextEdit { background: white; }
"""


def configure_application_fonts(app):
    """Use installed fonts in both native and offscreen entry points.

    Windows offscreen may not discover its installed fonts automatically. Read
    those existing files into this process only; never install or copy fonts.
    """
    cached = app.property("caelabFontPolicy")
    if cached is not None:
        return cached
    loaded = []
    if sys.platform == "win32":
        system_root = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or "C:/Windows"
        for filename in ("segoeui.ttf", "malgun.ttf"):
            path = Path(system_root) / "Fonts" / filename
            if path.is_file() and QFontDatabase.addApplicationFont(str(path)) >= 0:
                loaded.append(filename)
    available = set(QFontDatabase.families())
    system = QFontInfo(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)).family()
    preferred = (["Segoe UI", "Malgun Gothic", system] if sys.platform == "win32"
                 else [system, "Noto Sans", "DejaVu Sans", "Liberation Sans"])
    korean = QFontDatabase.families(QFontDatabase.WritingSystem.Korean)
    if korean:
        preferred.append("Malgun Gothic" if "Malgun Gothic" in korean else korean[0])
    families = list(dict.fromkeys(name for name in preferred if name in available))
    font = QFont(app.font())
    if families:
        font.setFamilies(families)
        # Also resolve legacy explicit family requests without assuming that a
        # font from another OS is installed (including older review wrappers).
        for alias in ("DejaVu Sans", "Segoe UI", "Malgun Gothic"):
            if alias not in available:
                QFont.insertSubstitutions(alias, families)
    font.setPointSize(10)
    app.setFont(font)
    policy = {"platform": sys.platform, "ui_families": font.families(),
              "resolved_family": QFontInfo(font).family(), "point_size": 10,
              "hangul_family_available": bool(korean), "loaded_existing_files": loaded}
    app.setProperty("caelabFontPolicy", policy)
    return policy


def box(*widgets, horizontal=False, margins=0):
    w = QWidget()
    layout = QHBoxLayout(w) if horizontal else QVBoxLayout(w)
    layout.setContentsMargins(margins, margins, margins, margins)
    layout.setSpacing(5)
    if horizontal:
        w.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
    for child in widgets:
        layout.addWidget(child)
    return w


def button(label, callback):
    b = QPushButton(label)
    def invoke(checked=False):
        try:return callback()
        except (ReviewError,OSError,ValueError,KeyError) as error:
            parent=b.window()
            if hasattr(parent,"update_title"):parent.update_title(str(error))
            QMessageBox.warning(parent,"Action needs attention",str(error))
    b.clicked.connect(invoke)
    return b


def text_dialog(parent, title, text, width=820):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(width, 580)
    view = QPlainTextEdit(text)
    view.setReadOnly(True)
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(10)
    view.setFont(font)
    close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    close.rejected.connect(dialog.reject)
    layout = QVBoxLayout(dialog)
    layout.addWidget(view)
    layout.addWidget(close)
    dialog.exec()


def number(text):
    result = float(text)
    if not math.isfinite(result):
        raise ValueError("A finite number is required.")
    return result


def numeric_draft(text):
    try:return number(text)
    except ValueError:return text


def fill_table(table, rows, editable=()):
    """Replace rows without treating a refresh as user input."""
    blocked = table.blockSignals(True)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c in range(table.columnCount()):
            value = row[c] if c < len(row) else ""
            item = QTableWidgetItem()
            item.setData(Qt.ItemDataRole.DisplayRole, "" if value is None else value)
            if c not in editable:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(r, c, item)
    table.blockSignals(blocked)


def mark_invalid(item, invalid):
    table = item.tableWidget()
    blocked = table.blockSignals(True)
    item.setBackground(QColor("#fce8e6" if invalid else "white"))
    table.blockSignals(blocked)


class ToolWindow(QMainWindow):
    def __init__(self, hub, key):
        super().__init__()
        self.hub, self.session, self.key = hub, hub.session, key
        self.resize(1440, 900)
        self.setMinimumSize(900, 600)
        self.setDockOptions(QMainWindow.DockOption.AllowNestedDocks |
                            QMainWindow.DockOption.AllowTabbedDocks |
                            QMainWindow.DockOption.AnimatedDocks)
        self._building = True
        self.docks = []
        self.toolbar = QToolBar("Commands", self)
        self.toolbar.setObjectName("commands")
        self.toolbar.setMovable(True)
        self.toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(self.toolbar)
        self.status = QLabel()
        self.statusBar().addWidget(self.status, 1)
        self.statusBar().addPermanentWidget(QLabel("시안 · 합성 데이터"))
        self.make_menus()
        self.build()
        self._building = False
        self.update_title()
        QTimer.singleShot(0, self.remember_layout)

    @property
    def document(self):
        return self.session.doc(self.key)

    @property
    def data(self):
        return self.document["draft"]

    def make_menus(self):
        file_menu = self.menuBar().addMenu("&File")
        new = file_menu.addMenu("New window")
        for key, title in TOOL_NAMES.items():
            action = new.addAction(title if key not in ("thermal","thermoelastic") else key.title())
            action.triggered.connect(lambda checked=False, k=key: self.hub.open(k))
        self.action(file_menu, "&Open…", self.open_file, "Ctrl+O")
        self.action(file_menu, "&Save", self.save, "Ctrl+S")
        self.action(file_menu, "Save &as…", lambda: self.save(True), "Ctrl+Shift+S")
        self.action(file_menu, "Save review session…", self.save_session, "Ctrl+Alt+S")
        file_menu.addSeparator()
        self.action(file_menu, "&Close", self.close, "Ctrl+W")
        edit = self.menuBar().addMenu("&Edit")
        self.undo_action = self.action(edit, "Undo", lambda: self.undo(False), "Ctrl+Z")
        self.redo_action = self.action(edit, "Redo", lambda: self.undo(True), "Ctrl+Y")
        self.view_menu = self.menuBar().addMenu("&View")
        self.action(self.view_menu, "Restore layout", self.restore_layout)
        self.action(self.view_menu, "History and sources…", self.history, "Ctrl+H")
        tools = self.menuBar().addMenu("&Window")
        for key in ("cad","simulation","runner","post","numerical","expert","study","data","material","pde","evaluation","workbench"):
            self.action(tools, TOOL_NAMES[key], lambda k=key:self.hub.open(k))
        self.review_menu = self.menuBar().addMenu("&Review")
        self.action(self.review_menu, "Runtime and capability…", self.capabilities)
        self.action(self.review_menu, "Open saved Material repair scenario…", self.open_repair_scenario)
        self.action(self.review_menu, "Save all review drafts…", self.save_session)
        self.action(self.toolbar, "Open", self.open_file)
        self.action(self.toolbar, "Save", self.save)

    def action(self, target, title, callback, shortcut=None):
        action = QAction(title, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(lambda checked=False: self.guard(callback))
        target.addAction(action)
        return action

    def guard(self, function):
        try:
            return function()
        except (ReviewError, OSError, ValueError, KeyError) as error:
            self.status.setText(str(error))
            QMessageBox.warning(self, "Action needs attention", str(error))
            return False

    def add_dock(self, title, widget, area=Qt.DockWidgetArea.LeftDockWidgetArea, minimum=180):
        dock = QDockWidget(title, self)
        dock.setObjectName(self.key + "-" + title)
        dock.setMinimumWidth(minimum)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        self.docks.append(dock)
        self.view_menu.addAction(dock.toggleViewAction())
        return dock

    def remember_layout(self):
        self.default_layout = self.saveState()
        view=self.document.get("view",{})
        if view:
            from PySide6.QtCore import QByteArray
            self.restoreState(QByteArray.fromBase64(view.get("docks", "").encode()))
            for splitter,sizes in zip(self.findChildren(QSplitter),view.get("splits",[])):splitter.setSizes(sizes)
            for tabs,index in zip(self.findChildren(QTabWidget),view.get("tabs",[])):
                if 0<=index<tabs.count():tabs.setCurrentIndex(index)
            if view.get("size"):self.resize(*view["size"])

    def restore_layout(self):
        if hasattr(self,"default_layout"):
            self.restoreState(self.default_layout)

    def build(self):
        raise NotImplementedError

    def refresh(self):
        self.update_title()

    def update_title(self, message=None):
        doc = self.document
        family = TOOL_NAMES.get(self.key, doc["owner"])
        name = Path(doc["file"]).name if doc["file"] else doc["name"]
        self.setWindowTitle(name + (" *" if doc["dirty"] else "") + " — " + family)
        self.status.setText(message or ("Unsaved changes" if doc["dirty"] else "Ready"))
        self.undo_action.setEnabled(bool(doc["undo"]))
        self.redo_action.setEnabled(bool(doc["redo"]))
        self.undo_action.setText("Undo " + (doc["undo"][-1]["label"] if doc["undo"] else ""))
        self.redo_action.setText("Redo " + (doc["redo"][-1]["label"] if doc["redo"] else ""))

    def capture_view(self):
        self.document["view"]={"docks":bytes(self.saveState().toBase64()).decode(),
            "splits":[splitter.sizes() for splitter in self.findChildren(QSplitter)],
            "tabs":[tabs.currentIndex() for tabs in self.findChildren(QTabWidget)],"size":[self.width(),self.height()]}

    def save(self, force_path=False):
        self.flush_editor();self.capture_view()
        path = self.document["file"]
        if force_path or not path:
            chosen, _ = QFileDialog.getSaveFileName(self, "Save " + self.document["name"],
                str(self.session.workspace / (self.document["name"] + ".json")),
                "Review document (*.json);;All files (*)")
            if not chosen:
                return False
            path = chosen
        self.session.save_document(self.key, path)
        self.update_title("Saved")
        return True

    def flush_editor(self):
        focus = QApplication.focusWidget()
        if focus and focus.window() is self:
            focus.clearFocus()

    def raw(self, locator, value):
        return self.document["buffers"].get(locator, value)

    def open_file(self):
        path,_ = QFileDialog.getOpenFileName(self,"Open review document or session",
                  str(self.session.workspace),"Review JSON (*.json);;All files (*)")
        if not path:
            return
        raw=json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("kind")=="session":
            self.hub.open_session(path)
        else:
            key=self.session.open_document(path)
            self.hub.open(key)

    def save_session(self):
        path,_=QFileDialog.getSaveFileName(self,"Save review session",
                   str(self.session.workspace/"Desktop review.json"),"Review session (*.json)")
        if path:
            self.session.selected["tool"]=self.key
            for window in self.hub.windows.values():window.flush_editor();window.capture_view()
            self.session.save_session(path)
            self.update_title("Review session saved; owner save states are preserved")
            return True
        return False

    def undo(self, redo):
        self.session.history_step(self.key, redo)
        self.refresh()

    def history(self):
        doc=self.document
        raw={"document":doc["id"],"owner":doc["owner"],"saved_revision":doc["revision"],
             "draft_generation":doc["generation"],"file":doc["file"],
             "history":[{"revision":h["revision"],"source":h["source"]} for h in doc["history"]],
             "sources":doc["draft"].get("sources",doc["draft"].get("model_ref",{})),
             "qualification":"UNKNOWN","release":"NOT_RELEASED",
             "preserved_F05":{"value":3.32295e-6,"tolerance":1e-6,"verdict":"FAIL"}}
        text_dialog(self,"History and sources",json.dumps(raw,ensure_ascii=False,indent=2))

    def capabilities(self):
        text_dialog(self,"Runtime and capability",
            "Qt interaction prototype\n\n"
            "Native FreeCAD / ParaView: illustration only; not launched.\n"
            "Solver / optimizer / provider: not connected; not executed.\n"
            "Local tables, selections, draft edits and JSON saves are real prototype operations.\n"
            "Backend absence preserves editable drafts and retained evidence.\n"
            "General weak form, ODE, contact/failure, coupling, inverse, DOE/UQ,\n"
            "sensitivity, surrogate, MOO/MDO and remote remain design scope.\n\n"
            "Product adapters and runtime admission must be checked by Codex on Windows.\n"
            "MoAI state is not accessed by this prototype.")

    def open_repair_scenario(self):
        if self.document["dirty"]:
            raise ReviewError("Save the current work before opening another scenario.")
        answer=QMessageBox.question(self,"Open review scenario",
            "Open a separate synthetic Material r19 recovery session? Current session is retained.")
        if answer==QMessageBox.StandardButton.Yes:
            other=ReviewSession()
            other.material_repair_scenario()
            self.hub.open_other(other,"material")

    def retain_input(self,locator,value):
        buffers=clone(self.document["buffers"]);buffers[locator]=value
        self.session.change(self.key,self.data,"Edit unfinished "+locator,buffers=buffers)

    def edit_number(self, field, item, nested=None):
        text=item.text()
        doc=self.document
        locator=(nested+"."+field) if nested else field
        try:
            value=number(text)
        except ValueError:
            self.retain_input(locator,text)
            mark_invalid(item, True)
            self.update_title("Invalid input retained: "+locator)
            return
        buffers=clone(doc["buffers"]);buffers.pop(locator,None)
        payload=clone(self.data)
        if nested:
            payload.setdefault(nested,{})[field]=value
        else:
            payload[field]=value
        self.session.change(self.key,payload,"Edit "+locator,buffers=buffers)
        mark_invalid(item, False)
        self.update_title()

    def submit_review(self):
        self.flush_editor()
        if self.session.diagnostics(self.key):
            self.input_diagnostics()
            return
        frozen=self.session.freeze(self.key)
        dialog=QDialog(self); dialog.setWindowTitle("Run analysis" if self.document["owner"]=="Simulation" else "Run study" if self.document["owner"]=="Numerical" else "Review evaluation");dialog.resize(760,470)
        layout=QVBoxLayout(dialog);layout.addWidget(QLabel("Planning prototype / synthetic input / no execution"))
        d=self.data;owner=self.document["owner"]
        if owner=="Simulation":
            rows=[["Model",self.document["name"]],["Solver",d.get("backend","")],["Analysis",d["family"]]]
            rows += [["Step",step["name"]+" / "+str(step["duration"])+" s"] for step in d.get("steps",[{"name":d.get("step","Stationary"),"duration":d.get("duration",0)}])]
            if "force" in d:rows.append(["Load",str(d["force"])+" "+d.get("force_unit","N")])
            rows.append(["Output",", ".join(k for k,v in d.get("outputs",{}).items() if v) or d.get("required_response",d.get("field","Selected fields"))])
        elif owner=="Numerical":
            rows=[["Study",self.document["name"]],["Method",d["method"]],["Evaluator",d["evaluator"]],["Variables",", ".join(v["owner"]+"."+v["field"] for v in d["variables"])],["Responses",", ".join(r["name"]+" / "+r["role"] for r in d["responses"])],["Evaluation budget",d["budget"]]]
        elif owner=="Material":rows=[["Material",self.document["name"]],["Law",d["law"]],["Load case",d["protocol"]],["Train",d["train"]],["Holdout",d["holdout"]]]
        elif owner=="PDE":rows=[["Field",d["field"]],["Domain",d["domain"]],["Equation",d["equation"]],["Study",d.get("study_type","Stationary")]]
        else:rows=[["Model",self.document["name"]],["Stages",", ".join(stage["stage"] for stage in d.get("stages",[]))],["Transfer",d.get("transfer","")]]
        if "included_count" in frozen:rows.append(["Training observations",frozen["included_count"]])
        layout.addWidget(make_table(["Input","Value"],rows))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        create=buttons.addButton("Create review attempt",QDialogButtonBox.ButtonRole.AcceptRole)
        create.clicked.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            job=self.session.create_attempt(frozen["id"])
            self.session.selected["job"]=job["id"]
            self.hub.open("runner").refresh()

    def input_diagnostics(self):
        errors=self.session.diagnostics(self.key)
        if not errors:
            self.update_title("Required inputs checked")
            return True
        dialog=QDialog(self);dialog.setWindowTitle("Check input");dialog.resize(800,370)
        layout=QVBoxLayout(dialog);table=make_table(["Location","Correction"],errors)
        layout.addWidget(table)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        edit=buttons.addButton("Edit selected",QDialogButtonBox.ButtonRole.AcceptRole)
        edit.clicked.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        table.selectRow(0)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            row=max(0,table.currentRow());field=errors[row][0]
            self.focus_problem(field)
        self.update_title("Correct required inputs before freeze")
        return False

    def focus_problem(self,field):
        if self.document["owner"]=="native_pre":
            mode="Contact" if "contact" in field else "Mesh" if "mesh" in field else "Conditions" if "conditions" in field else "Features"
            self.mode.setCurrentText(mode)
            if field in ("thickness","width","height"):
                self.props.setCurrentCell(("thickness","width","height").index(field),1);self.props.setFocus()
        elif self.document["owner"]=="Numerical":
            if field=="method_inputs":self.top_tabs.setCurrentIndex(3);self.method_detail.setFocus();return
            if field in ("method","budget","seed") or field.startswith("method."):self.top_tabs.setCurrentIndex(2);self.method_table.setFocus();return
            if field=="evaluator":self.evaluator.setFocus()
            else:
                index=1 if field=="responses" or any(r["name"]==field for r in self.data["responses"]) else 0
                self.top_tabs.setCurrentIndex(index)
                table=self.responses if index else self.variables
                table.setFocus()
        elif self.document["owner"]=="Simulation" and field in self.numeric_fields:
            self.pages.setCurrentIndex(1)
            self.table.setCurrentCell(self.numeric_fields.index(field),1);self.table.setFocus()
        elif self.document["owner"]=="Simulation":
            page=1 if field.startswith("steps") else 2 if "condition" in field else 5 if "failure" in field else 1
            self.pages.setCurrentIndex(page)
            if field.startswith("steps."):
                index=int(field.split(".")[1]);self.steps.selectRow(index);self.table.setFocus()
        elif self.document["owner"]=="PDE":
            if field=="boundary":self.pages.setCurrentIndex(4)
            elif field=="field":self.pages.setCurrentIndex(2);self.field_name.setFocus()
            elif field in ("mesh","width","height"):
                self.pages.setCurrentIndex(1 if field=="mesh" else 0)
            else:self.pages.setCurrentIndex(3);self.equation.setFocus()
        elif self.document["owner"]=="Material":self.coeff.setFocus()

    def closeEvent(self,event):
        if self.document["dirty"]:
            choice=QMessageBox(self)
            choice.setWindowTitle("Unsaved "+self.document["name"])
            choice.setText("Save this document before closing? Running jobs are not cancelled.")
            save=choice.addButton("Save",QMessageBox.ButtonRole.AcceptRole)
            keep=choice.addButton("Save review recovery…",QMessageBox.ButtonRole.ActionRole)
            discard=choice.addButton("Discard draft",QMessageBox.ButtonRole.DestructiveRole)
            choice.addButton(QMessageBox.StandardButton.Cancel)
            choice.exec()
            clicked=choice.clickedButton()
            if clicked==save:
                if not self.guard(self.save): event.ignore(); return
            elif clicked==keep:
                if not self.guard(self.save_session): event.ignore(); return
            elif clicked==discard:
                self.document["draft"]=clone(self.document["saved"])
                self.document["dirty"]=False; self.document["buffers"].clear()
            else:
                event.ignore(); return
        event.accept()
        self.hub.windows.pop(self.key,None)


class CADWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Create…",self.create_geometry)
        self.action(self.toolbar,"Import…",self.import_geometry)
        self.mode=QComboBox();self.mode.addItems(["Sketch","Features","Assembly","Motion","Mesh","Conditions","Contact"])
        self.mode.setCurrentText("Contact");self.toolbar.addWidget(self.mode)
        self.action(self.toolbar,"Check",self.check)
        self.action(self.toolbar,"Run analysis…",self.to_simulation)
        self.action(self.toolbar,"Use in Simulation",self.to_simulation)
        self.viewer=EngineeringView("cad");self.setCentralWidget(self.viewer)
        self.tree=QTreeWidget();self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self.tree_selected)
        self.props=make_table(["Property","Value","Unit"],[],editable=(1,),select_rows=False)
        self.props.setObjectName("cadDimensions");self.props.itemChanged.connect(self.property_changed)
        self.task_pages=QStackedWidget()
        self.face_name=QLineEdit("Clamp/Pad/Face6");self.face_name.setReadOnly(True)
        self.constraints=make_table(["Constraint","Value","Unit"],[],editable=(1,),select_rows=False)
        self.constraints.itemChanged.connect(self.constraint_changed)
        self.sketch_lines=make_table(["Line","x1","y1","x2","y2"],[],editable=(1,2,3,4),select_rows=False)
        self.sketch_lines.itemChanged.connect(self.sketch_line_changed)
        self.task_pages.addWidget(box(QLabel("Rectangle sketch"),self.constraints,
            box(button("Draw line",self.draw_line),button("Remove line",self.remove_line),horizontal=True),self.sketch_lines,
            button("Constrain rectangle",self.constrain_sketch),margins=7))
        self.hole=QCheckBox("Through hole");self.hole.toggled.connect(self.hole_changed)
        self.task_pages.addWidget(box(QLabel("Pad / pocket"),self.props,self.hole,
            button("Edit sketch",lambda:self.mode.setCurrentText("Sketch")),margins=7))
        self.instances=QSpinBox();self.instances.setRange(1,4);self.instances.valueChanged.connect(self.assembly_changed)
        self.joint=QComboBox();self.joint.addItems(["Fixed","Revolute","Slider"]);self.joint.currentTextChanged.connect(self.assembly_changed)
        self.part=QComboBox();self.part.addItems(["Clamp","Base"]);self.part.currentTextChanged.connect(self.part_changed)
        form=QFormLayout();form.addRow("Part",self.part);form.addRow("Instances",self.instances);form.addRow("Joint",self.joint)
        fw=QWidget();fw.setLayout(form);self.task_pages.addWidget(box(fw,margins=7))
        self.angle=QDoubleSpinBox();self.angle.setRange(-180,180);self.angle.setSuffix(" deg");self.angle.valueChanged.connect(self.preview_pose)
        self.task_pages.addWidget(box(QLabel("Joint motion"),self.angle,box(button("Use pose",self.use_pose),button("Restore pose",self.restore_pose),horizontal=True),margins=7))
        self.mesh_size=QDoubleSpinBox();self.mesh_size.setRange(.05,50);self.mesh_size.setSuffix(" mm");self.mesh_size.valueChanged.connect(self.mesh_changed)
        self.mesh_type=QComboBox();self.mesh_type.addItems(["Tet4","Tet10","Hex illustration"]);self.mesh_type.currentTextChanged.connect(self.mesh_type_changed)
        self.task_pages.addWidget(box(QLabel("Element size"),self.mesh_size,QLabel("Element type"),self.mesh_type,
            button("Preview mesh",self.rebuild_mesh),button("Inspect poor elements",lambda:self.quality_dock.show()),margins=7))
        self.conditions=make_table(["Condition","Face","Value","Unit"],[])
        self.conditions.itemSelectionChanged.connect(self.condition_selected)
        self.task_pages.addWidget(box(QLabel("Loads and constraints"),self.conditions,
            box(button("Add…",self.condition_dialog),button("Edit…",lambda:self.condition_dialog(True)),
                button("Remove",self.remove_condition),horizontal=True),margins=7))
        self.face_set=QComboBox();self.face_set.addItems(["Set A","Set B"])
        self.contact_table=make_table(["Set","Face"],[])
        self.law=QComboBox();self.law.addItems(["Frictionless","Coulomb","Tie","Cohesive"])
        self.law.currentTextChanged.connect(lambda v:self.change_contact("law",v))
        self.mu=QDoubleSpinBox();self.mu.setRange(0,10);self.mu.setDecimals(3);self.mu.valueChanged.connect(lambda v:self.change_contact("mu",v))
        self.gap=QDoubleSpinBox();self.gap.setRange(-10,10);self.gap.setDecimals(3);self.gap.setSuffix(" mm");self.gap.valueChanged.connect(lambda v:self.change_contact("gap",v))
        form=QFormLayout();form.addRow("Law",self.law);form.addRow("Friction",self.mu);form.addRow("Initial gap",self.gap)
        fw=QWidget();fw.setLayout(form)
        self.contact_active=QCheckBox("Use contact");self.contact_active.toggled.connect(lambda v:self.change_contact("active",v))
        self.task_pages.addWidget(box(self.contact_active,self.contact_table,
            box(self.face_set,button("Add face",self.add_face),button("Remove",self.remove_face),horizontal=True),fw,
            button("Rebind…",lambda:self.guard(self.rebind)),margins=7))
        self.combo=QTabWidget();self.combo.addTab(self.tree,"Model")
        self.combo.addTab(box(self.face_name,self.task_pages),"Tasks");self.combo.setCurrentIndex(1)
        dock=self.add_dock("Combo View",self.combo,minimum=320);self.resizeDocks([dock],[370],Qt.Orientation.Horizontal)
        self.quality=make_table(["Element","Quality","Limit","State"],
            [[314,.19,.25,"Review"],[829,.22,.25,"Review"],[1204,.72,.25,"Within fixture limit"]])
        self.quality.itemSelectionChanged.connect(self.quality_selected)
        self.quality_dock=self.add_dock("Mesh quality",self.quality,Qt.DockWidgetArea.BottomDockWidgetArea);self.quality_dock.hide()
        self.mode.currentTextChanged.connect(self.mode_changed)
        self.viewer.faceSelected.connect(self.face_name.setText)
        self.viewer.sketchLineAdded.connect(self.add_sketch_line)
        self.action(self.review_menu,"Geometry change / unresolved contact",self.break_contact)
        self.action(self.review_menu,"Review contact rebind…",self.rebind)
        self.action(self.review_menu,"Review rebuilt mesh",self.rebuild_mesh)
        self.refresh();self.mode_changed("Contact")

    def mode_changed(self,mode):
        self.task_pages.setCurrentIndex(self.mode.findText(mode));self.combo.setCurrentIndex(1)
        self.quality_dock.setVisible(mode=="Mesh");self.viewer.sketch=mode=="Sketch"
        self.viewer.mesh=mode=="Mesh";self.viewer.update()

    def create_geometry(self):
        dialog=QDialog(self);dialog.setWindowTitle("Create geometry");form=QFormLayout(dialog)
        shape=QComboBox();shape.addItems(["Clamp","Plate","Block"])
        fields={}
        for key,value in (("Width",72),("Height",28),("Thickness",14)):
            spin=QDoubleSpinBox();spin.setRange(.1,1000);spin.setValue(value);spin.setSuffix(" mm");fields[key]=spin
        form.addRow("Shape",shape)
        for key,widget in fields.items():form.addRow(key,widget)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            payload=clone(self.data);payload["geometry_type"]=shape.currentText()
            for key,widget in fields.items():payload[key.lower()]=widget.value()
            payload["geometry_origin"]="Created in review";payload["sketch"]["fully_constrained"]=False
            payload["contact"]["resolved"]=False;payload["contact"]["active"]=shape.currentText()=="Clamp";payload["mesh"]["stale"]=True
            if shape.currentText()!="Clamp":
                payload["conditions"]=[{"type":"Fixed support","face":"Plate/Pad/Face6","axis":"All","value":0,"unit":"mm"}]
            self.session.change(self.key,payload,"Create geometry");self.refresh();self.mode.setCurrentText("Sketch")

    def import_geometry(self):
        path,_=QFileDialog.getOpenFileName(self,"Select native geometry","","Geometry (*.FCStd *.step *.stp *.iges *.igs);;All files (*)")
        if path:
            self.session.edit(self.key,"import_proposal",{"path":path,"reader":"FreeCAD","status":"NOT_LOADED"})
            self.update_title(Path(path).name+" selected; native import is not connected")

    def property_changed(self,item):
        if self._building or item.column()!=1:return
        self.edit_number(["thickness","width","height"][item.row()],item);self.update_view()

    def draw_line(self):
        self.viewer.draw_line=True;self.viewer.setFocus();self.update_title("Drag a sketch line; dimensions are in mm")

    def add_sketch_line(self,line):
        payload=clone(self.data);payload["sketch"].setdefault("lines",[]).append(line)
        payload["sketch"]["fully_constrained"]=False;self.session.change(self.key,payload,"Draw sketch line");self.refresh()

    def remove_line(self):
        row=self.sketch_lines.currentRow()
        if row>=0:
            payload=clone(self.data);payload["sketch"].setdefault("lines",[]).pop(row)
            self.session.change(self.key,payload,"Remove sketch line");self.refresh()

    def sketch_line_changed(self,item):
        if self._building or item.column()==0:return
        locator=f"sketch.lines.{item.row()}.{item.column()-1}"
        try:value=number(item.text())
        except ValueError:
            self.retain_input(locator,item.text());mark_invalid(item,True);self.update_title();return
        buffers=clone(self.document["buffers"]);buffers.pop(locator,None);payload=clone(self.data)
        payload["sketch"]["lines"][item.row()][item.column()-1]=value;payload["sketch"]["fully_constrained"]=False
        self.session.change(self.key,payload,"Edit sketch line",buffers=buffers);self.update_view();self.update_title()

    def part_changed(self,value):
        if self._building:return
        self.session.edit(self.key,"selected_part",value);self.viewer.moving_part=value;self.viewer.set_selected(value+"/Face2")
        self.update_title()

    def mesh_type_changed(self,value):
        if self._building:return
        payload=clone(self.data);payload["mesh"].update(type=value,stale=True)
        self.session.change(self.key,payload,"Edit element type");self.update_title()

    def constraint_changed(self,item):
        if self._building or item.column()!=1:return
        self.edit_number(["width","height"][item.row()],item)
        sketch=clone(self.data["sketch"]);sketch.update(length_constraint=str(self.data["width"]),fully_constrained=False)
        self.session.edit(self.key,"sketch",sketch);self.update_view()

    def constrain_sketch(self):
        if any(self.data[k]<=0 for k in ("width","height")):raise ReviewError("Use positive rectangle dimensions.")
        sketch=clone(self.data["sketch"]);sketch.update(length_constraint=str(self.data["width"]),fully_constrained=True)
        self.session.edit(self.key,"sketch",sketch)
        self.update_title("Rectangle dimensions assigned in illustration; native constraint solve pending")

    def hole_changed(self,value):
        if not self._building:
            payload=clone(self.data);payload["through_hole"]=value;payload["mesh"]["stale"]=True
            self.session.change(self.key,payload,"Edit through hole");self.update_view();self.update_title()

    def assembly_changed(self,*args):
        if self._building:return
        payload=clone(self.data);payload["instances"]=self.instances.value();payload["joint"]["type"]=self.joint.currentText()
        payload["mesh"]["stale"]=True
        self.session.change(self.key,payload,"Edit assembly");self.refresh();self.update_title()

    def mesh_changed(self,value):
        if self._building:return
        payload=clone(self.data);payload["mesh"].update(size=value,stale=True)
        self.session.change(self.key,payload,"Edit mesh size");self.update_title()

    def condition_dialog(self,editing=False):
        row=self.conditions.currentRow();old=self.data.get("conditions",[])
        if editing and row<0:return
        source=old[row] if editing else {"type":"Force","face":self.face_name.text(),"axis":"Z","value":-250,"unit":"N"}
        dialog=QDialog(self);dialog.setWindowTitle("Condition");form=QFormLayout(dialog)
        kind=QComboBox();kind.addItems(["Fixed support","Force","Displacement","Pressure","Temperature"]);kind.setCurrentText(source["type"])
        face=QLineEdit(source["face"]);axis=QComboBox();axis.addItems(["All","X","Y","Z","Normal"]);axis.setCurrentText(source["axis"])
        value=QLineEdit(str(source["value"]));unit=QLabel(source["unit"])
        units={"Fixed support":"mm","Force":"N","Displacement":"mm","Pressure":"MPa","Temperature":"K"}
        kind.currentTextChanged.connect(lambda k:unit.setText(units[k]))
        for label,w in (("Type",kind),("Selected face",face),("Direction",axis),("Value",value),("Unit",unit)):form.addRow(label,w)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            if not face.text().strip():raise ReviewError("Select a face for the condition.")
            item={"type":kind.currentText(),"face":face.text(),"axis":axis.currentText(),"value":number(value.text()),"unit":unit.text()}
            payload=clone(self.data);items=payload.setdefault("conditions",[])
            if editing:items[row]=item
            else:items.append(item)
            self.session.change(self.key,payload,"Edit boundary condition");self.refresh()

    def remove_condition(self):
        row=self.conditions.currentRow()
        if row>=0:
            payload=clone(self.data);payload["conditions"].pop(row)
            self.session.change(self.key,payload,"Remove boundary condition");self.refresh()

    def condition_selected(self):
        row=self.conditions.currentRow()
        if row>=0:
            self.viewer.set_selected(self.data["conditions"][row]["face"])
            self.viewer.annotation=self.data["conditions"][row]["type"];self.viewer.update()

    def quality_selected(self):
        row=self.quality.currentRow()
        if row>=0:
            self.viewer.annotation="Element "+self.quality.item(row,0).text();self.viewer.selected_element=int(self.quality.item(row,0).text());self.viewer.update()

    def change_contact(self,field,value):
        if self._building:return
        payload=clone(self.data);payload["contact"][field]=value
        self.session.change(self.key,payload,"Edit contact "+field);self.update_title()

    def add_face(self):
        payload=clone(self.data);which="set_a" if self.face_set.currentIndex()==0 else "set_b"
        if self.face_name.text() not in payload["contact"][which]:
            payload["contact"][which].append(self.face_name.text())
            self.session.change(self.key,payload,"Add contact face");self.refresh()

    def remove_face(self):
        row=self.contact_table.currentRow()
        if row<0:return
        side=self.contact_table.item(row,0).text();name=self.contact_table.item(row,1).text()
        payload=clone(self.data);payload["contact"]["set_a" if side=="A" else "set_b"].remove(name)
        self.session.change(self.key,payload,"Remove contact face");self.refresh()

    def tree_selected(self):
        item=self.tree.currentItem()
        if not item:return
        if item.text(0) in [self.mode.itemText(i) for i in range(self.mode.count())]:self.mode.setCurrentText(item.text(0))
        name="Base/Face2" if item.text(0)=="Base" else "Clamp/Pad/Face6"
        self.viewer.set_selected(name);self.face_name.setText(name)

    def preview_pose(self,value):
        self.pose_preview=value;self.viewer.joint_angle=value;self.viewer.update()

    def use_pose(self):
        payload=clone(self.data);payload["joint"]["angle"]=getattr(self,"pose_preview",15);payload["mesh"]["stale"]=True
        self.session.change(self.key,payload,"Use reviewed pose");self.update_title()

    def restore_pose(self):
        self.angle.setValue(self.data["joint"]["angle"]);self.preview_pose(self.data["joint"]["angle"])
        self.update_title("Design pose restored")

    def save(self,force_path=False):
        if getattr(self,"pose_preview",self.data["joint"]["angle"])!=self.data["joint"]["angle"]:
            raise ReviewError("Use pose or Restore pose before saving the model.")
        return super().save(force_path)

    def break_contact(self):
        payload=clone(self.data);payload["contact"]["resolved"]=False;payload["mesh"]["stale"]=True
        self.session.change(self.key,payload,"Review geometry change");self.update_title("Contact needs rebind; mesh is stale")

    def rebind(self):
        if self.data.get("geometry_type","Clamp")!="Clamp":raise ReviewError("This split-face example belongs to Clamp. Use the current geometry face selection to define contact; no mapping was applied.")
        dialog=QDialog(self);dialog.setWindowTitle("Rebind contact faces");dialog.resize(820,360)
        layout=QVBoxLayout(dialog)
        layout.addWidget(make_table(["Old face","Proposed face","Area [mm²]","Normal dot"],[
            ["Clamp/Pad/Face6","Clamp/Pad/Face8 + Face9","320 → 319.8",1],["Base/Face2","Base/Face2","336 → 336",-1]]))
        confirm=QCheckBox("I reviewed both new faces and the reversed normal");layout.addWidget(confirm)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        apply=buttons.addButton("Apply selected",QDialogButtonBox.ButtonRole.AcceptRole);apply.setEnabled(False)
        confirm.toggled.connect(apply.setEnabled);apply.clicked.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            payload=clone(self.data);payload["contact"].update(set_a=["Clamp/Pad/Face8","Clamp/Pad/Face9"],resolved=True)
            payload["mesh"]["stale"]=True;self.session.change(self.key,payload,"Rebind selected contact faces");self.refresh()
            self.update_title("Contact rebound. Preview the rebuilt mesh before freeze.")

    def rebuild_mesh(self):
        payload=clone(self.data);payload["mesh"].update(stale=False,reviewed=True)
        size=payload["mesh"]["size"];payload["mesh"]["bad_elements"]=[314,829] if size>1.5 else []
        self.session.change(self.key,payload,"Review rebuilt mesh fixture")
        self.viewer.mesh=True;self.viewer.mesh_size=size;self.viewer.mesh_type=payload["mesh"].get("type","Tet4")
        fill_table(self.quality,[[314,.19 if size>1.5 else .48,.25,"Review" if size>1.5 else "Within fixture limit"],[829,.22 if size>1.5 else .52,.25,"Review" if size>1.5 else "Within fixture limit"]])
        self.viewer.update();self.update_title("Synthetic mesh preview; native mesher not executed")

    def check(self):
        errors=self.session.diagnostics(self.key)
        if errors:raise ReviewError("\n".join(field+": "+msg for field,msg in errors))
        self.update_title("Required input checked; native validation remains pending")

    def to_simulation(self):
        self.flush_editor()
        if getattr(self,"pose_preview",self.data["joint"]["angle"])!=self.data["joint"]["angle"]:raise ReviewError("Use pose or Restore pose first.")
        self.check()
        if self.document["dirty"]:raise ReviewError("Save the edited geometry before using it in Simulation.")
        self.session.edit("simulation","model_ref",{"id":self.document["id"],"revision":self.document["revision"]})
        self.hub.open("simulation").refresh()

    def update_view(self):
        self.viewer.set_geometry(self.data)
        self.viewer.joint_angle=getattr(self,"pose_preview",self.data["joint"]["angle"])
        self.viewer.update()

    def refresh(self):
        was=self._building;self._building=True
        fill_table(self.props,[[key.title(),self.raw(key,self.data[key]),"mm"] for key in ("thickness","width","height")],(1,))
        fill_table(self.constraints,[[key.title(),self.raw(key,self.data[key]),"mm"] for key in ("width","height")],(1,))
        fill_table(self.contact_table,[["A",v] for v in self.data["contact"]["set_a"]]+[["B",v] for v in self.data["contact"]["set_b"]])
        fill_table(self.conditions,[[c["type"],c["face"],c["value"],c["unit"]] for c in self.data.get("conditions",[])])
        fill_table(self.sketch_lines,[["Line "+str(i+1)]+[self.raw(f"sketch.lines.{i}.{c}",v) for c,v in enumerate(line)] for i,line in enumerate(self.data["sketch"].get("lines",[]))],(1,2,3,4))
        self.contact_active.setChecked(self.data["contact"].get("active",True));self.mesh_type.setCurrentText(self.data["mesh"].get("type","Tet4"))
        self.part.clear();self.part.addItems(["Base"]+["Clamp" if i==1 else "Clamp "+str(i) for i in range(1,self.data.get("instances",2))])
        self.part.setCurrentText(self.data.get("selected_part","Clamp"))
        self.law.setCurrentText(self.data["contact"]["law"]);self.mu.setValue(self.data["contact"]["mu"]);self.gap.setValue(self.data["contact"]["gap"])
        self.instances.setValue(self.data.get("instances",2));self.joint.setCurrentText(self.data["joint"]["type"])
        self.angle.setValue(self.data["joint"]["angle"]);self.mesh_size.setValue(self.data["mesh"]["size"]);self.hole.setChecked(self.data.get("through_hole",False))
        self.tree.clear();root=QTreeWidgetItem(self.tree,[self.document["name"]])
        for name in ("Base",self.data.get("geometry_type","Clamp"),"Sketch","Features","Assembly","Motion","Mesh","Conditions","Contact"):QTreeWidgetItem(root,[name])
        self.tree.expandAll();self.update_view();self._building=was;self.update_title()


class SimulationWindow(ToolWindow):
    def build(self):
        self.geometry_action=self.action(self.toolbar,"Update geometry…",self.update_geometry)
        self.action(self.toolbar,"Check",self.input_diagnostics)
        self.action(self.toolbar,"Run analysis…",self.submit_review)
        self.action(self.toolbar,"Runner",lambda:self.hub.open("runner"))
        self.action(self.toolbar,"Evaluation",lambda:self.hub.open("evaluation"))
        self.tree=QTreeWidget();self.tree.setHeaderHidden(True);root=QTreeWidgetItem(self.tree,[self.document["name"]])
        self.nodes=["Model","Steps","Boundary conditions","Contact","Initial conditions","Failure","Output"]
        for name in self.nodes:QTreeWidgetItem(root,[name])
        self.tree.expandAll();self.add_dock("Model",self.tree,minimum=210)
        self.pages=QStackedWidget();self.family=QComboBox();self.backend=QComboBox()
        thermal=self.data["family"] in ("Thermal","Thermoelastic")
        families=[self.data["family"]] if thermal else ["Nonlinear implicit","Explicit impact","Failure / interface"]
        self.family.addItems(families);self.family.setCurrentText(self.data["family"])
        self.family.currentTextChanged.connect(self.family_changed)
        self.backend.addItems([self.data["backend"]] if thermal else ["Code_Aster","OpenCourant / OpenRadioss","CalculiX","External deck"])
        self.backend.currentTextChanged.connect(lambda v:self.edit_value("backend",v))
        self.geometry_label=QLabel();self.geometry_label.setWordWrap(True)
        self.pages.addWidget(box(QLabel("Analysis"),self.family,QLabel("Solver"),self.backend,self.geometry_label,
            button("Open geometry / domain",self.open_geometry),margins=8))
        if thermal:
            self.numeric_fields=["temperature"] if self.data["family"]=="Thermal" else ["Tref","alpha"]
            rows=[[key,self.raw(key,self.data[key]),"K" if key in ("temperature","Tref") else "1/K"] for key in self.numeric_fields]
        else:
            self.numeric_fields=["duration","increments","time_step","force"]
            rows=[["Step duration",self.raw("duration",self.data["duration"]),"s"],
                  ["Maximum increments",self.raw("increments",self.data["increments"]),""],
                  ["Time step",self.raw("time_step",self.data["time_step"]),"s"],
                  ["Load amplitude",self.raw("force",self.data["force"]),"N"]]
        self.table=make_table(["Setting","Value","Unit"],rows,editable=(1,),select_rows=False);self.table.setObjectName("simulationSettings")
        self.table.itemChanged.connect(self.cell_changed)
        self.steps=make_table(["Step","Duration [s]","Control"],[])
        self.step_index=self.document.get("view",{}).get("step",0)
        self.steps.itemSelectionChanged.connect(self.step_selected)
        self.step_controls=make_table(["Nonlinear control","Value"],[],editable=(1,),select_rows=False)
        self.step_controls.itemChanged.connect(self.control_changed)
        self.pages.addWidget(box(self.steps,box(button("Add step…",self.step_dialog),button("Edit…",lambda:self.step_dialog(True)),button("Delete",self.delete_step),horizontal=True),self.table,self.step_controls,margins=8))
        self.boundaries=make_table(["Condition","Target","Direction","Value","Unit"],[])
        self.boundaries.itemSelectionChanged.connect(self.boundary_selected)
        self.pages.addWidget(box(self.boundaries,box(button("Add…",self.boundary_dialog),button("Edit…",lambda:self.boundary_dialog(True)),button("Delete",self.delete_boundary),horizontal=True),margins=8))
        self.contact=make_table(["Contact","Value"],[])
        self.pages.addWidget(box(self.contact,button("Edit faces / contact law",self.open_contact),margins=8))
        self.initial_mode=QComboBox();self.initial_mode.addItems(["Measured pre-impact velocity","Height and gravity"])
        self.initial_mode.currentTextChanged.connect(lambda v:self.edit_value("initial_mode",v))
        self.initial=make_table(["Initial condition","Value","Unit"],[],editable=(1,),select_rows=False)
        self.initial.itemChanged.connect(self.initial_changed)
        self.pages.addWidget(box(self.initial_mode,self.initial,margins=8))
        self.failure=QComboBox();self.failure.addItems(["None","Interface damage","Bulk plastic damage","Cohesive separation"])
        self.failure.currentTextChanged.connect(lambda v:self.edit_value("failure",v))
        self.failure_values=make_table(["Parameter","Value","Unit"],[],editable=(1,),select_rows=False)
        self.failure_values.itemChanged.connect(self.failure_changed)
        self.pages.addWidget(box(QLabel("Failure model"),self.failure,self.failure_values,margins=8))
        self.output=make_table(["Quantity","Location","Write"],[],editable=(2,),select_rows=False)
        self.output.itemChanged.connect(self.output_changed);self.pages.addWidget(box(self.output,margins=8))
        mode="thermal" if self.data["family"]=="Thermal" else "thermoelastic" if thermal else "cad"
        self.viewer=EngineeringView(mode);self.viewer.label="Selected model illustration"
        self.viewer.faceSelected.connect(lambda name:self.update_title("Selected target: "+name))
        split=QSplitter();split.addWidget(self.pages);split.addWidget(self.viewer);split.setSizes([420,760]);self.setCentralWidget(split)
        self.tree.itemSelectionChanged.connect(self.selection_changed);self.refresh();self.pages.setCurrentIndex(1)

    def open_geometry(self):
        if self.data["family"] not in ("Thermal","Thermoelastic"):return self.hub.open("cad")
        dialog=QDialog(self);dialog.setWindowTitle("Plate domain");form=QFormLayout(dialog)
        width=QLineEdit(str(self.data.get("width",1)));height=QLineEdit(str(self.data.get("height",.6)));mesh=QLineEdit(str(self.data.get("element_size",.05)))
        for name,widget in (("Width [m]",width),("Height [m]",height),("Element size [m]",mesh)):form.addRow(name,widget)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            payload=clone(self.data);payload.update(width=number(width.text()),height=number(height.text()),element_size=number(mesh.text()))
            self.session.change(self.key,payload,"Edit independent plate domain");self.refresh()

    def configure_domain_pages(self):
        thermal=self.data["family"] in ("Thermal","Thermoelastic")
        root=self.tree.topLevelItem(0)
        for i,name in enumerate(self.nodes):root.child(i).setHidden(thermal and name in ("Contact","Initial conditions","Failure"))
        self.geometry_action.setEnabled(not thermal)
        self.steps.parentWidget().layout().itemAt(1).widget().setVisible(not thermal)
        self.steps.setVisible(not thermal);self.step_controls.setVisible(not thermal)
        if thermal:
            self.viewer.model_width=self.data.get("width",1)*100;self.viewer.model_height=self.data.get("height",.6)*100
            quantities=[("Temperature","Point"),("Heat flux","Cell")] if self.data["family"]=="Thermal" else [("Displacement","Point"),("Stress","Cell"),("Temperature source","Point")]
            fill_table(self.output,[[name,loc,"Yes" if self.data.get("outputs",{}).get(name,True) else "No"] for name,loc in quantities],(2,))
            if self.pages.currentIndex() in (3,4,5):self.pages.setCurrentIndex(1)

    def edit_value(self,field,value):
        if not self._building:self.session.edit(self.key,field,value);self.update_title()

    def step_selected(self):
        if self._building:return
        self.step_index=max(0,self.steps.currentRow());self.document.setdefault("view",{})["step"]=self.step_index
        self.refresh_step_values()

    def refresh_step_values(self):
        rows=self.data.get("steps",[]);step=rows[self.step_index] if 0<=self.step_index<len(rows) else {}
        blocked=self.table.blockSignals(True)
        for i,key in enumerate(self.numeric_fields):
            value=step.get(key,self.data[key]);locator=f"steps.{self.step_index}.{key}" if rows else key
            self.table.item(i,1).setText(str(self.raw(locator,value)))
        self.table.blockSignals(blocked)

    def cell_changed(self,item):
        if self._building or item.column()!=1:return
        field=self.numeric_fields[item.row()]
        if self.data["family"] in ("Thermal","Thermoelastic") or not self.data.get("steps"):
            self.edit_number(field,item);return
        payload=clone(self.data);locator=f"steps.{self.step_index}.{field}"
        try:value=number(item.text())
        except ValueError:
            self.retain_input(locator,item.text());mark_invalid(item,True);self.update_title();return
        buffers=clone(self.document["buffers"]);buffers.pop(locator,None)
        payload["steps"][self.step_index][field]=value
        if self.step_index==0:payload[field]=value
        self.session.change(self.key,payload,"Edit selected analysis step",buffers=buffers)
        mark_invalid(item,False);self.update_title()
        if field=="duration":
            blocked=self.steps.blockSignals(True);self.steps.item(self.step_index,1).setText(str(value));self.steps.blockSignals(blocked)

    def family_changed(self,value):
        if self._building:return
        self.session.edit(self.key,"family",value);self.refresh();self.update_title(value+" settings")

    def control_changed(self,item):
        if self._building or item.column()!=1:return
        field=self.control_fields[item.row()]
        if field=="line_search":self.edit_value(field,item.text())
        else:self.edit_number(field,item)

    def initial_changed(self,item):
        if not self._building and item.column()==1:self.edit_number(["initial_velocity","angular_velocity","drop_height","gravity"][item.row()],item)

    def failure_changed(self,item):
        if not self._building and item.column()==1:self.edit_number(["strength","fracture_energy","damage_limit"][item.row()],item,nested="failure_parameters")

    def output_changed(self,item):
        if self._building or item.column()!=2:return
        payload=clone(self.data);payload.setdefault("outputs",{})[self.output.item(item.row(),0).text()]=item.text().lower() in ("yes","true","1")
        self.session.change(self.key,payload,"Select analysis output");self.update_title()

    def step_dialog(self,editing=False):
        steps=self.data.get("steps",[{"name":"Load","duration":self.data.get("duration",1),"control":"Automatic"}]);row=self.steps.currentRow()
        if editing and row<0:return
        src=steps[row] if editing else {"name":"Hold","duration":1,"control":"Automatic"}
        dialog=QDialog(self);dialog.setWindowTitle("Analysis step");form=QFormLayout(dialog)
        name=QLineEdit(src["name"]);duration=QLineEdit(str(src["duration"]));control=QComboBox();control.addItems(["Automatic","Fixed increments","Explicit stable step"]);control.setCurrentText(src["control"])
        for label,w in (("Name",name),("Duration [s]",duration),("Control",control)):form.addRow(label,w)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            payload=clone(self.data);items=clone(steps);item={"name":name.text(),"duration":number(duration.text()),"control":control.currentText()}
            if editing:items[row]=item
            else:items.append(item)
            payload["steps"]=items;payload["duration"]=items[0]["duration"];self.step_index=row if editing else len(items)-1
            self.session.change(self.key,payload,"Edit analysis step");self.refresh()

    def delete_step(self):
        row=self.steps.currentRow()
        if row<0:return
        items=clone(self.data.get("steps",[{"name":"Load","duration":1,"control":"Automatic"}]))
        items.pop(row);self.session.edit(self.key,"steps",items);self.refresh()

    def boundary_dialog(self,editing=False):
        items=self.data.get("conditions",clone(self.session.doc("cad")["saved"].get("conditions",[])));row=self.boundaries.currentRow()
        if editing and row<0:return
        src=items[row] if editing else {"type":"Force","face":self.viewer.selected,"axis":"Z","value":-250,"unit":"N"}
        dialog=QDialog(self);dialog.setWindowTitle("Boundary condition");form=QFormLayout(dialog)
        kind=QComboBox();units={"Fixed support":"mm","Force":"N","Displacement":"mm","Pressure":"MPa","Temperature":"K"};kind.addItems(units);kind.setCurrentText(src["type"])
        face=QLineEdit(src["face"]);axis=QComboBox();axis.addItems(["All","X","Y","Z","Normal"]);axis.setCurrentText(src["axis"]);value=QLineEdit(str(src["value"]));unit=QLabel(src["unit"])
        kind.currentTextChanged.connect(lambda v:unit.setText(units[v]))
        for label,w in (("Type",kind),("Target",face),("Direction",axis),("Value",value),("Unit",unit)):form.addRow(label,w)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            item={"type":kind.currentText(),"face":face.text(),"axis":axis.currentText(),"value":number(value.text()),"unit":unit.text()};items=clone(items)
            if editing:items[row]=item
            else:items.append(item)
            self.session.edit(self.key,"conditions",items);self.refresh()

    def delete_boundary(self):
        row=self.boundaries.currentRow()
        if row>=0:
            items=clone(self.data.get("conditions",self.session.doc("cad")["saved"].get("conditions",[])));items.pop(row)
            self.session.edit(self.key,"conditions",items);self.refresh()

    def boundary_selected(self):
        row=self.boundaries.currentRow()
        if row>=0:self.viewer.set_selected(self.boundaries.item(row,1).text());self.viewer.annotation=self.boundaries.item(row,0).text();self.viewer.update()

    def open_contact(self):
        window=self.hub.open("cad");window.mode.setCurrentText("Contact")

    def update_geometry(self):
        if self.data["family"] in ("Thermal","Thermoelastic"):raise ReviewError("This bounded plate model uses its own SI domain; edit its thermal definition.")
        cad=self.session.doc("cad")
        if cad["dirty"]:raise ReviewError("Save CAD before updating this analysis geometry.")
        errors=self.session.diagnostics("cad")
        if errors:raise ReviewError("Correct CAD input first: "+errors[0][1])
        if QMessageBox.question(self,"Update geometry",f"Use saved {cad['name']} ({cad['saved']['width']:g} × {cad['saved']['height']:g} × {cad['saved']['thickness']:g} mm)?")==QMessageBox.StandardButton.Yes:
            payload=clone(self.data);payload["model_ref"]={"id":cad["id"],"revision":cad["revision"]};payload["conditions"]=clone(cad["saved"].get("conditions",[]))
            self.session.change(self.key,payload,"Update saved geometry");self.refresh()

    def selection_changed(self):
        node=self.tree.currentItem()
        if node and node.text(0) in self.nodes:
            self.pages.setCurrentIndex(self.nodes.index(node.text(0)))
            self.viewer.annotation=node.text(0);self.viewer.update()

    def refresh(self):
        was=self._building;self._building=True;self.family.setCurrentText(self.data["family"]);self.backend.setCurrentText(self.data["backend"])
        self.refresh_step_values()
        fill_table(self.steps,[[r["name"],r["duration"],r["control"]] for r in self.data.get("steps",[{"name":"Load","duration":self.data.get("duration",1),"control":"Automatic"}])])
        controls=([("mass_scaling",0),("cfl",.8)] if self.data["family"]=="Explicit impact" else [("residual_tolerance",1e-6),("max_iterations",25),("line_search","On")])
        self.control_fields=[key for key,_ in controls]
        fill_table(self.step_controls,[[k.replace("_"," ").title(),self.raw(k,self.data.get(k,d))] for k,d in controls],(1,))
        fill_table(self.initial,[[label,self.raw(k,self.data.get(k,d)),unit] for label,k,d,unit in [("Velocity","initial_velocity",0,"m/s"),("Angular velocity","angular_velocity",0,"rad/s"),("Height","drop_height",.6,"m"),("Gravity","gravity",9.81,"m/s²")]],(1,))
        self.initial_mode.setCurrentText(self.data.get("initial_mode","Measured pre-impact velocity"));self.failure.setCurrentText(self.data.get("failure","None"))
        fill_table(self.failure_values,[[k.replace("_"," ").title(),self.raw("failure_parameters."+k,self.data.get("failure_parameters",{}).get(k,d)),u] for k,d,u in [("strength",12,"MPa"),("fracture_energy",.2,"N/mm"),("damage_limit",1,"1")]],(1,))
        outputs=[("Displacement / reaction","Node"),("Contact pressure / slip","Contact surface"),("Internal / kinetic / contact energy","Global"),("Damage / separation","Interface"),("Temperature","Point")]
        fill_table(self.output,[[name,loc,"Yes" if self.data.get("outputs",{}).get(name,name!="Temperature") else "No"] for name,loc in outputs],(2,))
        try:
            ref=self.data.get("model_ref");_,geometry=self.session.resolve(ref) if ref else (None,{})
            if ref:
                self.geometry_label.setText("Geometry: "+self.session.doc(ref["id"])["name"]+f" / {geometry['width']:g} × {geometry['height']:g} × {geometry['thickness']:g} mm")
                self.viewer.set_geometry(geometry)
                self.viewer.conditions=self.data.get("conditions",geometry.get("conditions",[]))
                fill_table(self.contact,[["Law",geometry["contact"]["law"]],["Set A",len(geometry["contact"]["set_a"])],["Set B",len(geometry["contact"]["set_b"])],["Friction",geometry["contact"]["mu"]]])
            else:self.geometry_label.setText(self.data.get("mesh","Plate domain")+" / "+self.data.get("unit",""))
            fill_table(self.boundaries,[[c["type"],c["face"],c["axis"],c["value"],c["unit"]] for c in self.data.get("conditions",geometry.get("conditions",[]))])
        except ReviewError as error:self.geometry_label.setText(str(error))
        self.step_index=min(self.step_index,max(0,self.steps.rowCount()-1));self.steps.selectRow(self.step_index);self.refresh_step_values()
        self.configure_domain_pages()
        self.viewer.update();self._building=was;self.update_title()


DATA_UNITS={"time":{"s":(1,0),"ms":(.001,0)},"extension":{"mm":(1,0),"m":(1000,0)},
            "force":{"N":(1,0),"kN":(1000,0)},"temperature":{"degC":(1,0),"K":(1,-273.15)}}


def canonical_observations(payload):
    result=clone(payload)
    for column in result["columns"]:
        key=column["key"];factor,offset=DATA_UNITS[key][column["unit"]]
        for sample in result["samples"]:sample[key]=sample[key]*factor+offset
        column["unit"]=next(iter(DATA_UNITS[key]))
    return result


class DataWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Import CSV…",self.import_csv)
        self.action(self.toolbar,"Exclude",lambda:self.exclude(True))
        self.action(self.toolbar,"Restore",lambda:self.exclude(False))
        self.action(self.toolbar,"Calibration…",self.calibration)
        self.action(self.toolbar,"Use in Material…",self.to_material)
        self.meta=make_table(["A","B","C","D"],[
            [c["name"] for c in self.data["columns"]],[c["unit"] for c in self.data["columns"]],
            [c["role"] for c in self.data["columns"]],[c["formula"] for c in self.data["columns"]]],
            editable=(0,1,2,3),select_rows=False)
        self.meta.setVerticalHeaderLabels(["Name","Units","Role","F(x)"])
        self.meta.setMaximumHeight(150)
        self.meta.itemChanged.connect(self.meta_changed)
        self.table=make_table(["Sample","Time [s]","Extension [mm]","Force [N]","Temperature [degC]"],[])
        self.table.setObjectName("dataSamples")
        self.table.setSortingEnabled(False)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.context_menu)
        self.curve=CurveView(xlabel="Extension [mm]",ylabel="Force [N]")
        self.curve.samplesSelected.connect(self.curve_selected)
        workbook=box(self.meta,self.table)
        split=QSplitter(Qt.Orientation.Vertical);split.addWidget(workbook);split.addWidget(self.curve);split.setSizes([500,300])
        self.setCentralWidget(split)
        self.refresh()

    def meta_changed(self,item):
        if self._building:return
        fields=["name","unit","role","formula"];payload=clone(self.data);column=payload["columns"][item.column()]
        value=item.text();key=column["key"];buffers=clone(self.document["buffers"])
        if item.row()==1:
            if value not in DATA_UNITS[key]:
                self.retain_input("column.unit."+key,value);mark_invalid(item,True);self.update_title("Choose "+" or ".join(DATA_UNITS[key]));return
            old_factor,old_offset=DATA_UNITS[key][column["unit"]];new_factor,new_offset=DATA_UNITS[key][value]
            if value!=column["unit"]:
                answer=QMessageBox.question(self,"Convert column units","Convert "+column["name"]+" from "+column["unit"]+" to "+value+"?")
                if answer!=QMessageBox.StandardButton.Yes:self.refresh();return
                for sample in payload["samples"]:sample[key]=(sample[key]*old_factor+old_offset-new_offset)/new_factor
            buffers.pop("column.unit."+key,None)
        column[fields[item.row()]]=value;self.session.change(self.key,payload,"Edit column "+fields[item.row()],buffers=buffers);self.refresh()

    def to_material(self):
        self.flush_editor()
        if self.document["dirty"]:raise ReviewError("Save the workbook before using its observations.")
        observations=canonical_observations(self.data)
        if QMessageBox.question(self,"Use observations in Material",f"Use {len(observations['samples'])-len(observations['quality_excluded'])} included observations from {self.document['name']}?")==QMessageBox.StandardButton.Yes:
            payload=clone(self.session.doc("material")["draft"]);payload["observations"]={"id":self.document["id"],"revision":self.document["revision"]}
            payload["observation_snapshot"]=observations;self.session.change("material",payload,"Use saved measurement data");self.hub.open("material").refresh()

    def selected_ids(self):
        return [self.table.item(index.row(),0).data(Qt.ItemDataRole.UserRole)
                for index in self.table.selectionModel().selectedRows()]

    def selection_changed(self):
        ids=self.selected_ids();self.session.selected["samples"]=ids
        self.curve.select_ids(ids,self.data["quality_excluded"])
        self.update_title(f"{len(ids)} selected   |   {len(self.data['samples'])-len(self.data['quality_excluded'])} included")

    def curve_selected(self,ids):
        wanted=set(ids);selection=QItemSelection()
        for row in range(self.table.rowCount()):
            if self.table.item(row,0).data(Qt.ItemDataRole.UserRole) in wanted:
                selection.select(self.table.model().index(row,0),self.table.model().index(row,self.table.columnCount()-1))
        self.table.selectionModel().select(selection,QItemSelectionModel.SelectionFlag.ClearAndSelect|QItemSelectionModel.SelectionFlag.Rows)
        if ids:
            rows=self.table.selectionModel().selectedRows()
            if rows:self.table.scrollTo(rows[0])

    def exclude(self,exclude):
        ids=self.selected_ids()
        if not ids:raise ReviewError("Select samples in the workbook or curve.")
        self.session.mask(ids,exclude)
        self.paint_mask();self.selection_changed()

    def paint_mask(self):
        excluded=set(self.data["quality_excluded"])
        for row in range(self.table.rowCount()):
            sid=self.table.item(row,0).data(Qt.ItemDataRole.UserRole)
            for c in range(self.table.columnCount()):
                self.table.item(row,c).setForeground(QColor("#8d969e" if sid in excluded else "#263442"))

    def context_menu(self,point):
        menu=QMenu(self)
        self.action(menu,"Exclude selected samples",lambda:self.exclude(True))
        self.action(menu,"Restore selected samples",lambda:self.exclude(False))
        index=self.table.indexAt(point)
        if index.isValid():
            self.action(menu,"Sort ascending",lambda:self.table.sortItems(index.column(),Qt.SortOrder.AscendingOrder))
            self.action(menu,"Sort descending",lambda:self.table.sortItems(index.column(),Qt.SortOrder.DescendingOrder))
        menu.exec(self.table.viewport().mapToGlobal(point))

    def calibration(self):
        self.hub.calibration(self)

    def import_csv(self):
        path,_=QFileDialog.getOpenFileName(self,"Import measurement CSV",str(HERE/"fixtures"),"CSV (*.csv);;All files (*)")
        if not path:return
        with open(path,newline="",encoding="utf-8-sig") as stream:
            reader=csv.DictReader(stream);rows=list(reader);fields=reader.fieldnames or []
        if not rows:raise ReviewError("The selected CSV has no samples.")
        dialog=QDialog(self);dialog.setWindowTitle("Map measurement columns");layout=QFormLayout(dialog)
        combos={};unit_boxes={}
        defaults={"time":"time_s","extension":"extension_mm","force":"force_N","temperature":"temperature_C"}
        for key,title in [("time","Time [s]"),("extension","Gauge extension [mm]"),("force","Force [N]"),("temperature","Temperature [degC]")]:
            combo=QComboBox();combo.addItems(fields)
            if defaults[key] in fields:combo.setCurrentText(defaults[key])
            combos[key]=combo;units=QComboBox();units.addItems(DATA_UNITS[key]);unit_boxes[key]=units
            layout.addRow(title,box(combo,units,horizontal=True))
        layout.addRow(QLabel("Apply converts the selected source units to s, mm, N and degC."))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addRow(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        if len({c.currentText() for c in combos.values()})!=4:
            raise ReviewError("Each required role must map to a distinct source column.")
        samples=[]
        for i,row in enumerate(rows):
            sample={"id":f"A{i}"}
            for key,combo in combos.items():
                try:
                    factor,offset=DATA_UNITS[key][unit_boxes[key].currentText()];sample[key]=number(row[combo.currentText()])*factor+offset
                except (ValueError,TypeError):raise ReviewError(f"Invalid {key} in source row {i+2}. Original CSV is unchanged.")
            samples.append(sample)
        if any(b["time"]<=a["time"] for a,b in zip(samples,samples[1:])):
            raise ReviewError("Time must be strictly increasing. Source order was preserved.")
        payload=clone(self.data);payload.update(samples=samples,quality_excluded=[],exclusion_reasons={})
        for column in payload["columns"]:column["unit"]=next(iter(DATA_UNITS[column["key"]]))
        payload["import"]={"filename":Path(path).name,"path":path,
                           "sha256":hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                           "mapping":{k:c.currentText() for k,c in combos.items()},"source_units":{k:c.currentText() for k,c in unit_boxes.items()}}
        self.session.change(self.key,payload,"Import measurement CSV");self.refresh()

    def refresh(self):
        was=self._building;self._building=True
        fill_table(self.meta,[[self.raw("column.unit."+c["key"],c[field]) if field=="unit" else c[field] for c in self.data["columns"]] for field in ("name","unit","role","formula")],(0,1,2,3))
        self.table.setHorizontalHeaderLabels(["Sample"]+[c["name"]+" ["+c["unit"]+"]" for c in self.data["columns"]])
        self.curve.xlabel=self.data["columns"][1]["name"]+" ["+self.data["columns"][1]["unit"]+"]"
        self.curve.ylabel=self.data["columns"][2]["name"]+" ["+self.data["columns"][2]["unit"]+"]"
        selected=self.session.selected.get("samples",[])
        self.table.blockSignals(True);self.table.setSortingEnabled(False)
        samples=self.data["samples"];self.table.setRowCount(len(samples))
        for r,sample in enumerate(samples):
            for c,field in enumerate(("id","time","extension","force","temperature")):
                item=QTableWidgetItem();item.setData(Qt.ItemDataRole.DisplayRole,sample[field])
                item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable)
                if c==0:item.setData(Qt.ItemDataRole.UserRole,sample["id"])
                self.table.setItem(r,c,item)
        if not getattr(self,"sorting_initialized",False):self.table.sortItems(1,Qt.SortOrder.AscendingOrder);self.sorting_initialized=True
        self.table.setSortingEnabled(True);self.table.blockSignals(False)
        self.curve.set_series([{"name":"Tension A","x":[s["extension"] for s in samples],
            "y":[s["force"] for s in samples],"ids":[s["id"] for s in samples],"color":BLUE}])
        self.paint_mask();self.curve_selected(selected)
        self._building=was
        self.update_title(f"{len(samples)} samples   |   {len(samples)-len(self.data['quality_excluded'])} included")


class MaterialWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Direct evaluation…",self.submit_review)
        self.action(self.toolbar,"Calibrate…",self.open_fit)
        self.action(self.toolbar,"Holdout",self.show_holdout)
        self.action(self.toolbar,"Repair references…",self.repair)
        self.curve=CurveView(xlabel="Engineering strain",ylabel="First Piola stress [MPa]")
        self.setCentralWidget(self.curve)
        self.tests=make_table(["Load case","Use"],[["Tension A","Train"],["Tension B","Holdout"],["Relaxation","Virtual"]])
        self.tests.itemSelectionChanged.connect(self.test_changed)
        self.coeff=make_table(["Parameter","Current","Unit"],[
            ["Shear modulus",self.data["mu"],"MPa"],["Bulk modulus",self.data["bulk"],"MPa"]],
            editable=(1,),select_rows=False)
        self.coeff.setObjectName("materialCoefficients")
        self.coeff.itemChanged.connect(self.coeff_changed)
        law=QComboBox();self.law=law;law.addItems(["Neo-Hookean","J2 plasticity","Drucker–Prager","Prony viscoelastic","User constitutive law"])
        law.setCurrentText(self.data["law"])
        law.currentTextChanged.connect(lambda value:self.edit_law(value))
        protocol=QComboBox();self.protocol=protocol;protocol.addItems(["Uniaxial traction-free","Prescribed deformation gradient","Measured transverse history"])
        protocol.setCurrentText(self.data["protocol"])
        protocol.currentTextChanged.connect(lambda value:self.edit_protocol(value))
        left=box(law,self.tests,QLabel("Parameters"),self.coeff,QLabel("Protocol"),protocol,
                 button("Edit history / state…",self.protocol_dialog),margins=6)
        dock=self.add_dock("Load cases",left,minimum=315);self.resizeDocks([dock],[350],Qt.Orientation.Horizontal)
        self.output=QPlainTextEdit("Retained synthetic comparison. No material evaluator has run.\n"
                                  "Direct evaluation, identification and holdout are separate actions.")
        self.output.setReadOnly(True)
        out=self.add_dock("Output",self.output,Qt.DockWidgetArea.BottomDockWidgetArea)
        self.resizeDocks([out],[120],Qt.Orientation.Vertical)
        self.refresh();self.set_curves()

    def set_curves(self,holdout=False):
        if self.data["law"]!="Neo-Hookean":
            self.curve.set_series([]);self.curve.caption="No retained result for "+self.data["law"];return
        xs=[i*.004 for i in range(81)]
        self.curve.set_series([
            {"name":"Observed B (holdout)" if holdout else "Observed A","x":xs,
             "y":[.85*(x+1-(1+x)**-2) for x in xs],"color":BLUE},
            {"name":"Retained prediction","x":xs,
             "y":[.87*(x+1-(1+x)**-2) for x in xs],"color":ORANGE}])
        if not holdout and self.data.get("observation_snapshot"):
            obs=self.data["observation_snapshot"];included=[row for row in obs["samples"] if row["id"] not in obs["quality_excluded"]]
            if self.data["L0"]>0 and self.data["A0"]>0:
                self.curve.set_series([{"name":"Saved observations","x":[row["extension"]/self.data["L0"] for row in included],"y":[row["force"]/self.data["A0"] for row in included],"color":BLUE}])
        self.curve.caption="Synthetic fixture; changing coefficients does not recompute a result"

    def coeff_changed(self,item):
        if self._building or item.column()!=1:return
        field=self.parameter_fields()[item.row()][0]
        self.edit_number(field,item,None if field in ("mu","bulk") else "parameters")
        self.output.setPlainText("Current coefficients edited. The displayed prediction retains its original input.\n"
                                 "Save the draft and choose Direct evaluation to review a new attempt.")

    def test_changed(self):
        self.set_curves(self.tests.currentRow()==1)

    def edit_law(self,value):
        if not self._building:self.session.edit(self.key,"law",value);self.refresh();self.set_curves();self.update_title("Constitutive parameters edited")

    def edit_protocol(self,value):
        if not self._building:self.session.edit(self.key,"protocol",value);self.update_title()

    def show_holdout(self):
        self.tests.setCurrentCell(1,0);self.set_curves(True)

    def open_fit(self):
        self.hub.open_fit(self.key)

    def parameter_fields(self):
        return {
            "Neo-Hookean":[("mu","MPa"),("bulk","MPa")],
            "J2 plasticity":[("E","MPa"),("nu","1"),("yield","MPa"),("hardening","MPa")],
            "Drucker–Prager":[("E","MPa"),("nu","1"),("cohesion","MPa"),("friction_angle","deg"),("dilation_angle","deg")],
            "Prony viscoelastic":[("mu","MPa"),("bulk","MPa"),("g1","1"),("tau1","s"),("g2","1"),("tau2","s")],
            "User constitutive law":[("E","MPa"),("nu","1")]}[self.data["law"]]

    def protocol_dialog(self):
        dialog=QDialog(self);dialog.setWindowTitle("Load case history and state");dialog.resize(880,580)
        layout=QVBoxLayout(dialog);tabs=QTabWidget()
        history=make_table(["Time [s]","Control","Target","Unit"],self.data.get("history",[[0,"Stretch F11",1,""],[1,"Stretch F11",1.2,""]]),editable=(0,1,2,3),select_rows=False)
        state=make_table(["Variable","Initial value"],self.data.get("initial_state",[["Plastic strain",0],["Damage",0],["Lateral traction",0]]),editable=(1,),select_rows=False)
        def add_history():
            rows=[[history.item(r,c).text() for c in range(4)] for r in range(history.rowCount())];rows.append([0,"Stretch F11",1,""]);fill_table(history,rows,(0,1,2,3))
        tabs.addTab(box(history,box(button("Add time point",add_history),button("Delete",lambda:history.removeRow(history.currentRow()) if history.currentRow()>=0 else None),horizontal=True)),"History")
        tabs.addTab(state,"Initial state")
        tabs.addTab(make_table(["Integration check","Value","State"],[["Consistent tangent error",None,"NOT_EVALUATED"],["Increment refinement",None,"NOT_EVALUATED"],["Return mapping failure",None,"No evaluator called"]]),"Integration / tangent")
        layout.addWidget(tabs);error=QLabel();layout.addWidget(error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel);apply=buttons.addButton("Apply",QDialogButtonBox.ButtonRole.AcceptRole)
        def accept():
            try:
                rows=[]
                for r in range(history.rowCount()):rows.append([number(history.item(r,0).text()),history.item(r,1).text(),number(history.item(r,2).text()),history.item(r,3).text()])
                if not rows or any(row[0]<0 for row in rows) or any(rows[i][0]>rows[i+1][0] for i in range(len(rows)-1)):raise ReviewError("Use nonnegative time points in order.")
                initial=[[state.item(r,0).text(),number(state.item(r,1).text())] for r in range(state.rowCount())]
                payload=clone(self.data);payload.update(history=rows,initial_state=initial)
                self.session.change(self.key,payload,"Edit load case protocol");self.update_title();dialog.accept()
            except (ValueError,ReviewError) as e:error.setText(str(e))
        apply.clicked.connect(accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec()

    def repair(self):
        self.hub.repair_material(self,self.key)

    def refresh(self):
        was=self._building;self._building=True
        defaults={"E":210000,"nu":.3,"yield":250,"hardening":1000,"cohesion":12,"friction_angle":30,"dilation_angle":5,"g1":.35,"tau1":1,"g2":.15,"tau2":10}
        rows=[]
        for key,unit in self.parameter_fields():
            value=self.data[key] if key in ("mu","bulk") else self.data.get("parameters",{}).get(key,defaults[key])
            locator=key if key in ("mu","bulk") else "parameters."+key
            rows.append([key,self.raw(locator,value),unit])
        fill_table(self.coeff,rows,(1,));self.law.setCurrentText(self.data["law"]);self.protocol.setCurrentText(self.data["protocol"])
        self._building=was;self.set_curves(self.tests.currentRow()==1);self.update_title()


class PDEWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Check equation",self.check);self.action(self.toolbar,"Solve…",self.evaluate)
        self.action(self.toolbar,"Evaluation",lambda:self.hub.open("evaluation"))
        self.tree=QTreeWidget();self.tree.setHeaderHidden(True);root=QTreeWidgetItem(self.tree,[self.document["name"]])
        self.node_names=["Domain","Mesh","Field","Equation","Left edge","Right edge","Top edge","Bottom edge","Initial condition","Study"]
        for name in self.node_names:QTreeWidgetItem(root,[name])
        self.tree.expandAll();self.add_dock("Model Builder",self.tree,minimum=215)
        self.pages=QStackedWidget();self.domain=QComboBox();self.domain.addItems(["Rectangle","Imported mesh (draft)"])
        self.domain.currentTextChanged.connect(lambda v:self.edit_field("domain",v))
        self.domain_size=make_table(["Dimension","Value","Unit"],[],editable=(1,),select_rows=False)
        self.domain_size.itemChanged.connect(lambda item:self.numeric_changed(item,["width","height"]))
        self.pages.addWidget(box(QLabel("Domain"),self.domain,self.domain_size,margins=8))
        self.mesh_table=make_table(["Mesh setting","Value","Unit"],[],editable=(1,),select_rows=False)
        self.mesh_table.itemChanged.connect(lambda item:self.numeric_changed(item,["mesh"]))
        self.pages.addWidget(box(self.mesh_table,button("Preview mesh",self.preview_mesh),margins=8))
        self.field_name=QLineEdit();self.field_unit=QLineEdit();self.space=QComboBox();self.space.addItems(["P1","P2","Vector P1"])
        self.field_name.editingFinished.connect(lambda:self.edit_field("field",self.field_name.text()))
        self.field_unit.editingFinished.connect(lambda:self.edit_field("field_unit",self.field_unit.text()))
        self.space.currentTextChanged.connect(lambda v:self.edit_field("space",v))
        form=QFormLayout();form.addRow("Unknown field",self.field_name);form.addRow("Unit",self.field_unit);form.addRow("Function space",self.space)
        fw=QWidget();fw.setLayout(form);self.pages.addWidget(box(fw,margins=8))
        self.form=QComboBox();self.form.addItems(["Registered PDE","General weak form","ODE"]);self.form.currentTextChanged.connect(self.form_changed)
        self.equation=QPlainTextEdit();self.equation.setMaximumHeight(190);self.equation.textChanged.connect(self.equation_changed)
        self.coefficients=make_table(["Coefficient","Value","Unit"],[],editable=(1,),select_rows=False)
        self.coefficients.itemChanged.connect(lambda item:self.numeric_changed(item,["k","f"]))
        self.extension=make_table(["Definition","Value","Unit"],[],editable=(1,),select_rows=False)
        self.extension.itemChanged.connect(self.extension_changed)
        self.extension.setColumnWidth(0,130);self.extension.setColumnWidth(1,180)
        self.pages.addWidget(box(QLabel("Equation form"),self.form,self.equation,self.coefficients,self.extension,margins=8))
        self.boundary_pages=[]
        for name in self.node_names[4:8]:
            kind=QComboBox();kind.addItems(["Dirichlet","Flux / Neumann","Robin"])
            expr=QLineEdit();apply=button("Apply boundary",lambda n=name,k=kind,e=expr:self.apply_boundary(n,k.currentText(),e.text()))
            reset=button("Reset",lambda n=name:self.reset_boundary(n))
            kind.currentTextChanged.connect(lambda v,n=name:self.pending_boundary(n,"type",v))
            expr.textEdited.connect(lambda v,n=name:self.pending_boundary(n,"expression",v))
            self.boundary_pages.append((name,kind,expr));self.pages.addWidget(box(QLabel(name),kind,expr,box(apply,reset,horizontal=True),margins=8))
        self.initial=QLineEdit();self.initial.textEdited.connect(lambda v:self.edit_field("initial",v));self.pages.addWidget(box(QLabel("Initial value / expression"),self.initial,margins=8))
        self.study_type=QComboBox();self.study_type.addItems(["Stationary","Transient"]);self.study_type.currentTextChanged.connect(lambda v:self.edit_field("study_type",v))
        self.time_range=QLineEdit();self.time_range.textEdited.connect(lambda v:self.edit_field("time_range",v))
        self.pages.addWidget(box(QLabel("Study"),self.study_type,QLabel("Output times [s]"),self.time_range,button("Solve…",self.evaluate),margins=8))
        self.graphics=EngineeringView("pde");self.graphics.faceSelected.connect(self.graphic_selected)
        self.graphics_tabs=QTabWidget();self.graphics_tabs.addTab(self.graphics,"Graphics")
        self.ode_curve=CurveView(xlabel="Time [s]",ylabel="x [1]")
        self.graphics_tabs.addTab(self.ode_curve,"ODE curve")
        self.action(self.review_menu,"Show authored ODE curve",self.ode_example)
        split=QSplitter();split.addWidget(self.pages);split.addWidget(self.graphics_tabs);split.setSizes([430,780]);self.setCentralWidget(split)
        self.messages=make_table(["Location","Message"],[["Result","No PDE evaluator has run"]])
        self.messages_dock=self.add_dock("Messages",self.messages,Qt.DockWidgetArea.BottomDockWidgetArea);self.resizeDocks([self.messages_dock],[110],Qt.Orientation.Vertical)
        self.tree.itemSelectionChanged.connect(self.node_selected);self.refresh();self.pages.setCurrentIndex(3)

    def edit_field(self,key,value):
        if not self._building:self.session.edit(self.key,key,value);self.update_title()

    def form_changed(self,value):
        self.edit_field("form",value)
        if not self._building:
            self.refresh()
            fill_table(self.messages,[["Adapter","Extension unavailable; editable draft retained" if value!="Registered PDE" else "Not connected"]])

    def extension_changed(self,item):
        if self._building or item.column()!=1:return
        group="weak_form" if self.data["form"]=="General weak form" else "ode"
        field=self.extension_fields[item.row()];value=item.text()
        if group=="ode" and field in ("initial","start","stop","step","a"):self.edit_number(field,item,group);return
        payload=clone(self.data);payload[group][field]=value
        if field=="trial":payload["field"]=value
        self.session.change(self.key,payload,"Edit "+group+" definition");self.update_title()

    def ode_example(self):
        self.ode_curve.set_series([{"name":"Authored x(t) example","x":[0,1,2,3,4,5],"y":[1,.367879,.135335,.049787,.018316,.006738],"color":BLUE}])
        self.ode_curve.caption="Authored x(0)=1, a=1, f=0 example; current equation was not solved"
        self.graphics_tabs.setCurrentIndex(1)

    def equation_changed(self):
        if self._building:return
        if self.data["form"]=="Registered PDE":self.edit_field("equation",self.equation.toPlainText());return
        payload=clone(self.data);group="weak_form" if self.data["form"]=="General weak form" else "ode"
        payload[group]["integral" if group=="weak_form" else "rhs"]=self.equation.toPlainText()
        self.session.change(self.key,payload,"Edit "+group+" expression");self.update_title()

    def numeric_changed(self,item,fields):
        if not self._building and item.column()==1:self.edit_number(fields[item.row()],item);self.update_graphics()

    def pending_boundary(self,name,key,value):
        if self._building:return
        payload=clone(self.data);pending=payload.setdefault("pending_boundaries",{}).setdefault(name,{})
        pending[key]=value;self.session.change(self.key,payload,"Edit boundary draft");self.update_title()

    def reset_boundary(self,name):
        payload=clone(self.data);payload.setdefault("pending_boundaries",{}).pop(name,None)
        self.session.change(self.key,payload,"Reset boundary draft");self.refresh()

    def apply_boundary(self,name,kind,expression):
        if not expression.strip():raise ReviewError("Enter the boundary expression.")
        payload=clone(self.data);payload.setdefault("boundaries",{})[name]=expression
        payload.setdefault("boundary_types",{})[name]=kind;payload.setdefault("pending_boundaries",{}).pop(name,None)
        payload.update(bc=expression,selection=name);self.session.change(self.key,payload,"Apply boundary condition");self.update_title()

    def preview_mesh(self):
        self.graphics.mesh=True;self.update_graphics();self.update_title("Synthetic mesh preview")

    def node_selected(self):
        if self._building:return
        node=self.tree.currentItem()
        if node and node.text(0) in self.node_names:
            name=node.text(0);self.pages.setCurrentIndex(self.node_names.index(name));self.graphics.set_selected(name)
            if "edge" in name:self.session.edit(self.key,"selection",name)
            self.update_title()

    def graphic_selected(self,name):
        if name in self.node_names:
            self.pages.setCurrentIndex(self.node_names.index(name));self.session.edit(self.key,"selection",name);self.update_title()

    def check(self):
        errors=self.session.diagnostics(self.key);fill_table(self.messages,errors or [["Input","Required values checked; backend equation semantics pending"]])
        if errors:self.input_diagnostics();return False
        self.update_title("Required equation inputs checked");return True

    def evaluate(self):
        if self.data["form"]!="Registered PDE" or self.data["domain"]!="Rectangle":raise ReviewError("The selected extension is not connected. Save and continue editing this model.")
        self.submit_review()

    def update_graphics(self):
        self.graphics.model_width=100*self.data.get("width",1);self.graphics.model_height=100*self.data.get("height",.6)
        self.graphics.mesh_size=self.data["mesh"]*40;self.graphics.field=self.data["field"]+" ["+self.data.get("field_unit","1")+"]";self.graphics.update()

    def refresh(self):
        was=self._building;self._building=True
        self.domain.setCurrentText(self.data["domain"]);self.field_name.setText(self.data["field"]);self.field_unit.setText(self.data.get("field_unit","1"));self.space.setCurrentText(self.data["space"])
        self.form.setCurrentText(self.data["form"])
        mode=self.data["form"]
        self.equation.setPlainText(self.data["equation"] if mode=="Registered PDE" else self.data["weak_form"]["integral"] if mode=="General weak form" else self.data["ode"]["rhs"])
        self.extension_fields=["test","trial","domain","quadrature"] if mode=="General weak form" else ["state","initial","start","stop","step","a","unit"]
        group="weak_form" if mode=="General weak form" else "ode"
        self.extension.setVisible(mode!="Registered PDE");self.coefficients.setVisible(mode!="ODE")
        if mode!="Registered PDE":fill_table(self.extension,[[key.replace("_"," ").title(),self.raw(group+"."+key,self.data[group][key]),"s" if key in ("start","stop","step") else "1/s" if key=="a" else ""] for key in self.extension_fields],(1,))
        self.graphics_tabs.setTabEnabled(1,mode=="ODE")
        fill_table(self.domain_size,[[k.title(),self.raw(k,self.data.get(k,d)),"m"] for k,d in (("width",1),("height",.6))],(1,))
        fill_table(self.mesh_table,[["Element size",self.raw("mesh",self.data["mesh"]),"m"]],(1,))
        fill_table(self.coefficients,[[k,self.raw(k,self.data[k]),"declared"] for k in ("k","f")],(1,))
        for name,kind,expr in self.boundary_pages:
            pending=self.data.get("pending_boundaries",{}).get(name,{})
            kind.setCurrentText(pending.get("type",self.data.get("boundary_types",{}).get(name,"Dirichlet")))
            expr.setText(pending.get("expression",self.data.get("boundaries",{}).get(name,self.data["bc"])))
        self.initial.setText(self.data.get("initial","0"));self.study_type.setCurrentText(self.data.get("study_type","Stationary"));self.time_range.setText(self.data.get("time_range","0:0.1:1"))
        self.graphics.set_selected(self.data["selection"]);self.update_graphics();self._building=was;self.update_title()




class NumericalWindow(ToolWindow):
    def build(self):
        self.method=QComboBox();self.method.addItems(list(METHODS));self.toolbar.addWidget(self.method)
        self.method.currentTextChanged.connect(self.method_changed)
        self.action(self.toolbar,"Check",self.input_diagnostics)
        self.action(self.toolbar,"Run study…",self.submit_review)
        self.action(self.toolbar,"Review candidate…",self.inspect_candidate)
        self.action(self.toolbar,"Open study result",self.open_method_result)
        self.adopt_action=self.action(self.toolbar,"Apply to owners…",self.adopt)
        self.action(self.review_menu,"Refresh saved observations…",self.refresh_observations)
        self.action(self.review_menu,"Show synthetic method results",self.show_method_example)
        self.action(self.review_menu,"Fail next Material adoption save",lambda:self.session.selected.update(inject_material_save_failure=True))
        self.tree=QTreeWidget();self.tree.setHeaderHidden(True)
        root=QTreeWidgetItem(self.tree,[self.document["name"]])
        for name in ("Definition","Variables","Responses","Method","Candidates","Comparisons","Saved selections"):QTreeWidgetItem(root,[name])
        self.tree.expandAll();self.add_dock("Study",self.tree,minimum=190)
        self.evaluator=QComboBox();self.evaluator.addItems(EVALUATORS)
        self.evaluator.currentTextChanged.connect(self.evaluator_changed)
        self.variables=make_table(["Owner","Variable","Start","Lower","Upper","Unit","Free"],[],editable=(2,3,4,6),select_rows=False)
        self.variables.setObjectName("numericalVariables");self.variables.itemChanged.connect(self.variable_changed)
        self.responses=make_table(["Quantity","Role","Limit","Unit","Location","Time [s]","Reduction"],[],editable=(0,1,2,3,4,5,6),select_rows=False)
        self.responses.setObjectName("numericalResponses");self.responses.itemChanged.connect(self.response_changed)
        self.method_table=make_table(["Setting","Value"],[],editable=(1,),select_rows=False)
        self.method_table.itemChanged.connect(self.method_setting_changed)
        self.method_detail=make_table(["Input","Definition","Use"],[],editable=(1,2),select_rows=False)
        self.method_detail.itemChanged.connect(self.detail_changed)
        self.secondary=make_table(["Input","Value"],[],editable=(1,),select_rows=False);self.secondary.itemChanged.connect(self.secondary_changed)
        self.sheet_tabs=QTabWidget()
        self.sheet_tabs.addTab(box(self.method_detail,box(button("Add row",self.add_method_row),button("Remove row",self.remove_method_row),button("Example matrix",self.example_matrix),horizontal=True)),"Definition")
        self.sheet_tabs.addTab(self.secondary,"Checks / pairing")
        self.top_tabs=QTabWidget()
        self.top_tabs.addTab(box(self.variables,box(button("Add variable…",self.add_variable),button("Remove",lambda:self.remove_definition("variables")),horizontal=True)),"Variables")
        self.top_tabs.addTab(box(self.responses,box(button("Add response…",self.add_response),button("Remove",lambda:self.remove_definition("responses")),horizontal=True)),"Responses")
        self.top_tabs.addTab(self.method_table,"Method")
        self.top_tabs.addTab(self.sheet_tabs,"Method inputs")
        self.cases=make_table(["Candidate","Mass [kg]","Error [%]","Disp. [mm]","Clearance [mm]","Status"],[])
        self.cases.setObjectName("candidateTable");self.cases.itemSelectionChanged.connect(self.candidate_changed)
        self.cases.itemDoubleClicked.connect(lambda item:self.guard(self.inspect_candidate))
        self.case_title=QLabel("Retained MOO example")
        self.case_panel=box(self.case_title,self.cases)
        left=QSplitter(Qt.Orientation.Vertical);left.addWidget(self.top_tabs);left.addWidget(self.case_panel);left.setSizes([360,350])
        self.plot=CurveView(xlabel="Mass [kg]",ylabel="Gauge error [%]");self.plot.samplesSelected.connect(self.plot_selected)
        self.curve=CurveView(xlabel="Time [s]",ylabel="Gauge displacement [mm]")
        self.plot_tabs=QTabWidget();self.plot_tabs.addTab(self.plot,"Pareto front");self.plot_tabs.addTab(self.curve,"Selected candidate")
        self.method_view=make_table(["Output","Value","State"],[]);self.plot_tabs.addTab(self.method_view,"Analysis")
        self.summary=make_table(["Response","Selected","Limit"],[["Candidate","p19",""],["Displacement",.31,"≤ 0.35 mm"],["Clearance",.12,"≥ 0.10 mm"]])
        self.summary.setMaximumHeight(145)
        right=box(self.plot_tabs,self.summary)
        split=QSplitter();split.addWidget(left);split.addWidget(right);split.setSizes([720,470])
        evaluator_row=box(QLabel("Evaluator"),self.evaluator,button("Open definition",self.open_evaluator),horizontal=True)
        evaluator_row.setMaximumHeight(38)
        central=box(evaluator_row,split,margins=6);central.layout().setStretch(1,1);self.setCentralWidget(central)
        self.tree.itemSelectionChanged.connect(self.tree_changed);self.refresh();QTimer.singleShot(0,self.candidate_changed)

    def evaluator_changed(self,value):
        if self._building:return
        self.session.edit(self.key,"evaluator",value);self.update_title()

    def open_evaluator(self):
        target={"Clamp / material response":"simulation","Structural Simulation":"simulation","Material response":"material","PDE response":"pde","Thermal expansion Evaluation":"evaluation"}.get(self.evaluator.currentText())
        if not target:raise ReviewError("Select an evaluator first.")
        self.hub.open(target)

    def add_variable(self):
        dialog=QDialog(self);dialog.setWindowTitle("Bind variable");form=QFormLayout(dialog)
        owner=QComboBox();owner.addItems(list(VARIABLE_BINDINGS));field=QComboBox();unit=QLabel()
        start=QLineEdit();lower=QLineEdit();upper=QLineEdit()
        def update_field(*args):
            key=owner.currentText();fields=VARIABLE_BINDINGS[key];field.blockSignals(True);field.clear();field.addItems(fields);field.blockSignals(False);update_value()
        def update_value(*args):
            key=owner.currentText();name=field.currentText()
            if not name:return
            value=self.session.doc(key)["draft"]
            for part in name.split("."):value=value[part]
            unit.setText(VARIABLE_BINDINGS[key][name]);start.setText(str(value))
            values=sorted((value*.8,value*1.2));lower.setText(str(values[0] if value else -1));upper.setText(str(values[1] if value else 1))
        owner.currentTextChanged.connect(update_field);field.currentTextChanged.connect(update_value);update_field()
        for label,w in (("Owner",owner),("Field",field),("Unit",unit),("Start",start),("Search lower",lower),("Search upper",upper)):form.addRow(label,w)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            payload=clone(self.data)
            if any(v["owner"]==owner.currentText() and v["field"]==field.currentText() for v in payload["variables"]):raise ReviewError("This owner field is already a variable.")
            payload["variables"].append({"owner":owner.currentText(),"field":field.currentText(),"unit":unit.text(),
                "start":numeric_draft(start.text()),"lower":numeric_draft(lower.text()),"upper":numeric_draft(upper.text()),"free":True,"type":"float"})
            doc=self.session.doc(owner.currentText());payload["sources"][owner.currentText()]={"id":doc["id"],"revision":doc["revision"]}
            self.session.change(self.key,payload,"Bind research variable");self.refresh();self.top_tabs.setCurrentIndex(0)

    def add_response(self):
        dialog=QDialog(self);dialog.setWindowTitle("Define response");form=QFormLayout(dialog)
        units={"Mass":"kg","Gauge error":"%","Displacement":"mm","Clearance":"mm","Normal force":"N","Stress residual":"MPa","Temperature":"K","Compliance":"N mm","Damage":"1"}
        quantity=QComboBox();quantity.addItems(units);role=QComboBox();role.addItems(RESPONSE_ROLES)
        limit=QLineEdit();unit=QLabel(units[quantity.currentText()]);location=QLineEdit("Global")
        time=QLineEdit("0.04");reduction=QComboBox();reduction.addItems(["Value at time","Maximum","Minimum","Mean","RMS","Integral"])
        quantity.currentTextChanged.connect(lambda v:unit.setText(units[v]))
        for label,w in (("Quantity",quantity),("Role",role),("Limit / target",limit),("Unit",unit),("Location",location),("Time [s]",time),("Reduction",reduction)):form.addRow(label,w)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            payload=clone(self.data);payload["responses"].append({"name":quantity.currentText(),"role":role.currentText(),"unit":unit.text(),
                "limit":numeric_draft(limit.text()) if limit.text().strip() else "","location":location.text(),"time":numeric_draft(time.text()),"reduction":reduction.currentText()})
            self.session.change(self.key,payload,"Define response");self.refresh();self.top_tabs.setCurrentIndex(1)

    def remove_definition(self,kind):
        table=self.variables if kind=="variables" else self.responses;row=table.currentRow()
        if row<0:return
        payload=clone(self.data);payload[kind].pop(row)
        prefix=kind+".";buffers={}
        for key,value in self.document["buffers"].items():
            if key.startswith(prefix):
                parts=key.split(".");index=int(parts[1])
                if index==row:continue
                if index>row:parts[1]=str(index-1)
                key=".".join(parts)
            buffers[key]=value
        self.session.change(self.key,payload,"Remove "+kind[:-1],buffers=buffers);self.refresh()

    def method_changed(self,method):
        if self._building:return
        self.session.edit(self.key,"method",method);self.refresh();self.top_tabs.setCurrentIndex(2)

    def variable_changed(self,item):
        if self._building:return
        field={2:"start",3:"lower",4:"upper",6:"free"}.get(item.column())
        if field is None:return
        locator=f"variables.{item.row()}.{field}";payload=clone(self.data)
        try:
            if field=="free":
                if item.text().lower() not in ("yes","no","true","false","1","0"):raise ValueError()
                value=item.text().lower() in ("yes","true","1")
            else:value=number(item.text())
        except ValueError:
            self.retain_input(locator,item.text());mark_invalid(item,True);self.update_title("Correct variable value before freeze");return
        buffers=clone(self.document["buffers"]);buffers.pop(locator,None);payload["variables"][item.row()][field]=value
        self.session.change(self.key,payload,"Edit variable "+field,buffers=buffers);mark_invalid(item,False);self.update_title()

    def response_changed(self,item):
        if self._building:return
        field=["name","role","limit","unit","location","time","reduction"][item.column()];text=item.text()
        payload=clone(self.data);locator=f"responses.{item.row()}.{field}"
        try:value=number(text) if field in ("limit","time") and text.strip() else text
        except ValueError:value=text
        payload["responses"][item.row()][field]=value
        self.session.change(self.key,payload,"Edit response "+field)
        invalid=(field=="role" and value not in RESPONSE_ROLES) or (field in ("limit","time") and bool(text) and not isinstance(value,(int,float)))
        mark_invalid(item,invalid);self.update_title()

    def method_setting_changed(self,item):
        if self._building or item.column()!=1:return
        if item.row()<2:self.edit_number(["budget","seed"][item.row()],item);return
        name,default=METHOD_INPUTS[self.data["method"]][item.row()-2]
        payload=clone(self.data);locator="method."+self.data["method"]+"."+name
        try:value=number(item.text()) if isinstance(default,(int,float)) else item.text()
        except ValueError:
            self.retain_input(locator,item.text());mark_invalid(item,True);self.update_title();return
        buffers=clone(self.document["buffers"]);buffers.pop(locator,None)
        payload.setdefault("method_settings",{}).setdefault(self.data["method"],{})[name]=value
        self.session.change(self.key,payload,"Edit method input",buffers=buffers);mark_invalid(item,False);self.update_title()

    def worksheet(self):
        return method_sheet(self.data, self.session.candidates, self.session.pareto_ids())

    def detail_changed(self,item):
        if self._building:return
        rows=[[(self.method_detail.item(r,c).text() if self.method_detail.item(r,c) else "") for c in range(self.method_detail.columnCount())] for r in range(self.method_detail.rowCount())]
        payload=clone(self.data);payload.setdefault("method_sheets",{}).setdefault(self.data["method"],{})["primary"]=rows
        sheet=payload["method_sheets"][self.data["method"]];sheet["bindings"]=binding_ids(self.data["variables"])
        if self.data["method"]=="MOO":
            for response,row in zip(payload["responses"],rows):
                response["name"],response["limit"],response["role"]=row
        self.session.change(self.key,payload,"Edit "+self.data["method"]+" definition");self.update_title()

    def secondary_changed(self,item):
        if self._building:return
        rows=[[(self.secondary.item(r,c).text() if self.secondary.item(r,c) else "") for c in range(self.secondary.columnCount())] for r in range(self.secondary.rowCount())]
        payload=clone(self.data);payload.setdefault("method_sheets",{}).setdefault(self.data["method"],{})["secondary"]=rows
        self.session.change(self.key,payload,"Edit "+self.data["method"]+" pairing / support");self.update_title()

    def add_method_row(self):
        if self.data["method"]=="MOO":return self.add_response()
        headers,defaults,_,_=self.worksheet();rows=self.data.get("method_sheets",{}).get(self.data["method"],{}).get("primary",defaults)
        rows=clone(rows);rows.append([""]*len(headers));payload=clone(self.data)
        payload.setdefault("method_sheets",{}).setdefault(self.data["method"],{})["primary"]=rows
        self.session.change(self.key,payload,"Add method input row");self.refresh();self.top_tabs.setCurrentIndex(3)

    def remove_method_row(self):
        row=self.method_detail.currentRow()
        if row<0:return
        if self.data["method"]=="MOO":
            self.responses.setCurrentCell(row,0);return self.remove_definition("responses")
        _,defaults,_,_=self.worksheet();rows=clone(self.data.get("method_sheets",{}).get(self.data["method"],{}).get("primary",defaults));rows.pop(row)
        payload=clone(self.data);payload.setdefault("method_sheets",{}).setdefault(self.data["method"],{})["primary"]=rows
        self.session.change(self.key,payload,"Remove method input row");self.refresh();self.top_tabs.setCurrentIndex(3)

    def example_matrix(self):
        method=self.data["method"];variables=self.data["variables"]
        if method in ("DOE","Optimization","RBF surrogate"):
            fractions=[.125,.625,.875,.375];rows=[]
            for i in range(4):
                values=[round(v["lower"]+(v["upper"]-v["lower"])*fractions[(i+2*j)%4],8) for j,v in enumerate(variables)]
                rows.append(["d"+str(i+1)]+values+([round(.4+.025*i,4),"Train" if i<3 else "Holdout"] if method=="RBF surrogate" else ["Yes"]))
        elif method=="Sobol sensitivity":
            base=[[v["lower"]+.25*(v["upper"]-v["lower"]) for v in variables],[v["lower"]+.75*(v["upper"]-v["lower"]) for v in variables]]
            other=list(reversed(base));rows=[[block,i+1]+clone(values) for block,matrix in (("A",base),("B",other)) for i,values in enumerate(matrix)]
            for j,v in enumerate(variables):
                for i in range(2):
                    values=clone(base[i]);values[j]=other[i][j];rows.append(["A_B:"+v["field"],i+1]+values)
        else:rows=self.worksheet()[1]
        payload=clone(self.data);payload.setdefault("method_sheets",{}).setdefault(method,{})["primary"]=rows
        payload["method_sheets"][method]["origin"]="AUTHORED_SYNTHETIC_EXAMPLE"
        payload["method_sheets"][method]["bindings"]=binding_ids(variables)
        if method=="DOE":payload.setdefault("method_settings",{}).setdefault(method,{})["Design points"]=4
        if method=="Sobol sensitivity":payload.setdefault("method_settings",{}).setdefault(method,{})["Base samples"]=2
        self.session.change(self.key,payload,"Load authored method matrix");self.refresh();self.top_tabs.setCurrentIndex(3)

    def show_method_example(self, record=True):
        if self.has_fixture():self.plot_tabs.setCurrentIndex(0);return
        method=self.data["method"];examples=json.loads((HERE/"fixtures"/"methods.json").read_text(encoding="utf-8"))
        fixture=examples[method]
        if record:self.session.edit(self.key,"method_example",method)
        fill_table(self.method_view,[[name,value,"Synthetic example"] for name,value in fixture["summary"]])
        self.plot.xlabel=fixture["xlabel"];self.plot.ylabel=fixture["ylabel"];self.plot.caption="Authored synthetic example / not evaluated"
        self.plot.set_series(fixture["series"]);self.plot_tabs.setTabText(0,fixture["view"]);self.plot_tabs.setTabEnabled(0,True);self.plot_tabs.setCurrentIndex(0)
        self.update_title("Synthetic "+method+" results example")

    def open_method_result(self):
        result_id=self.data.get("method_result")
        if not result_id:
            found=[r for r in self.session.results.values() if r.get("kind")=="numerical" and r["source"]["id"]==self.document["id"]]
            if found:result_id=found[-1]["id"]
        if not result_id:raise ReviewError("Create a review attempt, then use Runner / Review / Load retained result fixture.")
        return self.hub.open_result(result_id)

    def refresh_observations(self):
        data=self.session.doc("data");used=len(data["saved"]["samples"])-len(data["saved"]["quality_excluded"])
        if QMessageBox.question(self,"Refresh observations",f"Use saved {data['name']} with {used} included samples?")==QMessageBox.StandardButton.Yes:
            self.session.refresh_data_source(self.key);self.refresh()

    def has_fixture(self):
        return self.document["id"]=="N-MOO" and self.data["method"]=="MOO"

    def candidate_changed(self):
        if self._building or not self.has_fixture():return
        row=self.cases.currentRow()
        if row<0:return
        cid=self.cases.item(row,0).text();self.session.selected["candidate"]=cid
        c=next(c for c in self.session.candidates if c["id"]==cid);self.plot.select_ids([cid])
        fill_table(self.summary,[["Candidate",cid,""],["Displacement",c["displacement"],"≤ 0.35 mm"],["Clearance",c["clearance"],"≥ 0.10 mm"]])
        if not c.get("result_ref"):
            self.curve.set_series([]);self.curve.caption=c["diagnostic"]
        else:
            result=self.session.results[c["result_ref"]]
            self.curve.set_series([{"name":cid+" fixture","x":result["times"],"y":result["fields"]["Displacement"]["values"],"color":BLUE}])
            self.curve.caption="Retained synthetic response"
        self.update_title(cid+"   |   "+c["status"])

    def plot_selected(self,ids):
        if not ids:return
        for row in range(self.cases.rowCount()):
            if self.cases.item(row,0).text()==ids[0]:self.cases.selectRow(row);return

    def inspect_candidate(self):
        if not self.has_fixture():raise ReviewError("No evaluated candidate is retained for this method. Complete the definition and review its input first.")
        cid=self.session.selected.get("candidate","p19");c=next(c for c in self.session.candidates if c["id"]==cid)
        dialog=QDialog(self);dialog.setWindowTitle("Candidate "+cid);dialog.resize(780,490);layout=QVBoxLayout(dialog)
        layout.addWidget(make_table(["Input / response","Value"],[[k,v] for k,v in c.items() if k not in ("plan_ref",)]))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        opened=buttons.addButton("Open retained result",QDialogButtonBox.ButtonRole.ActionRole);opened.setEnabled(bool(c["result_ref"]))
        opened.clicked.connect(lambda:self.hub.open_result(c["result_ref"]));buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec()

    def adopt(self):
        if not self.has_fixture():raise ReviewError("Select a retained candidate from its original MOO plan.")
        group=self.session.prepare_adoption(self.session.selected.get("candidate","p19"));self.hub.adoption_dialog(self,group["id"])

    def tree_changed(self):
        item=self.tree.currentItem()
        if not item:return
        name=item.text(0)
        if name in ("Variables","Responses","Method"):self.top_tabs.setCurrentIndex(("Variables","Responses","Method").index(name))
        if name=="Saved selections":self.hub.receipts(self)

    def refresh(self):
        was=self._building;self._building=True
        self.method.setCurrentText(self.data["method"]);self.evaluator.setCurrentText(self.data["evaluator"])
        rows=[]
        for i,v in enumerate(self.data["variables"]):
            rows.append([v["owner"],v["field"]]+[self.raw(f"variables.{i}.{k}",v[k]) for k in ("start","lower","upper")]+[v["unit"],self.raw(f"variables.{i}.free","Yes" if v["free"] else "No")])
        fill_table(self.variables,rows,(2,3,4,6))
        fill_table(self.responses,[[r["name"],r["role"],r["limit"],r["unit"],str(r.get("location","Global")),r.get("time",.04),r.get("reduction","Value at time")] for r in self.data["responses"]],(0,1,2,3,4,5,6))
        method=self.data["method"];settings=self.data.get("method_settings",{}).get(method,{})
        rows=[["Total evaluation budget",self.raw("budget",self.data["budget"])],["Seed",self.raw("seed",self.data["seed"])]]
        rows += [[name,self.raw("method."+method+"."+name,settings.get(name,value))] for name,value in METHOD_INPUTS[method]]
        fill_table(self.method_table,rows,(1,))
        headers,defaults,secondary_headers,secondary_defaults=self.worksheet();sheet=self.data.get("method_sheets",{}).get(method,{})
        self.method_detail.setColumnCount(len(headers));self.method_detail.setHorizontalHeaderLabels(headers)
        fill_table(self.method_detail,defaults if method=="MOO" else sheet.get("primary",defaults),tuple(range(len(headers))))
        if getattr(self,"_sheet_layout_method",None)!=method:
            for table in (self.variables,self.responses,self.method_table,self.method_detail):
                table.resizeColumnsToContents()
            self._sheet_layout_method=method
        self.secondary.setColumnCount(len(secondary_headers));self.secondary.setHorizontalHeaderLabels(secondary_headers)
        fill_table(self.secondary,sheet.get("secondary",secondary_defaults),tuple(range(1,len(secondary_headers))) if method in ("UQ","MDO","RBF surrogate") else ())
        self.sheet_tabs.setTabText(1,{"UQ":"Correlations","Sobol sensitivity":"Pairing","RBF surrogate":"Validation / support","MDO":"Transfer"}.get(method,"Definition checks"))
        self.top_tabs.setTabText(3,METHODS[method][0])
        fill_table(self.method_view,[[name,None,"NOT_EVALUATED"] for name in METHODS[method][1:]])
        fixture=self.has_fixture();self.case_panel.setVisible(fixture);self.summary.setVisible(fixture);self.adopt_action.setEnabled(fixture)
        self.plot_tabs.setTabText(0,"Pareto front");self.plot.xlabel="Mass [kg]";self.plot.ylabel="Gauge error [%]"
        self.plot_tabs.setTabEnabled(0,fixture);self.plot_tabs.setTabEnabled(1,fixture);self.plot_tabs.setCurrentIndex(0 if fixture else 2)
        fill_table(self.cases,[[c[k] if c[k] is not None else "—" for k in ("id","mass","error","displacement","clearance","status")] for c in self.session.candidates] if fixture else [])
        valid=[c for c in self.session.candidates if c["mass"] is not None and c["error"] is not None]
        front=set(self.session.pareto_ids())
        self.plot.set_series([{"name":"All evaluated candidates","x":[c["mass"] for c in valid],"y":[c["error"] for c in valid],"ids":[c["id"] for c in valid],"color":"#8b98a4","scatter":True},{"name":"Non-dominated feasible","x":[c["mass"] for c in valid if c["id"] in front],"y":[c["error"] for c in valid if c["id"] in front],"ids":[c["id"] for c in valid if c["id"] in front],"color":TEAL,"scatter":True}] if fixture else [])
        self._building=was
        if fixture:self.plot_selected([self.session.selected.get("candidate","p19")]);self.candidate_changed()
        elif self.data.get("method_example")==method:self.show_method_example(record=False)
        self.update_title()


class RunnerWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Open input",self.open_input)
        self.action(self.toolbar,"Execution target…",self.execution_target)
        self.action(self.toolbar,"Open result",self.open_result)
        self.action(self.toolbar,"Cancel…",self.cancel_job)
        self.action(self.toolbar,"Reconnect",lambda:self.review_event("reconnect"))
        self.action(self.review_menu,"Load running state fixture",lambda:self.review_event("running"))
        self.action(self.review_menu,"Load failed state fixture",lambda:self.review_event("failed"))
        self.action(self.review_menu,"Load retained result fixture",lambda:self.review_event("result"))
        self.action(self.review_menu,"Load terminal cancel receipt",lambda:self.review_event("terminal"))
        self.action(self.review_menu,"Simulate connection loss",lambda:self.review_event("disconnect"))
        self.action(self.review_menu,"Create review attempt from saved Simulation",self.seed_attempt)
        self.action(self.review_menu,"Retry unchanged input as new review attempt",self.retry)
        self.jobs=make_table(["Job","Source","Status","Connection","Result"],[])
        self.jobs.itemSelectionChanged.connect(self.select_job)
        self.jobs.itemDoubleClicked.connect(lambda item:self.guard(self.open_input))
        self.tabs=QTabWidget()
        self.input=make_table(["Frozen input","Value"],[])
        self.log=QPlainTextEdit();self.log.setReadOnly(True)
        log_font=QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont);log_font.setPointSize(10);self.log.setFont(log_font)
        self.diagnostics=make_table(["Scope","Message"],[])
        self.result=make_table(["Result quantity","Value","Unit"],[])
        for view,name in [(self.input,"Input"),(self.log,"Log"),(self.diagnostics,"Diagnostics"),(self.result,"Results")]:
            self.tabs.addTab(view,name)
        self.monitor=CurveView(xlabel="Iteration",ylabel="Relative residual")
        self.monitor_table=make_table(["Increment","Iteration","Time [s]","Residual","Cutback"],[])
        monitor_split=QSplitter();monitor_split.addWidget(self.monitor_table);monitor_split.addWidget(self.monitor);monitor_split.setSizes([550,700])
        self.tabs.addTab(monitor_split,"Convergence / energy")
        split=QSplitter(Qt.Orientation.Vertical);split.addWidget(self.jobs);split.addWidget(self.tabs);split.setSizes([370,390])
        self.setCentralWidget(split);self.refresh()

    def execution_target(self):
        dialog=QDialog(self);dialog.setWindowTitle("Execution target");form=QFormLayout(dialog)
        source=self.data.get("target",{});target=QComboBox();target.addItems(["Local","Existing remote"]);target.setCurrentText(source.get("kind","Local"))
        host=QLineEdit(source.get("host",""));host.setPlaceholderText("Configured host alias");cores=QSpinBox();cores.setRange(1,256);cores.setValue(source.get("cores",4))
        queue=QLineEdit(source.get("queue",""))
        for label,w in (("Target",target),("Host",host),("Processes",cores),("Queue",queue)):form.addRow(label,w)
        form.addRow(QLabel("Connection / scheduler admission unverified. No process is submitted."))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.session.edit(self.key,"target",{"kind":target.currentText(),"host":host.text(),"cores":cores.value(),"queue":queue.text(),"status":"UNVERIFIED"});self.update_title()

    def current_job(self):
        row=self.jobs.currentRow()
        if row<0:raise ReviewError("Select a review attempt. No job is submitted by opening this window.")
        jid=self.jobs.item(row,0).data(Qt.ItemDataRole.UserRole)
        return next(j for j in self.session.jobs if j["id"]==jid)

    def seed_attempt(self):
        frozen=self.session.freeze("simulation");job=self.session.create_attempt(frozen["id"])
        self.session.selected["job"]=job["id"];self.refresh()

    def retry(self):
        job=self.current_job()
        if job["status"] not in ("FAILED","CANCELLED"):
            raise ReviewError("Retry applies to a failed or cancelled review attempt.")
        new=self.session.create_attempt(job["input"])
        self.session.selected["job"]=new["id"];self.refresh()

    def review_event(self,event):
        job=self.current_job()
        self.session.job_event(job["id"],event);self.refresh()

    def cancel_job(self):
        job=self.current_job()
        if QMessageBox.question(self,"Request cancel",
            "Request cancellation for this selected review attempt?\nA request does not mean terminal cancellation.")==QMessageBox.StandardButton.Yes:
            self.session.job_event(job["id"],"cancel");self.refresh()

    def select_job(self):
        if self.jobs.currentRow()<0:return
        job=self.current_job();self.session.selected["job"]=job["id"]
        frozen=self.session.frozen[job["input"]]
        rows=[["Document",job["name"]],["Saved revision",job["source"]["revision"]],
              ["Attempt",job["attempt"]],["Execution","NOT_EXECUTED / review fixture"]]
        if "included_count" in frozen:rows.append(["Frozen samples",frozen["included_count"]])
        self.input.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,value in enumerate(row):self.input.setItem(i,j,QTableWidgetItem(str(value)))
        self.log.setPlainText("\n".join(job["log"]))
        messages=[["Status",job["status"]],["Connection","Connected review state" if job["connected"] else "Disconnected; terminal status unknown"],
                  ["Native process","None was started"]]
        self.diagnostics.setRowCount(len(messages))
        for i,row in enumerate(messages):
            for j,value in enumerate(row):self.diagnostics.setItem(i,j,QTableWidgetItem(value))
        self.result.setRowCount(0)
        if job["result"]:
            result=self.session.results[job["result"]]
            if result.get("kind")=="numerical":
                fill_table(self.result,[[name,value,""] for name,value in result["fixture"]["summary"]])
            for i,(key,value) in enumerate(result.get("metrics",{}).items()):
                self.result.insertRow(i)
                for j,text in enumerate([key,str(value),"kg" if key=="mass" else "mm"]):
                    self.result.setItem(i,j,QTableWidgetItem(text))
        loaded=job["status"] in ("RUNNING_FIXTURE","FAILED","CANCEL_REQUESTED","CANCELLED","RETAINED_FIXTURE")
        family=frozen["payload"].get("family","")
        if loaded and family=="Explicit impact":
            self.monitor.xlabel="Time [s]";self.monitor.ylabel="Energy [J]"
            self.monitor.set_series([{"name":"Kinetic example","x":[0,.01,.02,.04],"y":[.32,.21,.12,.04],"color":BLUE},
                {"name":"Internal example","x":[0,.01,.02,.04],"y":[0,.08,.16,.23],"color":TEAL},
                {"name":"Contact work example","x":[0,.01,.02,.04],"y":[0,.025,.035,.045],"color":ORANGE}])
            self.monitor_table.setHorizontalHeaderLabels(["Time [s]","Kinetic [J]","Internal [J]","Contact [J]","State"])
            fill_table(self.monitor_table,[[0,.32,0,0,"Synthetic"],[.01,.21,.08,.025,"Synthetic"],[.02,.12,.16,.035,"Synthetic"],[.04,.04,.23,.045,"Synthetic"]])
        elif loaded:
            self.monitor.xlabel="Newton iteration";self.monitor.ylabel="Relative residual"
            self.monitor.set_series([{"name":"Synthetic residual","x":[1,2,3,4,5],"y":[.085,.022,.0038,.00012,8e-7],"color":BLUE}])
            self.monitor_table.setHorizontalHeaderLabels(["Increment","Iteration","Time [s]","Residual","Cutback"])
            fill_table(self.monitor_table,[[7,i,.14,v,"No"] for i,v in enumerate([.085,.022,.0038,.00012,8e-7],1)])
        else:self.monitor.set_series([]);fill_table(self.monitor_table,[])
        self.monitor.caption="Authored monitor example / no solver run"
        self.update_title(job["status"]+"   |   "+job["name"])

    def open_input(self):
        job=self.current_job()
        frozen=self.session.frozen[job["input"]]
        text_dialog(self,"Frozen input — "+job["name"],json.dumps(frozen,ensure_ascii=False,indent=2))

    def open_result(self):
        job=self.current_job()
        if not job["result"]:raise ReviewError("No retained result exists for this attempt.")
        self.hub.open_result(job["result"])

    def refresh(self):
        selected=self.session.selected.get("job")
        self.jobs.blockSignals(True);self.jobs.setRowCount(len(self.session.jobs));target=0
        for r,job in enumerate(self.session.jobs):
            row=[job["name"],self.session.doc(job["source"]["id"])["owner"],job["status"],
                 "Available" if job["connected"] else "Disconnected",
                 "Retained" if job["result"] else "None"]
            for c,value in enumerate(row):
                item=QTableWidgetItem(value)
                if c==0:item.setData(Qt.ItemDataRole.UserRole,job["id"])
                item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable);self.jobs.setItem(r,c,item)
            if job["id"]==selected:target=r
        self.jobs.blockSignals(False)
        if self.session.jobs:self.jobs.selectRow(target);self.select_job()
        else:self.update_title("No jobs. Open a saved input to create a review attempt.")


class PostWindow(ToolWindow):
    def build(self):
        self.array=QComboBox();self.array.addItems(["Displacement","Contact pressure","Normal force","Slip (unavailable)"])
        self.association=QComboBox();self.association.addItems(["POINTS","CELLS","FIELD"])
        self.time=QComboBox()
        for t in self.result().get("times",[]):self.time.addItem(f"{t:.3f} s",t)
        self.toolbar.addWidget(self.array);self.toolbar.addWidget(self.association);self.toolbar.addWidget(self.time)
        self.action(self.toolbar,"Compare…",self.compare);self.action(self.toolbar,"Measure…",self.measure_dialog)
        self.action(self.toolbar,"Pick gauge",self.pick_gauge);self.action(self.toolbar,"Register response…",self.register_response)
        self.action(self.toolbar,"Use in Numerical…",self.to_numerical);self.action(self.toolbar,"Source…",self.source)
        self.viewer=EngineeringView("post");self.curve=CurveView(xlabel="Time [s]",ylabel="Displacement [mm]")
        self.measure=make_table(["Measurement","Value","Unit","Location"],[]);self.measure.setObjectName("postMeasurements")
        self.bottom=QTabWidget();self.bottom.addTab(self.curve,"Curve");self.bottom.addTab(self.measure,"Measurements")
        split=QSplitter(Qt.Orientation.Vertical);split.addWidget(self.viewer);split.addWidget(self.bottom);split.setSizes([500,250]);self.setCentralWidget(split)
        self.pipeline=QTreeWidget();self.pipeline.setHeaderHidden(True)
        source=QTreeWidgetItem(self.pipeline,[self.document["name"]])
        for name in ("Surface","Contact pair","Gauge endpoints"):QTreeWidgetItem(source,[name])
        self.pipeline.expandAll();self.filter=QComboBox();self.filter.addItems(["Surface","Clip","Slice","Warp by vector","Plot over line"])
        self.filter.currentTextChanged.connect(self.pending_filter)
        self.props=make_table(["Property","Value"],[["Deformation scale",10],["Coordinate system","Global Cartesian"],["Unit","mm"]],editable=(1,),select_rows=False)
        self.props.itemChanged.connect(self.property_changed)
        pane=box(self.pipeline,QLabel("Properties"),self.filter,button("Filter settings…",self.filter_settings),self.props,box(button("Apply",self.apply_filter),button("Reset",self.reset_filter),horizontal=True),margins=6)
        dock=self.add_dock("Pipeline Browser",pane,minimum=285);self.resizeDocks([dock],[320],Qt.Orientation.Horizontal)
        self.array.currentTextChanged.connect(self.field_changed);self.association.currentTextChanged.connect(self.association_changed)
        self.time.currentIndexChanged.connect(self.time_changed);self.pipeline.itemSelectionChanged.connect(self.pipeline_selected)
        self.viewer.faceSelected.connect(self.face_selected);self.viewer.pointSelected.connect(self.picked_point);self.refresh()

    def result(self):
        return self.session.results.get(self.data["result"],{})

    def field_changed(self,value):
        if self._building:return
        payload=clone(self.data);field=self.result().get("fields",{}).get(value)
        payload.update(array=value,unit=field["unit"] if field else "mm",association=field["association"] if field else "POINTS")
        self.session.change(self.key,payload,"Select result field");self.refresh()

    def association_changed(self,value):
        if not self._building:self.session.edit(self.key,"association",value);self.render_frame();self.update_title()

    def time_changed(self,index):
        if not self._building and index>=0:
            self.session.edit(self.key,"time",self.time.itemData(index));self.render_frame();self.update_title("Time "+self.time.currentText())

    def pending_filter(self,value):
        if not self._building:self.session.edit(self.key,"pending_filter",value);self.update_title("Filter properties changed; Apply to preview")

    def property_changed(self,item):
        if self._building or item.column()!=1:return
        if item.row()==0:self.edit_number("deformation_scale",item)
        else:self.refresh();self.update_title("Field unit and coordinate basis come from the selected result")

    def apply_filter(self):
        payload=clone(self.data);payload["filter"]=payload["pending_filter"]
        payload["filter_parameters"]=clone(payload.get("pending_filter_parameters",{}))
        self.session.change(self.key,payload,"Apply filter settings");self.render_frame();self.update_title(self.data["filter"]+" illustration applied")

    def reset_filter(self):
        payload=clone(self.data);payload["pending_filter"]=payload["filter"];payload["pending_filter_parameters"]=clone(payload.get("filter_parameters",{}))
        self.session.change(self.key,payload,"Reset filter settings");self.refresh()

    def filter_settings(self):
        dialog=QDialog(self);dialog.setWindowTitle(self.data["pending_filter"]+" settings");form=QFormLayout(dialog)
        settings=self.data.get("pending_filter_parameters",self.data.get("filter_parameters",{}))
        axis=QComboBox();axis.addItems(["X","Y","Z"]);axis.setCurrentText(settings.get("axis","X"))
        offset=QLineEdit(str(settings.get("offset",0)));scale=QLineEdit(str(settings.get("scale",self.data["deformation_scale"])))
        start=QLineEdit(str(settings.get("start",0)));end=QLineEdit(str(settings.get("end",50)));samples=QLineEdit(str(settings.get("samples",21)))
        vector=QComboBox();vector.addItem("Displacement [mm]")
        mode=self.data["pending_filter"]
        if mode in ("Clip","Slice"):form.addRow("Plane normal",axis);form.addRow("Origin [mm]",offset)
        elif mode=="Warp by vector":form.addRow("Vector field",vector);form.addRow("Scale",scale)
        elif mode=="Plot over line":form.addRow("Gauge start [mm]",start);form.addRow("Gauge end [mm]",end);form.addRow("Sample points",samples)
        else:form.addRow(QLabel("Surface representation"))
        error=QLabel();form.addRow(error);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        keep=buttons.addButton("Use settings",QDialogButtonBox.ButtonRole.AcceptRole)
        def accept():
            try:
                values={"axis":axis.currentText(),"offset":number(offset.text()),"scale":number(scale.text()),"vector":"Displacement",
                        "start":number(start.text()),"end":number(end.text()),"samples":number(samples.text())}
                if not 2<=values["samples"]<=501 or not values["samples"].is_integer():raise ReviewError("Use 2–501 integer sample points.")
                if not 0<=values["start"]<values["end"]<=50:raise ReviewError("The retained gauge line spans 0–50 mm.")
                if values["scale"]<0:raise ReviewError("Use a nonnegative deformation scale.")
                self.session.edit(self.key,"pending_filter_parameters",values);self.update_title("Filter settings ready to Apply");dialog.accept()
            except (ValueError,ReviewError) as e:error.setText(str(e))
        keep.clicked.connect(accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons);dialog.exec()

    def pick_gauge(self):
        self.pick_points=[];self.viewer.point_pick=True;self.viewer.update();self.update_title("Pick point A, then point B in the view")

    def picked_point(self,name):
        self.pick_points.append(name)
        if len(self.pick_points)==2:
            self.session.edit(self.key,"gauge",{"a":self.pick_points[0],"b":self.pick_points[1],"direction":"X"})
            self.viewer.point_pick=False;self.render_frame();self.bottom.setCurrentIndex(1);self.update_title("Gauge measurement selected")
        else:self.update_title(name+" selected; pick point B")

    def register_response(self):
        row=self.measure.currentRow()
        if row<0:row=0
        if self.measure.item(row,1).text()=="Unavailable":raise ReviewError("The selected measurement has no value in this frame.")
        quantity=["Displacement","Contact pressure","Normal force"][row]
        dialog=QDialog(self);dialog.setWindowTitle("Use measurement in Numerical");form=QFormLayout(dialog)
        role=QComboBox();role.addItems(RESPONSE_ROLES);role.setCurrentText("Upper bound");limit=QLineEdit(self.measure.item(row,1).text())
        form.addRow("Quantity",QLabel(quantity));form.addRow("Unit",QLabel(self.measure.item(row,2).text()));form.addRow("Role",role);form.addRow("Limit",limit)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            payload=clone(self.session.doc("numerical")["draft"]);payload["responses"].append({"name":quantity,"role":role.currentText(),"limit":number(limit.text()),
                "unit":self.measure.item(row,2).text(),"time":self.data["time"],"location":clone(self.data.get("gauge",{})) if row==0 else "Contact surface",
                "reduction":"Two-point difference" if row==0 else "Resultant" if row==2 else "Maximum","result_ref":self.data["result"]})
            self.session.change("numerical",payload,"Register selected measurement response");self.hub.open("numerical").top_tabs.setCurrentIndex(1)

    def pipeline_selected(self):
        if self._building:return
        item=self.pipeline.currentItem()
        if item:
            self.session.edit(self.key,"selection",item.text(0));self.viewer.set_selected(item.text(0));self.update_title()
            if item.text(0)=="Gauge endpoints":self.bottom.setCurrentIndex(1)

    def face_selected(self,name):
        self.session.edit(self.key,"selection",name);self.update_title("Selected "+name)

    def source(self):
        text_dialog(self,"Exact result source",json.dumps(self.result(),ensure_ascii=False,indent=2))

    def to_numerical(self):
        if QMessageBox.question(self,"Use result in Numerical","Use the selected retained result as the comparison baseline?")==QMessageBox.StandardButton.Yes:
            self.session.edit("numerical","baseline_result",self.data["result"]);self.hub.open("numerical").refresh()

    def measure_dialog(self):
        dialog=QDialog(self);dialog.setWindowTitle("Gauge measurement");form=QFormLayout(dialog)
        source=self.data.get("gauge",{"a":"Gauge left","b":"Gauge right","direction":"X"});endpoints=["Gauge left","Gauge right","Clamp centre"]
        a=QComboBox();a.addItems(endpoints);a.setCurrentText(source["a"]);b=QComboBox();b.addItems(endpoints);b.setCurrentText(source["b"])
        direction=QComboBox();direction.addItems(["X","Y","Z","Magnitude"]);direction.setCurrentText(source["direction"])
        for label,w in (("Point A",a),("Point B",b),("Direction",direction)):form.addRow(label,w)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.session.edit(self.key,"gauge",{"a":a.currentText(),"b":b.currentText(),"direction":direction.currentText()})
            self.render_frame();self.bottom.setCurrentIndex(1);self.update_title()

    def render_frame(self):
        frame=self.session.post_frame(self.key)
        self.viewer.field=self.data["array"]+" ["+frame["unit"]+"]   t = "+str(frame["time"])+" s"
        self.viewer.field_available=frame["available"];self.viewer.field_max=frame["value"] or 0
        self.viewer.filter_mode=self.data["filter"];self.viewer.deformation_scale=self.data["deformation_scale"]
        self.viewer.warp_magnitude=frame["measurements"].get("Displacement",{}).get("value") or 0
        settings=self.data.get("filter_parameters",{});self.viewer.plane_axis=settings.get("axis","X");self.viewer.plane_offset=settings.get("offset",0)
        self.viewer.deformation_scale=settings.get("scale",self.data["deformation_scale"])
        self.viewer.set_geometry(self.result().get("geometry",self.result().get("input_values",{})))
        self.viewer.annotation="" if frame["available"] else "Selected field / association / frame unavailable"
        self.viewer.update();self.curve.ylabel=self.data["array"]+" ["+frame["unit"]+"]";self.curve.cursor_x=self.data["time"]
        if frame["available"]:
            if self.data["filter"]=="Plot over line":
                self.curve.xlabel="Gauge position [mm]";self.curve.cursor_x=None
                n=int(settings.get("samples",21));start=settings.get("start",0);end=settings.get("end",50);xs=[start+(end-start)*i/(n-1) for i in range(n)]
                self.curve.set_series([{"name":"Synthetic line sample","x":xs,"y":[frame["value"]*x/50 for x in xs],"color":BLUE}])
            else:
                self.curve.xlabel="Time [s]";self.curve.set_series([{"name":"Retained fixture","x":frame["times"],"y":frame["curve"],"color":BLUE}])
        else:self.curve.set_series([])
        rows=[];gauge=self.data.get("gauge",{"a":"Gauge left","b":"Gauge right","direction":"X"})
        factors={"Gauge left":0.0,"Gauge right":1.0,"Clamp centre":.5}
        gauge_valid=gauge["a"] in factors and gauge["b"] in factors and gauge["direction"] in ("X","Y","Z","Magnitude")
        for name,loc in (("Displacement","Gauge endpoints"),("Contact pressure","Contact surface"),("Normal force","Contact resultant")):
            m=frame["measurements"].get(name,{"value":None,"unit":""});value=m["value"] if frame["available"] else None
            if name=="Displacement":
                if gauge_valid and value is not None:
                    value*=factors[gauge["b"]]-factors[gauge["a"]]
                    if gauge["direction"] in ("Y","Z"):value=0.0
                    if gauge["direction"]=="Magnitude":value=abs(value)
                    loc=gauge["a"]+" → "+gauge["b"]+" / "+gauge["direction"]
                else:value=None;loc="Selected gauge is not retained"
            rows.append(["Gauge extension" if name=="Displacement" else name,value if value is not None else "Unavailable",m["unit"],loc])
        fill_table(self.measure,rows)
        if not getattr(self,"_measurement_columns_sized",False):
            self.measure.resizeColumnsToContents();self._measurement_columns_sized=True
        self.curve.caption="Synthetic frame "+str(frame["time"])+" s" if frame["available"] else "Unavailable; no interpolation"

    def compare(self):
        dialog=QDialog(self);dialog.setWindowTitle("Compare results");dialog.resize(1240,700);layout=QVBoxLayout(dialog);picker=QComboBox()
        for rid,result in self.session.results.items():
            if result.get("kind")=="structural" and rid!=self.data["result"]:picker.addItem(result.get("candidate",rid),rid)
        layout.addWidget(box(QLabel("Compare with"),picker,horizontal=True))
        a=EngineeringView("post");b=EngineeringView("post");views=QSplitter();views.addWidget(a);views.addWidget(b);layout.addWidget(views)
        values=make_table(["Quantity","A","B","Unit"],[]);values.setObjectName("postComparisonValues")
        values.horizontalHeader().setStretchLastSection(False)
        values.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        values.setMaximumHeight(135);layout.addWidget(values)
        layout.addWidget(QLabel("Side by side. Spatial mapping is unverified; difference is unavailable."))
        def redraw(*args):
            frames=[self.session.post_frame(self.key),self.session.post_frame(self.key,picker.currentData())]
            for view,frame,rid in zip((a,b),frames,(self.data["result"],picker.currentData())):
                record=self.session.results.get(rid,{})
                view.set_geometry(record.get("geometry",record.get("input_values",{})))
                view.field=self.data["array"]+" ["+frame["unit"]+"]";view.field_max=frame["value"] or 0
                view.field_available=frame["available"];view.annotation="t = "+str(frame["time"])+" s";view.update()
            fill_table(values,[[self.data["array"],frames[0]["value"],frames[1]["value"],frames[0]["unit"]]])
            values.resizeColumnsToContents()
            for column,minimum in ((1,120),(2,120),(3,80)):
                values.setColumnWidth(column,max(minimum,values.columnWidth(column)))
        picker.currentIndexChanged.connect(redraw);redraw()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        keep=buttons.addButton("Keep comparison",QDialogButtonBox.ButtonRole.AcceptRole);keep.setEnabled(picker.count()>0)
        keep.clicked.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.session.edit(self.key,"comparison",{"mode":"side_by_side","a":self.data["result"],"b":picker.currentData(),"mapping":"UNVERIFIED"});self.update_title()

    def refresh(self):
        was=self._building;self._building=True
        self.array.setCurrentText(self.data["array"]);self.association.setCurrentText(self.data["association"]);self.filter.setCurrentText(self.data["pending_filter"])
        self.time.setCurrentIndex(next((i for i in range(self.time.count()) if self.time.itemData(i)==self.data["time"]),-1))
        fill_table(self.props,[["Deformation scale",self.raw("deformation_scale",self.data["deformation_scale"])],["Coordinate system",self.data["basis"]],["Unit",self.data["unit"]]],(1,))
        for row in (1,2):self.props.item(row,1).setFlags(self.props.item(row,1).flags()&~Qt.ItemFlag.ItemIsEditable)
        self.render_frame();self._building=was;self.update_title()


class ExpertWindow(ToolWindow):
    def build(self):
        self.connection=QLabel("Provider: 미연결")
        self.toolbar.addWidget(self.connection)
        self.action(self.toolbar,"Models…",self.configure_models)
        self.action(self.toolbar,"Ask…",self.ask)
        self.pause_action=self.action(self.toolbar,"Resume",self.pause_resume)
        self.action(self.toolbar,"Plan…",self.edit_plan)
        self.action(self.toolbar,"Add topic…",self.add_topic)
        self.action(self.toolbar,"Add evidence…",self.add_evidence)
        self.action(self.toolbar,"Study",lambda:self.hub.open("study"))
        self.question=QLineEdit(self.data["question"])
        self.question.editingFinished.connect(self.question_changed)
        self.turns=QListWidget();self.turns.setSpacing(8)
        self.turns.setWordWrap(True);self.turns.itemDoubleClicked.connect(lambda item:self.reply_to())
        self.turns.currentRowChanged.connect(self.turn_selected)
        self.reply_label=QLabel("Reply")
        self.composer=QPlainTextEdit(self.data["pending_text"]);self.composer.setPlaceholderText("질문, 반론 또는 다음 확인 사항")
        self.composer.setMinimumHeight(95);self.composer.setMaximumHeight(165)
        self.composer.textChanged.connect(self.composer_changed)
        self.topic=QComboBox();self.topic.addItems(self.data["topics"])
        self.topic.currentTextChanged.connect(self.topic_changed)
        self.reply_target=self.data.get("reply_to")
        send=button("Save reply",lambda:self.guard(self.save_reply))
        self.action(self.composer,"Save reply",self.save_reply,"Ctrl+Return").setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        central=box(self.question,self.turns,self.reply_label,self.composer,
                    box(self.topic,button("Reply to selected",self.reply_to),button("Attach selected evidence",self.attach_evidence),send,horizontal=True),margins=8)
        self.setCentralWidget(central)
        nodes=[("question","지그 유연성",0,160)]
        nodes.extend((topic,topic,230,i*105) for i,topic in enumerate(self.data["topics"]))
        self.map=NodeView(nodes,[("question",t) for t in self.data["topics"]])
        self.map.chosen.connect(self.map_selected)
        self.map.moved.connect(self.map_moved)
        self.map.set_positions(self.data.get("map_positions",{}))
        roles=make_table(["Participant","Model / status"],[[role,"미설정"] for role in self.data["roles"]]);self.roles_table=roles
        roles.setMaximumHeight(150)
        map_dock=self.add_dock("Discussion map",box(self.map,roles),minimum=330)
        self.evidence=make_table(["Evidence","Location"],[[e["label"],e["locator"]] for e in self.data["evidence"]])
        self.visible_evidence=list(self.data["evidence"])
        self.evidence.itemDoubleClicked.connect(lambda item:self.guard(self.open_evidence))
        evidence_dock=self.add_dock("Evidence",box(self.evidence,button("Open selected",lambda:self.guard(self.open_evidence))),
                                    Qt.DockWidgetArea.RightDockWidgetArea,minimum=270)
        self.resizeDocks([map_dock,evidence_dock],[365,295],Qt.Orientation.Horizontal)
        self.action(self.review_menu,"Show labelled discussion layout example",self.layout_example)
        self.refresh()
        QTimer.singleShot(0,lambda:self.map.fitInView(self.map.scene().itemsBoundingRect().adjusted(-15,-15,15,15),Qt.AspectRatioMode.KeepAspectRatio))

    def question_changed(self):
        if not self._building:self.session.edit(self.key,"question",self.question.text());self.update_title()

    def composer_changed(self):
        if not self._building:
            self.session.edit(self.key,"pending_text",self.composer.toPlainText());self.update_title()

    def topic_changed(self,value):
        self.session.selected["topic"]=value
        if not self._building:
            self.session.edit(self.key,"selected_topic",value);self.update_title()

    def map_selected(self,key):
        if key in self.data["topics"]:self.topic.setCurrentText(key)

    def map_moved(self,positions):
        if not self._building:self.session.edit(self.key,"map_positions",positions);self.update_title()

    def turn_selected(self,row):
        if row<0 or row>=len(self.data["turns"]):return
        turn=self.data["turns"][row]
        self.topic.setCurrentText(turn["topic"]);self.map.select_node(turn["topic"])
        refs=set(turn.get("evidence",[]));self.visible_evidence=[e for e in self.data["evidence"] if e["id"] in refs] if refs else list(self.data["evidence"])
        fill_table(self.evidence,[[e["label"],e["locator"]] for e in self.visible_evidence])
        self.update_title("선택 발언: "+turn["role"])

    def reply_to(self):
        row=self.turns.currentRow()
        if row>=0:
            turn=self.data["turns"][row];self.reply_target=turn["id"]
            self.session.edit(self.key,"reply_to",self.reply_target);self.update_title()
            self.reply_label.setText("Reply to "+turn["role"]);self.composer.setFocus()

    def save_reply(self):
        self.session.append_reply(self.composer.toPlainText(),self.topic.currentText(),self.reply_target,self.key,self.data.get("pending_evidence",[]))
        self.reply_target=None;self.reply_label.setText("Reply")
        self.refresh()
        self.update_title("사용자 발언 저장 초안. Provider는 미연결입니다.")

    def pause_resume(self):
        self.session.edit(self.key,"paused",not self.data["paused"])
        self.pause_action.setText("Resume" if self.data["paused"] else "Pause")
        self.update_title("Paused" if self.data["paused"] else "대기 중: Provider 미연결")

    def configure_models(self):
        dialog=QDialog(self);dialog.setWindowTitle("Expert models");dialog.resize(800,610);layout=QVBoxLayout(dialog)
        form=QFormLayout();route=QComboBox();route.addItems(["Not configured","Existing subscription OAuth","Existing local endpoint"])
        config=self.data.get("runtime_proposal",{});route.setCurrentText(config.get("route","Not configured"))
        model=QLineEdit(config.get("model", ""));model.setPlaceholderText("Existing profile model identifier")
        profile=QLineEdit(config.get("openscience_profile", ""));endpoint=QLineEdit(config.get("api_base_url", ""))
        endpoint.setPlaceholderText("Existing localhost or private-network endpoint")
        form.addRow("Route",route);form.addRow("Default model",model);form.addRow("Existing OAuth profile",profile);form.addRow("Local API base URL",endpoint);layout.addLayout(form)
        overrides=config.get("expert_models",{})
        roles=make_table(["Role","Model override","State"],[[role,overrides.get(role,{}).get("model",""),"UNVERIFIED"] for role in self.data["roles"]],editable=(1,),select_rows=False);layout.addWidget(roles)
        status=QLabel("Provider 연결과 해당 모델 사용 권한은 미확인입니다. 이 시안은 요청을 보내지 않습니다.");status.setWordWrap(True);layout.addWidget(status)
        budget=QSpinBox();budget.setRange(1,32);budget.setValue(config.get("max_model_calls",4));layout.addWidget(box(QLabel("Round model-call limit"),budget,horizontal=True))
        def changed(value):
            oauth=value=="Existing subscription OAuth";local=value=="Existing local endpoint"
            profile.setEnabled(oauth);endpoint.setEnabled(local);model.setEnabled(oauth or local);roles.setEnabled(oauth or local)
            status.setText("Existing OpenScience OAuth profile / openai-codex model entitlement UNVERIFIED" if oauth else
                           "Existing local endpoint / model and tool calls UNVERIFIED" if local else "Provider 미설정. 질문·사용자 발언·Plan은 편집할 수 있습니다.")
        route.currentTextChanged.connect(changed);changed(route.currentText())
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel);apply=buttons.addButton("Apply configuration draft",QDialogButtonBox.ButtonRole.AcceptRole)
        def accept():
            selected=route.currentText();model_id=model.text().strip()
            if selected=="Existing subscription OAuth" and model_id and not model_id.startswith("openai-codex/"):model_id="openai-codex/"+model_id
            proposal={"route":selected,"provider":"openscience" if selected=="Existing subscription OAuth" else "openai-compatible" if selected=="Existing local endpoint" else None,
                "model":model_id,"api_base_url":endpoint.text().strip() if selected=="Existing local endpoint" else "",
                "openscience_profile":profile.text().strip() if selected=="Existing subscription OAuth" else "","credential_env":"",
                "max_model_calls":budget.value(),"expert_models":{},"connection":"UNVERIFIED","model_entitlement":"UNVERIFIED","tool_calls":"UNVERIFIED","execution":"UNAVAILABLE"}
            for row,role in enumerate(self.data["roles"]):
                value=roles.item(row,1).text().strip()
                if value:
                    if selected=="Existing subscription OAuth" and not value.startswith("openai-codex/"):value="openai-codex/"+value
                    proposal["expert_models"][role]={"model":value,"provider":proposal["provider"]}
            self.session.edit(self.key,"runtime_proposal",proposal);self.refresh();dialog.accept()
        apply.clicked.connect(accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec()

    def ask(self):
        config=self.data.get("runtime_proposal",{})
        if not config or config.get("route")=="Not configured":
            self.configure_models();return
        raise ReviewError("선택한 provider/model의 연결·사용 권한은 미확인입니다. 시안에서는 발언을 요청하지 않습니다. 질문·reply·Plan은 저장할 수 있습니다.")

    def open_evidence(self):
        row=self.evidence.currentRow()
        if row<0:raise ReviewError("Select evidence first.")
        ref=self.visible_evidence[row]
        if ref["id"]=="CAL-018":self.hub.calibration(self)
        else:self.hub.open_result(ref["id"])

    def attach_evidence(self):
        row=self.evidence.currentRow()
        if row<0:raise ReviewError("Select a retained result or source in Evidence.")
        ref=self.visible_evidence[row]["id"];refs=list(self.data.get("pending_evidence",[]))
        if ref not in refs:refs.append(ref)
        self.session.edit(self.key,"pending_evidence",refs);self.reply_label.setText("Reply / "+str(len(refs))+" evidence attached");self.update_title()

    def add_evidence(self):
        dialog=QDialog(self);dialog.setWindowTitle("Add discussion evidence");form=QFormLayout(dialog)
        choice=QComboBox()
        for rid,result in self.session.results.items():
            if result.get("fields") or result.get("kind")=="numerical":choice.addItem(result.get("method",result.get("candidate",rid)),rid)
        choice.addItem("Calibration original","CAL-018");locator=QLineEdit("Gauge / t = 0.04 s");label=QLineEdit("Gauge measurement")
        form.addRow("Result / source",choice);form.addRow("Location",locator);form.addRow("Label",label)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            payload=clone(self.data);payload["evidence"].append({"id":choice.currentData(),"locator":locator.text(),"label":label.text(),"synthetic":True})
            self.session.change(self.key,payload,"Add discussion evidence");self.refresh()

    def add_topic(self):
        dialog=QDialog(self);dialog.setWindowTitle("Add discussion topic");layout=QVBoxLayout(dialog);name=QLineEdit();layout.addWidget(name)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted and name.text().strip():
            payload=clone(self.data);value=name.text().strip()
            if value in payload["topics"]:raise ReviewError("This topic already exists.")
            payload["topics"].append(value);self.session.change(self.key,payload,"Add discussion topic")
            from qt_widgets import GraphNode
            node=GraphNode(value,value,230,(len(payload["topics"])-1)*105,self.map.redraw)
            self.map.nodes[value]=node;self.map.scene().addItem(node);self.map.set_links([("question",t) for t in payload["topics"]]);self.refresh()

    def edit_plan(self):
        self.hub.plan_dialog(self)

    def layout_example(self):
        answer=QMessageBox.question(self,"Discussion layout example",
            "Add clearly labelled illustrative speaker turns to this review draft?\nThese are authored examples, not provider responses.")
        if answer!=QMessageBox.StandardButton.Yes:return
        payload=clone(self.data)
        examples=[
            ("구조 예시","지그를 강체로 가정하면 장비 변위에 포함된 지그 굽힘을 분리할 수 없습니다.","지그 강성"),
            ("시험 예시","게이지 구간의 두 점 변위와 장비 변위를 같은 하중 단계에서 비교하겠습니다.","측정 위치"),
            ("재료 예시","재료계수를 먼저 바꾸기보다 같은 계수에서 접촉·지그 강성 변화의 영향을 확인하겠습니다.","판별 시험")]
        for i,(role,text,topic) in enumerate(examples):
            payload["turns"].append({"id":"layout-example-"+str(i),"role":role,"actual":False,
                "text":text,"topic":topic,"reply_to":"question-example","evidence":[]})
        self.session.change(self.key,payload,"Load labelled discussion illustration");self.refresh()

    def refresh(self):
        self._building=True;self.turns.clear()
        for turn in self.data["turns"]:
            label=turn["role"]+("" if turn["actual"] else "  [합성 예시]")
            if turn["reply_to"]:label+="  ↳ reply"
            item=QListWidgetItem(label+"\n"+turn["text"]+"\n"+turn["topic"])
            item.setSizeHint(QSize(400,112))
            self.turns.addItem(item)
        self.question.setText(self.data["question"]);self.composer.setPlainText(self.data["pending_text"])
        self.topic.clear();self.topic.addItems(self.data["topics"]);self.topic.setCurrentText(self.data.get("selected_topic",self.session.selected.get("topic",self.data["topics"][0])))
        self.reply_target=self.data.get("reply_to");self.reply_label.setText("Reply to selected turn" if self.reply_target else "Reply")
        self.visible_evidence=list(self.data["evidence"]);fill_table(self.evidence,[[e["label"],e["locator"]] for e in self.visible_evidence])
        self.map.set_positions(self.data.get("map_positions",{}));self.map.nodes["question"].label=self.data["question"][:16];self.map.viewport().update()
        self.pause_action.setText("Resume" if self.data["paused"] else "Pause")
        config=self.data.get("runtime_proposal",{});route=config.get("route","Not configured")
        self.connection.setText("Provider: "+("미설정" if route=="Not configured" else "OAuth / 미확인" if route=="Existing subscription OAuth" else "Local / 미확인"))
        fill_table(self.roles_table,[[role,(config.get("expert_models",{}).get(role,{}).get("model") or config.get("model") or "미설정")+" / 미확인"] for role in self.data["roles"]])
        self._building=False;self.turns.scrollToBottom();self.update_title("Actual provider turns: none")


class StudyWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Discuss",lambda:self.hub.open(self.hub.discussion_for(self.key)))
        self.action(self.toolbar,"Next research…",self.next_plan)
        self.action(self.toolbar,"Add hypothesis…",self.add_hypothesis)
        self.action(self.toolbar,"Add evidence…",self.add_evidence)
        self.question=QLineEdit(self.data["question"]);self.question.editingFinished.connect(self.question_changed)
        self.hypotheses=make_table(["Hypothesis","Explanation","Judgment"],[
            [h["id"],h["text"],h["judgment"]] for h in self.data["hypotheses"]],editable=(1,),select_rows=False)
        self.hypotheses.itemChanged.connect(self.hypothesis_changed)
        self.evidence=make_table(["Evidence","Location","Hypothesis","Relation"],[
            [e["ref"],e["locator"],e["hypothesis"],e["relation"]] for e in self.data["evidence"]],
            editable=(2,3),select_rows=False)
        self.evidence.itemChanged.connect(self.evidence_changed)
        self.evidence.itemDoubleClicked.connect(lambda item:self.open_evidence() if item.column()<2 else None)
        self.judgment=QComboBox();self.judgment.addItems(["Undecided","Supported","Refuted","Insufficient evidence"])
        self.judgment.setCurrentText(self.data["judgment"])
        self.reason=QPlainTextEdit(self.data["reason"]);self.reason.setPlaceholderText("판단 이유와 남은 불확실성")
        self.reason.setMinimumHeight(100)
        self.judgment.currentTextChanged.connect(self.pending_judgment)
        self.reason.textChanged.connect(self.pending_judgment)
        self.next=QLineEdit(self.data["next_research"])
        self.next.editingFinished.connect(self.next_changed)
        lower=box(QLabel("Research judgment"),self.judgment,self.reason,
                  button("Apply judgment",lambda:self.guard(self.apply_judgment)),
                  QLabel("Next research"),self.next,margins=8)
        upper=QSplitter();upper.addWidget(self.hypotheses);upper.addWidget(self.evidence);upper.setSizes([630,650])
        split=QSplitter(Qt.Orientation.Vertical);split.addWidget(upper);split.addWidget(lower);split.setSizes([430,300])
        self.setCentralWidget(box(self.question,split,margins=7));self.refresh()

    def question_changed(self):
        if not self._building:self.session.edit(self.key,"question",self.question.text());self.update_title()

    def hypothesis_changed(self,item):
        if self._building:return
        payload=clone(self.data);payload["hypotheses"][item.row()]["text"]=item.text()
        self.session.change(self.key,payload,"Edit hypothesis");self.update_title()

    def evidence_changed(self,item):
        if self._building or item.column() not in (2,3):return
        payload=clone(self.data);field="hypothesis" if item.column()==2 else "relation"
        payload["evidence"][item.row()][field]=item.text()
        self.session.change(self.key,payload,"Edit evidence relation");self.update_title()

    def pending_judgment(self,*args):
        if self._building:return
        payload=clone(self.data);payload["pending_judgment"]={"judgment":self.judgment.currentText(),"reason":self.reason.toPlainText()}
        self.session.change(self.key,payload,"Edit proposed judgment");self.update_title("Judgment draft; Apply to record decision")

    def add_hypothesis(self):
        payload=clone(self.data);used={h["id"] for h in payload["hypotheses"]};i=1
        while "H"+str(i) in used:i+=1
        payload["hypotheses"].append({"id":"H"+str(i),"text":"New hypothesis","judgment":"Undecided"})
        self.session.change(self.key,payload,"Add competing hypothesis");self.refresh();self.hypotheses.setCurrentCell(len(payload["hypotheses"])-1,1);self.hypotheses.editItem(self.hypotheses.currentItem())

    def add_evidence(self):
        dialog=QDialog(self);dialog.setWindowTitle("Relate evidence");form=QFormLayout(dialog)
        result=QComboBox()
        for rid,value in self.session.results.items():
            if value.get("fields") or value.get("kind")=="numerical":result.addItem(value.get("method",value.get("candidate",rid)),rid)
        hypothesis=QComboBox();hypothesis.addItems([h["id"] for h in self.data["hypotheses"]]);relation=QComboBox();relation.addItems(["Support","Refute","Neutral"])
        locator=QLineEdit("Gauge / t = 0.04 s")
        for label,w in (("Result",result),("Hypothesis",hypothesis),("Relation",relation),("Location",locator)):form.addRow(label,w)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            payload=clone(self.data);payload["evidence"].append({"ref":result.currentData(),"locator":locator.text(),"hypothesis":hypothesis.currentText(),"relation":relation.currentText(),"synthetic":True})
            self.session.change(self.key,payload,"Relate research evidence");self.refresh()

    def apply_judgment(self):
        if self.judgment.currentText()!="Undecided" and not self.reason.toPlainText().strip():
            raise ReviewError("Enter the reason for this explicit judgment.")
        if any(e["hypothesis"] not in [h["id"] for h in self.data["hypotheses"]] or e["relation"] not in ("Support","Refute","Neutral") for e in self.data["evidence"]):raise ReviewError("Correct the hypothesis / relation in the evidence table.")
        payload=clone(self.data);payload.pop("pending_judgment",None);payload["judgment"]=self.judgment.currentText()
        payload["reason"]=self.reason.toPlainText()
        self.session.change(self.key,payload,"Apply research judgment");self.update_title("Judgment applied to draft")

    def next_changed(self):
        if not self._building:self.session.edit(self.key,"next_research",self.next.text());self.update_title()

    def open_evidence(self):
        row=self.evidence.currentRow()
        if row>=0:self.hub.open_result(self.data["evidence"][row]["ref"])

    def next_plan(self):
        self.hub.plan_dialog(self)

    def refresh(self):
        self._building=True;self.question.setText(self.data["question"])
        self.judgment.setCurrentText(self.data.get("pending_judgment",self.data)["judgment"]);self.reason.setPlainText(self.data.get("pending_judgment",self.data)["reason"])
        self.next.setText(self.data["next_research"])
        fill_table(self.hypotheses,[[h["id"],h["text"],h["judgment"]] for h in self.data["hypotheses"]],(1,))
        fill_table(self.evidence,[[e["ref"],e["locator"],e["hypothesis"],e["relation"]] for e in self.data["evidence"]],(2,3))
        self._building=False;self.update_title()


class EvaluationWindow(ToolWindow):
    TRANSFER_DEFAULT={"quantity":"Temperature","source_unit":"K","target_unit":"K","association":"POINTS","mapping":"exact_same_mesh"}
    def build(self):
        self.action(self.toolbar,"Open stage",self.open_stage);self.action(self.toolbar,"Move up",lambda:self.move_stage(-1));self.action(self.toolbar,"Move down",lambda:self.move_stage(1))
        self.action(self.toolbar,"Check connection",self.check);self.action(self.toolbar,"Run evaluation…",self.submit_review)
        self.stages=make_table(["Stage","Model","Operation","Output"],[]);self.stages.itemDoubleClicked.connect(lambda item:self.guard(self.open_stage))
        self.transfer=make_table(["Transfer","Value"],[],editable=(1,),select_rows=False);self.transfer.itemChanged.connect(self.transfer_changed)
        self.iteration=QComboBox();self.iteration.addItems(["One-way","Lagged Picard"]);self.iteration.currentTextChanged.connect(lambda v:self.edit_iteration(v))
        self.controls=make_table(["Iteration control","Value"],[],editable=(1,),select_rows=False);self.controls.itemChanged.connect(self.control_changed)
        tabs=QTabWidget();tabs.addTab(box(self.transfer,box(button("Apply",self.apply_transfer),button("Reset",self.reset_transfer),horizontal=True)),"Field transfer")
        tabs.addTab(box(self.iteration,self.controls),"Coupling")
        self.status_table=make_table(["Stage / check","Status","Detail"],[]);tabs.addTab(self.status_table,"Results")
        self.tabs=tabs
        left=QSplitter(Qt.Orientation.Vertical);left.addWidget(self.stages);left.addWidget(tabs);left.setSizes([230,430])
        self.viewer=EngineeringView("thermal");self.viewer.label="Thermal / structural field illustration"
        split=QSplitter();split.addWidget(left);split.addWidget(self.viewer);split.setSizes([680,570]);self.setCentralWidget(split);self.refresh()

    def open_stage(self):
        row=self.stages.currentRow()
        if row<0:raise ReviewError("Select a stage.")
        self.hub.open_reference(self.data["stages"][row]["ref"],self)

    def move_stage(self,offset):
        row=self.stages.currentRow();target=row+offset
        if row<0 or target<0 or target>=len(self.data["stages"]):return
        payload=clone(self.data);payload["stages"][row],payload["stages"][target]=payload["stages"][target],payload["stages"][row]
        self.session.change(self.key,payload,"Reorder Evaluation stages");self.refresh();self.stages.selectRow(target)

    def transfer_changed(self,item):
        if self._building or item.column()!=1:return
        key=list(self.TRANSFER_DEFAULT)[item.row()];payload=clone(self.data)
        payload.setdefault("transfer_draft",{})[key]=item.text();self.session.change(self.key,payload,"Edit field transfer");self.update_title()

    def apply_transfer(self):
        proposal={**self.TRANSFER_DEFAULT,**self.data.get("transfer_fields",{}),**self.data.get("transfer_draft",{})}
        if proposal!=self.TRANSFER_DEFAULT:raise ReviewError("This bounded fixture transfers Temperature [K], POINTS on the exact same mesh. Other mappings remain an unconnected draft.")
        payload=clone(self.data);payload["transfer_fields"]=proposal;payload.pop("transfer_draft",None)
        self.session.change(self.key,payload,"Apply field transfer");self.refresh()

    def reset_transfer(self):
        payload=clone(self.data);payload.pop("transfer_draft",None);self.session.change(self.key,payload,"Reset field transfer");self.refresh()

    def edit_iteration(self,value):
        if not self._building:self.session.edit(self.key,"iteration",value);self.update_title()

    def control_changed(self,item):
        if not self._building and item.column()==1:self.edit_number(["tolerance","limit"][item.row()],item)

    def check(self):
        errors=self.session.diagnostics(self.key)
        if errors:
            fill_table(self.status_table,[[field,"Needs correction",msg] for field,msg in errors]);self.tabs.setCurrentIndex(2);self.input_diagnostics();return False
        heat=self.session.resolve(self.data["stages"][0]["ref"])[1];expand=self.session.resolve(self.data["stages"][1]["ref"])[1]
        if heat["unit"]!="K" or heat["mesh"]!=expand["mesh"]:raise ReviewError("The exact saved stages do not share the required K field and mesh.")
        fill_table(self.status_table,[["Static connection","Checked","Heat → Expand / K / POINTS / exact same mesh"],["Actual Heat field","PENDING","Receiver is not submitted"],["Coupling convergence","NOT_EVALUATED","No calculation"]])
        self.tabs.setCurrentIndex(2);self.update_title("Static field connection checked; actual source field pending");return True

    def refresh(self):
        was=self._building;self._building=True;rows=[]
        for stage in self.data["stages"]:
            key,payload=self.session.resolve(stage["ref"]);rows.append([stage["stage"],self.session.doc(key)["name"],stage["operation"],payload["field"]+" ["+payload["unit"]+"]"])
        fill_table(self.stages,rows)
        current={**self.TRANSFER_DEFAULT,**self.data.get("transfer_fields",{}),**self.data.get("transfer_draft",{})}
        fill_table(self.transfer,[[k.replace("_"," ").title(),v] for k,v in current.items()],(1,))
        fill_table(self.controls,[["Tolerance",self.raw("tolerance",self.data["tolerance"])],["Iteration limit",self.raw("limit",self.data["limit"])]],(1,))
        self.iteration.setCurrentText(self.data["iteration"])
        fill_table(self.status_table,[["Heat","NOT_EXECUTED","Temperature field pending"],["Expand","NOT_EXECUTED","Waiting for source field"],["Convergence","NOT_EVALUATED",""]])
        self._building=was;self.update_title()


class WorkbenchWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Open selected",self.open_selected)
        self.action(self.toolbar,"Connection…",self.connection)
        coords={"cad":(15,20),"simulation":(270,20),"runner":(530,20),"post":(790,20),
                "data":(15,180),"material":(270,180),"numerical":(790,180),
                "expert":(270,340),"study":(530,340),"evaluation":(15,340)}
        saved=self.data.get("positions",{})
        nodes=[(key,TOOL_NAMES[key],*(saved.get(key) or xy)) for key,xy in coords.items()]
        self.graph=NodeView(nodes,self.data["links"])
        self.graph.chosen.connect(self.selected_node);self.graph.opened.connect(self.hub.open)
        self.graph.moved.connect(self.positions_changed)
        self.graph.edgeChosen.connect(self.selected_edge)
        self.graph.portChosen.connect(lambda key,port:self.port_selected(key,port))
        self.setCentralWidget(self.graph)
        self.items=make_table(["Document","Tool"],[[self.session.doc(k)["name"],TOOL_NAMES[k]] for k in coords])
        self.node_keys=list(coords)
        self.items.itemDoubleClicked.connect(lambda item:self.hub.open(self.node_keys[item.row()]))
        dock=self.add_dock("Documents",self.items,minimum=245);self.resizeDocks([dock],[300],Qt.Orientation.Horizontal)
        self.current="cad"

    def selected_node(self,key):
        self.current=key;self.update_title(self.session.doc(key)["name"])

    def port_selected(self,key,port):
        self.current=key;self.session.selected["port"]={"owner":key,"direction":port}
        self.update_title(TOOL_NAMES[key]+" / "+port+" / Enter opens the owner")

    def selected_edge(self,a,b):
        self.current=b;self.update_title(TOOL_NAMES[a]+" → "+TOOL_NAMES[b]+" / open receiving tool")

    def positions_changed(self,positions):
        if not self._building:self.session.edit(self.key,"positions",positions);self.update_title()

    def open_selected(self):
        self.hub.open(self.current)

    def connection(self):
        dialog=QDialog(self);dialog.setWindowTitle("Connect documents");layout=QFormLayout(dialog)
        source=QComboBox();target=QComboBox()
        for k in self.node_keys:
            source.addItem(TOOL_NAMES[k],k);target.addItem(TOOL_NAMES[k],k)
        port=QComboBox();port.addItems(["Saved document","Frozen input","Retained result"])
        layout.addRow("From",source);layout.addRow("Port",port);layout.addRow("To",target)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            a,b=source.currentData(),target.currentData()
            if a==b:raise ReviewError("Choose different document endpoints.")
            payload=clone(self.data)
            if [a,b] not in payload["links"]:payload["links"].append([a,b])
            payload.setdefault("port_proposals",[]).append({"from":a,"to":b,"port":port.currentText(),"state":"PROPOSED"})
            self.session.change(self.key,payload,"Propose document connection")
            self.graph.set_links(payload["links"]);self.update_title(TOOL_NAMES[a]+" → "+TOOL_NAMES[b])

    def refresh(self):
        if hasattr(self,"graph"):
            self.graph.set_links(self.data["links"]);self.graph.set_positions(self.data.get("positions",{}))
        self.update_title()


class DesktopHub:
    def __init__(self,session):
        self.session=session;self.windows={};self.other_hubs=[];self.result_dialogs={}

    def open(self,key):
        if key in self.windows:
            window=self.windows[key];window.refresh();window.showNormal();window.raise_();window.activateWindow()
            return window
        doc=self.session.doc(key)
        classes={"native_pre":CADWindow,"Simulation":SimulationWindow,"native_post":PostWindow,
                 "Data":DataWindow,"Material":MaterialWindow,"PDE":PDEWindow,"Numerical":NumericalWindow,
                 "JobManager view":RunnerWindow,"Discussion":ExpertWindow,"Study":StudyWindow,
                 "Evaluation":EvaluationWindow,"Study links":WorkbenchWindow}
        window=classes[doc["owner"]](self,key);self.windows[key]=window;window.show();return window

    def open_other(self,session,key):
        hub=DesktopHub(session);self.other_hubs.append(hub);return hub.open(key)

    def open_session(self,path):
        session=ReviewSession.open_session(path)
        return self.open_other(session,session.selected.get("tool","cad"))

    def open_reference(self,ref,parent):
        key,payload=self.session.resolve(ref)
        doc=self.session.doc(key)
        if doc["revision"]==ref["revision"] and not doc["dirty"]:
            return self.open(key)
        text_dialog(parent,"Saved "+doc["name"],
                    json.dumps({"reference":ref,"saved_input":payload},ensure_ascii=False,indent=2))

    def open_result(self,result_id):
        if result_id not in self.session.results:raise ReviewError("The exact result is unavailable.")
        if self.session.results[result_id].get("kind")=="numerical":return self.inspect_research_result(result_id)
        if not self.session.results[result_id].get("fields"):
            raise ReviewError("This retained result has no 3D field arrays. Inspect its owning tool result table.")
        key="post:"+result_id
        if key not in self.session.documents:
            from prototype_state import make_document
            payload=clone(self.session.doc("post")["saved"]);payload["result"]=result_id
            result=self.session.results[result_id]
            payload["time"]=result.get("time",.04)
            name=self.session.doc(result["source"]["id"])["name"]+" result" if result["source"]["id"] in [d["id"] for d in self.session.documents.values()] else "Retained result"
            self.session.documents[key]=make_document(key,name,"native_post","POST-"+result_id,1,payload)
        return self.open(key)

    def discussion_for(self,source_key):
        if not source_key or source_key not in self.session.documents:return "expert"
        source=self.session.doc(source_key)
        if source["owner"]=="Discussion":return source_key
        key="discussion:"+source["id"]
        if key not in self.session.documents:
            from prototype_state import make_document,token
            data=clone(self.session.doc("expert")["saved"])
            data.update(question=source["draft"].get("question",source["name"]),turns=[],evidence=[],pending_text="",reply_to=None)
            self.session.documents[key]=make_document(key,source["name"],"Discussion",token("DISC"),0,data)
        return key

    def discuss_result(self,result_id,locator):
        result=self.session.results[result_id];key=self.discussion_for(result.get("parent_key"))
        payload=clone(self.session.doc(key)["draft"]);label=result.get("method",result.get("candidate","Result"))+" example"
        if not any(e["id"]==result_id and e["locator"]==locator for e in payload["evidence"]):
            payload["evidence"].append({"id":result_id,"locator":locator,"label":label,"synthetic":True})
        payload["pending_evidence"]=[result_id]
        self.session.change(key,payload,"Discuss selected result")
        window=self.open(key);window.composer.setFocus();return window

    def result_to_study(self,result_id,locator,parent=None):
        dialog=QDialog(parent);dialog.setWindowTitle("Use result as research evidence");form=QFormLayout(dialog)
        studies=QComboBox()
        for key,doc in self.session.documents.items():
            if doc["owner"]=="Study":studies.addItem(doc["name"],key)
        hypothesis=QComboBox();relation=QComboBox();relation.addItems(["Neutral","Support","Refute"])
        def fill(*args):hypothesis.clear();hypothesis.addItems([h["id"]+" / "+h["text"] for h in self.session.doc(studies.currentData())["draft"]["hypotheses"]])
        studies.currentIndexChanged.connect(fill);fill()
        for label,widget in (("Study",studies),("Hypothesis",hypothesis),("Relation",relation)):form.addRow(label,widget)
        form.addRow("Selected result",QLabel(locator))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            key=studies.currentData();payload=clone(self.session.doc(key)["draft"])
            payload["evidence"].append({"ref":result_id,"locator":locator,"hypothesis":payload["hypotheses"][hypothesis.currentIndex()]["id"],"relation":relation.currentText(),"synthetic":True})
            self.session.change(key,payload,"Relate selected result evidence");return self.open(key)

    def inspect_research_result(self,result_id):
        if result_id in self.result_dialogs:
            window=self.result_dialogs[result_id];window.show();window.raise_();return window
        record=self.session.results[result_id];fixture=record["fixture"]
        dialog=QDialog();dialog.setWindowTitle(record["method"]+" result");dialog.resize(1440,900)
        layout=QVBoxLayout(dialog);label=QLabel(record["method"]+" / authored synthetic result / no evaluation")
        label.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed);label.setMaximumHeight(30)
        layout.addWidget(label);tabs=QTabWidget();tables=[]
        for definition in fixture["tables"]:
            table=make_table(definition["headers"],definition["rows"]);tables.append(table);tabs.addTab(table,definition["name"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        plot=CurveView(xlabel=fixture["xlabel"],ylabel=fixture["ylabel"]);plot.set_series(fixture["series"])
        plot.caption="Authored example / not evaluated from this plan"
        split=QSplitter();split.addWidget(tabs);split.addWidget(plot);split.setSizes([760,640]);layout.addWidget(split,1)
        summary=make_table(["Finding","Value"],fixture["summary"]);summary.setMaximumHeight(135);layout.addWidget(summary)
        def locator():
            index=tabs.currentIndex();table=tables[index];row=table.currentRow()
            return record["method"]+" / "+fixture["tables"][index]["name"]+(" / "+table.item(row,0).text() if row>=0 else "")
        def selection_changed():
            self.session.selected["result_evidence"]={"id":result_id,"locator":locator()}
            table=tables[tabs.currentIndex()];row=table.currentRow()
            if row>=0:plot.select_ids([table.item(row,0).text()]);plot.update()
        for table in tables:table.itemSelectionChanged.connect(selection_changed)
        def view_changed(index):
            definition=fixture["tables"][index];rows=definition["rows"];name=definition["name"]
            if name in ("Train residuals","Holdout"):
                plot.xlabel="Engineering strain";plot.ylabel="Stress [MPa]"
                plot.set_series([{"name":label,"x":[r[1] for r in rows],"y":[r[c] for r in rows],"ids":[r[0] for r in rows],"color":color} for label,c,color in (("Observed",2,BLUE),("Prediction example",3,ORANGE))])
            elif name=="Prediction support":
                plot.set_series([]);plot.caption="Outside support is unavailable; no extrapolated value is shown"
            else:
                plot.xlabel=fixture["xlabel"];plot.ylabel=fixture["ylabel"];plot.set_series(fixture["series"]);plot.caption="Authored example / no evaluation"
            selection_changed()
        tabs.currentChanged.connect(view_changed)
        controls=box(button("Discuss selection",lambda:self.discuss_result(result_id,locator())),button("Use as Study evidence…",lambda:self.result_to_study(result_id,locator(),dialog)),horizontal=True)
        if record["method"]=="MDO":
            controls.layout().addWidget(button("Open Heat",lambda:self.open_reference({"id":"V-02","revision":4},dialog)))
            controls.layout().addWidget(button("Open Expand",lambda:self.open_reference({"id":"V-03","revision":6},dialog)))
            controls.layout().addWidget(button("Open Evaluation",lambda:self.open("evaluation")))
        controls.layout().addWidget(button("Save review session…",lambda:self.save_result_session(dialog)))
        controls.layout().addWidget(button("Close",dialog.close));layout.addWidget(controls)
        dialog.result_tabs=tabs;dialog.result_plot=plot;dialog.result_tables=tables;dialog.result_id=result_id
        self.result_dialogs[result_id]=dialog;dialog.show();tables[0].selectRow(0);return dialog

    def save_result_session(self,parent):
        path,_=QFileDialog.getSaveFileName(parent,"Save review session",str(self.session.workspace/"Research.json"),"Review session (*.json)")
        if path:self.session.save_session(path)

    def open_fit(self,material_key):
        from prototype_state import make_document
        key="fit:"+material_key
        if key not in self.session.documents:
            material=self.session.doc(material_key);payload=clone(self.session.doc("numerical")["draft"])
            payload["method"]="Inverse";payload["evaluator"]="Material response"
            payload["responses"]=[{"name":"Stress residual","role":"Minimize","unit":"MPa","limit":"","location":"Gauge","time":0,"reduction":"RMS"}]
            if material["draft"].get("observation_snapshot"):
                payload["observation_snapshot"]=clone(material["draft"]["observation_snapshot"]);payload["sources"]["data"]=clone(material["draft"]["observations"])
            payload["sources"]["material"]={"id":material["id"],"revision":material["revision"]}
            fields={"Neo-Hookean":[("mu","MPa")],"J2 plasticity":[("parameters.yield","MPa"),("parameters.hardening","MPa")],
                    "Drucker–Prager":[("parameters.cohesion","MPa"),("parameters.friction_angle","deg")],
                    "Prony viscoelastic":[("parameters.g1","1"),("parameters.tau1","s")],"User constitutive law":[("parameters.E","MPa")]}
            payload["variables"]=[]
            for field,unit in fields[material["saved"]["law"]]:
                value=material["saved"]
                for part in field.split("."):value=value[part]
                payload["variables"].append({"owner":material_key,"field":field,"unit":unit,"start":value,"lower":value*.7,"upper":value*1.3,"free":True})
            self.session.documents[key]=make_document(key,"Rubber identification","Numerical","N-FIT",1,payload)
        return self.open(key)

    def plan_dialog(self,parent):
        dialog=QDialog(parent);dialog.setWindowTitle("Research plan");dialog.resize(780,510)
        layout=QFormLayout(dialog)
        source=parent.data.get("plan_proposal",{})
        objective=QLineEdit(source.get("objective",parent.data.get("next_research","")))
        variables=QLineEdit(source.get("variables","Thickness, contact friction"))
        response=QLineEdit(source.get("response","Gauge extension"))
        budget=QSpinBox();budget.setRange(1,10000);budget.setValue(int(source.get("budget",12)))
        layout.addRow("Objective",objective);layout.addRow("Variables",variables);layout.addRow("Response",response);layout.addRow("Evaluation budget",budget)
        layout.addRow(QLabel("Edit the numerical definition before submitting any evaluation."))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        save=buttons.addButton("Save proposal",QDialogButtonBox.ButtonRole.ActionRole)
        numerical=buttons.addButton("Open editable Numerical plan",QDialogButtonBox.ButtonRole.AcceptRole)
        def record():
            proposal={"objective":objective.text(),"variables":variables.text(),"response":response.text(),"budget":budget.value()}
            self.session.edit(parent.key,"plan_proposal",proposal);parent.update_title();return proposal
        save.clicked.connect(lambda:(record(),dialog.accept()))
        def create():
            from prototype_state import make_document,token
            proposal=record();key="plan:"+parent.key
            if key not in self.session.documents:
                payload=clone(self.session.doc("numerical")["saved"]);payload.update(method="DOE",budget=budget.value(),proposal=proposal,parent_key=parent.key)
                payload["evaluator"]="Unassigned";payload["variables"]=[];payload["responses"]=[]
                self.session.documents[key]=make_document(key,"Next experiment","Numerical",token("N"),0,payload)
                self.session.documents[key]["dirty"]=True
            self.open(key);dialog.accept()
        numerical.clicked.connect(create);buttons.rejected.connect(dialog.reject);layout.addRow(buttons);dialog.exec()

    def adoption_dialog(self,parent,group_id):
        group=self.session.groups[group_id]
        dialog=QDialog(parent);dialog.setWindowTitle("Apply candidate "+group["candidate"]);dialog.resize(850,410)
        layout=QVBoxLayout(dialog)
        table=make_table(["Target","Current","Proposed","Unit","State"],[])
        table.setRowCount(2)
        for column,width in enumerate((175,120,120,70)):table.setColumnWidth(column,width)
        layout.addWidget(table)
        controls=QHBoxLayout()
        failure_message=QLabel("")
        def redraw():
            for i,key in enumerate(("cad","material")):
                row=group["owners"][key];doc=self.session.doc(key)
                values=[doc["name"],doc["saved"][row["field"]],row["candidate"],"mm" if key=="cad" else "MPa",
                        "Save failed" if row.get("error") else row["status"].title()]
                for j,value in enumerate(values):table.setItem(i,j,QTableWidgetItem(str(value)))
            publish.setEnabled(all(r["status"]=="SAVED" for r in group["owners"].values()) and group["status"]!="CANCELLED")
        def apply(key):
            try:self.session.apply_owner(group_id,key);failure_message.clear()
            except ReviewError as error:failure_message.setText(str(error))
            redraw()
        def save_owner(key):
            try:
                injected=key=="material" and self.session.selected.pop("inject_material_save_failure",False)
                self.session.save_adoption_owner(group_id,key,fail=injected)
                group["owners"][key].pop("error",None);failure_message.clear()
            except (ReviewError,OSError) as error:
                group["owners"][key]["error"]=str(error);failure_message.setText(str(error))
            redraw()
        for key in ("cad","material"):
            label="CAD" if key=="cad" else "Material"
            controls.addWidget(button("Apply "+label,lambda checked=False,k=key:apply(k)))
            controls.addWidget(button("Save "+label,lambda checked=False,k=key:save_owner(k)))
        layout.addLayout(controls);layout.addWidget(failure_message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        publish=buttons.addButton("Confirm saved selection",QDialogButtonBox.ButtonRole.AcceptRole)
        def finish():
            try:
                self.session.publish_group(group_id)
                failure_message.setText("CAD and Material are saved. Candidate selection recorded.")
                redraw();publish.setEnabled(False)
                buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Close")
            except (ReviewError,OSError) as error:failure_message.setText(str(error))
        publish.clicked.connect(finish)
        def close():
            if not group["receipt"]:self.session.cancel_adoption(group_id)
            dialog.reject()
        buttons.rejected.connect(close);layout.addWidget(buttons);redraw()
        dialog.exec()
        if not group["receipt"] and group["status"]!="CANCELLED":self.session.cancel_adoption(group_id)
        for key in ("cad","material"):
            if key in self.windows:self.windows[key].refresh()
        parent.update_title("Candidate "+group["candidate"]+" / "+group["status"].lower())

    def receipts(self,parent):
        rows=[g["receipt"] or {"candidate":g["candidate"],"status":g["status"]} for g in self.session.groups.values()]
        text_dialog(parent,"Saved candidate selections",json.dumps(rows,ensure_ascii=False,indent=2))

    def repair_material(self,parent,key):
        doc=self.session.doc(key);dependencies=doc["saved"]["dependencies"]
        dialog=QDialog(parent);dialog.setWindowTitle("Locate material observations");dialog.resize(800,390)
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel(doc["name"]+" — saved material stays open"))
        table=make_table(["Observation","Availability","Candidate"],[[d["name"],"Missing" if d["missing"] else "Available",""] for d in dependencies])
        layout.addWidget(table);status=QLabel("Choose a replacement file to compare its content.");layout.addWidget(status)
        candidate={"path":None,"same":False}
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        locate=buttons.addButton("Locate…",QDialogButtonBox.ButtonRole.ActionRole)
        repair=buttons.addButton("Use identical file",QDialogButtonBox.ButtonRole.ActionRole);repair.setEnabled(False)
        branch=buttons.addButton("Create changed-content branch",QDialogButtonBox.ButtonRole.ActionRole);branch.setEnabled(False)
        def choose():
            path,_=QFileDialog.getOpenFileName(dialog,"Locate "+dependencies[0]["name"],str(HERE/"fixtures"),"CSV (*.csv);;All files (*)")
            if not path:return
            candidate["path"]=path;candidate["same"]=hashlib.sha256(Path(path).read_bytes()).hexdigest()==dependencies[0]["sha256"]
            status.setText("Identical content. Existing material and results are retained." if candidate["same"] else "Content differs. A separate material branch is required.")
            table.item(0,2).setText(Path(path).name);repair.setEnabled(candidate["same"]);branch.setEnabled(not candidate["same"])
        def apply(changed):
            try:
                result=self.session.repair_dependency(key,dependencies[0]["id"],candidate["path"],changed)
                if result["kind"]=="CHANGED_CONTENT_BRANCH":self.open(result["key"])
                dialog.accept()
            except (OSError,ReviewError) as error:status.setText(str(error))
        locate.clicked.connect(choose);repair.clicked.connect(lambda:apply(False));branch.clicked.connect(lambda:apply(True))
        buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec();parent.update_title()

    def calibration(self,parent):
        cal=self.session.doc("data")["draft"]["calibration"]
        dialog=QDialog(parent);dialog.setWindowTitle("Calibration — force channel");dialog.resize(850,620)
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel(cal["id"]+" / source revision "+str(cal["revision"])))
        layout.addWidget(QLabel(cal["locator"]+"   |   "+cal["range"]))
        view=QPlainTextEdit();view.setReadOnly(True);layout.addWidget(view)
        path=Path(self.session.relocations.get("CAL-018",{}).get("path",HERE/"fixtures"/cal["file"]))
        def show_path(path):
            if not path.exists():view.setPlainText("Original file unavailable: "+path.name+"\nLocate the same calibration source.");return
            expected=cal.get("sha256")
            if expected and hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise ReviewError("This is not the registered calibration original.")
            view.setPlainText(path.read_text(encoding="utf-8"))
            if view.find("row 18"):view.ensureCursorVisible()
        show_path(path)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        locate=buttons.addButton("Locate original…",QDialogButtonBox.ButtonRole.ActionRole)
        def choose():
            chosen,_=QFileDialog.getOpenFileName(dialog,"Locate calibration original",str(HERE/"fixtures"),"Text (*.txt);;All files (*)")
            if chosen:
                try:
                    show_path(Path(chosen));self.session.relocations["CAL-018"]={"path":chosen}
                except (OSError,ReviewError) as error:QMessageBox.warning(dialog,"Original source mismatch",str(error))
        locate.clicked.connect(choose);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons);dialog.exec()


def main(argv=None):
    parser=argparse.ArgumentParser(description="Native Qt UX planning prototype; no solver/provider calls.")
    parser.add_argument("--tool",choices=list(TOOL_NAMES),default="cad")
    parser.add_argument("--workspace",type=Path)
    parser.add_argument("--session",type=Path)
    parser.add_argument("--scenario",choices=["default","material-repair"],default="default")
    args=parser.parse_args(argv)
    app=QApplication(sys.argv[:1]);app.setApplicationName("Autonomous CAE Lab UX review")
    configure_application_fonts(app)
    app.setStyle("Fusion");app.setStyleSheet(STYLE)
    session=ReviewSession.open_session(args.session) if args.session else ReviewSession(args.workspace)
    if args.scenario=="material-repair":session.material_repair_scenario()
    hub=DesktopHub(session)
    entry=session.selected.get("tool",args.tool) if args.session else ("material" if args.scenario=="material-repair" else args.tool)
    hub.open(entry)
    return app.exec()


if __name__=="__main__":
    raise SystemExit(main())
