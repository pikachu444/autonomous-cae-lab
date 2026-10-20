"""Explicit native leaf selection; identities stay scoped to their leaf path.

Uses the same VTK composite child APIs as report_image_data.fingerprint. A
coincident coordinate or repeated native ID in another leaf is never merged.
"""
from copy import deepcopy
import math


def _children(data):
    if data is None:return None
    kind=data.GetClassName()
    if kind=='vtkMultiBlockDataSet':
        return [data.GetBlock(i) for i in range(data.GetNumberOfBlocks())]
    if kind=='vtkPartitionedDataSetCollection':
        return [data.GetPartitionedDataSet(i) for i in range(data.GetNumberOfPartitionedDataSets())]
    if kind=='vtkPartitionedDataSet':
        return [data.GetPartition(i) for i in range(data.GetNumberOfPartitions())]
    return None


def leaves(data):
    """Include empty leaves and the actual VTK preorder composite flat index."""
    rows=[];flat=-1
    def visit(item,path):
        nonlocal flat
        flat+=1;index=flat
        if len(path)>16 or flat>4096:
            raise ValueError('Measurement supports at most 4096 blocks and 16 nested levels')
        children=_children(item)
        if children is not None:
            for i,child in enumerate(children):visit(child,path+[i])
        else:
            rows.append({'leaf_path':path,'flat_index':index,'data':item,
                'empty':item is None or not hasattr(item,'GetPoints') or item.GetPoints() is None or
                        item.GetNumberOfPoints()==0 or item.GetNumberOfCells()==0})
    visit(data,[])
    return rows


def resolve(data,path):
    if not isinstance(path,list) or any(type(i) is not int or i<0 for i in path):
        raise ValueError('Select an exact native leaf path')
    matches=[row for row in leaves(data) if row['leaf_path']==path]
    if len(matches)!=1 or matches[0]['empty']:
        raise ValueError('The selected leaf is empty, missing or is a composite parent')
    return matches[0]


def selected(data,selections,*,track,faces):
    """Verify every selected leaf and its original face capture independently."""
    if not isinstance(selections,list) or not 1<=len(selections)<=1000:
        raise ValueError('Select 1–1000 explicit native leaves')
    rows=[];seen=set()
    for selection in selections:
        if not isinstance(selection,dict) or set(selection)!={'leaf_path','surface_faces'}:
            raise ValueError('Each leaf requires its path and original selected faces')
        row=resolve(data,selection['leaf_path']);key=tuple(row['leaf_path'])
        if key in seen:raise ValueError('The same native leaf cannot be selected twice')
        seen.add(key)
        captured=faces(row['data'],{'surface_faces':selection['surface_faces']})
        identity,mode=track(row['data'])
        rows.append({**row,'surface_faces':captured,'identity':identity,'tracking':mode})
    return rows


def aggregate(reports,mode):
    """An invalid leaf invalidates the requested union; never shrink its area."""
    if mode not in ('per_leaf','area_weighted_mean','integral_sum'):
        raise ValueError('Choose leaf results, area-weighted mean or integral sum explicitly')
    if not reports:raise ValueError('No selected leaf measurement is available')
    if mode=='per_leaf':return {'leaves':deepcopy(reports),'aggregation':mode}
    valid=all(row.get('valid') is True for row in reports)
    if not valid:
        return {'value':None,'area':None,'integral':None,'valid':False,
                'reason':'invalid_selected_leaf','leaves':deepcopy(reports),'aggregation':mode}
    area=math.fsum(row['area'] for row in reports)
    integral=math.fsum(row.get('integral',row['area']*row['value']) for row in reports)
    if not math.isfinite(area) or area<=0 or not math.isfinite(integral):
        raise ValueError('Selected leaf area and integral must be finite with positive area')
    geometry={}
    if all(row.get('reference_geometry_area') is not None for row in reports):
        geometry={'reference_geometry_area':math.fsum(row['reference_geometry_area'] for row in reports),
                  'current_geometry_area':area}
    return {'value':integral/area if mode=='area_weighted_mean' else integral,
            'area':area,'integral':integral,'valid':True,'reason':'valid',
            'leaves':deepcopy(reports),'aggregation':mode,**geometry}


def _tables(history,values,namespace):
    """One retained native table per explicitly selected source leaf."""
    import json
    payload=json.dumps(values,allow_nan=False,separators=(',',':'))
    script=("import json\nfrom vtkmodules.vtkCommonCore import vtkDoubleArray\n"
        "from vtkmodules.vtkCommonDataModel import vtkTable,vtkMultiBlockDataSet\n"
        "rows=json.loads("+repr(payload)+")\noutput=self.GetOutputDataObject(0)\noutput.Initialize()\n"
        "output.SetNumberOfBlocks(len(rows))\nfor i,columns in enumerate(rows):\n"
        "    table=vtkTable()\n    for name,values in columns.items():\n"
        "        array=vtkDoubleArray()\n        array.SetName(name)\n        for value in values:\n"
        "            array.InsertNextValue(float('nan') if value is None else value)\n"
        "        table.AddColumn(array)\n    output.SetBlock(i,table)\n")
    proxy=history.p.ProgrammableSource(registrationName=history.analysis._name(namespace,'leaf measurements'),
        OutputDataSetType='vtkMultiBlockDataSet')
    try:proxy.Script=script;proxy.UpdatePipeline();return proxy
    except BaseException:history.p.Delete(proxy);raise


def build(source,draft,namespace):
    """Existing measurement owner/clock/materialization, explicit leaf scope."""
    try:from . import measurement_histories as history
    except ImportError:import measurement_histories as history
    mode=draft.get('aggregation')
    if mode not in ('per_leaf','area_weighted_mean','integral_sum'):
        raise ValueError('Choose a leaf aggregation explicitly')
    kind=draft.get('measurement');single=kind=='surface_average'
    if kind not in ('surface_average','surface_time'):
        raise ValueError('Explicit leaf measurements currently support native surfaces')
    if single:
        native=history.external.times(source);reference=draft.get('time')
        if native and (type(reference) not in (int,float) or reference not in native):
            raise ValueError('Choose an exact native frame for the selected leaves')
        if not native and any(draft.get(k) is not None for k in ('time','time_units','time_origin')):
            raise ValueError('A static dataset has no physical clock')
        times=[reference]
        for key in ('units','frame','quantity','coordinate_units','coordinate_frame','measure'):
            if not isinstance(draft.get(key),str) or not draft[key].strip() or draft[key].lower() in ('unknown','undeclared'):
                raise ValueError('Declare the leaf measurement quantity, units and fixed frame')
        if native and any(not isinstance(draft.get(k),str) or not draft[k].strip() for k in ('time_units','time_origin')):
            raise ValueError('Declare the actual native clock semantics and units')
    else:times,reference=history._clock(source,draft)
    p=history.p;before=p.GetActiveSource(),p.GetActiveView();temporary=[];result=None
    try:
        frozen=history.analysis._freeze(source,reference,namespace,temporary);data=history.analysis._fetch(frozen)
        captures=selected(data,draft['leaf_selections'],track=history._tracking,faces=history._faces)
        widths=set()
        for row in captures:
            attrs=row['data'].GetPointData() if draft['association']=='POINTS' else row['data'].GetCellData()
            field=attrs.GetArray(draft['array'])
            row['field_components']=field.GetNumberOfComponents() if field is not None else None
            if field is not None:widths.add(field.GetNumberOfComponents())
        if len(widths)>1:raise ValueError('Selected leaves have incompatible native field components')
        samples=[]
        for time in times:
            local=[]
            try:
                frozen=history.analysis._freeze(source,time,namespace,local);current=history.analysis._fetch(frozen)
                reports=[]
                for capture in captures:
                    row=resolve(current,capture['leaf_path']);identity,_=history._tracking(row['data'])
                    if identity!=capture['identity'] or row['flat_index']!=capture['flat_index']:
                        raise ValueError('Native leaf identities or connectivity changed between frames')
                    attrs=row['data'].GetPointData() if draft['association']=='POINTS' else row['data'].GetCellData()
                    field=attrs.GetArray(draft['array'])
                    if field is not None and capture['field_components'] is not None and field.GetNumberOfComponents()!=capture['field_components']:
                        raise ValueError('Native field components changed between selected frames')
                    report=history.surface_average(row['data'],draft,capture['surface_faces'])
                    reports.append({**report,'leaf_path':deepcopy(row['leaf_path']),'flat_index':row['flat_index']})
                samples.append({'time':time,**aggregate(reports,mode)})
            finally:history.analysis.cleanup({'proxies':local})
        array='SurfaceIntegral' if mode=='integral_sum' else history.SURFACE_ARRAY
        def columns(rows):
            values={'SampleIndex' if single else 'Time':[0] if single else times,
                array:[row['value'] for row in rows],
                'vtkValidMask':[int(row.get('valid') is True) for row in rows],
                'SurfaceArea':[row.get('area') for row in rows]}
            if array!='SurfaceIntegral':
                values['SurfaceIntegral']=[row.get('integral',row.get('area')*row['value']
                    if row.get('area') is not None and row.get('value') is not None else None) for row in rows]
            if draft.get('geometry')=='current':
                values['ReferenceSurfaceArea']=[row.get('reference_geometry_area') for row in rows]
            return values
        if mode=='per_leaf':
            result=_tables(history,[columns([row['leaves'][i] for row in samples]) for i in range(len(captures))],namespace)
        else:result=history._table(columns(samples),namespace)
        summary={**{k:deepcopy(draft.get(k)) for k in ('units','frame','quantity','coordinate_units',
            'coordinate_frame','time_units','time_origin','geometry_state')},
            'measurement':kind,'input_array':draft['array'],'array':array,'association':'ROWS',
            'recipe':deepcopy(draft),'input_association':draft['association'],'time_values':[] if single else times,
            'reference_time':reference,'tracking':'explicit_leaf_native_ids_and_connectivity',
            'samples':samples,'aggregation':mode,'geometry':draft['geometry'],'measure':draft['measure'],
            'area_unit':draft['coordinate_units']+'^2','integral_unit':draft['units']+'*'+draft['coordinate_units']+'^2',
            'reduction':{'per_leaf':'native_leaf_results','area_weighted_mean':'native_leaf_area_weighted_mean',
                         'integral_sum':'native_leaf_integral_sum'}[mode],
            'component_label':'scalar' if draft.get('component') is None else str(draft['component']),
            'location':str([row['leaf_path'] for row in captures]),
            'sample_semantics':'explicit_native_leaf_surface_measurement','qualification':'UNKNOWN',
            'leaf_results':[{**{k:deepcopy(row[k]) for k in ('leaf_path','flat_index','identity','tracking','surface_faces')},
                             'table_block':[i] if mode=='per_leaf' else []} for i,row in enumerate(captures)]}
        if mode=='integral_sum':summary['units']=summary['integral_unit']
        if draft.get('geometry')=='current':
            observed=[report for sample in samples for report in sample['leaves'] if report.get('valid') is True]
            verified=observed and all(report.get('display_scale_used') is False and
                report.get('geometry_state')==draft['geometry_state'] for report in observed)
            summary['display_scale_used']=False if verified else None
        if single:summary.update(time=reference,axis_name='SampleIndex',axis_unit='1',axis_values=[0])
        return {'source':result,'proxies':[result],'summary':summary}
    except BaseException:
        if result is not None:p.Delete(result)
        raise
    finally:
        history.analysis.cleanup({'proxies':temporary});p.SetActiveSource(before[0]);p.SetActiveView(before[1])
