"""Narrow free native CalculiX 2.22 extension for end moments and radians.

The installed FreeCAD mesh and section writers are compared at freeze time.
No solid conversion, rigid-body workaround, force-couple synthesis or stress
interpretation is performed by this module.
"""
from .beam_model import validate_model, number


def section_card(model):
    s=model['draft']['section'];m=model['axes']['local1']
    return ('*BEAM SECTION, ELSET=BEAM, MATERIAL=BEAMMAT, SECTION=RECT\n'
            +f"{number(s['width_mm']):.13G},{number(s['height_mm']):.13G}\n"
            +', '.join(f'{x:.13G}' for x in m)+'\n')


def render(model):
    nodes,elements,_=validate_model(model)
    material=model['draft']['material']
    out=['*HEADING','CAE Lab B32R beam; mm N Nmm MPa rad; original 1D nodes',
         '*NODE, NSET=NALL']
    out += [f'{n},'+','.join(f'{x:.13G}' for x in nodes[n]) for n in sorted(nodes)]
    out += ['*ELEMENT, TYPE=B32R, ELSET=BEAM']
    out += [f'{e},'+','.join(str(n) for n in elements[e]) for e in sorted(elements)]
    out += ['*MATERIAL, NAME=BEAMMAT','*ELASTIC',
            f"{number(material['young_MPa']):.13G},{number(material['poisson']):.13G}",
            # Explicit ccx 2.22 effective defaults avoid its warning for tmin=0.
            # This is a unitless linear-static load parameter, not physical time.
            section_card(model).rstrip(), '*STEP', '*STATIC','1.,1.,1.e-6,1.e30', '*BOUNDARY']
    out += [f"{b['node']},{b['dof']},{b['dof']},{b['value']:.13G}" for b in model['boundaries']]
    if model['loads']:
        out += ['*CLOAD']
        out += [f"{v['node']},{v['dof']},{v['value']:.13G}" for v in model['loads']]
    # S slots here are mixed-unit section forces, NEVER a stress tensor.
    out += ['*NODE FILE, OUTPUT=2D, GLOBAL=YES','U,RF',
            '*EL FILE, SECTION FORCES','S', '*NODE PRINT, NSET=NALL','U,RF','*END STEP']
    return '\n'.join(out)+'\n'


def matches_saved_input(text, model):
    """Read only the exact current or originally emitted linear-static deck.

    The old deck omitted native effective increment defaults. Its preserved
    warning/execution verdict remains unchanged; new exports use explicit values.
    """
    current = render(model)
    legacy = current.replace('*STATIC\n1.,1.,1.e-6,1.e30\n', '*STATIC\n1.,1.\n', 1)
    return text.replace('\r\n', '\n') in (current, legacy)


def parse_native_mesh(text):
    """Read only the installed FemMesh.writeABAQUS mesh portion."""
    nodes,elements={},{}; keyword='';kind=''
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('**'): continue
        if line.startswith('*'):
            parts=[x.strip().upper() for x in line.split(',')]
            keyword=parts[0];options=dict(x.split('=',1) for x in parts[1:] if '=' in x)
            if keyword not in ('*NODE','*ELEMENT','*NSET','*ELSET','*HEADING'):
                raise ValueError('Native mesh writer emitted an unsupported keyword: '+keyword)
            if keyword=='*ELEMENT':
                kind=options.get('TYPE')
                if kind!='B32R':raise ValueError('Native writer must emit B32R, not '+str(kind))
            continue
        fields=[x.strip() for x in line.split(',')]
        if keyword=='*NODE':
            n=int(fields[0])
            if n in nodes or len(fields)!=4:raise ValueError('Invalid native node record')
            nodes[n]=[float(x.replace('D','E')) for x in fields[1:]]
        elif keyword=='*ELEMENT':
            e=int(fields[0])
            if e in elements or len(fields)!=4:raise ValueError('Invalid native B32R connectivity')
            elements[e]=list(map(int,fields[1:]))
    return nodes,elements
