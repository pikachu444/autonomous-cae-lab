param(
    [Parameter(Mandatory=$true)][string]$WorkRoot,
    [Parameter(Mandatory=$true)][string]$Python,
    [string]$SevenZip
)
$ErrorActionPreference = 'Stop'
if (-not $SevenZip) {
    $command = Get-Command 7z.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { $SevenZip = $command.Source }
    else { $SevenZip = Join-Path $env:ProgramFiles '7-Zip/7z.exe' }
}
$repo = Split-Path -Parent $PSScriptRoot
# Use the existing artifact verifier; do not regenerate its pins after copying.
$code = @'
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True
root, repo, seven = (Path(p).resolve(strict=True) for p in sys.argv[1:])
sys.path.insert(0, str(repo))
from apps.desktop_post.native_exit_abi import verify_artifact, file_sha256

def require(condition, message):
    if not condition:
        raise ValueError(message)

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def regular(path):
    require(not (path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT),
            'Links/reparse points are not package inputs: ' + str(path))

def copy_file(source, target):
    regular(source)
    expected = file_sha256(source)
    if target.exists():
        require(file_sha256(target) == expected, 'Conflicting package file: ' + str(target))
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    require(file_sha256(target) == expected == file_sha256(source), 'Copy changed: ' + str(source))

def copy_tree(source, target, exclude=()):
    regular(source)
    require(source.is_dir(), 'Missing required directory: ' + str(source))
    for folder, dirs, files in os.walk(source, followlinks=False):
        base = Path(folder)
        for name in dirs:
            regular(base / name)
        dirs[:] = [name for name in dirs if name not in exclude and name != '__pycache__']
        for name in files:
            if not name.endswith(('.pyc', '.pyo')):
                copy_file(base / name, target / (base / name).relative_to(source))

out = root / 'recovery'
require(not out.exists(), 'Preserve existing recovery output; use a new SDK work directory')
evidence = read(root / 'build-evidence.json')
require(evidence.get('native_backend') == 'PLUGIN_LOAD_EXISTING_COMPARISON_SAVE_AND_COLD_REOPEN_PASSED',
        'Only the successful existing SDK/native-backend check may be packaged')
require(evidence.get('sdk_build') == 'RUNTIME_AND_DEVELOPMENT_INSTALL_COMPLETED', 'SDK install incomplete')
require(evidence['python']['version'] == '3.12.10' and evidence['python']['bits'] == 64,
        'Requires the recorded official CPython 3.12.10 x64 prefix')
prefix = Path(evidence['python']['prefix']).resolve(strict=True)
runtime = root / 'runtime'
plugins = list((root / 'plugin-build/bin').rglob('CaePostExit.dll'))
require(len(plugins) == 1, 'Expected one exact built plugin')
plugin = plugins[0]
manifest = verify_artifact(plugin, runtime)
require(file_sha256(plugin) == evidence['plugin_sha256'], 'Build/plugin receipt differs')
require(file_sha256(prefix / 'python312.dll') == evidence['python_dll_sha256'] ==
        file_sha256(runtime / 'bin/python312.dll'), 'Official Python DLL differs from the pinned runtime')
sdk = read(root / 'sdk-evidence.json')
require(file_sha256(root / 'sdk-evidence.json') == manifest['build']['sdk_evidence_sha256'],
        'SDK evidence differs from the artifact')
require(sdk.get('runtime_relationship') == 'same-sdk-build', 'Requires this same-build SDK/runtime')
for name, expected in sdk['files'].items():
    path = Path(name).resolve(strict=True)
    require(path.is_relative_to(root) and file_sha256(path) == expected, 'SDK provenance changed: ' + name)
inputs = read(root / 'inputs.json')
require((inputs['paraview_version'], inputs['qt_version'], inputs['numpy_version']) ==
        ('6.2.0', '6.9.0', '2.3.5'), 'SDK input versions differ')
wheel_info = next(row for row in inputs['inputs'] if row['name'] == 'numpy')
require(wheel_info['file'] == 'numpy-2.3.5-cp312-cp312-win_amd64.whl', 'Wrong NumPy wheel')
wheel = root / 'downloads' / wheel_info['file']
require(file_sha256(wheel) == wheel_info['sha256'], 'NumPy wheel changed')
for name in ('python.exe', 'pythonw.exe', 'python3.dll', 'LICENSE.txt', 'Lib/os.py',
             'Lib/encodings/__init__.py', 'DLLs/_ssl.pyd'):
    require((prefix / name).is_file(), 'Missing official Python payload: ' + name)
require((runtime / 'bin/platforms/qwindows.dll').is_file(), 'Missing deployed Qt Windows platform')
require((runtime / 'bin/pvpython.exe').is_file(), 'Missing installed pvpython')
require(any('platforms/qwindows.dll' in p.replace('\\', '/') for p in manifest['runtime_files']),
        'Qt platform must be in the existing artifact pins')

# Only this new child is written. Neither original outputs nor Python packages are modified.
out.mkdir()
bundle = out / 'post-runtime'
bundle.mkdir()
copy_tree(runtime, bundle / 'runtime')
copy_file(plugin, bundle / 'plugin/CaePostExit.dll')
copy_file(plugin.with_suffix('.dll.manifest.json'), bundle / 'plugin/CaePostExit.dll.manifest.json')
pybin = bundle / 'runtime/bin'
for name in ('python.exe', 'pythonw.exe', 'python3.dll', 'python312.dll', 'LICENSE.txt'):
    copy_file(prefix / name, pybin / name)
copy_tree(prefix / 'Lib', pybin / 'Lib', exclude=('site-packages',))
copy_tree(prefix / 'DLLs', pybin / 'DLLs')
if (prefix / 'tcl').exists():
    copy_tree(prefix / 'tcl', pybin / 'tcl')

# Admit only this exact wheel's runtime directories, including its bundled DLLs/licenses.
numpy_dirs = {'numpy', 'numpy.libs', 'numpy-2.3.5.dist-info'}
with zipfile.ZipFile(wheel) as archive:
    members = archive.infolist()
    require({PurePosixPath(m.filename).parts[0] for m in members} >= numpy_dirs,
            'NumPy runtime or license metadata missing')
    require(any('/licenses/' in m.filename.lower() for m in members), 'NumPy licenses missing')
    for member in members:
        relative = PurePosixPath(member.filename)
        require(not relative.is_absolute() and '..' not in relative.parts and
                '\\' not in member.filename and ':' not in member.filename and
                not stat.S_ISLNK(member.external_attr >> 16), 'Unsafe NumPy wheel entry')
        if member.is_dir() or relative.parts[0] not in numpy_dirs:
            continue
        content = archive.read(member)
        installed = prefix / 'Lib/site-packages' / Path(*relative.parts)
        require(installed.is_file(), 'Installed NumPy file missing: ' + str(relative))
        regular(installed)
        # pip rewrites RECORD when installing scripts; retain the wheel's original index.
        require(relative.name == 'RECORD' or hashlib.sha256(content).hexdigest() == file_sha256(installed),
                'Installed NumPy differs from the fixed wheel: ' + str(relative))
        target = pybin / 'Lib/site-packages' / Path(*relative.parts)
        require(not target.exists(), 'Unexpected NumPy payload collision')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

for name in ('inputs.json', 'build-evidence.json', 'sdk-evidence.json',
             'plugin-build/cae-post-exit-build-info.json'):
    copy_file(root / name, bundle / 'provenance' / name)
for name in sdk['files']:
    source = Path(name).resolve(strict=True)
    copy_file(source, bundle / 'provenance/sdk-files' / source.relative_to(root))
copy_tree(root / 'qt/source-license-notices', bundle / 'licenses/Qt')
for module in ('qtbase', 'qttools', 'qtsvg', 'qt5compat'):
    require((bundle / 'licenses/Qt' / module / 'LICENSE.LGPL3').is_file(), 'Qt notice missing: ' + module)
    require((root / 'qt/sbom' / (module + '-6.9.0.spdx.json')).is_file(), 'Qt third-party SBOM missing: ' + module)
copy_tree(root / 'qt/sbom', bundle / 'licenses/Qt/sbom')
for folder in ('doc', 'licenses', 'LICENSES'):
    if (root / 'qt' / folder).exists():
        for path in (root / 'qt' / folder).rglob('*'):
            if path.is_file() and (path.name.lower().startswith(('license', 'copyright', 'copying', 'notice'))
                                   or 'license' in path.parts or 'licenses' in path.parts):
                copy_file(path, bundle / 'licenses/Qt' / path.relative_to(root / 'qt'))
source = root / 'source/ParaView-v6.2.0'
require((source / 'Copyright.txt').is_file(), 'ParaView copyright missing')
for path in source.rglob('*'):
    if path.is_file() and path.name.lower().startswith(('license', 'copyright', 'copying', 'notice')):
        copy_file(path, bundle / 'licenses/ParaView' / path.relative_to(source))
copy_file(repo / 'native/post_exit/LICENSE', bundle / 'licenses/CaePostExit-LICENSE')
# LGPLv3 is additional permission on GPLv3; keep both unmodified license texts.
copy_file(repo / 'benchmarks/input-data/codeaster/COPYING.GPL-3.0', bundle / 'licenses/Qt/COPYING.GPL-3.0')
copy_file(repo / 'docs/post-exit/RUNTIME_RECOVERY_KO.md', bundle / 'READ_ME_KO.md')
write(bundle / 'sources.json', {
    'inputs': inputs, 'source_commit': evidence['source_commit'],
    'plugin_source': 'https://github.com/pikachu444/autonomous-cae-lab/tree/' + evidence['source_commit'] + '/native/post_exit',
    'python': 'https://www.python.org/downloads/release/python-31210/',
    'qt_source': 'https://download.qt.io/archive/qt/6.9/6.9.0/single/qt-everywhere-src-6.9.0.tar.xz',
    'numpy_source': 'https://github.com/numpy/numpy/tree/v2.3.5',
    'system_prerequisite': 'https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170',
    'system_crt_versions': evidence.get('system_crt_versions'),
    'compiler_file_version': evidence.get('compiler_file_version'),
    'actual_gui_exit_acceptance': 'NOT_RUN', 'clean_pc_install_acceptance': 'NOT_RUN'})
verify_artifact(bundle / 'plugin/CaePostExit.dll', bundle / 'runtime')
files = {path.relative_to(bundle).as_posix(): {'sha256': file_sha256(path), 'bytes': path.stat().st_size}
         for path in sorted(bundle.rglob('*')) if path.is_file()}
write(bundle / 'files.json', {'schema': 'cae.post-runtime-package/1', 'files': files,
                            'artifact_pins': 'UNCHANGED', 'binary_execution': 'NOT_RUN'})
# 1890 MiB leaves room below the requested 1900 MiB and GitHub's 2 GiB per asset.
subprocess.run([str(seven), 'a', '-t7z', '-mx=1', '-v1890m', '-y',
                str(out / 'post-runtime.7z'), 'post-runtime'], cwd=out, check=True)
volumes = sorted(out.glob('post-runtime.7z.*'))
require(volumes and all(0 < p.stat().st_size < 1900 * 1024**2 for p in volumes), 'Invalid archive volumes')
subprocess.run([str(seven), 't', str(volumes[0])], cwd=out, check=True)
write(out / 'package-receipt.json', {
    'schema': 'cae.post-runtime-recovery/1', 'source_commit': evidence['source_commit'],
    'files_manifest_sha256': file_sha256(bundle / 'files.json'),
    'volumes': [{'file': p.name, 'bytes': p.stat().st_size, 'sha256': file_sha256(p)} for p in volumes],
    'staged_artifact_verification': 'PASSED', 'archive_test': 'PASSED',
    'publication': 'NONE', 'actual_gui_exit_acceptance': 'NOT_RUN'})
print(out / 'package-receipt.json')
'@
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$code | & $Python - $WorkRoot $repo $SevenZip
if ($LASTEXITCODE -ne 0) { throw "Post runtime packaging failed: $LASTEXITCODE. Preserve the new recovery folder for diagnosis." }
