"""Controlled S8 deck assembly and admission, separate from every solid reader.

FreeCAD supplies the mesh, section and pressure fragments. We verify their
semantics before selecting/orienting elements. The final text is deterministic;
reopen admission regenerates that same text and compares it byte for byte.
"""
import hashlib
import json
import math
from pathlib import Path
import re

from caelab.shell_model import prepare_mesh, check_supports, number, digest, issue, ShellError

KIND = 'freecad-shell-frozen'
MESH_KIND = 'freecad-shell-mesh'
MAX_BYTES = 256 * 1024 * 1024
MEMBERS = {'editable.FCStd', 'mesh.json', 'native_mesh.inp', 'shell.inp'}


def token(value):
    # Reuse the existing CalculiX 20-character numeric serializer.
    from .native_structural_deck import native_number
    return native_number(value)


def sections(text):
    result = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('**'):
            continue
        if line.startswith('*'):
            parts = [p.strip().upper() for p in line.split(',')]
            opts = {}
            for p in parts[1:]:
                k, sep, v = p.partition('=')
                if not sep or not k or not v or k in opts:
                    raise ValueError('Unsupported or repeated shell keyword option: ' + p)
                opts[k] = v
            result.append((parts[0], opts, []))
        elif not result:
            raise ValueError('Shell data precedes a keyword')
        else:
            result[-1][2].append(line)
    return result


def native_mesh(text):
    nodes, elements = {}, {}
    for key, options, rows in sections(text):
        if key == '*NODE':
            if set(options) - {'NSET'}:
                raise ValueError('Unexpected native NODE option')
            for row in rows:
                fields = [p.strip() for p in row.split(',')]
                if len(fields) != 4 or not fields[0].isdigit():
                    raise ValueError('Malformed native shell node')
                n = int(fields[0])
                if n <= 0 or n in nodes:
                    raise ValueError('Repeated/nonpositive native shell node')
                nodes[n] = [number(p) for p in fields[1:]]
        elif key == '*ELEMENT':
            if options.get('TYPE') != 'S8' or set(options) - {'TYPE','ELSET'}:
                raise ValueError('첫 셸 실행은 S8만 지원합니다. 막/S8R/삼각형/체적 요소를 혼합하지 마세요.')
            for row in rows:
                fields = [p.strip() for p in row.split(',')]
                if len(fields) != 9 or any(not p.isdigit() or int(p) <= 0 for p in fields):
                    raise ValueError('Malformed native S8 connectivity')
                e, *conn = map(int, fields)
                if e in elements or len(set(conn)) != 8:
                    raise ValueError('Repeated native element/node')
                elements[e] = conn
        elif key in ('*NSET', '*ELSET'):
            # writeABAQUS(group_param=False) still writes Eall/Nall summaries.
            if set(options) != {key[1:]}:
                raise ValueError('Unexpected native mesh set options')
            # Sets are not used as a shortcut for participation or support.
            if any(not re.fullmatch(r'[A-Za-z0-9_,\s]+', row) for row in rows):
                raise ValueError('Malformed inert native mesh set')
        else:
            raise ValueError('Unexpected card in the native mesh-only export: ' + key)
    if not nodes or not elements or any(n not in nodes for c in elements.values() for n in c):
        raise ValueError('Incomplete native S8 mesh')
    return nodes, elements


def _section_fragments(text, mesh, material):
    found = {}
    for key, options, rows in sections(text):
        if key != '*SHELL SECTION' or set(options) != {'ELSET','MATERIAL','OFFSET'} or len(rows) != 1:
            raise ValueError('Native thickness writer did not emit homogeneous SHELL SECTIONs')
        name = options['ELSET']
        if name in found or options['MATERIAL'] != material.upper():
            raise ValueError('Native shell section identity mismatch')
        values = mesh['values']
        # FreeCAD's source formats Thickness and Offset with .13G.
        if (number(rows[0]) != float(format(values['thickness_mm'], '.13G')) or
                number(options['OFFSET']) != float(format(values['offset'], '.13G'))):
            raise ValueError('Native Thickness/Offset differs from the applied shell draft')
        if len(rows[0].strip()) > 20 or len(options['OFFSET']) > 20:
            raise ValueError('Native shell property exceeds CalculiX numeric field length')
        found[name] = (options['OFFSET'], rows[0])
    if set(found) != {'ES'+str(e) for e in mesh['elements']}:
        raise ValueError('Native shell sections do not cover the exact participating elements')
    return found


def _pressure_fragment(text, mesh):
    entries = sections(text)
    if len(entries) != 1 or entries[0][:2] != ('*DLOAD', {}):
        raise ValueError('Native pressure writer must emit one non-amplitude DLOAD')
    found = {}
    for line in entries[0][2]:
        parts = [p.strip() for p in line.split(',')]
        if len(parts) != 3 or not parts[0].isdigit() or parts[1].upper() != 'P':
            raise ValueError('Expected native whole-shell P pressure, not a solid-face Pn load')
        e = int(parts[0])
        if e in found:
            raise ValueError('Repeated native shell pressure')
        found[e] = number(parts[2])
    expected = -mesh['values']['pressure_MPa']
    # Native Pressure.getValueAs('MPa') yields the applied float; no mesh-area
    # distribution or force conversion is performed by this adapter.
    if set(found) != set(mesh['elements']) or any(abs(v-expected) > 8*math.ulp(expected) for v in found.values()):
        raise ValueError('Native pressure target/sign differs from the applied shell draft')
    return found


def _material_fragment(text, mesh, material):
    entries = sections(text)
    allowed = {'*PHYSICAL CONSTANTS','*MATERIAL','*ELASTIC','*EXPANSION'}
    if any(k not in allowed for k, _, _ in entries):
        raise ValueError('Native material writer emitted a non-isotropic/static card')
    by = {}
    for k, opts, rows in entries:
        if k in by:
            raise ValueError('Repeated native material card')
        by[k] = (opts, rows)
    if by.get('*MATERIAL') != ({'NAME':material.upper()}, []):
        raise ValueError('Native material identity differs from selected material')
    opts, rows = by.get('*ELASTIC', (None, []))
    if opts != {} or len(rows) != 1:
        raise ValueError('One native isotropic ELASTIC row is required')
    fields = [p.strip() for p in rows[0].split(',')]
    if len(fields)!=2 or any(len(p)>20 for p in fields):
        raise ValueError('Invalid native ELASTIC row')
    expected = [mesh['values']['young_MPa'],mesh['values']['poisson']]
    if any(number(p)!=float(format(v,'.13G')) for p,v in zip(fields,expected)):
        raise ValueError('Native Young modulus/Poisson ratio differs from applied draft')
    # Thermal cards are retained in mesh.json but not included in this explicitly
    # non-thermal step. Unsupported thermal/load objects are blocked by the editor.
    return rows[0]


def build(model):
    if model.get('kind') != MESH_KIND or model.get('schema_version') != '1':
        raise ValueError('Unsupported shell mesh contract')
    if model.get('units') != {'position':'mm','stress':'MPa','force':'N'}:
        raise ValueError('Shell units must be mm, MPa and N')
    if model.get('applied',{}).get('draft') != model.get('draft'):
        raise ValueError('The saved applied shell draft differs from the calculation definition')
    source_nodes = {int(n): xyz for n, xyz in model['source_nodes'].items()}
    if len(source_nodes)!=len(model['source_nodes']) or any(n<=0 for n in source_nodes):
        raise ValueError('Repeated or invalid native source node identity')
    source_elements = {int(e): row for e, row in model['source_elements'].items()}
    if len(source_elements)!=len(model['source_elements']) or any(e<=0 for e in source_elements):
        raise ValueError('Repeated or invalid native source element identity')
    mesh = prepare_mesh(source_nodes, source_elements, model['draft'])
    fixed = check_supports(mesh, model['fixed_nodes'])
    material = model['material_name']
    if not isinstance(material, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}', material):
        raise ValueError('Invalid native material name')
    elastic = _material_fragment(model['native_material'], mesh, material)
    native_sections = _section_fragments(model['native_sections'], mesh, material)
    pressures = _pressure_fragment(model['native_pressure'], mesh)
    offset_token, thickness_token = next(iter(native_sections.values()))
    mesh['section_values'] = {'thickness_mm':number(thickness_token),'offset':number(offset_token)}
    # Bind result geometry to the values actually serialized, not extra draft digits.
    mesh['nodes'] = {n:[float(token(v)) for v in xyz] for n,xyz in mesh['nodes'].items()}
    # The selected subset and the explicit reversal are the only mesh edits.
    lines = ['*HEADING', 'CAE Lab user S8 shell; native FreeCAD section/pressure; global mm N MPa',
             '*NODE']
    for n, xyz in mesh['nodes'].items():
        lines.append(str(n)+', '+', '.join(token(v) for v in xyz))
    lines.append('*ELEMENT, TYPE=S8, ELSET=LABSHELL')
    for e, conn in mesh['elements'].items():
        lines.append(str(e)+', '+', '.join(map(str,conn)))
    lines += ['*NSET, NSET=LABFIX']
    lines += [', '.join(map(str, fixed[i:i+12])) for i in range(0, len(fixed), 12)]
    lines += ['*MATERIAL, NAME='+material, '*ELASTIC',
              elastic]
    for e in mesh['elements']:
        # Native rectangular orientation fixes the material/output reference;
        # isotropic stiffness is unchanged. FRD and DAT are requested globally.
        x, y, _ = mesh['axes'][e]
        lines += [f'*ELSET, ELSET=ES{e}', str(e),
                  f'*ORIENTATION, NAME=O{e}, SYSTEM=RECTANGULAR',
                  ', '.join(token(v) for v in (*x, *y))]
        offset, thickness = native_sections['ES'+str(e)]
        lines += [f'*SHELL SECTION, ELSET=ES{e}, MATERIAL={material}, OFFSET={offset}, ORIENTATION=O{e}',
                  thickness]
    lines += ['*STEP', '*STATIC', '1., 1.', '*BOUNDARY', 'LABFIX, 1, 6', '*DLOAD']
    lines += [f'{e}, P, {token(pressures[e])}' for e in mesh['elements']]
    # No NSET filter: expanded nodes are not members of the original Nall.
    lines += ['*NODE FILE, OUTPUT=3D, GLOBAL=YES', 'U', '*EL FILE, GLOBAL=YES', 'S, E',
              '*EL PRINT, ELSET=LABSHELL, GLOBAL=YES', 'S, E, COORD', '*END STEP']
    return '\n'.join(lines)+'\n', mesh


def read_bytes(path, limit=MAX_BYTES):
    path = Path(path)
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Shell artifact must be a regular, non-linked local file')
    with path.open('rb') as stream:
        data = stream.read(limit+1)
    if len(data) > limit:
        raise ValueError('Shell artifact exceeds its size limit')
    return data


def sha(path):
    return hashlib.sha256(read_bytes(path)).hexdigest()


def json_read(path, limit=16*1024*1024):
    def pairs(rows):
        result = {}
        for k, v in rows:
            if k in result:
                raise ValueError('Repeated shell JSON field: '+k)
            result[k] = v
        return result
    def constant(value):
        raise ValueError('Nonfinite shell JSON value: '+value)
    return json.loads(read_bytes(path,limit), object_pairs_hook=pairs, parse_constant=constant)


def validate_snapshot(path):
    path = Path(path)
    if not path.is_absolute() or path.name != 'snapshot.json':
        raise ValueError('Select the absolute retained shell snapshot.json')
    manifest = json_read(path)
    if (manifest.get('kind') != KIND or manifest.get('schema_version') != '1'
            or manifest.get('input_file') != 'shell.inp'):
        raise ValueError('Not an admitted S8 shell snapshot')
    from caelab.storage import check_id
    check_id(manifest['id'])
    if manifest.get('native_version', [])[:3] != ['1','1','4']:
        raise ValueError('The first shell writer contract requires FreeCAD 1.1.4')
    expected = MEMBERS | ({'editable.caepre'} if manifest.get('editable_project') == 'editable.caepre' else set())
    if manifest.get('editable_project') not in (None,'editable.caepre'):
        raise ValueError('Unknown editable shell project member')
    rows = manifest.get('files', [])
    if len(rows) != len(expected) or {r.get('relative') for r in rows} != expected:
        raise ValueError('Incomplete or unexpected frozen shell file set')
    pins = {'snapshot.json': {'bytes':len(read_bytes(path)), 'sha256':sha(path)}}
    for row in rows:
        data = read_bytes(path.parent / row['relative'])
        if type(row['bytes']) is not int or row['bytes'] <= 0 or len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Frozen shell file changed: '+row['relative'])
        pins[row['relative']] = {'bytes':row['bytes'],'sha256':row['sha256']}
    model = json_read(path.parent / 'mesh.json', MAX_BYTES)
    native_nodes, native_elements = native_mesh(read_bytes(path.parent/'native_mesh.inp').decode('ascii'))
    if ({str(n):p for n,p in native_nodes.items()} != model['source_nodes'] or
            {str(e):c for e,c in native_elements.items()} != model['source_elements']):
        raise ValueError('The source mesh record differs from native writeABAQUS output')
    text, mesh = build(model)
    if read_bytes(path.parent/'shell.inp') != text.encode('ascii'):
        raise ValueError('Shell input differs from its retained selection/properties/output contract')
    if digest(model['applied']) != manifest.get('applied_sha256'):
        raise ValueError('Applied native shell state changed')
    return manifest, model, mesh, pins
