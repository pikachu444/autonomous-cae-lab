"""Action rows remain separate when the measurement editor needs scrolling."""
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QPoint, QRect, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from test_research_post_ui import app, window, edit, wait


@pytest.mark.parametrize('size',[(1060,700),(1200,760)])
def test_capture_editor_does_not_cover_the_native_view_controls(app,window,size):
    window.client.document['state']['views']=[
        {'view_id':'Vrender','type':'RenderView'},{'view_id':'Vchart','type':'XYChartView'}]
    window.refresh_document();wait(app,lambda:not window._busy and window.view_selector.count()==3)
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
    buttons=tuple(window.selected_toolbar.widgetForAction(action)
                  for action in (window.preview_action,window.apply_action,window.keep_action))
    assert (window.width(),window.height())==size
    for button in buttons:
        assert button.isVisible()
        assert bounds(window.selected_toolbar).contains(bounds(button))
        assert not bounds(button).intersects(bounds(window.editor_area))
    assert window.tabs.currentWidget().verticalScrollBar().maximum()>0
    window.work_tabs.setCurrentIndex(1);app.processEvents()
    assert window.view_selector.isVisible()
    assert bounds(window.work_tabs).contains(bounds(window.view_selector))
    assert all(not bounds(button).intersects(bounds(window.view_selector)) for button in buttons)
