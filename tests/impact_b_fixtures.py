"""Synthetic test bytes; not solver output and never native acceptance evidence."""
import json
from pathlib import Path
import runpy
import struct
import subprocess
import sys
from caelab import impact_model,impact_b
from caelab.impact_damage import apply_laws,verify_laws
from caelab.adapters.impact_admission import validate_physics,normalize_contact_friction,normalize_surfaces,global_gravity
from caelab.storage import save_json
ROOT=Path(__file__).resolve().parents[1]


def settings():
    return runpy.run_path(str(ROOT/'examples/impact/bulk_interface/example.py'))['settings']()


def compile_fixture(folder,s=None):
    s=s or settings(); folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    text,initial=impact_model.render(s)
    model=impact_model.model_from_settings(s)
    model={**model,"nodes":initial["nodes"]}
    inp=folder/'converter.inp';inp.write_text(text,encoding='ascii');target=folder/'converter_0000.rad'
    command=[sys.executable,str(ROOT/'caelab/adapters/inp2rad_worker.py'),str(inp)]
    completed=subprocess.run(command,capture_output=True,text=True,timeout=30)
    if completed.returncode:
        raise AssertionError(completed.stdout+'\n'+completed.stderr)
    native=target.read_text(encoding='ascii')
    native,_=global_gravity(native,s['gravity_mm_s2'])
    native,_=normalize_surfaces(normalize_contact_friction(native,s),model)
    physics=validate_physics(native,model,initial,s)
    native,cohesive=apply_laws(native,model,s['cohesive']);verify_laws(native,model,s['cohesive'],cohesive)
    effective,definition=impact_b.compile(native,model,s,cohesive)
    return s,model,initial,physics,effective,definition


def rec(data):
    n=struct.pack('>I',len(data));return n+data+n


def ints(*data):return rec(struct.pack('>'+str(len(data))+'i',*data))
def floats(*data):return rec(struct.pack('>'+str(len(data))+'f',*data))
def title(text,size=100):return text.encode('ascii').ljust(size,b' ')


def history_bytes(groups,*,times=(0.,.0001,.0003),units=(1000.,.001,1.),reorder=False,nan=False):
    groups=json.loads(json.dumps(groups))
    if reorder:
        for group in groups:group['tokens'].reverse()
    data=rec(struct.pack('>i',4021)+title('SYNTHETIC_TEST_NOT_NATIVE',80))+rec(b' '*80)
    data+=ints(2)+ints(100)+floats(*units)+ints(0,0,0,0,len(groups),23)+ints(*range(1,24))
    titles=[]
    for group in groups:
        n=len(group['tokens']);members=group['members']
        data+=rec(struct.pack('>5i',group['id'],group['type'],0,len(members),n)+title(group['title']))
        for member in members:
            data+=rec(struct.pack('>i',member)+title('MEMBER_'+str(member)))
            for token in group['tokens']:titles.extend([f"{group['type']:10d}",f'{token:<10}'])
        data+=ints(*range(1,n+1))
    starts=[]
    for i,time in enumerate(times):
        starts.append(len(data));data+=floats(time)+floats(*[float(j+i) for j in range(23)])
        for group in groups:
            values=[]
            for _ in group['members']:
                row={'OFF':0. if i==2 else 1.,'DAMA':i*.4,'PLAS':i*.1,'IE':i*10.,'VOL':1.,
                     'SX':100.,'SY':0.,'SZ':0.,'SXY':0.,'SYZ':0.,'SXZ':0.,'PLSR':i*100.}
                if nan and i==1:row['IE']=float('nan')
                values.extend(row.get(token,3.+i) for token in group['tokens'])
            data+=floats(*values)
    return data,('\n'.join(titles)+'\n').encode('ascii'),starts


def vtk_bytes(model,time,*,cohesive_active=1):
    nodes=sorted(model['nodes']);elements=sorted(model['elements']);idx={n:i for i,n in enumerate(nodes)}
    rows=['# vtk DataFile Version 3.0','SYNTHETIC_TEST_NOT_NATIVE','ASCII','DATASET UNSTRUCTURED_GRID','FIELD FieldData 1','TIME 1 1 float',str(time),
          f'POINTS {len(nodes)} float']
    rows+=[' '.join(map(str,model['nodes'][n])) for n in nodes]
    rows.append(f'CELLS {len(elements)} {len(elements)*9}')
    rows+=['8 '+' '.join(str(idx[n]) for n in model['elements'][e]['nodes']) for e in elements]
    rows +=[f'CELL_TYPES {len(elements)}',' '.join(['12']*len(elements)),f'POINT_DATA {len(nodes)}',
            'SCALARS NODE_ID int 1','LOOKUP_TABLE default',' '.join(map(str,nodes)),
            f'CELL_DATA {len(elements)}','SCALARS ELEMENT_ID int 1','LOOKUP_TABLE default',' '.join(map(str,elements)),
            'SCALARS PART_ID int 1','LOOKUP_TABLE default',' '.join(str(e) for e in elements),
            'SCALARS EROSION_STATUS int 1','LOOKUP_TABLE default',
            ' '.join(str(cohesive_active if model['elements'][e]['type']=='COH3D8' else 1) for e in elements)]
    return ('\n'.join(rows)+'\n').encode('ascii')


def attempt(folder,compiled,*,truncate=True,broken_frame=True):
    # Original delivery's legacy reprocess fixture is not part of the current
    # B card/history slice. Do not require that replaced owner path at import.
    from caelab.impact_reprocess import seal_terminal
    s,model,initial,physics,effective,definition=compiled
    folder=Path(folder);native=folder/'native';native.mkdir(parents=True)
    save_json(folder/'input.json',s);save_json(folder/'initial_conditions.json',initial)
    save_json(folder/'physical_admission.json',{'physics':physics});save_json(folder/'b_definition.json',definition)
    (native/'impact_0000.rad').write_text(effective,encoding='ascii')
    data,titles,starts=history_bytes(definition['outputs']['groups'])
    (native/'impactT01').write_bytes(data[:-13] if truncate else data)
    (native/'impactT01_TITLES').write_bytes(titles)
    for i,t in enumerate((0.,.0001,.0003)):
        (native/f'frame{i:04d}.vtk').write_bytes(b'BROKEN_SYNTHETIC_FRAME' if i==1 and broken_frame else vtk_bytes(model,t,cohesive_active=0 if i==2 else 1))
    (native/'impactA001').write_bytes(b'RAW_SYNTHETIC_ANIMATION_NOT_CONVERTED')
    result={'execution_status':'FAILED','diagnostics':{'decision':'NOT_RELEASED','fixture':'SYNTHETIC_NOT_NATIVE','native_execution_status':'FAILED'}}
    save_json(folder/'impact_execution.json',result)
    return seal_terminal(folder,result)
