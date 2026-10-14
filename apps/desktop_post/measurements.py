"""Native selections and curves, with explicit original-point tracking."""
from copy import deepcopy
import hashlib
import json
import math
import uuid

import numpy as np
from paraview import simple as p, servermanager
try:
    from paraview.vtk.util.numpy_support import vtk_to_numpy
except ImportError:
    from vtk.util.numpy_support import vtk_to_numpy
try:
    from . import analysis, external
except ImportError:
    import analysis
    import external


def _name(namespace, role):
    return namespace + ' | ' + role + ' | ' + uuid.uuid4().hex[:10]


def _indices(indices, size):
    if (not isinstance(indices, list) or not 1 <= len(indices) <= 1000
            or any(type(value) is not int or not 0 <= value < size for value in indices)
            or len(set(indices)) != len(indices)):
        raise ValueError('Select 1–1000 distinct original point indexes inside this exact source')
    return indices


def _selection(indices, namespace):
    from paraview.selection import CreateSelection
    return CreateSelection('SelectionQuerySource', _name(namespace, 'original point indexes'),
                           ElementType=0, QueryString=' | '.join('(id == %d)' % value for value in indices), InsideOut=0)


def highlight_point(source, point_index):
    """Change only this source's native point selection, using the actual query API."""
    _indices([point_index],source.GetDataInformation().GetNumberOfPoints())
    from paraview.selection import QuerySelect
    QuerySelect(QueryString='id == %d' % point_index,FieldType='POINT',Source=source,InsideOut=False)
    p.SetActiveSource(source)
    p.RenderAllViews()


def capture_point_selection(source):
    """Use the native point selection attached to the requested original reader."""
    selection = source.GetSelectionInput(0)
    if selection is None:
        raise ValueError('Select original points on this reader in the native Render/Spreadsheet view first')
    if not hasattr(selection, 'SMProxy'):
        selection = servermanager._getPyProxy(selection)
    prop = selection.GetProperty('ElementType') or selection.GetProperty('FieldType')
    if prop is not None:
        field = prop.GetData()
        if isinstance(field, (tuple, list)) and len(field) == 1:
            field = field[0]
        if field not in (0, 'POINT', 'POINTS'):
            raise ValueError('Choose a native point selection; cell/location selections are different measurements')
    before = p.GetActiveSource(), p.GetActiveView()
    extraction = None
    try:
        extraction = p.ExtractSelection(registrationName=_name('CAE selection', 'capture'), Input=source, Selection=selection)
        extraction.UpdatePipeline()
        data = servermanager.Fetch(extraction)
        if not hasattr(data, 'GetPointData'):
            raise ValueError('Original point capture currently requires a single dataset')
        ids = data.GetPointData().GetArray('vtkOriginalPointIds')
        if ids is None:
            raise ValueError('Native selection did not preserve original point indexes')
        values = np.asarray(vtk_to_numpy(ids)).reshape(-1)
        return _indices([int(item) for item in values], source.GetDataInformation().GetNumberOfPoints())
    finally:
        if extraction is not None:
            p.Delete(extraction)
        p.SetActiveSource(before[0])
        p.SetActiveView(before[1])


def _tracking_identity(data):
    if not hasattr(data, 'GetPoints') or data.GetPoints() is None:
        raise ValueError('Time tracking currently requires a single point dataset')
    identity = hashlib.sha256()
    identity.update(str((data.GetNumberOfPoints(), data.GetNumberOfCells())).encode())
    for cell in range(data.GetNumberOfCells()):
        ids = data.GetCell(cell).GetPointIds()
        identity.update(np.asarray([data.GetCellType(cell), *[ids.GetId(i) for i in range(ids.GetNumberOfIds())]], dtype='<i8').tobytes())
    original_ids = data.GetPointData().GetGlobalIds()
    if original_ids is None:
        for name in ('NativeNodeId', 'GlobalNodeId', 'GlobalIds'):
            original_ids = data.GetPointData().GetArray(name)
            if original_ids is not None:
                break
    if original_ids is None:
        # Without a stable native identity, moving/reordered points cannot be
        # interpreted as the same physical points across frames.
        identity.update(np.asarray(vtk_to_numpy(data.GetPoints().GetData()), dtype='<f8').tobytes())
        mode = 'unchanged_coordinates_and_connectivity'
    else:
        ids = np.asarray(vtk_to_numpy(original_ids)).reshape(-1)
        if len(ids) != data.GetNumberOfPoints() or len(np.unique(ids)) != len(ids):
            raise ValueError('Time curve requires unique original point identities')
        identity.update(ids.dtype.str.encode())
        identity.update(ids.tobytes())
        mode = 'native_ids_and_connectivity'
    return identity.hexdigest(), mode


def build_measurement(source, draft, namespace):
    if not isinstance(draft, dict) or draft.get('association') != 'POINTS':
        raise ValueError('Choose a declared POINTS measurement')
    kind = draft.get('measurement')
    array = draft.get('array')
    if not isinstance(array, str) or not array:
        raise ValueError('Choose an exact native array')
    source.UpdatePipeline()
    if array not in source.PointData.keys():
        raise ValueError('Selected point array is not available on this native source')
    if kind == 'path':
        settings = {key: deepcopy(draft[key]) for key in ('array', 'association', 'point1', 'point2', 'resolution', 'tolerance')}
        if 'time' in draft:
            settings['time'] = draft['time']
        bundle = analysis.create_filter(source, 'PlotOverLine', settings, namespace)
        bundle['summary'].update(measurement='path', sample_semantics='interpolated_at_path_points',
                                 recipe=deepcopy(draft), **{key: draft.get(key) or None for key in
                                     ('quantity', 'units', 'frame', 'measure', 'coordinate_units', 'coordinate_frame', 'time_units', 'time_origin')})
        return bundle
    if kind not in ('point', 'time'):
        raise ValueError('Supported measurements are original point, original-point time curve, and interpolated path')
    indices = _indices(draft.get('point_indices'), source.GetDataInformation().GetNumberOfPoints())
    before = p.GetActiveSource(), p.GetActiveView()
    proxies = []
    selection = None
    try:
        native_times = external.times(source)
        if kind == 'time':
            if not native_times or any(b <= a for a, b in zip(native_times, native_times[1:])):
                raise ValueError('A time curve requires strictly ordered actual native frames')
            if len(native_times) > 1024:
                raise ValueError('This time-curve connection supports at most 1024 native frames')
            for key in ('time_units', 'time_origin'):
                if not isinstance(draft.get(key), str) or not draft[key].strip():
                    raise ValueError('Explicitly declare the actual clock ' + key)
            identity = tracking = None
            for time in native_times:
                temporary = []
                try:
                    frozen = analysis._freeze(source, time, namespace, temporary)
                    data = servermanager.Fetch(frozen)
                    current, mode = _tracking_identity(data)
                    if identity is not None and current != identity:
                        raise ValueError('TIME_TRACKING_UNSUPPORTED: native identities/topology changed between frames; no point correspondence is guessed')
                    identity, tracking = current, mode
                finally:
                    for proxy in reversed(temporary):
                        p.Delete(proxy)
            selected_input = source
        else:
            if native_times and ('time' not in draft or draft['time'] not in native_times):
                raise ValueError('Choose an exact native frame for the saved original-point measurement')
            selected_input = analysis._freeze(source, draft.get('time'), namespace, proxies)
        selection = _selection(indices, namespace)
        # Selection sources live in the selection_sources group. Keep their
        # stable names separately; SaveState retains the actual selection proxy.
        extraction = (p.PlotSelectionOverTime(registrationName=_name(namespace, 'native point histories'), Input=selected_input, Selection=selection,
                                               OnlyReportSelectionStatistics=0) if kind == 'time' else
                      p.ExtractSelection(registrationName=_name(namespace, 'original samples'), Input=selected_input, Selection=selection))
        proxies.append(extraction)
        extraction.UpdatePipeline()
        summary = {'measurement': kind, 'array': array, 'association': 'POINTS',
                   'sample_semantics': 'original_native_points', 'point_indices': list(indices),
                   'time': draft.get('time') if kind == 'point' else None,
                   'time_values': native_times if kind == 'time' else [],
                   'time_units': draft.get('time_units'), 'time_origin': draft.get('time_origin'),
                   'tracking': tracking if kind == 'time' else None,
                   **{key: draft.get(key) or None for key in ('quantity', 'units', 'frame', 'measure', 'coordinate_units', 'coordinate_frame')},
                   'selection_type': 'SelectionQuerySource', 'selection_query': ' | '.join('(id == %d)' % value for value in indices)}
        return {'source': extraction, 'proxies': proxies, 'selection_proxies': [selection], 'summary': summary}
    except BaseException:
        for proxy in reversed(proxies):
            p.Delete(proxy)
        if selection is not None:
            p.Delete(selection)
        raise
    finally:
        p.SetActiveSource(before[0])
        p.SetActiveView(before[1])


def sample_data(source, *, offset=0, limit=100, point_index=None, declarations=None):
    data = analysis._fetch(source)
    if hasattr(data, 'GetPointData'):
        return analysis.sample_data(source, offset=offset, limit=limit, point_index=point_index, declarations=declarations)
    if point_index is not None:
        raise ValueError('Time tables use result rows and block identity, not spatial point indexes')
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Choose an offset and 1–1000 table rows')
    rows, total = [], 0
    def visit(block, path):
        nonlocal total
        if block is None:
            return
        if hasattr(block, 'GetNumberOfBlocks'):
            for index in range(block.GetNumberOfBlocks()):
                visit(block.GetBlock(index), path + [index])
            return
        if hasattr(block, 'GetRowData'):
            fields, count = block.GetRowData(), block.GetNumberOfRows()
        elif hasattr(block, 'GetPointData'):
            fields, count = block.GetPointData(), block.GetNumberOfPoints()
        else:
            raise ValueError('Native curve output is not a supported table/point block')
        arrays = [(fields.GetArray(i).GetName(), np.asarray(vtk_to_numpy(fields.GetArray(i))))
                  for i in range(fields.GetNumberOfArrays()) if fields.GetArray(i) is not None]
        for index in range(count):
            if offset <= total < offset + limit:
                values = {}
                for name, array in arrays:
                    value = np.asarray(array[index]).tolist()
                    def safe(v):
                        if isinstance(v, list): return [safe(x) for x in v]
                        if isinstance(v, float) and not math.isfinite(v): return None
                        return v
                    values[name] = safe(value)
                rows.append({'block': list(path), 'row': index, 'values': values})
            total += 1
    visit(data, [])
    return {'rows': rows, 'total': total, 'offset': offset, 'limit': limit, 'semantics': 'native_time_table'}


def save_native_data(source, folder, stem, *, table_xml=False):
    """Select the native writer from its actual VTK output type, retain dependencies."""
    data = analysis._fetch(source)
    extensions = {'vtkUnstructuredGrid': '.vtu', 'vtkPolyData': '.vtp', 'vtkTable': '.csv',
                  'vtkRectilinearGrid': '.vtr', 'vtkImageData': '.vti', 'vtkStructuredGrid': '.vts',
                  'vtkMultiBlockDataSet': '.vtm', 'vtkPartitionedDataSetCollection': '.vtpc'}
    extension = '.vtt' if table_xml and data.IsA('vtkTable') else extensions.get(data.GetClassName())
    if extension is None:
        raise ValueError('No managed native writer for ' + data.GetClassName())
    folder.mkdir(parents=True, exist_ok=False)
    path = folder / (stem + extension)
    if data.GetClassName() == 'vtkTable':
        # Table association and round-trip Float64 precision are explicit; the
        # contact load parameter is a column, not a native physical Time field.
        if table_xml:
            p.SaveData(str(path), proxy=source, DataMode='Binary', CompressorType='None')
        else:
            p.SaveData(str(path), proxy=source, FieldAssociation='Row Data', Precision=17,
                       AddTime=0, AddTimeStep=0)
    else:
        p.SaveData(str(path), proxy=source)
    if not path.is_file() or not path.stat().st_size:
        raise RuntimeError('Native writer produced no result')
    files = [file for file in folder.rglob('*') if file.is_file()]
    return {'entry': str(path), 'files': [{'path': str(file), 'bytes': file.stat().st_size,
            'sha256': external.sha(file)} for file in files]}
