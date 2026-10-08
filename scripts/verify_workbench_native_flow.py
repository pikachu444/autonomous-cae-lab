"""Exercise actual native jobs, common channel comparison and solver-free restart."""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from caelab.storage import save_json
from caelab.workbench import Workbench
from plugins.pde_transient.reference import manufactured_settings
from scripts.verify_openradioss import specification


def run(store):
    store = Path(store).resolve()
    store.mkdir(parents=True, exist_ok=False)
    configuration = {'workers': 2, 'cpu_budget': 4, 'workspace_id': 'native-flow'}
    bench = Workbench(store, configuration=configuration)
    records = {}

    def wait(job):
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            current = bench.manager.status(job['id'])
            if current['status'] in {'SUCCEEDED', 'FAILED', 'PARTIAL_FAILURE', 'CANCELLED', 'INTERRUPTED'}:
                assert current['status'] == 'SUCCEEDED', current
                return job['id']
            time.sleep(.2)
        raise TimeoutError(job['id'])

    try:
        jobs = [
            ('pde', 'pde.fenicsx.transient', manufactured_settings(), 'pde.study2.u@544'),
            ('explicit', 'explicit.openradioss', specification(), 'radioss-center-vz'),
            ('explicit_changed', 'explicit.openradioss', {**specification(), 'gravity_m_s2': 4.905}, 'radioss-center-vz'),
        ]
        for label, backend, settings, channel in jobs:
            identifier = wait(bench.submit('run', {'backend': backend, 'settings': settings}))
            result = bench.result(identifier, selection=[channel])
            assert result['execution_status'] == 'SUCCEEDED', result
            selected = result['responses'][channel]
            assert len(selected['value']) > 10 and len(selected['axes'][0]['values']) == len(selected['value'])
            records[label] = {'job_id': identifier, 'channel': channel, 'response': selected}
            print(label, identifier, len(selected['value']), flush=True)
        comparison = wait(bench.submit('compare', {
            'prediction_job': records['explicit_changed']['job_id'],
            'observation_job': records['explicit']['job_id'],
            'prediction_response': 'radioss-center-vz', 'observation_response': 'radioss-center-vz'}))
        records['comparison'] = {'job_id': comparison, 'result': bench.result(comparison)}
        pde_comparison=wait(bench.submit('compare',{
            'prediction_job':records['pde']['job_id'],'observation_job':records['pde']['job_id'],
            'prediction_response':records['pde']['channel'],'observation_response':records['pde']['channel']}))
        records['pde_identity_comparison']={'job_id':pde_comparison,'result':bench.result(pde_comparison)}
    finally:
        bench.manager.shutdown()
    # Reading these retained bytes must not probe/import a native runtime.
    prior = {key: os.environ.pop(key, None) for key in ('CAELAB_FENICSX_PYTHON', 'CAELAB_OPENRADIOSS_ROOT')}
    restarted = Workbench(store, configuration=configuration)
    try:
        for label in ('pde', 'explicit', 'explicit_changed'):
            entry = records[label]
            reread = restarted.result(entry['job_id'], selection=[entry['channel']])
            assert reread['responses'][entry['channel']] == entry['response']
        records['restart_solver_free'] = True
    finally:
        restarted.manager.shutdown()
        for key, value in prior.items():
            if value is not None:
                os.environ[key] = value
    save_json(store / 'native_flow_receipt.json', records)
    print('Native workbench flow passed:', store, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', required=True)
    run(parser.parse_args().store)
