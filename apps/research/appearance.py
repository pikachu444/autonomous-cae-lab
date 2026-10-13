"""Shared Qt Widgets appearance for the research processes, not native hosts.

Window owners may set ``appearanceRole`` to ``primary`` on a command, or
``title``, ``section`` and ``muted`` on labels before showing the window.
"""
from PySide6.QtGui import QColor, QFont, QPalette


_STYLE = """
QMainWindow, QDialog { background: #eef2f6; }
QMenuBar { background: #203449; color: #ffffff; padding: 1px 8px; }
QMenuBar::item { background: transparent; padding: 4px 10px; }
QMenuBar::item:selected { background: #37526e; }
QMenuBar::item:pressed { background: #45637f; }
QMenu { background: #ffffff; color: #1c2c3d; border: 1px solid #becbda; padding: 5px; }
QMenu::item { padding: 6px 24px 6px 12px; border-radius: 3px; }
QMenu::item:selected { background: #dceafb; color: #163e68; }
QMenu::item:disabled { color: #788596; }
QMenu::separator { height: 1px; background: #e0e7ef; margin: 5px 8px; }
QToolBar { background: #f8fafc; border: none; border-bottom: 1px solid #d2dce7;
           padding: 1px 8px; spacing: 4px; qproperty-iconSize: 18px 18px; }
QToolBar::separator { width: 1px; background: #d2dce7; margin: 4px 6px; }
QStatusBar { background: #e6edf4; color: #526174; border-top: 1px solid #d2dce7; }
QStatusBar::item { border: none; }
QLabel[appearanceRole="title"] { color: #152c45; font-size: 18px; font-weight: bold; }
QLabel[appearanceRole="section"] { color: #263e58; font-size: 14px; font-weight: bold; }
QLabel[appearanceRole="muted"] { color: #526174; }
QPushButton, QToolButton { background: #ffffff; color: #253b52;
    border: 1px solid #bccbd9; border-radius: 4px; padding: 5px 10px; }
QPushButton:hover, QToolButton:hover { background: #eaf2fc; border-color: #7e9fbe; }
QPushButton:pressed, QToolButton:pressed { background: #d3e4f7; border-color: #426c98; }
QPushButton:checked, QToolButton:checked { background: #dceafb; border-color: #7196bb; }
QPushButton:focus, QToolButton:focus { border: 2px solid #2768a9; padding: 4px 9px; }
QPushButton:flat { background: transparent; border-color: transparent; color: #205e9d; }
QPushButton:flat:hover { background: #eaf2fc; border-color: #b3cbe4; }
QPushButton:flat:pressed { background: #d3e4f7; border-color: #7196bb; }
QPushButton:flat:focus { border: 2px solid #2768a9; }
QPushButton[appearanceRole="primary"] { background: #245f9e; color: #ffffff;
    border-color: #245f9e; font-weight: bold; }
QPushButton[appearanceRole="primary"]:hover { background: #1d528c; border-color: #1d528c; }
QPushButton[appearanceRole="primary"]:pressed { background: #143f6d; border-color: #143f6d; }
QPushButton[appearanceRole="primary"]:focus { border: 2px solid #0c304f; }
QPushButton:disabled, QToolButton:disabled, QPushButton[appearanceRole="primary"]:disabled {
    background: #e9eef4; color: #778697; border-color: #d2dce7; }
QToolBar QPushButton, QToolBar QToolButton { padding: 3px 8px; }
QToolBar QPushButton:focus, QToolBar QToolButton:focus { padding: 2px 7px; }
QToolBar QToolButton { background: transparent; border-color: transparent; }
QToolBar QToolButton:hover { background: #eaf2fc; border-color: #b3cbe4; }
QToolBar QToolButton:pressed { background: #d3e4f7; border-color: #7196bb; }
QToolBar QToolButton:focus { border: 2px solid #2768a9; }
QToolBar QToolButton:disabled { background: transparent; border-color: transparent; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {
    background: #ffffff; color: #1c2c3d; border: 1px solid #b8c8d8;
    border-radius: 4px; padding: 4px 6px; selection-background-color: #c8def8;
    selection-color: #173c63; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {
    border: 2px solid #2768a9; padding: 3px 5px; }
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled, QComboBox:disabled {
    background: #e9eef4; color: #778697; border-color: #d2dce7; }
QTextBrowser { background: #ffffff; border: 1px solid #d1dce7; padding: 8px; }
QTextBrowser#turnBody { border: none; padding: 0px; }
QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #9bb2c9;
    selection-background-color: #dceafb; selection-color: #163e68; padding: 3px; }
QAbstractItemView { background: #ffffff; alternate-background-color: #f4f7fb;
    border: 1px solid #ccd8e4; border-radius: 4px; padding: 0px;
    color: #1c2c3d; gridline-color: #e2e8f0; selection-background-color: #dceafb;
    selection-color: #163e68; }
QAbstractItemView:focus { border-color: #2768a9; }
QAbstractItemView::item { padding: 3px 4px; border: none; }
QAbstractItemView::item:hover { background: #edf4fc; }
QAbstractItemView::item:selected { background: #dceafb; color: #163e68; }
QAbstractItemView::item:selected:!active { background: #e7edf4; color: #304b68; }
QHeaderView { background: #e8eff6; border: none; padding: 0px; }
QHeaderView::section { background: #e8eff6; color: #314a64; border: none;
    border-bottom: 1px solid #c4d2e0; border-right: 1px solid #d8e1eb;
    padding: 4px 7px; font-weight: bold; }
QTableCornerButton::section { background: #e8eff6; border: none; }
QTabWidget::pane { border: 1px solid #ccd8e4; background: #ffffff; }
QTabBar::tab { background: #e6edf4; color: #526174; padding: 6px 12px;
    border: 1px solid #ccd8e4; border-bottom: none; margin-right: 3px;
    border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background: #ffffff; color: #173c63; border-top: 2px solid #2768a9;
    padding-top: 5px; font-weight: bold; }
QTabBar::tab:hover:!selected { background: #dceafb; color: #163e68; }
QTabBar::tab:disabled { color: #778697; }
QGroupBox { border: 1px solid #ccd8e4; border-radius: 4px; margin-top: 12px;
    padding: 8px; padding-top: 12px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
    padding: 0px 5px; left: 8px; color: #314a64; font-weight: bold; }
QCheckBox, QRadioButton { spacing: 6px; color: #253b52; }
QCheckBox:disabled, QRadioButton:disabled { color: #778697; }
QSplitter::handle { background: #eef2f6; }
QSplitter::handle:horizontal { width: 6px; }
QSplitter::handle:vertical { height: 6px; }
QSplitter::handle:hover { background: #c4d9ee; }
QScrollBar:vertical { background: #f2f5f9; width: 12px; margin: 0px; }
QScrollBar:horizontal { background: #f2f5f9; height: 12px; margin: 0px; }
QScrollBar::handle:vertical { background: #a6b8c9; border: 3px solid #f2f5f9;
    border-radius: 5px; min-height: 28px; }
QScrollBar::handle:horizontal { background: #a6b8c9; border: 3px solid #f2f5f9;
    border-radius: 5px; min-width: 28px; }
QScrollBar::handle:hover { background: #6e8dad; }
QScrollBar::handle:pressed { background: #426c98; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip { background: #203449; color: #ffffff; border: 1px solid #45637f;
    padding: 6px 8px; }
"""


def apply_appearance(application):
    """Apply once to a QApplication in a research GUI process.

    Set semantic properties before first polish; changes on an already shown
    widget require its owner's normal unpolish/polish cycle.
    """
    if application.property("caeAppearanceApplied"):
        return
    application.setStyle("Fusion")
    font = QFont()
    font.setFamilies(["Segoe UI", "Malgun Gothic", "Noto Sans CJK KR", "sans-serif"])
    font.setPointSizeF(10)
    application.setFont(font)
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#eef2f6"),
        (QPalette.ColorRole.WindowText, "#1c2c3d"),
        (QPalette.ColorRole.Base, "#ffffff"),
        (QPalette.ColorRole.AlternateBase, "#f4f7fb"),
        (QPalette.ColorRole.Text, "#1c2c3d"),
        (QPalette.ColorRole.Button, "#ffffff"),
        (QPalette.ColorRole.ButtonText, "#253b52"),
        (QPalette.ColorRole.Highlight, "#dceafb"),
        (QPalette.ColorRole.HighlightedText, "#163e68"),
        (QPalette.ColorRole.PlaceholderText, "#526174"),
        (QPalette.ColorRole.Link, "#205e9d"),
        (QPalette.ColorRole.ToolTipBase, "#203449"),
        (QPalette.ColorRole.ToolTipText, "#ffffff"),
    ):
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText,
                 QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#778697"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor("#e9eef4"))
    application.setPalette(palette)
    application.setStyleSheet(_STYLE)
    application.setProperty("caeAppearanceApplied", True)
