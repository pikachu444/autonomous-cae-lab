"""Read-only C1 proof, with a separate explicit installed-FreeCAD cold check.

Python CLI only checks retained bytes and the digest-authenticated BREP witness.
It does not imply native kernel restoration, Windows acceptance or a solve.
"""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import zipfile

from caelab.shell_model import digest
from apps.desktop_pre.shell_edit import _saved_brep_export_candidate, _brep_zero_identity

PUBLIC_SHA = '543356fc526483866e94eadfbf21d9b1f46286c9008283370896fb758239cd6e'
REQUEST_ID = 'PRO-B13-C1-FRESH-20261015-01'


def retained_proof(archive_path, output):
    """Verify the exact original fixture and retain a reproducible textual proof."""
    path, output = Path(archive_path), Path(output)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != PUBLIC_SHA:
        raise ValueError('Select the exact original 29,632-byte public C1 archive')
    output.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('Public input CRC failure')
        manifest = json.loads(archive.read('MANIFEST.json'))
        expected = {'MANIFEST.json', *(row['path'] for row in manifest['files'])}
        if len(archive.namelist()) != len(expected) or set(archive.namelist()) != expected:
            raise ValueError('Unexpected or duplicate public input member')
        payload = {}
        for row in manifest['files']:
            value = archive.read(row['path'])
            if len(value) != row['bytes'] or hashlib.sha256(value).hexdigest() != row['sha256']:
                raise ValueError('Public input manifest differs: ' + row['path'])
            payload[row['path']] = value
    saved = json.loads(payload['stamp/saved-binding.json'])
    current = json.loads(payload['stamp/current-stamp.json'])
    before = _saved_brep_export_candidate(payload['stamp/saved-native-CurvedPatch.Shape.brp'].decode('ascii'))
    after = payload['stamp/CurvedPatch-exportBrepToString.brep'].decode('ascii')
    if digest(before) != saved['mesh_source']['brep'] or digest(after) != current['mesh_source']['brep']:
        raise ValueError('The reconstructed candidate is not authenticated by the old binding')
    if _brep_zero_identity(before) != _brep_zero_identity(after):
        raise ValueError('The exact supported plane-axis signed-zero comparison differs')
    changes = [(i, a, b) for i, (a, b) in enumerate(zip(before.split(), after.split())) if a != b]
    if len(before.split()) != len(after.split()) or [(a, b) for _, a, b in changes] != [('0', '-0'), ('0', '-0')]:
        raise ValueError('Unexpected retained byte comparison')
    (output/'authenticated-old-export-candidate.brep').write_bytes(before.encode('ascii'))
    (output/'recorded-cold-export.brep').write_bytes(after.encode('ascii'))
    (output/'old-to-cold.diff').write_text(''.join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile='hash-authenticated-old-candidate', tofile='recorded-cold-export')), encoding='utf-8')
    report = {'request_id': REQUEST_ID, 'status': 'RETAINED_BYTES_PROOF_PASSED',
        'native_execution': 'NOT_RUN', 'windows_acceptance': 'NOT_RUN',
        'presave_runtime_observation': 'NOT_AVAILABLE; candidate authenticated by previously recorded digest',
        'input_archive_sha256': PUBLIC_SHA, 'old_json_digest': digest(before), 'cold_json_digest': digest(after),
        'old_candidate_bytes': len(before), 'cold_recorded_bytes': len(after),
        'old_candidate_raw_sha256': hashlib.sha256(before.encode('ascii')).hexdigest(),
        'cold_recorded_raw_sha256': hashlib.sha256(after.encode('ascii')).hexdigest(),
        'token_differences': changes, 'changed_fields': ['/mesh_source/brep', '/reference_geometry/CurvedPatch/brep'],
        'model_mesh_placement_guard': 'UNCHANGED; bytes proof is not a replacement for current-owner checks',
        'original_archive_unchanged': path.read_bytes() == data}
    (output/'proof.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def native_cold_check(root, project, *, analysis_id='ShellAnalysis'):
    """Run only in an explicitly owned installed FreeCAD GUI process.

    Root passes the original saved .caepre from the verified archive. The
    existing checker owns unpack/open/remember_open/Owner/close and checks
    draft/applied equality plus ready; this wrapper never creates geometry,
    applies/rebinds, saves the source, freezes or launches any solver.
    The returned observation, not the process exit code, is the result.
    """
    import os
    import sys
    import traceback
    if os.environ.get('CAELAB_B13_C1_OWNED_CHECK') != REQUEST_ID:
        raise RuntimeError('Use a new explicitly owned native check process')
    import FreeCAD as App
    if list(App.Version())[:3] != ['1', '1', '4'] or not App.GuiUp:
        raise RuntimeError('Use the installed FreeCAD 1.1.4 GUI runtime')
    from examples.b13.check_in_freecad import read_saved_project
    root, project = Path(root), Path(project)
    root.mkdir(parents=True, exist_ok=False)
    original = project.read_bytes()
    report = {'request_id': REQUEST_ID, 'execution': 'FAILED', 'native_version': list(App.Version()),
        'platform': sys.platform, 'solver': 'NOT_RUN', 'native_apply': 'NOT_RUN',
        'engineering_qualification': False, 'source_project_sha256': hashlib.sha256(original).hexdigest()}
    try:
        report['cold_read'] = read_saved_project(root, project, 'shell', analysis_id)
        if project.read_bytes() != original:
            raise ValueError('Original saved project bytes changed')
        report.update(execution='SAME_SAVED_MEMBER_COLD_READY', original_project_unchanged=True)
    except BaseException as exc:
        report.update(error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc(),
                      original_project_unchanged=project.read_bytes() == original)
    finally:
        (root/'c1-native-cold-observation.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('public_inputs', type=Path)
    parser.add_argument('output', type=Path, help='A new directory; never overwrites earlier observations')
    args = parser.parse_args()
    print(json.dumps(retained_proof(args.public_inputs, args.output), ensure_ascii=False, indent=2))
