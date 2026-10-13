"""Bounded native pose/save check; call functions in separate FreeCAD GUI processes.

No mesher/FE solver is called. Native Motion is used only by prepare().
reopen() never drives the coordinate, rebinds references or repairs a target.
"""
from copy import deepcopy
from pathlib import Path
import json


def prepare(fixture_path, value, output):
    import FreeCAD as App
    import FreeCADGui as Gui
    Gui.activateWorkbench('AssemblyWorkbench')
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.assembly_candidates import validate_source, drive, verify
    from apps.desktop_pre.candidate_correspondence import apply, validate_original_contacts
    from apps.desktop_pre.fem_edit import _target
    from caelab.native_cad import unpack_project, sha

    fixture = json.loads(Path(fixture_path).read_text(encoding='utf-8'))
    folder = Path(output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    source = Path(fixture['project'])
    if sha(source) != fixture['sha256']:
        raise ValueError('Fixture source changed')
    manifest, entry = unpack_project(source, folder / 'source')
    doc = App.openDocument(str(entry))
    owner = Owner(doc, folder / 'exchange', App=App, Gui=Gui)
    recipe, values = fixture['recipe'], {'pose': float(value)}
    validate_original_contacts(owner)
    validate_source(owner, recipe)
    before = {row['body_id']: _target(owner._object(row['body_id']), [])
              for row in recipe['assembly']['connection']['bodies']}
    reached = drive(owner, recipe, values)
    mapped = apply(owner, recipe['correspondence'])
    validate_original_contacts(owner)
    verified = verify(owner, recipe, values, solve=True)
    after = {row['body_id']: _target(owner._object(row['body_id']), []) for row in recipe['assembly']['connection']['bodies']}
    moving = recipe['assembly']['definition']['moving_occurrence']
    body = next(row['body_id'] for row in recipe['assembly']['connection']['bodies'] if row['occurrence_id'] == moving)
    if value != 0. and before[body] == after[body]:
        raise ValueError('Pose did not change the actual FEM occurrence geometry')
    saved = owner.project.save()
    after_save = {name: _target(owner._object(name), []) for name in after}
    if after_save != after:
        raise ValueError('Saving the candidate changed its verified occurrence geometry')
    project = owner.export_root / Path(saved['retained_project']) if not Path(saved['retained_project']).is_absolute() else Path(saved['retained_project'])
    if sha(source) != fixture['sha256']:
        raise ValueError('Original project changed')
    receipt = {'project': str(project), 'sha256': sha(project), 'source': str(source),
               'source_sha256': fixture['sha256'], 'recipe': deepcopy(recipe), 'values': values,
               'reached': reached, 'after_normal_solve': verified, 'correspondence': mapped,
               'targets': after, 'save_did_not_change_live_targets': True, 'mesh_execution': 'NOT_PERFORMED', 'solver_execution': 'NOT_PERFORMED'}
    path = folder / 'pose.json'
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    return owner, path


def reopen(receipt_path, output):
    import FreeCAD as App
    import FreeCADGui as Gui
    Gui.activateWorkbench('AssemblyWorkbench')
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.assembly_candidates import verify
    from apps.desktop_pre.candidate_correspondence import validate_original_contacts
    from apps.desktop_pre.fem_edit import _target
    from caelab.native_cad import unpack_project, sha

    record = json.loads(Path(receipt_path).read_text(encoding='utf-8'))
    folder = Path(output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    if sha(record['project']) != record['sha256'] or sha(record['source']) != record['source_sha256']:
        raise ValueError('Saved candidate/source changed')
    manifest, entry = unpack_project(record['project'], folder / 'source')
    doc = App.openDocument(str(entry))
    owner = Owner(doc, folder / 'exchange', App=App, Gui=Gui)
    validate_original_contacts(owner)
    before = {name: _target(owner._object(name), []) for name in record['targets']}
    if before != record['targets']:
        raise ValueError('Cold occurrence geometry differs before native solve')
    actual = verify(owner, record['recipe'], record['values'], solve=True)
    after = {name: _target(owner._object(name), []) for name in record['targets']}
    validate_original_contacts(owner)
    if after != before or sha(record['project']) != record['sha256']:
        raise ValueError('Cold native solve changed saved occurrence geometry')
    result = {'state': 'VERIFIED', 'actual': actual, 'motion_executed': False,
              'before_after_targets_identical': True,
              'mesh_execution': 'NOT_PERFORMED', 'solver_execution': 'NOT_PERFORMED'}
    (folder / 'reopen.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return owner, result
