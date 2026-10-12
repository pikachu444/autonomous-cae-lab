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
import sys
from pathlib import Path

try:
    from PySide6.QtCore import Qt, QTimer, QSize, QItemSelection, QItemSelectionModel
    from PySide6.QtGui import QAction, QKeySequence, QFont, QColor, QTextCursor
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QDockWidget, QVBoxLayout, QHBoxLayout,
        QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem, QTableWidgetItem,
        QLabel, QComboBox, QPushButton, QToolBar, QFileDialog, QDialog,
        QDialogButtonBox, QMessageBox, QLineEdit, QPlainTextEdit, QFormLayout,
        QDoubleSpinBox, QSpinBox, QCheckBox, QSlider, QListWidget, QListWidgetItem,
        QAbstractItemView, QMenu, QHeaderView, QStackedWidget,
    )
except ImportError:
    raise SystemExit("PySide6 is not available in this interpreter. Use the existing Windows Python 3.13 / PySide6 6.9.1 environment. Nothing was installed.")

from prototype_state import (ReviewSession, ReviewError, TOOL_NAMES, METHODS, HERE, clone, digest,
                             RESPONSE_ROLES, EVALUATORS, VARIABLE_BINDINGS)
from qt_widgets import make_table, CurveView, EngineeringView, NodeView, BLUE, TEAL, ORANGE, RED

STYLE = """
QWidget { color: #263442; font-family: 'Segoe UI'; font-size: 10pt; }
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


def box(*widgets, horizontal=False, margins=0):
    w = QWidget()
    layout = QHBoxLayout(w) if horizontal else QVBoxLayout(w)
    layout.setContentsMargins(margins, margins, margins, margins)
    layout.setSpacing(5)
    for child in widgets:
        layout.addWidget(child)
    return w


def button(label, callback):
    b = QPushButton(label)
    b.clicked.connect(callback)
    return b


def text_dialog(parent, title, text, width=820):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(width, 580)
    view = QPlainTextEdit(text)
    view.setReadOnly(True)
    view.setFont(QFont("Consolas", 10))
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


def fill_table(table, rows, editable=()):
    """Replace rows without treating a refresh as user input."""
    blocked = table.blockSignals(True)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
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

    def save(self, force_path=False):
        self.flush_editor()
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

    def edit_number(self, field, item, nested=None):
        text=item.text()
        doc=self.document
        locator=(nested+"."+field) if nested else field
        try:
            value=number(text)
        except ValueError:
            doc["buffers"][locator]=text
            doc["dirty"]=True
            mark_invalid(item, True)
            self.update_title("Invalid input retained: "+locator)
            return
        doc["buffers"].pop(locator,None)
        payload=clone(self.data)
        if nested:
            payload[nested][field]=value
        else:
            payload[field]=value
        self.session.change(self.key,payload,"Edit "+locator)
        mark_invalid(item, False)
        self.update_title()

    def submit_review(self):
        self.flush_editor()
        if self.session.diagnostics(self.key):
            self.input_diagnostics()
            return
        frozen=self.session.freeze(self.key)
        dialog=QDialog(self); dialog.setWindowTitle("Review frozen input"); dialog.resize(700,470)
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel("시안: 실행 파일을 호출하지 않고 선택·제출·취소 경로를 검토합니다."))
        rows=[["Document",self.document["name"]],["Saved revision",frozen["source"]["revision"]],
              ["Owner",self.document["owner"]],["Execution","NOT_EXECUTED"]]
        if "included_count" in frozen:
            rows.extend([["Included samples",frozen["included_count"]],
                         ["Observation revision",frozen["observation_ref"]["revision"]]])
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
            mode="Contact" if "contact" in field else "Mesh" if "mesh" in field else "Features"
            self.mode.setCurrentText(mode)
            if field in ("thickness","width","height"):
                self.props.setCurrentCell(("thickness","width","height").index(field),1);self.props.setFocus()
        elif self.document["owner"]=="Numerical":
            if field=="evaluator":self.evaluator.setFocus()
            else:
                index=1 if field=="responses" or any(r["name"]==field for r in self.data["responses"]) else 0
                self.top_tabs.setCurrentIndex(index)
                table=self.responses if index else self.variables
                table.setFocus()
        elif self.document["owner"]=="Simulation" and field in self.numeric_fields:
            self.table.setCurrentCell(self.numeric_fields.index(field),1);self.table.setFocus()
        elif self.document["owner"]=="PDE":
            self.equation.setFocus()
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
        self.action(self.toolbar,"Freeze input…",self.submit_review)
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
        self.task_pages.addWidget(box(QLabel("Rectangle sketch"),self.constraints,
            button("Constrain rectangle",self.constrain_sketch),margins=7))
        self.hole=QCheckBox("Through hole");self.hole.toggled.connect(self.hole_changed)
        self.task_pages.addWidget(box(QLabel("Pad / pocket"),self.props,self.hole,
            button("Edit sketch",lambda:self.mode.setCurrentText("Sketch")),margins=7))
        self.instances=QSpinBox();self.instances.setRange(1,4);self.instances.valueChanged.connect(self.assembly_changed)
        self.joint=QComboBox();self.joint.addItems(["Fixed","Revolute","Slider"]);self.joint.currentTextChanged.connect(self.assembly_changed)
        form=QFormLayout();form.addRow("Instances",self.instances);form.addRow("Joint",self.joint)
        fw=QWidget();fw.setLayout(form);self.task_pages.addWidget(box(fw,margins=7))
        self.angle=QDoubleSpinBox();self.angle.setRange(-180,180);self.angle.setSuffix(" deg");self.angle.valueChanged.connect(self.preview_pose)
        self.task_pages.addWidget(box(QLabel("Joint motion"),self.angle,button("Use pose",self.use_pose),margins=7))
        self.mesh_size=QDoubleSpinBox();self.mesh_size.setRange(.05,50);self.mesh_size.setSuffix(" mm");self.mesh_size.valueChanged.connect(self.mesh_changed)
        self.task_pages.addWidget(box(QLabel("Element size"),self.mesh_size,
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
        self.task_pages.addWidget(box(self.contact_table,
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
            payload["contact"]["resolved"]=False;payload["mesh"]["stale"]=True
            self.session.change(self.key,payload,"Create geometry");self.refresh();self.mode.setCurrentText("Sketch")

    def import_geometry(self):
        path,_=QFileDialog.getOpenFileName(self,"Select native geometry","","Geometry (*.FCStd *.step *.stp *.iges *.igs);;All files (*)")
        if path:
            self.session.edit(self.key,"import_proposal",{"path":path,"reader":"FreeCAD","status":"NOT_LOADED"})
            self.update_title(Path(path).name+" selected; native import is not connected")

    def property_changed(self,item):
        if self._building or item.column()!=1:return
        self.edit_number(["thickness","width","height"][item.row()],item);self.update_view()

    def constraint_changed(self,item):
        if self._building or item.column()!=1:return
        self.edit_number(["width","height"][item.row()],item)
        self.session.edit(self.key,"sketch",{"length_constraint":str(self.data["width"]),"fully_constrained":False});self.update_view()

    def constrain_sketch(self):
        if any(self.data[k]<=0 for k in ("width","height")):raise ReviewError("Use positive rectangle dimensions.")
        self.session.edit(self.key,"sketch",{"length_constraint":str(self.data["width"]),"fully_constrained":True})
        self.update_title("Rectangle dimensions assigned in illustration; native constraint solve pending")

    def hole_changed(self,value):
        if not self._building:
            payload=clone(self.data);payload["through_hole"]=value;payload["mesh"]["stale"]=True
            self.session.change(self.key,payload,"Edit through hole");self.update_view();self.update_title()

    def assembly_changed(self,*args):
        if self._building:return
        payload=clone(self.data);payload["instances"]=self.instances.value();payload["joint"]["type"]=self.joint.currentText()
        self.session.change(self.key,payload,"Edit assembly");self.update_view();self.update_title()

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
        if row>=0:self.viewer.annotation="Element "+self.quality.item(row,0).text();self.viewer.update()

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
        self.pose_preview=value;self.viewer.yaw=-.52+math.radians(value-15);self.viewer.update()

    def use_pose(self):
        payload=clone(self.data);payload["joint"]["angle"]=getattr(self,"pose_preview",15)
        self.session.change(self.key,payload,"Use reviewed pose");self.update_title()

    def break_contact(self):
        payload=clone(self.data);payload["contact"]["resolved"]=False;payload["mesh"]["stale"]=True
        self.session.change(self.key,payload,"Review geometry change");self.update_title("Contact needs rebind; mesh is stale")

    def rebind(self):
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
        self.session.change(self.key,payload,"Review rebuilt mesh fixture")
        self.viewer.mesh=True;self.viewer.update();self.update_title("Synthetic mesh preview; native mesher not executed")

    def check(self):
        errors=self.session.diagnostics(self.key)
        if errors:raise ReviewError("\n".join(field+": "+msg for field,msg in errors))
        self.update_title("Required input checked; native validation remains pending")

    def to_simulation(self):
        self.flush_editor();self.check()
        if self.document["dirty"]:raise ReviewError("Save the edited geometry before using it in Simulation.")
        self.session.edit("simulation","model_ref",{"id":self.document["id"],"revision":self.document["revision"]})
        self.hub.open("simulation").refresh()

    def update_view(self):
        for key in ("thickness","width","height","geometry_type","instances","through_hole"):
            setattr(self.viewer,{"width":"model_width","height":"model_height"}.get(key,key),self.data.get(key,{"geometry_type":"Clamp","instances":2,"through_hole":False}.get(key)))
        self.viewer.conditions=self.data.get("conditions",[]);self.viewer.update()

    def refresh(self):
        was=self._building;self._building=True
        fill_table(self.props,[[key.title(),self.raw(key,self.data[key]),"mm"] for key in ("thickness","width","height")],(1,))
        fill_table(self.constraints,[[key.title(),self.raw(key,self.data[key]),"mm"] for key in ("width","height")],(1,))
        fill_table(self.contact_table,[["A",v] for v in self.data["contact"]["set_a"]]+[["B",v] for v in self.data["contact"]["set_b"]])
        fill_table(self.conditions,[[c["type"],c["face"],c["value"],c["unit"]] for c in self.data.get("conditions",[])])
        self.law.setCurrentText(self.data["contact"]["law"]);self.mu.setValue(self.data["contact"]["mu"]);self.gap.setValue(self.data["contact"]["gap"])
        self.instances.setValue(self.data.get("instances",2));self.joint.setCurrentText(self.data["joint"]["type"])
        self.angle.setValue(self.data["joint"]["angle"]);self.mesh_size.setValue(self.data["mesh"]["size"]);self.hole.setChecked(self.data.get("through_hole",False))
        self.tree.clear();root=QTreeWidgetItem(self.tree,[self.document["name"]])
        for name in ("Base",self.data.get("geometry_type","Clamp"),"Sketch","Features","Assembly","Motion","Mesh","Conditions","Contact"):QTreeWidgetItem(root,[name])
        self.tree.expandAll();self.update_view();self._building=was;self.update_title()


class SimulationWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Check",self.check)
        self.action(self.toolbar,"Freeze input…",self.submit_review)
        self.action(self.toolbar,"Runner",lambda:self.hub.open("runner"))
        self.action(self.toolbar,"Evaluation",lambda:self.hub.open("evaluation"))
        self.tree=QTreeWidget();self.tree.setHeaderHidden(True)
        root=QTreeWidgetItem(self.tree,[self.document["name"]])
        for name in ("Model","Steps","Boundary conditions","Contact","Initial conditions","Failure","Output"):
            QTreeWidgetItem(root,[name])
        self.tree.expandAll()
        self.add_dock("Model",self.tree,minimum=230)
        self.viewer=EngineeringView(self.key)
        payload=self.data
        if self.key in ("thermal","thermoelastic"):
            fields=(("temperature","K"),) if self.key=="thermal" else (("Tref","K"),("alpha","1/K"))
            self.viewer.field=payload["field"]+" ["+payload["unit"]+"]"
            self.table=make_table(["Setting","Value","Unit"],
                [[key,payload[key],unit] for key,unit in fields],editable=(1,),select_rows=False)
            self.numeric_fields=[key for key,unit in fields]
            settings=box(QLabel(payload["family"]),QLabel(payload["backend"]),self.table,
                         QLabel(payload["mesh"]),QLabel("Actual field: pending"),margins=10)
        else:
            self.family=QComboBox();self.family.addItems(["Nonlinear implicit","Explicit impact","Failure / interface"])
            self.family.setCurrentText(payload["family"])
            self.family.currentTextChanged.connect(self.family_changed)
            self.numeric_fields=["duration","increments","force","initial_velocity","angular_velocity","time_step"]
            self.table=make_table(["Setting","Value","Unit"],[
                ["Step duration",payload["duration"],"s"],["Max increments",payload["increments"],""],
                ["Load",payload["force"],"N"],["Initial velocity",payload["initial_velocity"],"m/s"],
                ["Angular velocity",payload["angular_velocity"],"rad/s"],["Time step",payload["time_step"],"s"]],
                editable=(1,),select_rows=False)
            self.backend=QComboBox();self.backend.addItems(["Code_Aster","OpenCourant / OpenRadioss","CalculiX","External deck"])
            self.backend.setCurrentText(payload["backend"])
            self.backend.currentTextChanged.connect(lambda v:self.edit_value("backend",v))
            settings=box(QLabel("Analysis"),self.family,self.backend,self.table,
                         QLabel("Output"),make_table(["Quantity","Location"],[
                             ["Displacement / reaction","Node"],["Contact pressure / slip","Contact surface"],
                             ["Internal / kinetic / contact energy","Global"],["Damage / failure","Declared association"]]),margins=10)
        self.table.itemChanged.connect(self.cell_changed)
        split=QSplitter();split.addWidget(settings);split.addWidget(self.viewer);split.setSizes([400,760])
        self.setCentralWidget(split)
        self.tree.itemSelectionChanged.connect(self.selection_changed)

    def edit_value(self,field,value):
        if not self._building:self.session.edit(self.key,field,value);self.update_title()

    def cell_changed(self,item):
        if not self._building and item.column()==1:self.edit_number(self.numeric_fields[item.row()],item)

    def family_changed(self,value):
        self.edit_value("family",value)
        self.update_title(value+" draft; adapter is not connected")

    def selection_changed(self):
        node=self.tree.currentItem()
        if not node:return
        name=node.text(0)
        if name=="Contact":self.hub.open("cad").mode.setCurrentText("Contact")
        elif name=="Failure" and hasattr(self,"family"):self.family.setCurrentText("Failure / interface")

    def check(self):
        errors=self.session.diagnostics(self.key)
        if errors:raise ReviewError("\n".join(message for field,message in errors))
        self.update_title("Draft retained. Actual adapter admission is not verified.")

    def refresh(self):
        self._building=True
        for i,key in enumerate(self.numeric_fields):self.table.item(i,1).setText(str(self.raw(key,self.data[key])))
        if hasattr(self,"family"):self.family.setCurrentText(self.data["family"])
        self._building=False;self.update_title()


class DataWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Import CSV…",self.import_csv)
        self.action(self.toolbar,"Exclude",lambda:self.exclude(True))
        self.action(self.toolbar,"Restore",lambda:self.exclude(False))
        self.action(self.toolbar,"Calibration…",self.calibration)
        self.action(self.toolbar,"Material",lambda:self.hub.open("material"))
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
        fields=["name","unit","role","formula"];payload=clone(self.data)
        payload["columns"][item.column()][fields[item.row()]]=item.text()
        self.session.change(self.key,payload,"Edit column "+fields[item.row()])
        self.update_title("Column metadata edited; no numeric conversion was applied")

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
        combos={}
        defaults={"time":"time_s","extension":"extension_mm","force":"force_N","temperature":"temperature_C"}
        for key,title in [("time","Time [s]"),("extension","Gauge extension [mm]"),("force","Force [N]"),("temperature","Temperature [degC]")]:
            combo=QComboBox();combo.addItems(fields)
            if defaults[key] in fields:combo.setCurrentText(defaults[key])
            combos[key]=combo;layout.addRow(title,combo)
        layout.addRow(QLabel("Selected units describe source values. No implicit unit conversion."))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addRow(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        if len({c.currentText() for c in combos.values()})!=4:
            raise ReviewError("Each required role must map to a distinct source column.")
        samples=[]
        for i,row in enumerate(rows):
            sample={"id":f"A{i}"}
            for key,combo in combos.items():
                try:sample[key]=number(row[combo.currentText()])
                except (ValueError,TypeError):raise ReviewError(f"Invalid {key} in source row {i+2}. Original CSV is unchanged.")
            samples.append(sample)
        if any(b["time"]<=a["time"] for a,b in zip(samples,samples[1:])):
            raise ReviewError("Time must be strictly increasing. Source order was preserved.")
        payload=clone(self.data);payload.update(samples=samples,quality_excluded=[],exclusion_reasons={})
        payload["import"]={"filename":Path(path).name,"path":path,
                           "sha256":hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                           "mapping":{k:c.currentText() for k,c in combos.items()}}
        self.session.change(self.key,payload,"Import measurement CSV");self.refresh()

    def refresh(self):
        self._building=True
        selected=self.session.selected.get("samples",[])
        self.table.blockSignals(True);self.table.setSortingEnabled(False)
        samples=self.data["samples"];self.table.setRowCount(len(samples))
        for r,sample in enumerate(samples):
            for c,field in enumerate(("id","time","extension","force","temperature")):
                item=QTableWidgetItem();item.setData(Qt.ItemDataRole.DisplayRole,sample[field])
                item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable)
                if c==0:item.setData(Qt.ItemDataRole.UserRole,sample["id"])
                self.table.setItem(r,c,item)
        self.table.setSortingEnabled(True);self.table.blockSignals(False)
        self.curve.set_series([{"name":"Tension A","x":[s["extension"] for s in samples],
            "y":[s["force"] for s in samples],"ids":[s["id"] for s in samples],"color":BLUE}])
        self.paint_mask();self.curve_selected(selected)
        self._building=False
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
        law=QComboBox();law.addItems(["Neo-Hookean","J2 plasticity","Drucker–Prager","Prony viscoelastic","User constitutive law"])
        law.setCurrentText(self.data["law"])
        law.currentTextChanged.connect(lambda value:self.edit_law(value))
        protocol=QComboBox();protocol.addItems(["Uniaxial traction-free","Prescribed deformation gradient","Measured transverse history"])
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
        self.set_curves()

    def set_curves(self,holdout=False):
        xs=[i*.004 for i in range(81)]
        self.curve.set_series([
            {"name":"Observed B (holdout)" if holdout else "Observed A","x":xs,
             "y":[.85*(x+1-(1+x)**-2) for x in xs],"color":BLUE},
            {"name":"Retained prediction","x":xs,
             "y":[.87*(x+1-(1+x)**-2) for x in xs],"color":ORANGE}])
        self.curve.caption="Synthetic fixture; changing coefficients does not recompute this result"

    def coeff_changed(self,item):
        if self._building or item.column()!=1:return
        self.edit_number(["mu","bulk"][item.row()],item)
        self.output.setPlainText("Current coefficients edited. The displayed prediction retains its original input.\n"
                                 "Save the draft and choose Direct evaluation to review a new attempt.")

    def test_changed(self):
        self.set_curves(self.tests.currentRow()==1)

    def edit_law(self,value):
        if not self._building:self.session.edit(self.key,"law",value);self.update_title("Law draft retained; evaluate capability separately")

    def edit_protocol(self,value):
        if not self._building:self.session.edit(self.key,"protocol",value);self.update_title()

    def show_holdout(self):
        self.tests.setCurrentCell(1,0);self.set_curves(True)

    def open_fit(self):
        self.hub.open_fit(self.key)

    def protocol_dialog(self):
        dialog=QDialog(self);dialog.setWindowTitle("Load case history and constitutive state");dialog.resize(850,540)
        layout=QVBoxLayout(dialog);tabs=QTabWidget()
        tabs.addTab(make_table(["Time [s]","Control","Target","Unit"],
            [[0,"Stretch F11",1,""],[1,"Stretch F11",1.2,""],[60,"Hold",1.2,""]],editable=(0,1,2,3)),"History")
        tabs.addTab(make_table(["Variable","Initial state","Rule"],
            [["Plastic strain",0,"Per-candidate isolated"],["Damage",0,"History preserving"],
             ["Lateral traction",0,"Mixed-control evaluator required"]],editable=(1,)),"State")
        tabs.addTab(make_table(["Check","Value","State"],
            [["Consistent tangent error",None,"NOT_EVALUATED"],["Increment refinement",None,"NOT_EVALUATED"],
             ["Return mapping failure",None,"No evaluator called"]]),"Integration / tangent")
        layout.addWidget(tabs)
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);close.rejected.connect(dialog.reject)
        layout.addWidget(close);dialog.exec()

    def repair(self):
        self.hub.repair_material(self,self.key)

    def refresh(self):
        self._building=True
        for i,k in enumerate(("mu","bulk")):self.coeff.item(i,1).setText(str(self.data[k]))
        self._building=False;self.update_title()


class PDEWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Check equation",self.check)
        self.action(self.toolbar,"Evaluate…",self.evaluate)
        self.action(self.toolbar,"Evaluation",lambda:self.hub.open("evaluation"))
        self.tree=QTreeWidget();self.tree.setHeaderHidden(True)
        root=QTreeWidgetItem(self.tree,["Diffusion"])
        for name in ("Domain","Mesh","Field u","Equation","Left edge","Right edge","Initial condition","Study"):
            QTreeWidgetItem(root,[name])
        self.tree.expandAll()
        self.add_dock("Model Builder",self.tree,minimum=225)
        self.form=QComboBox();self.form.addItems(["Registered PDE","General weak form","ODE"])
        self.form.setCurrentText(self.data["form"])
        self.form.currentTextChanged.connect(self.form_changed)
        self.equation=QPlainTextEdit(self.data["equation"])
        self.equation.setMaximumHeight(160)
        self.equation.textChanged.connect(self.equation_changed)
        self.coefficients=make_table(["Coefficient","Value","Unit"],[
            ["k",self.data["k"],"declared"],["f",self.data["f"],"declared"],
            ["Mesh size",self.data["mesh"],"m"]],editable=(1,),select_rows=False)
        self.coefficients.itemChanged.connect(self.coefficient_changed)
        self.selected_node=QLabel("Equation")
        self.boundary=QLineEdit(self.data["bc"])
        self.boundary.editingFinished.connect(lambda:self.boundary_changed())
        settings=box(self.selected_node,self.form,QLabel("Expression"),self.equation,
                     self.coefficients,QLabel("Boundary condition"),self.boundary,
                     QLabel("Field: u   Space: P1   Domain: Rectangle"),margins=10)
        self.graphics=EngineeringView("pde")
        self.graphics.set_selected(self.data["selection"])
        split=QSplitter();split.addWidget(settings);split.addWidget(self.graphics);split.setSizes([365,820])
        self.setCentralWidget(split)
        messages=make_table(["Location","Message"],[["Adapter","Not connected"],["Equation","Editable draft"],["Result","No calculation"]])
        self.add_dock("Messages",messages,Qt.DockWidgetArea.BottomDockWidgetArea)
        self.tree.itemSelectionChanged.connect(self.node_selected)
        self.graphics.faceSelected.connect(self.graphic_selected)

    def form_changed(self,value):
        if self._building:return
        self.session.edit(self.key,"form",value)
        self.update_title("General weak form / ODE support is retained as an adapter extension" if value!="Registered PDE" else "Registered PDE draft")

    def equation_changed(self):
        if not self._building:self.session.edit(self.key,"equation",self.equation.toPlainText());self.update_title()

    def coefficient_changed(self,item):
        if not self._building and item.column()==1:self.edit_number(["k","f","mesh"][item.row()],item)

    def boundary_changed(self):
        if not self._building:self.session.edit(self.key,"bc",self.boundary.text());self.update_title()

    def node_selected(self):
        node=self.tree.currentItem()
        if node:
            self.selected_node.setText(node.text(0))
            if "edge" in node.text(0):
                self.graphics.set_selected(node.text(0));self.session.edit(self.key,"selection",node.text(0))
                self.update_title()

    def graphic_selected(self,name):
        self.selected_node.setText(name);self.session.edit(self.key,"selection",name);self.update_title()

    def check(self):
        errors=self.session.diagnostics(self.key)
        if errors:self.equation.setFocus();raise ReviewError("\n".join(msg for field,msg in errors))
        self.update_title("Required entries checked. Equation semantics require the selected backend.")

    def evaluate(self):
        if self.data["form"]!="Registered PDE":
            raise ReviewError("The general weak-form / ODE adapter is not connected. Save and continue editing this draft.")
        self.submit_review()

    def refresh(self):
        self._building=True
        self.form.setCurrentText(self.data["form"]);self.equation.setPlainText(self.data["equation"])
        self.boundary.setText(self.data["bc"])
        for r,key in enumerate(("k","f","mesh")):self.coefficients.item(r,1).setText(str(self.data[key]))
        self._building=False;self.update_title()


METHOD_INPUTS = {
    "DOE": [("Sampling","Latin hypercube"),("Design points",20),("Replicates",1)],
    "Inverse": [("Algorithm","Least squares"),("Loss","Huber"),("Residual scale",1.0),("Observation weight",1.0),("Holdout","Tension B")],
    "Optimization": [("Algorithm","Differential evolution"),("Population",15),("Relative tolerance",1e-6)],
    "Sobol sensitivity": [("Design","Saltelli A/B/crossed"),("Base samples",128),("Bootstrap replicates",200),("Input dependence","Independent")],
    "UQ": [("Sampling","Monte Carlo"),("Samples",1000),("Quantiles","0.05, 0.50, 0.95"),("Failure threshold",.35)],
    "RBF surrogate": [("Kernel","Thin plate spline"),("Smoothing",0.0),("Holdout fraction",.2),("Extrapolation","Block outside support")],
    "MOO": [("Method","Epsilon constraint"),("Primary objective","Mass"),("Error thresholds [%]","2.0, 2.5, 3.0, 4.0"),("Feasibility tolerance",1e-6)],
    "MDO": [("Architecture","Existing Evaluation"),("Coupling","Lagged Picard"),("Iteration limit",25),("Coupling tolerance",1e-6)],
}


class NumericalWindow(ToolWindow):
    def build(self):
        self.method=QComboBox();self.method.addItems(list(METHODS));self.toolbar.addWidget(self.method)
        self.method.currentTextChanged.connect(self.method_changed)
        self.action(self.toolbar,"Check",self.input_diagnostics)
        self.action(self.toolbar,"Freeze input…",self.submit_review)
        self.action(self.toolbar,"Review candidate…",self.inspect_candidate)
        self.adopt_action=self.action(self.toolbar,"Apply to owners…",self.adopt)
        self.action(self.review_menu,"Refresh saved observations…",self.refresh_observations)
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
        self.top_tabs=QTabWidget()
        self.top_tabs.addTab(box(self.variables,box(button("Add variable…",self.add_variable),button("Remove",lambda:self.remove_definition("variables")),horizontal=True)),"Variables")
        self.top_tabs.addTab(box(self.responses,box(button("Add response…",self.add_response),button("Remove",lambda:self.remove_definition("responses")),horizontal=True)),"Responses")
        self.top_tabs.addTab(self.method_table,"Method")
        self.top_tabs.addTab(self.method_detail,"Method inputs")
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
        self.setCentralWidget(box(box(QLabel("Evaluator"),self.evaluator,button("Open definition",self.open_evaluator),horizontal=True),split,margins=6))
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
            value=self.session.doc(key)["draft"][name];unit.setText(VARIABLE_BINDINGS[key][name]);start.setText(str(value))
            values=sorted((value*.8,value*1.2));lower.setText(str(values[0] if value else -1));upper.setText(str(values[1] if value else 1))
        owner.currentTextChanged.connect(update_field);field.currentTextChanged.connect(update_value);update_field()
        for label,w in (("Owner",owner),("Field",field),("Unit",unit),("Start",start),("Search lower",lower),("Search upper",upper)):form.addRow(label,w)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            payload=clone(self.data)
            if any(v["owner"]==owner.currentText() and v["field"]==field.currentText() for v in payload["variables"]):raise ReviewError("This owner field is already a variable.")
            payload["variables"].append({"owner":owner.currentText(),"field":field.currentText(),"unit":unit.text(),
                "start":number(start.text()),"lower":number(lower.text()),"upper":number(upper.text()),"free":True,"type":"float"})
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
                "limit":number(limit.text()) if limit.text().strip() else "","location":location.text(),"time":number(time.text()),"reduction":reduction.currentText()})
            self.session.change(self.key,payload,"Define response");self.refresh();self.top_tabs.setCurrentIndex(1)

    def remove_definition(self,kind):
        table=self.variables if kind=="variables" else self.responses;row=table.currentRow()
        if row<0:return
        payload=clone(self.data);payload[kind].pop(row)
        prefix=kind+".";self.document["buffers"]={k:v for k,v in self.document["buffers"].items() if not k.startswith(prefix)}
        self.session.change(self.key,payload,"Remove "+kind[:-1]);self.refresh()

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
            self.document["buffers"][locator]=item.text();self.document["dirty"]=True;mark_invalid(item,True);self.update_title("Correct variable value before freeze");return
        self.document["buffers"].pop(locator,None);payload["variables"][item.row()][field]=value
        self.session.change(self.key,payload,"Edit variable "+field);mark_invalid(item,False);self.update_title()

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
            self.document["buffers"][locator]=item.text();self.document["dirty"]=True;mark_invalid(item,True);self.update_title();return
        self.document["buffers"].pop(locator,None)
        payload.setdefault("method_settings",{}).setdefault(self.data["method"],{})[name]=value
        self.session.change(self.key,payload,"Edit method input");mark_invalid(item,False);self.update_title()

    def method_rows(self):
        variables=self.data["variables"];method=self.data["method"]
        if method in ("UQ","Sobol sensitivity"):
            return [[v["owner"]+"."+v["field"],f"Uniform({v['lower']}, {v['upper']})","Independent"] for v in variables]
        if method=="Inverse":return [["Training observations",self.data.get("holdout","Tension B"),"Separate holdout"],["Residual", "prediction − observation","Train samples only"]]
        if method=="RBF surrogate":return [["Training cases","Select retained input / response table","Training"],["Validation cases","Independent holdout","Validation"]]
        if method=="MDO":return [["Heat","V-02 / temperature [K]","Evaluation stage"],["Expand","V-03 / displacement [m]","Receiver"]]
        if method=="MOO":return [[r["name"],str(r["limit"]),r["role"]] for r in self.data["responses"]]
        return [[v["owner"]+"."+v["field"],f"{v['lower']} … {v['upper']}","Free" if v["free"] else "Fixed"] for v in variables]

    def detail_changed(self,item):
        if self._building:return
        rows=[[self.method_detail.item(r,c).text() for c in range(3)] for r in range(self.method_detail.rowCount())]
        payload=clone(self.data);payload.setdefault("method_inputs",{})[self.data["method"]]=rows
        self.session.change(self.key,payload,"Edit "+self.data["method"]+" definition");self.update_title()

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
        fill_table(self.responses,[[r["name"],r["role"],r["limit"],r["unit"],r.get("location","Global"),r.get("time",.04),r.get("reduction","Value at time")] for r in self.data["responses"]],(0,1,2,3,4,5,6))
        method=self.data["method"];settings=self.data.get("method_settings",{}).get(method,{})
        rows=[["Total evaluation budget",self.raw("budget",self.data["budget"])],["Seed",self.raw("seed",self.data["seed"])]]
        rows += [[name,self.raw("method."+method+"."+name,settings.get(name,value))] for name,value in METHOD_INPUTS[method]]
        fill_table(self.method_table,rows,(1,))
        fill_table(self.method_detail,self.data.get("method_inputs",{}).get(method,self.method_rows()),(1,2))
        self.top_tabs.setTabText(3,METHODS[method][0])
        fill_table(self.method_view,[[name,None,"NOT_EVALUATED"] for name in METHODS[method][1:]])
        fixture=self.has_fixture();self.case_panel.setVisible(fixture);self.summary.setVisible(fixture);self.adopt_action.setEnabled(fixture)
        self.plot_tabs.setTabEnabled(0,fixture);self.plot_tabs.setTabEnabled(1,fixture);self.plot_tabs.setCurrentIndex(0 if fixture else 2)
        fill_table(self.cases,[[c[k] if c[k] is not None else "—" for k in ("id","mass","error","displacement","clearance","status")] for c in self.session.candidates] if fixture else [])
        valid=[c for c in self.session.candidates if c["status"]=="Retained fixture"]
        self.plot.set_series([{"name":"Feasible fixture candidates","x":[c["mass"] for c in valid],"y":[c["error"] for c in valid],"ids":[c["id"] for c in valid],"color":TEAL}] if fixture else [])
        self._building=was
        if fixture:self.plot_selected([self.session.selected.get("candidate","p19")]);self.candidate_changed()
        self.update_title()


class RunnerWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Open input",self.open_input)
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
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setFont(QFont("Consolas",10))
        self.diagnostics=make_table(["Scope","Message"],[])
        self.result=make_table(["Result quantity","Value","Unit"],[])
        for view,name in [(self.input,"Input"),(self.log,"Log"),(self.diagnostics,"Diagnostics"),(self.result,"Results")]:
            self.tabs.addTab(view,name)
        split=QSplitter(Qt.Orientation.Vertical);split.addWidget(self.jobs);split.addWidget(self.tabs);split.setSizes([370,390])
        self.setCentralWidget(split);self.refresh()

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
            for i,(key,value) in enumerate(result["metrics"].items()):
                self.result.insertRow(i)
                for j,text in enumerate([key,str(value),"kg" if key=="mass" else "mm"]):
                    self.result.setItem(i,j,QTableWidgetItem(text))
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
        pane=box(self.pipeline,QLabel("Properties"),self.filter,self.props,box(button("Apply",self.apply_filter),button("Reset",self.reset_filter),horizontal=True),margins=6)
        dock=self.add_dock("Pipeline Browser",pane,minimum=285);self.resizeDocks([dock],[320],Qt.Orientation.Horizontal)
        self.array.currentTextChanged.connect(self.field_changed);self.association.currentTextChanged.connect(self.association_changed)
        self.time.currentIndexChanged.connect(self.time_changed);self.pipeline.itemSelectionChanged.connect(self.pipeline_selected)
        self.viewer.faceSelected.connect(self.face_selected);self.refresh()

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
        if self.data["pending_filter"]=="Warp by vector" and self.data["array"]!="Displacement":raise ReviewError("Choose the displacement vector for warp.")
        self.session.edit(self.key,"filter",self.data["pending_filter"]);self.render_frame();self.update_title(self.data["filter"]+" illustration applied")

    def reset_filter(self):
        self.session.edit(self.key,"pending_filter",self.data["filter"]);self.refresh()

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
        self.viewer.thickness=self.result().get("input_values",{}).get("thickness",14)
        self.viewer.annotation="" if frame["available"] else "Selected field / association / frame unavailable"
        self.viewer.update();self.curve.ylabel=self.data["array"]+" ["+frame["unit"]+"]";self.curve.cursor_x=self.data["time"]
        if frame["available"]:
            if self.data["filter"]=="Plot over line":
                self.curve.xlabel="Gauge position [mm]";self.curve.cursor_x=None
                self.curve.set_series([{"name":"Synthetic line sample","x":[0,25,50],"y":[0,frame["value"]*.5,frame["value"]],"color":BLUE}])
            else:
                self.curve.xlabel="Time [s]";self.curve.set_series([{"name":"Retained fixture","x":frame["times"],"y":frame["curve"],"color":BLUE}])
        else:self.curve.set_series([])
        rows=[];gauge=self.data.get("gauge",{"a":"Gauge left","b":"Gauge right","direction":"X"})
        gauge_valid=gauge=={"a":"Gauge left","b":"Gauge right","direction":"X"}
        for name,loc in (("Displacement","Gauge endpoints"),("Contact pressure","Contact surface"),("Normal force","Contact resultant")):
            m=frame["measurements"].get(name,{"value":None,"unit":""});value=m["value"] if frame["available"] else None
            if name=="Displacement" and not gauge_valid:value=None;loc="Selected gauge is not retained"
            rows.append(["Gauge extension" if name=="Displacement" else name,value if value is not None else "Unavailable",m["unit"],loc])
        fill_table(self.measure,rows)
        self.curve.caption="Synthetic frame "+str(frame["time"])+" s" if frame["available"] else "Unavailable; no interpolation"

    def compare(self):
        dialog=QDialog(self);dialog.setWindowTitle("Compare results");dialog.resize(1240,700);layout=QVBoxLayout(dialog);picker=QComboBox()
        for rid,result in self.session.results.items():
            if result.get("kind")=="structural" and rid!=self.data["result"]:picker.addItem(result.get("candidate",rid),rid)
        layout.addWidget(box(QLabel("Compare with"),picker,horizontal=True))
        a=EngineeringView("post");b=EngineeringView("post");views=QSplitter();views.addWidget(a);views.addWidget(b);layout.addWidget(views)
        values=make_table(["Quantity","A","B","Unit"],[]);values.setMaximumHeight(135);layout.addWidget(values)
        layout.addWidget(QLabel("Side by side. Spatial mapping is unverified; difference is unavailable."))
        def redraw(*args):
            frames=[self.session.post_frame(self.key),self.session.post_frame(self.key,picker.currentData())]
            for view,frame in zip((a,b),frames):
                view.field=self.data["array"]+" ["+frame["unit"]+"]";view.field_max=frame["value"] or 0
                view.field_available=frame["available"];view.annotation="t = "+str(frame["time"])+" s";view.update()
            fill_table(values,[[self.data["array"],frames[0]["value"],frames[1]["value"],frames[0]["unit"]]])
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
        self.action(self.toolbar,"Ask…",self.ask)
        self.pause_action=self.action(self.toolbar,"Resume",self.pause_resume)
        self.action(self.toolbar,"Plan…",self.edit_plan)
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
        self.reply_target=None
        send=button("Save reply",lambda:self.guard(self.save_reply))
        self.action(self.composer,"Save reply",self.save_reply,"Ctrl+Return").setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        central=box(self.question,self.turns,self.reply_label,self.composer,
                    box(self.topic,button("Reply to selected",self.reply_to),send,horizontal=True),margins=8)
        self.setCentralWidget(central)
        nodes=[("question","지그 유연성",0,160)]
        nodes.extend((topic,topic,230,i*105) for i,topic in enumerate(self.data["topics"]))
        self.map=NodeView(nodes,[("question",t) for t in self.data["topics"]])
        self.map.chosen.connect(self.map_selected)
        self.map.moved.connect(self.map_moved)
        roles=make_table(["Participant","Connection"],[[role,"미연결"] for role in self.data["roles"]])
        roles.setMaximumHeight(150)
        map_dock=self.add_dock("Discussion map",box(self.map,roles),minimum=330)
        self.evidence=make_table(["Evidence","Location"],[[e["label"],e["locator"]] for e in self.data["evidence"]])
        self.evidence.itemDoubleClicked.connect(lambda item:self.open_evidence())
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

    def map_selected(self,key):
        if key in self.data["topics"]:self.topic.setCurrentText(key)

    def map_moved(self,positions):
        if not self._building:self.session.edit(self.key,"map_positions",positions);self.update_title()

    def turn_selected(self,row):
        if row<0 or row>=len(self.data["turns"]):return
        turn=self.data["turns"][row]
        self.topic.setCurrentText(turn["topic"])
        self.update_title("선택 발언: "+turn["role"])

    def reply_to(self):
        row=self.turns.currentRow()
        if row>=0:
            turn=self.data["turns"][row];self.reply_target=turn["id"]
            self.reply_label.setText("Reply to "+turn["role"]);self.composer.setFocus()

    def save_reply(self):
        self.session.append_reply(self.composer.toPlainText(),self.topic.currentText(),self.reply_target)
        self.reply_target=None;self.reply_label.setText("Reply")
        self.refresh()
        self.update_title("사용자 발언 저장 초안. Provider는 미연결입니다.")

    def pause_resume(self):
        self.session.edit(self.key,"paused",not self.data["paused"])
        self.pause_action.setText("Resume" if self.data["paused"] else "Pause")
        self.update_title("Paused" if self.data["paused"] else "대기 중: Provider 미연결")

    def ask(self):
        raise ReviewError("연결된 제품 Expert provider가 없습니다. 질문·발언·논점·계획 초안은 계속 편집하고 저장할 수 있습니다.")

    def open_evidence(self):
        row=self.evidence.currentRow()
        if row<0:raise ReviewError("Select evidence first.")
        ref=self.data["evidence"][row]
        self.hub.open_result(ref["id"])

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
        self.pause_action.setText("Resume" if self.data["paused"] else "Pause")
        self._building=False;self.turns.scrollToBottom();self.update_title("Provider 미연결 · 실제 전문가 발언 없음")


class StudyWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Discuss",lambda:self.hub.open("expert"))
        self.action(self.toolbar,"Next research…",self.next_plan)
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
        self.next=QLineEdit(self.data["next_research"])
        self.next.editingFinished.connect(self.next_changed)
        lower=box(QLabel("Research judgment"),self.judgment,self.reason,
                  button("Apply judgment",lambda:self.guard(self.apply_judgment)),
                  QLabel("Next research"),self.next,margins=8)
        upper=QSplitter();upper.addWidget(self.hypotheses);upper.addWidget(self.evidence);upper.setSizes([630,650])
        split=QSplitter(Qt.Orientation.Vertical);split.addWidget(upper);split.addWidget(lower);split.setSizes([430,300])
        self.setCentralWidget(box(self.question,split,margins=7))

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

    def apply_judgment(self):
        if self.judgment.currentText()!="Undecided" and not self.reason.toPlainText().strip():
            raise ReviewError("Enter the reason for this explicit judgment.")
        payload=clone(self.data);payload["judgment"]=self.judgment.currentText()
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
        self.judgment.setCurrentText(self.data["judgment"]);self.reason.setPlainText(self.data["reason"])
        self.next.setText(self.data["next_research"])
        for row,h in enumerate(self.data["hypotheses"]):self.hypotheses.item(row,1).setText(h["text"])
        self._building=False;self.update_title()


class EvaluationWindow(ToolWindow):
    def build(self):
        self.action(self.toolbar,"Open stage",self.open_stage)
        self.action(self.toolbar,"Move up",lambda:self.move_stage(-1))
        self.action(self.toolbar,"Move down",lambda:self.move_stage(1))
        self.action(self.toolbar,"Check connection",self.check)
        self.action(self.toolbar,"Review attempt…",self.submit_review)
        self.stages=make_table(["Stage","Model","Operation","Output"],[])
        self.stages.itemDoubleClicked.connect(lambda item:self.guard(self.open_stage))
        self.transfer=make_table(["Transfer","Value"],[
            ["From","Heat / temperature [K]"],["To","Expand / temperature input [K]"],
            ["Association","POINTS"],["Mapping","exact_same_mesh"],
            ["Actual field","PENDING"],["Iteration","Lagged Picard"],["Tolerance",self.data["tolerance"]]],
            editable=(1,),select_rows=False)
        self.transfer.itemChanged.connect(self.transfer_changed)
        tabs=QTabWidget();tabs.addTab(self.transfer,"Transfer / iteration")
        status=make_table(["Stage","Solver status","Convergence"],[
            ["Heat","NOT_EXECUTED","NOT_EVALUATED"],["Expand","NOT_EXECUTED","NOT_EVALUATED"]])
        tabs.addTab(status,"Result")
        left=QSplitter(Qt.Orientation.Vertical);left.addWidget(self.stages);left.addWidget(tabs)
        right=EngineeringView("thermal");right.label="Thermal → structural field illustration"
        split=QSplitter();split.addWidget(left);split.addWidget(right);split.setSizes([750,570])
        self.setCentralWidget(split);self.refresh()

    def open_stage(self):
        row=self.stages.currentRow()
        if row<0:raise ReviewError("Select a stage.")
        self.hub.open_reference(self.data["stages"][row]["ref"],self)

    def move_stage(self,offset):
        row=self.stages.currentRow();target=row+offset
        if row<0 or target<0 or target>=len(self.data["stages"]):return
        payload=clone(self.data)
        payload["stages"][row],payload["stages"][target]=payload["stages"][target],payload["stages"][row]
        self.session.change(self.key,payload,"Reorder Evaluation stages");self.refresh();self.stages.selectRow(target)

    def transfer_changed(self,item):
        if self._building or item.column()!=1:return
        if item.row()==6:self.edit_number("tolerance",item)
        else:
            payload=clone(self.data);payload.setdefault("transfer_draft",{})[str(item.row())]=item.text()
            self.session.change(self.key,payload,"Edit transfer setting");self.update_title()

    def check(self):
        self.update_title("Static connection proposal inspected. Actual source field remains pending.")

    def refresh(self):
        self._building=True;self.stages.setRowCount(len(self.data["stages"]))
        for r,stage in enumerate(self.data["stages"]):
            key,payload=self.session.resolve(stage["ref"])
            row=[stage["stage"],self.session.doc(key)["name"],stage["operation"],payload["field"]+" ["+payload["unit"]+"]"]
            for c,value in enumerate(row):self.stages.setItem(r,c,QTableWidgetItem(value))
        self._building=False;self.update_title()


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
        self.setCentralWidget(self.graph)
        self.items=make_table(["Document","Tool"],[[self.session.doc(k)["name"],TOOL_NAMES[k]] for k in coords])
        self.node_keys=list(coords)
        self.items.itemDoubleClicked.connect(lambda item:self.hub.open(self.node_keys[item.row()]))
        dock=self.add_dock("Documents",self.items,minimum=245);self.resizeDocks([dock],[300],Qt.Orientation.Horizontal)
        self.current="cad"

    def selected_node(self,key):
        self.current=key;self.update_title(self.session.doc(key)["name"])

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
            self.update_title("Connection proposal retained; no scheduler or owner was created")


class DesktopHub:
    def __init__(self,session):
        self.session=session;self.windows={};self.other_hubs=[]

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
        key="post:"+result_id
        if key not in self.session.documents:
            from prototype_state import make_document
            payload=clone(self.session.doc("post")["saved"]);payload["result"]=result_id
            result=self.session.results[result_id]
            payload["time"]=result.get("time",.04)
            name=self.session.doc(result["source"]["id"])["name"]+" result" if result["source"]["id"] in [d["id"] for d in self.session.documents.values()] else "Retained result"
            self.session.documents[key]=make_document(key,name,"native_post","POST-"+result_id,1,payload)
        return self.open(key)

    def open_fit(self,material_key):
        from prototype_state import make_document
        key="fit:"+material_key
        if key not in self.session.documents:
            material=self.session.doc(material_key);payload=clone(self.session.doc("numerical")["draft"])
            payload["method"]="Inverse";payload["evaluator"]="Material response"
            payload["sources"]["material"]={"id":material["id"],"revision":material["revision"]}
            payload["variables"]=[{"owner":material_key,"field":"mu","unit":"MPa","start":material["saved"]["mu"],"lower":.6,"upper":1.4,"free":True}]
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
                payload=clone(self.session.doc("numerical")["saved"]);payload.update(method="DOE",budget=budget.value(),proposal=proposal)
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
        table.setRowCount(2);layout.addWidget(table)
        controls=QHBoxLayout();fail=QCheckBox("Review a Material save failure once")
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
                injected=key=="material" and fail.isChecked()
                if injected:fail.setChecked(False)
                self.session.save_adoption_owner(group_id,key,fail=injected)
                group["owners"][key].pop("error",None);failure_message.clear()
            except (ReviewError,OSError) as error:
                group["owners"][key]["error"]=str(error);failure_message.setText(str(error))
            redraw()
        for key in ("cad","material"):
            label="CAD" if key=="cad" else "Material"
            controls.addWidget(button("Apply "+label,lambda checked=False,k=key:apply(k)))
            controls.addWidget(button("Save "+label,lambda checked=False,k=key:save_owner(k)))
        layout.addLayout(controls);layout.addWidget(fail);layout.addWidget(failure_message)
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
    app.setStyle("Fusion");app.setStyleSheet(STYLE);app.setFont(QFont("Segoe UI",10))
    session=ReviewSession.open_session(args.session) if args.session else ReviewSession(args.workspace)
    if args.scenario=="material-repair":session.material_repair_scenario()
    hub=DesktopHub(session)
    entry=session.selected.get("tool",args.tool) if args.session else ("material" if args.scenario=="material-repair" else args.tool)
    hub.open(entry)
    return app.exec()


if __name__=="__main__":
    raise SystemExit(main())
