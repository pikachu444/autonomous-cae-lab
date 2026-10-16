"""Routing only: explicit panel/action doubles; no native writer or solver."""
from types import SimpleNamespace
import pytest
from apps.desktop_pre.composite_controls import route


def test_composite_route_never_falls_through_and_open_only_never_calculates():
    events=[];panel=SimpleNamespace(open_analysis=lambda aid:events.append(('open',aid)),
        prepare_input=lambda:events.append('prepare'),run_prepared=lambda:events.append('run'))
    owner=SimpleNamespace(read_metadata=lambda:{'composite_shells':{'A':{}}})
    connection=SimpleNamespace(show_panel=lambda kind,owner:panel)
    assert route(connection,owner,'other') is False and events==[]
    assert route(connection,owner,'A',open_only=True) is True and events==[('open','A')]
    assert route(connection,owner,'A',export_only=True) is True and events[-1]=='prepare'
    assert route(connection,owner,'A') is True and events[-1]=='run'
    panel.run_prepared=lambda:(_ for _ in ()).throw(ValueError('invalid raw draft'))
    with pytest.raises(ValueError,match='invalid raw draft'):route(connection,owner,'A')
