"""CalculiX 2.22 ASCII S8 result locations, tied to native .12d expansion.

No nearest-node matching, extrapolation, interpolation or missing-value fill.
FRD S/E at expanded surface nodes are native recovered/averaged estimates.
DAT S/E/COORD are internal Gauss-point observations, never surface stresses.
"""
from decimal import Decimal
import math
import re

from caelab.shell_model import GAUSS27, unit, dot, sub, basis
from .shell_deck import read_bytes

CCX_222 = 'cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54'
FRD_FROM_C3D20 = tuple(range(12))+tuple(range(16,20))+tuple(range(12,16))
BOTTOM = (0,1,2,3,8,9,10,11)
TOP = (4,5,6,7,12,13,14,15)
LABELS = {
    'DISP': ('D1 1 2 1 0','D2 1 2 2 0','D3 1 2 3 0','ALL 1 2 0 0 1ALL'),
    'STRESS': ('SXX 1 4 1 1','SYY 1 4 2 2','SZZ 1 4 3 3',
               'SXY 1 4 1 2','SYZ 1 4 2 3','SZX 1 4 3 1'),
    'TOSTRAIN': ('EXX 1 4 1 1','EYY 1 4 2 2','EZZ 1 4 3 3',
                 'EXY 1 4 1 2','EYZ 1 4 2 3','EZX 1 4 3 1'),
    'ERROR': ('STR(%) 1 1 0 0',),
}
WIDTHS = {'DISP':3,'STRESS':6,'TOSTRAIN':6,'ERROR':1}
REQUIRED = {'DISP','STRESS','TOSTRAIN'}
EXPANSION = re.compile(
    r'\bELEMENT\s+(\d+)\s*with label\s*"([^"\r\n]+)"\s*and with nodes:\s*'
    r'([\d\s]+?)\s*is expanded into a\s*"([^"\r\n]+)"\s*element with topology:\s*([\d\s]+)',
    re.IGNORECASE)


def ascii_source(path):
    text=read_bytes(path).decode('ascii').replace('\r\n','\n')
    if '\x00' in text or '\r' in text:
        raise ValueError('Malformed native shell ASCII source')
    return text


def read_expansion(path, elements, *, family='S8'):
    # ccx 2.22 beamsections.f sets lakon(8)='R' for RECT;
    # gen3delem.f changes only lakon(1:7), retaining that final shape marker.
    profiles={'S8':('S8','C3D20 L',8), 'B32R_RECT':('B32R   R','C3D20RBR',3)}
    if family not in profiles:
        raise ValueError('Unsupported native expansion family')
    original_label, expanded_label, original_count=profiles[family]
    text=ascii_source(path)
    found={}
    for match in EXPANSION.finditer(text):
        e=int(match[1]); original=tuple(map(int,match[3].split()))
        expanded=tuple(map(int,match[5].split()))
        if (e in found or match[2].strip()!=original_label or match[4].strip()!=expanded_label
                or e not in elements or original!=tuple(elements[e]) or len(original)!=original_count
                or len(expanded)!=20 or min(expanded)<=0 or len(set(expanded))!=20):
            raise ValueError('Native .12d S8→C3D20 topology disagrees with the retained input')
        found[e]={'original':original,'expanded':expanded,
                  'source_line':text[:match.start()].count('\n')+1}
    if set(found)!=set(elements) or len(re.findall(r'\bELEMENT\s+\d+\s*with label',text,re.I))!=len(found):
        raise ValueError('Missing, duplicate or unsupported native .12d element expansion')
    return found


def _coordinate_error(token):
    # Quantization interval only: E12.5 ASCII after native float32 cast.
    # A printed zero must not gain an arbitrary 1e-5 absolute tolerance.
    v=float(token)
    if not v:
        return 2.0**-150
    dec=.51*10.**Decimal(token).as_tuple().exponent
    max_magnitude=abs(v)+dec
    float_ulp=2.**max(-149,math.floor(math.log2(max_magnitude))-23)
    return dec+.51*float_ulp+32*math.ulp(v)


def read_frd(path, expansion, *, profile='S8'):
    if profile not in ('S8','B32R_RECT'):
        raise ValueError('Unsupported native expanded FRD profile')
    field_labels=dict(LABELS); field_widths=dict(WIDTHS); required=set(REQUIRED)
    if profile=='B32R_RECT':
        field_labels['FORC']=('F1 1 2 1 0','F2 1 2 2 0','F3 1 2 3 0','ALL 1 2 0 0 1ALL')
        field_widths['FORC']=3; required.add('FORC')
    from .fixture_field import _frd_record, _identifier, _number
    lines=ascii_source(path).splitlines()
    versions=[s.strip() for s in lines if s.strip().startswith('1UVERSION')]
    if versions!=['1UVERSION    Version 2.22'] and (len(versions)!=1 or
            not re.fullmatch(r'1UVERSION\s+Version 2\.22',versions[0])):
        raise ValueError('Shell surface reader requires actual CalculiX 2.22 FRD metadata')
    expected_nodes={n for row in expansion.values() for n in row['expanded']}
    xyz,coordinate_tokens,topology,frames={},{},{},[]
    i=0; pending=None; header=None; ended=False; counter=0; diagnostic=None
    active=None
    def fail(message):
        raise ValueError(message)
    try:
        while i<len(lines):
            line=lines[i].rstrip(); parts=line.split(); i+=1
            if not parts: continue
            if ended: fail('Trailing data after FRD end marker')
            if parts[0] in ('2C','3C'):
                if len(parts)!=3 or parts[2]!='1' or frames or pending:
                    fail('Unsupported or repeated native FRD mesh block')
                count=_identifier(parts[1])
                if parts[0]=='2C':
                    if xyz or topology or count!=len(expected_nodes): fail('FRD expanded node count differs')
                    while i<len(lines) and lines[i].strip()!='-3':
                        n,values,tokens=_frd_record(lines[i].rstrip(),3); i+=1
                        if n in xyz or n not in expected_nodes: fail('Foreign/repeated expanded FRD node')
                        xyz[n]=values; coordinate_tokens[n]=tokens
                    if set(xyz)!=expected_nodes: fail('Incomplete expanded FRD coordinates')
                else:
                    if not xyz or topology or count!=len(expansion): fail('FRD expanded element count differs')
                    while i<len(lines) and lines[i].strip()!='-3':
                        row=lines[i].rstrip(); i+=1
                        if (len(row)!=28 or row[:3]!=' -1' or
                                [row[a:b].strip() for a,b in ((13,18),(18,23),(23,28))]!=['4','0','1']):
                            fail('Expected FRD HEX20, material 1 for homogeneous S8')
                        e=_identifier(row[3:13].strip())
                        conn=[]
                        while i<len(lines) and lines[i][:3]==' -2':
                            row=lines[i].rstrip(); i+=1
                            if len(row)<=3 or (len(row)-3)%10 or len(row)>103:
                                fail('Malformed HEX20 continuation record')
                            conn.extend(_identifier(row[j:j+10].strip()) for j in range(3,len(row),10))
                            if len(conn)>20: fail('Excess HEX20 connectivity')
                        if e in topology or e not in expansion or tuple(conn)!=tuple(
                                expansion[e]['expanded'][j] for j in FRD_FROM_C3D20):
                            fail('FRD topology differs from native .12d expansion')
                        topology[e]=tuple(conn)
                    if set(topology)!=set(expansion): fail('Incomplete FRD topology')
                if i==len(lines): fail('Unterminated native FRD geometry')
                i+=1
            elif parts[0]=='1PSTEP':
                row=line.ljust(70)
                if not topology or pending or header or len(line)>70 or row[10:24].strip() or row[60:].strip():
                    fail('Malformed native shell field step')
                count,inc,step=(_identifier(row[a:b].strip()) for a,b in ((24,36),(36,48),(48,60)))
                if count!=counter+1 or step!=1 or active and inc<active['increment']:
                    fail('Unordered or unsupported shell field step')
                pending=(count,inc,step)
            elif parts[0]=='100CL':
                if pending is None or header is not None or len(line)!=75:
                    fail('Malformed native shell field header')
                kode=_identifier(line[58:63].strip())
                coverage=_identifier(line[24:36].strip())
                time_token=line[12:24].strip(); time=_number(time_token)
                if (line[7:12].strip()!=str(100+kode) or coverage!=len(expected_nodes)
                        or line[36:58].strip()!='0' or line[63:74].strip() or line[74]!='1' or time<=0):
                    fail('Wrong static field time/mode/expanded coverage')
                if active and pending[1]==active['increment']:
                    if time!=active['load_parameter'] or kode!=active['kode']:
                        fail('Shell fields disagree on the increment/time')
                else:
                    if active and (kode<=active['kode'] or time<=active['load_parameter']):
                        fail('Unordered native shell increments')
                    active={'step':1,'increment':pending[1], 'kode':kode,
                            'load_parameter':time,'load_parameter_token':time_token,'fields':{},'source_lines':{}}
                    frames.append(active)
                header=True
            elif parts[0]=='-4':
                if not header or len(parts)!=4 or parts[1] not in field_labels:
                    fail('Unexpected native shell field definition')
                name=parts[1]; labels=field_labels[name]; start=i
                if name in active['fields'] or parts[2:]!=[str(len(labels)),'1']:
                    fail('Repeated or changed native shell field meaning')
                for label in labels:
                    if i>=len(lines) or lines[i].split()!=['-5',*label.split()]:
                        fail('Native shell component labels/order differ')
                    i+=1
                values={}
                while i<len(lines) and lines[i].strip()!='-3':
                    n,value,_=_frd_record(lines[i].rstrip(),field_widths[name]); i+=1
                    if n in values or n not in expected_nodes: fail('Repeated/foreign shell field node')
                    values[n]=value
                if i==len(lines) or set(values)!=expected_nodes:
                    fail('Truncated native shell field; uncommitted field discarded')
                i+=1
                active['fields'][name]=values; active['source_lines'][name]=[start,i]
                counter=pending[0]; pending=None; header=None
            elif parts==['9999']:
                if pending or header: fail('Unfinished field before end marker')
                ended=True
            elif xyz or not re.match(r'\s*1[CU]',line):
                fail('Unexpected native shell FRD record')
    except (ValueError,IndexError) as exc:
        if profile=='B32R_RECT' and (i<len(lines) or str(exc) != 'Truncated native shell field; uncommitted field discarded'):
            # The new beam profile must not downgrade middle-file corruption,
            # label/identity errors or malformed numeric rows into partial data.
            raise ValueError(f'Invalid expanded beam FRD at line {i}: {exc}') from exc
        if not xyz or set(topology)!=set(expansion):
            raise ValueError(f'No admitted expanded mesh at FRD line {i}: {exc}') from exc
        diagnostic={'line':i,'reason':str(exc)}
    # A completed field is retained only at its own native step/increment/time.
    # Never borrow an earlier U/S/E to complete a later truncated increment.
    frames=[f for f in frames if f['fields']]
    if not frames: raise ValueError('No complete native shell field was recovered')
    for frame in frames:
        frame['complete']=required<=set(frame['fields'])
    complete=ended and diagnostic is None and all(f['complete'] for f in frames)
    return {'native_version':'2.22','coordinates':xyz,'coordinate_tokens':coordinate_tokens,
            'topology':topology,'frames':frames,'status':'COMPLETE' if complete else 'PARTIAL',
            'diagnostic':diagnostic or (None if ended else {'line':len(lines),'reason':'Missing FRD end marker'})}


def locations(mesh, expansion, observed):
    """Prove the native top/bottom topology and corroborate thickness/offset.

    Actual expansion can use averaged normals or knot-specific nodes. We retain
    those IDs and derive a displayed normal from their actual coordinate pair.
    Coordinate checks use only source print/float32 quantization intervals.
    """
    xyz=observed['coordinates']; tokens=observed['coordinate_tokens']
    rows=[]
    for e, item in sorted(expansion.items()):
        if 'section_values_by_element' in mesh:
            values=mesh['section_values_by_element'][e]
        else:
            values=mesh.get('section_values',mesh['values'])
        thickness=values['thickness_mm']; offset=values['offset']
        expanded=item['expanded']
        for j, original in enumerate(item['original']):
            bn,tn=expanded[BOTTOM[j]],expanded[TOP[j]]
            b,t=xyz[bn],xyz[tn]
            delta=sub(t,b); distance=math.hypot(*delta)
            eb=[_coordinate_error(v) for v in tokens[bn]]
            et=[_coordinate_error(v) for v in tokens[tn]]
            bound=math.hypot(*(a+c for a,c in zip(eb,et)))
            if distance<=bound or abs(distance-thickness)>bound+64*math.ulp(thickness):
                raise ValueError(f'Expanded thickness is wrong or unresolved at element {e}, shell node {original}')
            n=unit(delta)
            if dot(n,mesh['normals'][e])<=0:
                raise ValueError(f'Expanded normal opposes retained shell orientation at element {e}')
            reference=mesh['nodes'][original]
            for c in range(3):
                restored=(.5-offset)*b[c]+(.5+offset)*t[c]
                error=abs(.5-offset)*eb[c]+abs(.5+offset)*et[c]
                error+=64*math.ulp(max(abs(reference[c]),abs(restored)))
                if abs(restored-reference[c])>error:
                    raise ValueError(f'Native offset/reference surface mismatch at element {e}, node {original}')
            for side,node,zeta in (('bottom',bn,-1),('top',tn,1)):
                rows.append({'element_id':e,'shell_node_id':original,'local_node':j+1,
                    'expanded_node_id':node,'side':side,'zeta':zeta,'position_mm':xyz[node],
                    'normal_from_native_expansion':list(n), 'native_12d_line':item['source_line'],
                    'location_kind':'expanded_surface_node',
                    'stress_recovery':'native_extrapolated_nodal_averaged',
                    'strain_recovery':'native_extrapolated_nodal_averaged',
                    'exact_surface_integration_point':False,
                    **({'region':mesh['region_by_element'][e]} if 'region_by_element' in mesh else {})})
    return rows


DAT_HEADER=re.compile(r'^\s*(stresses|strains|global coordinates)\s*\(([^)]*)\)\s*for set\s+(\S+)\s+and time\s+(\S+)\s*$',re.I)
DAT_STEP=re.compile(r'^\s*S\s+T\s+E\s+P\s+([1-9]\d*)\s*$')
DAT_INCREMENT=re.compile(r'^\s*INCREMENT\s+([1-9]\d*)\s*$')
DAT_NAMES={'stresses':('S',('elem','integ.pnt.','sxx','syy','szz','sxy','sxz','syz')),
           'strains':('E',('elem','integ.pnt.','exx','eyy','ezz','exy','exz','eyz')),
           'global coordinates':('COORD',('elem','integ.pnt.','x','y','z'))}


def read_dat(path, elements, *, profile='S8', retain_lines=False):
    if profile not in ('S8','B32R_RECT'):
        raise ValueError('Unsupported native DAT profile')
    from caelab.beam_gauss import B32R_RECT_GAUSS50
    natural = GAUSS27 if profile=='S8' else B32R_RECT_GAUSS50
    set_name='LABSHELL' if profile=='S8' else 'BEAM'
    from .fixture_field import _number, _identifier
    lines=ascii_source(path).splitlines(); tables={}; i=0; diagnostic=None
    expected={(e,p) for e in elements for p in range(1,len(natural)+1)}
    step=None; increment=None; increment_time=None; previous_time=None
    try:
        while i<len(lines):
            line=lines[i]; i+=1
            if not line.strip(): continue
            step_header=DAT_STEP.fullmatch(line)
            if step_header:
                if step is not None or tables or int(step_header[1])!=1:
                    raise ValueError('Only one native shell DAT step is supported')
                step=1
                continue
            increment_header=DAT_INCREMENT.fullmatch(line)
            if increment_header:
                next_increment=int(increment_header[1])
                if step is None or increment is not None and next_increment<=increment:
                    raise ValueError('Unordered native shell DAT increment')
                if increment is not None and (increment_time is None or
                        {kind for time,kind in tables if time==increment_time}!={'S','E','COORD'}):
                    raise ValueError('Incomplete native shell DAT increment')
                previous_time=increment_time
                increment=next_increment; increment_time=None
                continue
            header=DAT_HEADER.fullmatch(line)
            if header is None: raise ValueError('Unexpected DAT content outside a retained shell S/E/COORD table')
            kind,labels=DAT_NAMES[header[1].lower()]
            if tuple(p.strip().lower() for p in header[2].split(','))!=labels or header[3].upper()!=set_name:
                raise ValueError('DAT integration-point labels/set differ')
            time=_number(header[4]); key=(time,kind)
            if time<=0 or key in tables: raise ValueError('Repeated/invalid native DAT time/table')
            if step is not None:
                if increment is None or previous_time is not None and time<=previous_time:
                    raise ValueError('Missing increment or unordered native DAT time')
                if increment_time is not None and time!=increment_time:
                    raise ValueError('Native DAT tables disagree on increment time')
                increment_time=time
            values={}; source_line=i
            while i<len(lines) and not lines[i].strip(): i+=1
            while i<len(lines) and lines[i].strip() and DAT_HEADER.fullmatch(lines[i]) is None:
                parts=lines[i].split(); i+=1
                width=3 if kind=='COORD' else 6
                if len(parts)!=width+2: raise ValueError('Truncated/malformed native integration-point row')
                e,p=map(_identifier,parts[:2]); point=(e,p)
                if point not in expected or point in values: raise ValueError('Duplicate/foreign native integration point')
                raw=[_number(v) for v in parts[2:]]
                # DAT tensor: xx yy zz xy xz yz → explicit common xx yy zz xy yz zx.
                ordered=raw if width==3 else [raw[j] for j in (0,1,2,3,5,4)]
                values[point]={'values':ordered,'tokens':parts[2:],'raw_component_order':labels[2:]}
                if profile=='B32R_RECT' or retain_lines:
                    values[point].update(source_line=i,table_header_line=source_line,time_token=header[4])
            if set(values)!=expected: raise ValueError(f'Native DAT table does not contain exactly {len(natural)} points per element')
            tables[key]={'values':values,'source_line':source_line,'time_token':header[4]}
        if step is not None and (increment is None or increment_time is None):
            raise ValueError('Native DAT control header has no result table')
    except (ValueError,IndexError) as exc:
        if profile=='B32R_RECT' and (i<len(lines) or not str(exc).startswith('Native DAT table does not contain exactly')):
            raise ValueError(f'Invalid beam DAT at line {i}: {exc}') from exc
        diagnostic={'line':i,'reason':str(exc)}
    rows=[]
    for time in sorted({k[0] for k in tables}):
        available={kind for t,kind in tables if t==time}
        for e,p in sorted(expected):
            row={'element_id':e,'integration_point':p,'natural_coordinates':list(natural[p-1]),
                 'load_parameter':time,'location_kind':'internal_integration_point',
                 'surface':False,'available':sorted(available)}
            for kind in available:
                row[kind]=tables[(time,kind)]['values'][(e,p)]
            rows.append(row)
    complete=bool(tables) and diagnostic is None and all({k for t,k in tables if t==time}=={'S','E','COORD'}
                                                     for time in {k[0] for k in tables})
    return {'status':'COMPLETE' if complete else 'PARTIAL','rows':rows,'diagnostic':diagnostic}


def rotate_tensor(v, axes):
    # Exact basis change at the same observed node, not recovery/interpolation.
    xx,yy,zz,xy,yz,zx=v
    matrix=((xx,xy,zx),(xy,yy,yz),(zx,yz,zz))
    transformed=[[sum(axes[i][k]*matrix[k][l]*axes[j][l] for k in range(3) for l in range(3))
                  for j in range(3)] for i in range(3)]
    return [transformed[i][j] for i,j in ((0,0),(1,1),(2,2),(0,1),(1,2),(2,0))]
