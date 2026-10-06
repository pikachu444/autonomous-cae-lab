"""Explicit TEST ONLY Git metadata for bounded fake-native campaign unit tests.

Every source byte is still re-read. Actual Git/provenance, native solver, HTTP
acceptance and MCP evidence are checked separately without this pytest plugin.
"""
from pathlib import Path

import pytest


FILES = {'test_observation_target.py', 'test_campaign_report.py',
         'test_campaign_research_http.py', 'test_model_optimization.py',
         'test_optimization.py', 'test_fixed_cad_optimization.py',
         'test_campaign_conditions.py'}


@pytest.fixture(autouse=True)
def synthetic_metadata_boundary(request, monkeypatch):
    if Path(str(request.node.path)).name not in FILES:
        return
    from caelab import analysis_conditions, campaign_report, declared_model, engine, model_doe, optimization, storage
    def identity(root):
        return {'core_commit': 'TEST_ONLY_NO_GIT_METADATA', 'core_dirty': True,
                'core_source_sha256': storage.core_source_hash(root)}
    for module in (analysis_conditions, campaign_report, declared_model, engine, model_doe, optimization):
        monkeypatch.setattr(module, 'source_identity', identity)
