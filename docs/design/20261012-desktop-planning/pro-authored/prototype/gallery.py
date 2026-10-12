"""Qt Widgets screen review gallery. All interactions are planning simulations."""
import argparse
import json
from pathlib import Path
import sys
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QLabel, QPushButton, QScrollArea, QComboBox, QSplitter, QMessageBox,
)


class Gallery(QMainWindow):
    def __init__(self, screens_path, store_path):
        super().__init__()
        self.screens_path = Path(screens_path)
        self.artifact_root = self.screens_path.parent.parent
        self.store_path = Path(store_path)
        spec = json.loads(self.screens_path.read_text(encoding="utf-8"))
        if spec.get("schema_version") != "1.0":
            raise ValueError("Expected screens schema_version 1.0")
        self.spec = spec
        self.screens = {s["id"]: s for s in spec["screens"]}
        self.history, self.shortcuts = [], []
        self.current = None
        self.material_window = None
        self.scenario_step = -1
        self.setWindowTitle("SIMULATED UI • Desktop design review gallery")
        self.resize(1560, 1050)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        banner = QLabel("SIMULATED UI • Clickable screen planning only. No solver, fit, provider or production save service.")
        banner.setStyleSheet("padding:10px; background:#fff0cc; color:#713e00; font-weight:bold")
        layout.addWidget(banner)
        toolbar = QHBoxLayout()
        layout.addLayout(toolbar)
        self.back_button = QPushButton("Back (Alt+Left)")
        self.back_button.clicked.connect(self.back)
        toolbar.addWidget(self.back_button)
        reset = QPushButton("Reset gallery")
        reset.clicked.connect(self.reset)
        toolbar.addWidget(reset)
        demo = QPushButton("Open Material interaction demo")
        demo.clicked.connect(self.open_material)
        toolbar.addWidget(demo)
        self.scenarios = QComboBox()
        self.scenarios.addItem("Choose a scripted review scenario", None)
        for scenario in spec.get("scenarios", []):
            self.scenarios.addItem(scenario["title"], scenario)
        self.scenarios.currentIndexChanged.connect(self.start_scenario)
        toolbar.addWidget(self.scenarios, 1)
        next_step = QPushButton("Next scenario step")
        next_step.clicked.connect(self.next_scenario_step)
        toolbar.addWidget(next_step)
        self.info = QLabel()
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        split = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(split, 1)
        self.list = QListWidget()
        self.list.setMinimumWidth(260)
        for screen in spec["screens"]:
            self.list.addItem(f"{screen['id']} • {screen['title']} [{screen.get('state', '')}]")
        self.list.currentRowChanged.connect(self.list_selected)
        split.addWidget(self.list)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        split.addWidget(self.scroll)
        split.setStretchFactor(1, 1)
        self.outcome = QLabel("Review navigation ready.")
        self.outcome.setWordWrap(True)
        self.outcome.setStyleSheet("padding:8px; background:#eef5fa")
        layout.addWidget(self.outcome)
        shortcut = QShortcut(QKeySequence("Alt+Left"), self)
        shortcut.activated.connect(self.back)
        self.reset()

    def list_selected(self, row):
        if row >= 0:
            self.navigate(self.spec["screens"][row]["id"])

    def navigate(self, screen_id, record_history=True):
        if screen_id not in self.screens:
            self.outcome.setText(f"SIMULATED action has no screen target: {screen_id}. No external operation executed.")
            return
        if self.current == screen_id:
            return
        if record_history and self.current:
            self.history.append(self.current)
        self.current = screen_id
        screen = self.screens[screen_id]
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts = []
        width, height = self.spec.get("canvas", {}).get("width", 1440), self.spec.get("canvas", {}).get("height", 900)
        surface = QWidget()
        surface.setFixedSize(width, height)
        preview = QLabel(surface)
        preview.setGeometry(0, 0, width, height)
        pixmap = QPixmap(str(self.screens_path.parent / screen["preview"]))
        if pixmap.isNull():
            preview.setText(f"Preview missing: {screen['preview']}\nThis gallery never substitutes a production screen.")
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            preview.setPixmap(pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        for hotspot in screen.get("hotspots", []):
            button = QPushButton(surface)
            button.setGeometry(round(hotspot["x"]), round(hotspot["y"]), round(hotspot["w"]), round(hotspot["h"]))
            button.setToolTip(f"{hotspot['label']}\nOwner: {hotspot.get('owner', screen.get('owner', 'unspecified'))}\n{hotspot.get('effect', '')}\nShortcut: {hotspot.get('shortcut', '')}")
            button.setAccessibleName(hotspot["label"])
            button.setStyleSheet("QPushButton {background:rgba(31,112,167,12); border:1px solid rgba(31,112,167,90); border-radius:3px;} QPushButton:hover,QPushButton:focus {background:rgba(31,112,167,45); border:2px solid #1f70a7;}")
            button.clicked.connect(lambda checked=False, h=hotspot: self.activate(h))
            if hotspot.get("shortcut"):
                shortcut = QShortcut(QKeySequence(hotspot["shortcut"]), self)
                shortcut.activated.connect(lambda h=hotspot: self.activate(h))
                self.shortcuts.append(shortcut)
        self.scroll.setWidget(surface)
        self.info.setText(f"{screen['id']} • {screen['title']} | {screen.get('tool', '')} | state: {screen.get('state', '')}\nOwner: {screen.get('owner', '')} | Next: {screen.get('next_action', '')}\nFunctions: {', '.join(screen.get('function_ids', []))}")
        self.list.blockSignals(True)
        self.list.setCurrentRow(next(i for i, s in enumerate(self.spec["screens"]) if s["id"] == screen_id))
        self.list.blockSignals(False)
        self.back_button.setEnabled(bool(self.history))

    def activate(self, hotspot):
        self.outcome.setText(f"SIMULATED {hotspot['label']}: {hotspot.get('effect', hotspot.get('action', 'navigation'))}. Owner: {hotspot.get('owner', '')}.")
        if hotspot.get("target"):
            self.navigate(hotspot["target"])

    def back(self):
        if self.history:
            self.navigate(self.history.pop(), record_history=False)

    def reset(self):
        self.history.clear()
        self.current = None
        self.scenario_step = -1
        self.scenarios.blockSignals(True)
        self.scenarios.setCurrentIndex(0)
        self.scenarios.blockSignals(False)
        if self.spec["screens"]:
            self.navigate(self.spec["screens"][0]["id"], record_history=False)
        self.outcome.setText("Gallery reset. Material draft and planning save file are independent and retained.")

    def start_scenario(self):
        scenario = self.scenarios.currentData()
        self.scenario_step = -1
        if scenario:
            self.navigate(scenario["start"])
            self.outcome.setText(f"SIMULATED scenario: {scenario['title']}. Select Next scenario step to review expected transitions.")

    def next_scenario_step(self):
        scenario = self.scenarios.currentData()
        if not scenario:
            self.outcome.setText("Choose a scenario first.")
            return
        self.scenario_step += 1
        steps = scenario.get("steps", [])
        if self.scenario_step >= len(steps):
            self.outcome.setText("SIMULATED scripted scenario complete. This is navigation evidence only, not a production workflow test.")
            return
        step = steps[self.scenario_step]
        self.navigate(step.get("target") or step["screen"])
        self.outcome.setText(f"SIMULATED step {self.scenario_step + 1}/{len(steps)}: {step['screen']} → {step.get('action', '')} → {step.get('target', '')}\nExpected: {step.get('expected', '')}")

    def open_material(self):
        try:
            if self.material_window is None:
                from material_demo import MaterialDemo
                self.material_window = MaterialDemo(self.artifact_root, self.store_path)
            self.material_window.show()
            self.material_window.raise_()
            self.material_window.activateWindow()
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, "Material planning input unavailable", str(exc))

    def closeEvent(self, event):
        if self.material_window is not None and not self.material_window.close():
            event.ignore()
        else:
            event.accept()


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="SIMULATED UI planning prototype; no production computations")
    parser.add_argument("--screens", type=Path, default=root / "screens" / "screens.json")
    parser.add_argument("--state", type=Path, default=Path.home() / "CAE_Planning_Demo" / "material-neo-hooke-planning.json")
    parser.add_argument("--material-only", action="store_true")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    if args.material_only:
        from material_demo import MaterialDemo
        window = MaterialDemo(args.screens.parent.parent, args.state)
    else:
        window = Gallery(args.screens, args.state)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
