"""Installed ParaView: time measurement + Data → preview/apply/save/cold reopen.

No solver/provider. Prepare inputs first with python -m examples.post_curves.
"""
import argparse
import builtins
from copy import deepcopy
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--create',type=Path,help='prepared examples.post_curves input.json')
    modes.add_argument('--reopen',type=Path,help='receipt.json from the first process')
    args=parser.parse_args(argv)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from apps.desktop_post import external
    from apps.desktop_post.bridge import Owner
    if args.reopen:
        receipt=json.loads(args.reopen.read_text(encoding='utf-8'))
        path=Path(receipt['project']);doc=json.loads(path.read_text(encoding='utf-8-sig'))
        os.environ['CAE_POST_PROJECT']=str(path)
        external.restore_workspace(path,doc)
        owner=Owner();ws=owner.workspace
        payload=ws.sample(object_ref=receipt['object_ref'],preview=False,limit=1000)
        assert payload['rows']==receipt['rows']
        assert payload['originals']==receipt['originals']
        assert not ws.restore_issues,ws.restore_issues
        assert ws.restore_selection()
        print('PASS same rows, units, original samples and alignment after cold reopen; no new calculation')
        return 0
    inputs=json.loads(args.create.read_text(encoding='utf-8'))
    root=args.create.resolve().parent
    external.open_result(inputs['native_field'],root/'post-project')
    owner=Owner();ws=owner.workspace
    measure={'source_ref':'result','measurement':'time','association':'POINTS','array':'force',
        'point_indices':[0],'quantity':'force','units':'N','measure':'force','frame':'global',
        'coordinate_units':'mm','coordinate_frame':'global','time_units':'s','time_origin':'physical_time',
        'layout':{'kind':'vector','components':['x','y','z']}}
    obj=ws.edit_measurement(draft=measure,title='상단 힘')
    ws.validate(object_ref=obj['id']);ws.apply(object_ref=obj['id'],show=False)
    owner.save_project()
    native=inputs['curve_input']
    added=ws.add_source(input_id=native['id'],receipt=native,label_text='하중 시험')
    options=ws.curve_catalog()
    a=next(o for o in options['curves'] if o['source_ref']==obj['id'] and
           o['declaration']['observable'].get('selection')=='x' and o['axis_column']=='Time')
    b=next(o for o in options['curves'] if o['source_ref']==added['source_ref'])
    a,b=deepcopy(a),deepcopy(b)
    b['declaration']['quantity']='force'
    assert a['declaration']['reduction']==b['declaration']['reduction']=='none', options
    recipe={'version':3,'a':a,'b':b,'axis_kind':'physical_time',
        'axis_origins':{'a':'load start','b':'DAQ start'},'b_axis_offset':-.1,
        'alignment':'bracket','max_gap':1.,'axis_tolerance':0.,'target_unit':'N','locations_confirmed':True}
    compared=ws.edit_comparison(draft=recipe,title='시험과 해석')
    ws.validate(object_ref=compared['id'])
    preview=ws.sample(object_ref=compared['id'],preview=True,limit=1000)
    assert not preview['summary']['blocked'],preview['summary']
    assert len(preview['rows'])==3,preview
    assert builtins.all(row['valid'] and abs(row['delta'])<1e-12 for row in preview['rows']),preview
    assert preview['rows'][0]['percent'] is None
    assert preview['rows'][1]['weight']==.5
    ws.apply(object_ref=compared['id'],show=True)
    # Editing and resetting a preview never overwrites the applied values.
    changed=deepcopy(recipe);changed['b_axis_offset']='1e'
    ws.edit_comparison(draft=changed,object_ref=compared['id'])
    ws.validate(object_ref=compared['id'])
    assert ws.sample(object_ref=compared['id'],preview=True)['summary']['blocked']
    assert ws.sample(object_ref=compared['id'],preview=False)['rows']==preview['rows']
    ws.reset(object_ref=compared['id'])
    ws.undo(object_ref=compared['id']);ws.redo(object_ref=compared['id'])
    ws.sample(object_ref=compared['id'],preview=False,row_index=1,expected_revision=ws.applied(ws.object(compared['id']))['id'])
    saved=owner.save_project()
    retained=ws.sample(object_ref=compared['id'],preview=False,limit=1000)
    receipt={'project':str(saved),'object_ref':compared['id'],'rows':retained['rows'],
        'originals':retained['originals'],'solver_execution':'NOT_PERFORMED','provider_execution':'NOT_PERFORMED'}
    path=root/'receipt.json'
    path.write_text(json.dumps(receipt,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    print('PASS native curve comparison, preview/reset/Undo/Redo/save; next --reopen '+str(path))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
