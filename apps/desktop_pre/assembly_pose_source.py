"""Restore design placement only in an explicitly opened, verified source COPY.

A source saved during motion preview contains those preview placements. Preserve
both them and the original design values without temporarily editing the live
source, then restore the design when a user opens this independent recovery copy.
No motion calculation, frame inference, adopt_pose or binder update takes place.
"""
from pathlib import Path, PurePosixPath

from caelab import native_cad
from .motion import _pose
from .assembly_pose_geometry import placement, same_pose


def retained_design_poses(owner, documents, names):
    result = []
    for doc in documents:
        other = owner if doc is owner.doc else getattr(owner, 'find_owner', lambda _: None)(doc)
        if other is None or not other.motion._preview:
            continue
        if other.generation != other.motion._expected_generation:
            raise ValueError('참조 문서의 미리보기 중 편집이 발생했습니다. 새 편집을 보존하고 그 문서를 먼저 확인하세요.')
        for obj, prop, value in other.motion._base:
            if (doc.getObject(obj.Name) is not obj
                    or _pose(getattr(obj, prop)) != other.motion._last.get((obj.Name, prop))):
                raise ValueError('참조 부품의 배치가 바뀌었습니다. 원래 편집을 보존했습니다.')
            if prop not in {'Placement', 'Placement1', 'Placement2'}:
                raise ValueError('보존할 설계 배치의 속성을 확인할 수 없습니다.')
            result.append({'file': names[doc.Name], 'object': obj.Name, 'property': prop,
                           'displayed': _pose(getattr(obj, prop)), 'design': _pose(value)})
    return result


def restore_retained_source(doc, manifest):
    """Called only by Project.remember_open AFTER native_cad verifies/unpacks.

    Complete validation precedes writes. It accepts ONLY exact working files of
    the verified manifest, never a source filename or name-only object match.
    Failed assignments are rolled back and the disk copy remains untouched.
    """
    info = manifest.get('assembly_pose_source')
    if info is None:
        return
    if info.get('version') != 1 or not isinstance(info.get('restore_design'), list):
        raise ValueError('보존한 원 조립의 설계 자세 정보를 읽을 수 없습니다. 보관 파일을 유지하세요.')
    if not info['restore_design']:
        return
    import FreeCAD as App
    entry = PurePosixPath(manifest['entry'])
    if entry.is_absolute() or '..' in entry.parts or '\\' in str(entry):
        raise ValueError('보존 모델의 상대 경로가 잘못되었습니다.')
    root = Path(doc.FileName).resolve().parents[len(entry.parts)-1]
    paths = {}
    for row in manifest['documents']:
        relative = PurePosixPath(row['file'])
        if relative.is_absolute() or '..' in relative.parts or '\\' in str(relative):
            raise ValueError('보존 부품의 상대 경로가 잘못되었습니다.')
        filename = (root/row['file']).resolve()
        if root not in filename.parents:
            raise ValueError('보존 모델 밖의 부품 경로입니다.')
        paths[row['file']] = filename
    live = {Path(item.FileName).resolve(): item for item in App.listDocuments().values() if item.FileName}
    pending, seen = [], set()
    for row in info['restore_design']:
        key = (row['file'], row['object'], row['property'])
        if key in seen or row['property'] not in {'Placement', 'Placement1', 'Placement2'}:
            raise ValueError('보존한 설계 배치의 참조가 중복되거나 잘못되었습니다.')
        seen.add(key)
        filename = paths.get(row['file'])
        target_doc = live.get(filename)
        target = target_doc.getObject(row['object']) if target_doc is not None else None
        if target is None or not hasattr(target, row['property']):
            raise ValueError('보존한 원부품 참조가 없습니다. 전체 .caepre 파일을 새 프로세스에서 여세요.')
        current = getattr(target, row['property'])
        if not same_pose(_pose(current), row['displayed']):
            raise ValueError('보존한 원 조립의 표시 자세가 달라졌습니다. 새 편집을 자동 덮어쓰지 않습니다.')
        pending.append((target, row['property'], current, placement(App, row['design'])))
    applied = []
    try:
        for target, prop, previous, design in pending:
            applied.append((target, prop, previous))
            setattr(target, prop, design)
            if not same_pose(_pose(getattr(target, prop)), _pose(design)):
                raise ValueError('독립 사본에서 설계 자세를 복구하지 못했습니다.')
    except Exception:
        for target, prop, previous in reversed(applied):
            setattr(target, prop, previous)
        raise
    # A restored design working document is intentionally unsaved; input bytes
    # remain immutable. It may be saved through the existing Save As action.
    manifest['new_design_branch'] = True
    manifest['design_pose_restored'] = True
