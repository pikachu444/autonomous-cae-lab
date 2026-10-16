"""VTK-order quadratic face shapes, in unit natural coordinates.

TRI6: (0,1,2,01,12,20), r>=0,s>=0,r+s<=1.
QUAD8: (0,1,2,3,01,12,23,30), 0<=r,s<=1.
Derivatives have shape (2, nodes), rows d/dr and d/ds.
No native owner, interpolation fallback, inverse mapping or data storage.
"""
import numpy as np


def tri6_shape(r, s):
    a=1-r-s
    return np.array([a*(2*a-1),r*(2*r-1),s*(2*s-1),4*a*r,4*r*s,4*s*a])


def tri6_derivatives(r, s):
    a=1-r-s
    return np.array([[-4*a+1,4*r-1,0,4*(a-r),4*s,-4*s],
                     [-4*a+1,0,4*s-1,-4*r,4*r,4*(a-s)]])


def quad8_shape(r, s):
    x,y=2*r-1,2*s-1
    corners=[.25*(1+a*x)*(1+b*y)*(a*x+b*y-1) for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    return np.array(corners+[.5*(1-x*x)*(1-y),.5*(1+x)*(1-y*y),.5*(1-x*x)*(1+y),.5*(1-x)*(1-y*y)])


def quad8_derivatives(r, s):
    x,y=2*r-1,2*s-1
    dr=[.5*a*(1+b*y)*(2*a*x+b*y) for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    ds=[.5*b*(1+a*x)*(a*x+2*b*y) for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]]
    return np.array([dr+[-2*x*(1-y),1-y*y,-2*x*(1+y),-(1-y*y)],
                     ds+[-(1-x*x),-2*(1+x)*y,1-x*x,-2*(1-x)*y]])


def shape(kind, r, s):
    return {6:tri6_shape,8:quad8_shape}[kind](r,s)


def derivatives(kind, r, s):
    return {6:tri6_derivatives,8:quad8_derivatives}[kind](r,s)
