"""Owned ParaView filters for comparison v2. No source or scene mutation."""
from copy import deepcopy
import hashlib
import json
import numpy as np
from paraview import simple as p
try:
    from paraview.numpy_support import vtk_to_numpy, numpy_to_vtk
except ImportError:
    from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk
from caelab import post_comparison as physical

RAW = '__comparison_raw'
VALUE = '__comparison_value'
ORIGINAL = '__comparison_unmasked'


def geometry(data):
    if not (data.IsA('vtkUnstructuredGrid') or data.IsA('vtkPolyData')) or data.GetNumberOfPoints() == 0:
        raise ValueError('점/경로 또는 비정형 메시 자료를 선택하세요. 표의 시간 곡선은 별도 축 대응이 필요합니다.')
    points = np.asarray([data.GetPoint(i) for i in range(data.GetNumberOfPoints())], dtype=np.float64)
    if not np.isfinite(points).all():
        raise ValueError('형상 좌표에 비유한 값이 있습니다.')
    cells = [(data.GetCellType(i), tuple(data.GetCell(i).GetPointId(j)
             for j in range(data.GetCell(i).GetNumberOfPoints()))) for i in range(data.GetNumberOfCells())]
    digest = hashlib.sha256(points.tobytes() + json.dumps(cells, separators=(',', ':')).encode()).hexdigest()
    return points, cells, digest


def _put(attributes, name, values):
    values = np.ascontiguousarray(values)
    arr = numpy_to_vtk(values, deep=True)
    arr.SetName(name)
    attributes.AddArray(arr)


def _values(data, name):
    arr = data.GetPointData().GetArray(name)
    if arr is None:
        raise ValueError('변환 배열이 없습니다: ' + name)
    values = np.asarray(vtk_to_numpy(arr), dtype=np.float64)
    return values[:, None] if values.ndim == 1 else values


def execute(inputs, output, stage, settings):
    """Called by saved native ProgrammableFilter; only detached outputs change."""
    from paraview import vtk
    if stage == 'frozen':
        output.DeepCopy(inputs[0])
        output.GetInformation().Remove(vtk.vtkDataObject.DATA_TIME_STEP())
    elif stage == 'quality_only':
        source = inputs[0]; output.DeepCopy(source)
        values = _values(source, settings['array']).copy()
        if len(values) != source.GetNumberOfPoints():
            raise ValueError('파생 응답 행 수와 원 점 개수가 다릅니다.')
        valid = np.isfinite(values).all(axis=1)
        for name in settings['masks']:
            mask = source.GetPointData().GetArray(name)
            if mask is None or mask.GetNumberOfComponents() != 1 or mask.GetNumberOfTuples() != len(values):
                raise ValueError('파생 응답의 원 품질 마스크를 확인할 수 없습니다: ' + name)
            flags = vtk_to_numpy(mask)
            valid &= np.isfinite(flags) & (flags != 0)
        values[~valid] = np.nan
        output.GetPointData().RemoveArray(settings['array'])
        _put(output.GetPointData(), settings['array'], values)
    elif stage == 'prepare':
        source = inputs[0]; side = settings
        geometry(source)
        attrs = source.GetPointData() if side['association'] == 'POINTS' else source.GetCellData()
        arr = attrs.GetArray(side['array'])
        if arr is None or arr.GetNumberOfComponents() != physical.layout_size(side['layout']):
            raise ValueError('선언한 원 배열/성분이 실제 자료와 다릅니다.')
        expected = source.GetNumberOfPoints() if side['association'] == 'POINTS' else source.GetNumberOfCells()
        if arr.GetNumberOfTuples() != expected:
            raise ValueError('배열 행 수와 실제 점/셀 개수가 다릅니다.')
        from .analysis import _identity
        if _identity(side['array']) or side['array'].lower().endswith(('mask', '_valid', '_id')):
            raise ValueError('식별자·유효성 배열은 물리 응답으로 보간하지 않습니다.')
        values = np.asarray(vtk_to_numpy(arr), dtype=np.float64).copy()
        if values.ndim == 1: values = values[:, None]
        masks = list(side.get('validity_masks', []))
        if attrs.GetArray('vtkValidPointMask') is not None and 'vtkValidPointMask' not in masks:
            masks.append('vtkValidPointMask')
        valid = np.isfinite(values).all(axis=1)
        for name in masks:
            mask = attrs.GetArray(name)
            if mask is None or mask.GetNumberOfComponents() != 1 or mask.GetNumberOfTuples() != len(values):
                raise ValueError('명시한 유효성 마스크가 없거나 위치가 다릅니다: ' + name)
            mask_values = vtk_to_numpy(mask)
            valid &= np.isfinite(mask_values) & (mask_values != 0)
        original = values.copy()
        values[~valid] = np.nan
        detached = source.NewInstance(); detached.DeepCopy(source)
        detached.GetPointData().Initialize(); detached.GetCellData().Initialize(); detached.GetFieldData().Initialize()
        if side['association'] == 'CELLS':
            # This managed desktop comparison requires a single local dataset.
            # The owner rejects distributed pieces instead of averaging incomplete halos.
            _put(detached.GetCellData(), RAW, values)
            _put(detached.GetCellData(), ORIGINAL, original)
            projection = vtk.vtkCellDataToPointData()
            projection.SetInputData(detached); projection.SetProcessAllArrays(False)
            projection.AddCellDataArray(RAW); projection.AddCellDataArray(ORIGINAL); projection.SetPassCellData(False)
            projection.SetContributingCellOption(0)  # All incident cells, equal weights.
            projection.Update()
            output.ShallowCopy(projection.GetOutput())
            projected = _values(output, RAW).copy()
            raw_projected = _values(output, ORIGINAL).copy()
            # Conservative coverage: every incident cell must supply a valid tuple.
            ids = vtk.vtkIdList()
            for point in range(source.GetNumberOfPoints()):
                source.GetPointCells(point, ids)
                if ids.GetNumberOfIds() == 0 or any(not valid[ids.GetId(j)] for j in range(ids.GetNumberOfIds())):
                    projected[point] = np.nan
            output.GetPointData().Initialize(); output.GetCellData().Initialize()
            _put(output.GetPointData(), RAW, projected)
            _put(output.GetPointData(), ORIGINAL, raw_projected)
        else:
            output.ShallowCopy(detached)
            _put(output.GetPointData(), RAW, values)
            _put(output.GetPointData(), ORIGINAL, original)
    elif stage == 'temporal':
        if geometry(inputs[0])[2] != geometry(inputs[1])[2]:
            raise ValueError('시간 구간에서 좌표/위상 대응이 달라졌습니다. 보간하지 않습니다.')
        left, right = _values(inputs[0], RAW), _values(inputs[1], RAW)
        if left.shape != right.shape:
            raise ValueError('시간 끝점의 배열 성분이 다릅니다.')
        weight = settings['weight']
        values = (1. - weight) * left + weight * right
        values[~(np.isfinite(left).all(axis=1) & np.isfinite(right).all(axis=1))] = np.nan
        output.ShallowCopy(inputs[0]); output.GetPointData().Initialize()
        _put(output.GetPointData(), RAW, values)
        _put(output.GetPointData(), ORIGINAL, (1. - weight) * _values(inputs[0], ORIGINAL) + weight * _values(inputs[1], ORIGINAL))
    elif stage == 'transform':
        source = inputs[0]; side, recipe = settings['side'], settings['recipe']
        output.DeepCopy(source)
        raw = _values(source, RAW)
        transformed = physical.transform_values(raw, side, recipe['target'], settings['response_rotation'])
        points = physical.transform_points(geometry(source)[0], side['coordinate_units'], recipe['a']['coordinate_units'],
                                          settings['geometry_rotation'], settings['translation'])
        native_points = vtk.vtkPoints(); native_points.SetData(numpy_to_vtk(points, deep=True))
        output.SetPoints(native_points)
        output.GetPointData().Initialize(); output.GetCellData().Initialize()
        _put(output.GetPointData(), RAW, raw); _put(output.GetPointData(), VALUE, transformed)
        _put(output.GetPointData(), ORIGINAL, _values(source, ORIGINAL))
    elif stage == 'difference':
        from .analysis import OUTPUT_ARRAYS, _identity_arrays
        a, b = inputs[:2]; recipe = settings
        output.DeepCopy(a)
        output.GetPointData().Initialize(); output.GetCellData().Initialize(); output.GetFieldData().Initialize()
        # Identities come from the exact A endpoint, never from any projection.
        for source_attrs, target_attrs in ((inputs[2].GetPointData(), output.GetPointData()),
                                          (inputs[2].GetCellData(), output.GetCellData())):
            for name in _identity_arrays(source_attrs):
                target_attrs.AddArray(source_attrs.GetAbstractArray(name))
        inside = b.GetPointData().GetArray('vtkValidPointMask')
        inside = np.ones(a.GetNumberOfPoints(), dtype=bool) if inside is None else vtk_to_numpy(inside).astype(bool)
        av, bv = _values(a, VALUE), _values(b, VALUE).copy()
        bv[~inside] = np.nan
        values = physical.compare(av, bv, recipe, inside)
        for role, name in OUTPUT_ARRAYS.items():
            array = values[role]
            _put(output.GetPointData(), name, array.astype(np.uint8) if array.dtype == bool else array)
        for name, source, side in (('A_source_value', a, recipe['a']), ('B_source_sampled', b, recipe['b'])):
            raw_values = _values(source, ORIGINAL).copy()
            if source is b: raw_values[~inside] = np.nan
            original_components = physical.canonical(raw_values, side['layout'])
            _put(output.GetPointData(), name, physical.scalar(original_components, side['layout']['kind'], recipe['selection']))
        for name, mask in (('spatial_valid', inside), ('A_finite', np.isfinite(_values(a, VALUE)).all(axis=1)),
                           ('B_finite', np.isfinite(bv).all(axis=1))):
            _put(output.GetPointData(), name, np.asarray(mask, dtype=np.uint8))
        for name, source, key in (('A_original_components', a, ORIGINAL), ('B_sampled_original_components', b, ORIGINAL),
                                  ('A_common_components', a, VALUE), ('B_common_components', b, VALUE)):
            component_values = _values(source, key).copy()
            if source is b: component_values[~inside] = np.nan
            _put(output.GetPointData(), name, component_values)
        _put(output.GetPointData(), 'vtkValidPointMask', values['valid'].astype(np.uint8))
        output.GetInformation().Remove(vtk.vtkDataObject.DATA_TIME_STEP())
    else:
        raise ValueError('Unknown comparison stage')


def _filter(inputs, stage, settings, namespace, proxies):
    from . import analysis
    encoded = json.dumps(settings, ensure_ascii=True, allow_nan=False)
    script = ("import json\nfrom apps.desktop_post.comparison_native import execute\n"
              "execute([self.GetInputDataObject(0, i) for i in range(self.GetNumberOfInputConnections(0))], "
              "self.GetOutputDataObject(0), " + repr(stage) + ", json.loads(" + repr(encoded) + "))\n")
    if stage not in ('difference', 'frozen'):
        return analysis._program(inputs, script, namespace, stage, proxies)
    result = p.ProgrammableFilter(registrationName=analysis._name(namespace, stage), Input=inputs)
    proxies.append(result)
    result.Script = script
    # The values are frozen, while their physical sample clock is retained in
    # the owner declaration. Advertising upstream timesteps would invent data.
    result.RequestInformationScript = (
        "executive = self.GetExecutive()\n"
        "info = executive.GetOutputInformation(0)\n"
        "info.Remove(executive.TIME_STEPS())\n"
        "info.Remove(executive.TIME_RANGE())\n")
    result.UpdatePipeline()
    if analysis._times(result):
        raise ValueError('고정 결과가 원 reader의 시계열로 광고됩니다. 저장 측정으로 사용할 수 없습니다.')
    return result


def _side(source, side, plan, recipe, which, namespace, proxies):
    from . import analysis
    endpoints, originals = [], []
    for time in plan['times']:
        frozen = analysis._freeze(source, time, namespace, proxies); originals.append(frozen)
        endpoint = _filter(frozen, 'prepare', side, namespace, proxies)
        # ProgrammableFilter exceptions can be swallowed by VTK; verify required output.
        _values(analysis._fetch(endpoint), RAW)
        endpoints.append(endpoint)
    current = endpoints[0]
    if len(endpoints) == 2:
        # Host checks precede native execution too, with an actionable error.
        if geometry(analysis._fetch(endpoints[0]))[2] != geometry(analysis._fetch(endpoints[1]))[2]:
            raise ValueError('시간 구간의 메시/좌표가 달라져 보간할 수 없습니다.')
        current = _filter(endpoints, 'temporal', {'weight': plan['weights'][1]}, namespace, proxies)
    alignment = recipe['alignment']
    settings = {'side': side, 'recipe': recipe,
        'geometry_rotation': alignment['geometry_rotation'] if which == 'b' else physical.IDENTITY,
        'response_rotation': alignment['response_rotation'] if which == 'b' else physical.IDENTITY,
        'translation': alignment['translation'] if which == 'b' else [0., 0., 0.]}
    result = _filter(current, 'transform', settings, namespace, proxies)
    _values(analysis._fetch(result), VALUE)
    return result, originals[0]


def build(a, b, recipe, namespace):
    from . import analysis
    before = analysis._preserve_active()
    bundle = {'proxies': [], 'source': None}
    try:
        from paraview import servermanager
        connection = servermanager.ActiveConnection
        if connection is not None and connection.Session.GetNumberOfProcesses(1) != 1:
            raise ValueError('이 비교는 로컬 단일 ParaView 프로세스 자료에서 지원합니다.')
        plans = physical.validate(recipe, analysis._times(a), analysis._times(b))
        af, original_a = _side(a, recipe['a'], plans[0], recipe, 'a', namespace, bundle['proxies'])
        bf, original_b = _side(b, recipe['b'], plans[1], recipe, 'b', namespace, bundle['proxies'])
        ad, bd = analysis._fetch(af), analysis._fetch(bf)
        ag, bg = geometry(ad), geometry(bd)
        sample = bf
        correspondence = None
        if recipe['method'] == 'same_mesh':
            correspondence = physical.ordered_match(ag[0], ag[1], bg[0], bg[1], recipe['tolerance'])
            correspondence['coordinate_units'] = recipe['a']['coordinate_units']
        else:
            analysis._mesh(bd)  # The admitted spatial interpolator remains linear tetra only.
            sample = p.ResampleWithDataset(registrationName=analysis._name(namespace, 'mapped B'),
                                          SourceDataArrays=bf, DestinationMesh=af)
            bundle['proxies'].append(sample)
            for key, value in {'ComputeTolerance': 0, 'Tolerance': recipe['tolerance'],
                'SnapToCellWithClosestPoint': 0, 'MarkBlankPointsAndCells': 0,
                'PassPointArrays': 0, 'PassCellArrays': 0, 'PassFieldArrays': 0, 'CategoricalData': 0}.items():
                if key not in sample.ListProperties():
                    raise ValueError('설치된 ParaView가 필요한 공간 보간 속성을 제공하지 않습니다: ' + key)
                setattr(sample, key, value)
            sample.UpdatePipeline()
        output = _filter([af, sample, original_a], 'difference', recipe, namespace, bundle['proxies'])
        bundle['source'] = output
        data = analysis._fetch(output)
        if geometry(data)[2] != ag[2]:
            raise ValueError('비교 결과의 A 위치 대응이 바뀌었습니다.')
        # Required tuples/masks must exist even if VTK logged a script error.
        for name in analysis.OUTPUT_ARRAYS.values(): analysis._scalar(data, name)
        summary = {'comparison_version': 2, 'recipe': deepcopy(recipe), 'arrays': deepcopy(analysis.OUTPUT_ARRAYS),
            'point_count': len(ag[0]), 'cell_count': len(ag[1]), 'mesh_hash_a': ag[2], 'mesh_hash_b': bg[2],
            'ordered_correspondence': correspondence,
            'source_geometry_hash_a': geometry(analysis._fetch(original_a))[2],
            'source_geometry_hash_b': geometry(analysis._fetch(original_b))[2],
            'input_hash_a': analysis._values_hash(_values(ad, VALUE)),
            'input_hash_b': analysis._values_hash(_values(bd, VALUE)),
            'original_a_id_arrays': analysis._identity_arrays(analysis._fetch(original_a).GetPointData()),
            'order': physical.ORDER, 'time_plans': plans, 'qualification': 'UNQUALIFIED',
            'percent_definition': recipe.get('percent', 'disabled'),
            'sample_semantics': 'transformed_B_sampled_at_A',
            'declarations': declarations(recipe)}
        bundle['summary'] = summary
        summary.update(analysis._comparison_fingerprint(data, version=2))
        summary['graph'] = analysis.graph_signature(bundle)
        return bundle
    except BaseException:
        analysis.cleanup(bundle)
        raise
    finally:
        analysis._restore_active(before)


def declarations(recipe):
    a = recipe['a']
    row = {key: a[key] for key in ('quantity', 'measure', 'frame')}
    row.update(units=recipe['target']['units'], association='POINTS',
               layout={'kind': 'scalar', 'components': ['scalar']},
               validity_masks=['comparison_valid'])
    arrays = []
    for name in ('A_original', 'B_at_A', 'B_minus_A'):
        current = dict(row, name=name)
        current['validity_masks'] = [{'A_original': 'A_finite', 'B_at_A': 'B_finite', 'B_minus_A': 'comparison_valid'}[name]]
        current['layout'] = {'kind': 'scalar', 'components': ['scalar'], 'scalar_semantics':
            ('invariant' if recipe['selection'] == 'magnitude' or name == 'B_minus_A' and recipe.get('difference') == 'norm_of_difference'
             else a['layout'].get('scalar_semantics') if recipe['selection'] == 'scalar' else 'component')}
        if name == 'B_minus_A' and a.get('temperature_kind') == 'absolute':
            current['temperature_kind'] = 'difference'
        else:
            current['temperature_kind'] = a.get('temperature_kind')
        arrays.append(current)
    clock = recipe.get('clock', {})
    frozen_clock = {key: clock[key] for key in ('value', 'unit', 'semantics')} if clock.get('value') is not None else None
    return {'coordinate_units': a['coordinate_units'], 'coordinate_frame': a['coordinate_frame'],
            'arrays': arrays, 'time': None, 'frozen_clock': frozen_clock, 'sample_clock': deepcopy(clock),
            'derivation': 'comparison_v2', 'selection': recipe['selection']}
