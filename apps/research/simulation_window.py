"""Direct editor for the admitted native structural/explicit/material declarations.

Reuses the PDE document editor's typed fields, revision commands and actual
result selectors. It never exposes a general solver-card or Python editor.
"""
import argparse
import math
import os
import sys

from PySide6.QtWidgets import QApplication, QPushButton
from caelab.workbench_client import Client
from caelab.simulation_document import BACKENDS, default_draft, diagnostics, support_details
from .pde_window import PDEWindow, display


class SimulationWindow(PDEWindow):
    document_kind, tool_label = 'simulation', 'Simulation'
    model_backends = BACKENDS
    model_default, model_diagnostics, model_support = map(staticmethod, (default_draft, diagnostics, support_details))
    settings_sections = [(label, ('settings', name)) for name, label in (
        ('domain', 'Domain / physical coordinates'), ('case', 'Supported model family'),
        ('geometry', 'Geometry definition'), ('mesh', 'Mesh / function space'),
        ('material', 'Material / stress-free state'), ('constitutive', 'Constitutive law'),
        ('history', 'Load / deformation history'), ('time', 'Physical clock'),
        ('conductivity', 'Conductivity / Picard coefficient'), ('heat_source', 'Volumetric heat source'),
        ('boundary_temperature', 'Temperature boundary'), ('temperature', 'Captured temperature input'),
        ('linearization_temperature', 'Optional lagged temperature'), ('limits', 'Original numerical limits'),
        ('validation', 'Numerical acceptance'), ('analysis', 'Analysis controls'),
        ('loads', 'Loads'), ('boundary_conditions', 'Boundary conditions'))]

    @staticmethod
    def field_label(path):
        return ' / '.join(str(k).replace('_', ' ') for k in path[1:])

    def _build_ui(self):
        super()._build_ui()
        self.new_action.setText('&New simulation declaration…')
        self.open_action.setText('&Open simulation declaration…')
        self.identity.setText('Opening simulation document…')
        self.validate_button.setText('Check declared inputs / support')
        self.plan_button.setObjectName('simulationNumericalPlan')
        self.readiness_button = QPushButton('Inspect installed runtime')
        self.readiness_button.setToolTip('Runs the existing dependency/version discovery only; no solver, new credentials or model call')
        self.readiness_button.clicked.connect(self.inspect_runtime)
        self.statusBar().addPermanentWidget(self.readiness_button)

    def inspect_runtime(self):
        backend = self.edited_draft().get('backend')
        def accepted(result):
            self.messages.appendPlainText('Runtime inspection for ' + str(backend) + ':\n' + display(result))
            self.message.setText(str(result.get('dependencies', 'NOT_CHECKED')) + ' · solver execution NOT_PERFORMED')
        return self._call(lambda: self.client.backend_readiness(backend), accepted)

    def _show_document(self, document, *, preserve_draft=None):
        # Include every existing adapter setting as a normal editable section;
        # model validation, not a copied schema, decides admission.
        draft = preserve_draft if preserve_draft is not None else document['draft']
        settings = draft.get('settings', {})
        base = type(self).settings_sections
        known = {path[-1] for _, path in base}
        self.settings_sections = base + [(str(k).replace('_', ' ').capitalize(), ('settings', k))
            for k in settings if k not in known] if isinstance(settings, dict) else base
        super()._show_document(document, preserve_draft=preserve_draft)

    def _show_support(self, draft=None, checks=None, details=None):
        draft = self._draft if draft is None else draft
        details = details if details is not None else self.document.get('simulation_support', {}) if self.document else {}
        checks = diagnostics(draft) if checks is None else checks
        self.equation.setText('Declared model: ' + str(draft.get('backend', '')))
        self.space.setText('The model retains its explicit units, material convention, physical clock and original numerical limits.')
        self.support.setText('Edit / Save requires no solver. Only the admitted declaration can run; general CAD contact, DP, damage and arbitrary native cards are not implied.')
        self.messages.setPlainText('\n'.join(['Input diagnostics:', *[row['message'] for row in checks],
            'Supported model:', *details.get('limitations', []), 'Declared inputs / transfer ports:',
            display(details.get('declaration') or details.get('ports') or {}),
            'Runtime: NOT_PROBED · Engineering: NOT_RELEASED']))

    def _draw_domain(self, path=None):
        axes = self.domain_axes
        axes.clear()
        settings = self.edited_draft().get('settings', {})
        domain = settings.get('domain', {}) if isinstance(settings, dict) else {}
        lengths = domain.get('lengths') if isinstance(domain, dict) else None
        if isinstance(lengths, list) and len(lengths) == 2 and all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in lengths):
            x, y = lengths
            axes.plot([0, x, x, 0, 0], [0, 0, y, y, 0], color='#334155')
            axes.set_aspect('equal')
            axes.set_xlabel('x [' + str(domain.get('unit', '?')) + ']')
            axes.set_ylabel('y [' + str(domain.get('unit', '?')) + ']')
            axes.set_title('Declared domain · no computed deformation is shown here')
        else:
            axes.set_axis_off()
            axes.text(.02, .95, 'Edit the selected model definition.\n\nNative fields / histories appear below only from a retained run.\nThe native CAD editor remains the owner of editable CAD geometry.',
                      transform=axes.transAxes, va='top', wrap=True)
        self.domain_canvas.draw_idle()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--service', default=os.environ.get('CAELAB_SERVICE_URL'))
    parser.add_argument('--document-id')
    options = parser.parse_args(argv)
    if not options.service:
        parser.error('--service or CAELAB_SERVICE_URL is required')
    from .desktop import launch_tool, open_document_result, open_domain_plan
    client = Client(options.service)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = SimulationWindow(client, document_id=options.document_id,
        runner_open=lambda job: launch_tool(client, 'runner', job_id=job),
        result_open=lambda doc, job, **kwargs: open_document_result(client, doc, job, **kwargs),
        plan_open=lambda doc, **kwargs: open_domain_plan(client, doc, **kwargs))
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
