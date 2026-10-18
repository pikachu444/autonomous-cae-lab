"""Retained observations open the existing Material editor without submitting work."""
import json

import pytest

from apps.research import desktop


SOURCE = {'document_id': 'Tdata', 'job_id': 'Jimport', 'response': '응력 xx',
          'input_revision': 'Iinput', 'input_sha256': 'a' * 64}


def test_exact_observation_is_one_native_argument_without_a_result_payload(monkeypatch):
    calls = []
    monkeypatch.setattr(desktop, '_spawn', lambda client, args: calls.append(args) or {'status': 'LAUNCH_REQUESTED'})
    assert desktop.launch_material_observation(object(), SOURCE, 'Mmaterial')['status'] == 'LAUNCH_REQUESTED'
    args = desktop._arguments(['--service', 'http://127.0.0.1:8766', *calls[0]])
    assert args.tool == 'material' and args.document_id == 'Mmaterial'
    assert json.loads(args.observation) == SOURCE
    assert len(calls[0]) == 5


@pytest.mark.parametrize('changed', [dict(SOURCE, path='private.csv'), dict(SOURCE, response=''),
                                   dict(SOURCE, input_sha256='old'), dict(SOURCE, job_id='../job')])
def test_unpinned_or_path_selected_observation_never_launches(monkeypatch, changed):
    monkeypatch.setattr(desktop, '_spawn', lambda *_: pytest.fail('Invalid observation launched a process'))
    with pytest.raises(ValueError):
        desktop.launch_material_observation(object(), changed)
