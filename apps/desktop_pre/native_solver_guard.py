"""Keep native CalculiX Tasks from silently omitting saved sidecar conditions."""
from functools import wraps

from . import metadata


def _check(analysis):
    data = metadata.read(analysis.Document)
    conditions = []
    for key, label in (
        ('contacts', '접촉'), ('contact_programs', '접촉 해석단계'),
        ('convergence_drafts', '수렴 설정'), ('periodic_constraints', '주기 구속'),
        ('pretension_sections', '볼트 체결'),
    ):
        if any(row.get('analysis_id') == analysis.Name for row in data.get(key, [])):
            conditions.append(label)
    for key, label in (
        ('initial_fields', '초기조건'), ('pretension_editors', '볼트 체결 초안'),
        ('shells', '셸 정의'), ('beam_models', '보 정의'),
        ('dynamic_programs', '동해석 단계'), ('composite_shells', '적층 셸'),
        ('displacement_transfers', '변위 전달'),
    ):
        if analysis.Name in data.get(key, {}):
            conditions.append(label)
    if conditions:
        raise ValueError(
            f'{getattr(analysis, "Label", analysis.Name)}: 저장된 {", ".join(conditions)}은 '
            'FreeCAD 솔버 작업창의 입력에 포함되지 않습니다. '
            'CAE 연구 ▸ 저장된 확장 조건 편집…에서 해당 조건을 확인하고 '
            '입력 파일 생성 또는 입력 보존 후 계산을 선택하세요. 미완성 조건은 그대로 보존됩니다.')


def install():
    """Delegate the original APIs unchanged after a read-only omission check."""
    from femviewprovider.view_solver_ccxtools import VPSolverCcxTools
    from femsolver.calculix.writer import FemInputWriterCcx
    from femtaskpanels.task_solver_ccxtools import _TaskPanel
    from .fem_edit import _native_type

    if not getattr(VPSolverCcxTools.setEdit, '_caelab_native_guard', False):
        original_edit = VPSolverCcxTools.setEdit

        @wraps(original_edit)
        def set_edit(self, vobj, mode=0):
            try:
                solver = vobj.Object
                for analysis in solver.Document.Objects:
                    if _native_type(analysis) == 'Fem::FemAnalysis' and solver in analysis.Group:
                        _check(analysis)
            except ValueError as error:
                import FreeCAD
                import FreeCADGui
                from PySide import QtGui
                FreeCAD.Console.PrintError(str(error) + '\n')
                QtGui.QMessageBox.warning(FreeCADGui.getMainWindow(), '솔버 입력 조건', str(error))
                return False
            return original_edit(self, vobj, mode)

        set_edit._caelab_native_guard = True
        VPSolverCcxTools.setEdit = set_edit

    if not getattr(FemInputWriterCcx.write_solver_input, '_caelab_native_guard', False):
        original_write = FemInputWriterCcx.write_solver_input

        @wraps(original_write)
        def write_solver_input(self, *args, **kwargs):
            _check(self.analysis)
            return original_write(self, *args, **kwargs)

        write_solver_input._caelab_native_guard = True
        FemInputWriterCcx.write_solver_input = write_solver_input

    if not getattr(_TaskPanel.runCalculix, '_caelab_native_guard', False):
        original_run = _TaskPanel.runCalculix

        @wraps(original_run)
        def run_calculix(self, *args, **kwargs):
            try:
                _check(self.fea.analysis)
            except ValueError as error:
                self.femConsoleMessage(str(error), 'Error')
                return None
            return original_run(self, *args, **kwargs)

        run_calculix._caelab_native_guard = True
        _TaskPanel.runCalculix = run_calculix
