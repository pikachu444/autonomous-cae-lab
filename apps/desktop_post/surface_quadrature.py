"""Reference quadratic surface area/field integration in native VTK order."""
import itertools
import math
import numpy as np
from caelab.quadratic_surface import shape, derivatives


def triangle_rule(high=False):
    if high:
        groups=[(.873821971016996,.063089014491502,.063089014491502,.050844906370207),
                (.501426509658179,.249286745170910,.249286745170910,.116786275726379),
                (.636502499121399,.310352451033785,.053145049844816,.082851075618374)]
    else:
        groups=[(1/3,1/3,1/3,.225),(.059715871789770,.470142064105115,.470142064105115,.132394152788506),
                (.797426985353087,.101286507323456,.101286507323456,.125939180544827)]
    return [(b,c,w/2) for a,b,c,w in groups for a,b,c in sorted(set(itertools.permutations((a,b,c))))]


def rule(kind, high=False):
    if kind==6:return triangle_rule(high)
    x,w=np.polynomial.legendre.leggauss(7 if high else 5)
    return [((a+1)/2,(b+1)/2,wa*wb/4) for a,wa in zip(x,w) for b,wb in zip(x,w)]


def integrate(coordinates, values):
    points=np.asarray(coordinates,dtype=float);kind=len(points)
    if points.shape not in ((6,3),(8,3)) or not np.isfinite(points).all():
        raise ValueError('TRI6/QUAD8의 실제 원 중간절점과 유한한 3D 기준 좌표가 필요합니다.')
    field=np.asarray(values,dtype=float)
    if field.shape not in ((),(kind,)) or not np.isfinite(field).all():
        raise ValueError('고차면의 원 점 성분 또는 원 owner 셀 상수가 필요합니다.')
    # Translation cancellation is avoided; derivatives sum to zero exactly
    # analytically, but absolute model origin is not part of the surface metric.
    points=points-points[0]
    checks=regularity(points)
    results=[]
    for high in (False,True):
        areas=[];weighted=[]
        for r,s,w in rule(kind,high):
            tangent=derivatives(kind,r,s)@points;cross=np.cross(tangent[0],tangent[1])
            jac=math.hypot(*cross)
            if not math.isfinite(jac) or jac<=0:raise ValueError('고차면의 Jacobian이 퇴화했거나 유한하지 않습니다.')
            value=float(field) if field.ndim==0 else float(shape(kind,r,s)@field)
            areas.append(w*jac);weighted.append(w*jac*value)
        area=math.fsum(areas);integral=math.fsum(weighted)
        if not math.isfinite(area) or area<=0 or not math.isfinite(integral):
            raise ValueError('고차면의 면적과 적분은 유한해야 하며 면적은 양수여야 합니다.')
        results.append((area,integral))
    primary,reference=results
    return {'area':primary[0],'integral':primary[1],'reference_area':reference[0],'reference_integral':reference[1],
        'value':primary[1]/primary[0], 'area_difference':abs(primary[0]-reference[0]),
        'integral_difference':abs(primary[1]-reference[1]),
        'mean_difference':abs(primary[1]/primary[0]-reference[1]/reference[0]),
        'rule':'TRI6_7' if kind==6 else 'QUAD8_5x5','reference_rule':'TRI6_12' if kind==6 else 'QUAD8_7x7',
        'geometry_checks':checks}


def regularity(points):
    """Conservative whole-domain injectivity certificate, not point sampling.

The derivative of the projected, affinely normalized map is polynomial. Its
Bernstein matrix coefficients bound ||Dg-I|| by convexity of the spectral norm.
A bound strictly below one certifies injectivity on the convex natural domain,
including its boundary. No shared/global normal is imposed on adjacent faces.
"""
    kind=len(points);corner=2 if kind==6 else 3
    first=points[1];normal=np.cross(first,points[corner])
    lengths=math.hypot(*first),math.hypot(*normal)
    if not all(math.isfinite(v) and v>0 for v in lengths):
        raise ValueError('고차면의 기준 corner 평면을 확인할 수 없습니다. 퇴화 또는 정규성 미확정 면은 측정하지 않습니다.')
    first=first/lengths[0];normal=normal/lengths[1]
    plane=np.array([first,np.cross(normal,first)])
    center=(1/3,1/3) if kind==6 else (.5,.5)
    affine=(derivatives(kind,*center)@points@plane.T).T
    try:inverse=np.linalg.inv(affine);condition=np.linalg.cond(affine)
    except np.linalg.LinAlgError:raise ValueError('고차면의 기준 투영이 퇴화했습니다. 면 순서·중간절점을 확인하세요.') from None
    def residual(r,s):
        return inverse@(derivatives(kind,r,s)@points@plane.T).T-np.eye(2)
    if kind==6:
        coefficients=np.array([residual(0,0),residual(1,0),residual(0,1)])
    else:
        values=np.array([[residual(r,s) for s in (0,.5,1)] for r in (0,.5,1)])
        inv_basis=np.array([[1.,0,0],[-.5,2,-.5],[0,0,1.]])
        coefficients=np.einsum('ai,bj,ijxy->abxy',inv_basis,inv_basis,values).reshape(-1,2,2)
    if not np.isfinite(coefficients).all() or not math.isfinite(condition):
        raise ValueError('고차면 정규성의 수치 범위를 확인할 수 없습니다.')
    bound=max(float(np.linalg.norm(matrix,2)) for matrix in coefficients)
    geometry_scale=float(np.linalg.norm(inverse,2))*max(math.hypot(*point) for point in points)
    margin=64*np.finfo(float).eps*(condition+geometry_scale)*max(1.,bound)
    if not math.isfinite(margin) or bound+margin>=1:
        raise ValueError('고차면의 정규성을 전 영역에서 확인하지 못했습니다. 접힘·중간절점 순서 또는 큰 overhang을 확인하세요. 정상 overhang도 이 보수적 graph 검증 밖일 수 있습니다.')
    return {'method':'affine_projection_contraction_bernstein','derivative_bound':bound,'roundoff_margin':margin,
            'status':'CERTIFIED_GRAPH_PATCH','engineering_qualification':'UNKNOWN'}
