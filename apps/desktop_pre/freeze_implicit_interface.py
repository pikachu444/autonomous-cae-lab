"""Freeze the user's native bodies and explicit joint definition without a run."""
from pathlib import Path
import uuid

from .freeze_contact import collect
from .freeze_analysis import _json, _hash
from caelab.adapters.implicit_interface_aster import BACKEND,mesh_text,command_text,validate_snapshot


def freeze(analysis,solver,output_root,*,fem):
    import FreeCAD as App
    model,identity = collect(analysis,solver,fem,_implicit_interface=True)
    root = Path(output_root).resolve()/('F'+uuid.uuid4().hex)
    root.mkdir(parents=True,exist_ok=False)
    original = analysis.Document.FileName
    original_sha = _hash(Path(original)) if original and Path(original).is_file() else None
    analysis.Document.saveCopy(str(root/'editable.FCStd'))
    if analysis.Document.FileName != original or not (root/'editable.FCStd').is_file():
        raise ValueError('편집 가능한 원 모델 사본을 보존하지 못했습니다. 입력을 다시 준비하세요.')
    _json(root/'mesh.json',model)
    mail,_,_ = mesh_text(model)
    (root/'mesh.mail').write_text(mail,encoding='ascii',newline='\n')
    (root/'model.comm').write_text(command_text(),encoding='ascii',newline='\n')
    after,current = collect(analysis,solver,fem,_implicit_interface=True)
    if after != model or current != identity or (original_sha and _hash(Path(original)) != original_sha):
        raise ValueError('입력 준비 중 모델이 바뀌었습니다. 원본을 확인하고 다시 준비하세요. 계산은 시작하지 않았습니다.')
    files = [dict(relative=p.name,bytes=p.stat().st_size,sha256=_hash(p)) for p in sorted(root.iterdir())]
    manifest = root/'snapshot.json'
    _json(manifest,dict(kind='freecad-contact-frozen',schema_version='1',id=root.name,backend=BACKEND,
        input_file='model.comm',files=files,native_version=list(App.Version()),analysis_id=analysis.Name,
        solver_id=solver.Name,bodies=identity,document=dict(name=analysis.Document.Name,original_sha256=original_sha),
        solver_execution='NOT_PERFORMED',qualification='UNKNOWN',decision='NOT_RELEASED'))
    validate_snapshot(manifest)
    return manifest
