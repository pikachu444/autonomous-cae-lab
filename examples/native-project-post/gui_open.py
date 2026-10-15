"""Open this example's copied saved project in the real ParaView GUI."""
import json
import os
from pathlib import Path
import sys
import uuid

REPO = Path(os.environ['CAE_NATIVE_POST_REPO']).resolve(strict=True)
sys.path.insert(0, str(REPO))
root = Path(os.environ['CAE_NATIVE_POST_EXAMPLE']).resolve(strict=True)
launch = json.loads((root / 'gui-launch.json').read_text(encoding='utf-8'))
os.environ['CAE_POST_NATIVE_OPEN'] = launch['launch_config']
os.environ['CAE_POST_PROJECT'] = launch['project_path']
os.environ['CAE_POST_HOME'] = str(REPO / 'apps' / 'desktop_post')
os.environ['CAE_POST_LAUNCH_DIR'] = str(root)
os.environ.pop('CAE_POST_SERVICE_URL', None)
from apps.desktop_post import startup
cae_post_bridge = startup.cae_post_bridge
if cae_post_bridge is None:
    raise RuntimeError('The existing native startup did not attach its owner and GUI dispatcher')
owner = cae_post_bridge[0]
from paraview import simple as p
p.RenderAllViews()
p.SaveScreenshot(str(root / 'native-render.png'), p.GetActiveView(), ImageResolution=[1200, 800])
(root / 'gui-readback.json').write_text(json.dumps({'status': 'OPENED',
    'document_id': owner.document_id, 'session': owner.session_id,
    'dispatcher': cae_post_bridge[1].__class__.__name__, 'broker': cae_post_bridge[2],
    'project': str(owner.project_path)}, indent=2) + '\n', encoding='utf-8')
