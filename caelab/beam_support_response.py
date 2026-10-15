"""Distinct beam support observations, without section-force/reaction aliases.

Stress-traction integration uses native recovered nodal stress and actual
expanded section coordinates. RF sums retain the external-nodal-force meaning
of CalculiX RF, including its MPC/load limitations. Neither is promoted to a
complete discrete constraint reaction by this module.
"""
from copy import deepcopy
import math

from .shell_model import shape8, derivatives8, cross, dot, sub, unit


def _vec(value):
    if len(value) != 3 or any(isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) for v in value):
        raise ValueError('A complete finite global three-component observation is required')
    return list(value)


def moment_about(force, moment, old_reference, new_reference):
    """M(r1) = M(r0) - (r1-r0) cross F. No change in physical observations."""
    force, moment = _vec(force), _vec(moment)
    shift = cross(sub(_vec(new_reference), _vec(old_reference)), force)
    return [moment[i]-shift[i] for i in range(3)]


def sum_observed_rf(points, forces, reference):
    if not points or set(points) != set(forces):
        raise ValueError('RF summation requires exact coordinate/force coverage; missing values are not zero')
    reference = _vec(reference)
    total = [0.,0.,0.]; moment = [0.,0.,0.]
    for n in sorted(points):
        p, f = _vec(points[n]), _vec(forces[n])
        m = cross(sub(p, reference), f)
        total = [a+b for a,b in zip(total,f)]; moment = [a+b for a,b in zip(moment,m)]
    return {'force_N': total, 'moment_Nmm': moment, 'reference_mm': reference,
            'measure': 'sum_native_expanded_external_nodal_RF_and_its_moment',
            'recovery': 'sum_of_observed_RF_no_missing_fill',
            'frame': 'FREECAD_DOCUMENT_GLOBAL', 'expanded_node_ids': sorted(points),
            'total_constraint_reaction': 'UNAVAILABLE',
            'limitation': 'RF includes external loads and may omit MPC contributions; no generalized reaction moment is inferred.'}


def integrate_face(points, stresses, outward_normal, reference):
    """3x3 Gauss integration of sigma*n on an actual eight-node section face.

    The native stress is already recovered/averaged. Interpolating that tensor
    on the actual face is an explicitly derived traction estimate, not raw IP.
    """
    if len(points) != 8 or len(stresses) != 8:
        raise ValueError('All eight actual expanded face observations are required')
    points = [_vec(p) for p in points]; reference = _vec(reference); normal = unit(_vec(outward_normal))
    for tensor in stresses:
        if len(tensor) != 6 or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) for v in tensor):
            raise ValueError('Complete finite native Cauchy tensor required on every face node')
    g=math.sqrt(3/5); quadrature=((-g,5/9),(0.,8/9),(g,5/9))
    force=[0.,0.,0.]; moment=[0.,0.,0.]; area=0.
    center = points[0]; winding = None
    for r,wr in quadrature:
        for s,ws in quadrature:
            N=shape8(r,s); dr,ds=derivatives8(r,s)
            a=[sum(w*(p[k]-center[k]) for w,p in zip(dr,points)) for k in range(3)]
            b=[sum(w*(p[k]-center[k]) for w,p in zip(ds,points)) for k in range(3)]
            jac=cross(a,b)
            if abs(dot(jac,normal)) <= 1e-12*max(1.,math.hypot(*jac)):
                raise ValueError('Expanded support face is degenerate or tangent to its declared end normal')
            sign = 1 if dot(jac,normal)>0 else -1
            if winding is not None and sign != winding:
                raise ValueError('Expanded support face is folded; inconsistent Jacobian orientation')
            winding = sign
            if sign<0: jac=tuple(-v for v in jac)
            xx,yy,zz,xy,yz,zx=[sum(w*t[k] for w,t in zip(N,stresses)) for k in range(6)]
            matrix=((xx,xy,zx),(xy,yy,yz),(zx,yz,zz))
            df=[wr*ws*dot(row,jac) for row in matrix]
            p=[sum(w*x[k] for w,x in zip(N,points)) for k in range(3)]
            dm=cross(sub(p,reference),df)
            force=[a+b for a,b in zip(force,df)]; moment=[a+b for a,b in zip(moment,dm)]
            area+=wr*ws*math.hypot(*jac)
    return {'force_N':force,'moment_Nmm':moment,'area_mm2':area,'reference_mm':reference,
            'outward_normal':list(normal), 'frame':'FREECAD_DOCUMENT_GLOBAL',
            'measure':'support_stress_traction_integral',
            'recovery':'S8_face_interpolation_of_native_extrapolated_averaged_stress',
            'quadrature':'3x3_Gauss_actual_expanded_surface_Jacobian',
            'native_integration_point_value':False,'discrete_constraint_reaction':False}


def support_responses(model, sections, fields, source_pins):
    from .beam_output import settings
    from .beam_model import number
    options=settings(model['draft']); result=[]
    reference=[number(v) for v in options['reference_mm']]
    for group in options['supports']:
        faces=[]; seen=set(); observed_nodes=set()
        for end in group['ends']:
            original=model['end_node_ids'][end]
            selected=[r for r in sections if r['beam_node_id']==original and r['station_kind'] in ('start','end')]
            if len(selected)!=1:
                raise ValueError('A support endpoint must identify one actual exterior expanded section')
            face=selected[0]; identity=tuple(sorted(face['expanded_node_ids']))
            if identity in seen:
                raise ValueError('Duplicate support face; refusing double-sided/double integration')
            seen.add(identity); faces.append(face); observed_nodes.update(face['expanded_node_ids'])
        row={'label':group['label'],'ends':deepcopy(group['ends']),
             'reference_mm':reference,'frame':'FREECAD_DOCUMENT_GLOBAL','source_pins':deepcopy(source_pins),
             'qualification':'NOT_ENGINEERING_QUALIFIED','faces':deepcopy(faces)}
        if 'FORC' in fields:
            points={n: p for face in faces for n,p in zip(face['expanded_node_ids'],face['positions_mm'])}
            if not observed_nodes <= set(fields['FORC']):
                raise ValueError('Incomplete support RF coverage')
            row['native_RF_sum']=sum_observed_rf(points,{n:fields['FORC'][n] for n in observed_nodes},reference)
        else:
            row['native_RF_sum']={'status':'UNAVAILABLE','reason':'No complete native FORC field at this frame'}
        if 'STRESS' in fields:
            contributions=[]
            for face in faces:
                normal=[v*(-1 if face['station_kind']=='start' else 1) for v in face['axes']['tangent']]
                contributions.append(integrate_face(face['positions_mm'],
                    [fields['STRESS'][n] for n in face['expanded_node_ids']],normal,reference))
            row['stress_traction']={'force_N':[sum(c['force_N'][i] for c in contributions) for i in range(3)],
                'moment_Nmm':[sum(c['moment_Nmm'][i] for c in contributions) for i in range(3)],
                'area_mm2':sum(c['area_mm2'] for c in contributions),'reference_mm':reference,
                'measure':'support_stress_traction_integral','discrete_constraint_reaction':False,
                'contributions':contributions}
        else:
            row['stress_traction']={'status':'UNAVAILABLE','reason':'No complete native STRESS field at this frame'}
        result.append(row)
    return result


def derived_rotation(section, displacement, source_pins):
    """Infinitesimal unweighted rigid-section fit, never native rotational DOF.

    Return fit residuals and every input observation, not a hidden assumption of
    an exactly rigid section. Rank-deficient or incomplete sections are rejected.
    """
    import numpy as np
    nodes=section['expanded_node_ids']; points=section['positions_mm']
    if not set(nodes)<=set(displacement):
        raise ValueError('Derived section rotation requires every native displacement observation')
    xyz=np.asarray(points,dtype=float); u=np.asarray([_vec(displacement[n]) for n in nodes])
    center=xyz.mean(axis=0); length=float(np.max(np.linalg.norm(xyz-center,axis=1)))
    if not math.isfinite(length) or length<=0:
        raise ValueError('Degenerate rotation observation section')
    design=[]
    for r in (xyz-center)/length:
        x,y,z=r
        design.extend(((1,0,0,0,z,-y),(0,1,0,-z,0,x),(0,0,1,y,-x,0)))
    matrix=np.asarray(design,dtype=float)
    solution,_,rank,singular=np.linalg.lstsq(matrix,u.reshape(-1),rcond=1e-12)
    if rank!=6:
        raise ValueError('Section observations do not identify all six rigid-fit parameters')
    residual=(matrix@solution-u.reshape(-1)).reshape(-1,3)
    theta=solution[3:]/length
    return {'value_rad':theta.tolist(),'translation_at_centroid_mm':solution[:3].tolist(),
            'centroid_mm':center.tolist(),'frame':'FREECAD_DOCUMENT_GLOBAL',
            'measure':'derived_infinitesimal_rigid_section_rotation',
            'definition':'argmin sum_i ||u_i - t - theta cross (x_i-centroid)||^2; equal nodal weights',
            'native_generalized_rotation':False,'native_DOF':'UNAVAILABLE',
            'assumptions':'Infinitesimal kinematics; rigid-section projection, not an assertion of zero warping',
            'fit_rms_mm':float(np.sqrt(np.mean(np.sum(residual**2,axis=1)))),
            'fit_max_mm':float(np.max(np.linalg.norm(residual,axis=1))),
            'rank':int(rank),'scaled_condition_number':float(singular[0]/singular[-1]),
            'element_id':section['element_id'],'beam_node_id':section['beam_node_id'],
            'station_kind':section['station_kind'],'location':'observed_expanded_section',
            'expanded_node_ids':list(nodes),'positions_mm':deepcopy(points),
            'native_displacements_mm':u.tolist(),'source_pins':deepcopy(source_pins),
            'qualification':'DERIVED_NOT_NATIVE_DOF'}
