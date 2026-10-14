"""Read native occurrence containment without following LinkedObject definitions."""
from collections import Counter, defaultdict
from contextlib import contextmanager


def hierarchy(assembly):
    rows=defaultdict(list)
    def children(obj):
        values=list(getattr(obj,'ElementList',[]) or getattr(obj,'Group',[]))
        # Native Assembly also lists JointGroup members directly in Group.
        # These are containment aliases, not two independent occurrences.
        grouped={joint.Name for group in values if group.TypeId=='Assembly::JointGroup' for joint in group.Group}
        return [child for child in values if child.Name not in grouped]
    def walk(parent,path,labels,rigid,ancestry):
        values=children(parent); counts=Counter(obj.Label for obj in values); ordinals=Counter()
        for obj in values:
            if obj.Name in ancestry: raise ValueError('조립 계층이 순환합니다. 해당 배치를 복구하세요.')
            ordinals[obj.Label]+=1
            label=obj.Label+(' (배치 '+str(ordinals[obj.Label])+')' if counts[obj.Label]>1 else '')
            names=path+[obj.Name]; titles=labels+[label]
            boundary=rigid or (obj.Name if obj.TypeId=='Assembly::AssemblyLink' and getattr(obj,'Rigid',True) else None)
            title=' / '.join(([assembly.Label] if len(names)>3 else [])+titles)
            rows[obj.Name].append({'id':obj.Name,'path':names,'label':title,
                'rigid_owner':boundary,'connectable':not (obj.TypeId=='Assembly::AssemblyLink' and not getattr(obj,'Rigid',True)) and (boundary is None or boundary==obj.Name)})
            if len(names)>64: raise ValueError('조립 계층이 너무 깊습니다.')
            walk(obj,names,titles,boundary,ancestry|{obj.Name})
    walk(assembly,[assembly.Name],[],None,{assembly.Name})
    return dict(rows)


def unique_path(assembly,obj,rows=None):
    paths=(rows if rows is not None else hierarchy(assembly)).get(obj.Name,[])
    if len(paths)!=1:
        raise ValueError('선택한 조립 안의 배치 참조가 '+('없습니다.' if not paths else '여러 위치에 걸쳐 있습니다.')+
            ' 원부품 대신 해당 위치의 별도 Link를 다시 선택하세요.')
    return paths[0]


def world_placement(assembly,obj):
    row=unique_path(assembly,obj)
    # Rooting at the actual occurrence hierarchy avoids the native helper's
    # ambiguous Parents fallback to a local placement. Never follow definitions.
    if hasattr(assembly,'getPlacementOf'):
        return assembly.getPlacementOf('.'.join(row['path'][1:])+'.',obj)
    return None  # API-shaped test fixtures may supply the existing utility.


class NestedRecoveryError(RuntimeError):
    """A temporary native ownership/coordinate change could not be restored."""


@contextmanager
def native_scope(assembly,joints,parts):
    """Use native deep joints in the native root solver, then restore ownership.

    GroupExtension.addObject temporarily MOVES normal-group membership; this is
    not an alias. No recompute, events, persistence, clone or new solver here.
    Native bodies use root-local coordinates; restored frames use original parents.
    """
    paths=hierarchy(assembly)
    flexible=[obj for obj in parts if obj.TypeId=='Assembly::AssemblyLink' and not getattr(obj,'Rigid',True)
        and unique_path(assembly,obj,paths)['rigid_owner'] is None]
    deep=[joint for joint in joints if hasattr(joint,'JointType') and len(unique_path(assembly,joint,paths)['path'])>4]
    if not deep and not flexible:
        yield; return
    objects={assembly.Name:assembly}
    for name in paths:
        obj=assembly.Document.getObject(name)
        if obj is not None: objects[name]=obj
    groups=[(obj,list(obj.Group)) for obj in objects.values() if hasattr(obj,'Group')]
    root_group=next(obj for obj,group in groups if obj.TypeId=='Assembly::JointGroup' and obj in assembly.Group)
    parents=[(obj,obj.Placement.copy()) for obj in flexible]
    transforms=[]; changed=[]; entered=False; errors=[]
    def names(values):return [obj.Name for obj in values]
    try:
        # Only independent native bodies: flexible leaf or rigid boundary.
        if flexible and hasattr(assembly.Placement,'inverse'):
            identity=type(assembly.Placement)()
            for part in parts:
                row=unique_path(assembly,part,paths)
                if not row['connectable']: continue
                transform=identity.copy()
                for name in row['path'][1:-1]:
                    parent=objects[name]
                    if hasattr(parent,'Placement'): transform=transform.multiply(parent.Placement)
                if transform.isIdentity(): continue
                transforms.append((part,transform,part.Placement.copy()))
            for part,transform,original in transforms:
                part.Placement=transform.multiply(original);changed.append((part,transform,original))
            for parent,original in parents: parent.Placement=identity.copy()
        for joint in deep: root_group.addObject(joint)
        entered=True
        yield
    finally:
        # Free moved joints from the temporary normal group first, then restore
        # original normal groups and the collateral GeoFeatureGroup memberships.
        snapshots=dict((obj.Name,values) for obj,values in groups)
        order=[(root_group,snapshots[root_group.Name]),(assembly,snapshots[assembly.Name])]
        order += [(obj,values) for obj,values in groups if obj is not root_group and obj.TypeId=='Assembly::JointGroup']
        order += [(obj,values) for obj,values in reversed(groups) if obj.TypeId!='Assembly::JointGroup' and obj is not assembly]
        order.append((assembly,snapshots[assembly.Name]))
        for obj,values in order:
            try:
                if names(obj.Group)!=names(values): obj.Group=values
            except Exception as error: errors.append(obj.Label+': '+str(error))
        for parent,original in parents:
            try: parent.Placement=original
            except Exception as error: errors.append(parent.Label+': '+str(error))
        for part,transform,original in changed:
            try: part.Placement=transform.inverse().multiply(part.Placement) if entered else original
            except Exception as error: errors.append(part.Label+': '+str(error))
        for obj,values in groups:
            try:
                if names(obj.Group)!=names(values): errors.append(obj.Label+': 원래 멤버/순서가 복원되지 않았습니다.')
            except Exception as error: errors.append(obj.Label+': '+str(error))
        if errors: raise NestedRecoveryError('조립 계층 복구가 필요합니다. 저장·전환을 중단했습니다. '+ '; '.join(errors))
