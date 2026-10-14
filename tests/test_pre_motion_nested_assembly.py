"""Native containment identity, repeated Link selection and repair. No solver."""
from copy import deepcopy
import pytest
from test_pre_motion import setup, qt_panel
from apps.desktop_pre.motion_occurrence import hierarchy,unique_path,world_placement


def nested(setup):
    owner,motion,target,d=setup;root=owner._object(target['assembly_id'])
    a,b=[joint.Reference1[0] for joint in motion._joints(root) if hasattr(joint,'Reference1')][0],owner.doc.moving
    a.Label=b.Label='반복 부품'
    outer=owner.doc.addObject('Assembly::AssemblyLink','Outer');outer.Label='중첩 배치';outer.Rigid=False
    inner=owner.doc.addObject('Assembly::AssemblyLink','Inner');inner.Label='가동 모듈';inner.Rigid=False
    root.Group=[obj for obj in root.Group if obj not in (a,b)]+[outer];root.OutList=list(root.Group)
    outer.Group=[inner];inner.Group=[a,b]
    motion._modules[0].getMovablePartsWithin=lambda _: [outer,inner,a,b]
    return root,outer,inner,a,b


def test_distinct_repeated_source_links_have_distinct_human_hierarchy_without_source_following(setup):
    root,outer,inner,a,b=nested(setup);paths=hierarchy(root)
    assert a.getLinkedObject() is b.getLinkedObject()
    assert unique_path(root,a)['path']==[root.Name,outer.Name,inner.Name,a.Name]
    assert paths[a.Name][0]['label']==root.Label+' / 중첩 배치 / 가동 모듈 / 반복 부품 (배치 1)'
    assert paths[b.Name][0]['label'].endswith('(배치 2)') and a.getLinkedObject().Name not in paths
    expected=object();calls=[]
    root.getPlacementOf=lambda path,target:(calls.append((path,target)) or expected)
    assert world_placement(root,b) is expected and calls==[('Outer.Inner.'+b.Name+'.',b)]


def test_native_joint_group_direct_alias_is_one_path_but_actual_shared_occurrence_is_ambiguous(setup):
    owner,motion,target,d=setup;root,outer,inner,a,b=nested(setup)
    joint=owner._object(d['drives'][0]['joint_id']);root.Group.append(joint)
    assert len(hierarchy(root)[joint.Name])==1
    other=owner.doc.addObject('App::Part','Other');other.Group=[b];root.Group.append(other)
    assert len(hierarchy(root)[b.Name])==2
    with pytest.raises(ValueError,match='여러 위치'):unique_path(root,b)
    inspected=motion.dispatch('pre.motion.inspect',{},target)
    selected=next(row for row in inspected['occurrences'] if row['id']==b.Name)
    assert not selected['connectable'] and selected['reference_issue']
    with pytest.raises(ValueError,match='여러 위치'):motion._connector(root,{'object_id':b.Name,'subelement':''})


def test_rigid_boundary_allows_whole_body_connector_and_leaf_trace_without_individual_ground(setup):
    owner,motion,target,d=setup;root,outer,inner,a,b=nested(setup);outer.Rigid=True
    paths=hierarchy(root)
    assert paths[outer.Name][0]['connectable'] and not paths[b.Name][0]['connectable']
    assert paths[b.Name][0]['rigid_owner']==outer.Name
    with pytest.raises(ValueError,match='강체'):motion._connector(root,{'object_id':b.Name,'subelement':''})
    with pytest.raises(ValueError,match='강체'):motion.dispatch('pre.joint.create',{'type':'Grounded','occurrence_id':b.Name},target)
    assert unique_path(root,b)['path'][-1]==b.Name  # trace identity remains distinct


def test_qt_exact_nested_selection_repair_cancel_preserves_prior_reference(qt_panel):
    app,widget,panel,queued,descriptor,setup=qt_panel;owner,motion,target,d=setup
    root,outer,inner,a,b=nested(setup)
    inspected=motion.dispatch('pre.motion.inspect',{},target);panel._inspect_value(inspected)
    panel.joint.setCurrentIndex(panel.joint.findData(d['drives'][0]['joint_id']));panel._joint_selected(0)
    assert panel.connector_b.currentData()==b.Name
    assert '(배치 2)' in panel.connector_b.currentText() and panel.traces.cellWidget(0,1).currentData()==b.Name
    assert panel.drives.cellWidget(0,0).toolTip()==panel.drives.cellWidget(0,0).currentText()
    panel.traces.selectRow(0)
    assert panel.trace_notice.text()=='추적 배치: '+panel.traces.cellWidget(0,1).currentText()
    before=deepcopy(panel.current_editor())
    panel.connector_b.setCurrentIndex(panel.connector_b.findData(a.Name));panel.subelement_b.setText('Missing.Face99');panel._mark_joint_edited()
    panel._cancel_joint();assert panel.connector_b.currentData()==b.Name and panel.subelement_b.text()==''
    assert panel.current_editor()==before
    # Saved raw trace missing identity stays visible, then explicit re-selection
    # repairs only that row; another identical-source Link is never substituted.
    raw=deepcopy(before);raw['definition_draft']={'time':{'start':'2','end':'3','step':'.5'},'fps':20,'tolerance':'1e-6',
        'drives':deepcopy(d['drives']),'traces':[{'id':'Tip','occurrence_id':'DeletedOccurrence','point':['1','2','0']}]}
    panel._restore_editor(raw)
    combo=panel.traces.cellWidget(0,1);assert combo.currentData()=='DeletedOccurrence' and '참조 없음' in combo.currentText()
    combo.setCurrentIndex(combo.findData(b.Name));panel._mark_edited()
    assert panel.current_editor()['definition_draft']['traces'][0]['occurrence_id']==b.Name


@pytest.mark.parametrize('failure',[None,'native','move'])
def test_temporary_deep_joint_move_restores_all_groups_even_after_failure(setup,failure):
    from apps.desktop_pre.motion_occurrence import native_scope
    owner,motion,target,d=setup;root,outer,inner,a,b=nested(setup)
    joint=owner._object(d['drives'][0]['joint_id'])
    root_group=next(o for o in root.Group if o.TypeId=='Assembly::JointGroup')
    root_group.Group.remove(joint)
    child_group=owner.doc.addObject('Assembly::JointGroup','NestedJoints');child_group.Group=[joint]
    inner.Group += [child_group,joint];inner.OutList=list(inner.Group)
    before={obj.Name:list(obj.Group) for obj in owner.doc.Objects if hasattr(obj,'Group')}
    def move(obj):
        child_group.Group.remove(obj);inner.Group.remove(obj)
        root_group.Group.append(obj);root.Group.append(obj)
        if failure=='move': raise RuntimeError('controlled group move failure')
    root_group.addObject=move
    def run():
        with native_scope(root,[joint],[outer,inner,a,b]):
            assert joint in root_group.Group and joint not in child_group.Group
            if failure=='native': raise RuntimeError('controlled native failure')
    if failure:
        with pytest.raises(RuntimeError,match='controlled'):run()
    else:run()
    assert {obj.Name:list(obj.Group) for obj in owner.doc.Objects if hasattr(obj,'Group')}==before
    assert joint.Reference1[0] is a and joint.Reference2[0] is b
    assert not any(call[0]=='generateSimulation' for call in owner.doc.calls)
