"""Two explicit stages on YOUR current native Analysis; no meshing or solving.

Call apply_two_steps(owner, analysis_id, force_id) from an already connected
FreeCAD owner. This edits its native document: use a working copy and Save.
Optional CLI reads one frozen snapshot; --run is a separate explicit action.
"""
from copy import deepcopy
from pathlib import Path


def apply_two_steps(owner, analysis_id, force_id, *, peak_N=100., procedure='static', duration=1.):
    from caelab.contact import number
    if procedure not in ('static','dynamic'):
        raise ValueError('Choose static or dynamic explicitly')
    peak,period=number(peak_N),number(duration)
    if period<=0: raise ValueError('Positive step duration required')
    editor=owner.fem.contact
    analysis=owner._object(analysis_id)
    info=editor.step_inputs(analysis)
    force=next((r for r in info['conditions'] if r['object_id']==force_id and r['type']=='Fem::ConstraintForce'),None)
    if force is None: raise ValueError('Select this Analysis Force by its exact native object name')
    first=deepcopy(info['step_defaults'])
    first.update(id='Step1',label='가압',duration=period,initial=period/10,
                 minimum=period/10000,maximum=period/10,increments=1000,output_frequency=1)
    for c in first['curves']:
        end=peak if c['condition_id']==force_id else c['points'][-1][1]
        c.update(mode='curve',points=[[0,0],[period,end]])
    second=deepcopy(first); second.update(id='Step2',label='제하')
    for c in second['curves']:
        end=c['points'][-1][1]
        c.update(mode='curve' if c['condition_id']==force_id else 'hold',
                 points=[[0,end],[period,0 if c['condition_id']==force_id else end]])
    return editor.set_steps(analysis,{'draft':{'schema_version':'1','procedure':procedure,'steps':[first,second]}})


def main(argv=None):
    import argparse
    import json
    from caelab.adapters.contact_fem import validate_snapshot,ContactFemCalculixAdapter
    from caelab.contact_steps import profile
    parser=argparse.ArgumentParser(description='Inspect already frozen contact stages; solve only with --run')
    parser.add_argument('--snapshot',required=True,type=Path)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    manifest,model,pins,gates=validate_snapshot(args.snapshot)
    print(json.dumps({'label':manifest.get('analysis_id'),'steps':profile(model),
                      'solver_execution':'NOT_PERFORMED'},ensure_ascii=False))
    if not args.run:
        return 0
    if args.output is None:
        parser.error('--run needs a fresh --output folder')
    result=ContactFemCalculixAdapter().run({'snapshot_path':str(args.snapshot.resolve())},output=args.output)
    print(json.dumps({'execution_status':result['execution_status'],'diagnostics':result['diagnostics'],
                      'post':result.get('post_artifact'),'partial':result.get('partial_result')},ensure_ascii=False))
    return 0 if result['execution_status']=='SUCCEEDED' else 1


if __name__=='__main__':
    raise SystemExit(main())
