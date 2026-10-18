"""Bounded spatial FE declarations for the existing FELUPE solver.

No FE assembly, quadrature, linear solver or global Newton is implemented here.
Hex8 reference configuration, quasistatic only, explicit mm/MPa/s.
"""
from copy import deepcopy
import numpy as np
from plugins.material_point import law_native as law
from plugins.material_point.law_native_tensors import finite

FE_LIMITS={'dp_stress_atol_mpa':2e-7,'dp_stress_rtol':2e-6,
           'neo_stress_atol_mpa':1e-8,'neo_stress_rtol':1e-6,
           'sls_stress_atol_mpa':1e-10,'sls_stress_rtol':1e-8,
           'F_absolute':2e-9,'relative_force_balance':2e-8,
           'native_newton_relative_tolerance':1e-12}


def dp_observables(stress_kelvin, state, parameters):
    """Project a retained DP response; never integrate or qualify a material.

    Pressure is compression-positive. The yield-function value is signed,
    including elastic unloading; it is not a Newton residual or a verdict.
    """
    stress = finite(stress_kelvin, (6,), 'Retained DP Kelvin stress')
    accepted = law.dp.validate_state(state)
    coefficients = law.dp.validate_parameters(parameters)
    pressure, equivalent = law.dp.invariants(stress)
    return {'pressure': pressure, 'equivalent_stress': equivalent,
            'yield_function': equivalent - coefficients['alpha'] * pressure
                - coefficients['k0'] - coefficients['H'] * accepted['kappa'],
            'plastic_volume_strain': float(sum(accepted['plastic_strain_kelvin'][:3])),
            'kappa': accepted['kappa']}


def cube_mesh(n=3, length_mm=1.):
    if type(n) is not int or not 3<=n<=9 or type(length_mm) not in (int,float) or length_mm<=0:
        raise ValueError('Public cube requires 3..9 nodes/axis and positive length in mm')
    points=[[i*length_mm/(n-1),j*length_mm/(n-1),k*length_mm/(n-1)]
            for k in range(n) for j in range(n) for i in range(n)]
    def ix(i,j,k):return i+n*j+n*n*k
    cells=[[ix(i,j,k),ix(i+1,j,k),ix(i+1,j+1,k),ix(i,j+1,k),
            ix(i,j,k+1),ix(i+1,j,k+1),ix(i+1,j+1,k+1),ix(i,j+1,k+1)]
           for k in range(n-1) for j in range(n-1) for i in range(n-1)]
    return {'points':points,'cells':cells,'length_unit':'mm','element':'Hexahedron8',
            'connectivity':'VTK_HEXAHEDRON_0_BASED','quadrature':'Gauss2x2x2'}


def default_settings(model=law.dp.MODEL):
    return {'law':law.default_settings(model),'mesh':cube_mesh(),
            'boundary':{'mode':'affine_boundary','origin_mm':[0.,0.,0.]},
            'solver':{'backend':law.FE,'felupe_version':law.FELUPE_VERSION,'step':'quasistatic',
                'max_iterations':40,'force_tolerance_N':1e-8},'compare_point':True}


def boundary_nodes(cells):
    faces={}
    for cell in cells:
        for face in ((0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):
            key=tuple(sorted(cell[i] for i in face));faces[key]=faces.get(key,0)+1
    if any(count>2 for count in faces.values()):
        raise ValueError('Nonmanifold Hex8 face incidence')
    return sorted({n for face,count in faces.items() if count==1 for n in face})


def _require_box_boundary_faces(cells, points):
    """Six complete axis-aligned exterior planes, not just nodes on their union."""
    incidence={}
    for cell in cells:
        for local in ((0,1,2,3),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):
            face=tuple(sorted(cell[i] for i in local))
            incidence[face]=incidence.get(face,0)+1
    limits=(points.min(axis=0),points.max(axis=0));covered=set()
    for face,count in incidence.items():
        if count!=1:continue
        planes={(axis,side) for axis in range(3) for side in (0,1)
                if np.all(points[list(face),axis]==limits[side][axis])}
        if not planes:
            raise ValueError('Box normal displacement boundary face must lie in one min/max plane')
        covered.update(planes)
    if covered!={(axis,side) for axis in range(3) for side in (0,1)}:
        raise ValueError('Box normal displacement requires all six exterior planes')


def validate_settings(settings):
    if (not isinstance(settings,dict) or not {'law','mesh','boundary','solver','compare_point'}<=set(settings)
            or set(settings)-{'law','mesh','boundary','solver','compare_point','source_receipt'}):
        raise ValueError('FE settings require exact law/mesh/boundary/solver/compare_point')
    s=deepcopy(settings);law.validate_settings(s['law'])
    if s['law']['stress_unit']!='MPa':
        raise ValueError('FE mapping must explicitly convert source to MPa; coordinates are mm, reactions N')
    if len(s['law']['time'])>128:
        raise ValueError('This small FE worker admits at most 128 requested states')
    mesh=s['mesh']
    if not isinstance(mesh,dict) or set(mesh)!={'points','cells','length_unit','element','connectivity','quadrature'}:
        raise ValueError('Complete frozen Hex8 mesh is required')
    if (mesh['length_unit'],mesh['element'],mesh['connectivity'],mesh['quadrature']) != (
            'mm','Hexahedron8','VTK_HEXAHEDRON_0_BASED','Gauss2x2x2'):
        raise ValueError('Only mm full-integration Hex8; no tetra/shell/beam/plane substitution')
    if not isinstance(mesh['points'],list) or not 9<=len(mesh['points'])<=4096:
        raise ValueError('FE mesh requires 9..4096 points (at least one unconstrained spatial node)')
    points=finite(mesh['points'],(len(mesh['points']),3),'FE points')
    if not isinstance(mesh['cells'],list) or not 1<=len(mesh['cells'])<=512:
        raise ValueError('Small FE mesh requires 1..512 Hex8 cells')
    if any(not isinstance(c,list) or len(c)!=8 or len(set(c))!=8 or
           any(type(i) is not int or not 0<=i<len(points) for i in c) for c in mesh['cells']):
        raise ValueError('Hex8 connectivity must contain eight distinct existing zero-based nodes')
    if len({tuple(c) for c in mesh['cells']})!=len(mesh['cells']):
        raise ValueError('Duplicate Hex8 cells')
    if {i for c in mesh['cells'] for i in c}!=set(range(len(points))):
        raise ValueError('Isolated/unused mesh points are not admissible')
    skin=boundary_nodes(mesh['cells'])
    if len(skin)==len(points):
        raise ValueError('Use the public 8-element cube or a mesh with actual free interior DOFs')
    solver=s['solver']
    if not isinstance(solver,dict) or set(solver)!={'backend','felupe_version','step','max_iterations','force_tolerance_N'}:
        raise ValueError('Explicit bounded FELUPE solver declaration required')
    if (solver['backend'],solver['felupe_version'],solver['step'])!=(law.FE,law.FELUPE_VERSION,'quasistatic'):
        raise ValueError('Wrong solver/version/step. No CalculiX, dynamic, contact or impact admission')
    if type(solver['max_iterations']) is not int or not 1<=solver['max_iterations']<=80:
        raise ValueError('FE maximum iterations must be 1..80')
    if not 0<finite([solver['force_tolerance_N']],(1,),'force tolerance')[0]<=1e-7:
        raise ValueError('Fixed force tolerance must be positive and at most 1e-7 N')
    if type(s['compare_point']) is not bool:
        raise ValueError('compare_point is an explicit boolean')
    b=s['boundary']
    if not isinstance(b,dict) or set(b)!={'mode','origin_mm'} or b['mode'] not in ('affine_boundary','uniaxial_zero_lateral','box_normal_displacement'):
        raise ValueError('Choose affine_boundary, uniaxial_zero_lateral or box_normal_displacement; no inferred loads')
    finite(b['origin_mm'],(3,),'boundary origin')
    if b['mode']=='affine_boundary' and s['law'].get('boundary_control'):
        raise ValueError('Affine FE boundary cannot be compared to free-lateral point history')
    if b['mode']=='box_normal_displacement':
        if s['law']['model']!=law.dp.MODEL or s['law'].get('boundary_control'):
            raise ValueError('Box normal displacement admits small-strain DP prescribed F only; no point stress control')
        _require_box_boundary_faces(mesh['cells'],points)
    if b['mode'] in ('uniaxial_zero_lateral','box_normal_displacement'):
        label='Uniaxial' if b['mode']=='uniaxial_zero_lateral' else 'Box normal displacement'
        if b['mode']=='uniaxial_zero_lateral':
            bc=s['law'].get('boundary_control',{}).get('stress_components',{})
            if set(bc)!={'yy','zz'} or any(any(v!=0 for v in a) for a in bc.values()):
                raise ValueError('Uniaxial FE pair requires explicit zero yy/zz point stress controls')
        for F in s['law']['deformation_gradient']:
            F=np.asarray(F)
            if np.any(F-np.diag(np.diag(F))):
                raise ValueError(label+' pair does not impose shear/rotation')
        if not np.allclose(s['law']['deformation_gradient'][0],np.eye(3),atol=0,rtol=0):
            raise ValueError(label+' initial geometry must be undeformed')
        if not np.array_equal(np.asarray(b['origin_mm']),points.min(axis=0)):
            raise ValueError(label+' origin must equal the box minimum')
        # Real specimen boundary faces must cover six axis-aligned surfaces.
        lo,hi=points.min(axis=0),points.max(axis=0)
        if np.any(hi<=lo) or any(not any(p[a] in (lo[a],hi[a]) for a in range(3)) for p in points[skin]):
            raise ValueError(('Free-lateral public pair' if b['mode']=='uniaxial_zero_lateral' else label)+
                ' requires an axis-aligned rectangular specimen')
    if 'source_receipt' in s:
        from .material_fe_transfer import cold_assignment, verify_source
        from .storage import canonical_hash
        record=cold_assignment(s['source_receipt'])
        reviewed=record['review']['interface']['settings']
        actual={k:v for k,v in s.items() if k!='source_receipt'}
        if canonical_hash(reviewed)!=canonical_hash(actual):
            raise ValueError('Frozen FE input differs from the explicitly applied saved Material/mesh/protocol')
        verify_source(record['review']['source'],current_code=True)
    return s


def describe_model(s):
    s=validate_settings(s)
    return {'backend':law.FE,'law':law.declaration(s['law']),'solver':s['solver'],
            'element':s['mesh']['element'],'quadrature':s['mesh']['quadrature'],
            'length_unit':'mm','force_unit':'N','boundary':s['boundary'],
            'evidence':'EXECUTION_NOT_TESTED','energy_location':'constitutive integration point',
            'physical_calibration':'UNKNOWN','engineering_release':'UNKNOWN'}
