"""Read one saved Study pressure preview after the physical-caption correction."""
import argparse
import hashlib
from pathlib import Path
import sys
import threading
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtWidgets import QApplication
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from apps.research.study_window import StudyWindow
from apps.research.law_native_labels import LABELS
from caelab.workbench_client import Client
from caelab.storage import canonical_hash,load_json,save_json
from check_case_a_study_windows import wait


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execution',type=Path,required=True)
    parser.add_argument('--prior',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    previous=load_json(args.prior/'study.json')
    sources=('apps/research/simulation_window.py','apps/research/reference_content.py',
             'apps/research/law_native_labels.py')
    pins={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
    service=LabService(Path(load_json(args.execution/'execution.json')['store']))
    server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}');app=QApplication([]);window=None
    try:
        jobs=client.request('/api/workbench')['jobs'];assert len(jobs)==10
        doc=client.document_open(kind='study',document_id=previous['document_id'])
        assert canonical_hash(doc['draft'])==previous['draft_sha256']
        assert doc['saved_revision']==previous['saved_revision']
        window=StudyWindow(client,document_id=doc['id'],poll_interval=60000);window.show()
        def ready():
            return (window.document is not None and not window._busy and not window._callbacks
                and window._content_pending is None and (window.reading.payload or {}).get('status')=='AVAILABLE')
        wait(app,ready)
        index=window.reading.channel.findData('ip0_pressure');assert index>=0
        window.reading.channel.setCurrentIndex(index);window.reading.channel.setFocus();window.reading.read.click()
        wait(app,lambda:ready() and bool(window.reading.axes.lines))
        label=LABELS['ip0_pressure']
        assert window.reading.channel.currentData()=='ip0_pressure'
        assert label in window.reading.channel.currentText()
        assert label in window.reading.title.text() and label in window.reading.axes.get_ylabel()
        raw=window.reading.payload['result']['responses']['ip0_pressure']
        assert raw['component']=='pressure' and raw['location']=='integration_point'
        assert raw['measure']=='minus_trace_Cauchy_over_3_compression_positive'
        for width,height in ((1440,900),(1000,720)):
            window.resize(width,height);app.processEvents();window.reading.canvas.draw();app.processEvents()
            assert window.width()==width
            assert window.grab().save(str(args.output/f'pressure-{width}.png'))
        after=client.document_read(doc['id'])
        assert after['draft']==doc['draft'] and after['saved_revision']==doc['saved_revision']
        assert client.request('/api/workbench')['jobs']==jobs
        assert pins=={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources}
        save_json(args.output/'caption.json',dict(status='PASS',document_id=doc['id'],
            saved_revision=doc['saved_revision'],draft_sha256=canonical_hash(doc['draft']),
            caption_sources=pins,checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            label=label,raw_response='ip0_pressure',raw_measure=raw['measure'],raw_location=raw['location'],
            new_studies=0,new_saves=0,new_jobs=0,jobs_before=10,jobs_after=10,
            scope='One pressure preview and two renders only; no repeat of nine-reference/Post acceptance.',
            simulation_lifecycle='Source hash includes separate B8 lifecycle edits; this check exercises Study ReferenceContent caption only.',
            claim='Actual Qt selection/read/render, not physical OS input'))
    finally:
        if window is not None:window._allow_close=True;window.close();app.processEvents()
        server.shutdown();server.server_close();service.shutdown();thread.join(5)


if __name__=='__main__':main()
