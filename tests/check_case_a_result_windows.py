"""Select actual retained DP FE derived responses in the existing Qt window."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from apps.research.simulation_window import SimulationWindow
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from caelab.workbench_client import Client
from caelab.storage import canonical_hash,save_json,load_json


def wait(app,predicate):
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        time.sleep(.01)
    raise TimeoutError('Existing Qt result selection/read')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execution',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--capture-only',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    receipt=load_json(args.execution/'execution.json');store=Path(receipt['store'])
    sources=('caelab/law_native_fe.py','caelab/adapters/law_native_fe_worker.py',
        'apps/research/simulation_window.py','tests/check_case_a_result_windows.py')
    pins={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}');app=QApplication([]);window=None
    try:
        jobs=client.request('/api/workbench')['jobs']
        source=next(c for c in receipt['cases'] if c['name']=='transverse_strain_confinement_DP_FE')
        doc=client.document_open(kind='simulation',document_id=source['document_id'])
        window=SimulationWindow(client,document_id=doc['id'],poll_interval=60000);window.show()
        wait(app,lambda:'ip0_pressure' in (window._result or {}).get('responses',{}) and not window._busy)
        assert window._selected_job==source['job_id']
        responses=('ip0_pressure',) if args.capture_only else ('ip0_pressure','ip0_plastic_volume_strain','ip0_kappa','ip0_pressure')
        for response in responses:
            index=next((i for i in range(window.result_selector.count())
                if tuple(window.result_selector.itemData(i))==('response',response)), -1)
            assert index>=0
            window.result_selector.setCurrentIndex(index);window.result_selector.setFocus();app.processEvents()
            line=window.result_axes.lines[0]
            np.testing.assert_array_equal(line.get_ydata(),window._result['responses'][response]['value'])
            assert tuple(window.result_selector.currentData())==('response',response)
        for width,height in ((1440,900),(1000,720)):
            window.resize(width,height);app.processEvents()
            assert window.width()==width
            window.result_canvas.draw();app.processEvents()
            assert window.grab().save(str(args.output/f'DP-FE-pressure-{width}.png'))
        after=client.document_read(doc['id'])
        assert after['draft']==doc['draft'] and after['runs']==doc['runs']
        assert canonical_hash(client.document_result(doc['id'],source['job_id']))==source['result_sha256']
        assert client.request('/api/workbench')['jobs']==jobs
        assert pins=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
        save_json(args.output/'result-windows.json',dict(status='PASS',source_files=pins,source=source,
            normal_width=1440,narrow_width=1000,selected_response='ip0_pressure',new_jobs=0,
            jobs_before=len(jobs),jobs_after=len(jobs),original_inputs_results_preserved=True,
            claim='Actual Qt selection/focus/render; no physical OS input claim',
            mode='label_delta_capture_only' if args.capture_only else 'response_selection_check'))
    finally:
        if window is not None:window._allow_close=True;window.close();app.processEvents()
        server.shutdown();server.server_close();service.shutdown();thread.join(5)


if __name__=='__main__':main()
