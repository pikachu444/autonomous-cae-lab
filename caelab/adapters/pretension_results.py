"""Pinned 2.22 SOF and RP U/RF, without inventing missing section forces.

SOF is the native extrapolated-stress section integral. RP RF1 is retained
separately and is not assumed equal to SOF in CalculiX 2.22.
"""
from copy import deepcopy
import math,re
from pathlib import Path
from ..pretension import sections,expected_solver_mesh
from ..contact_steps import axis,step_location
from .fixture_field import _printed_close
from .frozen_fem import _read


def solver_mesh(model,nodes,elements):
    if not model.get('pretension_sections'):return model,nodes,elements,[]
    effective,copies=expected_solver_mesh(model)
    return effective,{r['node_id']:r['position_mm'] for r in effective['nodes']},\
        {r['element_id']:r['node_ids'] for r in effective['elements']},copies


def read(path,model,frames,*,prefix=False):
    requested=sections(model)
    if not requested:return []
    from ..dynamic_native_stream import frame_catalog
    catalog=list(frame_catalog(frames));lines=_read(Path(path)).decode('ascii').splitlines()
    surfaces={r['surface_name'].upper():r for r in requested}
    sets={r['reference_set'].upper():r for r in requested}
    surface_header=re.compile(r'^\s*statistics for surface set (\S+) and time\s+(\S+)\s*$')
    node_header=re.compile(r'^\s*(displacements \(vx,vy,vz\)|forces \(fx,fy,fz\)) for set (\S+) and time\s+(\S+)\s*$')
    rows={};seen=set()
    def frame(token):
        try:value=float(token.replace('D','E'))
        except ValueError:raise ValueError('체결 출력의 native 단계 시각이 손상됐습니다.')
        if not math.isfinite(value):raise ValueError('체결 출력 시각이 유한하지 않습니다.')
        matches=[f for f in catalog if _printed_close(token,f['static']['load_parameter'])]
        if not matches and prefix and catalog and value>max(f['static']['load_parameter'] for f in catalog):return None
        if len(matches)!=1:raise ValueError('체결 DAT 시각을 실제 FRD 단계·증분에 유일하게 대응할 수 없습니다.')
        return matches[0]
    def row_for(section,f,quantity):
        key=(section['id'],f['static']['step'],f['static']['increment']);unique=(*key,quantity)
        if unique in seen:raise ValueError('체결 출력이 같은 절단면·단계·증분에서 중복됐습니다.')
        seen.add(unique)
        return rows.setdefault(key,{'section_id':section['id'],'label':section['draft']['label'],
            'static':deepcopy(f['static']),'step_location':step_location(model,f['static']['step'],f['static']['load_parameter']),
            'axis':deepcopy(section['draft']['axis']),'raw':{},'quality_reasons':[]})
    def nonblank(i):
        while i<len(lines) and not lines[i].strip():i+=1
        if i>=len(lines):raise ValueError('체결 DAT 출력 블록이 끝나지 않았습니다.')
        return i
    def numbers(i,count,row):
        i=nonblank(i);tokens=lines[i].split()
        if len(tokens)!=count:raise ValueError('체결 DAT 숫자 행의 성분 수가 다릅니다.')
        values=[]
        for token in tokens:
            try:v=float(token.replace('D','E'))
            except ValueError:v=math.nan
            values.append(v if math.isfinite(v) else None)
            if not math.isfinite(v):row['quality_reasons'].append('native_nonfinite_or_overflow:'+token)
        return i+1,values,tokens
    headings=(('total surface force (fx,fy,fz) and moment about the origin(mx,my,mz)',6),
              ('center of gravity and mean normal',6),('moment about the center of gravity(mx,my,mz)',3),
              ('area, normal force (+ = tension), shear force(size), torque and bending moment (size)',5))
    i=0
    while i<len(lines):
        line=lines[i];i+=1;match=surface_header.fullmatch(line)
        if match and match[1] in surfaces:
            section=surfaces[match[1]];f=frame(match[2])
            if f is None:continue
            row=row_for(section,f,'SOF');values=[];tokens=[]
            for heading,count in headings:
                i=nonblank(i)
                if ''.join(lines[i].split())!=''.join(heading.split()):raise ValueError('체결 SOF native 출력 표제가 다르거나 누락됐습니다.')
                i,v,t=numbers(i+1,count,row);values.append(v);tokens.append(t)
            row.update(force_global_N=values[0][:3],moment_origin_Nmm=values[0][3:],
                center_of_gravity_mm=values[1][:3],mean_normal=values[1][3:],moment_cog_Nmm=values[2],
                area_mm2=values[3][0],native_normal_force_N=values[3][1],shear_size_N=values[3][2],
                torque_Nmm=values[3][3],bending_size_Nmm=values[3][4])
            row['axial_force_N']=sum(v*a for v,a in zip(row['force_global_N'],row['axis'])) if all(v is not None for v in row['force_global_N']) else None
            row['raw']['SOF']={'time_token':match[2],'tokens':tokens,'surface':match[1]}
            continue
        match=node_header.fullmatch(line)
        if match and match[2] in sets:
            section=sets[match[2]];quantity='RP_U' if match[1].startswith('displacements') else 'RP_RF'
            f=frame(match[3])
            if f is None:continue
            row=row_for(section,f,quantity);i=nonblank(i);tokens=lines[i].split()
            if len(tokens)!=4 or tokens[0]!=str(section['reference_node']):raise ValueError('체결 RP 출력이 실제 참조 절점과 다릅니다.')
            values=[]
            for token in tokens[1:]:
                try:v=float(token.replace('D','E'))
                except ValueError:v=math.nan
                values.append(v if math.isfinite(v) else None)
                if not math.isfinite(v):row['quality_reasons'].append('native_nonfinite_or_overflow:'+token)
            row['rp_displacement_mm' if quantity=='RP_U' else 'rp_reaction_N']=values
            row['raw'][quantity]={'time_token':match[3],'tokens':tokens,'set':match[2]};i+=1
    expected={(s['id'],f['static']['step'],f['static']['increment'],q) for s in requested for f in catalog for q in ('SOF','RP_U','RP_RF')}
    if seen!=expected:raise ValueError('필요한 체결 SOF 또는 RP U/RF 출력이 누락됐습니다. 원 출력은 보존합니다.')
    return [rows[key] for key in sorted(rows,key=lambda k:(k[1],k[2],k[0]))]


def responses(model,rows,frames,*,raw_rows='pretension_resultants.json'):
    if not model.get('pretension_sections'):return {}
    out={};clock=axis(model)
    for section in sections(model):
        retained=[r for r in rows if r['section_id']==section['id']]
        definitions=(('axial_force','절단면 절점력 합','N',lambda r:r['assembled_cut_axis_N'],'isolated_cut_native_assembled_nodal_force_axis'),
            ('opposite_force','반대쪽 절단면 절점력 합','N',lambda r:r['opposite_cut_axis_N'],'opposite_isolated_cut_native_nodal_force_axis'),
            ('stress_integral_axis','복구 응력 면적분 축성분','N',lambda r:r['axial_force_N'],'recovered_stress_section_integral_axis'),
            ('normal_force','복구 응력 면적분 법선성분','N',lambda r:r['native_normal_force_N'],'native_section_normal_force'),
            ('differential','절단면 길이 변화','mm',lambda r:r['rp_displacement_mm'][0],'pretension_generalized_differential'),
            ('rp_reaction','참조 자유도 반력','N',lambda r:r['rp_reaction_N'][0],'raw_RP_RF1_not_section_force'))
        for support_id, info in (retained[0].get('support_nodal_axis_forces_N', {}) if retained else {}).items():
            definitions += (('support_'+support_id,info['label']+' / 지지 절점력 합','N',
                lambda r,k=support_id:r['support_nodal_axis_forces_N'][k]['value'],
                'native_FORC_at_axially_constrained_nodes'),)
        for key,label,unit,getter,meaning in definitions:
            valid=[r for r in retained if getter(r) is not None]
            out[section['id']+'.'+key]={'kind':'series','unit':unit,'value':[getter(r) for r in valid],
                'axes':[{'name':clock['name'],'unit':clock['unit'],'values':[r['static']['load_parameter'] for r in valid]}],
                'component':'along_selected_axis' if key=='axial_force' else 'SCALAR',
                'location':section['id'],'reduction':'none','measure':meaning,'frame':'FREECAD_DOCUMENT_GLOBAL',
                'metadata':{'title':section['draft']['label']+' / '+label,'axis_semantics':clock['semantics'],
                    'section_id':section['id'],'axis':section['draft']['axis'],'meaning':meaning,
                    'step_locations':[r['step_location'] for r in valid],'raw_rows':raw_rows,
                    'excluded_nonfinite_rows':len(retained)-len(valid),'engineering_release':'UNKNOWN',
                    'SOF_method':'native nodal stress extrapolation and section integration; not direct nodal equilibrium',
                    'force_scope':'isolated structural cut assembled FORC sum only; not generic RF internal force',
                    'cut_nodes':{'selected':retained[0].get('selected_solver_node_ids'), 'opposite':retained[0].get('opposite_solver_node_ids')}}}
    return out


def attach_nodal_resultants(model, rows, frames):
    """Only the admitted isolated structural cut, not a generic RF reinterpretation.

    CCX 2.22 resultsmech.f assembles sigma*grad(N); resultsforc.c restores MPC
    structural terms but excludes the PRETENSION dummy RP. frd.c emits this fn.
    The model gate excludes axial cut BC/load, contact and other coupling.
    """
    from ..dynamic_native_stream import frame_catalog
    catalog={(f['static']['step'],f['static']['increment']):f for f in frame_catalog(frames)}
    effective,copies=expected_solver_mesh(model)
    for section in sections(model):
        mapping={r['source_node_id']:r['solver_node_id'] for r in copies if r['section_id']==section['id']}
        original=section['node_ids'];selected=[mapping[n] for n in original];axis=section['draft']['axis']
        for row in (r for r in rows if r['section_id']==section['id']):
            f=catalog[(row['static']['step'],row['static']['increment'])]['fields']['FORC']
            def resultant(ids):
                if not all(n in f and len(f[n])==3 and all(math.isfinite(v) for v in f[n]) for n in ids):
                    raise ValueError('실제 절단면의 native FORC 원절점 출력이 누락됐습니다.')
                vector=[sum(f[n][d] for n in ids) for d in range(3)]
                return vector,sum(v*a for v,a in zip(vector,axis))
            left,axial=resultant(selected);right,opposite=resultant(original)
            displacements=catalog[(row['static']['step'],row['static']['increment'])]['fields']['DISP']
            differentials=[sum((displacements[mapping[n]][d]-displacements[n][d])*axis[d] for d in range(3)) for n in original]
            supports={}
            for condition in model.get('conditions',[]):
                support_ids=sorted({b['node_id'] for b in condition.get('boundary_dofs', []) if axis[int(b['component'])-1]!=0})
                if not support_ids:continue
                _,value=resultant(support_ids)
                applied=any(v['node_id'] in support_ids and v['weight']!=0 and axis[int(v['component'])-1]!=0
                    for c in model.get('conditions',[]) for v in c.get('force_weights',[]))
                supports[condition['object_id']]={'label':condition['label'],'node_ids':support_ids,
                    'value':value,'contains_configured_applied_load':applied,
                    'meaning':'native FORC at prescribed axial DOFs; applied loads are not subtracted'}
            row['support_nodal_axis_forces_N']=supports
            row['quality_reasons'].append('SOF_recovered_stress_integral_is_not_the_assembled_nodal_balance')
            row['stress_integral_minus_nodal_axis_N']=None if row['axial_force_N'] is None else row['axial_force_N']-axial
            row.update(assembled_cut_force_global_N=left,assembled_cut_axis_N=axial,
                opposite_cut_force_global_N=right,opposite_cut_axis_N=opposite,
                cut_axis_balance_N=axial+opposite,cut_pair_axis_differential_mm=differentials,selected_solver_node_ids=selected,opposite_solver_node_ids=original,
                assembled_force_scope='isolated structural cut, static linear state, no axial cut BC/load or other coupling')
    return rows
