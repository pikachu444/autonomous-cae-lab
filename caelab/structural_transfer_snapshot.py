"""Package an explicitly bound TR-U model for the existing contact Runner."""
from copy import deepcopy
from pathlib import Path
import shutil
import uuid

from .contact_deck import render, validate_model
from .evaluation import file_hash
from .storage import canonical_hash, save_json


def freeze_transfer(model, editable_fcstd, output_root, identity, *, native_version,
                    analysis_id, solver_id, expected_editable_sha256):
    """Retain native CAD and exact derived BCs; never collect or execute again."""
    from .adapters.contact_fem import validate_snapshot
    model=deepcopy(model)
    validate_model(model)
    transfer=model.get('displacement_transfer',{})
    bound={(r['node_id'],r['component']):r['value_mm'] for r in model['boundary_dofs']}
    transferred=transfer.get('boundary_dofs',[])
    if (transfer.get('status')!='READY' or not transferred
            or any((r['node_id'],r['component']) not in bound or
                   bound[r['node_id'],r['component']]!=r['value_mm'] for r in transferred)):
        raise ValueError('An explicitly bound displacement-transfer receipt is required')
    source=Path(editable_fcstd).resolve(strict=True)
    if source.suffix.lower()!='.fcstd' or file_hash(source)!=expected_editable_sha256:
        raise ValueError('The captured editable native source changed')
    root=Path(output_root).resolve()/('F'+uuid.uuid4().hex)
    root.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(source,root/'editable.FCStd')
    if file_hash(root/'editable.FCStd')!=expected_editable_sha256 or file_hash(source)!=expected_editable_sha256:
        raise ValueError('The editable native source changed during packaging')
    save_json(root/'mesh.json',model)
    (root/'contact.inp').write_text(render(model),encoding='ascii',newline='\n')
    files=[{'relative':path.name,'bytes':path.stat().st_size,'sha256':file_hash(path)}
           for path in sorted(root.iterdir())]
    manifest=root/'snapshot.json'
    save_json(manifest,{'kind':'freecad-contact-frozen','schema_version':'1','id':root.name,
        'input_file':'contact.inp','files':files,'native_version':list(native_version),
        'analysis_id':analysis_id,'solver_id':solver_id,'bodies':deepcopy(identity),
        'document':{'name':'StructuralTransferReceiver','original_sha256':expected_editable_sha256},
        'editable_role':'REFERENCE_BASELINE_NOT_EXECUTABLE_TRANSFER',
        'editable_relationship':{'baseline_fcstd_sha256':expected_editable_sha256,
            'captured_model_sha256':transfer['captured_model_sha256'],
            'derived_model_sha256':canonical_hash(model)},
        'derived_model_sha256':canonical_hash(model),'solver_execution':'NOT_PERFORMED',
        'qualification':'UNKNOWN','decision':'NOT_RELEASED'})
    validate_snapshot(manifest)
    return manifest
