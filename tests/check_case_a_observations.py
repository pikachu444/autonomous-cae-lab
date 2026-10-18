"""Read exact retained Case A frames, with no interpolation or new jobs."""
import argparse
import json
from pathlib import Path
import sys
import threading
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from apps.lab.service import LabService
from apps.lab.server import LabHTTPServer
from caelab.workbench_client import Client
from caelab.storage import canonical_hash,save_json,load_json
from caelab.contact_deck import validate_model
from caelab.contact_steps import profile
from caelab.adapters.frozen_fem import read_frd
from caelab.law_native_fe import dp_observables
from plugins.material_point import law_native as law


def tensor(values):
    xx,yy,zz,xy,yz,zx=values
    return [[xx,xy,zx],[xy,yy,yz],[zx,yz,zz]]


def summary(stress,points,displacement,force):
    stress=np.asarray(stress,dtype=float)
    assert np.isfinite(stress).all()
    mean=stress.mean(axis=0);pq=[law.dp.invariants(law.kelvin(s)) for s in stress]
    mean_pq=law.dp.invariants(law.kelvin(mean))
    x=np.asarray(points)[:,0];u=np.asarray(displacement);f=np.asarray(force)
    left=x==0.;right=x==1.
    return dict(mean_Cauchy_MPa=mean.tolist(),component_min_MPa=stress.min(axis=0).tolist(),
        component_max_MPa=stress.max(axis=0).tolist(),sample_count=len(stress),
        mean_p_MPa=float(np.mean([p for p,q in pq])),mean_q_MPa=float(np.mean([q for p,q in pq])),
        p_of_mean_sigma_MPa=mean_pq[0],q_of_mean_sigma_MPa=mean_pq[1],
        gauge_axial_strain=float(u[right,0].mean()-u[left,0].mean()),
        xhi_signed_nominal_RFx_over_A0_MPa=float(f[right,0].sum()),
        nominal_measure='signed nodal RFx sum / original 1 mm^2; not full Cauchy tensor',
        roi_reduction='arithmetic sample mean and component extrema; not a volume integral')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execution',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    receipt=load_json(args.execution/'execution.json');store=Path(receipt['store'])
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02},daemon=True);thread.start()
    client=Client(f'http://127.0.0.1:{server.server_port}');records=[]
    try:
        jobs=client.request('/api/workbench')['jobs'];assert len(jobs)==10
        for name in ('tension_unload','compression_unload','transverse_strain_confinement'):
            dp=next(r for r in receipt['cases'] if r['name']==name+'_DP_FE')
            j2=next(r for r in receipt['cases'] if r['name']==name+'_J2_reduction_point')
            ccx=next(r for r in receipt['cases'] if r['name']==name+'_CCX_J2')
            dpdoc=client.document_open(kind='simulation',document_id=dp['document_id'])
            j2doc=client.document_open(kind='material',document_id=j2['document_id'])
            dpresult=client.document_result(dpdoc['id'],dp['job_id'])
            j2result=client.document_result(j2doc['id'],j2['job_id'])
            ccxresult=client.result(ccx['job_id'])
            assert canonical_hash(dpresult)==dp['result_sha256']
            assert canonical_hash(j2result)==j2['result_sha256']
            assert canonical_hash(ccxresult)==ccx['result_sha256']
            folder=store/'workbench'/'native'/ccx['job_id']
            model=load_json(folder/'frozen_input/mesh.json');nodes,elements,bodies=validate_model(model)
            materials={'names':['M1'],'elements':{e:'M1' for e in elements}}
            raw=read_frd(folder/'solver/contact.frd',nodes,elements,contact_materials=materials,
                contact_profile=profile(model),require_contact=False)
            frames=raw['frames'];steps=[]
            for index in (1,2,3):
                exact=[f for f in frames if f['static']['step']==index and f['static']['load_parameter']==float(index)]
                row=dict(stage=index,CCX_status='OBSERVED_EXACT' if len(exact)==1 else 'NOT_OBSERVED',
                    cross_solver_qualification='UNKNOWN',initial_CCX_zero='NOT_OBSERVED_NOT_FILLED')
                ds=next(s for s in dpresult['diagnostics']['steps'] if s['increment']==index)
                row['DP_FE']=summary([law.tensor(ip['stress']) for ip in ds['local']],
                    dpdoc['draft']['settings']['mesh']['points'],ds['displacement_mm'],ds['reaction_N'])
                row['DP_FE'].update(location='ACTUAL_GAUSS_INTEGRATION_POINTS',
                    identity=[dict(cell_index=ip['cell_index'],quadrature_index=ip['quadrature_index']) for ip in ds['local']],
                    plastic_volume_strain=[dp_observables(ip['stress'],ip['state'],dpdoc['draft']['settings']['law']['parameters'])['plastic_volume_strain'] for ip in ds['local']],
                    kappa=[ip['state']['kappa'] for ip in ds['local']],
                    same_law_FE_point=dpresult['diagnostics']['pair_comparison']['checks'][index])
                ps=next(s for s in j2result['diagnostics']['constitutive_increments'] if s['increment']==index)
                row['J2_reduction_point']=dict(Cauchy_MPa=ps['stress_tensor'],F=ps['F'],
                    kappa=ps['committed_state']['kappa'],plastic_volume_strain=sum(ps['committed_state']['plastic_strain_kelvin'][:3]))
                if len(exact)==1:
                    frame=exact[0];ids=sorted(nodes)
                    cs=summary([tensor(frame['fields']['STRESS'][n]) for n in ids],
                        [nodes[n] for n in ids],[frame['fields']['DISP'][n] for n in ids],
                        [frame['fields']['FORC'][n] for n in ids])
                    cs.update(location='CALCULIX_NODAL_EXTRAPOLATION_AND_AVERAGING',node_ids=ids,
                        native_step_increment=frame['static'],PEEQ=[frame['fields']['PE'][n][0] for n in ids],
                        plastic_volume_strain='UNAVAILABLE_PEEQ_IS_NOT_A_PLASTIC_STRAIN_TENSOR')
                    row['CCX_J2']=cs
                    row['raw_CCX_minus_J2point_Cauchy_MPa']=(np.asarray(cs['mean_Cauchy_MPa'])-np.asarray(ps['stress_tensor'])).tolist()
                    row['raw_DP_minus_CCX_Cauchy_MPa']=(np.asarray(row['DP_FE']['mean_Cauchy_MPa'])-np.asarray(cs['mean_Cauchy_MPa'])).tolist()
                steps.append(row)
            records.append(dict(name=name,role='withheld_synthetic_boundary_history' if name.startswith('transverse') else 'synthetic_comparison',
                DP=dp,J2_point=j2,CCX=ccx,post_input=ccxresult['post_input'],steps=steps))
            assert client.document_read(dpdoc['id'])==dpdoc and client.document_read(j2doc['id'])==j2doc
        assert client.request('/api/workbench')['jobs']==jobs
        report=dict(status='PASS_RETAINED_READ',cases=records,jobs_before=10,jobs_after=10,new_jobs=0,
            engineering_release='UNKNOWN/NOT_RELEASED',interpolation=False,cross_mesh_IP_mapping=False)
        save_json(args.output/'observations.json',report)
        print(json.dumps(dict(status=report['status'],new_jobs=0,exact_endpoints=sum(s['CCX_status']=='OBSERVED_EXACT' for c in records for s in c['steps'])),ensure_ascii=False))
    finally:
        server.shutdown();server.server_close();service.shutdown();thread.join(5)


if __name__=='__main__':main()
