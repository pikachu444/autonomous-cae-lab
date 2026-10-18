"""Install and discover the separately packaged native Data runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def runtime_root():
    return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'AutonomousCAELab/data-runtime'


def verify_package(package, *, full=False):
    package = Path(package).resolve(strict=True)
    manifest_path = package / 'package-manifest.json'
    manifest = _read(manifest_path)
    if manifest.get('executable') != 'bin/labplot.exe' or not isinstance(manifest.get('files'), list):
        raise ValueError('Data runtime의 실행 파일과 배포 목록을 확인하세요.')
    rows = {}
    for row in manifest['files']:
        name = row['path']
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or name in rows:
            raise ValueError('Data runtime 배포 목록의 파일 경로가 잘못되었습니다.')
        path = (package / relative).resolve(strict=True)
        if not path.is_relative_to(package) or not path.is_file():
            raise ValueError('Data runtime의 파일이 배포 폴더 밖을 가리킵니다.')
        rows[name] = row
    required = {'bin/labplot.exe', 'bin/platforms/qwindows.dll', 'bin/qt.conf'}
    if not required <= rows.keys():
        raise ValueError('Data runtime에 필요한 Qt 실행 부품이 없습니다.')
    for name in rows if full else required:
        path = package / name
        if _sha(path) != rows[name]['sha256'] or path.stat().st_size != rows[name]['bytes']:
            raise ValueError('Data runtime 파일이 배포 목록과 다릅니다: ' + name)
    return {'root': package, 'executable': package / manifest['executable'],
            'plugins': package / 'bin', 'manifest_sha256': _sha(manifest_path)}


def installed_runtime():
    explicit = os.environ.get('CAELAB_DATA_RUNTIME')
    if explicit:
        return verify_package(explicit)
    root = runtime_root()
    pointer = root / 'current.json'
    if not pointer.is_file():
        return None
    selected = _read(pointer)
    package = (root / selected['package']).resolve(strict=True)
    if not package.is_relative_to(root.resolve()):
        raise ValueError('설치된 Data runtime 경로를 확인하세요.')
    runtime = verify_package(package)
    if runtime['manifest_sha256'] != selected['manifest_sha256']:
        raise ValueError('설치된 Data runtime의 배포 목록이 바뀌었습니다. 다시 설치하세요.')
    return runtime


def install(package, root=None):
    """Verify before copying; preserve every existing version and failed staging folder."""
    source = verify_package(package, full=True)
    root = Path(root) if root is not None else runtime_root()
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    name = source['manifest_sha256'][:24]
    destination = root / name
    if destination.exists():
        if verify_package(destination, full=True)['manifest_sha256'] != source['manifest_sha256']:
            raise ValueError('기존 Data runtime 폴더가 다른 내용입니다. 원본을 보존했습니다.')
    else:
        staging = root / ('install-' + uuid.uuid4().hex)
        shutil.copytree(source['root'], staging)
        verify_package(staging, full=True)
        staging.rename(destination)
    pointer = root / ('current-' + uuid.uuid4().hex + '.json')
    pointer.write_text(json.dumps({'package': name, 'manifest_sha256': source['manifest_sha256']}, indent=2), encoding='utf-8')
    pointer.replace(root / 'current.json')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', required=True, type=Path)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    print(install(args.install, args.root))


if __name__ == '__main__':
    main()
