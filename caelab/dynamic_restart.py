"""Actual CalculiX .rout -> .rin READ, inside the existing frozen-input format.

No restart is inferred from FRD's final time. The supported native sequential
unformatted layout is checked record-by-record against restartwrite.f at
cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54. Unknown compiler layouts, truncated
records and incomplete steps remain retained but are not offered for restart.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import math
import platform
import re
import shutil
import struct
import sys
import uuid

from .adapters.frozen_fem import _read, _relative, _sha
from .adapters.fixture_field import _printed_close
from .contact_steps import compile_program
from .dynamic_model import enabled, attach
from .storage import canonical_hash, save_json

MEMBERS = {'contact.rin', 'restart_parent_model.json', 'restart_parent_input.inp',
           'restart_parent_execution.json', 'restart_parent_status.sta'}
LAYOUT = 'ccx_cff1bb12_sequential_4byte_marker_int32_float64'


def runtime_platform():
    return {'system': sys.platform, 'machine': platform.machine(), 'pointer_bits': struct.calcsize('P')*8}


class _Records:
    def __init__(self, raw):
        self.raw, self.pos, self.count = memoryview(raw), 0, 0
        candidates = [order for order in ('<', '>') if len(raw) >= 88 and
                      struct.unpack_from(order+'i', raw, 0)[0] == 80 and
                      struct.unpack_from(order+'i', raw, 84)[0] == 80]
        if len(candidates) != 1:
            raise ValueError('Unsupported native restart record-marker layout; no conversion is attempted')
        self.order = candidates[0]

    def read(self, length, name):
        if type(length) is not int or length < 0 or self.pos+length+8 > len(self.raw):
            raise ValueError('Truncated/unsupported restart record: ' + name)
        size = struct.unpack_from(self.order+'i', self.raw, self.pos)[0]
        trailer = struct.unpack_from(self.order+'i', self.raw, self.pos+length+4)[0]
        if size != length or trailer != size:
            raise ValueError('Native restart record layout differs at ' + name)
        start = self.pos+4
        data = self.raw[start:start+length]
        self.pos += length+8
        self.count += 1
        return data, start

    def ints(self, name, count=1):
        raw, _ = self.read(4*count, name)
        values = struct.unpack(self.order+str(count)+'i', raw)
        return values[0] if count == 1 else values

    def scalar(self, name):
        raw, _ = self.read(8, name)
        value = struct.unpack(self.order+'d', raw)[0]
        if not math.isfinite(value):
            raise ValueError('Nonfinite native restart ' + name)
        return value


def read_rout(path):
    """Index complete native state blocks; verify the *entire* file layout.

    Payload offsets reference the original bytes; files are never shortened to
    salvage a checkpoint. Full arrays are hashed, not replaced with aggregates.
    This validates framing/presence, not the physical correctness of a state.
    """
    raw = _read(Path(path))
    r = _Records(raw)
    blocks = []
    while r.pos < len(raw):
        begin, first_record = r.pos, r.count
        version, _ = r.read(80, 'version')
        version = bytes(version).decode('ascii').rstrip(' \x00')
        if not re.fullmatch(r'Version [A-Za-z0-9_.+ -]+', version):
            raise ValueError('Unknown native restart version record')
        step = r.ints('completed step')
        if step < 1 or blocks and step <= blocks[-1]['step']:
            raise ValueError('Unordered native completed-step checkpoints')
        counts = {}
        for name in ('nset','nalset','nload','nbody','nforc','nboun','nflow','nk','ne','nef','nkon'):
            counts[name] = r.ints(name)
        counts['mi'] = list(r.ints('mi', 3))
        for name in ('nmpc','mpcend','maxlenmpc','memmpc','nfc','ndc','nmat','ntmat','npmat','ncmat',
                     'nprop','norien','ntrans','nam','namtot','nprint','nlabel','ntie','ncs','mcs','ne1d','ne2d'):
            counts[name] = r.ints(name)
        counts['infree'] = list(r.ints('infree', 4))
        counts['nmethod'] = r.ints('nmethod')
        counts['iperturb'] = list(r.ints('iperturb', 2))
        for name in ('nener','iplas','ithermal','nstate','nslavs','iprestr','mortar'):
            counts[name] = r.ints(name)
        counts['ifacecount'] = r.ints('ifacecount') if counts['mortar'] == 1 else 0
        counts['nintpoint'] = r.ints('nintpoint') if counts['mortar'] == 1 else 0
        counts['nheading'], counts['network'] = r.ints('nheading'), r.ints('network')
        # iperturb/iplas are native mode flags, not array sizes. Validate sizes
        # without assuming that unrelated internal solver flags are nonnegative.
        sizes = [v for k, v in counts.items() if isinstance(v, int) and k not in
                 {'nmethod','iplas','mortar','network','ithermal','nener','iprestr'}]
        if any(v < 0 or v > len(raw) for v in sizes) or min(counts['mi']) < 1:
            raise ValueError('Invalid native restart array dimensions')
        c, arrays = counts, {}
        mi1, mi2, mi3 = c['mi']
        nk, ne, nmat, nt, nb = c['nk'], c['ne'], c['nmat'], c['ntmat'], c['nboun']
        def array(name, n, width, *, retain=False):
            value, offset = r.read(n*width, name)
            if retain:
                arrays[name] = {'payload_offset': offset, 'bytes': len(value), 'count': n,
                                'width': width, 'sha256': hashlib.sha256(value).hexdigest()}
            return value
        array('sets', c['nset'], 81)
        array('istartset', c['nset'], 4); array('iendset', c['nset'], 4)
        for _ in range(c['nalset']):
            r.ints('ialset entry')
        array('heading', c['nheading'], 66)
        array('co', 3*nk, 8, retain=True); array('kon', c['nkon'], 4, retain=True)
        array('ipkon', ne, 4, retain=True); array('lakon', ne, 8, retain=True)
        for name, width in (('nodeboun',4),('ndirboun',4),('typeboun',1),('xboun',8),('ikboun',4),('ilboun',4)):
            array(name, nb, width)
        if c['nam'] > 0: array('iamboun', nb, 4)
        for name, width in (('nodebounold',4),('ndirbounold',4),('xbounold',8)):
            array(name, nb, width)
        for name, width in (('ipompc',4),('labmpc',20),('ikmpc',4),('ilmpc',4),('fmpc',8)):
            array(name, c['nmpc'], width)
        array('nodempc', 3*c['mpcend'], 4); array('coefmpc', c['mpcend'], 8)
        if c['nfc'] > 0:
            array('coeffc', 7*c['nfc'], 8); array('ikdc', c['ndc'], 4); array('edc', 12*c['ndc'], 8)
        array('nodeforc', 2*c['nforc'], 4)
        for name, width in (('ndirforc',4),('xforc',8),('ikforc',4),('ilforc',4)):
            array(name, c['nforc'], width)
        if c['nam'] > 0: array('iamforc', c['nforc'], 4)
        array('xforcold', c['nforc'], 8)
        array('nelemload', 2*c['nload'], 4); array('sideload', c['nload'], 20)
        array('xload', 2*c['nload'], 8)
        if c['nam'] > 0: array('iamload', 2*c['nload'], 4)
        array('xloadold', 2*c['nload'], 8); array('cbody', c['nbody'], 81)
        array('ibody', 3*c['nbody'], 4); array('xbody', 7*c['nbody'], 8); array('xbodyold', 7*c['nbody'], 8)
        if c['iprestr'] > 0: array('prestr', 6*mi1*ne, 8, retain=True)
        array('prlab', c['nprint'], 6); array('prset', c['nprint'], 81); array('filab', c['nlabel'], 87)
        array('elcon', (c['ncmat']+1)*nt*nmat, 8); array('nelcon', 2*nmat, 4)
        array('rhcon', 2*nt*nmat, 8); array('nrhcon', nmat, 4)
        array('shcon', 4*nt*nmat, 8); array('nshcon', nmat, 4)
        array('cocon', 7*nt*nmat, 8); array('ncocon', 2*nmat, 4)
        array('alcon', 7*nt*nmat, 8); array('nalcon', 2*nmat, 4); array('alzero', nmat, 8)
        array('physcon', 14, 8)
        modal = array('xmodal', 11, 8, retain=True)
        damp_modes = struct.unpack(r.order+'11d', modal)[10]
        if not math.isfinite(damp_modes) or damp_modes < 0 or damp_modes != int(damp_modes):
            raise ValueError('Invalid native restart modal damping count')
        if damp_modes: array('xmodal_modes', int(damp_modes), 8, retain=True)
        if c['npmat'] != 0:
            for name, n, width in (('plicon',(2*c['npmat']+1)*nt*nmat,8),('nplicon',(nt+1)*nmat,4),
                                   ('plkcon',(2*c['npmat']+1)*nt*nmat,8),('nplkcon',(nt+1)*nmat,4)):
                array(name,n,width)
        if c['norien'] != 0:
            array('orname',c['norien'],80); array('orab',7*c['norien'],8); array('ielorien',mi3*ne,4)
        if c['nprop'] != 0:
            array('ielprop',ne,4); array('prop',c['nprop'],8)
        if c['ntrans'] != 0:
            array('trab',7*c['ntrans'],8); array('inotr',2*nk,4)
        if c['nam'] > 0:
            array('amname',c['nam'],80)
            namta = array('namta',3*c['nam']-1,4)
            r.ints('namta final entry')
            amplitude_points = struct.unpack_from(r.order+'i',namta,len(namta)-4)[0]
            array('amta',2*amplitude_points,8)
        if c['ithermal'] > 0:
            array('t0',nk,8); array('t1',nk,8)
            if c['ne1d'] > 0 or c['ne2d'] > 0:
                array('t0g',2*nk,8); array('t1g',2*nk,8)
            if c['nam'] > 0: array('iamt1',nk,4)
            array('t1old',nk,8)
        array('matname',nmat,80); array('ielmat',mi3*ne,4)
        array('vold',(mi2+1)*nk,8,retain=True)
        if c['nmethod'] == 4 or c['nmethod'] == 1 and c['iperturb'][0] >= 2:
            array('veold',(mi2+1)*nk,8,retain=True)
        if c['nef'] > 0:
            for name in ('vel','velo','veloo'): array(name,8*c['nef'],8)
        if c['ne1d'] > 0 or c['ne2d'] > 0:
            for name,n,width in (('iponor',2*c['nkon'],4),('xnor',c['infree'][0],8),
                ('knor',c['infree'][1],4),('thicke',mi3*c['nkon'],8),('offset',2*ne,8),
                ('iponoel',c['infree'][3],4),('inoel',3*(c['infree'][2]-1),4),
                ('rig',c['infree'][3],4),('ne2boun',2*c['infree'][3],4)):
                array(name,n,width)
        if c['ntie'] > 0:
            array('tieset',3*c['ntie'],81); array('tietol',4*c['ntie'],8)
        if c['ncs'] > 0: array('ics',c['ncs'],4)
        if c['mcs'] > 0: array('cs',17*c['mcs'],8)
        array('sti',6*mi1*ne,8,retain=True); array('eme',6*mi1*ne,8,retain=True)
        if c['nener'] == 1:
            array('ener',2*mi1*(ne+(c['nslavs'] if c['mortar'] != 1 else 0)),8,retain=True)
        if c['nstate'] > 0:
            array('xstate',c['nstate']*mi1*(ne+(c['nslavs'] if c['mortar'] != 1 else c['nintpoint'])),8,retain=True)
        if c['mortar'] == 1:
            array('islavsurf',2*c['ifacecount']+2,4,retain=True)
            array('pslavsurf',3*c['nintpoint'],8,retain=True)
            array('clearini',3*9*c['ifacecount'],8,retain=True)
        array('ctrl',52,8,retain=True); array('qaold',2,8,retain=True)
        array('output',1,4)
        total = r.scalar('ttime')
        restart = list(r.ints('irstrt',2))
        blocks.append({'step':step,'native_global_coordinate':total,'native_version_record':version,
            'begin':begin,'end':r.pos,'records':r.count-first_record,
            'state_block_sha256':hashlib.sha256(memoryview(raw)[begin:r.pos]).hexdigest(),
            'counts':counts,'arrays':arrays,'restart_flags':restart,
            'validation':'COMPLETE_NATIVE_RECORD_LAYOUT; NATIVE_READ_STILL_REQUIRED'})
    if not blocks:
        raise ValueError('No actual native restart state blocks')
    return {'layout':LAYOUT,'byte_order':'little' if r.order == '<' else 'big',
            'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'checkpoints':blocks}


def _array_values(raw, inventory, checkpoint, name):
    entry = checkpoint['arrays'][name]
    value = memoryview(raw)[entry['payload_offset']:entry['payload_offset']+entry['bytes']]
    if hashlib.sha256(value).hexdigest() != entry['sha256']:
        raise ValueError('Restart state array changed during read')
    code = 'd' if entry['width'] == 8 else 'i'
    return struct.iter_unpack(('<' if inventory['byte_order'] == 'little' else '>')+code, value)


def _matches_mesh(raw, inventory, checkpoint, model):
    """Check original deck coordinates and ordered C3D10 topology in native state."""
    from .contact_deck import num
    c = checkpoint['counts']
    if (c['nmethod'] not in (1,4) or c['ne1d'] or c['ne2d'] or c['nef'] or c['network']
            or c['ithermal'] > 1 or c['nener'] != 1):
        raise ValueError('Restart state is not the supported energy-enabled implicit structural solid path')
    nodes = {r['node_id']:r for r in model['nodes']}
    if not nodes or max(nodes) > c['nk']:
        raise ValueError('Restart state lacks original structural nodes')
    co = list(v[0] for v in _array_values(raw,inventory,checkpoint,'co'))
    for node,row in nodes.items():
        expected = [float(num(v)) for v in row['position_mm']]
        if co[3*(node-1):3*node] != expected:
            raise ValueError('Restart state original mesh coordinates differ from executed deck')
    kon = [v[0] for v in _array_values(raw,inventory,checkpoint,'kon')]
    ipkon = [v[0] for v in _array_values(raw,inventory,checkpoint,'ipkon')]
    e = checkpoint['arrays']['lakon']; types = raw[e['payload_offset']:e['payload_offset']+e['bytes']]
    for row in model['elements']:
        eid = row['element_id']
        if eid > len(ipkon) or ipkon[eid-1] < 0:
            raise ValueError('Restart state lacks an original structural element')
        offset = ipkon[eid-1]
        if types[8*(eid-1):8*eid].strip() != b'C3D10' or kon[offset:offset+10] != row['node_ids']:
            raise ValueError('Restart state ordered structural connectivity differs from executed deck')


def checkpoint_inventory(path, model, status):
    raw = _read(Path(path))
    inventory = read_rout(path)
    if hashlib.sha256(raw).hexdigest() != inventory['sha256']:
        raise ValueError('Native restart file changed during inspection')
    stages = compile_program(model['analysis_steps'],model['conditions'])
    for checkpoint in inventory['checkpoints']:
        step = checkpoint['step']
        if not 1 <= step <= len(stages):
            raise ValueError('Native restart checkpoint step is outside its actual parent program')
        stage = stages[step-1]
        total = checkpoint['native_global_coordinate']
        # The binary's ttime is actual saved state time. STA supplies the
        # independently completed step evidence, never an inferred FRD checkpoint.
        matches = [r for r in status['rows'] if r['step'] == step and r['converged']
                   and _printed_close(r['native_tokens'][4],total)
                   and _printed_close(r['native_tokens'][5],stage['duration'])]
        if len(matches) != 1 or not _printed_close(matches[0]['native_tokens'][4],stage['end']):
            raise ValueError('Native checkpoint is not a uniquely completed retained STA step')
        expected_method = 4 if stage['procedure'] == 'dynamic' else 1
        if checkpoint['counts']['nmethod'] != expected_method:
            raise ValueError('Native checkpoint procedure differs from the executed step')
        _matches_mesh(raw,inventory,checkpoint,model)
        checkpoint.update(step_id=stage['id'],procedure=stage['procedure'],
                          sta_line=matches[0]['line'],sta_raw=matches[0]['raw'])
    return inventory


def _pinned_attempt(attempt):
    from .adapters.contact_fem import validate_snapshot
    attempt = Path(attempt)
    if not attempt.is_absolute():
        raise ValueError('Select an absolute retained parent attempt directory')
    raw = _read(attempt/'contact_execution.json')
    record = json.loads(raw)
    manifest, model, pins, _ = validate_snapshot(attempt/'frozen_input/snapshot.json')
    if not enabled(model) or record.get('snapshot_id') != manifest['id']:
        raise ValueError('Parent attempt is not the admitted NS2 snapshot')
    entries = {r['relative']:r for r in record['artifacts']}
    if len(entries) != len(record['artifacts']):
        raise ValueError('Duplicate parent artifact pins')
    required = {'solver/contact.rout','solver/contact.sta','solver/contact.inp'} | {'frozen_input/'+p for p in pins}
    for name in required:
        data = _read(attempt/_relative(name))
        pin = entries.get(name)
        if pin is None or len(data) != pin['bytes'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
            raise ValueError('Retained parent source changed: ' + name)
    if _read(attempt/'solver/contact.inp') != _read(attempt/'frozen_input/contact.inp'):
        raise ValueError('Parent executed input differs from its frozen input')
    runtime = record.get('runtime',{})
    if not re.fullmatch(r'[a-f0-9]{64}',runtime.get('sha256','')) or not runtime.get('platform'):
        raise ValueError('Exact parent executable hash/platform was not recorded; restart is unavailable')
    return record, raw, manifest, model, pins


def inspect_attempt(attempt):
    """Offer only actual completed saved steps; a missing file is not a restart."""
    from .contact_status import read_status
    record, raw, manifest, model, pins = _pinned_attempt(attempt)
    inventory = checkpoint_inventory(Path(attempt)/'solver/contact.rout',model,
                                      read_status(Path(attempt)/'solver/contact.sta',model))
    return {'status':'available','inventory':inventory,'parent_snapshot_id':manifest['id'],
            'parent_execution_sha256':hashlib.sha256(raw).hexdigest(),'runtime':record['runtime'],
            'parent_data_id':record.get('data_id'), 'parent_attempt':str(Path(attempt)),
            'solver_execution':'NOT_PERFORMED','qualification':'UNKNOWN'}


def prepare(attempt, checkpoint_step, continuation_steps, output_root):
    """Make one *new existing-format* snapshot from a pinned parent and .rout.

    Only the subsequent stage schedule is editable here. Changing geometry,
    material, density, IC or source conditions requires an ordinary new run, not
    an invented restart. The parent's bytes and results are never rewritten.
    """
    from .contact_status import read_status
    from .contact_deck import render,validate_model
    attempt, output_root = Path(attempt), Path(output_root)
    record, record_raw, manifest, parent, pins = _pinned_attempt(attempt)
    if type(checkpoint_step) is not int:
        raise ValueError('Choose an actual completed native step checkpoint')
    inventory = checkpoint_inventory(attempt/'solver/contact.rout',parent,
                                      read_status(attempt/'solver/contact.sta',parent))
    found = [r for r in inventory['checkpoints'] if r['step'] == checkpoint_step]
    if len(found) != 1:
        raise ValueError('The selected native step has no actual retained checkpoint')
    if not isinstance(continuation_steps,list) or not continuation_steps:
        raise ValueError('Author at least one explicit continuation step')
    draft = deepcopy(parent['dynamic']['draft'])
    draft['program']['steps'] = deepcopy(parent['analysis_steps']['steps'][:checkpoint_step]) + deepcopy(continuation_steps)
    procedures = {r.get('procedure',parent['analysis_steps']['procedure']) for r in draft['program']['steps']}
    draft['program']['procedure'] = next(iter(procedures)) if len(procedures) == 1 else 'mixed'
    model = attach(parent,draft)
    unique = 'F'+uuid.uuid4().hex
    parent_record_hash = hashlib.sha256(record_raw).hexdigest()
    model['restart'] = {'kind':'native_restart_read','version':1,
        'checkpoint':deepcopy(found[0]), 'rout':{'relative':'solver/contact.rout','bytes':inventory['bytes'],'sha256':inventory['sha256']},
        'rin':{'relative':'contact.rin','bytes':inventory['bytes'],'sha256':inventory['sha256']},
        'layout':inventory['layout'],'byte_order':inventory['byte_order'],
        'parent_snapshot_id':manifest['id'],'parent_snapshot_sha256':pins['snapshot.json']['sha256'],
        'parent_model_sha256':pins['mesh.json']['sha256'],'parent_input_sha256':pins['contact.inp']['sha256'],
        'parent_execution_sha256':parent_record_hash,'parent_attempt':str(attempt),
        'parent_data_id':record.get('data_id'),'parent_job_id':record.get('job_id'),
        'parent_runtime':deepcopy(record['runtime']),
        'amplitude_namespace':'R'+unique[1:13]+'A',
        'state_support':'SAME_MESH_MATERIAL_CONTACT_DAMPING; NATIVE_EQUIVALENCE_TEST_REQUIRED',
        'qualification':'UNKNOWN'}
    validate_model(model)
    root = output_root/unique
    if any(p.is_symlink() for p in (root,*root.parents)):
        raise ValueError('New restart snapshot must be a regular local directory')
    root.mkdir(parents=True,exist_ok=False)
    # Each copy belongs to the same validated parent, not a caller-provided rin.
    mapping = {'editable.FCStd':'frozen_input/editable.FCStd', 'contact.rin':'solver/contact.rout',
               'restart_parent_model.json':'frozen_input/mesh.json',
               'restart_parent_input.inp':'solver/contact.inp',
               'restart_parent_execution.json':'contact_execution.json',
               'restart_parent_status.sta':'solver/contact.sta'}
    if manifest.get('editable_project') == 'editable.caepre':
        mapping['editable.caepre'] = 'frozen_input/editable.caepre'
    for name,source in mapping.items():
        shutil.copyfile(attempt/source,root/name)
    save_json(root/'mesh.json',model)
    (root/'contact.inp').write_text(render(model),encoding='ascii',newline='\n')
    fresh = deepcopy(manifest)
    fresh.update(id=unique,files=[{'relative':p.name,'bytes':p.stat().st_size,'sha256':_sha(p)}
                                for p in sorted(root.iterdir()) if p.is_file()],
                 solver_execution='NOT_PERFORMED',restart_parent=manifest['id'])
    save_json(root/'snapshot.json',fresh)
    # Recheck capture and parent record before exposing anything to JobManager.
    from .adapters.contact_fem import validate_snapshot
    validate_snapshot(root/'snapshot.json')
    _pinned_attempt(attempt)
    if _read(attempt/'contact_execution.json') != record_raw:
        raise ValueError('Parent attempt changed during restart preparation; no run submitted')
    return root/'snapshot.json'


def validate_members(folder, model, pins):
    """Additional validation from the existing contact snapshot admission hook."""
    from .contact_status import read_status
    from .contact_deck import render
    restart = model.get('restart')
    if not restart:
        return
    if not enabled(model) or restart.get('kind') != 'native_restart_read' or restart.get('version') != 1:
        raise ValueError('Unsupported restart snapshot contract')
    folder = Path(folder)
    pairs = {'restart_parent_model.json':'parent_model_sha256','restart_parent_input.inp':'parent_input_sha256',
             'restart_parent_execution.json':'parent_execution_sha256'}
    for member,key in pairs.items():
        if pins[member]['sha256'] != restart.get(key):
            raise ValueError('Restart parent identity mismatch: '+member)
    if pins['contact.rin'] != {k:restart['rin'][k] for k in ('bytes','sha256')} or restart['rin']['sha256'] != restart['rout']['sha256']:
        raise ValueError('READ rin is not an exact copy of the retained native rout')
    parent = json.loads(_read(folder/'restart_parent_model.json'))
    parent_record = json.loads(_read(folder/'restart_parent_execution.json'))
    if (parent_record.get('snapshot_id') != restart['parent_snapshot_id'] or
            parent_record.get('runtime') != restart['parent_runtime'] or
            parent_record.get('data_id') != restart['parent_data_id'] or
            parent_record.get('job_id') != restart['parent_job_id']):
        raise ValueError('Restart parent execution/runtime identity mismatch')
    artifact = {r['relative']:r for r in parent_record['artifacts']}
    if (len(artifact) != len(parent_record['artifacts']) or
            artifact.get('frozen_input/snapshot.json', {}).get('sha256') != restart['parent_snapshot_sha256']):
        raise ValueError('Restart parent frozen snapshot identity mismatch')
    checks = {'solver/contact.rout':'contact.rin','solver/contact.sta':'restart_parent_status.sta',
              'solver/contact.inp':'restart_parent_input.inp','frozen_input/mesh.json':'restart_parent_model.json'}
    for original,copy in checks.items():
        pin = artifact.get(original,{})
        if {k:pin.get(k) for k in ('bytes','sha256')} != pins[copy]:
            raise ValueError('Restart source is not pinned by its exact parent attempt: '+original)
    if _read(folder/'restart_parent_input.inp') != render(parent).encode('ascii'):
        raise ValueError('Restart parent deck differs from retained model')
    index = checkpoint_inventory(folder/'contact.rin',parent,read_status(folder/'restart_parent_status.sta',parent))
    matches = [r for r in index['checkpoints'] if r['step'] == restart['checkpoint']['step']]
    if len(matches) != 1 or matches[0] != restart['checkpoint']:
        raise ValueError('READ checkpoint differs from the actual native saved state')
    cutoff = restart['checkpoint']['step']
    # Compare all physical inputs, retaining only deliberately new schedule and
    # operation provenance. The original model settings are NOT silently edited.
    left,right = deepcopy(parent),deepcopy(model)
    for value in (left,right):
        value.pop('restart',None)
        value.pop('analysis_steps',None)
        value['dynamic']['draft'].pop('program',None)
    if canonical_hash(left) != canonical_hash(right):
        raise ValueError('Restart cannot change mesh/material/density/damping/initial/source-condition state')
    if model['analysis_steps']['steps'][:cutoff] != parent['analysis_steps']['steps'][:cutoff]:
        raise ValueError('Restart cannot rewrite preceding native stages')
    if len(model['analysis_steps']['steps']) <= cutoff:
        raise ValueError('Restart has no new step')
    namespace = restart.get('amplitude_namespace','')
    if not re.fullmatch(r'R[a-f0-9]{12}A',namespace):
        raise ValueError('Restart amplitudes need a unique retained native namespace')


def stage_read(retained, native, model, runtime):
    """Called by the existing adapter just before its one ccx invocation."""
    if not model.get('restart'):
        return
    parent = model['restart']['parent_runtime']
    if runtime.get('sha256') != parent['sha256'] or runtime.get('platform') != parent['platform']:
        raise ValueError('Native restart requires the exact parent executable and platform; no binary conversion or fallback')
    source, target = Path(retained)/'contact.rin',Path(native)/'contact.rin'
    if target.exists():
        raise ValueError('READ input already exists in the new attempt')
    shutil.copyfile(source,target)
    expected = model['restart']['rin']
    if target.stat().st_size != expected['bytes'] or _sha(target) != expected['sha256']:
        raise ValueError('Native rin changed during exact rout capture')


def compare_saved_states(left_path, right_path, *, left_step, right_step, tolerances, time_tolerance, relative_tolerance=0.):
    """Compare all saved structural state arrays; caller prescribes tolerances.

    This checks native restart-state observables, not state that this CalculiX
    build does not write. In particular no absent acceleration state is invented.
    """
    if not math.isfinite(relative_tolerance) or relative_tolerance < 0 or not math.isfinite(time_tolerance) or time_tolerance < 0:
        raise ValueError('Nonnegative finite relative and native-time tolerances are required')
    a,b = read_rout(left_path),read_rout(right_path)
    def select(inv,step):
        rows=[r for r in inv['checkpoints'] if r['step']==step]
        if len(rows)!=1: raise ValueError('Comparison requires two actual native saved steps')
        return rows[0]
    ac,bc = select(a,left_step),select(b,right_step)
    ar,br = _read(Path(left_path)),_read(Path(right_path))
    for name in ('co','kon','ipkon','lakon'):
        av,bv=ac['arrays'].get(name),bc['arrays'].get(name)
        if av is None or bv is None or av['sha256'] != bv['sha256']:
            raise ValueError('Saved state native geometry/connectivity/order differ: '+name)
    fields = {'vold','veold','sti','eme','ener','xstate','pslavsurf','clearini','xmodal','ctrl','qaold','prestr','xmodal_modes'}
    result,missing = [],[]
    for name in sorted(fields):
        av,bv=ac['arrays'].get(name),bc['arrays'].get(name)
        if av is None and bv is None: continue
        if av is None or bv is None or av['count']!=bv['count']:
            missing.append({'array':name,'reason':'different_or_missing_saved_state_coverage'});continue
        tolerance = tolerances.get(name)
        if tolerance is None or not math.isfinite(tolerance) or tolerance<0:
            missing.append({'array':name,'reason':'finite_tolerance_not_prescribed'});continue
        worst,failed,nonfinite = 0.,0,0
        for x,y in zip(_array_values(ar,a,ac,name),_array_values(br,b,bc,name)):
            x,y=x[0],y[0]
            if not math.isfinite(x) or not math.isfinite(y): nonfinite+=1;continue
            delta=abs(x-y);worst=max(worst,delta)
            failed+=delta>tolerance+relative_tolerance*max(abs(x),abs(y))
        result.append({'array':name,'count':av['count'],'max_absolute_difference':worst,
                       'failed_values':failed,'nonfinite_values':nonfinite,'absolute_tolerance':tolerance})
    time_difference = abs(ac['native_global_coordinate']-bc['native_global_coordinate'])
    return {'status':'FAIL' if time_difference>time_tolerance or any(r['failed_values'] for r in result) else
                    'INCOMPLETE' if missing or any(r['nonfinite_values'] for r in result) or not result else 'PASS',
            'arrays':result,'missing':missing,'relative_tolerance':relative_tolerance,
            'time_coordinates':{'continuous':ac['native_global_coordinate'],'restart':bc['native_global_coordinate'],
                                'absolute_difference':time_difference,'tolerance':time_tolerance},
            'source_hashes':[a['sha256'],b['sha256']], 'qualification':'UNKNOWN','decision':'NOT_RELEASED',
            'scope':'arrays actually written by this native restart layout; not engineering approval'}
