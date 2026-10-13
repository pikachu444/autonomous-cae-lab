"""Fixed MGIS generic worker for an operator-admitted small-strain source."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import os


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):Path(path).write_text(json.dumps(value,allow_nan=False,sort_keys=True,indent=2),encoding='utf-8')


def describe(binding,b):
    def variables(name):
        return [{'name':v.name,'type':str(v.getType()),'size':int(binding.getVariableSize(v,b.hypothesis))}
                for v in getattr(b,name)]
    if (b.hypothesis!=binding.Hypothesis.Tridimensional or
        b.btype!=binding.BehaviourType.StandardStrainBasedBehaviour or
        b.kinematic!=binding.BehaviourKinematic.SmallStrainKinematic):
        raise ValueError('Only native standard small-strain Tridimensional behaviours are supported')
    d={key:str(getattr(b,key)) for key in ('behaviour','hypothesis','btype','kinematic','tfel_version','symmetry','build_id')}
    for key in ('gradients','thermodynamic_forces','material_properties','external_state_variables','internal_state_variables'):
        d[key]=variables(key)
    if ([v['size'] for v in d['gradients']]!=[6] or [v['size'] for v in d['thermodynamic_forces']]!=[6]):
        raise ValueError('The actual native strain/stress arrays are not Kelvin6')
    blocks=list(b.tangent_operator_blocks)
    if len(blocks)!=1 or blocks[0][0].name!=b.thermodynamic_forces[0].name or blocks[0][1].name!=b.gradients[0].name:
        raise ValueError('Expected exact stress/strain tangent block is absent')
    if any(v['size']!=1 for key in ('material_properties','external_state_variables') for v in d[key]):
        raise ValueError('This adapter requires explicitly declared scalar properties/external variables')
    d.update(pair='dσKelvin/dεKelvin',components=['xx','yy','zz','xy','xz','yz'],
        stress_unit='Pa (user declaration)',strain_unit='1',time_unit='s',
        computes_stored_energy=bool(b.computesStoredEnergy),computes_dissipated_energy=bool(b.computesDissipatedEnergy))
    return d


def integrate(binding,b,s,output):
    import numpy as np
    from native_helpers import _integrate
    properties={r['name']:r['value'] for r in s['properties']};external={r['name']:r['value'] for r in s['external']}
    buffers=['gradients','thermodynamic_forces']
    if b.internal_state_variables:buffers.append('internal_state_variables')
    if b.computesStoredEnergy:buffers.append('stored_energies')
    if b.computesDissipatedEnergy:buffers.append('dissipated_energies')
    def allocate():
        m=binding.MaterialDataManager(b,1);m.allocateArrayOfTangentOperatorBlocks()
        for state in (m.s0,m.s1):
            for name,value in properties.items():binding.setMaterialProperty(state,name,value)
            for name,value in external.items():binding.setExternalStateVariable(state,name,value)
            for name in buffers:getattr(state,name).reshape(-1)[:]=0.
        m.K.reshape(-1)[:]=0.
        return m
    def snapshot(m):
        return {**{key:{name:getattr(getattr(m,key),name).reshape(-1).tolist() for name in buffers} for key in ('s0','s1')},
            'K':m.K.reshape(-1).tolist(),'properties':deepcopy(properties),'external':deepcopy(external)}
    def restored(base):
        m=allocate()
        for key in ('s0','s1'):
            for name,values in base[key].items():
                array=getattr(getattr(m,key),name)
                if array.size!=len(values):raise ValueError('Native state shape changed')
                array.reshape(-1)[:]=values
        m.K.reshape(-1)[:]=base['K']
        if snapshot(m)!=base:raise ValueError('Independent state restoration differs')
        return m
    first=allocate();internal=s['initial_internal']
    count=int(binding.getArraySize(b.internal_state_variables,b.hypothesis)) if b.internal_state_variables else 0
    if count!=len(internal):raise ValueError('Explicit initial internal state differs from native descriptor')
    if count:
        for state in (first.s0,first.s1):state.internal_state_variables.reshape(-1)[:]=internal
    baseline=snapshot(first);steps=[];result={'steps':steps,'initial_state':baseline,'status':'SUCCEEDED'}
    scale=np.asarray([1.,1.,1.,math.sqrt(2),math.sqrt(2),math.sqrt(2)])
    for index,row in enumerate(s['history'][1:],1):
        dt=row['time']-s['history'][index-1]['time'];nominal=restored(baseline)
        initial=snapshot(nominal);nominal.s1.gradients[0,:]=np.asarray(row['strain'])*scale
        verdict=_integrate(binding,nominal,dt)
        record={'time_s':row['time'],'increment':index,'dt_s':dt,'initial_state':initial,**verdict,
            'finite_differences':[]}
        # A rejected native integration may leave nonfinite arrays. Preserve
        # the error and completed steps; do not project invalid arrays as zero.
        if verdict['integration_return']!=1:
            record['phase']='nominal rejected';steps.append(record);result['status']='FAILED'
            save(output/'history.partial.json',result);break
        record.update(strain_kelvin=nominal.s1.gradients.reshape(6).tolist(),
            stress_kelvin=nominal.s1.thermodynamic_forces.reshape(6).tolist(),
            tangent=nominal.K.reshape(6,6).tolist(),trial_state=snapshot(nominal))
        if index==s['probe']['increment']:
            col=['xx','yy','zz','xy','xz','yz'].index(s['probe']['component'])
            for h in s['probe']['steps']:
                signed={};evidence=[]
                for sign in (-1,1):
                    probe=restored(baseline);start=snapshot(probe)
                    probe.s1.gradients[0,:]=nominal.s1.gradients[0,:];probe.s1.gradients[0,col]+=sign*h
                    status=_integrate(binding,probe,dt)
                    item={'sign':sign,'initial_state':start,**status}
                    if status['integration_return']==1:
                        item['state']=snapshot(probe);signed[sign]=probe.s1.thermodynamic_forces.reshape(6).copy()
                    evidence.append(item)
                fd={'h':h,'component':s['probe']['component'],'probes':evidence}
                if len(signed)==2:fd['column_values']=((signed[1]-signed[-1])/(2*h)).tolist()
                record['finite_differences'].append(fd)
                if len(signed)!=2:
                    result['status']='FAILED';record['phase']='independent probe rejected';break
        if snapshot(nominal)!=record['trial_state']:raise ValueError('Independent probes mutated nominal state')
        if result['status']=='FAILED':
            steps.append(record);save(output/'history.partial.json',result);break
        binding.update(nominal);record['committed_state']=snapshot(nominal);baseline=snapshot(nominal)
        steps.append(record);save(output/'history.partial.json',result)
    return result


def main():
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,)*2)
    resource.setrlimit(resource.RLIMIT_CPU,(240,240))
    resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,)*2)
    os.umask(0o077)
    out=Path('/work');sys.path.insert(0,str(out));sys.dont_write_bytecode=True
    pins=json.loads((out/'sources.json').read_text(encoding='utf-8'))
    if any(Path(name).name!=name or sha(out/name)!=digest for name,digest in pins.items()):raise ValueError('Captured worker source changed')
    from user_material import validate_settings,source_hash
    from native_helpers import _executable,_command,portable_compiler_flags,MGIS_PREFIX,installed_package_identity
    s=validate_settings(json.loads((out/'input.json').read_text(encoding='utf-8')))
    admission=json.loads((out/'admission.json').read_text(encoding='utf-8'))
    if admission['source_sha256']!=source_hash(s['source']):raise ValueError('Admitted source changed')
    build=out/'build';build.mkdir()
    source=build/(s['behaviour']+'.mfront');source.write_bytes(s['source'].encode('utf-8'))
    config=_executable('tfel-config');mfront=_executable('mfront');make=_executable('make');compiler=_executable('g++')
    runtime={'tfel':_command([config,'--version'],out,'tfel_version',10),
             'mfront':_command([mfront,'--version'],out,'mfront_version',10),
             'compiler':_command([compiler,'--version'],out,'compiler_version',10)}
    if not runtime['tfel'].startswith('tfel-config 5.0.0'):raise ValueError('Expected existing TFEL5 runtime')
    flags=portable_compiler_flags(_command([config,'--oflags0'],out,'oflags',10),
          _command([config,'--cppflags','--compiler-flags'],out,'cppflags',10),
          _command([config,'--include-path'],out,'include',10))
    argv=[mfront,'--omake','--interface=generic','--@SelectedModellingHypothesis=Tridimensional',source.name]
    _command(argv,build,'generate')
    log=_command([make,'-C','src','-f','Makefile.mfront','-j1','--trace','CXX='+compiler,
                  'CXXFLAGS='+__import__('shlex').join(flags)],build,'compile')
    commands=[line for line in log.splitlines() if compiler in line and any(token in line for token in (' -c',' -shared'))]
    if not commands:raise ValueError('Actual compiler command evidence is absent')
    library=build/'src/libBehaviour.so'
    import mgis.behaviour as binding
    package=installed_package_identity(MGIS_PREFIX,'mgis','3.0',binding.__file__,out)
    runtime.update(mgis=package)
    b=binding.load(str(library),s['behaviour'],binding.Hypothesis.Tridimensional)
    descriptor=describe(binding,b)
    for key,native in [('properties','material_properties'),('external','external_state_variables')]:
        if {row['name'] for row in s[key]}!={row['name'] for row in descriptor[native]}:raise ValueError('Declared '+key+' differ from native descriptor')
    receipt={'source_sha256':sha(source),'library_sha256':sha(library),'makefile_sha256':sha(build/'src/Makefile.mfront'),
             'interface':'generic','hypothesis':'Tridimensional','generation_arguments':argv,
             'compiler_flags':flags,'compiler_commands':commands,'runtime':runtime,'descriptor':descriptor}
    save(out/'build_identity.json',receipt)
    history=integrate(binding,b,s,out) if s['action']=='evaluate' else {'steps':[],'status':'BUILT_ONLY'}
    save(out/'user_result.json',{'input_sha256':sha(out/'input.json'),'sources_sha256':sha(out/'sources.json'),
        'build':receipt,'constitutive':history,'source_sha256':sha(source),'library_sha256':sha(library)})


if __name__=='__main__':main()
