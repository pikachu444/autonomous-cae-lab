"""Run this with installed Windows ParaView 6.2 pvpython, never Research Python.

Start the normal workbench service with an approved local input root, then run:

  pvpython.exe scripts/check_post_analysis_workflow.py create \
    --service-url http://127.0.0.1:8765 --input-root checks \
    --root-path C:/CAE/approved-checks --case-name post-flow-001 --spawn-reopen

The root path must be the configured path for that input-root ID. Use a fresh
case name. This creates small VTU fixtures, uses real registered receipts and
the existing Post Owner/NativeCommands/HTTP paths, and saves normal PVSM and
project.json revisions. It registers honestly as a HEADLESS native owner; this
does not test QVTK dispatch, human interaction, a solver, or physical validity.

Separate fresh-process modes (also invoked by --spawn-reopen):

  pvpython.exe scripts/check_post_analysis_workflow.py reopen --case-dir ...
  pvpython.exe scripts/check_post_analysis_workflow.py repair --case-dir ...

Repair temporarily moves only this run's newly registered B snapshot, verifies
that missing input is diagnosed, then restores the exact bytes in a finally
block. Replacement content is independently registered through the service.
No existing project, reader, file, root configuration or saved revision is edited.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import itertools
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
import uuid

REPO = Path(__file__).resolve().parents[1]
RESAMPLE_TOLERANCE = 1e-9
ABSOLUTE_ERROR = 1e-10
REFERENCE = {
    'method': 'linear_tetra_b_to_a', 'resample_tolerance': RESAMPLE_TOLERANCE,
    'absolute_value_error': ABSOLUTE_ERROR,
    'b_affine_coefficients': [1.25, 1.0, 2.0, 3.0],
    'ordinary_a_definition': '1 + x + 2*y + 3*z',
    'inside_delta_mm': 0.25, 'outside_b_indexes': [8, 9, 10, 11],
    'original_a_node_id_base': 2**53 + 101,
    'declaration': {'association': 'POINTS', 'array': 'q', 'quantity': 'displacement',
                    'units': 'mm', 'measure': 'scalar_displacement_component', 'frame': 'global_cartesian',
                    'coordinate_units': 'mm', 'coordinate_frame': 'global_cartesian',
                    'time': None, 'time_units': None, 'time_origin': None},
    'scope': 'Synthetic numerical field, real ParaView 6.2 headless owner/service pipeline; no GUI or physical approval',
}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def runtime():
    sys.path.insert(0, str(REPO))
    from paraview import simple as p, servermanager
    from apps.desktop_post import bridge, commands, external, analysis
    from caelab.workbench_client import Client
    version = str(p.GetParaViewVersion())
    if not (version.startswith('6.2') or version == '(6, 2)'):
        raise RuntimeError('This workflow requires the installed ParaView 6.2 API; observed ' + version)
    if p.GetSources():
        raise RuntimeError('Use a fresh pvpython process; existing sources must be preserved')
    return p, servermanager, bridge, commands, external, analysis, Client


def affine(point):
    constant, x, y, z = REFERENCE['b_affine_coefficients']
    return constant + x*point[0] + y*point[1] + z*point[2]


def fixture_geometry():
    cube = [(0.,0.,0.), (1.,0.,0.), (1.,1.,0.), (0.,1.,0.),
            (0.,0.,1.), (1.,0.,1.), (1.,1.,1.), (0.,1.,1.)]
    index = {point: i for i, point in enumerate(cube)}
    b_cells = []
    for order in itertools.permutations(range(3)):
        point, cell = [0.,0.,0.], [index[(0.,0.,0.)]]
        for direction in order:
            point[direction] = 1.
            cell.append(index[tuple(point)])
        b_cells.append(cell)
    a_points = [tuple(.1 + .8*value for value in point) for point in cube]
    a_points += [(1.1,.2,.2), (1.3,.2,.2), (1.1,.4,.2), (1.1,.2,.4)]
    a_cells = [[0,1,3,4], [1,2,3,6], [1,3,4,6], [1,4,5,6], [3,4,6,7], [8,9,10,11]]
    return a_points, a_cells, cube, b_cells


def write_grid(path, points, cells, values, node_base, element_base):
    from vtkmodules.vtkCommonCore import vtkPoints, vtkDoubleArray, vtkTypeInt64Array
    from vtkmodules.vtkCommonDataModel import vtkUnstructuredGrid, vtkTetra
    from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridWriter
    grid, coordinates = vtkUnstructuredGrid(), vtkPoints()
    coordinates.SetDataTypeToDouble()
    for point in points:
        coordinates.InsertNextPoint(*point)
    grid.SetPoints(coordinates)
    for indices in cells:
        cell = vtkTetra()
        for i, point in enumerate(indices):
            cell.GetPointIds().SetId(i, point)
        grid.InsertNextCell(cell.GetCellType(), cell.GetPointIds())
    scalar = vtkDoubleArray()
    scalar.SetName('q')
    for value in values:
        scalar.InsertNextValue(value)
    grid.GetPointData().AddArray(scalar)
    for attributes, name, count, base in ((grid.GetPointData(), 'NativeNodeId', len(points), node_base),
                                         (grid.GetCellData(), 'NativeElementId', len(cells), element_base)):
        identities = vtkTypeInt64Array()
        identities.SetName(name)
        for i in range(count):
            identities.InsertNextValue(base + 13*i)
        attributes.AddArray(identities)
    writer = vtkXMLUnstructuredGridWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(grid)
    writer.SetDataModeToAscii()
    if writer.Write() != 1:
        raise RuntimeError('Actual VTK failed to write fixture ' + str(path))


class ConnectedOwner:
    """Synchronous HEADLESS use of the normal authenticated native protocol.

    Started is acknowledged before the one native call. All proxies remain on
    pvpython's main thread. No timer, GUI identity or background proxy access is
    fabricated to satisfy the service.
    """
    def __init__(self, owner, client, p, transcript):
        self.owner, self.client, self.p, self.transcript = owner, client, p, transcript
        self.host_id = 'H' + uuid.uuid4().hex
        self.identity = None
        receipt = client.request('/api/workbench/hosts/register', {
            'host_id': self.host_id, 'session_id': owner.session_id, 'application': 'paraview',
            'version': str(p.GetParaViewVersion()), 'execution_mode': 'headless',
            'documents': [owner.descriptor()], 'registration_nonce': secrets.token_urlsafe(32)})
        self.identity = {'session_id': owner.session_id, 'host_token': receipt['host_token']}

    def event(self, event, **fields):
        self.owner.refresh()
        receipt = self.client.request('/api/workbench/hosts/' + self.host_id + '/events',
            {**self.identity, 'event': event, **fields, 'documents': [self.owner.descriptor()]})
        if receipt.get('accepted') is not True:
            raise RuntimeError('Service did not acknowledge native event ' + event)

    def call(self, operation, arguments=None, *, failure=False):
        self.event('heartbeat')
        identifier = 'C' + uuid.uuid4().hex
        queued = self.client.document_command(self.owner.document_id, operation, arguments or {},
            session_id=self.owner.session_id, expected_generation=self.owner.generation, command_id=identifier)
        if queued['command_id'] != identifier:
            raise RuntimeError('Service returned a different command identity')
        dispatched = self.client.request('/api/workbench/hosts/' + self.host_id + '/commands/next', self.identity)['command']
        if dispatched is None or dispatched['command_id'] != identifier:
            raise RuntimeError('The exact native command was not dispatched')
        self.event('started', command_id=identifier)
        outcome = self.owner.dispatch(dispatched)
        finished = {'state': 'SUCCEEDED' if outcome['status'] == 'COMPLETED' else 'FAILED', 'result': outcome}
        if outcome.get('error'):
            finished['error'] = outcome['error']
        self.event('finished', command_id=identifier, outcome=finished)
        status = self.client.command_status(identifier)
        if status['state'] != finished['state'] or status['outcome'] != finished:
            raise RuntimeError('Service completion differs from the exact native outcome')
        self.transcript.append({'operation': operation, 'command_id': identifier, 'outcome': outcome})
        if failure:
            if outcome['status'] != 'FAILED':
                raise AssertionError('Expected an explicit refusal for ' + operation)
            return outcome['error']
        if outcome['status'] != 'COMPLETED':
            raise RuntimeError(operation + ': ' + str(outcome.get('error')))
        return outcome['result']

    def close(self):
        if self.identity is not None:
            self.event('closed')
            self.identity = None


def recipe(a_ref, b_ref, method='linear_tetra_b_to_a', tolerance=RESAMPLE_TOLERANCE):
    return {'method': method, 'tolerance': tolerance,
            'a': {**REFERENCE['declaration'], 'source_ref': a_ref},
            'b': {**REFERENCE['declaration'], 'source_ref': b_ref}}


def assert_close(actual, expected, description):
    if expected is None:
        if actual is not None:
            raise AssertionError(description + ': undefined value must stay JSON null')
    elif actual is None or not math.isfinite(actual) or abs(actual-expected) > ABSOLUTE_ERROR:
        raise AssertionError(description + ': expected ' + str(expected) + ', observed ' + str(actual))


def check_rows(page, *, same_mesh=False):
    a_points, _, _, _ = fixture_geometry()
    if page['points'] != len(a_points) or len(page['rows']) != len(a_points):
        raise AssertionError('Bounded native page does not cover the exact original A points')
    for row in page['rows']:
        index = row['point_index']
        if row['coordinates'] != list(a_points[index]):
            raise AssertionError('A original ordered coordinates changed')
        if row['original_a_ids'] != {'NativeNodeId': REFERENCE['original_a_node_id_base'] + 13*index}:
            raise AssertionError('Original A int64 IDs changed or B IDs were interpolated')
        source_a = 1. + a_points[index][0] + 2.*a_points[index][1] + 3.*a_points[index][2]
        inside = same_mesh or index < 8
        valid = inside and source_a is not None
        expected_b = affine(a_points[index]) if inside else None
        delta = expected_b-source_a if valid else None
        percent = 100.*delta/abs(source_a) if valid and source_a != 0 else None
        reason = 'outside_b_domain' if not inside else 'nonfinite_a' if source_a is None else 'valid'
        assert_close(row['a'], source_a, 'A source value at ' + str(index))
        for name, expected in (('b',expected_b), ('delta',delta), ('percent',percent)):
            assert_close(row[name], expected, name + ' at ' + str(index))
        if row['valid'] != valid or row['validity_reason'] != reason or row['percent_valid'] != (percent is not None):
            raise AssertionError('Native validity/undefined reason mismatch at ' + str(index))
        expected_percent_reason = 'zero_a' if valid and source_a == 0 else reason
        if row['percent_reason'] != expected_percent_reason:
            raise AssertionError('Percent denominator/invalid reason mismatch')


def check_summary(summary, *, same_mesh=False):
    expected = {'valid':12 if same_mesh else 8, 'outside_b_domain':0 if same_mesh else 4,
                'nonfinite_a':0, 'nonfinite_b':0, 'nonfinite_difference':0}
    if summary['validity_counts'] != expected or summary['percent_zero_a'] != 0:
        raise AssertionError('Native summary validity counts differ from the predeclared original points')
    expected_finite = {'a':12, 'b':12 if same_mesh else 8, 'delta':12 if same_mesh else 8,
                       'percent':12 if same_mesh else 8}
    for key, count in expected_finite.items():
        if summary['finitecounts'][key]['finite'] != count or summary['finitecounts'][key]['nonfinite'] != 12-count:
            raise AssertionError('Native finite/undefined counts differ for ' + key)


def native_id_check(owner, object_ref, servermanager):
    obj = owner.workspace.object(object_ref)
    record = owner.workspace.applied(obj)
    bundle = owner.workspace.bundles[record['id']]
    data = servermanager.Fetch(bundle['source'])
    identities = data.GetCellData().GetArray('NativeElementId')
    if identities is None or any(int(identities.GetVariantValue(i).ToLongLong()) != 2**53+401+13*i for i in range(data.GetNumberOfCells())):
        raise AssertionError('Output cell IDs are not the original A IDs')
    return record


def register(client, root_id, root_path, path):
    relative = path.relative_to(root_path).as_posix()
    result = client.register_local_input(root_id, relative)
    receipt = client.native_input(result['id'])
    from apps.desktop_post.commands import sha
    if receipt['format'] != 'vtu' or sha(receipt['path']) != sha(path):
        raise AssertionError('Registered native snapshot differs from the generated original fixture')
    return receipt


def create(args, modules):
    p, servermanager, bridge, commands, external, analysis, Client = modules
    root_path = args.root_path.resolve(strict=True)
    if not args.case_name or Path(args.case_name).name != args.case_name or args.case_name in ('.','..'):
        raise ValueError('Use a fresh plain case name')
    case = root_path / args.case_name
    case.mkdir(exist_ok=False)
    source_dir = case / 'inputs'
    source_dir.mkdir()
    write_json(case / 'reference.json', REFERENCE)  # Fixed before any native comparison.
    a_points, a_cells, b_points, b_cells = fixture_geometry()
    values_a = [1. + point[0] + 2.*point[1] + 3.*point[2] for point in a_points]
    for name, points, cells, values, node_base, element_base in (
        ('A.vtu',a_points,a_cells,values_a,REFERENCE['original_a_node_id_base'],2**53+401),
        ('B.vtu',b_points,b_cells,[affine(point) for point in b_points],2**53+10001,2**53+10401),
        ('C.vtu',a_points,a_cells,[affine(point) for point in a_points],2**53+20001,2**53+20401)):
        write_grid(source_dir/name, points, cells, values, node_base, element_base)
    client = Client(args.service_url)
    if args.input_root not in {row['id'] for row in client.local_roots()['roots']}:
        raise ValueError('Select an existing operator-approved service input root')
    receipts = {name:register(client,args.input_root,root_path,source_dir/(name+'.vtu')) for name in ('A','B','C')}
    project = external.open_registered(receipts['A']['id'],case/'project',args.service_url)
    os.environ['CAE_POST_PROJECT'] = str(project)
    owner = bridge.Owner()
    commands.set_save_owner(owner)
    transcript = []
    connection = ConnectedOwner(owner,client,p,transcript)
    record = {'reference':REFERENCE,'service_url':args.service_url,'input_root':args.input_root,
              'root_path':str(root_path),'case_dir':str(case),'creation_pid':os.getpid(),
              'runtime':str(p.GetParaViewVersion()),'execution_mode':'headless','commands':transcript,
              'receipt_ids':{name:receipt['id'] for name,receipt in receipts.items()}}
    try:
        a_ref = 'result'
        active, view, clock = p.GetActiveSource(), p.GetActiveView(), float(p.GetAnimationScene().AnimationTime)
        b_ref = connection.call('post.source_add',{'input_id':receipts['B']['id'],'label_text':'Affine B cube, six linear tetra'})['source_ref']
        c_ref = connection.call('post.source_add',{'input_id':receipts['C']['id'],'label_text':'Same ordered A mesh, independent IDs'})['source_ref']
        if p.GetActiveSource() != active or p.GetActiveView() != view:
            raise AssertionError('Add result changed the preexisting native active source/view')
        main_recipe = recipe(a_ref,b_ref)
        obj = connection.call('post.comparison_edit',{'draft':main_recipe,'title':'Affine B onto shifted A'})['id']
        layouts, views = len(p.GetLayouts()), len(p.GetViews())
        preview = connection.call('post.mapping_validate',{'object_ref':obj})
        check_summary(preview['summary'])
        if (p.GetActiveSource() != active or p.GetActiveView() != view or len(p.GetLayouts()) != layouts
                or len(p.GetViews()) != views or float(p.GetAnimationScene().AnimationTime) != clock):
            raise AssertionError('Preview leaked native source/view/layout/clock changes')
        check_rows(connection.call('post.sample',{'object_ref':obj,'preview':True,'limit':100}))
        pick = connection.call('post.sample',{'object_ref':obj,'preview':True,'point_index':3})
        assert_close(pick['rows'][0]['delta'], .25, 'Independent affine offset at the selected point')
        assert_close(pick['rows'][0]['percent'], 100.*.25/abs(pick['rows'][0]['a']),
                     'Independent affine percent change at the selected point')
        changed = recipe(a_ref,b_ref,tolerance=2*RESAMPLE_TOLERANCE)
        connection.call('post.comparison_edit',{'object_ref':obj,'draft':changed})
        connection.call('post.apply',{'object_ref':obj,'show':False},failure=True)
        if owner.workspace.object(obj)['history']:
            raise AssertionError('Stale settings published an applied history revision')
        connection.call('post.comparison_edit',{'object_ref':obj,'draft':main_recipe})
        connection.call('post.mapping_validate',{'object_ref':obj})
        reader = owner.workspace.resolve(a_ref)
        arrays = list(reader.PointArrayStatus)
        try:
            reader.PointArrayStatus = [name for name in arrays if name != 'q']
            reader.UpdatePipeline()
            connection.call('post.apply',{'object_ref':obj,'show':False},failure=True)
            if owner.workspace.object(obj)['history']:
                raise AssertionError('Changed source published an old preview')
        finally:
            reader.PointArrayStatus = arrays
            reader.UpdatePipeline()
        connection.call('post.mapping_validate',{'object_ref':obj})
        first = connection.call('post.apply',{'object_ref':obj,'show':True})
        check_rows(connection.call('post.sample',{'object_ref':obj,'preview':False,'limit':100}))
        native_id_check(owner,obj,servermanager)
        connection.call('post.undo',{'object_ref':obj})
        if owner.workspace.applied(owner.workspace.object(obj)) is not None:
            raise AssertionError('Undo did not return to the unapplied state')
        connection.call('post.mapping_validate',{'object_ref':obj})
        reapplied = connection.call('post.apply',{'object_ref':obj,'show':True})
        if reapplied['id'] == first['id'] or len(owner.workspace.object(obj)['history']) != 2:
            raise AssertionError('Reapply did not preserve the earlier actual revision')
        same = connection.call('post.comparison_edit',{'draft':recipe(a_ref,c_ref,'same_mesh'),'title':'Exact ordered same mesh, different IDs'})['id']
        same_preview = connection.call('post.mapping_validate',{'object_ref':same})
        check_summary(same_preview['summary'],same_mesh=True)
        check_rows(connection.call('post.sample',{'object_ref':same,'preview':True,'limit':100}),same_mesh=True)
        connection.call('post.apply',{'object_ref':same,'show':False})
        mismatch = connection.call('post.comparison_edit',{'draft':recipe(a_ref,b_ref,'same_mesh'),'title':'Must refuse different ordered mesh'})['id']
        connection.call('post.mapping_validate',{'object_ref':mismatch},failure=True)
        # Keep the intended applied comparison and exact original output pick active.
        connection.call('post.comparison_edit',{'object_ref':obj,'draft':main_recipe})
        connection.call('post.sample',{'object_ref':obj,'preview':False,'point_index':3})
        saved = connection.call('document.save')['project']
        final = native_id_check(owner,obj,servermanager)
        record.update(project=saved,main_object=obj,same_object=same,b_source_ref=b_ref,
                      main_revision=final['id'],output_hash=final['summary']['output_hash'],
                      mesh_hash=final['summary']['mesh_hash'],finitecounts=final['summary']['finitecounts'],
                      selected_point_index=3,outcome='CREATED_NATIVE_OWNER_WORKFLOW')
        write_json(case/'run.json',record)
    finally:
        connection.close()
        commands.clear_save_owner(owner)
        write_json(case/'commands-create.json',transcript)
    print('CREATED ' + str(case/'run.json'),flush=True)
    if args.spawn_reopen:
        for mode in ('reopen','repair'):
            process = subprocess.run([sys.executable,str(Path(__file__).resolve()),mode,'--case-dir',str(case)],
                                     capture_output=True,text=True,timeout=180)
            (case/(mode+'-stdout.txt')).write_text(process.stdout,encoding='utf-8')
            (case/(mode+'-stderr.txt')).write_text(process.stderr,encoding='utf-8')
            if process.returncode:
                raise RuntimeError('Fresh-process ' + mode + ' failed; inspect ' + str(case/(mode+'-stderr.txt')))
            print(process.stdout,flush=True)


def reopen(args, modules, *, repair=False):
    p, servermanager, bridge, commands, external, analysis, Client = modules
    case = args.case_dir.resolve(strict=True)
    record = json.loads((case/'run.json').read_text(encoding='utf-8'))
    if record['reference'] != REFERENCE or os.getpid() == record['creation_pid']:
        raise AssertionError('Reopen requires the exact predeclared reference in a separate process')
    project = Path(record['project']).resolve(strict=True)
    document = json.loads(project.read_text(encoding='utf-8'))
    client = Client(record['service_url'])
    hidden = original = None
    connection = owner = None
    transcript = []
    try:
        replacement = None
        if repair:
            original = Path(document['sources'][record['b_source_ref']]['entry_path'])
            fresh_receipt = client.native_input(record['receipt_ids']['B'])
            if Path(fresh_receipt['path']) != original or external.sha(original) != document['sources'][record['b_source_ref']]['source_pins'][0]['sha256']:
                raise AssertionError('Repair may move only this run\'s exact newly registered B snapshot')
            relocated = case/'relocated'
            relocated.mkdir(exist_ok=True)
            target = relocated/'B.vtu'
            if target.exists():
                raise FileExistsError('Preserve the prior repair run; use a fresh created case')
            target.write_bytes(original.read_bytes())
            replacement = register(client,record['input_root'],Path(record['root_path']),target)
            hidden = original.with_name(original.name+'.post-check-hidden-'+uuid.uuid4().hex)
            original.rename(hidden)
        restored = external.restore_workspace(project,document,allow_repair=repair)
        if repair and (not isinstance(restored,dict) or restored.get('state') != 'SOURCE_REPAIR_REQUIRED'):
            raise AssertionError('Missing exact source was silently loaded or ignored')
        os.environ['CAE_POST_PROJECT'] = str(project)
        owner = bridge.Owner()
        commands.set_save_owner(owner)
        connection = ConnectedOwner(owner,client,p,transcript)
        if repair:
            result = connection.call('post.source_repair',{'source_ref':record['b_source_ref'],'input_id':replacement['id']})
            if result.get('content_changed') is not False or result.get('workspace_loaded') is not True or result.get('remaining'):
                raise AssertionError('Exact-content repair did not restore the existing saved native graph')
        if owner.workspace.restore_issues:
            raise AssertionError('Saved native analyses/selection did not restore: ' + str(owner.workspace.restore_issues))
        page = connection.call('post.sample',{'object_ref':record['main_object'],'preview':False,'limit':100})
        check_rows(page)
        actual = native_id_check(owner,record['main_object'],servermanager)
        for key in ('output_hash','mesh_hash','finitecounts'):
            if actual['summary'][key] != record[key]:
                raise AssertionError('Reopen changed retained ' + key)
        fingerprint = analysis.output_fingerprint(owner.workspace.bundles[actual['id']])
        if any(fingerprint[key] != record[key] for key in fingerprint):
            raise AssertionError('Actual native Fetch after reopen differs from retained output hashes/counts')
        check_rows(connection.call('post.sample',{'object_ref':record['same_object'],'preview':False,'limit':100}),same_mesh=True)
        obj = owner.workspace.object(record['main_object'])
        if obj.get('selection_revision') != actual['id'] or obj.get('selection',[{}])[0].get('point_index') != record['selected_point_index']:
            raise AssertionError('Saved exact output selection identity was not retained')
        if repair:
            repaired_project = connection.call('document.save')['project']
        else:
            repaired_project = None
        receipt = {'mode':'repair' if repair else 'reopen','pid':os.getpid(),'creation_pid':record['creation_pid'],
                   'runtime':str(p.GetParaViewVersion()),'execution_mode':'headless',
                   'project':str(project),'repaired_project':repaired_project,
                   'outcome':'PASSED_ACTUAL_NATIVE_OWNER_WORKFLOW','scope':REFERENCE['scope'],
                   'output_hash':fingerprint['output_hash'],'mesh_hash':fingerprint['mesh_hash'],'commands':transcript}
        write_json(case/('repair-check.json' if repair else 'reopen-check.json'),receipt)
        print(json.dumps({key:receipt[key] for key in ('mode','pid','outcome','scope')},ensure_ascii=False),flush=True)
    finally:
        try:
            if connection is not None:
                connection.close()
        finally:
            if owner is not None:
                commands.clear_save_owner(owner)
            try:
                if hidden is not None and hidden.exists():
                    if original.exists():
                        raise RuntimeError('Original generated snapshot path became occupied; hidden exact content is preserved at ' + str(hidden))
                    hidden.rename(original)
            finally:
                write_json(case/('commands-repair.json' if repair else 'commands-reopen.json'),transcript)


def main():
    parser = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode',choices=('create','reopen','repair'))
    parser.add_argument('--service-url')
    parser.add_argument('--input-root')
    parser.add_argument('--root-path',type=Path)
    parser.add_argument('--case-name')
    parser.add_argument('--case-dir',type=Path)
    parser.add_argument('--spawn-reopen',action='store_true')
    args = parser.parse_args()
    if args.mode == 'create' and not all((args.service_url,args.input_root,args.root_path,args.case_name)):
        parser.error('create requires --service-url, --input-root, --root-path and --case-name')
    if args.mode != 'create' and args.case_dir is None:
        parser.error('reopen/repair require --case-dir from the completed create mode')
    modules = runtime()
    if args.mode == 'create':
        create(args,modules)
    else:
        reopen(args,modules,repair=args.mode == 'repair')


if __name__ == '__main__':
    main()
