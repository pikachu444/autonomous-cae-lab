"""Execution-only package/ABI/source fingerprint; no runtime probing during edit."""
from pathlib import Path
from importlib import metadata
import hashlib
import platform
import sys
from ..evaluation import file_hash
from plugins.material_point.law_native import FELUPE_VERSION

SOURCE_RELATIVES=(
 'plugins/material_point/law_native_tensors.py','plugins/material_point/drucker_prager.py',
 'plugins/material_point/single_branch_native.py','plugins/material_point/law_native.py',
 'plugins/material_point/law_native_history.py','caelab/law_native_fe.py',
 'caelab/adapters/law_native_fe_worker.py','caelab/adapters/law_native_fe.py',
 'caelab/adapters/law_native_point.py','caelab/adapters/law_native_runtime.py')


def source_identity(*, text=False):
    root=Path(__file__).resolve().parents[2]
    files={}
    for name in SOURCE_RELATIVES:
        path=root/name
        if not path.is_file() or path.is_symlink():
            raise ValueError('Trusted law-native source is missing or linked: '+name)
        row={'sha256':file_hash(path)}
        if text:row['text']=path.read_bytes().decode('utf-8')
        files[name]=row
    return {'interface':'law-native/1','files':files}


def runtime_identity():
    import felupe, numpy, scipy
    if felupe.__version__!=FELUPE_VERSION:
        raise ValueError('FELUPE version mismatch; expected '+FELUPE_VERSION)
    packages={}
    for module in (felupe,numpy,scipy):
        dist=metadata.distribution(module.__name__)
        files={}
        # Loaded extension and constitutive/solver Python sources, not huge data files.
        for relative in dist.files or []:
            name=str(relative)
            if (module is felupe and name.endswith('.py')) or name.endswith(('.so','.pyd','.dll')):
                path=Path(dist.locate_file(relative)).resolve()
                if path.is_file():files[name]=file_hash(path)
        packages[module.__name__]={'version':module.__version__,'source_and_binary_sha256':files,
            'license':dist.metadata.get('License-Expression') or dist.metadata.get('License','UNAVAILABLE')[:2000]}
    return {'os':platform.platform(),'machine':platform.machine(),'python':sys.version,
        'python_executable_sha256':file_hash(sys.executable),'abi':sys.implementation.cache_tag,
        'packages':packages,'source':source_identity(),
        'compiler':'NOT_REQUIRED: fixed Python constitutive interface, no user-source build',
        'mfront_generic_abi':'NOT_USED','calculix_abi':'NOT_USED',
        'windows_execution':'ACTUAL' if sys.platform=='win32' else 'NOT_RUN_ON_WINDOWS'}
