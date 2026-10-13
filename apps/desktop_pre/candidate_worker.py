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



def verify_saved_project(path, folder, recipe, values, App, Gui):
    """Read the exact retained model; never rebind or update its fingerprints."""
    from .mesh_binding import PROPERTY_NAME
    before = sha(path)
    manifest, entry = unpack_project(path, folder)
    if manifest.get('unavailable_dependencies'):
        raise ValueError('Prepared design has unavailable saved dependencies')
    doc = App.openDocument(str(entry))
    analysis = doc.getObject(recipe['analysis_id'])
    for row in recipe['meshes']:
        mesh = doc.getObject(row['object_id'])
        if (mesh is None or analysis is None or mesh not in analysis.Group
                or getattr(mesh, 'Suppressed', False)
                or getattr(getattr(mesh, 'Shape', None), 'Name', None) != row['body_id']
                or PROPERTY_NAME not in mesh.PropertiesList):
            raise ValueError('Reopened candidate mesh binding is missing or changed')
    owner = Owner(doc, Path(folder) / 'inspection', App=App, Gui=Gui)
    try:
        validate_original_contacts(owner)
        for row in recipe['meshes']:
            owner.mesh_bindings.validate(owner._object(row['object_id']))
        from .assembly_candidates import verify as verify_pose
        pose = verify_pose(owner, recipe, values, solve=True)
        # Assembly solve/native binder evaluation must not invalidate the
        # retained mesh or conditions after their initial readback checks.
        if pose:
            validate_original_contacts(owner)
            for row in recipe['meshes']:
                owner.mesh_bindings.validate(owner._object(row['object_id']))
        for row in recipe['variables']:
            if row['target']['family'] == 'joint_coordinate':
                continue  # Measured in the explicit angular/length tolerance above.
            if value_at(owner, row['target'], row['unit']) != values[row['id']]:
                raise ValueError('Reopened candidate variable changed: ' + row['label'])
        if sha(path) != before:
            raise ValueError('Prepared project changed during read-only reopening')
        return {'state': 'VERIFIED', 'project_sha256': before,
                'mesh_objects': [row['object_id'] for row in recipe['meshes']],
                'contact_repair_performed': False, 'assembly_pose': pose}
    finally:
        owner.close()


def prepare_saved_pose(owner, recipe, values, folder, *, adopt_owner):
    """Candidate-only, bounded native Placement roundtrip before any meshing.

    FreeCAD 1.1.4 restores Placement from its saved axis/angle, not the saved
    quaternion. Evaluate occurrence Supports from that restored placement once,
    map ORIGINAL FEM targets to the stable geometry once, then prove another
    save/reopen is unchanged. Frozen/retained-result readers never call this.
    """
    from .assembly_candidates import _verify_coordinate, verify
    from .occurrence_fem import binding_targets, refresh_bindings
    from .mesh_binding import PROPERTY_NAME
    from .projects import exact_shape_serialization, remember_open

    folder = Path(folder).resolve()
    stage = folder / 'pose-save'
    stage.mkdir(parents=True, exist_ok=False)
    saved = recipe['assembly']
    report = {'state': 'PREPARING', 'phase': 'placement_save',
              'mesh_execution': 'NOT_PERFORMED', 'solver_execution': 'NOT_PERFORMED',
              'mesh_rebound': False, 'archives': []}

    def targets():
        return binding_targets(owner, owner._object(recipe['analysis_id']), saved['connection'])

    def mesh_stamps():
        return {row['object_id']: getattr(owner._object(row['object_id']), PROPERTY_NAME, None)
                for row in recipe['meshes']}

    original_stamps = mesh_stamps()
    def unchanged_stamps():
        if mesh_stamps() != original_stamps:
            raise ValueError('Pose serialization changed a retained mesh association')

    def checkpoint(phase):
        report['phase'] = phase
        save_json(stage / 'receipt.json', report)

    def private_documents():
        # This function is only for a candidate-owned copied project graph.
        # Never close or save a dependency still pointing to a user's source.
        documents = list(owner.project._documents())
        for doc in documents:
            if not doc.FileName or not Path(doc.FileName).resolve().is_relative_to(folder):
                raise ValueError('Pose staging requires candidate-owned document copies')
        return documents

    def roundtrip(label):
        nonlocal owner
        documents = private_documents()
        before = targets()
        archive = stage / (label + '.caepre')
        with exact_shape_serialization(owner.App):
            result = owner.project.save(archive)
        if result.get('unavailable_dependencies'):
            raise ValueError('Pose staging has unavailable saved dependencies')
        if targets() != before:
            raise ValueError('Saving the candidate changed its occurrence geometry')
        unchanged_stamps()
        digest = sha(archive)
        report['archives'].append({'path': str(archive), 'sha256': digest,
                                   'retained_project': result.get('retained_project')})
        checkpoint(label + '_reopen')
        App, Gui = owner.App, owner.Gui
        owner.close()  # Stop observers before disposing of their native objects.
        owner = None
        adopt_owner(None)
        for doc in documents:
            App.closeDocument(doc.Name)
        manifest, entry = unpack_project(archive, stage / label)
        if manifest.get('unavailable_dependencies') or sha(archive) != digest:
            raise ValueError('Saved pose archive is unavailable or changed')
        existing = list(App.listDocuments().values())
        document = App.openDocument(str(entry))
        if any(document is other for other in existing) or Path(document.FileName).resolve() != entry.resolve():
            raise ValueError('Pose reopen reused an unrelated native document')
        document.UndoMode = 1
        App.setActiveDocument(document.Name)
        remember_open(document, manifest, archive)
        owner = Owner(document, stage / (label + '-exchange'), App=App, Gui=Gui)
        adopt_owner(owner)
        private_documents()
        # Binary BREP must survive the read itself. Only the FIRST subsequent
        # native Support evaluation is an explicit pre-mesh write boundary.
        if targets() != before:
            raise ValueError('Saved occurrence geometry changed during native restoration')
        unchanged_stamps()

    try:
        checkpoint('placement_save')
        roundtrip('placement')
        checkpoint('restored_support')
        _verify_coordinate(owner, recipe, values, solve=True)
        before = targets()
        refresh_bindings(owner, owner._object(recipe['analysis_id']),
                         saved['connection'], require_unchanged=False)
        after = targets()
        report['updated_bodies'] = [name for name in before if before[name] != after[name]]
        report['after_refresh'] = verify(owner, recipe, values, solve=True)
        unchanged_stamps()

        # No earlier apply/recapture: region/contact/local-size metadata still
        # carries the original keys, now resolved against the FINAL geometry.
        checkpoint('correspondence')
        report['correspondence'] = apply_correspondence(owner, recipe['correspondence'])
        validate_original_contacts(owner)
        report['after_correspondence'] = verify(owner, recipe, values, solve=True)
        unchanged_stamps()

        checkpoint('stable_save')
        roundtrip('stable')
        checkpoint('strict_reopen')
        report['verified'] = verify(owner, recipe, values, solve=True)
        validate_original_contacts(owner)
        unchanged_stamps()
        report.update(state='STABLE', phase='complete')
        save_json(stage / 'receipt.json', report)
        return owner, report
    except Exception as error:
        report.update(state='FAILED', error=str(error), error_type=type(error).__name__)
        save_json(stage / 'receipt.json', report)
        # Both archives and the latest live copied document are retained.
        # The worker captures the current editable fallback through adopt_owner.
        raise


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
        save_native_copy(self.owner.doc, path, App=self.App)
        self.record['editable_draft'] = str(path)
        self.record['editable_draft_sha256'] = sha(path)
        save_json(self.folder / 'candidate-preparation.json', self.record)

    def begin(self):
        try:
            settings = self.config['settings']
            self.recipe = settings['recipe']
            if self.recipe.get('assembly'):
                # Candidate GUI has its own user/system configuration files.
                # Load the installed native joint proxies before restoring them.
                self.Gui.activateWorkbench('AssemblyWorkbench')
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
            from .assembly_candidates import validate_source, drive
            validate_source(self.owner, self.recipe)
            for row in self.recipe['variables']:
                current = value_at(self.owner, row['target'], row['unit'])
                equal = current == row['value']
                if row['target']['family'] == 'joint_coordinate':
                    from .assembly_candidates import _unit_value, ANGLE_TOLERANCE_RAD, LENGTH_TOLERANCE_MM
                    unit = 'rad' if row['target']['field'] == 'angle' else 'mm'
                    delta = _unit_value(self.owner, current - row['value'], row['unit'], unit)
                    equal = abs(delta) <= (ANGLE_TOLERANCE_RAD if unit == 'rad' else LENGTH_TOLERANCE_MM)
                if not equal:
                    raise ValueError('Saved typed variable differs from the frozen recipe: ' + row['label'])
            for row in self.recipe['variables']:
                if row['target']['family'] != 'joint_coordinate':
                    assign(self.owner, row, settings['values'][row['id']])
            self.document.recompute()
            self.retain_editable()
            self.record_phase('recompute')
            bad = [obj.Label for obj in self.document.Objects if set(obj.State) & {'Invalid', 'Error', 'Recompute'}]
            if bad:
                raise ValueError('Native recompute failed: ' + ', '.join(bad))
            if self.recipe.get('assembly'):
                self.record_phase('pose')
                self.record['assembly_pose'] = drive(self.owner, self.recipe, settings['values'])
                self.retain_editable()
                self.record_phase('pose_serialization')
                self.owner, stabilization = prepare_saved_pose(
                    self.owner, self.recipe, settings['values'], self.folder,
                    adopt_owner=self.adopt_working_owner)
                self.record['pose_serialization'] = stabilization
                self.record['correspondence'] = stabilization['correspondence']
            else:
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

    def adopt_working_owner(self, owner):
        self.owner = owner
        self.document = owner.doc if owner is not None else None
        # Every downstream Analysis/mesh lookup is through this fresh owner.
        self.mesh_queue, self.current_mesh = [], None

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
        from .assembly_candidates import verify as verify_pose
        self.record_phase('pose_after_mesh' if self.recipe.get('assembly') else 'freeze')
        pose = verify_pose(self.owner, self.recipe, self.config['settings']['values'], solve=True)
        if pose:
            self.record['assembly_pose_after_mesh'] = pose
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
        self.record.update(snapshot=str(snapshot), editable_project=str(editable),
                           editable_sha256=sha(editable), solver_execution='NOT_PERFORMED')
        self.record_phase('saved_reopen')
        # The native process owns all these transient documents. Release the
        # live originals so the check reads saved bytes, not an open document.
        self.owner.close()
        self.owner = None
        self.document = None
        for doc in list(self.App.listDocuments().values()):
            self.App.closeDocument(doc.Name)
        self.record['saved_reopen'] = verify_saved_project(
            editable, self.folder / 'saved-check', self.recipe,
            self.config['settings']['values'], self.App, self.Gui)
        self.record.update(state='PREPARED', phase='prepared')
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
