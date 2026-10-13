"""Data settings stay contextual without changing the imported document."""
from copy import deepcopy
import os

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('matplotlib')

from PySide6.QtTest import QTest
from apps.research.data_window import DataWindow
from test_research_data_numerical_ui import app, data_document


def test_settings_collapse_keeps_channel_edits_and_independent_row_selections(app):
    document = data_document()
    document['runs'] = []
    window = DataWindow(None, auto_open=False, poll_interval=0)
    try:
        window._opened(document)
        window.resize(1100, 780)
        window.show()
        app.processEvents()
        assert window.editor.isVisible()
        assert window.width() == 1100 and window.height() == 780
        assert window.canvas.height() >= 140
        window.editor.setCurrentIndex(2)
        field = window.row_fields['exclude_rows']
        field.setFocus()
        QTest.keyClicks(field, '2')
        edited = deepcopy(window.edited_draft())
        selection = edited['mapping']['columns']['response']['row_selection']
        assert selection['exclude_rows'] == [2]
        assert not selection.get('quality_rows') and not selection.get('display_hidden_rows')
        window.settings_button.click()
        window.resize(1440, 900)
        app.processEvents()
        assert window.editor.isHidden() and window.edited_draft() == edited
        assert window.identity.text() == '설정 적용 필요'
        window.settings_button.click()
        assert window.editor.currentIndex() == 2 and field.text() == '2'
        assert window.document['draft'] == document['draft']
        # Opening a different document with an existing import begins in reading mode.
        window._opened(data_document())
        app.processEvents()
        assert window.editor.isHidden()
        assert window.sheets.currentWidget() is window.values
        assert not window.local_dirty
    finally:
        window._allow_close = True
        window.close()
