"""Populate the existing constitutive inspector from retained evidence only."""
from copy import deepcopy
from .storage import canonical_hash


def populate(view, result, settings, increment):
    records=result.get('diagnostics',{}).get('constitutive_increments',[])
    selected=next((row for row in records if row['increment']==increment),None)
    failure=result.get('diagnostics',{}).get('failed_increment')
    if selected is None and failure and failure['increment']==increment:
        evidence=failure.get('local_evidence') or {}
        selected=deepcopy(evidence.get('partial_response'))
    if selected is None:
        if failure and failure['increment']==increment:
            view.update(increments=[{'index':r['increment'],'time':r['time'],'unit':'s'} for r in records]+[
                {'index':increment,'time':failure['time'],'unit':'s','failed':True}],
                increment=increment,time=failure['time'],time_unit='s',tangent=None,components=[],
                state_initial=deepcopy(failure.get('last_accepted_state')),state_trial=None,state_committed=None,
                failure=deepcopy(failure),pair=result['diagnostics']['declaration']['tangent_pair'],
                tangent_unit=settings['stress_unit'],frame=settings.get('frame','material_cartesian'),unavailable=['Failed trial stress/tangent/state not produced; no zeros inferred'])
            evidence=failure.get('local_evidence') or {}
            partial=evidence.get('partial_stress_kelvin')
            if partial is not None:
                from .constitutive_inspection import quantity,SYMMETRIC6
                view['stress']=deepcopy(partial)
                view['quantities']=[quantity('실패 local trial 응력 · 수락 아님','infinitesimal_Cauchy_kelvin',
                    partial,SYMMETRIC6,settings['stress_unit'],'material_cartesian')]
                view['local_diagnostics']=deepcopy(evidence)
                view['unavailable']=['Failed trial tangent/committed state not produced; partial trial stress is retained']
            return view
        raise ValueError('Selected increment was not retained')
    if canonical_hash(selected['initial_state'])!=selected['initial_state_sha256']:
        raise ValueError('Retained accepted-state hash mismatch')
    from .constitutive_inspection import quantity, CARTESIAN9, SYMMETRIC6
    decl=result['diagnostics']['declaration']
    quantities=[quantity('응력',selected['stress_measure'],selected['stress_tensor'],CARTESIAN9,
                         selected['stress_unit'],selected['frame']),
                quantity('변형구배 F','deformation_gradient',selected['F'],CARTESIAN9,'1',selected['frame'])]
    if selected['strain_kelvin'] is not None:
        quantities.append(quantity('Kelvin 변형률','infinitesimal_strain_kelvin',selected['strain_kelvin'],
                                   SYMMETRIC6,'1',selected['frame']))
    from plugins.material_point import law_native as law
    if settings['model'] == law.dp.MODEL and selected['committed_state'] is not None:
        from .law_native_fe import dp_observables
        observed = dp_observables(selected['stress'], selected['committed_state'], settings['parameters'])
        for key, symbol, name, unit, measure in (
            ('pressure','p','압력 p (압축 양)',settings['stress_unit'],'minus_trace_Cauchy_over_3'),
            ('equivalent_stress','q','등가응력 q',settings['stress_unit'],'sqrt_3J2_Cauchy'),
            ('yield_function','f','항복함수 f (부호 포함)',settings['stress_unit'],'q_minus_alpha_p_minus_k0_minus_H_kappa'),
            ('plastic_volume_strain','tr(εᵖ)','소성 체적변형률','1','trace_infinitesimal_plastic_strain'),
            ('kappa','κ','누적 편차 소성변형률 κ','1','accumulated_equivalent_deviatoric_plastic_strain')):
            quantities.append(quantity(name, measure, [observed[key]], [symbol], unit, selected['frame'],
                origin='derived_from_retained_stress_and_committed_state'))
    failure=result['diagnostics'].get('failed_increment')
    view.update(increments=[{'index':r['increment'],'time':r['time'],'unit':'s'} for r in records]+(
            [{'index':failure['increment'],'time':failure['time'],'unit':'s','failed':True}] if failure else []),
        increment=increment,time=selected['time'],time_unit='s',stress=deepcopy(selected['stress']),
        strain=deepcopy(selected['F'] if selected['strain_kelvin'] is None else selected['strain_kelvin']),
        tangent=deepcopy(selected['tangent']),components=deepcopy(decl['components']),
        tangent_unit=selected['stress_unit'],pair=selected['tangent_pair'],frame=selected['frame'],
        tangent_kind='consistent_discrete',state_initial=deepcopy(selected['initial_state']),
        state_trial=deepcopy(selected['trial_state']),state_committed=deepcopy(selected['committed_state']),
        residual=selected['local'].get('local_residual'),substeps=None,
        local_diagnostics=deepcopy(selected['local']),quantities=[q for q in quantities if q is not None],
        finite_differences=probe_rows(selected.get('tangent_probe')),
        tangent_probe_report=deepcopy(selected.get('tangent_probe')),
        failure=deepcopy(failure) if failure and failure['increment']==increment else None,
        energy={'stored':selected['stored_energy'],'dissipated':selected['dissipated_energy'],
                'unit':selected['stress_unit'],'origin':'retained_constitutive_output'})
    if selected['tangent'] is None:view['unavailable'].append('Unique discrete tangent not available for this accepted state/step')
    if selected['local'].get('local_residual') is None:view['unavailable'].append('Local nonlinear residual not produced; not filled with zero')
    if selected['dissipated_energy'] is None:view['unavailable'].append('Dissipated energy was not produced')
    return view


def probe_rows(report):
    """Exact retained differences projected to the existing inspector table."""
    if not report:return []
    out=[]
    for row in report.get('rows',[]):
        columns=row['columns'];n=len(columns)
        matrix=[[c['finite_difference'][i] if c.get('finite_difference') is not None else None
                 for c in columns] for i in range(n)]
        out.append({'h':row['h'],'tangent':matrix,'columns':deepcopy(columns),
                    'initial_state':deepcopy(row['initial_state']),
                    'initial_state_sha256':row['initial_state_sha256']})
    return out


def selected_probe_rows(data,i,j):
    out=[]
    for row in data['finite_differences']:
        col=row['columns'][j];signed={}
        for sign,probe in col['probes'].items():
            signed[int(sign)]={'input':deepcopy(probe.get('actual_gradient')),
                'stress':deepcopy(probe.get('stress')),'initial_state':deepcopy(row['initial_state']),
                'initial_state_sha256':probe['initial_state_sha256'],
                'final_state':deepcopy(probe.get('trial_state')),
                'scheme':col['scheme'],'active_set':probe.get('active_set'),
                'column_status':col['status'],'error':probe.get('error')}
        def item(sign,key,index):
            v=signed.get(sign,{}).get(key)
            return v[index] if isinstance(v,list) and index<len(v) else None
        out.append({'h':row['h'],'minus_input':item(-1,'input',j),'plus_input':item(1,'input',j),
            'minus_stress':item(-1,'stress',i),'plus_stress':item(1,'stress',i),
            'difference':row['tangent'][i][j],'signed':signed,'scheme':col['scheme'],'status':col['status']})
    return out
