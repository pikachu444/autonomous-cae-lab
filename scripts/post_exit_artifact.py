"""Pin a real SDK-built Windows DLL to a runtime; never assert GUI acceptance."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024*1024), b''):
            digest.update(part)
    return digest.hexdigest()


def require_pe64(path: Path) -> None:
    with path.open('rb') as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b'MZ':
            raise ValueError('Not a Windows PE DLL: ' + str(path))
        stream.seek(struct.unpack_from('<I', dos, 60)[0])
        header = stream.read(26)
        if (len(header) != 26 or header[:4] != b'PE\0\0' or
                struct.unpack_from('<H', header, 4)[0] != 0x8664 or
                struct.unpack_from('<H', header, 24)[0] != 0x20b or
                not (struct.unpack_from('<H', header, 22)[0] & 0x2000)):
            raise ValueError('Requires an AMD64 PE32+ DLL')


def pin(plugin: Path, runtime: Path, build_info: Path, sdk_evidence: Path) -> Path:
    plugin, runtime = plugin.resolve(strict=True), runtime.resolve(strict=True)
    require_pe64(plugin)
    build = json.loads(build_info.read_text(encoding='utf-8-sig'))
    if (build.get('schema') != 'cae.post-exit-build/1' or build.get('paraview') != '6.2.0' or
            build.get('qt') != '6.9.0' or build.get('pointer_bits') != 64 or
            build.get('configuration') != 'Release' or build.get('compiler_id') != 'MSVC'):
        raise ValueError('The recorded SDK build does not match the assigned Windows target')
    evidence = json.loads(sdk_evidence.read_text(encoding='utf-8-sig'))
    if evidence.get('schema') != 'cae.post-exit-sdk/1':
        raise ValueError('Missing SDK provenance evidence')
    if evidence.get('runtime_relationship') not in ('same-sdk-build', 'official-matching-sdk'):
        raise ValueError('Do not pin a separately built SDK to the stock bundle without matching evidence')
    files = evidence.get('files', {})
    if not files or not any('cmake' in str(name).lower() for name in files):
        raise ValueError('SDK cache/configuration identity is missing')
    for path, expected in files.items():
        if sha256(Path(path).resolve(strict=True)) != expected:
            raise ValueError('SDK evidence file changed: ' + path)
    build['sdk_evidence_sha256'] = sha256(sdk_evidence)
    paths = list((runtime / 'bin').glob('*.dll')) + [runtime / 'bin/paraview.exe']
    # Include the actual Qt platform DLL; loading a second Qt distribution via
    # PATH must not be treated as a tested runtime.
    paths += list(runtime.glob('**/platforms/qwindows.dll'))
    pins = {p.relative_to(runtime).as_posix(): sha256(p) for p in paths if p.is_file()}
    names = {Path(name).name.lower() for name in pins}
    required = {'paraview.exe', 'qt6core.dll', 'qt6gui.dll', 'qt6widgets.dll', 'python312.dll'}
    if not required.issubset(names) or not any(n.startswith('pqcore') for n in names):
        raise ValueError('Runtime identity is incomplete; do not copy guessed DLLs into this installation')
    output = plugin.with_suffix(plugin.suffix + '.manifest.json')
    if output.exists():
        raise FileExistsError('Preserve the prior manifest; use a new artifact directory: ' + str(output))
    manifest = dict(schema='cae.post-exit-artifact/1', abi=1, plugin_sha256=sha256(plugin),
                    build=build, runtime_files=pins, native_acceptance='NOT_RUN')
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--build-info', type=Path, required=True)
    parser.add_argument('--sdk-evidence', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(pin(args.plugin, args.runtime, args.build_info, args.sdk_evidence))
    except (OSError, ValueError, KeyError) as error:
        print('Artifact pin refused: ' + str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
