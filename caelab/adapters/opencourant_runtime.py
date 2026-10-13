"""Selected OpenCourant runtime; no installation or global environment mutation."""
import hashlib
import os
from pathlib import Path
from ..contracts import CapabilityUnavailable

WINDOWS_FILES = {
    "exec/starter_win64.exe": "606b8d9785bb79305ede5e1467fff6e07331678ae619fe9d4e118df6c5c1309e",
    "exec/engine_win64.exe": "7530cba04c5e73fa93167496d5e11476318084c84fff9c6b0dfccc35267a81a9",
    "exec/anim_to_vtk_win64.exe": "238278b91341168f517eb1547efdb249705af8080cd1f0beca0ba61d3bc65e12",
    "exec/th_to_csv_win64.exe": "ad5b8a76b5a13aa695616f15af400ad1ea344a1afb37a2480f17aaa0ec758d01",
    "extlib/hm_reader/win64/hm_reader_win64.dll": "54dea015c6e776b9f5519bb8a31ae2f5a8fe506315e9ea393cee439c9dc869c1",
    "extlib/hm_reader/win64/libapr-1.dll": "a165557741cd95d899a9af74dd2794850772e8ecb882b353e5a0f8e5317f2720",
    "extlib/h3d/lib/win64/h3dreader.dll": "b3de1e636d2c290a8c2e95f50a6dff7036af03cb8dfae62522f986d994e01836",
    "extlib/h3d/lib/win64/h3dwriter.dll": "cbe2ef4362095e1d952d17b69c0f6a023c830500595ce00d137365f7f741e483",
    "extlib/intelOneAPI_runtime/win64/impi.dll": "9cb6ee5a55b63fd22d3cd53c1bed93ad245dc0f87701bc167b6d431384f7ed89",
    "extlib/intelOneAPI_runtime/win64/libfabric.dll": "387e2faa96209ce5e94a5dbf6f1213fc9d81da674a4e170a30e7cf2b100d56ab",
    "extlib/intelOneAPI_runtime/win64/libiomp5md.dll": "f608eedb25e44de3db1d3db984ac113f3a8406a92ea87061a77f390852fe1174",
    "extlib/intelOneAPI_runtime/win64/libmmd.dll": "e2b0066f3f4479439d5f008c74482b78ed13203d62c2ecb480cc12b4d78a01fa",
    "extlib/intelOneAPI_runtime/win64/mkl_avx2.2.dll": "95a24cf1c3df05ac7a126c09c74a3d077be0743f2036af4a934e1f2a3850d66f",
    "extlib/intelOneAPI_runtime/win64/mkl_avx512.2.dll": "ec81d74d6d1102147ade9b4f4f1a27fd122d96771b4bd80dccb5fcdde05ff304",
    "extlib/intelOneAPI_runtime/win64/mkl_core.2.dll": "2c1c53445e9ec21a04d479107a03356fb3184422c851376d1d7438164a6f46ef",
    "extlib/intelOneAPI_runtime/win64/mkl_def.2.dll": "da9cb9af9aaea16fa03539524fd599bef7eea9d4504c99d4995323b05a09004a",
    "extlib/intelOneAPI_runtime/win64/mkl_intel_thread.2.dll": "0c8856befc20b72d18e4a712f842c2e528ab77255af27abafa18595d945eabe3",
    "extlib/intelOneAPI_runtime/win64/svml_dispmd.dll": "415dbc87ff6328fa45b69ca25a5861e5e25f50b348df67590abb99839efb9a90"
}
WINDOWS_CFG = '0cb6bcfa32474a76e2ad322cd2ea1c68a1c85821c0ff88b8e5e47723beb18fdf'
WINDOWS_SOURCE = 'cb760c206e346eff12161a2268b134ef9d48a4ef'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def runtime():
    if os.name != 'nt':
        from .openradioss import runtime as legacy
        root, env, identity = legacy()
        root = Path(root)
        names = {name: root / 'exec' / (name + '_linux64_gf')
                 for name in ('starter', 'engine', 'anim_to_vtk', 'th_to_csv')}
        for path in names.values():
            if not path.is_file() or not os.access(path, os.X_OK):
                raise CapabilityUnavailable('Selected runtime lacks executable converter: ' + path.name)
        return names, env, {**identity, 'converter_sha256': {k: sha(v) for k,v in names.items()},
                            'converter_source_commit': 'NOT_PROVEN_BY_RELEASE'}
    selected = os.environ.get('CAELAB_OPENCOURANT_ROOT') or os.environ.get('CAELAB_OPENRADIOSS_ROOT')
    if selected:
        root = Path(selected)
    else:
        base = os.environ.get('LOCALAPPDATA')
        if not base:
            raise CapabilityUnavailable('Select the installed Windows OpenCourant runtime')
        root = Path(base) / 'AutonomousCAELab/runtimes/opencourant-windows-20261011/OpenCourant'
    if not root.is_dir():
        raise CapabilityUnavailable('OpenCourant Windows runtime is not installed; editing and saving remain available')
    root = root.resolve()
    for relative, expected in WINDOWS_FILES.items():
        path = root / relative
        if path.is_symlink() or not path.is_file() or sha(path) != expected:
            raise CapabilityUnavailable('Selected OpenCourant runtime differs from the supported release: ' + relative)
    digest = hashlib.sha256()
    for path in sorted((root / 'hm_cfg_files').rglob('*')):
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(bytes.fromhex(sha(path)))
    if digest.hexdigest() != WINDOWS_CFG:
        raise CapabilityUnavailable('OpenCourant configuration digest differs')
    env = dict(os.environ)
    dll = [root / p for p in ('extlib/hm_reader/win64','extlib/h3d/lib/win64','extlib/intelOneAPI_runtime/win64')]
    env.update(PATH=os.pathsep.join([*(str(p) for p in dll), env.get('PATH','')]),
               RAD_CFG_PATH=str(root / 'hm_cfg_files'), RAD_H3D_PATH=str(dll[1]),
               OPENCOURANT_PATH=str(root), KMP_STACKSIZE='400m', OMP_NUM_THREADS='2')
    names = {name: root / 'exec' / (name + '_win64.exe')
             for name in ('starter','engine','anim_to_vtk','th_to_csv')}
    return names, env, {'release':'latest-20261011','platform':'win64',
        'source_tag':WINDOWS_SOURCE,'files':WINDOWS_FILES,'hm_cfg_sha256':WINDOWS_CFG,
        'converter_source_commit':'NOT_PROVEN_BY_RELEASE','process_control':'WINDOWS_OWNED_JOB'}
