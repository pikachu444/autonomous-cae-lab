"""Selected native point fields seed only an editable measurement draft."""
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from test_research_post_ui import app, window


def choose_field(window, *, association='POINTS', components=1, declared=True):
    source=window.document['state']['analysis']['sources'][0]
    source['metadata']['arrays'][0].update(association=association, components=components)
    source['native_metadata']['arrays'][0].update(association=association, components=components)
    if not declared:
        source['native_metadata']=None
    window._source_ref=source['source_ref']
    window._tree_selection=('source', source['source_ref'])
    window._show_arrays()
    window.array_table.selectRow(0)
    window._update_actions()


def test_selected_field_prepares_declared_measurement_without_native_execution(window):
    choose_field(window)
    before=deepcopy(window.document)
    assert window.measure_array_button.isEnabled()
    assert window.measure_selected_array()
    draft=window.edited_draft()
    assert (draft['source_ref'],draft['array'],draft['association'])==('Sfirst','stress','POINTS')
    assert draft['units']=='MPa' and draft['measure']=='Cauchy' and draft['frame']=='lab'
    assert draft['coordinate_units']=='mm'
    assert draft['time'] is None and draft['point_indices']==[]
    assert window.local_dirty and window._object_ref is None
    assert window.client.calls==[] and window.document==before
    assert window.measurement_kind.currentData()=='point'
    assert window.measurement_kind.currentText()=='선택한 원본 점'


def test_vector_display_component_does_not_become_a_scalar_measurement(window):
    choose_field(window,components=3)
    window.array_component.setCurrentIndex(window.array_component.findData(1))
    assert window.measure_selected_array()
    draft=window.edited_draft()
    assert draft['array']=='stress' and 'component' not in draft
    assert '전체 성분' in window.message.text()
    assert window.client.calls==[]


def test_undeclared_units_remain_unknown_in_selected_field_draft(window):
    choose_field(window,declared=False)
    assert window.measure_selected_array()
    draft=window.edited_draft()
    assert all(not draft.get(key) for key in ('units','quantity','measure','frame','coordinate_units'))
    assert window.client.calls==[]


def test_cell_field_is_not_silently_converted_into_point_measurement(window):
    choose_field(window,association='CELLS')
    before=deepcopy(window.edited_draft())
    assert not window.measure_array_button.isEnabled()
    assert window.measure_selected_array() is False
    assert window.edited_draft()==before and not window.local_dirty
    assert window.client.calls==[]


@pytest.mark.parametrize('blocked',['busy','draft'])
def test_field_measurement_preserves_pending_or_edited_work(window,blocked):
    choose_field(window)
    if blocked=='busy':window._busy=True
    else:window.local_dirty=True
    before=deepcopy(window.edited_draft())
    try:
        assert window.measure_selected_array() is False
        assert window.edited_draft()==before and window.client.calls==[]
    finally:
        window._busy=False


def test_old_source_field_cannot_seed_another_source_measurement(window):
    choose_field(window)
    window._source_ref='Ssecond'
    window._tree_selection=('source','Ssecond')
    before=deepcopy(window.edited_draft())
    assert window.measure_selected_array() is False
    assert window.edited_draft()==before and window.client.calls==[]
