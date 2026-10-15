"""Read CalculiX 2.22 B32R OUTPUT=2D / SECTION FORCES without stress aliases.

Existing fixed-column numeric/label readers are reused. This beam profile owns
only its native topology, mixed-unit section channels and strict EOF admission.
It never infers expanded node numbers, averages rotations or computes von Mises.
"""
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from .adapters.fixture_field import (_read_bytes, _frd_record, _identifier,
                                    _number, _printed_close, _LABELS)
from .beam_model import validate_model, dot, sub
from .storage import save_json

LABELS = {k: _LABELS[k] for k in ('DISP', 'STRESS')}
LABELS['FORC'] = ('F1 1 2 1 0', 'F2 1 2 2 0', 'F3 1 2 3 0', 'ALL 1 2 0 0 1ALL')
WIDTHS = {'DISP': 3, 'STRESS': 6, 'FORC': 3}
# CalculiX's S request also writes this auxiliary stress variation indicator.
# It is not a section-force error, a stress value or a solver failure verdict.
OPTIONAL_LABELS = {'ERROR': ('STR(%) 1 1 0 0',)}
FIELD_LABELS = {**LABELS, **OPTIONAL_LABELS}
FIELD_WIDTHS = {**WIDTHS, 'ERROR': 1}
# Order is native FRD SXX,SYY,SZZ,SXY,SYZ,SZX, not an assumed tensor order.
CHANNELS = {
    'UX': ('DISP', 0, 'mm', 'GLOBAL', 'X 변위', 'displacement'),
    'UY': ('DISP', 1, 'mm', 'GLOBAL', 'Y 변위', 'displacement'),
    'UZ': ('DISP', 2, 'mm', 'GLOBAL', 'Z 변위', 'displacement'),
    'RF_X_raw': ('FORC', 0, 'N', 'GLOBAL', 'X 절점 RF (원출력)', 'native_nodal_force'),
    'RF_Y_raw': ('FORC', 1, 'N', 'GLOBAL', 'Y 절점 RF (원출력)', 'native_nodal_force'),
    'RF_Z_raw': ('FORC', 2, 'N', 'GLOBAL', 'Z 절점 RF (원출력)', 'native_nodal_force'),
    'V1': ('STRESS', 0, 'N', 'SECTION_LOCAL', '1축 전단력', 'section_force'),
    'V2': ('STRESS', 1, 'N', 'SECTION_LOCAL', '2축 전단력', 'section_force'),
    'N': ('STRESS', 2, 'N', 'SECTION_LOCAL', '축력', 'section_force'),
    'Mt': ('STRESS', 3, 'Nmm', 'SECTION_LOCAL', '비틀림 모멘트', 'section_moment'),
    'M1': ('STRESS', 4, 'Nmm', 'SECTION_LOCAL', '1축 굽힘 모멘트', 'section_moment'),
    'M2': ('STRESS', 5, 'Nmm', 'SECTION_LOCAL', '2축 굽힘 모멘트', 'section_moment'),
}
UNAVAILABLE = {
    'rotation_rad': 'This OUTPUT=2D profile has no native rotational result channel. No slope or averaged displacement is labelled rotation.',
    'support_reaction_moment_Nmm': 'Section moments are not separately integrated support reaction moments.',
    'support_reaction_force_total_N': 'FORC at original beam nodes is retained as native averaged nodal RF, not summed into a support resultant.',
    'expanded_3D_stress_MPa': 'OUTPUT=3D is mutually exclusive with SECTION FORCES; no stress tensor is requested in this run.',
}


class _EndOfFile(Exception):
    pass


def sha(path):
    """Hash preserved artifacts without loading a large raw result into memory."""
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('Beam artifact must be a regular local file')
    before = path.stat()
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise ValueError('Beam artifact changed while reading')
    return value


def read_frd(path, model, *, allow_partial=False, data=None):
    """Return complete native frames, or reject. Partial never means valid solve.

    allow_partial admits a clean EOF or a syntactically plausible torn FINAL
    record only. Corruption followed by more content, wrong labels, duplicate
    nodes and foreign topology always reject the entire reading copy.
    """
    from .beam_output import mode
    if mode(model)=='raw_stress':
        if data is not None:
            raise ValueError('3D beam observations require the full pinned FRD/12d/DAT source set')
        from .beam_raw_results import read
        return read(path,model,allow_partial=allow_partial)
    nodes, elements, _ = validate_model(model)
    raw = _read_bytes(Path(path)) if data is None else data
    if not isinstance(raw, bytes) or len(raw) > 64 * 1024**2:
        raise ValueError('Beam FRD exceeds the 64 MiB reading limit')
    text = raw.decode('ascii').replace('\r\n', '\n')
    if '\r' in text or '\x00' in text:
        raise ValueError('Malformed ASCII FRD encoding')
    lines = text.splitlines()
    versions = [line.strip() for line in lines if line.strip().startswith('1UVERSION')]
    if len(versions) != 1 or not re.fullmatch(r'1UVERSION\s+Version 2\.22', versions[0]):
        raise ValueError('Beam results require explicit CalculiX 2.22 version metadata')
    xyz, topology, fields, frames = {}, {}, {}, []
    counter, current, pending, header, ended = 0, None, None, None, False
    frame_key, parameter_token, kode, truncation = None, None, None, None
    i = 0

    def final_fragment(index):
        return index == len(lines)-1 and not text.endswith('\n')

    def need():
        nonlocal i
        if i >= len(lines):
            raise _EndOfFile('EOF before a complete native record')
        value = lines[i].rstrip(); i += 1
        return value

    def retain():
        nonlocal fields
        if not set(LABELS) <= set(fields) <= set(FIELD_LABELS):
            raise ValueError('A complete beam frame needs DISP, FORC and SECTION FORCES')
        frames.append({'static': {'step': frame_key[0], 'increment': frame_key[1],
                                 'load_parameter': current},
                       'load_parameter_token': parameter_token, 'native_fields': fields})
        fields = {}

    def short_numeric(row, width, records):
        if row in (' -', ' -1'):
            return True
        if row[:3] != ' -1' or len(row) >= 13+12*width:
            return False
        if not re.fullmatch(r' *[0-9]*', row[3:13]):
            return False
        if len(row) < 13:
            return True
        n = _identifier(row[3:13].strip())
        if n not in nodes or n in records:
            raise ValueError('Foreign or duplicate node in torn beam record')
        for start in range(13, len(row), 12):
            token = row[start:start+12].strip()
            if start+12 <= len(row):
                _number(token)
            elif token and not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d*)(?:[EeDd][+-]?\d*)?|[+-]', token):
                return False
        return True

    try:
        while i < len(lines):
            line = need(); parts = line.split()
            if not parts:
                continue
            if ended:
                raise ValueError('Content after the native FRD end marker')
            marker = parts[0]
            if marker in ('2C', '3C'):
                if len(parts) != 3 or parts[2] != '1' or pending or fields or frames:
                    raise ValueError('Only a single native ASCII beam mesh is supported')
                count = _identifier(parts[1])
                if marker == '2C':
                    if xyz or topology or count != len(nodes):
                        raise ValueError('Duplicate/incomplete original beam geometry')
                    while True:
                        row = need()
                        if row.strip() == '-3': break
                        n, values, tokens = _frd_record(row, 3)
                        if n not in nodes or n in xyz or any(not _printed_close(t, v) for t, v in zip(tokens, nodes[n])):
                            raise ValueError('FRD original node/coordinate differs from frozen input')
                        xyz[n] = values
                    if set(xyz) != set(nodes):
                        raise ValueError('Missing original beam node')
                else:
                    if not xyz or topology or count != len(elements):
                        raise ValueError('Duplicate/incomplete original beam topology')
                    while True:
                        row = need()
                        if row.strip() == '-3': break
                        if (len(row) != 28 or row[:3] != ' -1' or
                                [row[a:b].strip() for a,b in ((13,18),(18,23),(23,28))] != ['12','0','1']):
                            raise ValueError('Expected original 3-node beam FRD type12/material1, not expanded 3D')
                        e = _identifier(row[3:13].strip())
                        if e not in elements or e in topology:
                            raise ValueError('Foreign or duplicate original beam element')
                        row = need()
                        if row[:3] != ' -2' or len(row) != 33:
                            raise ValueError('Malformed 3-node beam connectivity')
                        ids = [_identifier(row[3+10*j:13+10*j].strip()) for j in range(3)]
                        # CGX 2.22 p138: endpoints first, midpoint third.
                        ccx = elements[e]
                        if ids != [ccx[0], ccx[2], ccx[1]]:
                            raise ValueError('FRD ordered beam topology differs from frozen original nodes')
                        topology[e] = ids
                    if set(topology) != set(elements):
                        raise ValueError('Missing beam elements in FRD')
            elif marker == '1PSTEP':
                if final_fragment(i-1) and len(line) < 60 and re.fullmatch(r'\s*1PSTEP[ 0-9]*', line):
                    raise _EndOfFile('Torn final step header')
                row = line.ljust(70)
                if not topology or pending is not None or header is not None or len(line)>70 or row[10:24].strip() or row[60:].strip():
                    raise ValueError('Malformed native beam step header')
                count, inc, step = [_identifier(row[a:b].strip()) for a,b in ((24,36),(36,48),(48,60))]
                if count != counter+1 or step != 1 or (frame_key is not None and (step,inc) < frame_key):
                    raise ValueError('Unordered native beam output')
                pending = (count, inc, step)
                if frame_key is not None and (step,inc) != frame_key:
                    retain()
            elif marker == '100CL':
                if pending and header is None and final_fragment(i-1) and len(line)<75 and re.fullmatch(r'\s*100CL[ 0-9EeDd+.\-]*',line):
                    raise _EndOfFile('Torn final field header')
                if pending is None or header is not None or len(line)!=75:
                    raise ValueError('Malformed native static field header')
                output_inc = _identifier(line[58:63].strip())
                if (line[7:12].strip()!=str(100+output_inc) or _identifier(line[24:36].strip())!=len(nodes)
                        or line[36:58].strip()!='0' or line[63:74].strip() or line[74]!='1'):
                    raise ValueError('Native beam output mode/coverage differs')
                token = line[12:24].strip(); value = _number(token)
                new_key = (pending[2],pending[1])
                if value <= 0:
                    raise ValueError('Invalid static load parameter')
                if new_key == frame_key:
                    if current!=value or output_inc!=kode:
                        raise ValueError('Different native load parameters within one beam frame')
                elif frame_key is not None and (value<=current or output_inc<=kode):
                    raise ValueError('Unordered beam load parameters')
                frame_key, current, parameter_token, kode = new_key, value, token, output_inc
                header = True
            elif marker == '-4':
                candidates = [f'-4 {name} {len(labels)} 1' for name,labels in FIELD_LABELS.items() if name not in fields]
                fragment = ' '.join(parts)
                if header and final_fragment(i-1) and any(c!=fragment and c.startswith(fragment) for c in candidates):
                    raise _EndOfFile('Torn final field declaration')
                if header is None or len(parts)!=4 or parts[1] not in FIELD_LABELS or parts[1] in fields:
                    raise ValueError('Unexpected or duplicate beam field')
                name = parts[1]
                if parts[2:]!=[str(len(FIELD_LABELS[name])),'1']:
                    raise ValueError('Native beam field declaration differs')
                for label in FIELD_LABELS[name]:
                    row = need()
                    if row.split()!=['-5',*label.split()]:
                        if final_fragment(i-1) and ('-5 '+label).startswith(' '.join(row.split())):
                            raise _EndOfFile('Torn final component label')
                        raise ValueError('Native component meaning/order differs')
                records = {}
                while True:
                    row = need()
                    if row.strip()=='-3': break
                    if final_fragment(i-1) and short_numeric(row,FIELD_WIDTHS[name],records):
                        if len(records)>=len(nodes):
                            raise ValueError('Beam records exceed the declared coverage')
                        raise _EndOfFile('Torn final field record')
                    n, values, _ = _frd_record(row,FIELD_WIDTHS[name])
                    if n not in nodes or n in records:
                        raise ValueError('Foreign or duplicate beam field node')
                    records[n] = values
                if set(records)!=set(nodes):
                    raise ValueError('Incomplete beam field before its terminator')
                fields[name] = records
                counter = pending[0]; pending = header = None
            elif parts == ['9999']:
                if pending is not None or header is not None or not frame_key:
                    raise ValueError('Incomplete beam output at the end marker')
                retain(); ended = True
            elif final_fragment(i-1) and line.strip() in ('9','99','999'):
                if pending is not None or header is not None:
                    raise ValueError('End marker inside a beam field')
                raise _EndOfFile('Torn final file terminator')
            elif not xyz and re.match(r'\s*1[CU]',line):
                # FreeCAD source, mesh identity and exact solver version remain
                # checked independently; this is printable FRD metadata only.
                continue
            elif final_fragment(i-1) and topology and any(m.startswith(line.strip()) for m in ('1PSTEP','100CL','-4','9999')):
                raise _EndOfFile('Torn final record marker')
            else:
                raise ValueError('Unexpected native beam FRD content')
        if not ended:
            raise _EndOfFile('Native file has no final terminator')
    except _EndOfFile as exc:
        if not allow_partial:
            raise ValueError(str(exc)) from exc
        truncation = str(exc)
        # A terminated complete frame is retained even when the final 9999 or
        # the NEXT header is torn. An unfinished frame is never padded or merged.
        # A torn optional field cannot invalidate the already terminated required
        # fields, but the retained frame stays partial with its exact EOF reason.
        if set(LABELS) <= set(fields) <= set(FIELD_LABELS):
            retain()
    if not frames:
        raise ValueError('No complete native beam frame is available; raw files remain retained')
    return {'native_version':'2.22','frames':frames,'coordinates_mm':xyz,'frd_elements':topology,
            'complete_file':ended,'truncation':truncation,'unavailable':deepcopy(UNAVAILABLE)}


def channels(frame):
    """One component, frame, source field and unit per channel; never mixed tensors."""
    if frame.get('output_mode')=='raw_stress':
        raise ValueError('Raw Cauchy stress cannot be read through SECTION FORCES channels; use inspect_raw')
    result = {}
    for key,(source,index,unit,coordinate,title,measure) in CHANNELS.items():
        result[key] = {'unit':unit,'frame':coordinate,'label':title,'measure':measure,
            'source_field':source,'source_component':LABELS[source][index].split()[0],
            'values':{int(n):v[index] for n,v in frame['native_fields'][source].items()}}
    return result


def post_metadata(observed, model, *, source_status):
    """Exact field declaration for the PVD load-parameter collection, never seconds."""
    from .beam_output import mode
    if mode(model)=='raw_stress':
        from .beam_raw_results import post_metadata as raw_metadata
        return raw_metadata(observed,model,source_status=source_status)
    validate_model(model)
    frames = observed['frames']
    if not frames or len(frames) > 1024:
        raise ValueError('Beam Post requires 1..1024 complete native frames')
    import math
    times = [f['static']['load_parameter'] for f in frames]
    if (any(type(t) not in (int, float) or not math.isfinite(t) or t <= 0 for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))):
        raise ValueError('Beam collection requires strictly increasing native load parameters')
    if source_status not in {'SUCCEEDED', 'FAILED', 'CANCELLED', 'PARTIAL_FAILURE'}:
        raise ValueError('Beam Post must retain the explicit execution status')
    location = 'ORIGINAL_BEAM_NODES'
    arrays = [
        {'name':'NativeNodeId','association':'POINTS','components':1,'units':'1',
         'frame':'not_applicable','measure':'identity','quantity':'원 빔 절점 번호','location':location},
        {'name':'Station_mm','association':'POINTS','components':1,'units':'mm',
         'frame':'BEAM_SECTION_LOCAL','measure':'position','quantity':'빔 길이 좌표','location':location},
        {'name':'NativeElementId','association':'CELLS','components':1,'units':'1',
         'frame':'not_applicable','measure':'identity','quantity':'원 빔 요소 번호','location':'ORIGINAL_BEAM_ELEMENTS'},
        {'name':'U_mm','association':'POINTS','components':3,'component_names':['UX','UY','UZ'],
         'units':'mm','frame':'FREECAD_DOCUMENT_GLOBAL','measure':'displacement','quantity':'전역 변위',
         'location':location,'recovery':'native_nodal_dof'}]
    for name, entry in CHANNELS.items():
        source, _, unit_name, coord, label, measure = entry
        arrays.append({'name':name,'association':'POINTS','components':1,'units':unit_name,
            'frame':'FREECAD_DOCUMENT_GLOBAL' if coord == 'GLOBAL' else 'BEAM_SECTION_LOCAL',
            'measure':measure,'quantity':label,'location':location,
            'recovery':{'DISP':'native_nodal_dof', 'FORC':'native_original_beam_nodal_rf',
                        'STRESS':'native_section_force_output'}[source]})
    return {'coordinate_units':'mm','coordinate_frame':'FREECAD_DOCUMENT_GLOBAL',
        'static':None,'time':{'unit':'1','semantics':'STATIC_LOAD_PARAMETER','values':times},'arrays':arrays,
        'beam':{'element':'B32R','output':'2D_SECTION_FORCES','location':location,
                'axes':deepcopy(model['axes']),'units':deepcopy(model['units']),
                'unavailable':deepcopy(UNAVAILABLE),'source_execution_status':source_status,
                'complete_file':observed['complete_file'],'truncation':observed['truncation'],
                'observation_status':'COMPLETE' if observed['complete_file'] and source_status=='SUCCEEDED' else 'PARTIAL',
                'frames':[deepcopy(f['static']) for f in frames], 'engineering_valid':False}}


def post_files(observed, model, *, source_status):
    """Yield deterministic view/CSV bytes, also used for read-only semantic validation.

    No disk writes or solver imports on reopening. Each numeric array is rebuilt
    from native FRD component values and exact input node/element associations.
    """
    from .beam_output import mode
    if mode(model)=='raw_stress':
        from .beam_raw_results import post_files as raw_files
        yield from raw_files(observed,model,source_status=source_status)
        return
    import io
    post_metadata(observed, model, source_status=source_status)
    nodes, _, stations = validate_model(model)
    order = sorted(nodes); index = {n:i for i,n in enumerate(order)}
    collection = ET.Element('VTKFile',type='Collection',version='0.1',byte_order='LittleEndian')
    datasets = ET.SubElement(collection,'Collection')
    topology = {int(e):ids for e,ids in observed['frd_elements'].items()}
    element_order = sorted(topology)
    for fi,frame in enumerate(observed['frames']):
        native = {key:{int(n):v for n,v in rows.items()} for key,rows in frame['native_fields'].items()}
        frame = {**frame,'native_fields':native}
        component_data = channels(frame)
        xml = ET.Element('VTKFile',type='UnstructuredGrid',version='0.1',byte_order='LittleEndian')
        grid = ET.SubElement(xml,'UnstructuredGrid')
        piece = ET.SubElement(grid,'Piece',NumberOfPoints=str(len(order)),NumberOfCells=str(len(element_order)))
        def array(parent,name,data,components=1,kind='Float64',component_names=None):
            item = ET.SubElement(parent,'DataArray',type=kind,Name=name,NumberOfComponents=str(components),format='ascii')
            if component_names is not None:
                for i, label in enumerate(component_names): item.set('ComponentName'+str(i), label)
            flat = [v for row in data for v in row] if components>1 else data
            item.text = ' '.join(str(v) if kind.startswith('Int') or kind=='UInt8' else format(v,'.17g') for v in flat)
        point = ET.SubElement(piece,'PointData',Vectors='U_mm')
        array(point,'NativeNodeId',order,kind='Int64'); array(point,'Station_mm',[stations[n] for n in order])
        array(point,'U_mm',[native['DISP'][n] for n in order],3,component_names=['UX','UY','UZ'])
        for name,ch in component_data.items(): array(point,name,[ch['values'][n] for n in order])
        cell = ET.SubElement(piece,'CellData'); array(cell,'NativeElementId',element_order,kind='Int64')
        points = ET.SubElement(piece,'Points'); array(points,'Points',[nodes[n] for n in order],3)
        cells = ET.SubElement(piece,'Cells')
        array(cells,'connectivity',[index[n] for e in element_order for n in topology[e]],kind='Int64')
        array(cells,'offsets',[3*(j+1) for j in range(len(element_order))],kind='Int64')
        array(cells,'types',[21]*len(element_order),kind='UInt8')
        filename = f'beam_{fi:04d}.vtu'
        yield filename, ET.tostring(xml,encoding='utf-8',xml_declaration=True)
        ET.SubElement(datasets,'DataSet',timestep=format(frame['static']['load_parameter'],'.17g'),group='',part='0',file=filename)
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(['native_node_id','station_mm',*[f'{k} [{v[2]}]' for k,v in CHANNELS.items()]])
        for n in sorted(order,key=lambda n:stations[n]):
            writer.writerow([n,stations[n],*[component_data[key]['values'][n] for key in CHANNELS]])
        yield f'beam_{fi:04d}.csv', stream.getvalue().encode('utf-8-sig')
    yield 'beam.pvd', ET.tostring(collection,encoding='utf-8',xml_declaration=True)


def write_post(folder, observed, model, *, source_status):
    """Write a view; the owned adapter seals its raw companion before registration.

    A standalone view without beam_inspection is intentionally not admissible
    with beam engineering declarations. Never silently remove those declarations.
    """
    folder = Path(folder)
    metadata = post_metadata(observed, model, source_status=source_status)
    folder.mkdir(parents=True, exist_ok=False)
    for name, payload in post_files(observed, model, source_status=source_status):
        (folder/name).write_bytes(payload)
    save_json(folder/'beam_fields.json',{'kind':'beam-native-fields','schema_version':'1','model':model,
        'observed':observed,'source_execution_status':source_status,'native_metadata':metadata})
    return {'relative':'post/beam.pvd','bytes':(folder/'beam.pvd').stat().st_size,
            'sha256':sha(folder/'beam.pvd'),'native_metadata':metadata}


def final_responses(observed, model):
    from .beam_output import mode
    if mode(model)=='raw_stress':
        from .beam_raw_results import final_responses as raw_responses
        return raw_responses(observed,model)
    nodes,_,_ = validate_model(model); order=sorted(nodes)
    frame=observed['frames'][-1]
    return {name:{'kind':'field','unit':ch['unit'],'value':[ch['values'][n] for n in order],
                 'component':name,'location':'original_beam_nodes','reduction':'none',
                 'metadata':{'node_ids':order,'coordinate_frame':ch['frame'],'axes':model['axes'],
                             'static':frame['static'],'source_field':ch['source_field'],
                             'source_component':ch['source_component'],'engineering_valid':False,
                             'coverage':'ALL_ORIGINAL_BEAM_NODES','interpolated':False}}
            for name,ch in channels(frame).items()}
