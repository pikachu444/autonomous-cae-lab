"""A transient Windows sharing lock must not release an unverified native child."""
from types import SimpleNamespace
import json
import pytest
from caelab import windows_job


@pytest.mark.parametrize('condition', ['transient', 'timeout', 'cancel', 'wrong_pid', 'invalid_json'])
def test_gate_read_sharing_lock_preserves_deadline_identity_and_cancellation(monkeypatch, condition):
    released, assigned, reads = [], [], []
    process = SimpleNamespace(pid=42, poll=lambda: None,
        stdin=SimpleNamespace(write=lambda value: released.append(value), flush=lambda: None, close=lambda: None),
        _caelab_windows_job=SimpleNamespace(assign=lambda value: assigned.append(value)))
    def read_text(**_):
        reads.append(1)
        if len(reads)==1 or condition=='timeout':
            raise PermissionError('controlled Windows sharing lock')
        return 'bad json' if condition=='invalid_json' else json.dumps({'pid':43 if condition=='wrong_pid' else 42})
    ready=SimpleNamespace(is_file=lambda: True, read_text=read_text)
    clock=[0.]
    monkeypatch.setattr(windows_job.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(windows_job.time, 'sleep', lambda _: clock.__setitem__(0, clock[0]+6.))
    def cancelled():
        if condition=='cancel' and reads: raise InterruptedError('user cancelled')
    if condition=='transient':
        windows_job.release_gate(process, ready, cancelled)
        assert len(reads)==2 and released==[b'R'] and assigned==[process]
    else:
        error=InterruptedError if condition=='cancel' else json.JSONDecodeError if condition=='invalid_json' else RuntimeError
        with pytest.raises(error): windows_job.release_gate(process, ready, cancelled)
        assert released==[] and assigned==[]
