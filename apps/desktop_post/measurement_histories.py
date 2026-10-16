"""Bounded native surface/gauge histories, materialized by the existing Post owner.

Only actual frames and fixed reference geometry are admitted. Linear faces use
VTK integration; TRI6/QUAD8 use native-order parametric quadrature. The retained
table never recomputes a measurement when reopened.
"""
from copy import deepcopy
import json
import math
import hashlib

import numpy as np
from paraview import simple as p
try:
    from . import analysis,external
except ImportError:
    import analysis,external

SURFACE_ARRAY='SurfaceAreaAverage'
GAUGE_ARRAY='GaugeRelativeDisplacement'


def _measurement_module():
    try:from . import measurements
    except ImportError:import measurements
    return measurements


def _point_ids(data,indices):
    return _measurement_module()._gauge_point_ids(data,indices)


def _tracking(data):
    identity,mode=_measurement_module()._tracking_identity(data)
    h=hashlib.sha256(identity.encode());attrs=data.GetCellData()
    arrays=[attrs.GetGlobalIds(),*[attrs.GetArray(name) for name in ('NativeElementId','GlobalElementId','GlobalIds')]]
    for array in arrays:
        if array is None:continue
        values=np.asarray(analysis.vtk_to_numpy(array)).reshape(-1)
        if (array.GetNumberOfComponents()!=1 or len(values)!=data.GetNumberOfCells()
                or not np.issubdtype(values.dtype,np.number) or not np.isfinite(values).all() or len(np.unique(values))!=len(values)):
            raise ValueError('원 셀 식별자는 전체 셀에 유일한 유한 스칼라여야 합니다.')
        h.update((array.GetName() or 'active_global_ids').encode());h.update(values.dtype.str.encode());h.update(values.tobytes())
    return h.hexdigest(),mode


def _quadratic_owners(data):
    if not any(data.GetCellType(i) in (22,23,24,25,26,27) for i in range(data.GetNumberOfCells())):return None
    from vtkmodules.vtkCommonDataModel import vtkGenericCell
    cell=vtkGenericCell();result={}
    for owner in range(data.GetNumberOfCells()):
        data.GetCell(owner,cell)
        for number in range(cell.GetNumberOfFaces()) if cell.GetCellDimension()==3 else (None,) if cell.GetCellDimension()==2 else ():
            face=cell.GetFace(number) if number is not None else cell
            kind=face.GetCellType()
            if kind not in (5,9,22,23):continue
            ids=[face.GetPointId(j) for j in range(face.GetNumberOfPoints())]
            corners=3 if kind in (5,22) else 4
            result.setdefault(tuple(sorted(ids[:corners])),[]).append((owner,number,ids,kind))
    return result


def _original_quadratic_catalog(data,topology,offset,limit,owners):
    def connectivity(row):
        ids,kind=row[2],row[3];corners=3 if kind in (5,22) else 4
        edges=tuple(sorted((tuple(sorted((ids[i],ids[(i+1)%corners]))),ids[corners+i])
            for i in range(corners))) if kind in (22,23) else ()
        return kind,tuple(sorted(ids[:corners])),edges
    boundary=[]
    for candidates in topology.values():
        if len(candidates)>2 or len(candidates)==2 and (
                any(row[1] is None for row in candidates) or
                connectivity(candidates[0])!=connectivity(candidates[1])):
            raise ValueError('중복·비정합 고차 경계면입니다. 공유 중간절점과 원 face 연결을 확인하세요.')
        if len(candidates)==1:boundary.append(candidates[0])
    boundary.sort(key=lambda row:(row[0],-1 if row[1] is None else row[1]))
    rows=[]
    for owner,face_index,ids,kind in boundary[offset:None if limit is None else offset+limit]:
        if owners is not None and owner not in owners:continue
        if len(set(ids))!=len(ids) or min(ids)<0 or max(ids)>=data.GetNumberOfPoints():
            raise ValueError('고차면의 원 중간절점 번호가 누락·중복되었습니다.')
        rows.append({'cell_index':owner,'face_index':face_index,'point_indices':ids,
            'coordinates':[list(data.GetPoint(i)) for i in ids]})
    selected=sorted({i for row in rows for i in row['point_indices']});positions={value:i for i,value in enumerate(selected)}
    identities=_point_ids(data,selected)
    for row in rows:row['original_point_ids']={name:[values[positions[i]] for i in row['point_indices']] for name,values in identities.items()}
    return rows,len(boundary)


def _surface_catalog(data,*,offset=0,limit=None,owners=None):
    """Whole-source boundary first; never expose a cut cell's internal faces."""
    from vtkmodules.vtkFiltersGeometry import vtkDataSetSurfaceFilter
    if not hasattr(data,'GetPoints') or data.GetPoints() is None:
        raise ValueError('단일 원 자료를 선택하세요. 여러 블록의 면 대응은 자동 추정하지 않습니다.')
    topology=_quadratic_owners(data)
    if topology is not None:return _original_quadratic_catalog(data,topology,offset,limit,owners)
    surface=vtkDataSetSurfaceFilter();surface.SetInputData(data)
    surface.PassThroughPointIdsOn();surface.PassThroughCellIdsOn()
    surface.SetOriginalPointIdsName('CAE_MeasurePointIndex');surface.SetOriginalCellIdsName('CAE_MeasureCellIndex')
    surface.Update();output=surface.GetOutput()
    points=output.GetPointData().GetArray('CAE_MeasurePointIndex')
    cells=output.GetCellData().GetArray('CAE_MeasureCellIndex')
    if points is None or cells is None:raise ValueError('추출한 표면에서 원 셀·점 번호를 확인할 수 없습니다.')
    rows=[];seen=set()
    end=output.GetNumberOfCells() if limit is None else min(output.GetNumberOfCells(),offset+limit)
    for index in range(offset,end):
        cell=output.GetCell(index)
        if cell.GetCellDimension()!=2 or cell.GetCellType() not in (5,9):continue
        owner=int(cells.GetTuple1(index));original=data.GetCell(owner);face_index=None
        if owners is not None and owner not in owners:continue
        ids=[int(points.GetTuple1(cell.GetPointId(i))) for i in range(cell.GetNumberOfPoints())]
        if original.GetCellDimension()==3:
            matches=[i for i in range(original.GetNumberOfFaces()) if
                sorted(original.GetFace(i).GetPointId(j) for j in range(original.GetFace(i).GetNumberOfPoints()))==sorted(ids)]
            if len(matches)!=1:raise ValueError('원 셀의 경계면을 정확히 대응할 수 없습니다. 기준 시각에서 면을 다시 선택하세요.')
            face_index=matches[0]
        elif original.GetCellDimension()!=2:continue
        if min(ids)<0 or max(ids)>=data.GetNumberOfPoints():raise ValueError('고차면의 생성 점을 원 점으로 대신할 수 없습니다. 현재는 선형 삼각형·사각형 면을 지원합니다.')
        key=(owner,face_index)
        if key in seen:raise ValueError('원 경계면이 중복되어 선택 대상을 구분할 수 없습니다.')
        seen.add(key)
        rows.append({'cell_index':owner,'face_index':face_index,'point_indices':ids,
            'coordinates':[list(data.GetPoint(i)) for i in ids]})
    selected=sorted({i for row in rows for i in row['point_indices']});positions={value:i for i,value in enumerate(selected)}
    identities=_point_ids(data,selected)
    for row in rows:row['original_point_ids']={name:[values[positions[i]] for i in row['point_indices']] for name,values in identities.items()}
    return rows,output.GetNumberOfCells()


def surface_catalog(data):
    return _surface_catalog(data)[0]


def surface_options(source,reference_time,*,offset=0,limit=200):
    temporary=[];before=p.GetActiveSource(),p.GetActiveView()
    try:
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=1000:
            raise ValueError('면 목록은 시작 행과 1–1000행 범위로 조회하세요.')
        native=external.times(source)
        if native and (type(reference_time) not in (int,float) or reference_time not in native):
            raise ValueError('면을 선택하기 전에 실제 결과의 기준 시각을 선택하세요.')
        if not native and reference_time is not None:raise ValueError('정적 자료에는 기준 시각이 없습니다.')
        frozen=analysis._freeze(source,reference_time,'surface selection',temporary)
        rows,total=_surface_catalog(analysis._fetch(frozen),offset=offset,limit=limit)
        return {'reference_time':reference_time,'faces':rows,'total':total,'offset':offset,'limit':limit,'has_more':offset+limit<total,
            'geometry':'fixed_reference','selection':'원 경계의 TRI3/QUAD4/TRI6/QUAD8 면을 중간절점까지 명시 선택'}
    finally:
        analysis.cleanup({'proxies':temporary});p.SetActiveSource(before[0]);p.SetActiveView(before[1])


def _faces(data,draft):
    faces=draft.get('surface_faces')
    if not isinstance(faces,list) or not 1<=len(faces)<=1000:
        raise ValueError('원 경계면을 1–1000개 명시적으로 선택하세요.')
    owners=set()
    for face in faces:
        if not isinstance(face,dict) or type(face.get('cell_index')) is not int or face['cell_index']<0:
            raise ValueError('선택한 면의 원 셀 번호를 확인하세요.')
        owners.add(face['cell_index'])
    catalog=_surface_catalog(data,owners=owners)[0];selected=[];seen=set()
    for face in faces:
        if not isinstance(face,dict) or set(face)!={'cell_index','face_index','point_indices','coordinates','original_point_ids'}:
            raise ValueError('측정 전에 원 면·기준 좌표·점 번호를 다시 선택하세요.')
        if not isinstance(face['coordinates'],list):raise ValueError('선택한 면의 원 기준 좌표를 확인하세요.')
        for coordinate in face['coordinates']:analysis._vector(coordinate,'선택 면의 기준 좌표')
        if (not isinstance(face['original_point_ids'],dict) or
                any(not isinstance(values,list) or any(type(v) not in (int,float) or not math.isfinite(v) for v in values)
                    for values in face['original_point_ids'].values())):
            raise ValueError('선택한 면의 원 점 식별자를 확인하세요.')
        matches=[row for row in catalog if row==face]
        if len(matches)!=1:raise ValueError('선택한 면의 원본 형상이나 점 번호가 달라졌습니다. 기준 시각에서 면을 다시 선택하세요.')
        if face['face_index'] is not None and type(face['face_index']) is not int:raise ValueError('원 셀의 면 번호를 확인하세요.')
        _measurement_module()._indices(face['point_indices'],data.GetNumberOfPoints())
        key=tuple(sorted(face['point_indices']))
        if key in seen:raise ValueError('같은 원 면을 중복하여 평균낼 수 없습니다.')
        seen.add(key);selected.append(deepcopy(face))
    return selected


def _valid(attrs,indices,size,*,ghost_bit,masks=(),policy=None,ghost_only=False):
    names=['vtkGhostType'] if ghost_only else [*masks,*([] if policy=='declared_array' else ['vtkValidPointMask','vtkValidMask']),'vtkGhostType']
    for name in dict.fromkeys(names):
        mask=attrs.GetArray(name)
        if mask is None:
            if name in masks:raise ValueError('선택 물리량의 선언된 유효성 배열이 없습니다: '+name)
            continue
        if mask.GetNumberOfComponents()!=1 or mask.GetNumberOfTuples()!=size:
            raise ValueError('유효성 배열의 POINTS/CELLS 위치 또는 원 행 수가 다릅니다.')
        values=[mask.GetTuple1(i) for i in indices]
        if any(not math.isfinite(v) or (int(v)!=v or int(v)&ghost_bit if name=='vtkGhostType' else v==0) for v in values):
            return False,name
    return True,''


def surface_average(data,draft,faces=None):
    """Linear native integral or full quadratic-shape integral over reference area."""
    from vtkmodules.vtkCommonDataModel import vtkPolyData,vtkCellArray
    from vtkmodules.vtkCommonCore import vtkDoubleArray
    from vtkmodules.vtkFiltersParallel import vtkIntegrateAttributes
    from caelab.experiment_calibration import UNITS
    if draft.get('geometry')!='fixed_reference':raise ValueError('고정 기준 형상(fixed_reference)을 선택하세요. 변형된 현재 면적의 평균은 아직 지원하지 않습니다.')
    if UNITS.get(draft.get('coordinate_units'),(None,))[0]!='length':raise ValueError('원 기준 좌표의 길이 단위를 명시하세요.')
    faces=_faces(data,draft) if faces is None else faces
    point_indices=sorted({i for face in faces for i in face['point_indices']})
    selected_ids=_point_ids(data,point_indices);positions={value:i for i,value in enumerate(point_indices)}
    for face in faces:
        if ([list(data.GetPoint(i)) for i in face['point_indices']]!=face['coordinates'] or
                {name:[values[positions[i]] for i in face['point_indices']] for name,values in selected_ids.items()}!=face['original_point_ids']):
            raise ValueError('선택한 면의 기준 좌표나 원 점 번호가 달라졌습니다. 기준 시각에서 면을 다시 선택하세요.')
    association=draft['association'];attrs=data.GetPointData() if association=='POINTS' else data.GetCellData()
    size=data.GetNumberOfPoints() if association=='POINTS' else data.GetNumberOfCells()
    indices=point_indices if association=='POINTS' else [f['cell_index'] for f in faces]
    array=attrs.GetArray(draft['array'])
    if array is None:return {'value':None,'area':None,'valid':False,'reason':'missing_selected_field'}
    if array.GetNumberOfTuples()!=size:raise ValueError('원 수치 배열의 POINTS/CELLS 위치와 행 수를 확인하세요.')
    count=array.GetNumberOfComponents();component=draft.get('component');direction=draft.get('direction')
    if count>1 and (draft.get('basis')!='fixed_cartesian' or draft.get('frame')!=draft.get('coordinate_frame')
            or draft.get('frame','').strip().lower() in ('local','scalar','unknown','undeclared')):
        raise ValueError('벡터·텐서 성분과 방향 투영은 좌표와 같은 고정 직교기저(fixed_cartesian)를 명시해야 합니다.')
    if component=='projection':
        direction=analysis._vector(direction,'fixed projection direction')
        if count!=3 or not math.isclose(sum(v*v for v in direction),1.,rel_tol=0.,abs_tol=1e-12):
            raise ValueError('방향 투영은 3성분 벡터와 명시한 단위 방향벡터가 필요합니다.')
    elif count==1 and component is None:
        if direction is not None:raise ValueError('스칼라 평균에는 벡터 투영 방향을 지정하지 않습니다.')
    elif type(component) is int and 0<=component<count:
        if direction is not None:raise ValueError('원 성분 선택과 방향 투영 중 하나만 선택하세요.')
    else:raise ValueError('스칼라·원 성분·고정 방향 투영 중 하나를 선택하세요. 크기나 불변량을 자동 계산하지 않습니다.')
    values={i:(sum(v*n for v,n in zip(array.GetTuple(i),direction)) if component=='projection' else
        array.GetComponent(i,0 if component is None else component)) for i in indices}
    masks=draft.get('validity_masks',[])
    if not isinstance(masks,list) or any(not isinstance(v,str) for v in masks):raise ValueError('원 물리량의 실제 유효성 배열 이름을 확인하세요.')
    valid,reason=_valid(attrs,indices,size,ghost_bit=2 if association=='POINTS' else 33,masks=masks,policy=draft.get('validity_policy'))
    owner_valid,owner_reason=_valid(data.GetCellData(),[f['cell_index'] for f in faces],data.GetNumberOfCells(),ghost_bit=33,ghost_only=True)
    point_valid,point_reason=_valid(data.GetPointData(),point_indices,data.GetNumberOfPoints(),ghost_bit=2,ghost_only=True)
    if not valid or not owner_valid or not point_valid or any(not math.isfinite(v) for v in values.values()):
        return {'value':None,'area':None,'valid':False,'reason':reason or owner_reason or point_reason or 'nonfinite_selected_field'}
    if any(len(face['point_indices']) in (6,8) for face in faces):
        try:from .surface_quadrature import integrate
        except ImportError:from surface_quadrature import integrate
        reports=[]
        for face in faces:
            ids=face['point_indices']
            if len(ids) in (6,8):
                local=integrate(face['coordinates'],[values[i] for i in ids] if association=='POINTS' else values[face['cell_index']])
            else:
                local=surface_average(data,draft,[face]);area=local['area'];integral=area*local['value']
                local.update(integral=integral,reference_area=area,reference_integral=integral,rule='native_linear')
            reports.append(local)
        area=math.fsum(row['area'] for row in reports);integral=math.fsum(row['integral'] for row in reports)
        reference_area=math.fsum(row['reference_area'] for row in reports)
        reference_integral=math.fsum(row['reference_integral'] for row in reports)
        value=integral/area
        if not all(math.isfinite(v) for v in (area,integral,reference_area,reference_integral,value)) or min(area,reference_area)<=0:
            raise ValueError('선택 고차면의 전체 면적과 적분을 유한하게 계산할 수 없습니다.')
        return {'value':value,'area':area,'valid':True,'reason':'valid','integral':integral,
            'area_difference':math.fsum(abs(row['area']-row['reference_area']) for row in reports),
            'integral_difference':math.fsum(abs(row['integral']-row['reference_integral']) for row in reports),
            'mean_difference':abs(value-reference_integral/reference_area),
            'quadrature':{'version':1,'rules':sorted(set(row['rule'] for row in reports)),
                'reference_rules':['TRI6_12','QUAD8_7x7'],'error_bound':'NOT_ESTABLISHED',
                'convergence':'UNKNOWN','metric':'derived_geometric_area_not_native_IP_area',
                'regularity':'affine_projection_contraction_bernstein',
                'faces':[row.get('geometry_checks') for row in reports]}}
    surface=vtkPolyData();surface.SetPoints(data.GetPoints());polys=vtkCellArray()
    for face in faces:
        polys.InsertNextCell(len(face['point_indices']))
        for i in face['point_indices']:polys.InsertCellPoint(i)
    surface.SetPolys(polys);field=vtkDoubleArray();field.SetName('SelectedScalar')
    if association=='POINTS':
        field.SetNumberOfTuples(data.GetNumberOfPoints())
        field.Fill(0.)
        for i,value in values.items():field.SetValue(i,value)
        surface.GetPointData().AddArray(field)
    else:
        for face in faces:field.InsertNextValue(values[face['cell_index']])
        surface.GetCellData().AddArray(field)
    integrate=vtkIntegrateAttributes();integrate.SetInputData(surface);integrate.SetDivideAllCellDataByVolume(False);integrate.Update()
    output=integrate.GetOutput();area_array=output.GetCellData().GetArray('Area')
    if area_array is None:raise ValueError('선택한 면에서 표면적을 계산할 수 없습니다.')
    area=area_array.GetTuple1(0)
    if not math.isfinite(area) or area<=0:raise ValueError('선택한 원 면의 면적은 유한한 양수여야 합니다.')
    attributes=output.GetPointData() if association=='POINTS' else output.GetCellData()
    value=attributes.GetArray('SelectedScalar').GetTuple1(0)/area
    if not math.isfinite(value):return {'value':None,'area':area,'valid':False,'reason':'nonfinite_integral'}
    return {'value':value,'area':area,'valid':True,'reason':'valid'}


def _clock(source,draft):
    times=external.times(source);interval=draft.get('time_range');reference=draft.get('reference_time')
    if not times or any(not math.isfinite(v) for v in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('시간 이력은 엄격히 증가하는 실제 시각 1–1024개를 지원합니다. 정적 자료에 물리 시간 이력을 만들지 않습니다.')
    if (not isinstance(interval,list) or len(interval)!=2 or any(type(v) not in (int,float) or v not in times for v in interval)
            or interval[0]>interval[1] or type(reference) not in (int,float) or reference not in times):
        raise ValueError('실제 결과에 존재하는 시작·끝·기준 시각을 명시적으로 선택하세요.')
    for key in ('time_units','time_origin','units','frame','quantity','coordinate_units','coordinate_frame','measure'):
        if not isinstance(draft.get(key),str) or not draft[key].strip() or draft[key].strip().lower() in ('unknown','undeclared'):
            raise ValueError('측정의 다음 물리 선언을 확인하세요: '+key+'')
    selected=[t for t in times if interval[0]<=t<=interval[1]]
    if len(selected)>1024:raise ValueError('한 측정 구간은 실제 시각 1024개까지 지원합니다. 원 결과는 유지되므로 구간을 나누어 선택하세요.')
    return selected,reference


def _table(values,namespace):
    payload=json.dumps(values,allow_nan=False,separators=(',',':'))
    script=("import json\nfrom vtkmodules.vtkCommonCore import vtkDoubleArray\nrows=json.loads("+repr(payload)+")\n"
        "output=self.GetTableOutput()\noutput.Initialize()\nfor name,values in rows.items():\n"
        "    a=vtkDoubleArray()\n    a.SetName(name)\n    for v in values:\n        a.InsertNextValue(float('nan') if v is None else v)\n    output.AddColumn(a)\n")
    proxy=p.ProgrammableSource(registrationName=analysis._name(namespace,'measurement history'),OutputDataSetType='vtkTable')
    try:proxy.Script=script;proxy.UpdatePipeline();return proxy
    except BaseException:p.Delete(proxy);raise


def build(source,draft,namespace):
    m=_measurement_module();kind=draft['measurement'];single=kind=='surface_average'
    if single:
        native=external.times(source);reference=draft.get('time')
        if native and (type(reference) not in (int,float) or reference not in native):raise ValueError('면 평균을 읽을 실제 시각을 선택하세요.')
        if not native and any(draft.get(k) is not None for k in ('time','time_units','time_origin')):raise ValueError('정적 자료에는 물리 시각이 없습니다. 시간 선언을 비워 두세요.')
        if native and any(not isinstance(draft.get(k),str) or not draft[k].strip() for k in ('time_units','time_origin')):
            raise ValueError('선택한 실제 시각의 단위와 기준을 명시하세요.')
        times=[reference]
        for key in ('units','frame','quantity','coordinate_units','coordinate_frame','measure'):
            if not isinstance(draft.get(key),str) or not draft[key].strip() or draft[key].strip().lower() in ('unknown','undeclared'):raise ValueError('면 평균의 물리량·단위·기저를 명시하세요.')
    else:times,reference=_clock(source,draft)
    before=p.GetActiveSource(),p.GetActiveView();temporary=[];result=None
    try:
        frozen=analysis._freeze(source,reference,namespace,temporary);data=analysis._fetch(frozen)
        identity,tracking=_tracking(data)
        faces=_faces(data,draft) if kind in ('surface_average','surface_time') else None
        if kind=='gauge_time':m._gauge_definition(data,draft,allow_invalid=True)
        rows=[]
        for time in times:
            local=[]
            try:
                frozen=analysis._freeze(source,time,namespace,local);current=analysis._fetch(frozen)
                current_identity,_=_tracking(current)
                if current_identity!=identity:raise ValueError('시간 표본 사이에서 원 점 번호나 연결이 달라졌습니다. 대응을 추정하지 않으므로 측정 대상을 복구하세요.')
                if faces is not None:sample=surface_average(current,draft,faces)
                else:
                    sample=m._gauge_definition(current,draft,allow_invalid=True)
                    valid,reason=_valid(current.GetPointData(),draft['point_indices'],current.GetNumberOfPoints(),ghost_bit=2,masks=draft.get('validity_masks',[]),policy=draft.get('validity_policy'))
                    if not valid:sample.update(value=None,valid=False,reason=reason)
                rows.append({'time':time,'value':sample['value'],'valid':sample.get('valid',True),
                    'reason':sample.get('reason','valid'),'area':sample.get('area'),
                    **({k:sample.get(k) for k in ('integral','area_difference','integral_difference','mean_difference','quadrature')} if sample.get('quadrature') else {})})
            finally:analysis.cleanup({'proxies':local})
        array=SURFACE_ARRAY if faces is not None else GAUGE_ARRAY
        values={'SampleIndex' if single else 'Time':[0] if single else times,array:[r['value'] for r in rows],'vtkValidMask':[int(r['valid']) for r in rows]}
        high_order=faces is not None and any(len(f['point_indices']) in (6,8) for f in faces)
        if faces is not None:values['SurfaceArea']=[r['area'] for r in rows]
        if high_order:
            for column,key in [('SurfaceIntegral','integral'),('SurfaceAreaDifference','area_difference'),
                    ('SurfaceIntegralDifference','integral_difference'),('SurfaceAverageDifference','mean_difference')]:
                values[column]=[r.get(key) for r in rows]
        result=_table(values,namespace)
        summary={**{k:deepcopy(draft.get(k)) for k in ('units','frame','quantity','coordinate_units','coordinate_frame','time_units','time_origin')},
            'measurement':kind,'input_array':draft['array'],'array':array,'association':'ROWS','recipe':deepcopy(draft),
            'input_association':draft['association'],
            'time_values':[] if single else times,'reference_time':reference,'tracking':tracking,'samples':rows,
            'measure':draft['measure'] if faces is not None else 'projected_relative_displacement',
            'component_label':('projection '+json.dumps(draft['direction']) if draft.get('component')=='projection' or kind=='gauge_time' else 'scalar' if draft.get('component') is None else 'component '+str(draft['component'])),
            'location':json.dumps(faces if faces is not None else {k:draft[k] for k in ('point_indices','point1','point2')},sort_keys=True),
            'sample_semantics':'native_surface_triangulation_area_average' if faces is not None else 'signed_fixed_reference_two_point_displacement_difference',
            'geometry':'fixed_reference','baseline_subtraction':False,'qualification':'UNKNOWN'}
        if single:summary.update(time=reference,axis_name='SampleIndex',axis_unit='1',axis_values=[0])
        if faces is not None:summary.update(area_unit=draft['coordinate_units']+'^2',
            reduction='native_surface_triangulation_area_weighted_mean',
            field_interpolation='native_point_triangulation' if draft['association']=='POINTS' else 'original_owner_cell_piecewise_constant_on_face')
        if high_order:
            summary.update(reduction='native_parametric_quadratic_area_weighted_mean',
                sample_semantics='native_quadratic_shape_area_average',
                quadrature=next((r['quadrature'] for r in rows if r.get('quadrature')),
                    {'version':1,'rules':[],'error_bound':'NOT_ESTABLISHED','convergence':'UNKNOWN'}),
                integral_unit=draft['units']+'*'+draft['coordinate_units']+'^2',
                field_interpolation='native_quadratic_shape' if draft['association']=='POINTS' else 'original_owner_cell_piecewise_constant_on_face')
        if faces is not None and draft.get('field_recovery') is not None:summary['field_recovery']=deepcopy(draft['field_recovery'])
        return {'source':result,'proxies':[result],'summary':summary}
    except BaseException:
        if result is not None:p.Delete(result)
        raise
    finally:
        analysis.cleanup({'proxies':temporary});p.SetActiveSource(before[0]);p.SetActiveView(before[1])
