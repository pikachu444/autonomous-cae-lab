"""Deterministic CCX 2.22 S8R laminate cards; E1 S8 deck remains unchanged."""
from pathlib import Path
import json

from caelab.composite_shell import PROFILE, prepare_mesh, ply_axes, ORTHOTROPIC
from caelab.shell_model import check_supports, digest
from .shell_deck import token, native_mesh, read_bytes, sha, json_read

KIND='freecad-composite-shell-frozen'
MESH_KIND='freecad-composite-shell-mesh'
MEMBERS={'editable.FCStd','editable.caepre','mesh.json','native_mesh.inp','composite.inp'}


def build(model):
    if model.get('kind')!=MESH_KIND or model.get('profile')!=PROFILE:
        raise ValueError('Explicit CCX 2.22 S8R composite profile is required')
    if model.get('units')!={'position':'mm','stress':'MPa','force':'N'}:
        raise ValueError('Composite input requires mm, MPa and N')
    if model.get('applied',{}).get('draft')!=model.get('draft'):
        raise ValueError('Apply the current laminate draft before freezing it')
    nodes,elements=native_mesh(model['native_mesh'])
    if ({str(k):v for k,v in nodes.items()}!=model['source_nodes'] or
        {str(k):list(v) for k,v in elements.items()}!=model['source_elements']):
        raise ValueError('Native original eight-node mesh differs from retained geometry')
    mesh=prepare_mesh(nodes,elements,model['draft'])
    fixed=check_supports(mesh,model['fixed_nodes'])
    lines=['*HEADING','CAE Lab explicit S8R laminate; global mm N MPa; no homogenization','*NODE']
    for n,xyz in mesh['nodes'].items():lines.append(str(n)+', '+', '.join(token(v) for v in xyz))
    lines.append('*ELEMENT, TYPE=S8R, ELSET=LABCOMPOSITE')
    for e,conn in mesh['elements'].items():lines.append(str(e)+', '+', '.join(map(str,conn)))
    materials=mesh['values']['materials']; names={name:'PLYMAT'+str(i+1) for i,name in enumerate(sorted(materials))}
    for name in sorted(materials):
        material=materials[name]
        lines.append('*MATERIAL, NAME='+names[name]); values=material['constants']
        if material['law']=='isotropic_linear':
            lines+=['*ELASTIC',', '.join(token(values[k]) for k in ('E_MPa','nu'))]
        else:
            lines+=['*ELASTIC, TYPE=ENGINEERING CONSTANTS',
                    ', '.join(token(values[k]) for k in ORTHOTROPIC[:8]),token(values['G23_MPa'])]
    mapping={}
    for e,conn in mesh['elements'].items():
        region=mesh['region_by_element'][e]; native=[]
        for j,ply in enumerate(reversed(region['plies']),1):
            x,y,n=ply_axes(mesh['axes'][e],ply['angle_deg']); orientation=f'PLYORI{e}_{j}'
            lines += [f'*ORIENTATION, NAME={orientation}, SYSTEM=RECTANGULAR',
                      ', '.join(token(v) for v in (*x,*y))]
            native.append({'native_layer':j,'ply_id':ply['id'],'ui_position':len(region['plies'])-j+1,
                           'thickness_mm':float(token(ply['thickness_mm'])),'material_id':ply['material_id'],
                           'angle_deg':ply['angle_deg'],'axes_global':[x,y,n],'orientation':orientation})
        lines += [f'*ELSET, ELSET=COMPE{e}',str(e),
                  f'*SHELL SECTION, ELSET=COMPE{e}, COMPOSITE, OFFSET={token(region["offset"])}']
        for row in native:
            lines.append(f'{token(row["thickness_mm"])},, {names[row["material_id"]]}, {row["orientation"]}')
        mapping[e]=native
    lines += ['*NSET, NSET=COMPFIX']
    lines += [', '.join(map(str,fixed[i:i+12])) for i in range(0,len(fixed),12)]
    lines += ['*STEP','*STATIC','1., 1.','*BOUNDARY','COMPFIX, 1, 6','*DLOAD']
    lines += [f'{e}, P, {token(-mesh["region_by_element"][e]["pressure_MPa"])}' for e in mesh['elements']]
    # GLOBAL S/E intentionally do not enter CCX printoutint.f coords(3,27).
    # DAT is the layer IP source; FRD remains a native extrapolated spatial view.
    lines += ['*NODE FILE, OUTPUT=3D, GLOBAL=YES','U','*EL FILE, GLOBAL=YES','S, E',
              '*EL PRINT, ELSET=LABCOMPOSITE, GLOBAL=YES','S, E','*END STEP']
    mesh['native_layers']=mapping
    return '\n'.join(lines)+'\n',mesh


def validate_snapshot(path):
    path=Path(path)
    if not path.is_absolute() or path.name!='snapshot.json':raise ValueError('Select the completed absolute composite snapshot.json')
    manifest=json_read(path)
    if manifest.get('kind')!=KIND or manifest.get('input_file')!='composite.inp' or manifest.get('schema_version')!='1':
        raise ValueError('Not an admitted composite shell snapshot')
    if manifest.get('native_version',[])[:3]!=['1','1','4'] or manifest.get('editable_project')!='editable.caepre':
        raise ValueError('Editable FreeCAD 1.1.4 source is required')
    rows=manifest.get('files',[])
    if len(rows)!=len(MEMBERS) or {r.get('relative') for r in rows}!=MEMBERS:
        raise ValueError('Composite frozen file set is incomplete or unexpected')
    pins={'snapshot.json':{'bytes':path.stat().st_size,'sha256':sha(path)}}
    for row in rows:
        data=read_bytes(path.parent/row['relative'])
        if len(data)!=row['bytes'] or sha(path.parent/row['relative'])!=row['sha256']:
            raise ValueError('Frozen composite source changed: '+row['relative'])
        pins[row['relative']]={'bytes':row['bytes'],'sha256':row['sha256']}
    model=json_read(path.parent/'mesh.json');text,mesh=build(model)
    if read_bytes(path.parent/'composite.inp')!=text.encode('ascii') or read_bytes(path.parent/'native_mesh.inp').decode('ascii')!=model['native_mesh']:
        raise ValueError('Composite deck differs from its exact applied laminate/mesh')
    if manifest.get('applied_sha256')!=digest(model['applied']):raise ValueError('Applied laminate identity differs')
    return manifest,model,mesh,pins
