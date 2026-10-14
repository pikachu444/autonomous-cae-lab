"""Test-only script for ParaView --script. Uses the existing native startup.

The tester operates the real menu/keys. Snapshots and callback evidence are
recorded; they are not substituted for actual input-route evidence/captures.
"""
from __future__ import annotations
import atexit
import json
import os
from pathlib import Path
import runpy
import sys
import traceback
from datetime import datetime, timezone

config = json.loads(Path(os.environ['CAE_POST_EXIT_CHECK_CONFIG']).read_text(encoding='utf-8'))
output = Path(config['output']).resolve(strict=True)
log_path = output / 'native-events.jsonl'

def log(event, **details):
    with log_path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'event': event, 'pid': os.getpid(),
            'utc': datetime.now(timezone.utc).isoformat(), **details}, ensure_ascii=False, default=str) + '\n')

try:
    for name, key in [('CAE_POST_HOME', 'home'), ('CAE_POST_EXIT_PLUGIN', 'plugin'),
                      ('CAE_POST_PARAVIEW_ROOT', 'runtime'), ('CAE_POST_PROJECT', 'project'),
                      ('CAE_POST_SERVICE_URL', 'service_url')]:
        os.environ[name] = config[key]
    os.environ['CAE_POST_LAUNCH_DIR'] = str(output)
    sys.path.insert(0, config['home'])
    scope = runpy.run_path(str(Path(config['home']) / 'startup.py'))
    retained_bridge = scope['cae_post_bridge']
    if retained_bridge is None:
        raise RuntimeError('The existing native startup did not install its owner/broker')
    owner, dispatcher, broker = retained_bridge
    session = dispatcher.native_exit
    if session is None:
        raise RuntimeError('The native exit plugin is unavailable; no full-exit acceptance is possible')
    owner.refresh()
    log('ready', declared_route=config['route_declared'], route_automatically_observed=False,
        native=session._status().as_dict(), descriptor=owner.descriptor(), snapshot=owner.snapshot)
    original_event = session.on_event
    def observed(attempt, event):
        log('callback_enter', attempt=attempt, native_event=event)
        try:
            decision = original_event(attempt, event)
            log('callback_return', attempt=attempt, native_event=event, decision=decision,
                owner_closed=owner.closed, dispatcher_closed=dispatcher.closed,
                native_registration=session.registration,
                source_observer_count=len(owner._observers),
                snapshot=owner.snapshot, descriptor=owner.descriptor())
            return decision
        except BaseException:
            log('callback_exception', attempt=attempt, native_event=event, traceback=traceback.format_exc())
            raise
    session.on_event = observed
    dispatcher.native_controls.log = log
    def finalize():
        log('interpreter_finalizing', owner_closed=owner.closed, dispatcher_closed=dispatcher.closed,
            observer_count=len(owner._observers), native_registration=session.registration,
            broker_stopped=broker.stop.is_set())
    atexit.register(finalize)
    print('검사용 관리 Post입니다. 지정한 실제 종료 경로와 한글 선택을 실행하세요. '
          '입력 경로/화면 캡처는 검수표에 별도로 기록해야 합니다.', flush=True)
except BaseException:
    log('startup_failed', traceback=traceback.format_exc())
    raise
