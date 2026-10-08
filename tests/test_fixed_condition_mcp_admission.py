"""MCP delegates numerical capability validation to the common calculation API."""
from types import SimpleNamespace
import pytest
from openscience import mcp_server

@pytest.mark.parametrize('route', ['fixed_cad_analysis', 'model_analysis', None])
def test_transport_has_no_fixed_cad_profile_refusal(monkeypatch, route):
    calls = []
    lab = SimpleNamespace(run_optimization=lambda identifier: calls.append(identifier) or {'route': route})
    monkeypatch.setattr(mcp_server, '_lab', lambda: lab)
    assert mcp_server.optimization_run.__wrapped__('C-source-only') == {'route': route}
    assert calls == ['C-source-only']
