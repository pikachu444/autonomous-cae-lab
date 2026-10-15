"""Open the native analysis editor on an EXISTING local service; never auto-run.

Select exactly one: an original Data result, a saved Numerical evidence ref JSON,
a published Data processing selector JSON, or a saved analysis Plan document.
JSON is only the optional integration/diagnostics route; normal users use menus.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service',required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--data-document');group.add_argument('--evidence-json',type=Path)
    group.add_argument('--processing-json',type=Path);group.add_argument('--document-id')
    parser.add_argument('--job');parser.add_argument('--response')
    args=parser.parse_args(argv)
    if args.data_document and not (args.job and args.response):parser.error('Data 원 job/응답을 명시하세요.')
    from PySide6.QtWidgets import QApplication
    from caelab.workbench_client import Client
    from apps.research.experiment_analysis_window import ExperimentAnalysisWindow
    client=Client(args.service);kwargs={}
    if args.data_document:
        ref=client.document_result_reference(args.data_document,args.job)
        kwargs['source']={'kind':'result_response','reference':ref,'response':args.response}
    elif args.evidence_json:
        kwargs['evidence_reference']=json.loads(args.evidence_json.read_text(encoding='utf-8'))
    elif args.processing_json:
        kwargs['source']=json.loads(args.processing_json.read_text(encoding='utf-8'))
    else:kwargs['document_id']=args.document_id
    app=QApplication.instance() or QApplication([])
    from apps.research.appearance import apply_appearance
    apply_appearance(app)
    window=ExperimentAnalysisWindow(client,**kwargs);window.show()
    return app.exec()

if __name__=='__main__':raise SystemExit(main())
