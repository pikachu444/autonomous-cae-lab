"""Reference quadratic surface area/field integration in native VTK order."""
import itertools
import math
import numpy as np
from caelab.quadratic_surface import shape, derivatives, regularity


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
