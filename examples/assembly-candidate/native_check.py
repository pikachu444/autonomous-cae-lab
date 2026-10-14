"""Native Windows acceptance entry points; not executed by Linux pytest.

No output is prefilled with a success. A report is written only by actual native
execution. Cold read/edit and re-saved verification run in separate FreeCAD processes.
"""
from copy import deepcopy
from pathlib import Path
import sys
import os
import time

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path: sys.path.insert(0,str(REPOSITORY))


def acquire(doc, output):
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.assembly_pose_candidate import _hold
    module=sys.modules.get('apps.desktop_pre.cae_prep')
    connection=getattr(module,'CONNECTION',None)
    if connection is not None:
        live=connection.owners.get(doc.Name)
        if live and live[0].doc is doc:return live[0],False
    _hold(doc)
    owner=Owner(doc,Path(output)/'exchange',App=App,Gui=Gui);owner.QtCore=QtCore
    return owner,True


def release(owner, temporary):
    if temporary:
        from apps.desktop_pre.assembly_pose_candidate import _release
        owner.close();_release(owner.doc)


def snapshot(owner):
    from apps.desktop_pre.motion import _pose
    from caelab.native_cad import sha
    return {'metadata':owner.read_metadata(), 'generation':owner.generation,
            'saved_generation':owner.saved_generation, 'project_path':str(owner.project.path),
            'filename':owner.doc.FileName,
            'file_hash':sha(owner.doc.FileName) if owner.doc.FileName and Path(owner.doc.FileName).is_file() else None,
            'objects':[(obj.Name,obj.TypeId) for obj in owner.doc.Objects],
            'placements':{obj.Name:_pose(obj.Placement) for obj in owner.doc.Objects if hasattr(obj,'Placement')},
            'joints':{obj.Name:{key:(_pose(getattr(obj,key)) if key.startswith('Placement') else str(getattr(obj,key)))
                for key in ('Reference1','Reference2','Placement1','Placement2') if hasattr(obj,key)}
                for obj in owner.doc.Objects if hasattr(obj,'JointType')}}


def verify_selected(output, assembly_id, calculation_id, frame, *, with_mesh=False):
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore
    from apps.desktop_pre.assembly_pose_candidate import (require_valid,prepare_fem_object,selected_body)
    from apps.desktop_pre.assembly_pose_geometry import same_pose
    from apps.desktop_pre.motion import _pose
    from apps.desktop_pre.mesh_binding import PROPERTY_NAME
    from caelab.storage import save_json
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    owner,temporary=acquire(App.ActiveDocument,output/'source')
    report={'state':'RUNNING','native_version':'.'.join(App.Version()[:3]),'mesh_requested':with_mesh,
            'solver_execution':'NOT_PERFORMED','writer_pid':os.getpid(),'gui_workflow_acceptance':False}
    candidate=None;candidate_temporary=False
    try:
        # Exercise preservation of the actual preview, not only a design frame.
        owner.motion.dispatch('pre.motion.frame',{'calculation_id':calculation_id,'frame':frame},{'assembly_id':assembly_id})
        before=snapshot(owner)
        job=owner.pose_candidates
        job.start({'calculation_id':calculation_id,'frame':frame},{'assembly_id':assembly_id},automatic=False)
        for _ in range(1024):
            if not job.busy:break
            job.advance()
        if job.busy:job.cancel();job.advance()
        report['preparation']=deepcopy(job.current)
        if job.current['state']!='READY':raise RuntimeError(job.current['message'])
        assert snapshot(owner)==before,'원 조립이나 저장 결과가 변경됨'
        assert App.getDocument(owner.doc.Name) is owner.doc,'원 창이 닫힘'
        candidate,candidate_temporary=acquire(job._document,output/'target')
        model=require_valid(candidate,exact=True)
        saved=candidate.read_metadata()['assembly_pose_candidate']
        assert len(saved['bodies'])==4, '공개 중첩 슬라이더의 네 occurrence 필요'
        assert any(len(row['path'])>=4 for row in saved['bodies']),'두 깊이 배치 필요'
        assert len({row['source_id'] for row in saved['bodies']})<len(saved['bodies']),'반복 Link 필요'
        assert len(owner.motion._joints(owner._object(assembly_id)))>=3,'복수 관절 필요'
        analysis=candidate._object(model['analysis_id'])
        assert not any(hasattr(obj,'References') for obj in analysis.Group),'경계조건이 자동 추가됨'
        App.setActiveDocument(candidate.doc.Name)
        import FemGui
        FemGui.setActiveAnalysis(analysis)
        mesh_ids=[];material_ids=[];assignments=[]
        for index,row in enumerate(model['bodies'],1):
            body=candidate._object(row['body_id'])
            Gui.Selection.clearSelection();Gui.Selection.addSelection(body,'Face'+str(index))
            assert selected_body(candidate)==body.Name,'native 선택이 다른 반복 부품에 연결됨'
            mesh=prepare_fem_object(candidate,body.Name,'mesh');mesh_ids.append(mesh['object_id'])
            material=prepare_fem_object(candidate,body.Name,'material');material_ids.append(material['object_id'])
            candidate.fem.dispatch('pre.fem.material_set',{'young_modulus':200000.+1000.*index,'unit':'MPa','poisson_ratio':.3},
                                   {'object_id':material['object_id']})
            candidate.fem.dispatch('pre.fem.mesh_settings',{'min_size':2.+.1*index,'max_size':4.+.1*index,'unit':'mm','element_type':'C3D10'},
                                   {'object_id':mesh['object_id']})
            assert candidate._object(mesh['object_id']).Shape is body
            # Explicitly assign a different real face of every occurrence.
            # These supports are test edits, not a conversion of mechanism ground.
            face='Face'+str(index)
            region=candidate.fem.dispatch('pre.fem.region_set',
                {'label':body.Label+' — 시험 면 '+str(index),'subelements':[face]}, {'object_id':body.Name})
            condition=candidate.fem.dispatch('pre.fem.condition_set',
                {'region_id':region['id'],'kind':'Fixed'}, {'object_id':analysis.Name})
            local=candidate.fem.dispatch('pre.fem.mesh_local_size',
                {'region_id':region['id'],'size':1.5+.1*index,'unit':'mm'}, {'object_id':mesh['object_id']})
            native_mesh=candidate._object(mesh['object_id'])
            native_material=candidate._object(material['object_id'])
            assignments.append({'body_id':body.Name,'mesh_id':native_mesh.Name,
                'material_id':native_material.Name,'material':dict(native_material.Material),
                'condition_id':condition['object_id'],'region_id':region['id'],'face':face,
                'target':deepcopy(region['target']), 'mesh_settings':candidate.fem._mesh_settings(native_mesh),
                'local_id':local['object_id'],'local_size_mm':local['size_mm']})
            if with_mesh:
                info=candidate.fem.dispatch('pre.fem.mesh_generate',{}, {'object_id':mesh['object_id']})
                deadline=time.monotonic()+180.
                while candidate.fem._pending and time.monotonic()<deadline:
                    QtCore.QCoreApplication.processEvents();time.sleep(.02)
                if candidate.fem._pending:
                    candidate.fem.dispatch('pre.fem.mesh_cancel',{'history_id':info['history_id']}, {'object_id':mesh['object_id']})
                    raise RuntimeError('native 메시 완료를 확인하지 못했습니다. 취소와 원자료를 확인하세요.')
                record=next(row for row in candidate.fem._metadata()['mesh_history'] if row['id']==info['history_id'])
                assert record['state']=='SUCCEEDED',record
                assert native_mesh.FemMesh.VolumeCount>0
                candidate.mesh_bindings.validate(native_mesh)
                assert not candidate.fem._refinement_errors(native_mesh)
                assignments[-1]['mesh_binding'] = getattr(native_mesh,PROPERTY_NAME)
                assignments[-1]['mesh_volume_count'] = native_mesh.FemMesh.VolumeCount
                assignments[-1]['mesh_node_count'] = len(native_mesh.FemMesh.Nodes)
                from apps.desktop_pre.fem_edit import _mesh_hash
                assignments[-1]['mesh_content_sha256'] = _mesh_hash(native_mesh.FemMesh)
            native_condition=candidate._object(condition['object_id'])
            assert native_condition.References==[(body,(face,))] or native_condition.References==[(body,[face])]
            assert not candidate.fem._condition_errors(native_condition,candidate.fem._metadata())
        saved_edit=candidate.project.save(output/'edited.caepre')
        report.update(state='PASSED_NATIVE_PREPARATION_AND_EDIT', edited=saved_edit,
            expected={'bodies':saved['bodies'],'meshes':mesh_ids,'materials':material_ids,
                      'assignments':assignments,'frame':frame,'time':model['time']},
            mesh_execution='NATIVE_GMSH' if with_mesh else 'NOT_PERFORMED')
        assert snapshot(owner)==before,'편집 후 원 조립이 변경됨'
        # Candidate cache validation must never recompute on read.
        require_valid(candidate)
        save_json(output/'native-check.json',report)
        return report
    except Exception as error:
        report.update(state='FAILED',error=str(error))
        if candidate is not None:
            try:report['failed_edit']=candidate.project.save(output/'edit-failed.caepre')
            except Exception as save_error:report['retention_error']=str(save_error)
        save_json(output/'native-check.json',report)
        raise
    finally:
        if candidate is not None:release(candidate,candidate_temporary)
        release(owner,temporary)


class ReadObserver:
    """Observe native recomputes during a cold read; never suppress/replace them."""
    def __init__(self): self.recomputed=[]
    def slotRecomputedDocument(self,doc): self.recomputed.append(('document',doc.Name))
    def slotRecomputedObject(self,obj): self.recomputed.append(('object',obj.Name))


def candidate_references(obj):
    return [(source.Name,tuple([names] if isinstance(names,str) else names))
            for source,names in obj.References]


def check_assignments(owner, expected, mesh_execution):
    """Exact persisted targets/values, not a substitute model or nearest match."""
    from apps.desktop_pre.assembly_pose_candidate import KEY, require_valid
    from apps.desktop_pre.assembly_pose_geometry import same_pose
    from apps.desktop_pre.motion import _pose
    from apps.desktop_pre.fem_edit import _target, _mesh_hash
    from apps.desktop_pre.mesh_binding import PROPERTY_NAME
    result=require_valid(owner)
    assert result['state']=='READY' and result['ready']
    assert result['frame']==expected['frame'] and result['time']==expected['time']
    assert owner.read_metadata()[KEY]['bodies']==expected['bodies']
    assert {r['body_id'] for r in result['bodies']}=={r['body_id'] for r in expected['assignments']}
    assert len({r['mesh_id'] for r in expected['assignments']})==len(expected['assignments'])
    assert len({r['material_id'] for r in expected['assignments']})==len(expected['assignments'])
    for row in expected['bodies']:
        link=owner._object(row['link_id']);assert same_pose(_pose(link.Placement),row['world_pose'])
        assert list(owner._object(row['body_id']).SourceOccurrencePath)==row['path']
    for assignment in expected['assignments']:
        body=owner._object(assignment['body_id'])
        mesh=owner._object(assignment['mesh_id'])
        material=owner._object(assignment['material_id'])
        condition=owner._object(assignment['condition_id'])
        assert mesh.Shape is body
        assert candidate_references(material)==[(body.Name,('',))]
        assert dict(material.Material)==assignment['material']
        assert candidate_references(condition)==[(body.Name,(assignment['face'],))]
        assert _target(body,[assignment['face']])==assignment['target']
        assert owner.fem._mesh_settings(mesh)==assignment['mesh_settings']
        assert not owner.fem._refinement_errors(mesh)
        refinement=owner._object(assignment['local_id'])
        assert refinement in mesh.MeshRegionList
        assert abs(float(refinement.CharacteristicLength.getValueAs('mm').Value)
                   - assignment['local_size_mm']) <= 1.e-7
        assert candidate_references(refinement)==[(body.Name,(assignment['face'],))]
        assert not owner.fem._condition_errors(condition,owner.fem._metadata())
        region,source,names=owner.fem._region(assignment['region_id'])
        assert source is body and names==[assignment['face']] and region['target']==assignment['target']
        if mesh_execution=='NATIVE_GMSH':
            assert mesh.FemMesh.VolumeCount==assignment['mesh_volume_count']>0
            assert len(mesh.FemMesh.Nodes)==assignment['mesh_node_count']
            assert getattr(mesh,PROPERTY_NAME)==assignment['mesh_binding']
            if assignment.get('mesh_content_sha256'):
                assert _mesh_hash(mesh.FemMesh)==assignment['mesh_content_sha256']
            owner.mesh_bindings.validate(mesh)
    fixed=[obj for obj in owner.doc.Objects if obj.isDerivedFrom('Fem::ConstraintFixed')]
    assert {obj.Name for obj in fixed}=={r['condition_id'] for r in expected['assignments']}
    assert not owner.doc.OutList and not any(obj.TypeId.startswith('Assembly::') for obj in owner.doc.Objects)
    assert not owner.fem._pending
    return result


def edit_reopened_inputs(owner, expected, mesh_execution):
    """Apply new real FEM inputs through existing typed commands, without meshing.

    Keep each occurrence's mesh/material/condition/refinement OBJECT identity.
    New face selection is an explicit user edit, never automatic fingerprint
    repair. The previous .caepre and report retain the old inputs unchanged.
    """
    from apps.desktop_pre.assembly_pose_candidate import KEY, require_valid
    from apps.desktop_pre.fem_edit import _target, _mesh_hash
    from apps.desktop_pre.mesh_binding import PROPERTY_NAME
    require_valid(owner)
    before=deepcopy(owner.read_metadata())
    targets={r['body_id']:_target(owner._object(r['body_id']),[]) for r in expected['assignments']}
    mesh_before={r['mesh_id']:{'binding':getattr(owner._object(r['mesh_id']),PROPERTY_NAME,None),
        'contents':_mesh_hash(owner._object(r['mesh_id']).FemMesh) if mesh_execution=='NATIVE_GMSH' else None}
        for r in expected['assignments']}
    updated=deepcopy(expected);edits=[]
    for index,(old,row) in enumerate(zip(expected['assignments'],updated['assignments']),1):
        body=owner._object(old['body_id']);mesh=owner._object(old['mesh_id'])
        material=owner._object(old['material_id'])
        # Repeat selection is explicit on every command; there is no active-last
        # mesh fallback. All four materials and all four faces must change.
        e=210000.+1000.*index;nu=.29
        minimum=2.5+.1*index;maximum=4.5+.1*index;local_size=1.+.1*index
        material_reply=owner.fem.dispatch('pre.fem.material_set',
            {'young_modulus':e,'unit':'MPa','poisson_ratio':nu},{'object_id':material.Name})
        settings_reply=owner.fem.dispatch('pre.fem.mesh_settings',
            {'min_size':minimum,'max_size':maximum,'unit':'mm','element_type':'C3D10'},
            {'object_id':mesh.Name})
        assert material_reply['object_id']==material.Name
        assert settings_reply['mesh_id']==mesh.Name and settings_reply['mesh_generated'] is False
        assert dict(material.Material)!=old['material']
        # Check requested values, not just whatever a setter happened to return.
        units=owner.App.Units
        assert abs(float(units.Quantity(material.Material['YoungsModulus']).getValueAs('MPa').Value)-e)<=1.e-7
        assert abs(float(material.Material['PoissonRatio'])-nu)<=1.e-12
        assert abs(float(mesh.CharacteristicLengthMin.getValueAs('mm').Value)-minimum)<=1.e-7
        assert abs(float(mesh.CharacteristicLengthMax.getValueAs('mm').Value)-maximum)<=1.e-7
        assert owner.fem._mesh_settings(mesh)!=old['mesh_settings']
        face_count=len(body.Shape.Faces)
        if face_count<2:raise ValueError('재열기 편집 확인에는 구별되는 실제 면이 두 개 이상 필요합니다.')
        face='Face'+str(int(old['face'][4:]) % face_count+1)
        assert face!=old['face']
        region=owner.fem.dispatch('pre.fem.region_set',
            {'label':body.Label+' — 재열기 수정 면','subelements':[face]}, {'object_id':body.Name})
        condition=owner.fem.dispatch('pre.fem.condition_set',
            {'region_id':region['id'],'kind':'Fixed'}, {'object_id':old['condition_id']})
        local=owner.fem.dispatch('pre.fem.mesh_local_size',
            {'region_id':region['id'],'refinement_id':old['local_id'],'size':local_size,'unit':'mm'},
            {'object_id':mesh.Name})
        assert condition['object_id']==old['condition_id'] and local['object_id']==old['local_id']
        assert region['target']==_target(body,[face])
        row.update(material=dict(material.Material),mesh_settings=owner.fem._mesh_settings(mesh),
                   region_id=region['id'],face=face,target=deepcopy(region['target']),local_size_mm=local['size_mm'])
        assert abs(local['size_mm']-local_size)<=1.e-7 and local_size!=old['local_size_mm']
        edits.append({'body_id':body.Name,'mesh_id':mesh.Name,'material_id':material.Name,
                      'condition_id':old['condition_id'],'local_id':old['local_id'],
                      'old_face':old['face'],'new_face':face,'young_modulus_MPa':e,
                      'poisson_ratio':nu,'min_size_mm':minimum,'max_size_mm':maximum,
                      'local_size_mm':local_size})
    # Applying inputs must not solve, regenerate meshes or re-stamp old geometry.
    after=owner.read_metadata()
    assert after[KEY]==before[KEY]
    assert after.get('mesh_history',[])==before.get('mesh_history',[])
    assert after.get('motion_paths',{})==before.get('motion_paths',{})
    for old in before.get('regions',[]):
        assert old in after['regions']  # old face snapshots are retained, not refreshed
    for row in updated['assignments']:
        body=owner._object(row['body_id']);mesh=owner._object(row['mesh_id'])
        assert _target(body,[])==targets[body.Name]
        assert getattr(mesh,PROPERTY_NAME,None)==mesh_before[mesh.Name]['binding']
        if mesh_execution=='NATIVE_GMSH':
            assert _mesh_hash(mesh.FemMesh)==mesh_before[mesh.Name]['contents']
    check_assignments(owner,updated,mesh_execution)
    return updated,edits


def verify_cold(project, report_path, *, edit=False, receipt_name='cold-check.json'):
    """New process: prove no-recompute read FIRST; optionally edit and re-save.

    Explicit FEM apply transactions may recompute native objects after the read
    check. They do not replay motion, regenerate Gmsh meshes or run FEM solvers.
    A third fresh process must read cold-edited.caepre to prove persistence.
    """
    import FreeCAD as App
    from apps.desktop_pre.projects import remember_open
    from apps.desktop_pre.assembly_pose_candidate import require_valid
    from apps.desktop_pre.mesh_binding import PROPERTY_NAME
    from caelab import native_cad
    from caelab.storage import load_json,save_json
    import uuid
    project,report_path=Path(project).resolve(),Path(report_path).resolve()
    if App.listDocuments():raise ValueError('문서가 없는 새 FreeCAD 프로세스에서 실행하세요.')
    report=load_json(report_path);expected=report['expected']
    if report.get('state') not in {'PASSED_NATIVE_PREPARATION_AND_EDIT','PASSED_NATIVE_COLD_EDIT_AND_SAVE'}:
        raise ValueError('완료한 앞 단계의 실제 저장 기록이 필요합니다.')
    if report.get('writer_pid')==os.getpid():raise ValueError('저장한 프로세스와 다른 FreeCAD에서 여세요.')
    if len(expected.get('assignments',[]))!=4 or len(expected.get('bodies',[]))!=4:
        raise ValueError('네 부품의 정확한 메시/재료/면 대응 기록이 필요합니다.')
    file_sha=native_cad.sha(project);report_sha=native_cad.sha(report_path)
    if file_sha!=report['edited']['sha256']:
        raise ValueError('앞 단계에서 저장한 정확한 편집 파일이 아닙니다. 원파일을 보존하세요.')
    output=project.parent
    destination=output/'cold-edited.caepre'
    edit_report=output/'cold-edit-check.json'
    if edit and (destination.exists() or edit_report.exists()):
        raise FileExistsError('재열기 수정 사본이 이미 있습니다. 새 출력 폴더에서 실행하세요.')
    observer=ReadObserver();App.addDocumentObserver(observer)
    owner=None;temporary=False
    status={'state':'RUNNING','project':str(project),'solver_execution':'NOT_PERFORMED',
            'writer_pid':report['writer_pid'],'reader_pid':os.getpid(),'gui_workflow_acceptance':False}
    try:
        manifest,entry=native_cad.unpack_project(project,output/('cold-'+uuid.uuid4().hex[:8]))
        doc=App.openDocument(str(entry));remember_open(doc,manifest,project)
        owner,temporary=acquire(doc,output/'cold-exchange')
        before=snapshot(owner)
        stamps={r['mesh_id']:getattr(owner._object(r['mesh_id']),PROPERTY_NAME,None)
                for r in expected['assignments']}
        result=check_assignments(owner,expected,report['mesh_execution'])
        assert stamps=={r['mesh_id']:getattr(owner._object(r['mesh_id']),PROPERTY_NAME,None)
                       for r in expected['assignments']}
        assert snapshot(owner)==before and native_cad.sha(project)==file_sha
        assert not observer.recomputed, 'cold read triggered native recompute: '+repr(observer.recomputed)
        status.update(state='PASSED_NATIVE_COLD_REOPEN',recomputed=False,bodies=len(expected['bodies']))
        save_json(output/receipt_name,status)
        if not edit:return result
        status.update(state='EDITING',read_recomputed=False)
        updated,edits=edit_reopened_inputs(owner,expected,report['mesh_execution'])
        result=require_valid(owner)
        saved=owner.project.save(destination)
        # Save must not silently restore the original inputs. Native recomputes
        # from explicit apply are recorded separately from the cold read check.
        check_assignments(owner,updated,report['mesh_execution'])
        assert native_cad.sha(project)==file_sha and native_cad.sha(report_path)==report_sha
        status.update(state='PASSED_NATIVE_COLD_EDIT_AND_SAVE',edited=saved,
            expected=updated,applied_edits=edits,writer_pid=os.getpid(),
            prior_writer_pid=report['writer_pid'],previous_project_sha256=file_sha,
            previous_report_sha256=report_sha,mesh_execution=report['mesh_execution'],
            mesh_regeneration='NOT_PERFORMED',settings_changed_after_meshing=report['mesh_execution']=='NATIVE_GMSH',
            recomputed=bool(observer.recomputed),explicit_apply_recomputes=deepcopy(observer.recomputed))
        save_json(edit_report,status)
        return status
    except Exception as error:
        status.update(state='FAILED',error=str(error),observed_recomputes=deepcopy(observer.recomputed))
        if edit and owner is not None:
            try:
                failed=output/('cold-edit-failed-'+uuid.uuid4().hex[:8]+'.caepre')
                status['failed_edit']=owner.project.save(failed)
            except Exception as save_error:status['retention_error']=str(save_error)
        save_json(edit_report if edit else output/receipt_name,status)
        raise
    finally:
        try:
            if owner is not None:release(owner,temporary)
        finally:
            App.removeDocumentObserver(observer)
