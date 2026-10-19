"""Explicit historical installation for the immutable C1 input-gate fixture."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json

import pytest


@pytest.fixture
def historical_installation(monkeypatch):
    from caelab import material_fe_transfer as transfer
    from caelab.adapters import law_native_runtime as runtime

    raw = (Path(__file__).parent / 'fixtures/c1-frozen-simulation.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '7e92939e6fd75d64a81849483171846dfc0ca6f4f841f88a5fb7fcf5bb710a91'
    saved = json.loads(raw)['simulation_draft']['settings']['source_receipt']['review']['source']['law_source']
    identity = {'interface': saved['interface'], 'files': {
        name: {'sha256': row['sha256']} for name, row in saved['files'].items()}}
    # Fix trust before adversarial tests mutate their independent input copies.
    monkeypatch.setattr(transfer, 'source_identity', lambda: deepcopy(identity))
    monkeypatch.setattr(runtime, 'SOURCE_RELATIVES', tuple(identity['files']))
    return deepcopy(identity)
