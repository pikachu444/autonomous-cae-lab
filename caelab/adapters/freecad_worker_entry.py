"""FreeCAD loads .py files under their stem; invoke only our fixed workers as main."""
import os
from pathlib import Path
import runpy


entry = Path(globals().get('__file__') or os.environ['CAELAB_FREECAD_WORKER_ENTRY']).resolve()
root = entry.parents[2]
worker = Path(os.environ['CAELAB_FREECAD_PARAMETER_WORKER']).resolve()
allowed = {entry.with_name('freecad_parameter_worker.py'),
           root / 'plugins/fixture_design/upstream/fixturelab/freecad_worker.py'}
if worker not in allowed:
    raise RuntimeError('NATIVE_WORKER_ENTRY_INVALID: Only the fixed native workers may be invoked')
runpy.run_path(str(worker), run_name='__main__')
