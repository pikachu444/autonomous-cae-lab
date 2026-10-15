"""Independent scalar p-q and analytic energy expectations, never production update.

Synthetic proportional monotonic paths from zero accepted state. This oracle is
not used by either the point integrator or spatial FE worker.
"""
from copy import deepcopy
import numpy as np
from plugins.material_point.law_native import default_settings


def dp_scalar_reference(parameters,strain):
    p=parameters;E,nu=p['E'],p['nu'];G=E/(2*(1+nu));K=E/(3*(1-2*nu))
    e=np.asarray(strain,dtype=float);dev=e-np.trace(e)*np.eye(3)/3
    st=2*G*dev;pt=-K*np.trace(e);qt=float(np.sqrt(1.5*np.sum(st*st)))
    f=qt-p['alpha']*pt-p['k0'];gamma=max(0.,f/(3*G+p['alpha']*K*p['beta']+p['H']))
    if qt-3*G*gamma<0:raise ValueError('This independent smooth-cone oracle excludes apex')
    stress=(1-3*G*gamma/qt)*st if qt else st.copy()
    stress-=(pt+K*p['beta']*gamma)*np.eye(3)
    return {'stress_tensor_mpa':stress.tolist(),'p_mpa':float(-np.trace(stress)/3),
            'q_mpa':max(0.,qt-3*G*gamma),'kappa':gamma,'reference':'Independent physical tensor Hooke + scalar p-q closed form'}


def protocols():
    out=[]
    for name,role,end,response in [
        ('tension','fit',np.diag([.005,0,0]),'xx'),
        ('shear','fit',np.array([[0,.006,0],[.006,0,0],[0,0,0]]),'xy'),
        ('compression','holdout',np.diag([-.007,0,0]),'xx'),
        ('confined_deviatoric','holdout',np.diag([-.003,-.012,-.012]),'xx')]:
        s=default_settings();a=[0.,.3,.7,1.];s['time']=[0.,1.,2.,3.]
        s['deformation_gradient']=[(np.eye(3)+v*end).tolist() for v in a]
        expected=[dp_scalar_reference(s['parameters'],v*end) for v in a]
        i,j=('xyz'.index(c) for c in response)
        out.append({'id':name,'role':role,'settings':s,'response':'stress_'+response,'component':response,
                    'expected':expected,'observations':[v['stress_tensor_mpa'][i][j] for v in expected],
                    'source_kind':'SYNTHETIC_ANALYTICAL_REFERENCE','physical_measurement':False})
    return out


def neo_reference(F,mu,lmbda):
    F=np.asarray(F);J=np.linalg.det(F)
    if J<=0:raise ValueError('det F must be positive')
    A=np.linalg.inv(F).T;P=mu*F+(lmbda*np.log(J)-mu)*A
    C=np.zeros((3,3,3,3))
    for i in range(3):
        for Jj in range(3):
            for k in range(3):
                for L in range(3):
                    C[i,Jj,k,L]=(mu*(i==k)*(Jj==L)+lmbda*A[i,Jj]*A[k,L]
                                +(mu-lmbda*np.log(J))*A[i,L]*A[k,Jj])
    return {'P':P.tolist(),'DP_DF':C.reshape(9,9).tolist(),
            'Cauchy':(P@F.T/J).tolist(),'raw_energy':float(mu*(np.sum(F*F)/2-np.log(J))+lmbda*np.log(J)**2/2),
            'note':'Raw FELUPE energy gauge: psi(I)=3 mu/2; do not silently subtract'}
