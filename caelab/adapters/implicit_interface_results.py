"""Retain native joint integration-point tractions and nine CZM variables.

No continuous damage scalar, total dissipation, current-configuration traction
or Maxwell time response is inferred from these native channels.
"""
from pathlib import Path
import json
import math
from .codeaster_worker import _table, _table_identifier, _identifier, _field_order, _finite
from .frozen_fem import _read, _sha
from ..implicit_interface import SOURCE
from ..storage import canonical_hash

BACKEND = 'structure.codeaster.implicit_interface'

TRACTIONS = ('SIGN', 'SITX', 'SITY')
VARIABLES = {
    'V1': ('SEUILDEP', 'mm', 'irreversible equivalent separation threshold'),
    'V2': ('INDIDISS', '1', 'native dissipation indicator'),
    'V3': ('INDIENDO', '1', 'native state: 0=intact, 1=damaged, 2=broken; not continuous damage'),
    'V4': ('PCENERDI', '1', 'native min(1,kappa/lc); not continuous damage'),
    'V5': ('DISSIP', 'N/mm', 'native cohesive dissipation per area with initial offset'),
    'V6': ('ENEL_RES', 'N/mm', 'native cohesive residual energy per area; excludes compression energy'),
    'V7': ('SAUT_N', 'mm', 'native signed local normal jump'),
    'V8': ('SAUT_T1', 'mm', 'native local first tangential jump'),
    'V9': ('SAUT_T2', 'mm', 'native local second tangential jump'),
}
COORDINATES = ('COOR_X','COOR_Y','COOR_Z')


def _observed(value, label):
    if value is None or (isinstance(value,dict) and set(value) == {'invalid_numeric'}
                         and value['invalid_numeric'] in ('nan','inf','-inf')):
        return None
    return _finite(value,label)


def point_fields(tables, native_joint_cells, order, load_parameter, *, complete=True):
    """Decode actual internal cell IDs and FPG4 point identities.

    native_joint_cells maps actual 1-based imported cell indices to source
    interface/element IDs. Coordinates come from the tables, never centroids.
    Missing partial data stay unknown, with no fabricated zero-valued rows.
    """
    if type(order) is not int or order < 0:
        raise ValueError('원 native 저장 증분은 0 이상의 실제 정수여야 합니다.')
    parameter = _finite(load_parameter,'native static load parameter')
    if not isinstance(native_joint_cells,dict) or not native_joint_cells:
        raise ValueError('원 native joint 요소 목록이 필요합니다.')
    imported = {}
    for key,value in native_joint_cells.items():
        native = _identifier(key,'native cell index') if type(key) is int else _table_identifier(key,'native cell index')
        if native in imported:
            raise ValueError('원 native joint 요소 번호가 중복됐습니다.')
        imported[native] = value
    native_joint_cells = imported
    fields = {}
    for field,components in (('SIEF_ELGA',TRACTIONS),('VARI_ELGA',tuple(VARIABLES))):
        value = tables.get(field)
        if value is None and not complete:
            fields[field] = {}
            continue
        table,count = _table(value,('MAILLE','POINT','SOUS_POINT','NUME_ORDRE',*COORDINATES,*components),field)
        rows = {}
        for i in range(count):
            native = _table_identifier(table['MAILLE'][i],field+' MAILLE')
            point = _identifier(table['POINT'][i],field+' POINT')
            subpoint = _identifier(table['SOUS_POINT'][i],field+' SOUS_POINT')
            key = native,point,subpoint
            if native not in native_joint_cells or point not in (1,2,3,4) or subpoint != 1 or key in rows:
                raise ValueError('원 joint 요소·적분점이 중복됐거나 선택 영역과 다릅니다.')
            _field_order(table,i,order,field)
            if 'INST' in table and _finite(table['INST'][i],field+' INST') != parameter:
                raise ValueError('원 계면 결과의 하중 진행값이 다릅니다.')
            row = dict(coordinates_mm=[_finite(table[k][i],field+' coordinate') for k in COORDINATES],
                       values={k:_observed(table[k][i],field+' '+k) for k in components})
            if field == 'VARI_ELGA' and row['values']['V3'] not in (None,0.,1.,2.):
                raise ValueError('CZM_LIN_REG의 원 손상 상태 표시가 0, 1, 2와 다릅니다.')
            rows[key] = row
        expected = {(n,p,1) for n in native_joint_cells for p in (1,2,3,4)}
        if complete and set(rows) != expected:
            raise ValueError('각 원 joint 요소의 실제 네 적분점이 모두 필요합니다.')
        fields[field] = rows
    output = []
    for native in native_joint_cells:
        for point in (1,2,3,4):
            stress = fields['SIEF_ELGA'].get((native,point,1))
            state = fields['VARI_ELGA'].get((native,point,1))
            if stress and state and stress['coordinates_mm'] != state['coordinates_mm']:
                raise ValueError('계면 응력과 내부변수의 원 적분점 위치가 다릅니다.')
            values = {k:None for k in (*TRACTIONS,*VARIABLES)}
            if stress:
                values.update(stress['values'])
            if state:
                values.update(state['values'])
            source = native_joint_cells[native]
            output.append(dict(native_cell_index=native,element_id=source['element_id'],
                interface_id=source['interface_id'],point=point,subpoint=1,
                coordinates_mm=(stress or state)['coordinates_mm'] if stress or state else None,
                values=values,valid_mask={k:v is not None for k,v in values.items()},
                basis='NATIVE_JOINT_LOCAL',value_origin='NATIVE',
                quadrature='QU4_FPG4',coordinate_configuration='REFERENCE'))
    return output


def history(raw, native_joint_cells):
    """Keep actual accepted native orders/parameters and flag lost state."""
    if raw.get('versions',{}).get('code_aster') != '17.4.0' or raw.get('source_commit') != SOURCE:
        raise ValueError('현재 계면 reader에는 고정 Code_Aster 17.4.0 원 결과가 필요합니다.')
    orders = raw.get('available_orders')
    access = raw.get('access_parameters',{})
    if (not isinstance(orders,list) or not orders or len(set(orders)) != len(orders)
            or access.get('NUME_ORDRE') != orders or not isinstance(access.get('INST'),list)
            or len(access['INST']) != len(orders)):
        raise ValueError('실제 계면 결과의 저장 증분과 하중 진행값이 불완전합니다.')
    parameters = [_finite(v,'native static load parameter') for v in access['INST']]
    if any(b <= a for a,b in zip(parameters,parameters[1:])):
        raise ValueError('원 결과의 실제 하중 진행값이 증가하지 않습니다.')
    states = raw.get('states')
    if not isinstance(states,list) or [r['order'] for r in states] != orders:
        raise ValueError('보존한 계면 표가 실제 native 증분과 다릅니다.')
    complete = raw.get('solver_status') == 'COMPLETED' and raw.get('converged') is True
    output, previous, diagnostics = [], {}, []
    for state,order,parameter in zip(states,orders,parameters):
        rows = point_fields(state['tables'],native_joint_cells,order,parameter,complete=complete)
        for row in rows:
            key = row['native_cell_index'],row['point'],row['subpoint']
            kappa = row['values']['V1']
            old = previous.get(key)
            if old is not None and kappa is not None and kappa < old:
                diagnostics.append(dict(code='IRREVERSIBLE_THRESHOLD_DECREASE',order=order,
                    element_id=row['element_id'],point=row['point'],previous=old,observed=kappa))
            if kappa is not None:
                previous[key] = kappa
        output.append(dict(order=order,load_parameter=parameter,points=rows))
    return dict(steps=output,diagnostics=diagnostics,
        axis=dict(name='load_parameter',unit='1',semantics='STATIC_LOAD_PARAMETER_NOT_PHYSICAL_TIME'),
        original_solver_status=raw.get('solver_status'),complete=complete,
        qualification='UNKNOWN',decision='NOT_RELEASED')


def parse(raw,model,catalog):
    """Bind native cell/point/nodal tables to this exact prepared user model."""
    guard = raw['native_mesh_checks']
    if guard.get('status') != 'PASS':
        raise ValueError('원 native 계면 메시 검사를 확인하세요.')
    names = guard['cell_names_in_native_order']
    if len(names) != len(catalog['cells']) or len(set(names)) != len(names) or set(names) != set(catalog['cells']):
        raise ValueError('실제 native 요소 목록과 원 계면 입력이 다릅니다.')
    expected = {i:dict(element_id=catalog['cells'][cell]['element_id'],interface_id=catalog['cells'][cell]['interface_id'])
                for i,cell in enumerate(names,1) if catalog['cells'][cell].get('joint')}
    if {int(k):v for k,v in guard.get('native_joint_cells',{}).items()} != expected:
        raise ValueError('원 joint 요소와 실제 native 요소의 관계가 다릅니다.')
    parsed = history(raw,expected)
    geometry = {j['element_id']:j for interface in catalog['interfaces'].values() for j in interface['joints']}
    node_order = guard['node_ids_in_native_order']
    nodes = {r['node_id']:r['position_mm'] for r in model['nodes']}
    if len(node_order) != len(nodes) or len(set(node_order)) != len(nodes) or set(node_order) != set(nodes):
        raise ValueError('실제 native 절점 목록과 원 고체 메시가 다릅니다.')
    for state,step in zip(raw['states'],parsed['steps']):
        for point in step['points']:
            sample = geometry[point['element_id']]['quadrature'][point['point']-1]
            observed = point['coordinates_mm']
            if observed is not None and any(not math.isclose(a,b,rel_tol=1e-13,abs_tol=1e-13)
                                             for a,b in zip(observed,sample['coordinates_mm'])):
                raise ValueError('원 FPG4 적분점과 실제 native 계면 결과 위치가 다릅니다.')
            point['reference_basis_rows'] = [sample[k] for k in ('normal','tangent1','tangent2')]
            point['reference_basis_verified'] = observed is not None
        fields = {}
        for field in ('DEPL','REAC_NODA'):
            table,count = _table(state['tables'].get(field),('NOEUD','NUME_ORDRE','DX','DY','DZ'),field)
            values = {}
            for i in range(count):
                index = _table_identifier(table['NOEUD'][i],field+' NOEUD')-1
                if not 0 <= index < len(node_order) or str(node_order[index]) in values:
                    raise ValueError('원 고체의 native 절점 결과 행이 중복됐거나 없습니다.')
                _field_order(table,i,step['order'],field)
                node = node_order[index]
                for axis,key in enumerate(COORDINATES):
                    if key in table and not math.isclose(_finite(table[key][i],key),nodes[node][axis],rel_tol=1e-13,abs_tol=1e-13):
                        raise ValueError('원 고체와 실제 native 절점 결과 위치가 다릅니다.')
                values[str(node)] = {k:_finite(table[k][i],field+' '+k) for k in ('DX','DY','DZ')}
            if set(values) != {str(n) for n in nodes}:
                raise ValueError('원 고체의 실제 변위·반력 절점 결과가 빠졌습니다.')
            fields[field] = values
        step['fields'] = fields
    return {**parsed,'model_sha256':canonical_hash(model),'source_commit':SOURCE,
            'coordinate_frame':'FREECAD_DOCUMENT_GLOBAL'}


def context(output):
    from .implicit_interface_aster import validate_snapshot
    root = Path(output)
    receipt = json.loads(_read(root/'interface_execution.json'))
    if receipt['execution_status'] != 'SUCCEEDED':
        raise ValueError('완료된 계면 결과를 선택하세요. 원 실패와 부분 출력은 보존됩니다.')
    for pin in receipt['artifacts']:
        path = root/pin['relative']
        if not path.resolve().is_relative_to(root.resolve()) or len(_read(path)) != pin['bytes'] or _sha(path) != pin['sha256']:
            raise ValueError('보존한 원 계면 결과 파일이 바뀌었습니다.')
    _,model,_,_ = validate_snapshot(root/'frozen_input/snapshot.json')
    config = json.loads(_read(root/'solver/input.json'))
    raw = json.loads(_read(root/'solver/worker_result.json'))
    if raw['input_sha256'] != _sha(root/'solver/input.json') or raw['mail_sha256'] != _sha(root/'solver/mesh.mail'):
        raise ValueError('계면 입력과 원 결과의 관계가 다릅니다.')
    parsed = parse(raw,model,config['catalog'])
    if parsed != json.loads(_read(root/'interface_fields.json')):
        raise ValueError('원 native 계면 표와 보존한 읽기 결과가 다릅니다.')
    return receipt,model,parsed


def _catalog(receipt,model,parsed,root):
    result = {}
    source = dict(backend=BACKEND,artifact='interface_fields.json',sha256=_sha(root/'interface_fields.json'),
        sha256_kind='ARTIFACT_SHA256',manifest_sha256=canonical_hash(receipt['artifacts']),
        model_revision=parsed['model_sha256'],value_origin='NATIVE')
    for definition in model['interfaces']:
        identifier = definition['object_id']
        locations = [dict(element_id=r['element_id'],point=r['point'],coordinates_mm=r['coordinates_mm'])
                     for r in parsed['steps'][-1]['points'] if r['interface_id'] == identifier]
        for token in (*TRACTIONS,*VARIABLES):
            unit = 'MPa' if token in TRACTIONS else VARIABLES[token][1]
            result[identifier+'.'+token] = dict(kind='series',unit=unit,component=token,
                interface_id=identifier,location=definition['label']+' / 원 적분점',locations=locations,
                selector_template=identifier+'.'+token+'@<joint_element_id>:<native_point>',
                coordinate_frame='NATIVE_JOINT_LOCAL',axes=[parsed['axis']],reduction='none',
                quantity='native local interface traction' if token in TRACTIONS else VARIABLES[token][2],
                source={**source,'native_origin':'SIEF_ELGA' if token in TRACTIONS else 'VARI_ELGA'},
                qualification='UNKNOWN',original_execution_status=receipt['execution_status'])
    return result


def catalog(outcome,output):
    receipt,model,parsed = context(output)
    return _catalog(receipt,model,parsed,Path(output))


def read(outcome,output,selector,*,start=None,stop=None):
    receipt,model,parsed = context(output)
    descriptors = _catalog(receipt,model,parsed,Path(output))
    group,separator,location = selector.partition('@')
    element,colon,point = location.partition(':')
    if not separator or group not in descriptors or not colon or not element.isdecimal() or not point.isdecimal():
        raise ValueError('정확한 계면과 원 joint 요소·적분점·성분을 선택하세요.')
    descriptor = descriptors[group]
    element,point = int(element),int(point)
    start = 0 if start is None else start
    stop = len(parsed['steps']) if stop is None else stop
    if type(start) is not int or type(stop) is not int or not 0 <= start < stop <= len(parsed['steps']):
        raise ValueError('실제 저장 증분의 유효한 구간을 선택하세요.')
    values = []
    for step in parsed['steps'][start:stop]:
        rows = [r for r in step['points'] if r['interface_id'] == descriptor['interface_id']
                and r['element_id'] == element and r['point'] == point]
        if len(rows) != 1:
            raise ValueError('선택한 원 계면 요소·적분점이 보존 결과에 없습니다.')
        values.append(rows[0]['values'][descriptor['component']])
    mask = [v is not None for v in values]
    return {**descriptor,'value':values,'valid_mask':mask,'mask':mask,
        'status':'AVAILABLE' if all(mask) else 'UNKNOWN',
        'axes':[{**parsed['axis'],'values':[s['load_parameter'] for s in parsed['steps'][start:stop]]}],
        'source':{**descriptor['source'],'selector':selector,'sample_slice':[start,stop]}}


def write_post(output,model,parsed):
    from .contact_aster_results import write_post as bulk_post
    from apps.desktop_post.prepare import data_array
    import xml.etree.ElementTree as ET
    primary,secondary = bulk_post(output,model,parsed)
    step = parsed['steps'][-1]
    for definition in model['interfaces']:
        points = [r for r in step['points'] if r['interface_id'] == definition['object_id']]
        if any(r['coordinates_mm'] is None for r in points):
            continue
        path = Path(output)/'post'/(definition['object_id']+'.vtu')
        vtk = ET.Element('VTKFile',type='UnstructuredGrid',version='0.1',byte_order='LittleEndian')
        piece = ET.SubElement(ET.SubElement(vtk,'UnstructuredGrid'),'Piece',NumberOfPoints=str(len(points)),NumberOfCells=str(len(points)))
        data_array(ET.SubElement(piece,'Points'),'Position_mm',(v for r in points for v in r['coordinates_mm']),3)
        cells = ET.SubElement(piece,'Cells')
        for name,values in [('connectivity',range(len(points))),('offsets',range(1,len(points)+1)),('types',[1]*len(points))]:
            data_array(cells,name,values,integer=True)
        data = ET.SubElement(piece,'PointData')
        arrays = []
        for token in (*TRACTIONS,*VARIABLES):
            values = [r['values'][token] for r in points]
            data_array(data,token,[math.nan if v is None else v for v in values])
            data_array(data,token+'_valid',[int(v is not None) for v in values],integer=True)
            arrays.append(dict(name=token,association='POINTS',components=1,
                units='MPa' if token in TRACTIONS else VARIABLES[token][1],frame='NATIVE_JOINT_LOCAL',
                measure='native_joint_'+token,valid_mask_array=token+'_valid'))
        for name,values in [('NativeElementId',[r['element_id'] for r in points]),('NativePointId',[r['point'] for r in points])]:
            data_array(data,name,values,integer=True)
        ET.ElementTree(vtk).write(path,encoding='utf-8',xml_declaration=True)
        secondary.append(dict(relative=path.relative_to(output).as_posix(),bytes=path.stat().st_size,sha256=_sha(path),
            native_metadata=dict(coordinate_units='mm',coordinate_frame='FREECAD_DOCUMENT_GLOBAL',
                static=dict(step=1,increment=step['order'],load_parameter=step['load_parameter']),
                location='NATIVE_INTEGRATION_POINTS_QU4_FPG4',arrays=arrays)))
    return primary,secondary
