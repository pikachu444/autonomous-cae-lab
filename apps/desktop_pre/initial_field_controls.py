"""Protect saved sidecar initial conditions at the native solver entry."""


def route(connection, owner, solver):
    from .fem_edit import _native_type
    wanted = set(owner.read_metadata().get('initial_fields', {}))
    analyses = [obj for obj in owner.doc.Objects
                if _native_type(obj) == 'Fem::FemAnalysis' and solver in obj.Group and obj.Name in wanted]
    if not analyses:
        return False
    names = ', '.join(getattr(obj, 'Label', obj.Name) for obj in analyses)
    raise ValueError(names + ': 저장된 초기조건은 FreeCAD 솔버 작업창의 입력에 포함되지 않습니다. '
                     '계산 관리에서 입력 파일 생성 또는 입력 보존 후 계산을 선택하세요.')
