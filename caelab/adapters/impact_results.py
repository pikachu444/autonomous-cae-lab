"""Read actual converter bytes, preserving identity, missing rows and padding masks."""
import csv
import math
from pathlib import Path
from xml.etree import ElementTree as ET
from ..evaluation import file_hash
from ..storage import save_json

GLOBAL_NAMES = ['INTERNAL ENERGY','KINETIC ENERGY','X-MOMENTUM','Y-MOMENTUM','Z-MOMENTUM',
    'MASS','TIME STEP','ROTATION ENERGY','EXTERNAL WORK','SPRING ENERGY','CONTACT ENERGY',
    'HOURGLASS ENERGY','ELASTIC CONTACT ENERGY','FRICTIONAL CONTACT ENERGY',
    'DAMPING CONTACT ENERGY','PLASTIC WORK','ADDED MASS','PERCENTAGE ADDED MASS',
    'INLET MASS','OUTLET MASS','INLET ENERGY','OUTLET ENERGY','NO NAME']
GLOBAL_LABELS = ['내부 에너지','운동 에너지','X 운동량','Y 운동량','Z 운동량','질량','시간증분',
    '회전 에너지','외력 일','스프링 에너지','접촉 에너지','아워글라스 에너지','탄성 접촉 에너지',
    '마찰 접촉 에너지','접촉 감쇠 에너지','소성 일','추가 질량','추가 질량 비율',
    '유입 질량','유출 질량','유입 에너지','유출 에너지','원본 23번 채널']


def history(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.reader(stream)
        header=[v.strip() for v in next(reader)]
        if header and not header[-1]: header.pop()
        if header[:1]!=['time'] or header[1:24]!=GLOBAL_NAMES:
            raise ValueError('Native history global layout differs; original CSV retained')
        raw=[]
        for line,row in enumerate(reader,2):
            if row and not row[-1].strip(): row.pop()
            if len(row)!=len(header): raise ValueError('Incomplete native history row '+str(line))
            values=[]
            for value in row:
                try: value=float(value)
                except ValueError: value=None
                values.append(value if value is not None and math.isfinite(value) else None)
            raw.append({'source_row':line,'tokens':row,'values':values})
    times=[r['values'][0] for r in raw]
    if not times or any(x is None for x in times) or any(b<=a for a,b in zip(times,times[1:])):
        raise ValueError('Native history requires finite strictly increasing times')
    responses={}
    for i,(name,label) in enumerate(zip(GLOBAL_NAMES,GLOBAL_LABELS),1):
        # Channel 23 is retained, not assigned a physical meaning from "NO NAME".
        if name=='NO NAME': continue
        unit,factor=('J',.001) if 'ENERGY' in name or 'WORK' in name else (
            ('kg',1000.) if 'MASS' in name and 'PERCENTAGE' not in name else
            ('kg m/s',1.) if 'MOMENTUM' in name else ('s',1.) if name=='TIME STEP' else ('%',1.))
        selected=[r for r in raw if r['values'][i] is not None]
        if selected:
            responses['global_'+str(i)]={'kind':'series','unit':unit,
                'value':[r['values'][i]*factor for r in selected],
                'axes':[{'name':'time','unit':'s','values':[r['values'][0] for r in selected]}],
                'component':'scalar','location':'whole_model','reduction':'none',
                'metadata':{'label':label,'native_name':name,'native_variable':i,'source_rows':[r['source_row'] for r in selected],
                    'invalid_source_rows':[r['source_row'] for r in raw if r['values'][i] is None],
                    'source_artifact':Path(path).name,'source_sha256':file_hash(path),
                    'value_scale_from_Mg_mm_s':factor,'clock':'NATIVE_PHYSICAL_TIME'}}
    return responses,{'header':header,'rows':raw,'unmapped_columns':header[24:],
        'force_note':'Converter may differentiate impulses. Unmapped group columns are retained without a native-force claim.'}


def read_vtk(path):
    """Bounded reader of the pinned converter's legacy ASCII output, not arbitrary VTK."""
    path=Path(path)
    if path.stat().st_size>512*1024**2: raise ValueError('Animation text exceeds 512 MiB')
    lines=path.read_text(encoding='ascii').splitlines()
    if len(lines)<4 or lines[2].strip()!='ASCII' or lines[3].strip()!='DATASET UNSTRUCTURED_GRID':
        raise ValueError('Expected the official ANIM converter ASCII grid')
    tokens=iter(' '.join(lines[4:]).split())
    result={'points':[],'cells':[],'types':[],'POINTS':{},'CELLS':{},'FIELD':{}}
    association='FIELD'; count=None
    def take(n,cast=float):
        if n<0 or n>30000000: raise ValueError('Native array size exceeds bounds')
        return [cast(next(tokens)) for _ in range(n)]
    def add(name,components,values):
        if name in result[association]: raise ValueError('Duplicate native array name')
        result[association][name]={'components':components,'values':values}
    try:
        for key in tokens:
            if key=='FIELD':
                next(tokens); arrays=int(next(tokens))
                if not 0<=arrays<=256: raise ValueError('Invalid native field array count')
                for _ in range(arrays):
                    name=next(tokens); components=int(next(tokens)); tuples=int(next(tokens)); next(tokens)
                    add(name,components,take(components*tuples))
            elif key=='POINTS':
                n=int(next(tokens)); next(tokens); flat=take(3*n)
                result['points']=[flat[i:i+3] for i in range(0,len(flat),3)]
            elif key=='CELLS':
                n=int(next(tokens)); size=int(next(tokens)); seen=0
                for _ in range(n):
                    width=int(next(tokens)); row=take(width,int); seen+=width+1; result['cells'].append(row)
                if size!=seen: raise ValueError('Native connectivity size differs')
            elif key=='CELL_TYPES':
                result['types']=take(int(next(tokens)),int)
            elif key in ('POINT_DATA','CELL_DATA'):
                association='POINTS' if key=='POINT_DATA' else 'CELLS'
                count=int(next(tokens))
                if count!=len(result['points' if association=='POINTS' else 'cells']): raise ValueError('Native tuple count differs')
            elif key in ('SCALARS','VECTORS','TENSORS'):
                name=next(tokens); next(tokens)
                components=int(next(tokens)) if key=='SCALARS' else 3 if key=='VECTORS' else 9
                if key=='SCALARS':
                    if next(tokens)!='LOOKUP_TABLE' or next(tokens)!='default': raise ValueError('Unexpected scalar lookup')
                if count is None or not 1<=components<=9: raise ValueError('Invalid array shape')
                add(name,components,take(count*components))
            else: raise ValueError('Unsupported converter record: '+key)
    except StopIteration as error: raise ValueError('Truncated animation converter output') from error
    if len(result['types'])!=len(result['cells']): raise ValueError('Missing cell types')
    widths={1:1,3:2,5:3,9:4,10:4,12:8}
    for kind,row in zip(result['types'],result['cells']):
        # Converter sometimes writes a repeated corner for triangles. Do not
        # repair topology silently; retain the raw output for diagnosis.
        if kind not in widths or len(row)!=widths[kind] or any(n<0 or n>=len(result['points']) for n in row):
            raise ValueError('Native display-cell topology is inconsistent')
    if not all(math.isfinite(x) for p in result['points'] for x in p): raise ValueError('Invalid native coordinates')
    clock=result['FIELD'].get('TIME',{}).get('values',[])
    if len(clock)!=1 or not math.isfinite(clock[0]): raise ValueError('Missing native physical time')
    result['time']=clock[0]
    for assoc,name in (('POINTS','NODE_ID'),('CELLS','ELEMENT_ID'),('CELLS','EROSION_STATUS')):
        item=result[assoc].get(name)
        if not item or item['components']!=1 or any(not math.isfinite(x) or x!=int(x) for x in item['values']):
            raise ValueError('Missing native identity/activity array '+name)
    if len(set(result['POINTS']['NODE_ID']['values']))!=len(result['points']): raise ValueError('Duplicate native node ID')
    if any(v not in (0,1) for v in result['CELLS']['EROSION_STATUS']['values']): raise ValueError('Invalid erosion mask')
    return result


def field_units(name,components,association):
    key=name.upper()
    if key in ('NODE_ID','ELEMENT_ID','PART_ID','EROSION_STATUS'): return '1','native_identity_or_activity'
    exact={'DISPLACEMENT':('mm','displacement'),'VELOCITY':('mm/s','velocity'),
           'ACCELERATION':('mm/s^2','acceleration')}
    if association=='POINTS' and components==3 and key in exact: return exact[key]
    if association=='CELLS' and key in ('3DELEM_STRESS','3DELEM_STRESSES') and components==9: return 'MPa','Cauchy_stress'
    # Preserve unknown names/values, but do not invent their units or law.
    return None


def write_post(folder, frames):
    from apps.desktop_post.prepare import data_array
    folder=Path(folder); folder.mkdir()
    pvd=ET.Element('VTKFile',type='Collection',version='0.1',byte_order='LittleEndian')
    collection=ET.SubElement(pvd,'Collection'); times=[]; declared=None; observations=[]
    for index,(raw_path,raw) in enumerate(frames):
        t=raw['time']
        if times and t<=times[-1]: raise ValueError('Duplicate/out-of-order native animation time')
        times.append(t)
        vtk=ET.Element('VTKFile',type='UnstructuredGrid',version='0.1',byte_order='LittleEndian',header_type='UInt32')
        piece=ET.SubElement(ET.SubElement(vtk,'UnstructuredGrid'),'Piece',
            NumberOfPoints=str(len(raw['points'])),NumberOfCells=str(len(raw['cells'])))
        data_array(ET.SubElement(piece,'Points'),'Position_mm',(v for p in raw['points'] for v in p),3)
        cells=ET.SubElement(piece,'Cells'); offset=0; offsets=[]
        for row in raw['cells']: offset+=len(row); offsets.append(offset)
        data_array(cells,'connectivity',(n for row in raw['cells'] for n in row),integer=True)
        data_array(cells,'offsets',offsets,integer=True); data_array(cells,'types',raw['types'],integer=True)
        metadata=[]; masks={}
        for association,tag in (('POINTS','PointData'),('CELLS','CellData')):
            parent=ET.SubElement(piece,tag)
            for name,item in raw[association].items():
                components=item['components']; values=item['values']
                data_array(parent,name,values,components)
                units=field_units(name,components,association)
                if units:
                    metadata.append({'association':association,'name':name,'components':components,
                        'units':units[0],'frame':'MODEL_GLOBAL','measure':units[1]})
                if association=='CELLS' and name.startswith(('1DELEM_','2DELEM_','3DELEM_','SPHELEM_')):
                    prefix=name.split('_')[0]
                    kinds={'1DELEM':{3},'2DELEM':{5,9},'3DELEM':{10,12},'SPHELEM':{1}}[prefix]
                    mask=[int(kind in kinds and all(math.isfinite(x) for x in values[i*components:(i+1)*components]))
                          for i,kind in enumerate(raw['types'])]
                    mask_name=name+'_Applicable'
                    data_array(parent,mask_name,mask,integer=True); masks[name]=mask_name
                    metadata.append({'association':association,'name':mask_name,'components':1,'units':'1',
                                     'frame':'MODEL_GLOBAL','measure':'field_family_and_finite_mask'})
        if declared is None: declared=metadata
        elif declared!=metadata: raise ValueError('Native animation array declaration changes across frames')
        filename=f'frame{index:04d}.vtu'
        ET.ElementTree(vtk).write(folder/filename,encoding='utf-8',xml_declaration=True)
        ET.SubElement(collection,'DataSet',timestep=format(t,'.17g'),group='',part='0',file=filename)
        observations.append({'time_s':t,'raw_vtk':str(raw_path.name),'raw_sha256':file_hash(raw_path),
            'field_applicability':masks,'active_mask':'EROSION_STATUS','cycle':'NOT_RECORDED_BY_CONVERTER',
            'element_identity':'source FE ID may occur in multiple display cells'})
    ET.ElementTree(pvd).write(folder/'impact.pvd',encoding='utf-8',xml_declaration=True)
    save_json(folder/'frames.json',observations)
    return {'coordinate_units':'mm','coordinate_frame':'MODEL_GLOBAL','static':None,
        'time':{'unit':'s','semantics':'NATIVE_ANIMATION_TIME','values':times},'arrays':declared or []}
