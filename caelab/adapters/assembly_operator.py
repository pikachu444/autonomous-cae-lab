"""Trusted local startup configuration, never a browser/native-path API.

The independently pinned original qualification is preserved. Current verifier
pins are captured explicitly at startup under ADR0049's two-path boundary.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from . import fixture_assembly_mesh_reuse as reuse
from .fixture_assembly_native_import import QualifiedAssemblyMeshBundle


class AssemblyOperator:
    def __init__(self, config_path):
        path = Path(config_path)
        reuse._no_links(path.absolute())
        path = path.resolve(strict=True)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
            raise ValueError('Small regular operator configuration required')
        raw = path.read_bytes()
        config = json.loads(raw)
        if set(config) != {'schema_version', 'qualification_pins_path', 'qualification_pins_entry', 'bundle_root'} or config['schema_version'] != 1:
            raise ValueError('Explicit assembly operator configuration required')
        pin_path = Path(config['qualification_pins_path'])
        bundle_path = Path(config['bundle_root'])
        if not pin_path.is_absolute() or not bundle_path.is_absolute():
            raise ValueError('Operator paths must be explicit absolute local paths')
        reuse._no_links(pin_path)
        original = pin_path.read_bytes()
        pin = {'sha256': hashlib.sha256(original).hexdigest(), 'size_bytes': len(original)}
        if pin != config['qualification_pins_entry']:
            raise ValueError('Independent original qualification pin drift')
        pins = json.loads(original)
        if pins['profile']['name'] != 'coarse3' or pins['profile']['mesh_size_mm'] != 3.0:
            raise ValueError('This assembly route reuses qualified coarse3 only')
        from .fixture_assembly_mesh import source_fingerprint
        current = source_fingerprint()
        self.bundle = QualifiedAssemblyMeshBundle(bundle_path,
            request_entry=pins['request_entry'], result_entry=pins['result_entry'],
            mesh_revision=pins['mesh_revision'], source_files=pins['source_files'], current_source_files=current)
        from plugins.fixture_design.assembly_mesh import ACTIVE, INACTIVE
        self.retained_mesh = {'mesh_revision': pins['mesh_revision'], 'profile': 'coarse3',
            'cad_revision': pins['parent_identity']['cad_revision'], 'active_components': list(ACTIVE),
            'inactive_components': list(INACTIVE), 'qualification_pins_entry': pin,
            'native_revision': pins['parent_identity']['native_revision']}
        self.configuration = {'schema_version': 1, 'config_entry': {
            'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)},
            'qualification_pins_entry': pin, 'original_source_files': deepcopy(pins['source_files']),
            'current_parent_verifier_source_files': deepcopy(current)}

    def lab(self, store):
        from caelab import Lab
        from .fixture_assembly_conditions_catalog import AssemblyConditionsCADAdapter
        from .fixture_assembly_mechanics import FixtureAssemblyMechanicsAdapter
        lab = Lab(store)
        lab.adapters['fixture.assembly'] = AssemblyConditionsCADAdapter(self.retained_mesh)
        adapter = FixtureAssemblyMechanicsAdapter(self.bundle, self.retained_mesh, self.configuration)
        lab.analysis_adapters[adapter.backend] = adapter
        return lab
