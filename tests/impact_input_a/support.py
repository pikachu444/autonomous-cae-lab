"""Explicit synthetic native boundary fixtures. NEVER native solver acceptance."""
import csv
import io
from pathlib import Path
import struct
import subprocess

TIMES=(0.,.0005,.001)


def vtk(time,*,active=1,unknown=False):
    points=' '.join(f'{x:g} {y:g} {z-100*time:.12g}' for x,y,z in [(0,0,0),(10,0,0),(0,10,0),(0,0,10)])
    disp=' '.join(f'0 0 {-100*time:.12g}' for _ in range(4))
    return (f'# vtk DataFile Version 3.0\nUNIT SYNTHETIC OUTPUT NOT NATIVE SOLVER EVIDENCE\nASCII\nDATASET UNSTRUCTURED_GRID\n'
            f'FIELD FieldData 1\nTIME 1 1 double\n{time:.17g}\nPOINTS 4 float\n{points}\n'
            'CELLS 1 5\n4 0 1 2 3\nCELL_TYPES 1\n10\n'
            'POINT_DATA 4\nSCALARS NODE_ID int 1\nLOOKUP_TABLE default\n1 2 3 4\n'
            f'VECTORS Displacement float\n{disp}\nVECTORS Velocity float\n0 0 -100 0 0 -100 0 0 -100 0 0 -100\n'
            +('VECTORS Unknown_Force float\n1 2 3 1 2 3 1 2 3 1 2 3\n' if unknown else '')+
            f'CELL_DATA 1\nSCALARS ELEMENT_ID int 1\nLOOKUP_TABLE default\n1\nSCALARS PART_ID int 1\nLOOKUP_TABLE default\n1\n'
            f'SCALARS EROSION_STATUS int 1\nLOOKUP_TABLE default\n{active}\nTENSORS 3DELEM_Stress float\n0 0 0 0 0 0 0 0 0\n')


def th_and_csv(times=TIMES):
    from caelab.adapters.impact_results import GLOBAL_NAMES
    def record(b):return struct.pack('>I',len(b))+b+struct.pack('>I',len(b))
    def ints(*v):return struct.pack('>'+str(len(v))+'i',*v)
    def floats(v):return struct.pack('>'+str(len(v))+'f',*v)
    data=record(ints(4021)+b'UNIT synthetic TH'.ljust(80))+record(b'UNIT date'.ljust(80))
    data+=record(ints(2))+record(ints(100))+record(floats([1000.,.001,1.]))
    data+=record(ints(0,0,0,0,0,23))+record(ints(*range(1,24)))
    text=io.StringIO(newline='');writer=csv.writer(text);writer.writerow(['time',*GLOBAL_NAMES])
    for time in times:
        values=[0.]*23;values[1]=.0065;values[4]=-1.3e-4;values[5]=1.3e-6;values[6]=1e-6
        data+=record(floats([time]))+record(floats(values))
        converted=struct.unpack('>24f',floats([time,*values]))
        writer.writerow([format(v,'.6e') for v in converted])
    return data,text.getvalue().encode('ascii')


def install_boundary_double(monkeypatch,*,fail_after_engine=False):
    from caelab.adapters import impact
    calls=[];th,csvbytes=th_and_csv()
    names={n:'UNIT_'+n for n in ('starter','engine','anim_to_vtk','th_to_csv')}
    identity={'UNIT_SYNTHETIC_OUTPUTS_NOT_NATIVE':True}
    monkeypatch.setattr(impact,'selected_runtime',lambda:(names,{},identity))
    def command(argv,cwd,label,**kw):
        cwd=Path(cwd);calls.append(label);assert kw.get('owned_tree') is True
        stdout=b''
        if label=='starter':
            (cwd/'impact_0000.out').write_text('UNIT ONLY\nNORMAL TERMINATION\nNO SYNTAX ERROR DETECTED\n0 ERROR(S)\n0 WARNING(S)\nNUMNOD: 4\nWORK UNIT SYSTEM ( Mg , mm , s ) 1E3 1E-3 1E0\nINPUT UNIT SYSTEM ( Mg , mm , s ) 1E3 1E-3 1E0\n')
        elif label=='engine':
            (cwd/'impact_0001.out').write_text('UNIT ONLY\nFINAL TIME 1E-3\nNORMAL TERMINATION\nTOTAL NUMBER OF CYCLES : 1000\n')
            (cwd/'impactT01').write_bytes(th);(cwd/'impactT01_TITLES').write_bytes(b'UNIT ONLY synthetic titles')
            for i,_ in enumerate(TIMES):(cwd/f'impactA{i+1:03d}').write_bytes(b'UNIT ONLY synthetic ANIM placeholder')
        elif label=='history_convert':
            (cwd/'history.csv').write_bytes(csvbytes)
            if fail_after_engine:raise ValueError('UNIT injected readback failure after original outputs')
        elif label.startswith('animation_'):
            index=int(label.rsplit('_',1)[1]);stdout=vtk(TIMES[index],unknown=True).encode('ascii')
        else:raise AssertionError('Native direct path must not call INP2RAD or another process: '+label)
        return subprocess.CompletedProcess(argv,0,stdout=stdout,stderr=b'')
    monkeypatch.setattr(impact,'run_owned_command',command)
    return calls
