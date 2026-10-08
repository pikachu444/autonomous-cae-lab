"""FreeCADCmd acceptance: real edit/Undo/reopen and native Gmsh on a copied CAD.

Pass config via CAE_PRE_VERIFY_CONFIG. A success receipt is written only after
all assertions. This checks the native data path, not GUI click behavior.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import time
import traceback

import FreeCAD as App
import ObjectsFem
from femmesh.gmshtools import GmshTools

_owned_output = None


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run():
    global _owned_output
    config = json.loads(Path(os.environ['CAE_PRE_VERIFY_CONFIG']).read_text(encoding='utf-8-sig'))
    output = Path(config['output'])
    output.mkdir(parents=True, exist_ok=False)
    _owned_output = output
    original = Path(config['source'])
    before_hash = digest(original)
    copied = output / 'editable-input.FCStd'
    shutil.copy2(original, copied)
    doc = App.openDocument(str(copied))
    doc.UndoMode = 1
    support = doc.getObject('SupportBlock')
    final = doc.getObject('BoreCut4')
    assert support is not None and final is not None, 'Wrong fixture: required editable features missing'
    initial_length = support.Length.Value
    initial_volume = final.Shape.Volume
    initial_bounds = tuple(getattr(final.Shape.BoundBox, p) for p in ('XLength', 'YLength', 'ZLength'))
    doc.openTransaction('Acceptance — change support length')
    support.Length = initial_length + 2.0
    doc.recompute()
    assert final.Shape.isValid()
    assert abs(final.Shape.Volume - initial_volume) > 1e-6
    edited_volume = final.Shape.Volume
    doc.commitTransaction()
    doc.undo()
    doc.recompute()
    assert abs(support.Length.Value - initial_length) < 1e-10
    assert abs(final.Shape.Volume - initial_volume) < 1e-7
    doc.redo()
    doc.recompute()
    assert abs(final.Shape.Volume - edited_volume) < 1e-7
    doc.undo()
    doc.recompute()
    mesh = ObjectsFem.makeMeshGmsh(doc, 'MeshAcceptance')
    mesh.Shape = final
    mesh.CharacteristicLengthMax = 3.5
    mesh.CharacteristicLengthMin = 1.5
    mesh.ElementOrder = '2nd'
    doc.recompute()
    App.ParamGet('User parameter:BaseApp/Preferences/Mod/Fem/Gmsh').SetString('gmshBinaryPath', config['gmsh'])
    tool = GmshTools(mesh)
    tool.obj.WorkingDirectory = str(output / 'mesh')
    Path(tool.obj.WorkingDirectory).mkdir()
    started = time.perf_counter()
    tool.run(blocking=True)
    mesh_seconds = time.perf_counter() - started
    assert tool.process.exitCode() == 0, 'Gmsh process failed'
    # QProcess finished must have updated the actual native FemMesh.
    assert mesh.FemMesh.NodeCount > 0 and mesh.FemMesh.VolumeCount > 0, 'No actual mesh returned'
    counts = (mesh.FemMesh.NodeCount, mesh.FemMesh.VolumeCount)
    saved = output / 'verified-project.FCStd'
    doc.recompute()
    doc.saveAs(str(saved))
    App.closeDocument(doc.Name)
    reopened = App.openDocument(str(saved))
    assert abs(reopened.SupportBlock.Length.Value - initial_length) < 1e-10
    assert abs(reopened.BoreCut4.Shape.Volume - initial_volume) < 1e-7
    assert (reopened.MeshAcceptance.FemMesh.NodeCount, reopened.MeshAcceptance.FemMesh.VolumeCount) == counts
    assert digest(original) == before_hash
    receipt = dict(status='PASS', evidence_scope='native edit/undo/redo/gmsh/save/reopen; not GUI clicks or engineering approval',
                   source=str(original), source_sha256=before_hash, freecad='.'.join(App.Version()[:3]),
                   initial_length_mm=initial_length, changed_length_mm=initial_length+2,
                   volume_before_mm3=initial_volume, volume_changed_mm3=edited_volume,
                   bounds_mm=initial_bounds, nodes=counts[0], volume_elements=counts[1],
                   mesh_seconds=mesh_seconds, saved=str(saved), saved_sha256=digest(saved))
    (output / 'verification.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    App.closeDocument(reopened.Name)
    print(json.dumps(receipt))


try:
    run()
except Exception:
    print(traceback.format_exc())
    if _owned_output is not None:
        (_owned_output / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
    raise
