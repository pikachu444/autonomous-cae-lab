"""One candidate-owned FreeCAD GUI process using the maintained FEM/Gmsh owner.

Invoked only by a trusted generated macro. No base/live document is opened for
writing. Qt callbacks remain on this process's native GUI thread.
"""
from pathlib import Path
import traceback
import uuid

from caelab.storage import load_json, save_json
from caelab.native_cad import unpack_project, sha
from .bridge import Owner
from .projects import save_native_copy
from .research_inputs import assign, value_at
from .candidate_correspondence import apply as apply_correspondence, validate_original_contacts

_active = None


class CandidateWorker:
    def __init__(self, config, App, Gui, QtCore):
        self.config, self.App, self.Gui, self.QtCore = config, App, Gui, QtCore
        self.folder = Path(config['output']).resolve()
        self.owner, self.document, self.mesh_queue, self.current_mesh = None, None, [], None
        self.record = {'state': 'RUNNING', 'phase': 'copy', 'engineering_release': 'NOT_RELEASED'}
        self.timer = QtCore.QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)

    def record_phase(self, phase):
        self.record.update(phase=phase)
        save_json(self.folder / 'candidate-preparation.json', self.record)

    def retain_editable(self):
        if self.owner is None:
            return
        # Preserve usable editable native bytes even when an ensuing step fails.
        # The already copied source/dependencies remain beside this raw fallback.
        path = self.folder / 'candidate-draft.FCStd'
        save_native_copy(self.owner.doc, path)
        self.record['editable_draft'] = str(path)
        self.record['editable_draft_sha256'] = sha(path)
        save_json(self.folder / 'candidate-preparation.json', self.record)

    def begin(self):
        try:
            settings = self.config['settings']
            self.recipe = settings['recipe']
            manifest, entry = unpack_project(self.config['source'], self.folder / 'working')
            if manifest.get('unavailable_dependencies'):
                raise ValueError('Saved design has unavailable external dependencies')
            self.document = self.App.openDocument(str(entry))
            self.document.UndoMode = 1
            self.App.setActiveDocument(self.document.Name)
            self.owner = Owner(self.document, self.folder / 'exchange', App=self.App, Gui=self.Gui,
                               document_id='P' + uuid.uuid4().hex)
            self.owner.before_design_action('candidate binding')
            self.record_phase('binding')
            validate_original_contacts(self.owner)
            for row in self.recipe['variables']:
                current = value_at(self.owner, row['target'], row['unit'])
                if current != row['value']:
                    raise ValueError('Saved typed variable differs from the frozen recipe: ' + row['label'])
            for row in self.recipe['variables']:
                assign(self.owner, row, settings['values'][row['id']])
            self.document.recompute()
            self.retain_editable()
            self.record_phase('recompute')
            bad = [obj.Label for obj in self.document.Objects if set(obj.State) & {'Invalid', 'Error', 'Recompute'}]
            if bad:
                raise ValueError('Native recompute failed: ' + ', '.join(bad))
            self.record_phase('correspondence')
            self.record['correspondence'] = apply_correspondence(self.owner, self.recipe['correspondence'])
            self.retain_editable()
            analysis = self.owner._object(self.recipe['analysis_id'])
            if self.recipe['route'] == 'contact':
                self.owner.fem.contact.prepare_meshes(analysis)
            for row in self.recipe['meshes']:
                mesh = self.owner._object(row['object_id'])
                if mesh not in analysis.Group or getattr(mesh, 'Suppressed', False) or mesh.Shape.Name != row['body_id']:
                    raise ValueError('Candidate mesh no longer belongs to its saved body/Analysis')
                if self.owner.fem._mesh_settings(mesh) != row['settings']:
                    raise ValueError('Candidate meshing settings differ from the saved recipe')
                self.mesh_queue.append(mesh)
            gmsh = self.config.get('gmsh')
            if gmsh:
                if not Path(gmsh).is_file():
                    raise ValueError('Configured Gmsh executable is unavailable')
                self.App.ParamGet('User parameter:BaseApp/Preferences/Mod/Fem/Gmsh').SetString('gmshBinaryPath', gmsh)
            self.record_phase('mesh')
            self.next_mesh()
        except Exception as error:
            self.fail(error)

    def next_mesh(self):
        if not self.mesh_queue:
            self.freeze()
            return
        self.current_mesh = self.mesh_queue.pop(0)
        directory = self.folder / 'meshes' / self.current_mesh.Name
        directory.mkdir(parents=True, exist_ok=False)
        receipt = self.owner.fem._generate(self.current_mesh, owned_directory=directory)
        self.record.setdefault('mesh_directories', []).append(str(directory))
        self.record['mesh_history_id'] = receipt['history_id']
        self.record['mesh_object_id'] = self.current_mesh.Name
        self.record_phase('mesh')
        self.timer.start()

    def poll(self):
        try:
            if self.current_mesh.Name in self.owner.fem._pending:
                return
            self.timer.stop()
            history = next(row for row in self.owner.fem._metadata()['mesh_history']
                           if row['id'] == self.record['mesh_history_id'])
            if history['state'] != 'SUCCEEDED' or history.get('run_admissibility') != 'QUALITY_GATES_PASSED':
                raise ValueError(history.get('error') or history.get('binding_error') or 'Generated mesh failed admission')
            self.owner.mesh_bindings.validate(self.current_mesh)
            self.retain_editable()
            self.next_mesh()
        except Exception as error:
            self.fail(error)

    def freeze(self):
        self.record_phase('freeze')
        operation = 'pre.contact.freeze' if self.recipe['route'] == 'contact' else 'pre.freeze'
        request = {'command_id': 'C' + uuid.uuid4().hex, 'document_id': self.owner.document_id,
                   'session_id': self.owner.session_id, 'expected_generation': self.owner.generation,
                   'operation': operation, 'arguments': {'analysis_id': self.recipe['analysis_id'],
                                                        'solver_id': self.recipe['solver_id']}}
        result = self.owner.dispatch(request)
        if result.get('status') != 'COMPLETED':
            raise ValueError(str(result.get('error') or result))
        snapshot = self.owner.export_root / result['result']['snapshot_relative']
        manifest = load_json(snapshot)
        editable = snapshot.parent / manifest['editable_project']
        self.record.update(state='PREPARED', phase='prepared', snapshot=str(snapshot),
                           editable_project=str(editable), editable_sha256=sha(editable),
                           solver_execution='NOT_PERFORMED')
        save_json(self.folder / 'candidate-preparation.json', self.record)
        self.finish(0)

    def fail(self, error):
        self.timer.stop()
        self.record.update(state='FAILED', error=str(error), error_type=type(error).__name__)
        try:
            self.retain_editable()
        except Exception as retain_error:
            self.record['editable_capture_error'] = str(retain_error)
        save_json(self.folder / 'candidate-preparation.json', self.record)
        (self.folder / 'native-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        self.finish(1)

    def finish(self, code):
        # No save question from an owned transient candidate window.
        self.timer.stop()
        for doc in list(self.App.listDocuments().values()):
            self.App.closeDocument(doc.Name)
        self.QtCore.QCoreApplication.exit(code)


def start(path):
    global _active
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore
    if not App.GuiUp:
        raise ValueError('Candidate Gmsh preparation requires the configured FreeCAD GUI host')
    _active = CandidateWorker(load_json(path), App, Gui, QtCore)
    QtCore.QTimer.singleShot(0, _active.begin)
