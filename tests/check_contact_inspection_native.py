"""Focused installed-ParaView check of retained contact data; never runs a solver.

Run with pvpython, not pytest. --project performs inspection, creates/saves one
force measurement, then writes a NEW receipt. --reopen-receipt checks it in a
fresh pvpython process. Existing raw results and registered inputs are read only.
"""
import argparse
import json
import os
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(allow_abbrev=False)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--project', type=Path)
    mode.add_argument('--reopen-receipt', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--source', default='result')
    parser.add_argument('--pair')
    parser.add_argument('--frame-index', type=int, default=0)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from apps.desktop_post import external
    from apps.desktop_post.bridge import Owner
    from caelab.post_observation import completed_snapshot
    from paraview import simple as p
    if args.reopen_receipt:
        previous = json.loads(args.reopen_receipt.read_text(encoding='utf-8'))
        project = Path(previous['project'])
    else:
        if args.receipt is None or args.receipt.exists():
            parser.error('--project requires a new --receipt path')
        previous = None
        project = args.project
    document = json.loads(project.read_text(encoding='utf-8-sig'))
    os.environ['CAE_POST_PROJECT'] = str(project.resolve())
    external.restore_workspace(project, document)
    owner = Owner()
    workspace = owner.workspace
    if previous:
        selection = workspace.state['contact_selection']
        assert {k: selection[k] for k in previous['selection']} == previous['selection']
        obj = workspace.object(previous['object_ref'])
        record, bundle = workspace._bundle(obj)
        assert record['recipe'] == previous['recipe']
        page = workspace.sample(object_ref=obj['id'], preview=False, limit=1000)
        assert page['rows'] == previous['rows']
        assert record['summary']['time_units'] == '1'
        assert record['summary']['time_origin'] == 'STATIC_LOAD_PARAMETER'
        assert not workspace.restore_issues, workspace.restore_issues
        print(json.dumps({'status': 'PASS', 'mode': 'cold_reopen', 'rows': len(page['rows']),
                          'solver_execution': 'NOT_PERFORMED'}))
        return 0
    inspected = workspace.dispatch('post.contact_inspect', {
        'source_ref': args.source, 'pair_id': args.pair, 'frame_index': args.frame_index,
        'side': 'both', 'field': 'CPRESS', 'quantity': 'CFN', 'component': 2, 'show': True})
    selection = inspected['selection']
    assert inspected['scope'] == 'shared_nodal_projection' and inspected['active_state'] == 'UNKNOWN'
    assert p.GetAnimationScene().AnimationTime == inspected['static']['load_parameter']
    overlay = workspace.state['contact_selection']['overlay_names']
    assert len(overlay) == 3
    assert all(p.FindSource(name) is not None for name in overlay)
    render_view = next(view for name, view in workspace._views()
                       if name == workspace.state['contact_selection']['view_name'])
    for name in overlay[1:]:
        component = p.FindSource(name).SMProxy.GetProperty('SelectedComponent')
        assert component.GetNumberOfElements() == 1
        assert component.GetElement(0) == 0
        display = p.GetDisplayProperties(p.FindSource(name), render_view)
        assert list(display.ColorArrayName) == ['POINTS', '']
        assert display.Representation == 'Wireframe'
    created = workspace.dispatch('post.contact_measurement', {
        'source_ref': args.source, 'pair_id': selection['pair_id'], 'quantity': 'CFN', 'component': 2})
    object_ref = created['object_ref']
    page = workspace.sample(object_ref=object_ref, preview=False, limit=1000)
    assert [row['values']['CFN_Z_N'] for row in page['rows']] == [row['value'] for row in inspected['history']['rows']]
    assert [row['values']['load_parameter'] for row in page['rows']] == [
        row['static']['load_parameter'] for row in inspected['history']['rows']]
    saved = owner.save_project()
    snapshot = workspace.measurement_snapshot(object_ref=object_ref)
    # Exercise the service-side completed-command decoder with a labelled envelope;
    # this checks saved bytes/pins but is not a broker transport acceptance claim.
    command = {'state': 'SUCCEEDED', 'operation': 'post.measurement_snapshot',
        'command_id': 'Cnativeprobe', 'document_id': owner.document_id, 'session_id': owner.session_id,
        'arguments': {'object_ref': object_ref}, 'outcome': {'state': 'SUCCEEDED', 'result': {
            'status': 'COMPLETED', 'command_id': 'Cnativeprobe', 'document_id': owner.document_id,
            'session_id': owner.session_id, 'result': snapshot}}}
    assert completed_snapshot(command)['rows'] == page['rows']
    result = {'project': str(saved), 'object_ref': object_ref, 'recipe': created['recipe'],
              'selection': selection, 'rows': page['rows'], 'solver_execution': 'NOT_PERFORMED'}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    with args.receipt.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
    print(json.dumps({'status': 'PASS', 'mode': 'native_inspection_and_save',
                      'receipt': str(args.receipt), 'rows': len(page['rows']), 'solver_execution': 'NOT_PERFORMED'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
