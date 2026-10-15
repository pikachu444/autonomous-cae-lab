"""Load the real SDK-built GUI plugin in pvpython; no GUI exit claim.

The GUI autostart owner/filter is deliberately not inferred from a headless
process. Existing native reader/owner roundtrips are separate checks.
"""
import argparse
import hashlib
import json
from pathlib import Path

from paraview import simple

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--plugin', type=Path, required=True)
args = parser.parse_args()
plugin = args.plugin.resolve(strict=True)
version = simple.GetParaViewVersion()
if not version or version != (6, 2):
    raise RuntimeError('Expected the exact ParaView 6.2 runtime: ' + str(version))
simple.LoadPlugin(str(plugin), remote=False)
print(json.dumps({'plugin': str(plugin), 'sha256': hashlib.sha256(plugin.read_bytes()).hexdigest(),
                  'paraview': '6.2', 'plugin_load': 'PASSED',
                  'gui_owner_registration': 'NOT_EXERCISED',
                  'desktop_exit_acceptance': 'NOT_RUN'}), flush=True)
