"""Opt-in existing Simulation/JobManager native run, never a runtime installer.

Run from the product repository root. Only this Workbench owns the new job.
Native check status in the delivery is NOT_RUN. --execute-synthetic is required.
"""
import argparse
import json
from pathlib import Path
import time
from caelab.workbench import Workbench
from caelab.jobs import TERMINAL
from examples.impact.bulk_interface.bulk_coupon import settings


def main():
    parser=argparse.ArgumentParser(description='기존 Simulation의 합성 벌크 단일 native 검사')
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--execute-synthetic',action='store_true',required=True)
    parser.add_argument('--nx',type=int,choices=(1,2),default=1)
    parser.add_argument('--output-factor',type=float,choices=(1.,.5),default=1.)
    parser.add_argument('--cfl-scale',type=float,choices=(.9,.45),default=.9)
    args=parser.parse_args();wb=Workbench(args.workspace)
    try:
        owner=wb.simulation_documents
        doc=owner.open(title='합성 벌크 native 검사 — 교정 재료 아님',draft={
            'backend':'explicit.opencourant.model','settings':settings(args.nx,args.output_factor,args.cfl_scale)})
        def command(op):
            now=owner.read(doc['id'])
            return owner.command(doc['id'],op,{},session_id=now['session_id'],expected_generation=now['generation'])
        command('document.save');job=command('simulation.evaluate')['job']
        while wb.manager.status(job['id'])['state'] not in TERMINAL:time.sleep(.1)
        terminal=wb.manager.status(job['id']);command('document.save')
        print(json.dumps({'document_id':doc['id'],'job':terminal,'fixture':'SYNTHETIC_ONLY'},ensure_ascii=False,indent=2))
        return 0 if terminal['state']=='SUCCEEDED' else 1
    finally:
        closed=wb.shutdown(timeout=15.)
        if not closed['joined']:raise RuntimeError('Owned job cleanup remains pending; preserve original process receipt')

if __name__=='__main__':raise SystemExit(main())
