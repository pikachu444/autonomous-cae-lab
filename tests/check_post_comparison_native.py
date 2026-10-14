"""Installed pvpython owner preview/apply/save and separate-process reopen.

Never invokes a solver. --create requires a NEW directory. --reopen reads the
saved receipt without regenerating fixtures or revalidating the comparison.
"""
import argparse
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
    saved=owner.save_project()
    retained=workspace.sample(object_ref=obj['id'],preview=False,limit=1000)
    receipt={'project':str(saved),'object_ref':obj['id'],'rows':retained['rows'],
             'solver_execution':'NOT_PERFORMED','broker':'NOT_EXERCISED'}
    with (root/'receipt.json').open('x',encoding='utf-8') as stream:
        json.dump(receipt,stream,ensure_ascii=False,allow_nan=False,indent=2)
    print('PASS native owner comparison/save; next use --reopen '+str(root/'receipt.json'))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
