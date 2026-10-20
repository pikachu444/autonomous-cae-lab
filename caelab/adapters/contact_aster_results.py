"""Exact retained 17.4 contact tables, sparse values and existing result selectors."""
import json, math, hashlib
from pathlib import Path
from xml.etree import ElementTree as ET
from .contact_aster_worker import DISPLACEMENT, CONTACT_COMPONENTS, MULTIPLIERS, VERSION, SOURCE
from .contact_aster_model import BACKEND, surface_nodes, validate_snapshot
from .codeaster_worker import _table, _table_identifier, _field_order, _finite
from .frozen_fem import _read, _sha
from ..storage import save_json, canonical_hash

UNITS={**{k:'N' for k in CONTACT_COMPONENTS if k not in ('CONT','JEU')},
       'CONT':'1','JEU':'mm','LAGS_C':'MPa','LAGS_F1':'1','LAGS_F2':'1'}

def parse(raw,model,catalog):
    if (raw.get('solver_status')!='COMPLETED' or raw.get('converged')is not True or
        raw.get('versions',{}).get('code_aster')!=VERSION or raw.get('source_commit')!=SOURCE):
        raise ValueError('고정 Aster의 완료된 원 결과를 확인하세요.')
    guard=raw['native_mesh_checks'];node_order=guard['node_ids_in_native_order']
    source={r['node_id']:r['position_mm'] for r in model['nodes']}
    if guard.get('status')!='PASS' or len(node_order)!=len(source) or set(node_order)!=set(source):
        raise ValueError('원 메시와 실제 결과의 절점 관계가 다릅니다.')
    orders=raw['available_orders'];access=raw['access_parameters'];parameters=access.get('INST')
    if (not isinstance(orders,list) or not orders or any(type(v)is not int or v<0 for v in orders) or
        len(set(orders))!=len(orders) or access.get('NUME_ORDRE')!=orders or len(parameters)!=len(orders)):
        raise ValueError('원 결과의 실제 하중 단계 목록이 불완전합니다.')
    parameters=[_finite(v,'load parameter') for v in parameters]
    if any(b<=a for a,b in zip(parameters,parameters[1:])):raise ValueError('실제 하중 진행값이 증가하지 않습니다.')
    def rows(table,components,order,allowed,*,complete):
        table,count=_table(table,('NOEUD','NUME_ORDRE',*components),'native field')
        result={}
        for i in range(count):
            index=_table_identifier(table['NOEUD'][i],'NOEUD')-1
            if not 0<=index<len(node_order):raise ValueError('원 결과에 없는 절점 번호입니다.')
            n=node_order[index]
            if n not in allowed or n in result:raise ValueError('접촉쌍 밖의 절점 또는 중복 결과 행입니다.')
            _field_order(table,i,order,'native field')
            for axis,key in enumerate(('COOR_X','COOR_Y','COOR_Z')):
                if key in table and not math.isclose(_finite(table[key][i],key),source[n][axis],rel_tol=1e-12,abs_tol=1e-12):
                    raise ValueError('원 결과 행의 위치가 메시와 다릅니다.')
            result[n]={}
            for key in components:
                value=table[key][i]
                # Null native DOFs remain unknown, never a zero-valued field.
                if value is None or (isinstance(value,dict) and set(value)=={'invalid_numeric'} and value['invalid_numeric']in ('nan','inf','-inf')):
                    result[n][key]=None
                else:result[n][key]=_finite(value,key)
            if 'CONT' in result[n] and result[n]['CONT'] not in (None,-1.,0.,1.,2.):
                raise ValueError('지원하지 않는 native 접촉 상태입니다.')
        if complete and (set(result)!=set(allowed) or any(v is None for r in result.values() for v in r.values())):
            raise ValueError('원 변위·반력 절점 결과가 빠졌습니다.')
        return result
    if [r['order'] for r in raw['tables']]!=orders:raise ValueError('보존한 결과 표의 실제 단계가 다릅니다.')
    output=[]
    for order,parameter,step in zip(orders,parameters,raw['tables']):
        fields={key:rows(step['fields'][key],DISPLACEMENT,order,source,complete=True) for key in ('DEPL','REAC_NODA')}
        if set(step['pairs'])!=set(catalog['pairs']):raise ValueError('실제 접촉쌍 결과가 빠졌습니다.')
        pairs={}
        for p in model['contacts']:
            name=p['object_id'];allowed=surface_nodes(model,p['a']);native=step['pairs'][name]
            force=rows(native['CONT_NOEU'],CONTACT_COMPONENTS,order,allowed,complete=False)
            cmp=MULTIPLIERS if p['draft']['tangential_law']=='coulomb' else ('LAGS_C',)
            mult=rows(native['MULTIPLIERS'],cmp,order,allowed,complete=False)
            pairs[name]={'nodes':sorted(allowed),'values':{str(n):{**force.get(n,{}),**mult.get(n,{})} for n in allowed}}
        output.append(dict(order=order,load_parameter=parameter,fields={k:{str(n):v for n,v in values.items()} for k,values in fields.items()},pairs=pairs))
    return dict(schema_version='1',backend=BACKEND,steps=output,source_commit=SOURCE,
        model_sha256=canonical_hash(model),coordinate_frame='FREECAD_DOCUMENT_GLOBAL',
        axis={'name':'load_parameter','unit':'1','semantics':'STATIC_LOAD_PARAMETER_NOT_PHYSICAL_TIME'},
        qualification='UNKNOWN',decision='NOT_RELEASED')

def context(output):
    root=Path(output);receipt=json.loads(_read(root/'contact_execution.json'))
    if receipt['execution_status']!='SUCCEEDED':raise ValueError('완료된 접촉 결과를 선택하세요. 원 실패·원문은 보존됩니다.')
    for pin in receipt['artifacts']:
        path=root/pin['relative']
        if not path.resolve().is_relative_to(root.resolve()) or len(_read(path))!=pin['bytes'] or _sha(path)!=pin['sha256']:
            raise ValueError('원 접촉 결과 파일이 바뀌었습니다.')
    _,model,_,_=validate_snapshot(root/'frozen_input/snapshot.json')
    config=json.loads(_read(root/'solver/input.json'));raw=json.loads(_read(root/'solver/worker_result.json'))
    if raw['input_sha256']!=_sha(root/'solver/input.json') or raw['mail_sha256']!=_sha(root/'solver/mesh.mail'):
        raise ValueError('원 입력과 결과 관계가 다릅니다.')
    parsed=parse(raw,model,config['catalog'])
    if parsed!=json.loads(_read(root/'contact_fields.json')):raise ValueError('원 native 표와 보존한 읽기 결과가 다릅니다.')
    return receipt,model,parsed

def _catalog(receipt,model,parsed,root):
    result={};artifact=root/'contact_fields.json'
    artifact_sha = _sha(artifact)
    manifest_sha = canonical_hash(receipt['artifacts'])
    for pair in model['contacts']:
        name=pair['object_id'];nodes=sorted(surface_nodes(model,pair['a']))
        channels=CONTACT_COMPONENTS+(MULTIPLIERS if pair['draft']['tangential_law']=='coulomb' else ('LAGS_C',))
        for token in channels:
            key=name+'.'+token
            result[key]=dict(kind='series',unit=UNITS[token],component=token,
                location=pair['draft']['label']+' / A 면 native 절점',reduction='none',node_ids=nodes,
                selector_template=key+'@<native_node_id>',axes=[parsed['axis']],
                coordinate_frame=parsed['coordinate_frame'],quantity=('native signed contact pressure multiplier; compression negative' if token=='LAGS_C' else
                    'native tangential direction multiplier, not friction traction' if token.startswith('LAGS_F') else
                    'native signed gap: positive separation, negative penetration; unpaired is unavailable' if token=='JEU' else
                    ('native status: -1=unpaired, 0=open, 1=stick, 2=slip' if pair['draft']['tangential_law']=='coulomb' else
                     'native status: -1=unpaired, 0=open, 2=contact (not frictional slip)') if token=='CONT' else 'native global nodal contact force'),
                source=dict(backend=BACKEND,artifact='contact_fields.json',sha256=artifact_sha,
                    manifest_sha256=manifest_sha,sha256_kind='ARTIFACT_SHA256',model_revision=parsed['model_sha256'],
                    native_origin='DEPL' if token in MULTIPLIERS else 'CONT_NOEU',value_origin='NATIVE'),
                qualification='UNKNOWN',original_execution_status=receipt['execution_status'])
        for quantity in ('CFN', 'CFS', 'CF'):
            for response in ('F', 'M'):
                for component,axis in enumerate('XYZ'):
                    key = name+'.'+quantity+'_'+response+axis
                    result[key] = dict(kind='series', unit='N' if response == 'F' else 'N*mm',
                        component=axis, pair_id=name, quantity=quantity,
                        response='force' if response == 'F' else 'moment',
                        component_index=component, force_on='slave_A', reduction='none',
                        location=pair['draft']['label']+' / A면 전체',
                        axes=[parsed['axis']], coordinate_frame=parsed['coordinate_frame'],
                        moment_configuration='REFERENCE', reference_point_mm=[0.,0.,0.],
                        value_origin='DERIVED_SUM_NATIVE_NODAL_FORCES',
                        source=dict(backend=BACKEND, artifact='contact_fields.json', sha256=artifact_sha,
                            manifest_sha256=manifest_sha, sha256_kind='ARTIFACT_SHA256',
                            model_revision=parsed['model_sha256'], native_origin='CONT_NOEU',
                            value_origin='DERIVED_SUM_NATIVE_NODAL_FORCES'),
                        qualification='UNKNOWN', original_execution_status=receipt['execution_status'])
    return result

def catalog(outcome,output):
    receipt,model,parsed=context(output)
    return _catalog(receipt,model,parsed,Path(output))

def read(outcome,output,selector,*,start=None,stop=None):
    receipt,model,parsed=context(output);group,separator,node=selector.partition('@')
    descriptors=_catalog(receipt,model,parsed,Path(output))
    if selector in descriptors and descriptors[selector].get('value_origin') == 'DERIVED_SUM_NATIVE_NODAL_FORCES':
        from ..contact_resultants import selection, project
        descriptor = descriptors[selector]
        steps = parsed['steps']
        start = 0 if start is None else start
        stop = len(steps) if stop is None else stop
        if type(start) is not int or type(stop) is not int or not 0 <= start < stop <= len(steps):
            raise ValueError('실제 하중 단계의 유효한 표본 구간을 선택하세요.')
        selected = steps[start:stop]
        spec = selection()
        spec['response'] = descriptor['response']
        values, mask = [], []
        for step in selected:
            raw = pair_resultant(model, parsed, descriptor['pair_id'], step['order'], descriptor['quantity'])
            value, reason = project(raw, spec, descriptor['component_index'])
            values.append(value)
            mask.append(reason is None)
        return {**descriptor, 'value':values, 'valid_mask':mask, 'mask':mask,
            'status':'AVAILABLE' if all(mask) else 'UNKNOWN',
            'axes':[{**parsed['axis'], 'values':[s['load_parameter'] for s in selected]}],
            'source':{**descriptor['source'], 'selector':selector, 'sample_slice':[start,stop]}}
    if (not separator or group not in descriptors or 'node_ids' not in descriptors[group]
            or not node.isdecimal() or int(node) not in descriptors[group]['node_ids']):
        raise ValueError('접촉쌍의 실제 A 면 절점과 응답을 선택하세요.')
    descriptor=descriptors[group];pair,token=group.rsplit('.',1);node=str(int(node));steps=parsed['steps']
    start=0 if start is None else start;stop=len(steps) if stop is None else stop
    if type(start)is not int or type(stop)is not int or not 0<=start<stop<=len(steps):raise ValueError('실제 하중 단계의 유효한 표본 구간을 선택하세요.')
    selected=steps[start:stop];values=[s['pairs'][pair]['values'][node].get(token) for s in selected]
    mask=[v is not None and (token=='CONT' or s['pairs'][pair]['values'][node].get('CONT')not in (None,-1.)) for s,v in zip(selected,values)]
    return {**descriptor,'node_id':int(node),'value':values,'valid_mask':mask,'mask':mask,
        'status':'AVAILABLE' if all(mask) else 'UNKNOWN','axes':[{**parsed['axis'],'values':[s['load_parameter'] for s in selected]}],
        'source':{**descriptor['source'],'selector':selector,'sample_slice':[start,stop]}}

def pair_resultant(model, parsed, pair_id, order, quantity='CF'):
    """Sum retained slave-A forces using reference nodal positions.

    This is a derived nodal-force sum, not a native surface resultant or a
    current-configuration torque. contact_resultants.project handles the user's
    reference point and basis without summing side B again.
    """
    from ..contact_resultants import cross
    groups = {'CFN': ('RN',), 'CFS': ('RTA', 'RTG'), 'CF': ('RN', 'RTA', 'RTG')}
    pairs = [p for p in model['contacts'] if p['object_id'] == pair_id]
    steps = [s for s in parsed['steps'] if s['order'] == order]
    if (quantity not in groups or type(order) is not int or len(pairs) != 1
            or len(steps) != 1 or parsed.get('model_sha256') != canonical_hash(model)
            or parsed.get('coordinate_frame') != 'FREECAD_DOCUMENT_GLOBAL'):
        raise ValueError('정확한 접촉쌍과 저장 증분의 합력 또는 모멘트를 선택하세요.')
    step = steps[0]
    pair = step['pairs'][pair_id]
    ids = sorted(surface_nodes(model, pairs[0]['a']))
    if pair['nodes'] != ids or set(pair['values']) != {str(n) for n in ids}:
        raise ValueError('접촉쌍 A면의 원 절점 집합과 결과가 다릅니다.')
    positions = {r['node_id']: r['position_mm'] for r in model['nodes']}
    components = tuple(prefix+axis for prefix in groups[quantity] for axis in 'XYZ')
    unpaired = any(pair['values'][str(n)].get('CONT') in (None, -1.) for n in ids)
    nodal = []
    for node in ids:
        row = pair['values'][str(node)]
        force = []
        for axis in 'XYZ':
            values = [row.get(prefix+axis) for prefix in groups[quantity]]
            force.append(None if unpaired or any(v is None for v in values)
                         else math.fsum(_finite(v, 'native nodal force') for v in values))
        nodal.append((positions[node], force))
    force = [None if any(f[axis] is None for _,f in nodal)
             else math.fsum(f[axis] for _,f in nodal) for axis in range(3)]
    moment = []
    for axis in range(3):
        terms = []
        valid = not unpaired
        for position, f in nodal:
            basis = [float(i == axis) for i in range(3)]
            coefficient = cross(basis, position)
            for c, value in zip(coefficient, f):
                if c == 0:
                    continue
                if value is None:
                    valid = False
                else:
                    terms.append(c*value)
        moment.append(math.fsum(terms) if valid else None)
    mask = [value is not None for value in force+moment]
    return dict(association='contact_pair_resultant', basis='FREECAD_DOCUMENT_GLOBAL',
        pair_id=pair_id, quantity=quantity, force_on='slave_A',
        force_N=force, moment_origin_Nmm=moment,
        static=dict(step=1, increment=order, load_parameter=step['load_parameter']),
        status='AVAILABLE' if all(mask) else 'UNKNOWN', valid_mask=mask,
        reason='NATIVE_UNPAIRED_OR_MISSING_STATUS' if unpaired else
               None if all(mask) else 'NATIVE_NONFINITE_OR_MISSING_COMPONENT',
        value_origin='DERIVED_SUM_NATIVE_NODAL_FORCES',
        moment_configuration='REFERENCE', integration='NONE_NATIVE_NODAL_FORCE_SUM',
        source=dict(backend=BACKEND, native_origin='CONT_NOEU', native_components=list(components),
                    node_ids=ids, source_commit=parsed['source_commit'],
                    model_revision=parsed['model_sha256']),
        qualification='UNKNOWN', decision='NOT_RELEASED')


def write_post(output,model,parsed):
    """Physical body mesh and pair-separated native nodal fields, last actual order."""
    from apps.desktop_post.prepare import data_array
    root=Path(output)/'post';root.mkdir();step=parsed['steps'][-1]
    nodes=sorted(model['nodes'],key=lambda n:n['node_id']);index={r['node_id']:i for i,r in enumerate(nodes)}
    def grid(path,points,connectivity,types,arrays):
        vtk=ET.Element('VTKFile',type='UnstructuredGrid',version='0.1',byte_order='LittleEndian')
        piece=ET.SubElement(ET.SubElement(vtk,'UnstructuredGrid'),'Piece',NumberOfPoints=str(len(points)),NumberOfCells=str(len(connectivity)))
        data_array(ET.SubElement(piece,'Points'),'Position_mm',(v for p in points for v in p),3)
        cells=ET.SubElement(piece,'Cells');offset=0;offsets=[]
        for c in connectivity:offset+=len(c);offsets.append(offset)
        for name,values in [('connectivity',[v for c in connectivity for v in c]),('offsets',offsets),('types',types)]:data_array(cells,name,values,integer=True)
        pd=ET.SubElement(piece,'PointData')
        for name,values,components in arrays:data_array(pd,name,values,components)
        ET.ElementTree(vtk).write(path,encoding='utf-8',xml_declaration=True)
    displacement=[[step['fields']['DEPL'][str(r['node_id'])][k] for k in DISPLACEMENT] for r in nodes]
    grid(root/'displacement.vtu',[r['position_mm'] for r in nodes],[[index[n] for n in r['node_ids']] for r in model['elements']],
        [24 if r['type']=='C3D10' else 12 for r in model['elements']],
        [('U_mm',[v for row in displacement for v in row],3),('NativeNodeId',list(index),1)])
    def artifact(path,arrays):
        return dict(relative=path.relative_to(output).as_posix(),bytes=path.stat().st_size,sha256=_sha(path),native_metadata=dict(
            coordinate_units='mm',coordinate_frame=parsed['coordinate_frame'],static=dict(step=1,increment=step['order'],load_parameter=step['load_parameter']),arrays=arrays))
    primary=artifact(root/'displacement.vtu',[dict(name='U_mm',association='POINTS',components=3,units='mm',frame=parsed['coordinate_frame'],measure='displacement')])
    secondary=[];node_positions={r['node_id']:r['position_mm'] for r in nodes}
    for p in model['contacts']:
        name=p['object_id'];pair=step['pairs'][name];ids=pair['nodes'];arrays=[];metadata=[]
        for token in CONTACT_COMPONENTS+(MULTIPLIERS if p['draft']['tangential_law']=='coulomb' else ('LAGS_C',)):
            values=[pair['values'][str(n)].get(token) for n in ids]
            mask=[int(v is not None and (token=='CONT' or pair['values'][str(n)].get('CONT')not in (None,-1.))) for n,v in zip(ids,values)]
            arrays.extend([(token,[v if valid else math.nan for v,valid in zip(values,mask)],1),(token+'_valid',mask,1)])
            metadata.append(dict(name=token,association='POINTS',components=1,units=UNITS[token],frame=parsed['coordinate_frame'],
                measure=token,valid_mask_array=token+'_valid'))
        arrays.append(('NativeNodeId',ids,1));path=root/(name+'.vtu')
        grid(path,[node_positions[n] for n in ids],[[i] for i in range(len(ids))],[1]*len(ids),arrays)
        secondary.append(artifact(path,metadata))
    return primary,secondary
