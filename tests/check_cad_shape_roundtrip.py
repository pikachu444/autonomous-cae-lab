"""Optional native saved-shape probe. No mesher, solver, or reference repair.

Call run(project, fresh_short_output, object_names, App) from a FreeCAD macro.
The source archive stays immutable; new copies and BREP diagnostics go to output.
"""
from pathlib import Path
import uuid

from caelab.native_cad import unpack_project, sha
from caelab.storage import save_json
from apps.desktop_pre.fem_edit import _target
from apps.desktop_pre.projects import save_native_copy


def _read(doc, names, folder):
    folder.mkdir()
    result = {}
    for name in names:
        obj = doc.getObject(name)
        if obj is None:
            raise ValueError('Missing inspected object: ' + name)
        faces = ['Face' + str(i + 1) for i in range(len(obj.Shape.Faces))]
        result[name] = _target(obj, faces)
        (folder / (name + '.brep')).write_text(obj.Shape.exportBrepToString(), encoding='utf-8')
        for face_name in faces:
            shape = getattr(obj.Shape, 'Faces')[int(face_name[4:]) - 1]
            (folder / (name + '-' + face_name + '.brep')).write_text(
                shape.exportBrepToString(), encoding='utf-8')
    return result


def run(project, output, object_names, App):
    project, output = Path(project).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_hash = sha(project)
    manifest, entry = unpack_project(project, output / 'original')
    doc = App.openDocument(str(entry))
    before = _read(doc, object_names, output / 'before')
    saved = output / ('copy-' + uuid.uuid4().hex[:8] + '.FCStd')
    save_native_copy(doc, saved, App=App)
    after_save = _read(doc, object_names, output / 'after-save')
    App.closeDocument(doc.Name)
    reopened = App.openDocument(str(saved))
    try:
        after_open = _read(reopened, object_names, output / 'after-open')
    finally:
        App.closeDocument(reopened.Name)
    receipt = {'source_sha256': source_hash, 'source_unchanged': sha(project) == source_hash,
               'save_did_not_change_live_targets': before == after_save,
               'cold_targets_match': before == after_open,
               'before': before, 'after_save': after_save, 'after_open': after_open,
               'existing_metadata_repaired': False, 'mesh_solver_execution': 'NOT_PERFORMED'}
    save_json(output / 'receipt.json', receipt)
    return receipt
