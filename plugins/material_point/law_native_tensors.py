"""Explicit Kelvin-6 / physical-9 mappings for the law-native interface.

Symmetric order is xx, yy, zz, sqrt(2)xy, sqrt(2)xz, sqrt(2)yz.
Physical nine is row-major xx,xy,xz,yx,yy,yz,zx,zy,zz. No engineering shear.
"""
import numpy as np

K6 = ('xx', 'yy', 'zz', 'xy', 'xz', 'yz')
F9 = tuple(a+b for a in 'xyz' for b in 'xyz')
I6 = np.array([1., 1., 1., 0., 0., 0.])
DEV = np.eye(6) - np.outer(I6, I6)/3
BASIS = np.zeros((6, 3, 3))
for a, (i, j) in enumerate(((0,0),(1,1),(2,2),(0,1),(0,2),(1,2))):
    BASIS[a,i,j] = BASIS[a,j,i] = 1. if i == j else 1/np.sqrt(2.)


def finite(value, shape, name):
    raw = np.asarray(value, dtype=object)
    if raw.shape != shape or any(isinstance(x, (bool, np.bool_)) or
            not isinstance(x, (int, float, np.integer, np.floating)) for x in raw.flat):
        raise ValueError(f'{name}: require finite numeric shape {shape}; no text/bool')
    array = np.asarray(value, dtype=float)
    if not np.isfinite(array).all():
        raise ValueError(name + ': nonfinite value')
    return array.copy()


def kelvin(tensor):
    tensor = np.asarray(tensor, dtype=float)
    return np.einsum('aij,ij...->a...', BASIS, tensor)


def tensor(vector):
    return np.einsum('aij,a...->ij...', BASIS, np.asarray(vector, dtype=float))


def fourth(matrix):
    return np.einsum('aij,ab...,bkl->ijkl...', BASIS, np.asarray(matrix), BASIS)


def stiffness(bulk, shear):
    return bulk*np.outer(I6, I6) + 2*shear*DEV


def compliance(stress, bulk, shear):
    stress = np.asarray(stress)
    return DEV@stress/(2*shear) + I6*(I6@stress)/(9*bulk)


def moduli(E, nu):
    return E/(3*(1-2*nu)), E/(2*(1+nu))
