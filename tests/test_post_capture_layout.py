"""Action rows remain separate when the measurement editor needs scrolling."""
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QPoint, QRect, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from test_research_post_ui import app, window, edit, wait


@pytest.mark.parametrize('size',[(1060,700),(1200,760)])
def test_capture_editor_does_not_cover_the_native_view_controls(app,window,size):
    window._source_ref='Sfirst'
    window.new_object('measurement')
    edit(window,('array',),'stress')
    window.measurement_kind.setCurrentIndex(window.measurement_kind.findData('time'))
    window.capture_selection()
    wait(app,lambda:not window._busy and window._pending is None)
    window.resize(*size);window.show()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    app.processEvents();QTest.qWait(50)
    def bounds(widget):return QRect(widget.mapTo(window,QPoint(0,0)),widget.size())
    buttons=(window.edit_button,window.preview_button,window.apply_button,window.reset_button)
    views=(window.view_selector,window.show_applied_button,window.contact_button)
    assert (window.width(),window.height())==size
    assert window.view_selector.isVisible()
    for button in buttons:
        assert button.isVisible()
        assert bounds(window.editor_area).contains(bounds(button))
        assert all(not bounds(button).intersects(bounds(view)) for view in views if view.isVisible())
    assert window.tabs.currentWidget().verticalScrollBar().maximum()>0
