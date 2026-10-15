"""A native point capture must not replace the user's measurement intent."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
pytest.importorskip('PySide6')
from apps.research.post_window import PostWindow
from test_research_post_ui import app, window


def capture_view(draft):
    callbacks=[]
    view=SimpleNamespace(edited_draft=lambda:deepcopy(draft),
        message=SimpleNamespace(setText=lambda text:None),
        queue_command=lambda operation,arguments,accepted:callbacks.append(accepted) or True,
        _show_document=lambda *args,**kwargs:None,_populate_editor=lambda:None,
        document={},_edit_serial=0)
    return view,callbacks


def native_capture():
    return {'id':'Acaptured','draft':{'source_ref':'Soriginal','array':'U','measurement':'point',
        'association':'POINTS','point_indices':[2,8], 'time':.25,'time_units':'s',
        'time_origin':'PHYSICAL_TIME','units':'mm','frame':'global'}}


def test_capture_keeps_time_curve_intent_and_explicit_declarations():
    draft={'source_ref':'Soriginal','array':'U','association':'POINTS','measurement':'time',
           'point_indices':[4],'time_units':'ms','time_origin':'explicit clock',
           'units':'mm','frame':'explicit frame'}
    view,callbacks=capture_view(draft)
    assert PostWindow.capture_selection(view)
    callbacks[0](native_capture())
    assert view._draft['measurement']=='time'
    assert view._draft['point_indices']==[2,8]
    assert view._draft['time_units']=='ms' and view._draft['frame']=='explicit frame'
    assert 'time' not in view._draft
    assert view.local_dirty and view._object_ref=='Acaptured'


def test_capture_keeps_explicit_point_time_without_losing_native_clock_declarations():
    draft={'source_ref':'Soriginal','array':'U','association':'POINTS','measurement':'point',
           'point_indices':[],'time':0.,'time_units':None,'time_origin':None}
    view,callbacks=capture_view(draft)
    assert PostWindow.capture_selection(view)
    callbacks[0](native_capture())
    assert view._draft['time']==0.
    assert view._draft['time_units']=='s' and view._draft['time_origin']=='PHYSICAL_TIME'
    assert view._draft['point_indices']==[2,8] and view.local_dirty


@pytest.mark.parametrize('draft',[{'measurement':'path','association':'POINTS'},
                                  {'measurement':'point','association':'CELLS'}])
def test_capture_does_not_replace_path_or_cell_measurement(draft):
    view,callbacks=capture_view({'source_ref':'Soriginal','array':'U',**draft})
    assert PostWindow.capture_selection(view) is False
    assert callbacks==[]


def test_qt_capture_keeps_time_draft_through_existing_store(app, window):
    from test_research_post_ui import edit, wait
    window._source_ref='Sfirst'
    assert window.new_object('measurement')
    edit(window,('array',),'stress')
    window.measurement_kind.setCurrentIndex(window.measurement_kind.findData('time'))
    edit(window,('time_units',),'s')
    edit(window,('time_origin',),'PHYSICAL_TIME')
    edit(window,('frame',),'lab')
    window.capture_selection()
    wait(app,lambda:not window._busy and window._pending is None)
    assert window.edited_draft()['measurement']=='time'
    assert window.edited_draft()['point_indices']==[2,8]
    assert window.edited_draft()['time_units']=='s' and window.local_dirty
    assert window._object_ref=='Acaptured'
    assert '원본 점 선택 가져오기 완료' in window.message.text() and '아직 적용' in window.message.text()
    assert [call[1] for call in window.client.calls]==['post.measurement_capture']
    window.store_draft()
    wait(app,lambda:not window._busy and window._pending is None)
    assert window.edited_draft()['measurement']=='time' and not window.local_dirty
    assert window.client.calls[-1][1]=='post.measurement_edit'
    assert window.client.calls[-1][2]['draft']['point_indices']==[2,8]
    window.measurement_kind.setCurrentIndex(window.measurement_kind.findData('path'))
    assert not window.capture_button.isEnabled()
    assert window.capture_selection() is False
    assert len(window.client.calls)==2
