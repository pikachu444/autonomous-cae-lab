"""Calculated CCX 2.22 section/DOF cards, using existing ordered stage output."""
from .pretension import sections
from .contact_deck import num


def model_cards(model):
    rows=sections(model);lines=[]
    # All RP labels must precede all solver-generated partner labels.
    for row in rows:
        n=row['reference_node']
        lines+=['*NODE,NSET='+row['reference_set'],str(n)+',0,0,0']
    for row in rows:
        n=row['reference_node']
        lines+=['*SURFACE,NAME='+row['surface_name']]
        lines += [str(e)+',S'+str(f) for e,f in row['draft']['element_faces']]
        lines+=['*PRE-TENSION SECTION,SURFACE='+row['surface_name']+',NODE='+str(n),
                ','.join(num(v) for v in row['draft']['axis'])]
    return lines


def step_cards(model,index):
    lines=[]
    for row in sections(model):
        n=str(row['reference_node']);control=row['draft']['control']
        if index==1:
            if control['kind']=='force_N':lines+=['*CLOAD',n+',1,'+num(control['value'])]
            else:lines+=['*BOUNDARY',n+',1,1,'+num(control['value'])]
        else:
            # The existing stage writer has already reset CLOAD/BOUNDARY.
            # FIXED reads prior converged vold; an explicit 0 would unload it.
            lines+=['*BOUNDARY,FIXED',n+',1,1']
    return lines


def output_cards(model,frequency=''):
    lines=[]
    for row in sections(model):
        lines+=['*SECTION PRINT,SURFACE='+row['surface_name']+',NAME='+row['surface_name']+frequency.replace('FREQUENCY=','FREQUENCYF='),'SOF',
                '*NODE PRINT,NSET='+row['reference_set']+frequency,'U,RF']
    return lines
