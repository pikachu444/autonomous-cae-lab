"""Explicit native acceptance runner using the EXISTING contact adapter only.

Does not install/run anything until main() is explicitly invoked. This utility
was not executed with a real solver on the delivery host. No tolerance defaults
are supplied: the numerical comparison policy must be declared before running.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import hashlib
import json
import math
import shutil
import sys
import uuid

from caelab.adapters.contact_fem import ContactFemCalculixAdapter, validate_snapshot
from caelab.contact_deck import render
from caelab.dynamic_model import attach, has_dynamic
from caelab.dynamic_restart import prepare,compare_saved_states
from caelab.dynamic_results import read_attempt,compare_continuation
from caelab.storage import save_json


OUTPUT_TOLERANCES = {'DISP','VELO','FORC','STRESS','TOSTRAIN','ENER','ENER_IP','ELKE','ELSE'}
SAVED_TOLERANCES = {'vold','veold','sti','eme','ener','xstate','pslavsurf','clearini',
                    'xmodal','ctrl','qaold','prestr','xmodal_modes'}


def validate_policy(policy, model):
    """Refuse an incomplete/invalid comparison policy BEFORE any native run."""
    from caelab.calculix_material import has_plasticity
    keys={'absolute','relative','time','saved_arrays','saved_relative','saved_time'}
    if not isinstance(policy,dict) or set(policy)!=keys:
        raise ValueError('Declare all output/state/time tolerances before execution')
    def finite(value):
        return type(value) in (int,float) and math.isfinite(value) and value>=0
    for name in ('relative','time','saved_relative','saved_time'):
        if not finite(policy[name]):raise ValueError('Finite nonnegative tolerance required: '+name)
    required=OUTPUT_TOLERANCES|({'PE'} if has_plasticity(model) else set())
    for name,expected in (('absolute',required),('saved_arrays',SAVED_TOLERANCES)):
        values=policy[name]
        if not isinstance(values,dict) or not expected<=set(values) or any(not finite(v) for v in values.values()):
            raise ValueError('Predeclare every required finite nonnegative tolerance: '+name)


def prefix_snapshot(source,steps,root):
    manifest,model,pins,_=validate_snapshot(Path(source).absolute())
    draft=deepcopy(model['dynamic']['draft']);draft['program']['steps']=deepcopy(steps)
    procedures={r.get('procedure',draft['program']['procedure']) for r in steps}
    draft['program']['procedure']=next(iter(procedures)) if len(procedures)==1 else 'mixed'
    if not has_dynamic(draft['program']):raise ValueError('This acceptance helper requires at least one dynamic step before the split')
    prefix=attach(model,draft);folder=Path(root)/('F'+uuid.uuid4().hex);folder.mkdir(parents=True,exist_ok=False)
    for name in pins:
        if name in ('mesh.json','contact.inp','snapshot.json'):continue
        target=folder/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(Path(source).parent/name,target)
    save_json(folder/'mesh.json',prefix);(folder/'contact.inp').write_text(render(prefix),encoding='ascii',newline='\n')
    data=deepcopy(manifest);data.update(id=folder.name,solver_execution='NOT_PERFORMED')
    data['files']=[{'relative':p.relative_to(folder).as_posix(),'bytes':p.stat().st_size,
        'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(folder.rglob('*')) if p.is_file()]
    save_json(folder/'snapshot.json',data);validate_snapshot(folder/'snapshot.json');return folder/'snapshot.json'


def verify(snapshot,output,policy,*,checkpoint_step=None):
    """Three explicit native runs: continuous, prefix, actual READ continuation.

    No automatic reruns, binary substitutions, state conversions or interpolation.
    UNKNOWN engineering qualification is retained even when numeric checks pass.
    """
    snapshot=Path(snapshot).absolute();output=Path(output).absolute()
    manifest,model,_,_=validate_snapshot(snapshot)
    if model.get('restart'):raise ValueError('Select the original full-program input, not a prior READ input')
    rows=model['analysis_steps']['steps'];cut=len(rows)-1 if checkpoint_step is None else checkpoint_step
    if type(cut) is not int or not 1<=cut<len(rows):raise ValueError('Choose a completed step before the final dynamic stage')
    validate_policy(policy,model)
    output.mkdir(parents=True,exist_ok=False)
    save_json(output/'predeclared-comparison-policy.json',policy)
    adapter=ContactFemCalculixAdapter()
    continuous=adapter.run({'snapshot_path':str(snapshot)},output=output/'continuous')
    if continuous['execution_status']!='SUCCEEDED':raise ValueError('Continuous solve failed; retained original output must be inspected')
    prefix=prefix_snapshot(snapshot,rows[:cut],output/'prefix-input')
    first=adapter.run({'snapshot_path':str(prefix)},output=output/'prefix')
    if first['execution_status']!='SUCCEEDED':raise ValueError('Prefix solve failed; no implicit retry or fabricated checkpoint')
    continued=prepare(output/'prefix',cut,rows[cut:],output/'read-input')
    resumed=adapter.run({'snapshot_path':str(continued)},output=output/'resumed')
    if resumed['execution_status']!='SUCCEEDED':raise ValueError('Actual READ solve failed; its rin, deck and output are retained')
    # Cold reopen only reads the retained attempts; the adapter is not invoked.
    a,b=read_attempt(output/'continuous'),read_attempt(output/'resumed')
    values=compare_continuation(a,b,absolute_tolerances=policy['absolute'],relative_tolerance=policy['relative'],time_tolerance=policy['time'])
    state=compare_saved_states(output/'continuous/solver/contact.rout',output/'resumed/solver/contact.rout',
        left_step=len(rows),right_step=len(rows),tolerances=policy['saved_arrays'],
        relative_tolerance=policy['saved_relative'],time_tolerance=policy['saved_time'])
    statuses={values['status'],state['status']}
    result={'status':'FAIL' if 'FAIL' in statuses else 'INCOMPLETE' if 'INCOMPLETE' in statuses else 'PASS',
        'output_comparison':values,'saved_state_comparison':state,'qualification':'UNKNOWN','decision':'NOT_RELEASED',
        'scope':'three explicitly invoked native adapter attempts; GUI/physical experiment not certified',
        'native_runtime':resumed['runtime'],'checkpoint_step':cut}
    save_json(output/'native-comparison.json',result);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot');parser.add_argument('output');parser.add_argument('--policy',required=True)
    parser.add_argument('--checkpoint-step',type=int);args=parser.parse_args()
    output=Path(args.output).absolute()
    try:
        policy=json.loads(Path(args.policy).read_text(encoding='utf-8'))
        result=verify(args.snapshot,output,policy,checkpoint_step=args.checkpoint_step)
        print(json.dumps({'status':result['status'],'report':str(output/'native-comparison.json'),
                          'qualification':'UNKNOWN'},ensure_ascii=False))
        return 0 if result['status']=='PASS' else 2
    except Exception as exc:
        if output.is_dir():save_json(output/('acceptance-failure-'+uuid.uuid4().hex+'.json'),
            {'error':str(exc),'status':'NOT_ACCEPTED','qualification':'UNKNOWN','original_attempts_preserved':True})
        print(str(exc),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
