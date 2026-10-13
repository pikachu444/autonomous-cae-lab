"""Contact inspection on the existing native Post workspace; no new owner."""
from copy import deepcopy
import json
from pathlib import Path
import uuid

from paraview import simple as p
try:
    from . import external, analysis
except ImportError:
    import external
    import analysis


def read(workspace, source_ref):
    record = workspace.document.get('sources', {}).get(source_ref)
    if record is None or not record.get('input_id'):
        raise ValueError('Select the original registered contact result')
    declaration = (record.get('native_metadata') or {}).get('contact_inspection')
    if declaration is None:
        raise ValueError('This input has no retained contact inspection bundle; register a rebuilt Post result explicitly')
    workspace.pending([source_ref])
    workspace._verify_inputs([source_ref])
    return external.contact_api().load(record['entry_path'], declaration)


def inspect(workspace, *, source_ref, pair_id=None, side='both', frame_index=0,
            field='CPRESS', quantity='CFN', component=2, show=False, view_id=None,
            offset=0, limit=500):
    if type(show) is not bool or type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Use an explicit display choice and a bounded contact row page')
    bundle = read(workspace, source_ref)
    api = external.contact_api()
    if pair_id is None:
        saved = workspace.state.get('contact_selection', {})
        if saved.get('source_ref') == source_ref and saved.get('inspection_sha256') == bundle['descriptor']['sha256']:
            pair_id, side, frame_index, field, quantity, component = [
                saved[key] for key in ('pair_id', 'side', 'frame_index', 'field', 'quantity', 'component')]
        else:
            pair_id = next(iter(bundle['pairs']))
    selected = api.inspect(bundle, pair_id, side, frame_index, field, quantity, component)
    selection = {'source_ref': source_ref, 'pair_id': pair_id, 'side': side,
                 'frame_index': frame_index, 'field': field, 'quantity': quantity, 'component': component,
                 'inspection_sha256': bundle['descriptor']['sha256']}
    if show:
        _show(workspace, bundle, selection, view_id)
        workspace._touch()
    rows = selected.pop('rows')
    return {'catalog': api.describe(bundle), 'selection': selection, **selected,
            'rows': rows[offset:offset+limit], 'total_rows': len(rows), 'offset': offset,
            'next_offset': offset + limit if offset + limit < len(rows) else None,
            'displayed': show}


def _overlay_graph(proxies, bundle):
    """Path-independent identity only after checking the exact pinned reader."""
    graph = analysis.graph_signature({'source': proxies[-1], 'proxies': proxies}, raw_ints=True)
    graph.pop('sha256', None)
    readers = [proxy for proxy in proxies if proxy.GetXMLName() == 'XMLUnstructuredGridReader']
    if len(readers) != 1 or [str(Path(path).resolve()) for path in readers[0].FileName] != [
            str(Path(bundle['surfaces_path']).resolve())]:
        raise ValueError('Contact face reader no longer uses the pinned surface input')
    for node in graph['nodes']:
        if node['type'] == 'XMLUnstructuredGridReader':
            # An identical input relocation changes only FileName. Its current
            # path is checked above; all other native properties stay bound.
            node['properties'].pop('FileName', None)
    return graph


def _owned_overlay(workspace, selected, bundle, *, replacing):
    names = selected.get('overlay_names', [])
    if not names or len(names) != len(set(names)):
        raise ValueError('Saved contact surface names are unavailable or ambiguous')
    proxies = [p.FindSource(name) for name in names]
    if all(proxy is None for proxy in proxies) and replacing:
        # Explicitly removed/renamed native branches are never reclaimed by name.
        return []
    if any(proxy is None for proxy in proxies):
        raise ValueError('Contact surface branch changed; preserve it or remove/rename the complete old overlay before Show faces')
    for proxy in proxies:
        _, pending = workspace.owner.native_properties(proxy)
        if pending:
            raise ValueError('BUSY_EDIT: Apply/Reset pending contact surface properties before Show faces')
    if _overlay_graph(proxies, bundle) != selected.get('overlay_graph'):
        raise ValueError('Contact surface properties changed; keep or rename this native branch before Show faces again')
    if replacing:
        # Never delete an owned input from under a user's Clip, extraction or
        # other downstream native pipeline. No source-name heuristic grants this.
        for candidate in p.GetSources().values():
            if any(external._same_proxy(candidate, proxy) for proxy in proxies):
                continue
            for name in candidate.ListProperties():
                prop = candidate.GetProperty(name)
                if prop is None or not callable(getattr(prop, 'GetData', None)):
                    continue
                value = prop.GetData()
                values = value if isinstance(value, (tuple, list)) else [value]
                if any(hasattr(item, 'SMProxy') and any(external._same_proxy(item, proxy)
                       for proxy in proxies) for item in values):
                    raise ValueError('Contact surface has a native dependent filter; keep or rename the branch before Show faces again')
        for _, view in workspace._views():
            for display in getattr(view, 'Representations', []):
                inputs = getattr(display, 'Input', [])
                inputs = inputs if isinstance(inputs, (list, tuple)) else [inputs]
                if any(any(external._same_proxy(item, proxy) for proxy in proxies) for item in inputs):
                    _, pending = workspace.owner.native_properties(display)
                    if pending:
                        raise ValueError('BUSY_EDIT: Apply/Reset the contact surface display before Show faces')
    return proxies


def _show(workspace, bundle, selection, view_id=None):
    source = workspace.resolve(selection['source_ref'])
    views = [(name, view) for name, view in workspace._views() if view.GetXMLName() == 'RenderView']
    view = next((v for _, v in views if workspace.owner.proxy_id(v) == view_id), None) if view_id else (
        p.GetActiveView() if p.GetActiveView() is not None and p.GetActiveView().GetXMLName() == 'RenderView'
        else next((v for _, v in views), None))
    if view is None:
        raise ValueError('Choose an existing native Render View for the contact surfaces')
    pair = bundle['pairs'][selection['pair_id']]
    previous_source, previous_view = p.GetActiveSource(), p.GetActiveView()
    old = workspace.state.get('contact_selection', {})
    retired = []
    if old:
        previous_bundle = bundle if old['source_ref'] == selection['source_ref'] else read(workspace, old['source_ref'])
        if previous_bundle['descriptor']['sha256'] != old['inspection_sha256']:
            raise ValueError('Previous contact surface input changed; its native branch is preserved')
        retired = _owned_overlay(workspace, old, previous_bundle, replacing=True)
    created = []
    namespace = 'Contact faces ' + uuid.uuid4().hex[:10]
    try:
        reader = p.XMLUnstructuredGridReader(registrationName=namespace, FileName=[bundle['surfaces_path']])
        created.append(reader)
        reader.UpdatePipeline()
        for side, color in [('a', [0.95, 0.48, 0.12]), ('b', [0.05, 0.7, 0.85])]:
            if selection['side'] not in (side, 'both'):
                continue
            identifier = pair[side]['surface_index']
            face = p.Threshold(registrationName=namespace + ' ' + side.upper(), Input=reader)
            created.append(face)
            face.Scalars = ['CELLS', 'ContactSurfaceIndex']
            # The surface index is scalar. ParaView 6.2 otherwise reports an
            # empty default here before Save and component 0 after PVSM reload.
            face.SelectedComponent = 0
            face.ThresholdMethod = 'Between'
            face.LowerThreshold = identifier
            face.UpperThreshold = identifier
            face.UpdatePipeline()
            if not face.GetDataInformation().GetNumberOfCells():
                raise ValueError('The selected frozen contact surface has no native cells')
            display = p.Show(face, view)
            # ParaView 6.2 can initialize a new outline with association NONE;
            # ColorBy(None) still resolves that association before disabling it.
            display.ColorArrayName = ['POINTS', '']
            p.ColorBy(display, None)
            display.Representation = 'Wireframe'
            display.DiffuseColor = color
            display.LineWidth = 3.
        static = bundle['frames'][selection['frame_index']]['static']
        p.SetActiveView(view)
        external.select_array(source, 'POINTS', selection['field'],
                              time=static['load_parameter'], view=view)
        field = selection['field']
        unit = 'mm' if field in ('COPEN', 'CSLIP1', 'CSLIP2', 'GeomGap_mm') else 'MPa'
        scalar_bar = p.GetScalarBar(p.GetColorTransferFunction(field), view)
        scalar_bar.Title = ('Geometric gap (derived)' if field == 'GeomGap_mm' else field + (' (raw)' if field == 'COPEN' else '')) + ' [' + unit + ']'
        scalar_bar.ComponentTitle = ''
        p.SetActiveSource(source)
        p.Render(view)
        names = [next(name for (name, _), item in p.GetSources().items()
                      if external._same_proxy(item, proxy)) for proxy in created]
        graph = _overlay_graph(created, bundle)
        # The earlier guard checked both native edits and downstream consumers.
        for proxy in reversed(retired):
            p.Delete(proxy)
        if 'native_readers' in workspace.document:
            workspace.document['native_readers'] = [r for r in workspace.document['native_readers']
                if r['reader_name'] not in old.get('overlay_names', [])]
        workspace.state['contact_selection'] = {
            **deepcopy(selection), 'overlay_names': names, 'overlay_graph': graph,
            'view_name': next(name for name, candidate in views if external._same_proxy(candidate, view))}
    except BaseException:
        for proxy in reversed(created):
            p.Delete(proxy)
        p.SetActiveSource(previous_source)
        p.SetActiveView(previous_view)
        raise


def restore(workspace):
    selected = workspace.state.get('contact_selection')
    if not selected:
        return False
    try:
        bundle = read(workspace, selected['source_ref'])
        if bundle['descriptor']['sha256'] != selected['inspection_sha256']:
            raise ValueError('Saved contact selection belongs to another retained result')
        view = next((v for name, v in workspace._views() if name == selected.get('view_name')), None)
        if view is None:
            raise ValueError('Saved contact Render View is unavailable')
        external.contact_api().inspect(bundle, *[selected[k] for k in
            ('pair_id', 'side', 'frame_index', 'field', 'quantity', 'component')])
        _owned_overlay(workspace, selected, bundle, replacing=False)
        # PVSM already restored the exact display/time/visibility and any later
        # native edits. Opening a project must not replay an earlier Show action.
        return True
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        workspace.restore_issues.append({'source_ref': selected.get('source_ref'),
            'message': 'Contact selection was not restored: ' + str(error)})
        return False


def recipe(workspace, source_ref, pair_id, quantity, component):
    bundle = read(workspace, source_ref)
    history = external.contact_api().force_history(bundle, pair_id, quantity, component)
    return {'source_ref': source_ref, 'measurement': 'contact_force', 'association': 'ROWS',
            'pair_id': pair_id, 'quantity': quantity, 'component': component,
            'array': history['array'], 'units': 'N', 'frame': history['frame'],
            'measure': history['measure'], 'axis_name': 'load_parameter', 'axis_unit': '1',
            'time_units': '1', 'time_origin': 'STATIC_LOAD_PARAMETER',
            'inspection_sha256': bundle['descriptor']['sha256']}


def build_measurement(workspace, draft, namespace):
    expected = recipe(workspace, draft['source_ref'], draft['pair_id'], draft['quantity'], draft['component'])
    if draft != expected:
        raise ValueError('Contact force recipe differs from its exact pair/component and retained declarations')
    bundle = read(workspace, draft['source_ref'])
    history = external.contact_api().force_history(bundle, draft['pair_id'], draft['quantity'], draft['component'])
    # ProgrammableSource materializes an actual vtkTable from verified retained
    # numeric rows. The generated literal contains no caller code or file lookup.
    # Native PVSM retains this script; its properties are verified by graph_signature.
    values = {'load_parameter': [r['static']['load_parameter'] for r in history['rows']],
              draft['array']: [r['value'] for r in history['rows']],
              'vtkValidMask': [int(r['valid']) for r in history['rows']],
              'step': [r['static']['step'] for r in history['rows']],
              'increment': [r['static']['increment'] for r in history['rows']]}
    payload = json.dumps(values, allow_nan=False, separators=(',', ':'))
    script = (
        "import json\n"
        "from vtkmodules.vtkCommonCore import vtkDoubleArray\n"
        "rows = json.loads(" + repr(payload) + ")\n"
        "output = self.GetTableOutput()\n"
        "output.Initialize()\n"
        "for name, values in rows.items():\n"
        "    array = vtkDoubleArray()\n"
        "    array.SetName(name)\n"
        "    for value in values:\n"
        "        array.InsertNextValue(float('nan') if value is None else value)\n"
        "    output.AddColumn(array)\n")
    proxy = None
    try:
        proxy = p.ProgrammableSource(registrationName=namespace, OutputDataSetType='vtkTable')
        proxy.Script = script
        proxy.UpdatePipeline()
        data = analysis._fetch(proxy)
        if data.GetNumberOfRows() != len(history['rows']):
            raise ValueError('Native contact table has an incomplete row set')
        summary = {'measurement': 'contact_force', 'array': draft['array'], 'association': 'ROWS',
            'sample_semantics': 'retained_DAT_pair_resultant', 'units': 'N',
            'frame': history['frame'], 'measure': history['measure'], 'quantity': draft['quantity'],
            'component_label': draft['quantity'] + ' global ' + 'XYZ'[draft['component']],
            'location': bundle['pairs'][draft['pair_id']]['label'] + ' / ' + draft['pair_id'],
            'axis_name': 'load_parameter', 'axis_unit': '1',
            'axis_values': values['load_parameter'], 'time_units': '1', 'time_origin': 'STATIC_LOAD_PARAMETER',
            'pair_id': draft['pair_id'], 'force_rows': history['rows'],
            'inspection_sha256': draft['inspection_sha256'], 'active_state': 'UNKNOWN'}
        return {'source': proxy, 'proxies': [proxy], 'summary': summary}
    except BaseException:
        if proxy is not None:
            p.Delete(proxy)
        raise


def create_measurement(workspace, *, source_ref, pair_id, quantity, component):
    draft = recipe(workspace, source_ref, pair_id, quantity, component)
    label = read(workspace, source_ref)['pairs'][pair_id]['label']
    obj = workspace.edit_measurement(draft=draft, title=label + ' ' + quantity + ' ' + 'XYZ'[component])
    try:
        workspace.validate(object_ref=obj['id'])
        workspace.apply(object_ref=obj['id'], show=True)
    except BaseException:
        # Keep the explicit draft and diagnostics repairable. No saved project
        # or existing measurement is replaced when native display fails.
        raise
    return {'object_ref': obj['id'], 'recipe': draft, 'saved': False}


def annotate(page, summary):
    if summary.get('measurement') != 'contact_force':
        return page
    array = summary['array']
    expected = summary['force_rows']
    for row in page.get('rows', []):
        index = row.get('row')
        if row.get('block') != [] or type(index) is not int or not 0 <= index < len(expected):
            raise ValueError('Contact table row identity changed')
        source = expected[index]
        values = row['values']
        value = values.get(array)
        if (values.get('load_parameter') != source['static']['load_parameter']
                or values.get('step') != source['static']['step']
                or values.get('increment') != source['static']['increment']
                or values.get('vtkValidMask') != int(source['valid'])
                or value != source['value']):
            raise ValueError('Contact table values differ from retained pair samples')
        row['validity'] = {array: 'valid' if source['valid'] else source['reason']}
    return page
