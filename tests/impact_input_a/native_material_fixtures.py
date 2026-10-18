"""Public fixed inputs through existing converter/domain helpers; not solver runs."""
from pathlib import Path
import sys
from caelab import impact_model, impact_b
from caelab.impact_damage import apply_laws, verify_laws
from caelab.adapters import inp2rad_worker
from caelab.adapters.impact_admission import (global_gravity, normalize_contact_friction,
    normalize_surfaces, normalize_elastic_tetra4, validate_physics)
from caelab.execution_control import run_owned_command
from caelab.impact_source import capture


def make_native(folder, kind):
    if kind == 'bulk':
        from examples.impact.bulk_interface.bulk_coupon import settings
    elif kind=='interface':
        from examples.impact.cohesive_model import settings
    else:
        from examples.impact.bulk_interface.example import settings
    declared = settings()
    if kind=='delayed':
        declared['contacts']=[{'a':'LOWERFACE','b':'UPPERFACE','law':'TYPE24','friction':.1}]
        declared['interface_controls'][0].update(reclosure='DELAYED_TYPE24_REQUIRE_DELETION',contact_index=0,contact_start_s=.003)
    folder = Path(folder); folder.mkdir(parents=True)
    text, initial = impact_model.render(declared)
    model = impact_model.model_from_settings(declared)
    inp = folder/'impact.inp'; inp.write_text(text, encoding='ascii')
    process = run_owned_command([sys.executable, inp2rad_worker.__file__, str(inp)],
        folder, 'native-material-convert', timeout=30, owned_tree=True)
    assert process.returncode == 0
    raw = (folder/'impact_0000.rad').read_text(encoding='ascii')
    raw, _ = global_gravity(raw, declared['gravity_mm_s2'])
    raw = normalize_contact_friction(raw, declared)
    raw, _ = normalize_surfaces(raw, model)
    raw, _ = normalize_elastic_tetra4(raw, model, initial, declared)
    physics = validate_physics(raw, model, initial, declared)
    raw, cohesive = apply_laws(raw, model, declared['cohesive'])
    verify_laws(raw, model, declared['cohesive'], cohesive)
    raw, definition = impact_b.compile(raw, model, declared, cohesive)
    # Keep a real include graph and CRLF bytes, not a regenerated export path.
    start = raw.index('/NODE'); stop = raw.index('\n/', start+1)+1
    mesh = raw[start:stop]
    raw = raw[:start]+'#include mesh.inc\n'+raw[stop:]
    (folder/'mesh.inc').write_bytes(mesh.replace('\n','\r\n').encode('ascii'))
    (folder/'impact_0000.rad').write_bytes(raw.replace('\n','\r\n').encode('ascii'))
    engine = impact_model.engine_deck(declared, model=model, physics=physics)
    (folder/'impact_0001.rad').write_bytes(engine.replace('\n','\r\n').encode('ascii'))
    source = capture(folder/'impact_0000.rad', folder, engine=folder/'impact_0001.rad', units='Mg/mm/s')
    return declared, model, definition, source
