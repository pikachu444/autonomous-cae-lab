"""Installed pvpython owner preview/apply/save and separate-process reopen.

Never invokes a solver. --create requires a NEW directory. --reopen reads the
saved receipt without regenerating fixtures or revalidating the comparison.
"""
import argparse
import builtins
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--create',type=Path); modes.add_argument('--reopen',type=Path)
    args=parser.parse_args(argv)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from apps.desktop_post import external
    from apps.desktop_post.bridge import Owner
    if args.reopen:
        receipt=json.loads(args.reopen.read_text(encoding='utf-8'))
        project=Path(receipt['project'])
        doc=json.loads(project.read_text(encoding='utf-8-sig'))
        os.environ['CAE_POST_PROJECT']=str(project)
        external.restore_workspace(project,doc)
        owner=Owner(); workspace=owner.workspace
        rows=workspace.sample(object_ref=receipt['object_ref'],preview=False,limit=1000)['rows']
        assert rows==receipt['rows']
        for retained in receipt.get('derived', []):
            actual = workspace.sample(object_ref=retained['object_ref'], preview=False, limit=1000)['rows']
            assert actual == retained['rows']
            assert workspace._output_declaration(retained['object_ref']) == retained['declaration']
        assert not workspace.restore_issues, workspace.restore_issues
        print('PASS cold reopen, same original/transformed/difference/masks; no solver')
        return 0
    from examples.post_comparison import create
    root=args.create.resolve(); root.mkdir(parents=True,exist_ok=False)
    recipe=create(root/'input')
    external.open_result(root/'input/a.pvd',root/'project')
    owner=Owner(); workspace=owner.workspace
    b_source,b_record=external.admit_result(root/'input/b.pvd')
    # Same native admission implementation as workspace.add_source; local fixture
    # has no broker registration receipt and must not fabricate one.
    b_record.update(source_ref='manufactured-b',label='회전된 힘')
    workspace.document['sources']['manufactured-b']=b_record
    recipe['b']['source_ref']='manufactured-b'
    obj=workspace.edit_comparison(draft=recipe,title='힘 비교')
    preview=workspace.validate(object_ref=obj['id'])
    page=workspace.sample(object_ref=obj['id'],preview=True,limit=1000)
    assert len(page['rows'])==4
    assert [row['valid'] for row in page['rows']]==[True,True,False,True]
    for row in page['rows']:
        if row['valid']:
            assert abs(row['delta'])<1e-12 and abs(row['a']-2)<1e-12 and abs(row['b']-2)<1e-12
    workspace.apply(object_ref=obj['id'],show=True)
    workspace.undo(object_ref=obj['id']); workspace.redo(object_ref=obj['id'])
    # Changed path: fixed-clock comparison -> exact point/path measurement ->
    # comparison again. No time search on a retained single-sample output.
    from copy import deepcopy
    derived = []
    declaration = workspace._output_declaration(obj['id'])
    assert declaration['frozen_clock'] == {'value':.5, 'unit':'s', 'semantics':'physical_time'}
    for kind in ('point', 'path'):
        measured = {'source_ref':obj['id'], 'measurement':kind, 'array':'A_original',
            'association':'POINTS', 'time':None, 'point_indices':[0,2],
            'point1':[0.,0.,0.], 'point2':[0.,1.,0.], 'resolution':4, 'tolerance':0.}
        measurement = workspace.edit_measurement(draft=measured, title='비교의 점' if kind=='point' else '비교의 경로')
        workspace.validate(object_ref=measurement['id'])
        workspace.apply(object_ref=measurement['id'], show=False)
        declared = workspace._output_declaration(measurement['id'])
        assert declared['frozen_clock'] == declaration['frozen_clock']
        assert declared['arrays'][0]['layout']['scalar_semantics'] == 'component'
        derived.append({'object_ref':measurement['id'],
            'rows':workspace.sample(object_ref=measurement['id'],preview=False,limit=1000)['rows'],
            'declaration':declared})
        repeat = deepcopy(recipe)
        selected = declared['arrays'][0]
        for side in ('a','b'):
            repeat[side] = {key:deepcopy(value) for key,value in selected.items() if key!='name'}
            repeat[side].update(source_ref=measurement['id'],array=selected['name'],
                coordinate_units=declared['coordinate_units'],coordinate_frame=declared['coordinate_frame'],
                frozen_clock=deepcopy(declared['frozen_clock']),sampling={'mode':'exact','time':None},clock_offset=0.)
        from caelab.post_comparison import IDENTITY
        repeat.update(selection='scalar',difference='selected_difference',percent='disabled')
        repeat['alignment'] = {'geometry_rotation':deepcopy(IDENTITY),'response_rotation':deepcopy(IDENTITY),
                               'translation':[0.,0.,0.],'geometry_declared':False,'response_declared':False}
        compared = workspace.edit_comparison(draft=repeat,title='저장 측정 비교')
        workspace.validate(object_ref=compared['id'])
        workspace.apply(object_ref=compared['id'],show=False)
        rows = workspace.sample(object_ref=compared['id'],preview=False,limit=1000)['rows']
        assert builtins.any(not row['valid'] for row in rows), 'upstream invalid values became valid'
        assert builtins.all(row['delta'] == 0. for row in rows if row['valid'])
        derived.append({'object_ref':compared['id'],'rows':rows,
                        'declaration':workspace._output_declaration(compared['id'])})
    saved=owner.save_project()
    retained=workspace.sample(object_ref=obj['id'],preview=False,limit=1000)
    receipt={'project':str(saved),'object_ref':obj['id'],'rows':retained['rows'],
             'derived':derived, 'solver_execution':'NOT_PERFORMED','broker':'NOT_EXERCISED'}
    with (root/'receipt.json').open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,ensure_ascii=False,allow_nan=False,indent=2)
    print('PASS native owner comparison/save; next use --reopen '+str(root/'receipt.json'))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
