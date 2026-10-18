"""Complete only the retained B-observation read/busy/cancel acceptance delta."""
from copy import deepcopy
import argparse
import hashlib
from pathlib import Path
import sys
import threading
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from apps.research.material_window import MaterialWindow
from apps.research.result_return import review_material_observation
from caelab.storage import canonical_hash,load_json,save_json
from caelab.workbench_client import Client
from test_material_observation_owner_ui import MATERIAL,DATA,JOB,wait


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    pins={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
        'apps/research/material_window.py','apps/research/result_return.py',
        'apps/research/material_plan_panel.py','tests/check_material_observation_cancel_delta.py',
        'tests/test_material_observation_owner_ui.py')}
    def core():
        return {p.parent.name:{k:load_json(p).get(k) for k in ('draft','generation','runs','saved_revision')}
                for p in (args.store/'workbench/documents').glob('*/working.json')
                if p.parent.name.startswith(('M','N'))}
    before=core();service=LabService(args.store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}');app=QApplication([]);window=None
    def forbidden(*a,**kw):raise AssertionError('The cancellation delta cannot submit')
    server.workbench.submit=server.workbench.manager.submit=forbidden
    for owner in server.workbench.research_owners():owner.submit=forbidden
    try:
        jobs=client.request('/api/workbench')['jobs']
        data=client.document_open(kind='data',document_id=DATA)
        run=next(r for r in data['runs'] if r['job_id']==JOB)
        observation={key:run[key] for key in ('job_id','input_revision','input_sha256')}
        observation.update(document_id=DATA,response='fm_deformation')
        doc=client.document_open(kind='material',document_id=MATERIAL)
        window=MaterialWindow(client,document_id=MATERIAL,poll_interval=60000);window.show()
        wait(app,lambda:window.document is not None and not window._busy)
        panel=window.open_plan_variables()
        wait(app,lambda:panel.plans.currentData() is not None and not panel._busy and not window._busy)
        window.coefficients.item(0,1).setText('1e');app.processEvents()
        dirty=deepcopy(window.edited_draft());assert window.local_dirty
        receipt=review_material_observation(client,MATERIAL,observation)
        assert receipt['status']=='PRESENTED' and window._pending_observation_source==observation
        # Reuse an actual existing N9 result read. A synchronous action while
        # this real worker is busy must retain B; this is no registration/run.
        wait(app,lambda:not panel._busy)
        plan=panel._documents[panel.plans.currentData()];job=plan['runs'][-1]['job_id']
        assert panel._call(lambda:client.document_result(plan['id'],job),lambda _:None)
        busy_gate=dict(panel_busy=panel._busy,staged=deepcopy(panel._staged_observation),
            action_enabled=window.cancel_observation_action.isEnabled())
        assert busy_gate['panel_busy'] and busy_gate['staged'] is None and busy_gate['action_enabled']
        window.cancel_observation_action.trigger()
        busy_gate['message_after']=window.message.text()
        assert window._pending_observation_source==observation
        wait(app,lambda:not panel._busy and not window._busy)
        settled_gate=dict(panel_busy=panel._busy,staged=deepcopy(panel._staged_observation),
            action_enabled=window.cancel_observation_action.isEnabled(),message=window.message.text())
        assert settled_gate['action_enabled'] and settled_gate['staged'] is None
        window.cancel_observation_action.trigger();app.processEvents()
        assert window._pending_observation_source is None and panel._pending_observation is None
        assert window.edited_draft()==dirty
        wait(app,lambda:not panel._busy and not window._busy)
        assert core()==before and client.request('/api/workbench')['jobs']==jobs
        assert pins=={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in pins}
        save_json(args.output/'cancel-delta.json',dict(status='PASS',material_id=MATERIAL,
            session_id=doc['session_id'],observation=observation,receipt=receipt,
            busy_gate=busy_gate,settled_gate=settled_gate,pending_after_cancel=None,
            dirty_draft_sha256=canonical_hash(dirty),core_documents_unchanged=len(before),
            source_pins=pins,jobs_before=len(jobs),jobs_after=len(jobs),new_jobs=0,
            scope='Last B delivery, actual existing result read, settle and explicit cancel only; prior actual03 stages not repeated.',
            claim='Actual HTTP/Qt action, not physical OS input'))
    finally:
        if window is not None:
            wait(app,lambda:not window._busy)
            if window._plan_panel is not None:wait(app,lambda:not window._plan_panel._busy)
            window._allow_close=True;window.close();app.processEvents()
        server.shutdown();server.server_close();service.shutdown();thread.join(5)


if __name__=='__main__':main()
