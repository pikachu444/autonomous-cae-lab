"""Optional supplied C1 contract modules, never replacing installed product code.

Set CAELAB_CONTRACT_ROOT to the request ZIP's references directory when testing
its partial baseline. In an integrated checkout this setting is unnecessary.
"""
import os
from pathlib import Path
import caelab

root = os.environ.get('CAELAB_CONTRACT_ROOT')
if root:
    for suffix in ('data-c1/overlay/caelab', 'numerical-c1/caelab'):
        path = Path(root)/suffix
        if not path.is_dir():
            raise RuntimeError('Missing explicit public contract directory: '+str(path))
        caelab.__path__.append(str(path.resolve()))
