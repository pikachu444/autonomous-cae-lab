"""Exact CCX 2.22 laminate DAT tuples and separately recovered FRD layer solids."""
from pathlib import Path
import hashlib
import json
import math
import re
from io import BytesIO

from .adapters.shell_deck import read_bytes, json_read, sha
from .adapters.shell_results import (ascii_source, EXPANSION, FRD_FROM_C3D20, BOTTOM, TOP,
    DAT_HEADER, DAT_NAMES, DAT_STEP, DAT_INCREMENT, _coordinate_error, read_frd)
from .adapters.fixture_field import _frd_record, _identifier, _number
from .adapters.structural_family_mesh import hexa20_point_coordinates
from .adapters.composite_shell_deck import build
from .shell_model import dot, sub, unit

G=.577350269189626  # CCX 2.22 gauss.f gauss3d2; r fastest, z slowest.
GAUSS8=tuple((r,s,t) for t in (-G,G) for s in (-G,G) for r in (-G,G))
KIND='calculix-composite-shell-inspection'


def selected_tensor(row,field,*,basis='GLOBAL',layer=None):
    """Keep native tuples; an explicit basis change is separately derived."""
    from .adapters.shell_results import rotate_tensor
    values=list(row[field]['values'])
    if basis=='GLOBAL':return values
    if basis!='DECLARED_PLY' or layer is None or layer['ply_id']!=row['ply_id']:
        raise ValueError('Select the exact retained ply basis')
    return rotate_tensor(values,layer['axes_global'])


def expansion(path,mesh,frd_path):
    text=ascii_source(path);mother={}
    matches=list(EXPANSION.finditer(text))
    for match in matches:
        e=int(match[1]);original=tuple(map(int,match[3].split()));whole=tuple(map(int,match[5].split()))
        if (e in mother or e not in mesh['elements'] or original!=tuple(mesh['elements'][e]) or
            re.fullmatch(r'S8R\s+C',match[2].strip()) is None or match[4].strip()!='C3D20RLC' or
            len(whole)!=20 or len(set(whole))!=20 or min(whole)<=0):
            raise ValueError('Composite .12d source family/order/whole-thickness topology differs')
        mother[e]={'original':original,'whole_expanded':whole,'source_label':match[2],
                   'expanded_label':match[4],'source_line':text[:match.start()].count('\n')+1}
    if set(mother)!=set(mesh['elements']):raise ValueError('Missing original shell expansion')
    lines=ascii_source(frd_path).splitlines();coordinates={};tokens={};topology={};materials={};i=0
    while i<len(lines):
        parts=lines[i].split();i+=1
        if parts and parts[0]=='2C':
            while i<len(lines) and lines[i].strip()!='-3':
                n,xyz,raw=_frd_record(lines[i].rstrip(),3);i+=1
                if n in coordinates:raise ValueError('Repeated FRD coordinate')
                coordinates[n]=xyz;tokens[n]=raw
        elif parts and parts[0]=='3C':
            while i<len(lines) and lines[i].strip()!='-3':
                row=lines[i].rstrip();i+=1
                if len(row)!=28 or row[:3]!=' -1' or row[13:18].strip()!='4' or row[18:23].strip()!='0':
                    raise ValueError('Expected per-layer FRD HEX20 solids')
                e=_identifier(row[3:13].strip());material=_identifier(row[23:28].strip());conn=[]
                while i<len(lines) and lines[i][:3]==' -2':
                    line=lines[i].rstrip();i+=1
                    if (len(line)-3)%10 or len(line)>103:raise ValueError('Malformed layer connectivity')
                    conn.extend(_identifier(line[j:j+10].strip()) for j in range(3,len(line),10))
                if e in topology or len(conn)!=20 or len(set(conn))!=20:raise ValueError('Repeated or incomplete layer solid')
                # Normalize FRD ordering to the existing canonical CalculiX HEX20 ordering.
                ccx=[None]*20
                for f,c in enumerate(FRD_FROM_C3D20):ccx[c]=conn[f]
                topology[e]=tuple(ccx);materials[e]=material
            break
    material_ids={name:i+1 for i,name in enumerate(sorted(mesh['values']['materials']))}
    native={};counter=max(mesh['elements'])
    for e in sorted(mesh['elements']):
        for ply in mesh['native_layers'][e]:
            counter+=1
            if counter not in topology or materials[counter]!=material_ids[ply['material_id']]:
                raise ValueError('FRD layer solid ID/material order differs from CCX source mapping')
            native[counter]={'expanded':topology[counter],'original':tuple(mesh['elements'][e]),
                             'shell_element_id':e,**ply}
    if set(native)!=set(topology):raise ValueError('Unexpected FRD layer solids')
    # Verify native layer boundary positions relative to the actual outer faces.
    for e,layers in ((e,[row for row in native.values() if row['shell_element_id']==e]) for e in mesh['elements']):
        region=mesh['region_by_element'][e];total=sum(p['thickness_mm'] for p in layers)
        for j,node in enumerate(mesh['elements'][e]):
            bottom=layers[0]['expanded'][BOTTOM[j]];top=layers[-1]['expanded'][TOP[j]]
            a,b=coordinates[bottom],coordinates[top];delta=sub(b,a);distance=math.hypot(*delta)
            error=math.hypot(*[x+y for x,y in zip(map(_coordinate_error,tokens[bottom]),map(_coordinate_error,tokens[top]))])
            if abs(distance-total)>error+64*math.ulp(total) or dot(delta,mesh['normals'][e])<=0:
                raise ValueError('Layer stack total thickness/positive normal differs')
            for c in range(3):
                restored=(.5-region['offset'])*a[c]+(.5+region['offset'])*b[c]
                bound=abs(.5-region['offset'])*_coordinate_error(tokens[bottom][c])+abs(.5+region['offset'])*_coordinate_error(tokens[top][c])
                if abs(restored-mesh['nodes'][node][c])>bound+64*math.ulp(max(abs(restored),abs(mesh['nodes'][node][c]))):
                    raise ValueError('Layer stack reference plane/offset differs')
            accumulated=0.
            for ply in layers:
                for sign,fraction in ((BOTTOM[j],accumulated/total),(TOP[j],(accumulated+ply['thickness_mm'])/total)):
                    actual=ply['expanded'][sign]
                    for c in range(3):
                        expected=(1-fraction)*a[c]+fraction*b[c]
                        bound=(1-fraction)*_coordinate_error(tokens[bottom][c])+fraction*_coordinate_error(tokens[top][c])+_coordinate_error(tokens[actual][c])
                        if abs(coordinates[actual][c]-expected)>bound+64*math.ulp(max(abs(expected),abs(coordinates[actual][c]))):
                            raise ValueError('Native layer boundary position/order differs')
                accumulated+=ply['thickness_mm']
    observed=read_frd(frd_path,native,profile='S8R_COMPOSITE',material_ids=materials)
    return mother,native,observed


def read_dat(path,mesh,native):
    lines=ascii_source(path).splitlines();tables={};i=0;diagnostic=None;step=1;increment=None
    expected={(e,j) for e,layers in mesh['native_layers'].items() for j in range(1,len(layers)*8+1)}
    while i<len(lines):
        line=lines[i];i+=1
        if not line.strip():continue
        if DAT_STEP.fullmatch(line):
            step=int(DAT_STEP.fullmatch(line)[1])
            if step!=1:raise ValueError('Only one laminate static step is supported')
            continue
        if DAT_INCREMENT.fullmatch(line):increment=int(DAT_INCREMENT.fullmatch(line)[1]);continue
        header=DAT_HEADER.fullmatch(line)
        if not header or header[1].lower() not in ('stresses','strains') or header[3].upper()!='LABCOMPOSITE':
            raise ValueError('Unexpected composite DAT table/content')
        field,labels=DAT_NAMES[header[1].lower()]
        if tuple(p.strip().lower() for p in header[2].split(','))!=labels:raise ValueError('Composite DAT tuple labels differ')
        time=_number(header[4]);key=(time,field)
        if time<=0 or key in tables:raise ValueError('Repeated/invalid composite DAT frame')
        values={};start=i
        while i<len(lines) and not lines[i].strip():i+=1
        while i<len(lines) and lines[i].strip() and DAT_HEADER.fullmatch(lines[i]) is None:
            parts=lines[i].split();i+=1
            if len(parts)!=8:raise ValueError('Expected original GLOBAL DAT element/IP/six-tuple')
            e,j=map(_identifier,parts[:2]);point=(e,j)
            if point not in expected or point in values:raise ValueError('Repeated/foreign laminate integration point')
            raw=[_number(p) for p in parts[2:]]
            values[point]={'values':[raw[k] for k in (0,1,2,3,5,4)],'raw_tokens':parts[2:],
                           'raw_component_order':list(labels[2:]),'source_line':i,'table_header_line':start}
        if set(values)!=expected:
            if i<len(lines):raise ValueError('Incomplete laminate table before later content')
            diagnostic={'reason':'Truncated final layer table; previous complete tables retained','line':i};break
        tables[key]={'values':values,'step':step,'increment':increment,'load_parameter_token':header[4]}
    solid={(v['shell_element_id'],v['native_layer']):(key,v) for key,v in native.items()}
    frames=[]
    for time in sorted({k[0] for k in tables}):
        fields={field:table for (t,field),table in tables.items() if t==time};rows=[]
        for e,j in sorted(expected):
            layer=(j-1)//8+1;local=(j-1)%8;identifier,ply=solid[(e,layer)]
            position=hexa20_point_coordinates([mesh_xyz for mesh_xyz in ply['coordinates_mm']],GAUSS8[local])
            rows.append({'element_id':e,'native_solid_id':identifier,'integration_point':j,
                'native_layer':layer,'ply_id':ply['ply_id'],'ui_position':ply['ui_position'],
                'material_id':ply['material_id'],'inplane_ip':local%4+1,'thickness_ip':local//4+1,
                'natural_coordinates':list(GAUSS8[local]),'position_derived_mm':position,
                'position_provenance':'Calculated from printed FRD HEX20 coordinates, not native DAT COORD',
                **{field:table['values'][(e,j)] for field,table in fields.items()}})
        controls=next(iter(fields.values()))
        frames.append({'step':controls['step'],'increment':controls['increment'],'load_parameter':time,
                       'load_parameter_token':controls['load_parameter_token'],'fields':sorted(fields),'rows':rows})
    return {'status':'COMPLETE' if frames and diagnostic is None and all(set(f['fields'])=={'S','E'} for f in frames) else 'PARTIAL',
            'frames':frames,'diagnostic':diagnostic,'basis':'GLOBAL','recovery':'none_native_DAT',
            'native_version':'2.22','time_measure':'static_load_parameter_not_physical_time'}


def read_native(folder,model):
    _,mesh=build(model);folder=Path(folder)
    mother,native,frd=expansion(folder/'composite.12d',mesh,folder/'composite.frd')
    for row in native.values():row['coordinates_mm']=[frd['coordinates'][n] for n in row['expanded']]
    dat=read_dat(folder/'composite.dat',mesh,native)
    return {'mother_expansion':mother,'layer_solids':native,'frd':frd,'dat':dat,'mesh':mesh}


def layer_view(destination,observed,frame):
    from xml.etree import ElementTree as ET
    from .adapters.shell_post import _document,_array,_write_xml,TENSOR_COMPONENTS,FRAME
    points=[];cells=[];ordered=[];solids=[]
    for key,row in observed['layer_solids'].items():
        cells.append(list(range(len(points),len(points)+20)));solids.append((key,row))
        points.extend(row['coordinates_mm']);ordered.extend(row['expanded'])
    vtk,pd,cd=_document(points,cells,25);declarations=[]
    for field,name,unit,names,measure in (
        ('DISP','U_mm', 'mm',['X','Y','Z'],'displacement'),
        ('STRESS','S_FRD_global','MPa',TENSOR_COMPONENTS,'stress'),
        ('TOSTRAIN','E_FRD_global','1',TENSOR_COMPONENTS,'strain')):
        if field in frame['fields']:
            _array(pd,declarations,name,[v for n in ordered for v in frame['fields'][field][n]],components=len(names),
                   unit=unit,frame=FRAME,measure=measure,names=names,
                   location='native_expanded_layer_node',recovery='native_nodal_dof' if field=='DISP' else 'native_extrapolated_nodal_averaged')
    for name,values in (
        ('OriginalShellId',[r['shell_element_id'] for _,r in solids]),('NativeSolidId',[key for key,_ in solids]),
        ('PlyPosition',[r['ui_position'] for _,r in solids]),('NativeLayer',[r['native_layer'] for _,r in solids])):
        _array(cd,declarations,name,values,integer=True)
    _write_xml(ET.ElementTree(vtk),destination)
    return {'coordinate_units':'mm','coordinate_frame':FRAME,'arrays':declarations,
            'time_measure':'static_load_parameter_not_physical_time','engineering_valid':False,
            'layer_order':'PlyPosition 1 is top(+normal); NativeLayer 1 is bottom(-normal)',
            'surface_recovery':'native_extrapolated_nodal_averaged; not DAT integration points'}


def ip_view(destination,frame):
    from xml.etree import ElementTree as ET
    from .adapters.shell_post import _document,_array,_write_xml,TENSOR_COMPONENTS,FRAME
    rows=frame['rows'];vtk,pd,cd=_document([r['position_derived_mm'] for r in rows],[[i] for i in range(len(rows))],1)
    declarations=[]
    for field,unit,measure in (('S','MPa','stress'),('E','1','strain')):
        if field in frame['fields']:
            _array(cd,declarations,field+'_DAT_global',[v for row in rows for v in row[field]['values']],components=6,
                   unit=unit,frame=FRAME,measure=measure,names=TENSOR_COMPONENTS,
                   location='layer_integration_point',recovery='none_native_DAT')
    for key,label in (('element_id','OriginalShellId'),('native_solid_id','NativeSolidId'),('ui_position','PlyPosition'),
                      ('integration_point','NativeIP'),('inplane_ip','InplaneIP'),('thickness_ip','ThicknessIP')):
        _array(cd,declarations,label,[r[key] for r in rows],integer=True)
    _write_xml(ET.ElementTree(vtk),destination)
    return declarations


def retain(folder,model,observed,*,execution_status):
    from .storage import save_json
    from .adapters.shell_post import collection
    folder=Path(folder);entries=[];view_files=[];metadata=None
    for i,frame in enumerate(observed['frd']['frames']):
        name=f'layers_{i:04d}.vtu';metadata=layer_view(folder/name,observed,frame)
        entries.append((name,frame['load_parameter']));view_files.append(name)
    if not entries:raise ValueError('No complete native layer field is available')
    collection(folder/'layers.pvd',entries);view_files.append('layers.pvd')
    ips=[]
    for i,frame in enumerate(observed['dat']['frames']):
        name=f'ip_{i:04d}.vtu';ip_view(folder/name,frame);ips.append((name,frame['load_parameter']));view_files.append(name)
    if ips:collection(folder/'integration_points.pvd',ips);view_files.append('integration_points.pvd')
    save_json(folder/'composite_values.json',{'kind':KIND,'schema_version':'1','model':model,'observed':observed,
              'execution_status':execution_status,'native_metadata':metadata,'engineering_valid':False})
    names=['composite_values.json',*view_files]+['source/'+p.name for p in sorted((folder/'source').iterdir()) if p.is_file()]
    primary=entries[-1][0]
    manifest={'kind':KIND,'schema_version':'1','main_view':primary,'native_metadata':metadata,
              'files':[{'relative':name,'bytes':(folder/name).stat().st_size,'sha256':sha(folder/name)} for name in names]}
    save_json(folder/'composite_inspection.json',manifest)
    return primary,{**metadata,'composite_inspection':{'relative':'composite_inspection.json',
                'sha256':sha(folder/'composite_inspection.json'),'bytes':(folder/'composite_inspection.json').stat().st_size}}


def load(view,reference=None,*,verify_observations=True):
    from .shell_inspection import _member
    from .adapters.shell_post import collection
    view=Path(view).absolute();root=view.parent;reference=reference or {'relative':'composite_inspection.json'}
    manifest_path=_member(root,reference['relative']);raw=read_bytes(manifest_path)
    if ('sha256' in reference and hashlib.sha256(raw).hexdigest()!=reference['sha256'] or
        'bytes' in reference and len(raw)!=reference['bytes']):raise ValueError('Composite result manifest changed')
    manifest=json_read(manifest_path)
    if manifest.get('kind')!=KIND or manifest.get('schema_version')!='1' or manifest.get('main_view')!=view.name:raise ValueError('Composite result/view identity differs')
    members={};paths=[manifest_path]
    for row in manifest['files']:
        name=row['relative'];path=_member(root,name)
        if name in members or path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256']:
            raise ValueError('Composite retained source changed: '+name)
        members[name]=path;paths.append(path)
    required={view.name,'composite_values.json','source/composite.inp','source/composite.frd','source/composite.dat','source/composite.12d'}
    if not required<=members.keys():raise ValueError('Composite source/result set is incomplete')
    data=json_read(members['composite_values.json'],256*1024**2)
    if data.get('kind')!=KIND or data['native_metadata']!=manifest['native_metadata']:raise ValueError('Composite metadata differs')
    text,_=build(data['model'])
    if read_bytes(members['source/composite.inp'])!=text.encode('ascii'):raise ValueError('Original laminate deck differs from saved conditions')
    if verify_observations:
        original=read_native(root/'source',data['model'])
        normalized=lambda obj:json.loads(json.dumps(obj,allow_nan=False))
        if normalized(original)!=data['observed']:raise ValueError('Layer observations differ from original native files')
        entries=[]
        for i,frame in enumerate(original['frd']['frames']):
            name=f'layers_{i:04d}.vtu';buffer=BytesIO();layer_view(buffer,original,frame)
            if name not in members or read_bytes(members[name])!=buffer.getvalue():raise ValueError('Layer view differs from exact FRD tuples')
            entries.append((name,frame['load_parameter']))
        buffer=BytesIO();collection(buffer,entries)
        if read_bytes(members['layers.pvd'])!=buffer.getvalue():raise ValueError('Layer frame collection differs')
        ips=[]
        for i,frame in enumerate(original['dat']['frames']):
            name=f'ip_{i:04d}.vtu';buffer=BytesIO();ip_view(buffer,frame)
            if name not in members or read_bytes(members[name])!=buffer.getvalue():raise ValueError('Integration point view differs from exact DAT tuples')
            ips.append((name,frame['load_parameter']))
        if ips:
            buffer=BytesIO();collection(buffer,ips)
            if 'integration_points.pvd' not in members or read_bytes(members['integration_points.pvd'])!=buffer.getvalue():raise ValueError('Integration point frame collection differs')
    return {'manifest':manifest,'data':data,'paths':paths,'view':view}


def explicit_manifest(path):
    """Register only an explicitly selected pinned native laminate bundle."""
    from .shell_inspection import _member
    path=Path(path).absolute()
    if path.name!='composite_inspection.json':raise ValueError('Select composite_inspection.json')
    manifest=json_read(path);view=_member(path.parent,manifest['main_view'])
    reference={'relative':path.name,'sha256':sha(path),'bytes':path.stat().st_size}
    checked=load(view,reference)
    return view,{**checked['manifest']['native_metadata'],'composite_inspection':reference}
