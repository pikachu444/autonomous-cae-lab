"""Source admission boundary only; no provider, native solver or MCP transport."""
from types import SimpleNamespace

import pytest

from caelab import optimization
from caelab.contracts import CapabilityUnavailable
from openscience import mcp_server


@pytest.mark.parametrize('route', ['fixed_cad_analysis', 'model_analysis', None])
def test_existing_ai_executor_cannot_inherit_new_native_search_scope(monkeypatch, route):
    calls = []
    lab = SimpleNamespace(run_optimization=lambda identifier: calls.append(identifier) or {'TEST_ONLY': identifier})
    monkeypatch.setattr(mcp_server, '_lab', lambda: lab)
    monkeypatch.setattr(optimization, '_plan', lambda observed, identifier: ({'route': route},))
    run = mcp_server.optimization_run.__wrapped__
    if route == 'fixed_cad_analysis':
        with pytest.raises(CapabilityUnavailable, match='does not admit fixed-CAD'):
            run('C-source-only')
        assert calls == []
    else:
        assert run('C-source-only') == {'TEST_ONLY': 'C-source-only'}
        assert calls == ['C-source-only']
