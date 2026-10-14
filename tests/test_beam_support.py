"""Explicit synthetic native-shaped data for beam contract tests, NOT solver evidence."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace as NS
import json
from caelab.beam_model import SCHEMA,default_draft,native_axis_formula,frame,effective_conditions,validate_model,unit
from caelab.beam_deck import render
from caelab.beam_results import LABELS,sha
from caelab.storage import save_json, canonical_hash


def model(angle='0',direction=(1,0,0),diagnostic=False):
    t=unit(direction);a=frame(t,native_axis_formula(t,angle));d=default_draft('Analysis','Mesh',{'object':'Line','subelement':'Edge1'})
    d['section'].update(object_id='Section',rotation_id='Rotation',rotation_deg=str(angle))
    d['material']['object_id']='Material';d['diagnostic_oblique']=diagnostic
    d['ends'][0].update(reference={'object':'Line','subelement':'Vertex1'},translation_mm=['0']*3,rotation_deg=['0']*3)
    d['ends'][1].update(reference={'object':'Line','subelement':'Vertex2'},moment_Nmm=['0','1000','0'])
    value={'schema':SCHEMA,'element':'B32R','section_type':'RECT',
        'units':{'length':'mm','force':'N','moment':'Nmm','elasticity':'MPa','rotation':'rad'},
        'draft':d,'axes':a,'length_mm':1000.,'edge_start_mm':[0.,0.,0.],'edge_end_mm':[1000*v for v in t],
        'nodes':[{'id':n,'xyz_mm':[s*v for v in t]} for n,s in [(101,0),(408,250),(207,500),(913,750),(509,1000)]],
        'elements':[{'id':88,'native_nodes':[101,207,408],'ccx_nodes':[101,408,207]},
                    {'id':23,'native_nodes':[207,509,913],'ccx_nodes':[207,913,509]}],
        'end_node_ids':[101,509]}
    refresh(value);validate_model(value);return value


def refresh(value):
    value['loads'],value['boundaries'],value['end_conditions']=effective_conditions(value['draft'],value['axes'],value['end_node_ids'])
    return value


def frd(value,times=(1.,)):
    nodes,elements,_=validate_model(value)
    lines=['    1C','    1UVERSION           Version 2.22',f'    2C{len(nodes):30d}{1:38d}']
    row=lambda n,values:' -1'+f'{n:10d}'+''.join(f'{x:12.5E}' for x in values)
    lines += [row(n,p) for n,p in sorted(nodes.items())]+[' -3',f'    3C{len(elements):30d}{1:38d}']
    for e,ccx in sorted(elements.items()):
        lines += [' -1'+f'{e:10d}{12:5d}{0:5d}{1:5d}', ' -2'+''.join(f'{n:10d}' for n in (ccx[0],ccx[2],ccx[1]))]
    lines+=[' -3'];counter=0
    for inc,time in enumerate(times,1):
        for name,labels in LABELS.items():
            counter+=1
            lines += ['    1PSTEP'+' '*14+f'{counter:12d}{inc:12d}{1:12d}'+' '*10,
                '  100CL'+f'{100+inc:5d}{time:12.9f}{len(nodes):12d}'+' '*21+'0'+f'{inc:5d}'+' '*11+'1',
                f' -4 {name} {len(labels)} 1']
            lines += [' -5 '+label for label in labels]
            for n in sorted(nodes):
                # Deliberately NOT an analytical or fitted physical beam solution.
                values={'DISP':[.1,.2,.3],'FORC':[1.,2.,3.],'STRESS':[11.,22.,33.,44.,55.,66.]}[name]
                lines.append(row(n,[x*time for x in values]))
            lines+=[' -3']
    return '\n'.join(lines+[' 9999'])+'\n'


def snapshot(folder,value=None):
    value=deepcopy(value or model());folder=Path(folder);folder.mkdir(parents=True)
    # Synthetic geometry identity follows the actual native collect contract.
    # The opaque CAD bytes below remain explicitly NOT a FreeCAD execution.
    if 'source' not in value:
        value['source']={'document_id':'Pbeamtest','native_document':'SyntheticBeam',
            'analysis_id':value['draft']['analysis_id'],'mesh_id':value['draft']['mesh_id'],
            'solver_id':'Solver','end_object_ids':['End1','End2'],'binding':{
                'mesh_id':value['draft']['mesh_id'],
                'mesh_sha256':canonical_hash({'nodes':value['nodes'],'elements':value['elements']}),
                'edge':deepcopy(value['draft']['edge']),
                'ends':[deepcopy(row['reference']) for row in value['draft']['ends']]}}
    # Clearly synthetic opaque CAD files, admitted here only to test pinning and
    # execution contracts. Native FreeCAD acceptance uses the real generator.
    (folder/'editable.FCStd').write_bytes(b'SYNTHETIC CAD BYTES - NOT A FREECAD DOCUMENT')
    (folder/'editable.caepre').write_bytes(b'SYNTHETIC PROJECT BYTES - NOT A NATIVE PROJECT')
    save_json(folder/'mesh.json',value);(folder/'beam.inp').write_text(render(value),encoding='ascii')
    manifest={'kind':'freecad-beam-frozen','schema_version':'1','id':'Fbeamtest','input_file':'beam.inp',
        'editable_project':'editable.caepre','native_version':['1','1','4'],
        'document_id':'Pbeamtest','analysis_id':value['draft']['analysis_id'],
        'writers':{'output':'OUTPUT=2D / SECTION FORCES'},'files':[
            {'relative':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(folder.iterdir())]}
    save_json(folder/'snapshot.json',manifest);return folder/'snapshot.json'
