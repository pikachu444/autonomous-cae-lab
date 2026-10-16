"""Actual Qt settings layout; native command transport remains controlled."""
from copy import deepcopy
import time
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea
from apps.research.post_window import PostWindow, defaults
from test_research_post_ui import NativeClient


def settle(app, window):
    deadline = time.monotonic()+5
    quiet = 0
    while quiet < 3:
        assert time.monotonic()<deadline
        app.processEvents(); time.sleep(.005)
        quiet = quiet+1 if not (window._busy or window._pending or window._callback_calls) else 0
    flush(app)


def flush(app):
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


@pytest.fixture
def compact():
    app = QApplication.instance() or QApplication([])
    client = NativeClient()
    window = PostWindow(client,document_id='Dpost',session_id='Snative',auto_open=False,poll_interval=0)
    try:
        window.refresh_document(initial=True); settle(app, window)
        window.show(); flush(app)
        yield app, window
    finally:
        window._allow_close=True; window.close(); window.deleteLater(); flush(app)


@pytest.mark.parametrize('width', [380,440,460])
def test_selected_measurement_pages_fit_without_whole_form_scrolling(compact, width):
    app, w = compact
    from shiboken6 import isValid
    previous = w.comparison_editor
    w.resize(width,900)
    for kind in ('point','path','time','gauge','gauge_time','surface_average','surface_time'):
        w.local_dirty=False
        assert w.new_measurement_type(kind)
        flush(app)
        assert w.width()==width and w.editor_area.isVisible()
        assert w.settings_pages.count()==4
        for page in range(4):
            w.settings_pages.setCurrentIndex(page); flush(app)
            scroll = w.tabs.currentWidget()
            assert isinstance(scroll, QScrollArea)
            assert scroll.horizontalScrollBar().maximum()==0
            assert scroll.verticalScrollBar().maximum()==0
            assert w.settings_pages.currentWidget().isVisible()
        assert w.edited_draft()['measurement']==kind
    assert not isValid(previous)
    assert not client_calls(w)


def client_calls(w):
    return w.client.calls


def test_source_fields_and_commands_fit_at_narrow_width(compact):
    app,w=compact
    w.resize(380,900)
    item=w.tree.topLevelItem(0).child(0)
    w.tree.setCurrentItem(item); flush(app)
    assert w.width()==380 and w.source_settings.isVisible()
    assert w.array_controls.isVisible() and not w.editor_area.isVisible()
    for button in (w.select_array_button,w.measure_array_button):
        assert button.isVisible() and button.width()>0


def test_missing_declarations_page_and_rebuild_preserve_user_size_and_recipe(compact):
    app, w = compact
    assert w.new_measurement_type('gauge_time')
    assert '미정' in w.settings_pages.tabText(2)
    assert w.edited_draft().get('units') in (None,'')
    w.settings_pages.setCurrentIndex(2)
    w.compact_split.setSizes([180,600]); sizes=w.compact_split.sizes()
    recipe=deepcopy(w.edited_draft())
    w._draft=recipe; w._populate_editor(); flush(app)
    assert w.edited_draft()==recipe and w.settings_pages.currentIndex()==2
    assert w.compact_split.sizes()==sizes
    assert w.capture_button.text()=='선택으로 새 측정 추가'
    assert '단위 미지정' in w._compact_field_labels[('point1',)].text()
    assert 'F6' in w.preview_action.shortcut().toString()
    assert 'Ctrl+Return' in [key.toString() for key in w.apply_action.shortcuts()]


def test_capture_keeps_dirty_existing_object_and_keyboard_focus_is_available(compact):
    app, w = compact
    assert w.new_measurement_type('gauge')
    w._object_ref='Aexisting'; w.local_dirty=True
    before=deepcopy(w.edited_draft())
    assert not w.capture_new_measurement()
    assert w.edited_draft()==before and not w.client.calls
    assert '초안' in w.compact_notice.text()
    w.settings_pages.setCurrentIndex(0)
    field=w.fields[('source_ref',)][0]; field.setFocus(); flush(app)
    assert QApplication.focusWidget() is field
    QTest.keyClick(field,Qt.Key.Key_Tab); flush(app)
    assert QApplication.focusWidget() is not field


@pytest.mark.parametrize('kind', ['surface_average','surface_time','gauge_time'])
def test_compact_results_keep_invalid_rows_and_exact_row_revision(compact,kind):
    app,w=compact
    w._kind='measurement'; w._draft={**defaults('measurement'),'measurement':kind,'units':'mm','time_units':'s'}
    w._populate_editor(); w.local_dirty=False
    recipe=deepcopy(w.edited_draft())
    revision={'id':'Vretained','recipe':recipe,'summary':{'measurement':kind,'units':'mm'}}
    obj={'id':'Aretained','kind':'measurement','title':'선택한 측정','draft':recipe,'history':[revision],
         'position':0,'preview':deepcopy(revision)}
    for document in (w.document,w.client.document): document['state']['analysis']['objects']=[deepcopy(obj)]
    w._object_ref=obj['id']; w._tree_selection=('object',obj['id'])
    key='SurfaceAreaAverage' if kind.startswith('surface') else 'GaugeRelativeDisplacement'
    payload={'revision':revision['id'],'preview':False,'summary':revision['summary'],
        'rows':[{'block':[],'row':0,'values':{'Time':0.,key:2.,'vtkValidMask':1}},
                {'block':[],'row':1,'values':{'Time':.07,key:None,'vtkValidMask':0}}]}
    w._show_samples(payload); flush(app)
    assert w.work_tabs.currentIndex()==1 and w.output_tabs.currentWidget() is w._compact_summary
    assert w.compact_table.rowCount()==2 and w.compact_table.item(1,1).text()=='값 없음'
    assert w._samples==payload and w._analysis_state(obj)=='적용됨'
    w.compact_table.selectRow(1); settle(app,w)
    args=w.client.calls[-1][2]
    assert args['row_index']==1 and args['expected_revision']=='Vretained' and 'point_index' not in args
    assert w._samples['rows'][1]['values']['vtkValidMask']==0
    w.document['state']['analysis']['objects'][0]['history'][0]['id']='Vnewer'
    count=len(w.client.calls)
    w.compact_table.clearSelection(); w.compact_table.selectRow(0); flush(app)
    assert len(w.client.calls)==count


def test_preview_apply_save_use_original_owner_commands(compact):
    app,w=compact
    assert w.new_measurement_type('surface_average')
    QTest.keyClick(w,Qt.Key.Key_F6); settle(app,w)
    assert [call[1] for call in w.client.calls]==['post.measurement_edit','post.mapping_validate','post.sample']
    QTest.keyClick(w,Qt.Key.Key_Return,Qt.KeyboardModifier.ControlModifier); settle(app,w)
    assert [call[1] for call in w.client.calls][-2:]==['post.apply','post.sample']
    w.save_document(); settle(app,w)
    assert w.client.calls[-1][1]=='document.save'


@pytest.mark.parametrize('kind,clock,expected', [
    ('surface_time',None,'시각 0.07 s'), ('gauge_time',None,'시각 0.07 s'),
    ('surface_average',None,'시각 정보 없음'), ('surface_average',.5,'시각 0.5 s'),
    ('gauge',.5,'시각 0.5 s')])
def test_single_row_uses_actual_history_time_and_preserves_static_clock(compact,kind,clock,expected):
    app,w=compact
    recipe={'measurement':kind,'units':'mm','time_units':'s','time_origin':'analysis_start'}
    if kind not in ('surface_time','gauge_time'): recipe['time']=clock
    else: recipe.update(time_range=[.07,.07] if kind=='surface_time' else [0.,.2],reference_time=0.)
    key='SurfaceAreaAverage' if kind.startswith('surface') else 'GaugeRelativeDisplacement'
    payload={'summary':{'measurement':kind,'units':'mm'},'rows':[
        {'block':[],'row':7,'values':{'Time':.07,key:2.,'vtkValidMask':1}}]}
    before=deepcopy((recipe,payload))
    w._compact_samples(payload,recipe)
    assert expected in w.compact_value.text()
    assert (recipe,payload)==before
    if kind in ('surface_time','gauge_time'):
        assert w.compact_table.item(0,0).text()=='0.07'
    assert not w.client.calls


@pytest.mark.parametrize('reason',['dirty_selection','missing_declaration'])
def test_compact_notice_updates_immediately_on_early_return_without_editing_draft(compact,reason):
    from PySide6.QtWidgets import QTreeWidgetItem
    app,w=compact
    w.new_measurement_type('gauge')
    before=deepcopy(w.edited_draft())
    w.message.setText('earlier notice')
    assert w.compact_notice.text()=='earlier notice'
    if reason=='dirty_selection':
        item=QTreeWidgetItem(['다른 측정',''])
        item.setData(0,Qt.ItemDataRole.UserRole,('object','Aother'))
        w.tree.blockSignals(True);w.tree.addTopLevelItem(item);w.tree.setCurrentItem(item);w.tree.blockSignals(False)
        w._tree_selected()
        assert '초안' in w.compact_notice.text()
    else:
        w.use_declarations()
        assert '물리 선언' in w.compact_notice.text()
    assert w.compact_notice.text()==w.message.text()
    assert w.compact_notice.toolTip()==w.message.text()
    assert w.edited_draft()==before and w.local_dirty and not w.client.calls
