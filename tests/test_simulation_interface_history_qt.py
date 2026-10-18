"""The history view reads only the currently selected immutable result."""
from copy import deepcopy

from test_simulation_impact_readback_qt import app,viewer


def test_history_view_blocks_a_result_from_another_selection(viewer):
    window,_=viewer
    audit={'elements':[{'element_id':2,'samples':[]}],'qualification':'UNKNOWN'}
    window._result['diagnostics']={'b_observations':{'interface_history':audit}}
    window._update_actions()
    assert window.interface_history_action.isEnabled()
    window._selected_job='Jother';window._update_actions()
    assert not window.interface_history_action.isEnabled()
    assert window.show_interface_history() is False
    window._selected_job='Jsource';window._busy=True
    assert window.show_interface_history() is False
    window._busy=False


def test_history_view_gets_a_snapshot_and_cannot_mutate_the_owner(viewer,monkeypatch):
    import apps.research.impact_interface_history_view as view
    window,client=viewer
    audit={'elements':[{'element_id':2,'samples':[]}],'qualification':'UNKNOWN'}
    window._result['diagnostics']={'b_observations':{'interface_history':audit}}
    before=deepcopy((window.document,window._result,client.calls,client.reads))
    received=[]
    class ReadView:
        def __init__(self,value,parent):
            received.append(deepcopy(value));value['qualification']='changed in view'
        def exec(self):return 0
    monkeypatch.setattr(view,'InterfaceHistoryView',ReadView)
    assert window.show_interface_history() is True
    assert received==[audit]
    assert (window.document,window._result,client.calls,client.reads)==before
