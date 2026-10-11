"""Material owner view for the existing MFront law/protocol declarations.

Uses the same typed document editor and stored response reader as Simulation.
FELUPE's direct table editor is retained separately; there is no new numerical
law, FE-card emulation, independent owner or automatic backend fallback here.
"""
from copy import deepcopy

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QInputDialog

from caelab.material_document import NATIVE_LAWS, diagnostics
from caelab.simulation_document import default_draft, support_details
from .simulation_window import SimulationWindow


class NativeMaterialWindow(SimulationWindow):
    document_kind, tool_label = 'material', 'Material'
    model_backends = NATIVE_LAWS
    model_default, model_diagnostics, model_support = map(staticmethod, (default_draft, diagnostics, support_details))

    def __init__(self, client, **kwargs):
        new_native = kwargs.get('auto_open', True) and not kwargs.get('document_id')
        if new_native:
            kwargs['auto_open'] = False
        from .desktop import launch_tool, open_document_result, open_domain_plan
        kwargs.setdefault('runner_open', lambda job: launch_tool(client, 'runner', job_id=job))
        kwargs.setdefault('result_open', lambda doc, job, **kw: open_document_result(client, doc, job, **kw))
        kwargs.setdefault('plan_open', lambda doc, **kw: open_domain_plan(client, doc, **kw))
        super().__init__(client, **kwargs)
        self.new_action.setText('New constitutive law document…')
        self.open_action.setText('Open Material document…')
        self.plan_button.setText('Numerical Plan…')
        self._other_material_windows = []
        if new_native:
            self.open_document(draft=self.model_default(NATIVE_LAWS[0]))

    def _show_support(self, draft=None, checks=None, details=None):
        if details is None and self.document:
            details = self.document.get('material_support', {})
        super()._show_support(draft, checks, details)
        self.support.setText('Material-point law, protocol and native state convention are explicit. '
            'Elasticity, SVK and single-branch Maxwell use their existing MFront adapters. '
            'No MGIS J2/DP or general state-transfer support is implied. Open/Save needs no native runtime.')

    def _opened(self, document):
        # The shared Material file picker may return the other supported editor
        # family. Preserve the actual same M owner and open its existing editor.
        if document['draft'].get('backend') == 'material.felupe':
            from .material_window import MaterialWindow
            window = MaterialWindow(self.client, auto_open=False)
            self._other_material_windows.append(window)
            window._opened(document); window.show()
            return
        super()._opened(document)

    def new_document(self):
        backend, accepted = QInputDialog.getItem(self, 'New Material law', 'Existing native constitutive adapter', list(NATIVE_LAWS), 0, False)
        if accepted:
            self._abandon(lambda: self.open_document(draft=self.model_default(backend)))
