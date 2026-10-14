"""Native table branch of the existing Post comparison owner."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import uuid
import numpy as np
from paraview import simple as p, servermanager
from caelab import post_curves as curves, post_comparison as physical
from caelab.post_observation import choices, measurement_columns, saved_record
from . import analysis, measurements, external


def _rows(source):
    rows, total = [], None
    while total is None or len(rows) < total:
        page = measurements.sample_data(source, offset=len(rows), limit=1000)
        total = page['total']
        if not 1 <= total <= curves.MAX_ROWS or not page['rows']:
            raise ValueError('시간표는 1–20000개의 실제 저장 행이어야 합니다.')
        rows.extend(page['rows'])
    return rows


def _saved_measurement(ws, ref):
    obj = ws.object(ref)
    record, bundle = ws._bundle(obj)
    if obj['kind'] != 'measurement' or record['recipe'].get('measurement') not in ('time', 'contact_force'):
        raise ValueError('적용하고 저장한 시간 이력 또는 접촉 힘 이력을 선택하세요.')
    if obj['draft'] != record['recipe']:
        raise ValueError('먼저 이 측정의 미적용 변경을 적용하고 저장하세요.')
    if ws.owner.project_path.stat().st_size > curves.MAX_BYTES:
        raise ValueError('저장 Post 문서가 곡선 인도 한도를 초과합니다.')
    project = json.loads(ws.owner.project_path.read_text(encoding='utf-8-sig'))
    _, saved = saved_record(project, ref, record['id'])
    if saved['recipe'] != record['recipe'] or saved['graph'] != record['graph']:
        raise ValueError('현재 측정 결과를 저장한 뒤 비교하세요.')
    ws._verify_result_pins(saved['result_files'])
    if external.sha(Path(saved['result_file'])) != saved['result_sha256']:
        raise ValueError('저장된 측정값 파일이 바뀌었습니다.')
    return obj, saved, bundle


def options(ws, ref):
    """Actual block/columns only. Values never travel in the catalog receipt."""
    ws._verify_inputs([ref])
    if ref in ws.document['sources']:
        record = ws.document['sources'][ref]
        curve, _ = curves.load_curve(record['entry_path'], record.get('native_metadata'))
        return [{'source_ref': ref, 'label': record.get('label', curve['title']),
            'block': [], 'column': 'value', 'component': 0, 'axis_column': 'axis',
            'declaration': deepcopy(curve['declaration']), 'axis': deepcopy(curve['axis']),
            'row_count': len(curve['rows']), 'revision': record['source_revision']}]
    obj, record, bundle = _saved_measurement(ws, ref)
    recipe, summary = record['recipe'], record['summary']
    rows = _rows(bundle['source'])
    snapshot = {'recipe': recipe, 'rows': rows}
    available, columns = choices(snapshot), measurement_columns(snapshot)
    declaration = deepcopy(summary.get('selected_declaration') or
                           {k: recipe.get(k) for k in ('units', 'quantity', 'frame', 'measure', 'observable', 'layout')})
    result = []
    for block in available['blocks']:
        blockrows = [row for row in rows if row['block'] == block]
        for column, meaning in columns.items():
            if not all(column in r['values'] for r in blockrows):
                continue
            count = available['arrays'][column]
            for component in range(count):
                d = deepcopy(declaration)
                selection = meaning['component'] if meaning['component'] is not None else component
                if d.get('layout'):
                    layout = d['layout']
                    if layout.get('kind') != 'scalar':
                        selection = 'magnitude' if selection == 'Magnitude' else layout['components'][int(selection)]
                        d['observable'] = physical.observable_value(layout['kind'], selection)
                d.setdefault('observable', deepcopy(physical.UNKNOWN_OBSERVABLE))
                if d.get('observable') is None:
                    d['observable'] = deepcopy(physical.UNKNOWN_OBSERVABLE)
                d['reduction'] = meaning['statistic']
                d['location'] = obj.get('title', '측정') + ' / 위치 ' + str(available['blocks'].index(block)+1)
                for axis in ('Time', recipe.get('axis_name', 'load_parameter')):
                    if axis not in available['arrays'] or available['arrays'][axis] != 1:
                        continue
                    if any(r['values'].get(axis) is None for r in blockrows):
                        continue
                    result.append({'source_ref': ref, 'label': obj.get('title', '측정'),
                        'block': block, 'column': column, 'component': component,
                        'axis_column': axis, 'declaration': d,
                        'axis': {'name': axis, 'unit': recipe.get('time_units', summary.get('time_units')),
                                 'semantics': recipe.get('time_origin', summary.get('time_origin'))},
                        'row_count': len(blockrows), 'revision': record['id']})
    return result


def catalog(ws):
    results, issues = [], []
    for ref, item in ws.document['sources'].items():
        if (item.get('native_metadata') or {}).get('curve'):
            try:
                results.extend(options(ws, ref))
            except (ValueError, OSError, RuntimeError) as error:
                issues.append({'label': item.get('label', '시험'), 'message': str(error)})
    for obj in ws.state['objects'].values():
        if obj['kind'] == 'measurement' and (ws.applied(obj) or {}).get('recipe', {}).get('measurement') in ('time', 'contact_force'):
            try:
                results.extend(options(ws, obj['id']))
            except (ValueError, OSError, RuntimeError) as error:
                issues.append({'label': obj.get('title', '측정'), 'message': str(error)})
    if len(results) > 1024:
        raise ValueError('곡선 선택지가 1024개를 초과합니다. 측정 위치를 나누어 저장하세요.')
    return {'curves': results, 'issues': issues}


def selected(ws, side):
    key = ('source_ref', 'block', 'column', 'component', 'axis_column', 'revision')
    option = next((item for item in options(ws, side['source_ref'])
                   if all(item.get(k) == side.get(k) for k in key)), None)
    if option is None:
        raise ValueError('선택한 위치·성분·축의 저장 개정이 바뀌었습니다. 자료를 다시 선택하세요.')
    ref = side['source_ref']
    if ref in ws.document['sources']:
        record = ws.document['sources'][ref]
        curve, _ = curves.load_curve(record['entry_path'], record['native_metadata'])
        return curve
    obj, record, bundle = _saved_measurement(ws, ref)
    rawrows = [r for r in _rows(bundle['source']) if r['block'] == option['block']]
    rows = []
    for r in rawrows:
        values = r['values']; value = values[option['column']]
        value = value[option['component']] if isinstance(value, list) else value
        # Field-specific quality has already been applied before native time
        # sampling. Never substitute another curve's common comparison mask.
        rows.append({'identity': {'block': r['block'], 'row': r['row']},
            'x': curves.numeric(values[option['axis_column']]), 'y': curves.numeric(value),
            'raw_x': values[option['axis_column']], 'raw_y': value,
            'quality': True, 'calculation': True, 'visible': True,
            'quality_reason': '', 'exclusion_reason': '', 'segment': 0})
    return {'version': 1, 'kind': 'retained_curve', 'title': obj.get('title', '측정'),
        'origin': {'document_id': ws.owner.document_id, 'object_ref': ref, 'revision': record['id'],
                   'recipe': deepcopy(record['recipe']), 'result_sha256': record['result_sha256']},
        'declaration': deepcopy(option['declaration']), 'axis': deepcopy(option['axis']), 'rows': rows}


def build(ws, recipe, namespace):
    a, b = selected(ws, recipe['a']), selected(ws, recipe['b'])
    result = curves.compare(a, b, recipe)
    # All originals and correspondence are stored in native table columns. The
    # owner bindings still depend on both pinned inputs; frozen values cannot hide
    # external changes from Workspace's normal graph/input guards.
    count = max(len(result['a']['rows']), len(result['b']['rows']))
    columns = {}
    for tag in ('a', 'b'):
        for name in ('x', 'y', 'raw_x', 'raw_y', 'identity', 'quality', 'calculation',
                     'visible', 'quality_reason', 'exclusion_reason', 'segment'):
            columns[tag+'_'+name] = [r.get(name) for r in result[tag]['rows']] + [None]*(count-len(result[tag]['rows']))
    aligned = result['rows']
    for key in ('x', 'a', 'b', 'delta', 'percent', 'valid', 'reason', 'percent_reason', 'a_row', 'b_rows', 'b_axis', 'weight', 'a_valid', 'b_valid', 'a_segment', 'b_segment'):
        columns['aligned_'+key] = [r.get(key) for r in aligned] + [None]*(count-len(aligned))
    columns['b_common_x'] = result.get('b_axis', []) + [None]*(count-len(result.get('b_axis', [])))
    for tag in ('a', 'b'):
        vals = result.get(tag+'_values', [])
        columns[tag+'_common_y'] = vals + [None]*(count-len(vals))
    numeric = {name for name in columns if name.endswith(('_x', '_y', '_quality', '_calculation',
        '_visible', '_segment')) or name in ('aligned_x', 'aligned_a', 'aligned_b', 'aligned_delta',
        'aligned_percent', 'aligned_valid', 'aligned_weight', 'aligned_a_valid', 'aligned_b_valid',
        'aligned_a_segment', 'aligned_b_segment')}
    # Raw acquisition strings and identities are stored as JSON string arrays.
    numeric -= {'a_raw_x', 'a_raw_y', 'b_raw_x', 'b_raw_y'}
    payload = json.dumps(columns, ensure_ascii=False, allow_nan=False)
    if len(payload.encode()) > curves.MAX_BYTES:
        raise ValueError('비교 출력이 16 MiB를 초과합니다. 비교 원행 구간을 줄이세요.')
    # Materialize a bounded native table in this existing project's exports.
    # Keeping the values out of proxy Script properties prevents the descriptor
    # and native completion receipt from growing with every saved sample.
    from vtkmodules.vtkCommonCore import vtkDoubleArray, vtkStringArray
    from vtkmodules.vtkCommonDataModel import vtkTable
    from vtkmodules.vtkIOXML import vtkXMLTableWriter
    table = vtkTable()
    for name, values in columns.items():
        array = vtkDoubleArray() if name in numeric else vtkStringArray()
        array.SetName(name)
        for value in values:
            array.InsertNextValue((float(value) if value is not None else math.nan) if name in numeric
                                  else json.dumps(value, ensure_ascii=False, allow_nan=False))
        table.AddColumn(array)
    folder = Path(ws.document['project_root']) / 'exports'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ('curve-' + uuid.uuid4().hex + '.vtt')
    writer = vtkXMLTableWriter()
    writer.SetFileName(str(path)); writer.SetInputData(table)
    writer.SetDataModeToBinary(); writer.SetCompressorTypeToNone()
    if writer.Write() != 1 or not path.is_file():
        raise ValueError('곡선 native 표를 저장하지 못했습니다.')
    before = p.GetActiveSource(), p.GetActiveView()
    source = None
    try:
        source = p.XMLTableReader(registrationName=namespace + ' curve ' + uuid.uuid4().hex[:8], FileName=[str(path)])
        source.UpdatePipeline()
        summary = {'comparison_version': 3, 'recipe': deepcopy(recipe), 'blocked': result['blocked'],
            'count_a': len(result['a']['rows']), 'count_b': len(result['b']['rows']), 'count_aligned': len(aligned),
            'valid_count': sum(r['valid'] for r in aligned),
            'sources': {key: {k: deepcopy(result[key][k]) for k in ('title', 'origin', 'declaration', 'axis', 'selected_rows')
                             if k in result[key]} for key in ('a', 'b')},
            'arrays': {'a': 'a_common_y', 'b': 'b_common_y', 'delta': 'aligned_delta'},
            'qualification': 'UNKNOWN', 'percent_definition': '100*(B-A)/abs(A); absolute temperature disabled'}
        summary.update(fingerprint(servermanager.Fetch(source)))
        return {'source': source, 'proxies': [source], 'summary': summary}
    except BaseException:
        if source is not None:
            p.Delete(source)
        raise
    finally:
        p.SetActiveSource(before[0]); p.SetActiveView(before[1])


def fingerprint(table):
    if not table.IsA('vtkTable'):
        raise ValueError('곡선 비교의 실제 출력은 vtkTable이어야 합니다.')
    columns = []
    for i in range(table.GetNumberOfColumns()):
        a = table.GetColumn(i)
        if a.IsA('vtkDataArray'):
            try:
                from paraview.vtk.util.numpy_support import vtk_to_numpy
            except ImportError:
                from vtk.util.numpy_support import vtk_to_numpy
            values = np.asarray(vtk_to_numpy(a), dtype='<f8').copy()
            values[np.isnan(values)] = np.nan
            checksum = hashlib.sha256(values.tobytes()).hexdigest()
        else:
            values = [a.GetVariantValue(j).ToString() for j in range(a.GetNumberOfValues())]
            checksum = hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()
        columns.append([a.GetName(), a.GetDataTypeAsString(), a.GetNumberOfComponents(), a.GetNumberOfTuples(), checksum])
    return {'output_hash': hashlib.sha256(json.dumps(columns, ensure_ascii=False).encode()).hexdigest()}


def sample(bundle, *, offset=0, limit=100, row_index=None, point_index=None):
    if point_index is not None:
        raise ValueError('시간표는 공간 점 번호가 아니라 원행을 선택합니다.')
    table = servermanager.Fetch(bundle['source']); summary = bundle['summary']
    if row_index is not None:
        offset, limit = row_index, 1
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('1–1000행 범위를 선택하세요.')
    def value(name, i):
        array = table.GetColumnByName(name)
        if array is None:
            raise ValueError('저장 곡선 열이 없습니다: ' + name)
        if array.IsA('vtkStringArray'):
            return json.loads(array.GetValue(i))
        v = array.GetTuple1(i)
        return v if math.isfinite(v) else None
    end = min(table.GetNumberOfRows(), offset+limit)
    raw = {}
    for tag in ('a', 'b'):
        raw[tag] = [{'row_index': i, **{key: value(tag+'_'+key, i) for key in
            ('x', 'y', 'raw_x', 'raw_y', 'identity', 'quality', 'calculation', 'visible',
             'quality_reason', 'exclusion_reason', 'segment')},
            'common_x': value('b_common_x', i) if tag == 'b' else value('a_x', i),
            'common_y': value(tag+'_common_y', i)}
            for i in range(offset, min(end, summary['count_'+tag]))]
    rows = [{'row_index': i, **{key: value('aligned_'+key, i) for key in
        ('x', 'a', 'b', 'delta', 'percent', 'valid', 'reason', 'percent_reason', 'a_row', 'b_rows', 'b_axis', 'weight',
         'a_valid', 'b_valid', 'a_segment', 'b_segment')}}
        for i in range(offset, min(end, summary['count_aligned']))]
    return {'rows': rows, 'originals': raw, 'total': table.GetNumberOfRows(), 'offset': offset,
            'limit': limit, 'semantics': 'retained_curve_comparison', 'summary': deepcopy(summary)}
