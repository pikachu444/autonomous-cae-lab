"""Explicit material declarations shared by point, fit and the FELUPE FE pair.

No solver, compiler, provider or owner is imported during editing/validation.
Existing FELUPE, MFront/SVK, J2 and native Maxwell inputs remain unchanged.
"""
from copy import deepcopy
import math
import numpy as np
from . import drucker_prager as dp, single_branch_native as sls
from .law_native_tensors import finite, kelvin, tensor, fourth, stiffness, compliance, K6, F9

POINT = 'material.law_native'
FE = 'structure.felupe.law_native'
MODELS = (dp.MODEL, 'neo_hooke', 'single_branch_maxwell')
STRESS_TO_MPA = {'Pa': 1e-6, 'kPa': 1e-3, 'MPa': 1., 'GPa': 1e3}
FELUPE_VERSION = '11.1.3'
FRAME = 'material_cartesian'
BOUNDARY_OPTIONS = {'atol':1e-8, 'rtol':1e-10, 'max_iterations':40, 'max_backtracks':20}


def parameter_unit(model, name, stress_unit):
    return '1' if name in ('nu','alpha','beta') else 's' if name == 'tau' else stress_unit


def validate_parameters(model, p):
    if model == dp.MODEL:
        return dp.validate_parameters(p)
    if model == 'single_branch_maxwell':
        return sls.validate_parameters(p)
    if model == 'neo_hooke':
        if not isinstance(p,dict) or set(p) != {'mu','lmbda'}:
            raise ValueError('NeoHookeCompressible requires mu and lmbda; no bulk-energy substitution')
        mu, la = finite([p['mu'],p['lmbda']],(2,),'Neo-Hooke coefficients')
        if mu <= 0 or la+2*mu/3 <= 0:
            raise ValueError('Neo-Hooke shear and small-strain bulk modulus must be positive')
        return {'mu':float(mu),'lmbda':float(la)}
    raise ValueError('Choose an explicit law-native model')


def default_settings(model=dp.MODEL):
    if model not in MODELS:
        raise ValueError('Unknown law-native model')
    parameters = ({'E':210000.,'nu':.3,'alpha':.2,'beta':.05,'k0':250.,'H':1000.}
                  if model == dp.MODEL else {'mu':30.,'lmbda':50.} if model == 'neo_hooke'
                  else {'K0':1000.,'G0':500.,'K1':2000.,'G1':1000.,'tau':1.})
    initial = (dp.state() if model == dp.MODEL else sls.state() if model == 'single_branch_maxwell'
               else {'time':0.,'deformation_gradient':np.eye(3).tolist()})
    return {'model':model,'stress_unit':'MPa','time_unit':'s','parameters':parameters,
            'time':[0.,1.,2.,3.], 'deformation_gradient':[(np.eye(3)+np.diag([e,0,0])).tolist()
              for e in (0.,.001,.006,.002)],'initial_state':initial}


def validate_settings(settings):
    required = {'model','parameters','stress_unit','time_unit','time','deformation_gradient','initial_state'}
    if not isinstance(settings,dict) or not required <= set(settings) or set(settings)-required-{'boundary_control','tangent_probe'}:
        raise ValueError('Law-native requires model, parameters, units, time/F and explicit initial_state')
    s = deepcopy(settings)
    model = s['model']
    p = validate_parameters(model,s['parameters'])
    if s['stress_unit'] not in STRESS_TO_MPA or s['time_unit'] != 's':
        raise ValueError('Explicit Pa/kPa/MPa/GPa and physical seconds are required')
    # Bounds expressed in MPa and seconds, not arbitrary raw-unit bounds.
    for name,value in p.items():
        unit = parameter_unit(model,name,s['stress_unit'])
        if unit not in ('1','s') and abs(value)*STRESS_TO_MPA[unit] > 1e9:
            raise ValueError(name+': exceeds admitted 1e9 MPa scale')
    if model == 'single_branch_maxwell':
        if not 1e-6 <= p['tau'] <= 1e6:
            raise ValueError('SLS tau requires [1e-6,1e6] s')
        if any(p[k]*STRESS_TO_MPA[s['stress_unit']]<1e-6 for k in ('K0','G0','K1','G1')):
            raise ValueError('SLS moduli require [1e-6,1e9] MPa, retaining the original envelope')
    if not isinstance(s['time'],list) or not 2 <= len(s['time']) <= 256:
        raise ValueError('History requires 2..256 states')
    times = finite(s['time'],(len(s['time']),),'time')
    gradients = finite(s['deformation_gradient'],(len(times),3,3),'F history')
    if min(times) < 0 or max(times)>1e6 or np.any(np.diff(times)<=0):
        raise ValueError('Physical times must increase strictly within [0,1e6] s')
    for F in gradients:
        if np.linalg.det(F)<=0:
            raise ValueError('Nonpositive det(F) is not admissible')
        if model == 'neo_hooke':
            stretches=np.linalg.svd(F,compute_uv=False)
            if min(stretches)<.5 or max(stretches)>2:
                raise ValueError('This Neo-Hooke FE pair is bounded to principal stretches [0.5,2]')
        elif model == 'single_branch_maxwell' and np.max(abs(tensor(kelvin(F-np.eye(3)))))>.01+8*np.finfo(float).eps:
            raise ValueError('SLS physical strain components must remain within [-.01,.01]')
        elif max(abs(kelvin(F-np.eye(3)))) > .05 or np.linalg.norm(F-F.T)> .15:
            raise ValueError('Small-strain law outside the declared strain/rotation envelope')
    initial = s['initial_state']
    if model == 'neo_hooke':
        if not isinstance(initial,dict) or set(initial)!={'time','deformation_gradient'}:
            raise ValueError('Neo-Hooke is stateless: initial time and F, not plastic/viscous variables')
        finite([initial['time']],(1,),'initial time')
        F0=finite(initial['deformation_gradient'],(3,3),'initial F')
        if not np.array_equal(F0,gradients[0]):
            raise ValueError('First F must exactly equal accepted initial F')
    else:
        (dp if model==dp.MODEL else sls).validate_state(initial)
        if not np.allclose(kelvin(gradients[0]-np.eye(3)),initial['strain_kelvin'],rtol=0,atol=2e-16):
            raise ValueError('First F/strain differs from the explicitly accepted initial state')
    if initial['time'] != times[0]:
        raise ValueError('First history time must equal accepted initial time')
    bc=s.get('boundary_control')
    if bc is not None:
        if not isinstance(bc,dict) or set(bc)!={'stress_components','solver'}:
            raise ValueError('Boundary control requires stress_components and explicit solver options')
        if not isinstance(bc['stress_components'],dict) or not bc['stress_components'] or set(bc['stress_components'])-set(K6):
            raise ValueError('Use distinct physical xx/yy/zz/xy/xz/yz stress controls')
        for name,values in bc['stress_components'].items():
            finite(values,(len(times),),'controlled '+name)
        opts=bc['solver']
        if not isinstance(opts,dict) or set(opts)!=set(BOUNDARY_OPTIONS):
            raise ValueError('Boundary solver requires fixed atol,rtol,max_iterations,max_backtracks')
        if not (0<float(finite([opts['atol']],(1,),'atol')[0])<=1 and
                0<=float(finite([opts['rtol']],(1,),'rtol')[0])<=1e-5):
            raise ValueError('Invalid boundary residual tolerance')
        for key,maximum in (('max_iterations',80),('max_backtracks',32)):
            if type(opts[key]) is not int or not 1<=opts[key]<=maximum:
                raise ValueError('Invalid '+key)
    probe=s.get('tangent_probe')
    if probe is not None:
        if (not isinstance(probe,dict) or set(probe)!={'increment','steps'}
                or type(probe['increment']) is not int or not 1<=probe['increment']<len(times)
                or not isinstance(probe['steps'],list) or not 1<=len(probe['steps'])<=5):
            raise ValueError('Probe requires one noninitial increment and 1..5 positive steps')
        hs=finite(probe['steps'],(len(probe['steps']),),'probe steps')
        if min(hs)<=0 or max(hs)>.001:
            raise ValueError('Probe h must be in (0,.001]')
    return s


def describe_inputs(settings):
    s=validate_settings(settings)
    result=[]
    labels={'E':'탄성계수','nu':'푸아송비','alpha':'압력 계수 α','beta':'팽창 계수 β',
        'k0':'초기 항복 절편','H':'등방 경화 계수','mu':'전단계수 μ','lmbda':'Lamé 계수 λ',
        'K0':'평형 체적계수','G0':'평형 전단계수','K1':'branch 체적계수',
        'G1':'branch 전단계수','tau':'완화시간'}
    for name,value in s['parameters'].items():
        lo,hi= ((-.9,.49) if name=='nu' else (0.,1.) if name in ('alpha','beta') else
                (value*.1,value*10) if value>0 else (0.,max(1.,s['parameters'].get('E',1.)*.01)))
        result.append({'id':name,'label':labels[name],'unit':parameter_unit(s['model'],name,s['stress_unit']),
            'value':value,'lower':lo,'upper':hi,'path':['parameters',name],
            'role':'coefficient','kind':'continuous','default_free':name not in ('E','nu','beta'),
            'meaning':'Direct coefficient; no implicit angle/cohesion conversion'})
    return result


def bind_inputs(settings, values):
    s=validate_settings(settings)
    if not isinstance(values,dict) or set(values)-set(s['parameters']):
        raise ValueError('Only explicitly declared coefficients can be bound')
    s['parameters'].update(deepcopy(values))
    return validate_settings(s)


def declaration(settings):
    s=validate_settings(settings)
    finite_strain=s['model']=='neo_hooke'
    return {'law':s['model'],'variant':dp.VARIANT if s['model']==dp.MODEL else
                'FELUPE-NeoHookeCompressible-logJ/1' if finite_strain else 'SLS-bulk-shear-exact-ramp/1',
        'stress_measure':'first_Piola' if finite_strain else 'infinitesimal_Cauchy',
        'gradient_measure':'deformation_gradient' if finite_strain else 'infinitesimal_strain_kelvin',
        'tangent_pair':'DP_DF_physical9' if finite_strain else 'DsigmaK_DepsilonK',
        'tangent_kind':'consistent_discrete','components':list(F9 if finite_strain else K6),
        'shear':'physical9' if finite_strain else 'Kelvin sqrt(2), not engineering shear',
        'frame':FRAME,'stress_unit':s['stress_unit'],'time_unit':'s',
        'rate_dependence':s['model']=='single_branch_maxwell','initial_state':deepcopy(s['initial_state']),
        'pressure_sign':'compression_positive' if s['model']==dp.MODEL else None,
        'physical_calibration':'UNKNOWN','strength':'UNKNOWN','engineering_release':'UNKNOWN'}


def neo_response(parameters, F, time):
    import felupe
    if felupe.__version__ != FELUPE_VERSION:
        raise ValueError('This pair requires FELUPE '+FELUPE_VERSION+'; runtime upgrade needs separate validation')
    F=finite(F,(3,3),'F')
    if np.linalg.det(F)<=0 or min(np.linalg.svd(F,compute_uv=False))<.5 or max(np.linalg.svd(F,compute_uv=False))>2:
        raise ValueError('Neo-Hooke F outside pair envelope')
    material=felupe.NeoHookeCompressible(**parameters)
    x=[F[:,:,None,None],np.zeros((0,1,1))]
    P=np.asarray(material.gradient(x)[0])[:,:,0,0]
    C=np.asarray(material.hessian(x)[0]).reshape(9,9)
    energy=float(np.asarray(material.function(x)[0]).reshape(-1)[0])
    return {'stress':P,'tangent':C,'state':{'time':float(time),'deformation_gradient':F.tolist()},
        'stored_energy':energy,'dissipated_energy':0.,
        'diagnostics':{'active_set':'hyperelastic','differentiable':True,'tangent_kind':'consistent_discrete',
            'cauchy':(P@F.T/np.linalg.det(F)).tolist(),'J':float(np.linalg.det(F)),
            'energy_zero':'FELUPE raw energy: psi(I)=3*mu/2 (not shifted)', 'committed':False}}


def update(settings, initial, F, time):
    if settings['model']=='neo_hooke':
        return neo_response(settings['parameters'],F,time)
    return (dp if settings['model']==dp.MODEL else sls).integrate(settings['parameters'],
        initial,kelvin(np.asarray(F)-np.eye(3)),time)


def initial_response(s):
    initial=deepcopy(s['initial_state'])
    if s['model']=='neo_hooke':
        return neo_response(s['parameters'],s['deformation_gradient'][0],s['time'][0])
    if s['model']==dp.MODEL:
        result=dp.integrate(s['parameters'],initial,initial['strain_kelvin'],initial['time'])
        if result['state']['plastic_strain_kelvin'] != initial['plastic_strain_kelvin'] or result['state']['kappa'] != initial['kappa']:
            raise ValueError('Initial DP state lies outside yield surface; no silent initial return')
        return result
    p=s['parameters'];e=np.asarray(initial['strain_kelvin']);ev=np.asarray(initial['viscous_strain_kelvin'])
    C0,C1=stiffness(p['K0'],p['G0']),stiffness(p['K1'],p['G1'])
    q=C1@(e-ev)
    return {'stress':C0@e+q,'tangent':None,'state':initial,
        'stored_energy':float(.5*e@C0@e+.5*q@compliance(q,p['K1'],p['G1'])),
        'dissipated_energy':initial['dissipated_energy'],
        'diagnostics':{'active_set':'initial','differentiable':False,'tangent_kind':'unavailable_no_dt',
            'branch_stress_kelvin':q.tolist(),'local_residual':None,'committed':False}}


def physical_response(s, result):
    if s['model']=='neo_hooke':
        return np.asarray(result['stress']),None if result['tangent'] is None else np.asarray(result['tangent']).reshape(3,3,3,3)
    return tensor(result['stress']),None if result['tangent'] is None else fourth(result['tangent'])


def from_saved_legacy(draft):
    """Exact explicit mapping of legacy supported models; original draft is never edited."""
    backend,old=draft['backend'],deepcopy(draft['settings'])
    if backend==POINT:
        return validate_settings(old)
    if backend=='material.felupe' and old.get('model')=='neo_hooke':
        s=deepcopy(old)
        if 'tangent_probe' in s:
            old_probe=s['tangent_probe'];s['tangent_probe']={'increment':old_probe['increment'],'steps':old_probe['steps']}
        if 'boundary_control' in s:
            b=s['boundary_control']
            if b.get('stress_measure')!='first_Piola' or b.get('frame')!=FRAME:
                raise ValueError('Legacy Neo-Hooke boundary pair/frame is not explicit first Piola')
            s['boundary_control']={k:deepcopy(b[k]) for k in ('stress_components','solver')}
        s['initial_state']={'time':s['time'][0],'deformation_gradient':deepcopy(s['deformation_gradient'][0])}
        return validate_settings(s)
    if backend=='material.mfront.viscoelastic':
        from . import viscoelastic_reference as reference
        old=reference.validate_settings(old) # preserves original canonical admission/limits
        s=default_settings('single_branch_maxwell')
        s['parameters']=dict(zip(sls.KEYS,[old['material'][k] for k in reference.MATERIAL_KEYS]))
        s['time']=[r['time_s'] for r in old['history']]
        s['deformation_gradient']=[(np.eye(3)+tensor(np.asarray(r['strain'])*np.array([1,1,1,np.sqrt(2),np.sqrt(2),np.sqrt(2)]))).tolist() for r in old['history']]
        return validate_settings(s)
    raise ValueError('No exact pair mapping: SVK/J2/user source are not renamed Neo-Hooke/DP/SLS')
