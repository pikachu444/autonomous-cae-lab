"""Synthetic saved Post example. Run under scripts/native_check.py's Job Object.

Each native phase is a fresh installed pvpython process. No solver, service,
provider, plugin build or new analysis execution occurs during a cold open.
"""
from copy import deepcopy
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
import uuid

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def tracked_open(operation):
    """Count actual product Apply and Python process/network effects on reopen."""
    from apps.desktop_post.workspace import Workspace
    effects = {'post_apply_calls': 0, 'python_process_launches': 0, 'python_network_connects': 0}
    enabled = [True]
    def audit(event, arguments):
        if enabled[0] and event in ('subprocess.Popen', 'os.system'):
            effects['python_process_launches'] += 1
        if enabled[0] and event == 'socket.connect': effects['python_network_connects'] += 1
    sys.addaudithook(audit)
    apply = Workspace.apply
    def counted_apply(self, *args, **kwargs):
        effects['post_apply_calls'] += 1
        return apply(self, *args, **kwargs)
    Workspace.apply = counted_apply
    try:
        opened = operation()
        assert not any(effects.values()), effects
        return opened, effects
    finally:
        Workspace.apply = apply; enabled[0] = False


def grid(path, value):
    from vtkmodules.vtkCommonCore import vtkPoints, vtkDoubleArray
    from vtkmodules.vtkCommonDataModel import vtkUnstructuredGrid, vtkTetra
    from vtkmodules.vtkIOXML import vtkXMLUnstructuredGridWriter
    data = vtkUnstructuredGrid(); points = vtkPoints()
    for point in [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]: points.InsertNextPoint(*point)
    data.SetPoints(points); cell = vtkTetra()
    for index in range(4): cell.GetPointIds().SetId(index, index)
    data.InsertNextCell(cell.GetCellType(), cell.GetPointIds())
    u = vtkDoubleArray(); u.SetName('U'); u.SetNumberOfComponents(3)
    q = vtkDoubleArray(); q.SetName('q')
    for index in range(4): u.InsertNextTuple3(value, index / 100, 0); q.InsertNextValue(value + index)
    data.GetPointData().AddArray(u); data.GetPointData().AddArray(q)
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = vtkXMLUnstructuredGridWriter(); writer.SetFileName(str(path)); writer.SetInputData(data)
    writer.SetDataModeToAppended(); writer.EncodeAppendedDataOff()
    assert writer.Write() == 1


def register(workspace, project, roots):
    from caelab.native_project_inputs import NativeOnlyContext, register_saved
    context = NativeOnlyContext(workspace, approved_roots=roots)
    root_id = next(key for key, root in roots.items() if project.is_relative_to(root))
    registered = register_saved(context, {'mode': 'selected_file', 'native_kind': 'post',
        'root_id': root_id, 'relative': project.relative_to(roots[root_id]).as_posix()}, command_id='C' + uuid.uuid4().hex)
    write_json(workspace / 'reference.json', registered['reference'])
    return registered


def create(root):
    from paraview import simple as p
    from apps.desktop_post import external, bridge, commands, analysis
    source = root / 'original'; source.mkdir(parents=True)
    grid(source / 'A' / 'frame0.vtu', .1); grid(source / 'A' / 'frame1.vtu', .2)
    grid(source / 'B' / 'frame0.vtu', 2.)
    pvd = source / 'A' / 'series.pvd'
    pvd.write_text('<VTKFile type="Collection"><Collection><DataSet timestep="0" group="A" part="0" file="frame0.vtu"/>'
        '<DataSet timestep="1" group="A" part="0" file="frame1.vtu"/></Collection></VTKFile>')
    project = external.open_result(pvd, source / 'project')
    owner = bridge.Owner(); commands.set_save_owner(owner)
    b, record = external.admit_result(source / 'B' / 'frame0.vtu')
    owner.project_document['sources']['B'] = record
    # Native product filter A is applied once in setup, then its saved values
    # are reopened by the existing retained-reader recovery before B uses them.
    draft = {'source_ref': 'B', 'filter': 'WarpByVector',
             'settings': {'association': 'POINTS', 'array': 'U', 'scale_factor': .1}}
    a = owner.workspace.edit_filter(draft=draft, title='보존한 변형')
    ref_a = a['id'] if 'id' in a else a['object_ref']
    owner.workspace.validate(object_ref=ref_a); owner.workspace.apply(object_ref=ref_a, show=False)
    owner.save_project()
    for proxy in reversed(owner.workspace.bundles[owner.workspace.applied(owner.workspace.object(ref_a))['id']]['proxies']): p.Delete(proxy)
    owner.close(); commands.clear_save_owner(owner)
    owner = bridge.Owner(); commands.set_save_owner(owner)
    assert owner.workspace.bundles[owner.workspace.applied(owner.workspace.object(ref_a))['id']]['retained_only']
    draft_b = {**draft, 'source_ref': ref_a, 'settings': {**draft['settings'], 'scale_factor': .2}}
    result = owner.workspace.edit_filter(draft=draft_b, title='보존값에서 이어 변형')
    ref_b = result['id'] if 'id' in result else result['object_ref']
    owner.workspace.validate(object_ref=ref_b); owner.workspace.apply(object_ref=ref_b, show=False)
    original = p.FindSource(owner.project_document['sources']['result']['reader_name'])
    external.select_array(original, 'POINTS', 'q', time=1)
    view = p.GetActiveView(); view.CameraPosition = [4., 3., 2.]; view.CameraFocalPoint = [.4, .3, .2]
    project = owner.save_project()
    before = {'project': str(project), 'analysis_a': ref_a, 'analysis_b': ref_b, 'time': float(p.GetAnimationScene().AnimationTime),
              'camera': list(view.CameraPosition), 'camera_focal': list(view.CameraFocalPoint),
              'source_name': p.GetActiveSource().GetXMLLabel(), 'scope': 'SYNTHETIC; physical qualification UNKNOWN'}
    write_json(root / 'expected.json', before)
    register(root / 'registration', project, {'original': source})
    owner.close(); commands.clear_save_owner(owner)


def cold(root, copy_name, edit):
    from paraview import simple as p
    from apps.desktop_post import portable_project, commands, external
    from caelab.native_project_inputs import NativeOnlyContext, verify_registered
    from caelab.portable_project_native import prepare_open
    workspace = root / copy_name
    context = NativeOnlyContext(workspace, approved_roots={'copy': workspace})
    reference = json.loads((workspace / 'reference.json').read_text())
    expected = json.loads((root / 'expected.json').read_text(encoding='utf-8'))
    ticket = prepare_open(context, {'reference': reference, 'intent': 'saved', 'target_id': None,
        'expected_head': None, 'selection': None, 'allow_partial': False}, command_id='C' + uuid.uuid4().hex)
    result, open_effects = tracked_open(lambda: portable_project.restore_bound_project(ticket.verified_input, ticket.binding))
    assert result['status'] == 'OPENED', result
    owner = result['owner']; work = owner.workspace
    assert float(p.GetAnimationScene().AnimationTime) == expected['time']
    assert list(p.GetActiveView().CameraPosition) == expected['camera']
    assert list(p.GetActiveView().CameraFocalPoint) == expected['camera_focal']
    for row in work.describe()['objects']:
        assert not row.get('current_inputs_differ'), row
    # Upstream retained reader A and its consumer B must both verify on new paths.
    for ref in (expected['analysis_a'], expected['analysis_b']):
        work._bundle(work.object(ref))
    if edit:
        obj = work.object(expected['analysis_b'])
        draft = deepcopy(obj['draft']); draft['settings']['scale_factor'] = .3
        work.edit_filter(draft=draft, object_ref=obj['id'])
        work.validate(object_ref=obj['id']); work.apply(object_ref=obj['id'], show=False)
        work.undo(object_ref=obj['id']); work.redo(object_ref=obj['id'])
        project = owner.save_project()
        assert work.object(obj['id'])['draft']['settings']['scale_factor'] == .3
        expected['camera'] = list(p.GetActiveView().CameraPosition)
        expected['camera_focal'] = list(p.GetActiveView().CameraFocalPoint)
        expected['time'] = float(p.GetAnimationScene().AnimationTime)
        write_json(root / 'expected.json', expected)
        register(workspace, project, {'copy': workspace})
    else:
        assert work.object(expected['analysis_b'])['draft']['settings']['scale_factor'] == .3
    write_json(root / (copy_name + '-readback.json'), {'status': result['status'],
        'project': result['project_path'], 'sources': [str(path) for source in p.GetSources().values()
            for path in external.reader_input_files(source)], 'objects': work.describe()['objects'],
        'time': float(p.GetAnimationScene().AnimationTime), 'camera': list(p.GetActiveView().CameraPosition),
        'open_effects': open_effects,
        'execution_scope': 'Standalone native context; rendering and reader/filter pipeline evaluation occur. No service, provider or solver command is issued.'})
    owner.close(); commands.clear_save_owner(owner)


def partial_repair(root):
    from paraview import simple as p
    from apps.desktop_post import portable_project, commands, external
    from caelab.native_inputs import register_native_input
    from caelab.native_project_inputs import NativeOnlyContext, verify_registered
    from caelab.portable_project_native import prepare_open
    original = root / 'original'
    project = Path(json.loads((root / 'expected.json').read_text(encoding='utf-8'))['project'])
    missing = original / 'B' / 'frame0.vtu'; held = missing.with_suffix('.unavailable')
    missing.rename(held)
    owner = None
    try:
        workspace = root / 'partial'
        registered = register(workspace, project, {'original': original})
        context = NativeOnlyContext(workspace, approved_roots={'partial': workspace, 'original': original})
        verified = verify_registered(context, registered['reference'])
        assert verified.snapshot['validation']['closure'] == 'DECLARED_PARTIAL'
        ticket = prepare_open(context, {'reference': registered['reference'], 'intent': 'saved', 'target_id': None,
            'expected_head': None, 'selection': None, 'allow_partial': True}, command_id='C' + uuid.uuid4().hex)
        opened = portable_project.restore_bound_project(ticket.verified_input, ticket.binding, allow_partial=True)
        assert opened['status'] == 'PARTIAL_OPEN', opened
        owner = opened['owner']
        a = owner.project_document['sources']['result']
        assert p.FindSource(a['reader_name']) is not None and p.FindSource(owner.project_document['sources']['B']['reader_name']) is None
        replacement = workspace / 'replacement' / 'frame0.vtu'; replacement.parent.mkdir(parents=True)
        shutil.copyfile(held, replacement)
        receipt = register_native_input(context.root, replacement.parent, replacement, 'D' + uuid.uuid4().hex,
            root_id='partial', relative=replacement.name, limit=2*1024**3)
        # Use the existing registered receipt projection, not a fabricated locator.
        from caelab.native_post_dependencies import file_pin
        def registered_paths(receipt):
            pins = []
            for item in receipt['files']:
                path = context.root / item['file']
                pin = file_pin(path)
                assert all(pin[key] == item[key] for key in ('bytes', 'sha256'))
                pins.append(pin)
            return {**receipt, 'path': str(context.root / receipt['file']), 'source_pins': pins}
        actual = registered_paths(receipt)
        offer = portable_project.saved_offer(owner)
        plan = portable_project.preview_repair(owner, [{'source_ref': 'B', 'input_id': actual['id'], 'receipt': actual}], expected_stamp=offer['stamp'])
        repaired = portable_project.apply_repair(owner, plan, expected_stamp=offer['stamp'], command_id='C' + uuid.uuid4().hex)
        assert repaired['content_changed'] is False
        assert p.FindSource(owner.project_document['sources']['B']['reader_name']) is not None
        changed = workspace / 'changed' / 'frame0.vtu'; grid(changed, 99.)
        changed_receipt = register_native_input(context.root, changed.parent, changed, 'D' + uuid.uuid4().hex,
            root_id='partial', relative=changed.name, limit=2*1024**3)
        changed_actual = registered_paths(changed_receipt)
        try:
            portable_project.preview_repair(owner, [{'source_ref': 'B', 'input_id': changed_actual['id'], 'receipt': changed_actual}],
                expected_stamp=portable_project.saved_offer(owner)['stamp'])
        except ValueError as error:
            assert 'CONTENT_CHANGED' in str(error)
        else:
            raise AssertionError('Changed physical data was accepted as location repair')
        write_json(root / 'partial-readback.json', {'status': 'PARTIAL_OPEN_REPAIRED', 'healthy_a_retained': True,
            'identical_bytes_repair': repaired, 'changed_bytes': 'CONTENT_CHANGED',
            'execution_scope': 'Existing source admission and location repair only; no solver command is issued.'})
    finally:
        if owner is not None: owner.close(); commands.clear_save_owner(owner)
        if held.exists(): held.rename(missing)


def exact_selection(root):
    import xml.etree.ElementTree as ET
    from paraview import simple as p
    from apps.desktop_post import portable_project, commands
    from caelab.native_project_inputs import NativeOnlyContext
    from caelab.portable_project_native import prepare_open, verify_opened, _native_open_readback
    workspace = root / 'copy2'
    context = NativeOnlyContext(workspace, approved_roots={'copy': workspace})
    reference = json.loads((workspace / 'reference.json').read_text())
    ticket = prepare_open(context, {'reference': reference, 'intent': 'saved', 'target_id': None,
        'expected_head': None, 'selection': None, 'allow_partial': False}, command_id='C' + uuid.uuid4().hex)
    opened = portable_project.restore_bound_project(ticket.verified_input, ticket.binding)
    owner = opened['owner']
    try:
        snapshot = ticket.verified_input.snapshot
        member = next(edge['child_member'] for edge in snapshot['edges'] if edge['locator'] == {'codec': 'post_manifest_v1', 'field': 'workspace_file'})
        xml = ET.parse(ticket.verified_input.member_paths[member]).getroot().find('ServerManagerState')
        source_name = owner.project_document['sources']['result']['reader_name']
        source_id = next(item.get('id') for item in xml.findall("ProxyCollection[@name='sources']/Item") if item.get('name') == source_name)
        view_name = owner.project_document['active_selection']['view_name']
        view_id = next(item.get('id') for item in xml.findall("ProxyCollection[@name='views']/Item") if item.get('name') == view_name)
        selected = {'version': 1, 'native_kind': 'post', 'snapshot_sha256': snapshot['snapshot_sha256'], 'selection': {
            'source': {'registration_name': source_name, 'proxy_type': 'PVDReader', 'saved_proxy_id': source_id, 'output_port': 0},
            'view': {'registration_name': view_name, 'view_type': 'RenderView', 'saved_proxy_id': view_id},
            'association': 'POINTS', 'array_name': 'q', 'component': {'mode': 'scalar', 'index': None},
            'time': {'value': 1., 'data_time_value': 1., 'frame_index': 1}, 'block': None, 'analysis': None}}
        readback = portable_project.select_bound_target(owner, selected, verified_input=ticket.verified_input, binding=ticket.binding)
        assert readback['selection_status'] == 'SELECTED'
        bad = deepcopy(selected); bad['selection']['time']['value'] = 99.
        before = float(p.GetAnimationScene().AnimationTime)
        try:
            portable_project.select_bound_target(owner, bad, verified_input=ticket.verified_input, binding=ticket.binding)
        except ValueError as error: assert 'SELECTION_UNAVAILABLE' in str(error)
        else: raise AssertionError('Unavailable exact time was accepted')
        assert float(p.GetAnimationScene().AnimationTime) == before
        verified_readback = verify_opened(context, ticket.binding.open_id, _native_open_readback({**opened['readback'].payload, **readback}))
        write_json(root / 'selection-readback.json', verified_readback)
    finally:
        owner.close(); commands.clear_save_owner(owner)


def adopt_raw(root):
    from paraview import simple as p
    from apps.desktop_post import portable_project, commands
    from caelab.native_project_inputs import NativeOnlyContext, register_saved, verify_registered
    from caelab.portable_project_native import prepare_open
    from caelab.native_post_dependencies import file_pin
    expected = json.loads((root / 'expected.json').read_text(encoding='utf-8'))
    project = Path(expected['project']); document = json.loads(project.read_text(encoding='utf-8'))
    raw = project.parent / document['workspace_file']; original_pin = file_pin(raw)
    workspace = root / 'adopt'
    registered = register(workspace, raw, {'original': root / 'original'})
    context = NativeOnlyContext(workspace, approved_roots={'copy': workspace})
    ticket = prepare_open(context, {'reference': registered['reference'], 'intent': 'saved', 'target_id': None,
        'expected_head': None, 'selection': None, 'allow_partial': False}, command_id='C' + uuid.uuid4().hex)
    assert ticket.status == 'ADOPTION_REQUIRED' and not p.GetSources()
    witness = portable_project.adopt_pvsm(ticket.verified_input, ticket.binding, expected_empty_session=True)
    assert witness.publication_complete and file_pin(raw) == original_pin
    saved = json.loads(witness.saved_file.read_text(encoding='utf-8'))
    assert file_pin(saved['native_import']['state_pin']['path'])['sha256'] == original_pin['sha256']
    native = register_saved(context, witness, command_id='C' + uuid.uuid4().hex)
    verified = verify_registered(context, native['reference'])
    assert verified.snapshot['format'] == 'post-project' and verified.snapshot['validation']['closure'] == 'COMPLETE'
    import xml.etree.ElementTree as ET
    expected_names = [item.get('name') for item in ET.parse(raw).getroot().findall(".//ProxyCollection[@name='sources']/Item")]
    assert sorted(name for name, _ in p.GetSources()) == sorted(expected_names)
    write_json(root / 'adopt-readback.json', {'status': 'ADOPTED_MANAGED_SAVE', 'raw_sha256': original_pin['sha256'],
        'managed_reference': native['reference'], 'native_readers': saved['native_readers'], 'duplicate_readers': 0})


def polydata_capability(root, create):
    from paraview import simple as p
    from vtkmodules.vtkCommonCore import vtkPoints, vtkDoubleArray
    from vtkmodules.vtkCommonDataModel import vtkPolyData, vtkCellArray
    from vtkmodules.vtkIOXML import vtkXMLPolyDataWriter
    folder = root / 'polydata-capability'
    if create:
        folder.mkdir(); points = vtkPoints()
        for point in ((0, 0, 0), (1, 0, 0), (0, 1, 0)): points.InsertNextPoint(*point)
        polygons = vtkCellArray(); polygons.InsertNextCell(3)
        for index in range(3): polygons.InsertCellPoint(index)
        data = vtkPolyData(); data.SetPoints(points); data.SetPolys(polygons)
        values = vtkDoubleArray(); values.SetName('q')
        for value in (2., 4., 6.): values.InsertNextValue(value)
        data.GetPointData().AddArray(values)
        writer = vtkXMLPolyDataWriter(); writer.SetFileName(str(folder / 'triangle.vtp')); writer.SetInputData(data)
        writer.SetDataModeToAppended(); writer.EncodeAppendedDataOff(); assert writer.Write() == 1
        source = p.XMLPolyDataReader(registrationName='Polydata capability', FileName=[str(folder / 'triangle.vtp')])
        source.UpdatePipeline(); p.SaveState(str(folder / 'state.pvsm'))
    else:
        p.LoadState(str(folder / 'state.pvsm')); source = p.FindSource('Polydata capability'); source.UpdatePipeline()
    assert source.GetXMLName() == 'XMLPolyDataReader'
    assert list(source.FileName) == [str(folder / 'triangle.vtp')]
    assert source.GetDataInformation().GetNumberOfPoints() == 3
    assert tuple(source.PointData['q'].GetRange()) == (2., 6.)
    write_json(folder / ('source.json' if create else 'target.json'), {'reader_type': source.GetXMLName(),
        'property': 'FileName', 'slots': list(source.FileName), 'q_range': list(source.PointData['q'].GetRange()),
        'points': 3, 'status': 'NATIVE_READBACK'})


def transaction_cold(root, edit):
    from paraview import simple as p
    from apps.desktop_post import portable_project, commands
    from caelab import portable_project as portable
    from caelab.portable_project_native import prepare_open, verify_opened
    from caelab.native_project_inputs import publish_head, prepare_target_save
    workspace = root / ('transaction1' if edit else 'transaction2')
    context = portable.open_project(workspace)
    manifest = portable.verify_project(workspace)
    assert manifest['status'] == 'READY'
    target = manifest['native_projects'][0]
    head = json.loads((workspace / target['head_file']).read_text(encoding='utf-8'))
    expected_head = {'generation': head['head_generation'], 'reference': head['reference']}
    request = {'reference': head['reference'], 'intent': 'working', 'target_id': target['target_id'],
               'expected_head': expected_head, 'selection': None, 'allow_partial': False}
    ticket = prepare_open(context, request, command_id='C' + uuid.uuid4().hex)
    opened, effects = tracked_open(lambda: portable_project.restore_bound_project(ticket.verified_input, ticket.binding))
    verify_opened(context, ticket.binding.open_id, opened['readback'])
    owner = opened['owner']; work = owner.workspace
    try:
        expected = json.loads((root / 'expected.json').read_text(encoding='utf-8'))
        ref = expected['analysis_b']; obj = work.object(ref)
        if edit:
            for item in work.describe()['objects']: assert not item.get('current_inputs_differ'), item
        for analysis_ref in (expected['analysis_a'], ref): work._bundle(work.object(analysis_ref))
        if edit:
            draft = deepcopy(obj['draft']); draft['settings']['scale_factor'] = .4
            work.edit_filter(draft=draft, object_ref=ref); work.validate(object_ref=ref); work.apply(object_ref=ref, show=False)
            work.undo(object_ref=ref); work.redo(object_ref=ref)
            # Keep B0/B1 frozen on A0, then move A's current editor cursor to A1.
            upstream = work.object(expected['analysis_a'])
            original_a = work.applied(upstream)['id']
            newer = deepcopy(upstream['draft']); newer['settings']['scale_factor'] = .15
            work.edit_filter(draft=newer, object_ref=upstream['id'])
            work.validate(object_ref=upstream['id']); work.apply(object_ref=upstream['id'], show=False)
            assert work.applied(upstream)['id'] != original_a
            for old in obj['history']:
                work._verify_record(obj, old, work.bundles[old['id']])
            assert next(item for item in work.describe()['objects'] if item['id'] == ref)['current_inputs_differ']
            stamp = portable_project.saved_offer(owner)['stamp']
            reservation = prepare_target_save(context, ticket.binding.open_id, expected_stamp=stamp,
                expected_head=expected_head, command_id='C' + uuid.uuid4().hex)
            witness = portable_project.complete_save(owner, expected_stamp=stamp, _target_save=reservation)
            result = publish_head(context, target['target_id'], witness, expected_head=expected_head,
                command_id='C' + uuid.uuid4().hex, _target_save=reservation)
            assert result['head']['head_generation'] == 1
            check = portable.verify_project(workspace); assert check['status'] == 'READY'
            inspection = portable.inspect_copy(context, [{'native': result['reference'], 'copy_intent': 'complete', 'working_target': True}])
            assert inspection['status'] == 'READY'
            copied = portable.create_copy(context, inspection, root / 'transaction2', approved=True,
                command_id='C' + uuid.uuid4().hex, session_id=context.session_id)
            assert copied['status'] in ('COPIED', 'READY', 'CREATED'), copied
            saved = {'head': result['head'], 'camera': list(p.GetActiveView().CameraPosition), 'upstream_revision': work.applied(upstream)['id'],
                     'time': float(p.GetAnimationScene().AnimationTime)}
            write_json(root / 'transaction1-readback.json', {'status': 'WORKING_HEAD_PUBLISHED_RECOPIED',
                'head': saved, 'open_effects': effects, 'second_copy': copied})
        else:
            prior = json.loads((root / 'transaction1-readback.json').read_text(encoding='utf-8'))
            assert obj['draft']['settings']['scale_factor'] == .4
            assert work.applied(work.object(expected['analysis_a']))['id'] == prior['head']['upstream_revision']
            assert next(item for item in work.describe()['objects'] if item['id'] == ref)['current_inputs_differ']
            for old in obj['history']:
                work._verify_record(obj, old, work.bundles[old['id']])
            work.undo(object_ref=ref); work.redo(object_ref=ref)
            assert list(p.GetActiveView().CameraPosition) == prior['head']['camera']
            assert float(p.GetAnimationScene().AnimationTime) == prior['head']['time']
            write_json(root / 'transaction2-readback.json', {'status': 'WORKING_HEAD_COLD_OPENED',
                'source_reference': head['reference'], 'current_working_document_id': owner.document_id,
                'scale_factor': obj['draft']['settings']['scale_factor'], 'open_effects': effects})
    finally:
        owner.close(); commands.clear_save_owner(owner)


def transaction(root, pvpython):
    from caelab import portable_project as portable
    from caelab.native_project_inputs import NativeOnlyContext
    context = NativeOnlyContext(root / 'registration', approved_roots={})
    reference = json.loads((context.workspace / 'reference.json').read_text())
    inspection = portable.inspect_copy(context, [{'native': reference, 'copy_intent': 'complete', 'working_target': True}])
    assert inspection['status'] == 'READY'
    portable.create_copy(context, inspection, root / 'transaction1', approved=True,
        command_id='C' + uuid.uuid4().hex, session_id=context.session_id)
    blocked = []
    try:
        for name in ('original', 'registration'):
            (root / name).rename(root / (name + '-tx-unavailable')); blocked.append(name)
        subprocess.run([pvpython, str(Path(__file__).resolve()), 'transaction-cold1', '--root', str(root)], cwd=REPO, check=True, timeout=120)
        (root / 'transaction1').rename(root / 'transaction1-tx-unavailable'); blocked.append('transaction1')
        subprocess.run([pvpython, str(Path(__file__).resolve()), 'transaction-cold2', '--root', str(root)], cwd=REPO, check=True, timeout=120)
        write_json(root / 'transaction-result.json', {'status': 'PORTABLE_TRANSACTION_TWO_COLD_HEAD_ROUNDTRIP',
            'original_and_registration_absent': True, 'first_target_absent_on_cold2': True})
    finally:
        for name in reversed(blocked):
            held = root / (name + '-tx-unavailable')
            if held.exists() and not (root / name).exists(): held.rename(root / name)


def first_save(root):
    from apps.desktop_post import portable_project as post, commands
    from caelab.native_project_inputs import NativeOnlyContext, prepare_target_save, publish_head
    from caelab.portable_project_native import prepare_open, verify_opened
    from caelab import portable_project as portable
    workspace = root / 'registration'
    context = NativeOnlyContext(workspace, approved_roots={})
    reference = json.loads((workspace / 'reference.json').read_text())
    ticket = prepare_open(context, {'reference': reference, 'intent': 'saved', 'target_id': None,
        'expected_head': None, 'selection': None, 'allow_partial': False}, command_id='C' + uuid.uuid4().hex)
    opened, effects = tracked_open(lambda: post.restore_bound_project(ticket.verified_input, ticket.binding))
    verify_opened(context, ticket.binding.open_id, opened['readback'])
    owner = opened['owner']; owner.native_project_context = context
    original_id, original_binding = owner.document_id, owner.portable_binding
    original_files = {str(path): path.read_bytes() for path in ticket.verified_input.member_paths.values()}
    try:
        try: owner.save_project()
        except ValueError as error: assert str(error).startswith('FIRST_SAVE_TARGET_REQUIRED')
        else: raise AssertionError('An imported snapshot was saved without a new target reservation')
        # Lose only the publication reply, after the real Save/head completed.
        import caelab.native_project_inputs as inputs
        real_publish, real_save = inputs.publish_head, owner.save_project
        calls = {'native_save': 0, 'publish': 0}
        def counted_save(**kwargs):
            calls['native_save'] += 1
            return real_save(**kwargs)
        def lose_reply(*args, **kwargs):
            calls['publish'] += 1
            result = real_publish(*args, **kwargs)
            if calls['publish'] == 1: raise RuntimeError('SIMULATED_PUBLICATION_REPLY_LOST')
            return result
        owner.save_project, inputs.publish_head = counted_save, lose_reply
        try:
            try: post.save_current_project(owner, confirm_first_save=lambda: True)
            except RuntimeError as error: assert str(error) == 'SIMULATED_PUBLICATION_REPLY_LOST'
            else: raise AssertionError('Expected a lost publication reply')
            saved = post.save_current_project(owner, confirm_first_save=lambda: True)
        finally:
            owner.save_project, inputs.publish_head = real_save, real_publish
        assert calls == {'native_save': 1, 'publish': 2}, calls
        assert saved.is_file() and owner.document_id == original_id and owner.portable_binding is original_binding
        assert owner.native_target_id and saved.is_relative_to(workspace / 'native' / owner.native_target_id)
        assert all(Path(path).read_bytes() == data for path, data in original_files.items())
        inspection = portable.inspect_copy(context, [{'native': owner.native_target_head['reference'],
            'copy_intent': 'complete', 'working_target': True}])
        assert inspection['status'] == 'READY'
        copied = portable.create_copy(context, inspection, root / 'first-save-copy', approved=True,
            command_id='C' + uuid.uuid4().hex, session_id=context.session_id)
        write_json(root / 'first-save-readback.json', {'status': 'FIRST_SAVE_NEW_TARGET_PUBLISHED',
            'source_reference': reference, 'saved_reference': owner.native_target_head['reference'],
            'live_document_id_before_after': original_id, 'new_target': owner.native_target_id,
            'source_bytes_unchanged': True, 'open_effects': effects, 'copy': copied})
    finally:
        owner.close(); commands.clear_save_owner(owner)


def orchestrate(root, pvpython):
    root.mkdir(parents=True, exist_ok=False)
    script = Path(__file__).resolve()
    def run(phase): subprocess.run([pvpython, str(script), phase, '--root', str(root)], cwd=REPO, check=True, timeout=120)
    blocked = []
    try:
        run('create')
        shutil.copytree(root / 'registration', root / 'copy1')
        (root / 'original').rename(root / 'original-unavailable'); blocked.append(('original', 'original-unavailable'))
        run('cold1')
        shutil.copytree(root / 'copy1' / 'workbench', root / 'copy2' / 'workbench')
        shutil.copyfile(root / 'copy1' / 'reference.json', root / 'copy2' / 'reference.json')
        (root / 'copy1').rename(root / 'copy1-unavailable'); blocked.append(('copy1', 'copy1-unavailable'))
        run('cold2')
        for original, moved in reversed(blocked):
            if (root / moved).exists() and not (root / original).exists(): (root / moved).rename(root / original)
        blocked.clear()
        run('partial')
        run('selection')
        run('adopt')
        run('poly-source'); run('poly-target')
        write_json(root / 'result.json', {'status': 'TWO_COLD_OPENED', 'scope': 'synthetic native ParaView read/edit/save; no engineering qualification'})
    finally:
        for original, moved in reversed(blocked):
            if (root / moved).exists() and not (root / original).exists(): (root / moved).rename(root / original)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('phase', choices=['run', 'create', 'cold1', 'cold2', 'partial', 'selection', 'adopt', 'poly-source', 'poly-target', 'transaction', 'transaction-cold1', 'transaction-cold2', 'first-save'])
    parser.add_argument('--root', required=True, type=Path); parser.add_argument('--pvpython')
    args = parser.parse_args(); root = args.root.resolve()
    if args.phase == 'run': orchestrate(root, args.pvpython)
    elif args.phase == 'create': create(root)
    elif args.phase == 'partial': partial_repair(root)
    elif args.phase == 'selection': exact_selection(root)
    elif args.phase == 'adopt': adopt_raw(root)
    elif args.phase in ('poly-source', 'poly-target'): polydata_capability(root, args.phase == 'poly-source')
    elif args.phase == 'transaction': transaction(root, args.pvpython)
    elif args.phase == 'first-save': first_save(root)
    elif args.phase in ('transaction-cold1', 'transaction-cold2'): transaction_cold(root, args.phase == 'transaction-cold1')
    else: cold(root, args.phase.replace('cold', 'copy'), args.phase == 'cold1')
