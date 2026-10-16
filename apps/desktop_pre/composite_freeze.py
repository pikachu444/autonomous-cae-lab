"""Same native Project/READY/frozen-input protocol, explicit laminate profile."""
from pathlib import Path
import shutil
import threading
import uuid

from caelab.composite_shell import PROFILE, BACKEND
from caelab.shell_model import digest
from caelab.storage import save_json
from caelab.adapters.composite_shell_deck import KIND, MESH_KIND, build, validate_snapshot
from caelab.adapters.shell_deck import native_mesh, read_bytes, sha


def freeze(editor,analysis_id):
    from .freeze_analysis import require_ready_model, _serialized_coordinate_close
    owner=editor.owner;owner.assert_thread();owner._idle()
    if threading.current_thread() is not threading.main_thread() or list(owner.App.Version())[:3]!=['1','1','4']:
        raise ValueError('적층 입력은 FreeCAD 1.1.4의 현재 GUI 문서에서 준비합니다.')
    require_ready_model(owner.doc,owner=owner)
    editor.effective(analysis_id);editor.clear_preview()
    saved=owner.project.save()
    record,mesh,fixed=editor.effective(analysis_id)
    draft=record['draft'];before=editor._native_state(draft);generation=owner.generation
    doc=owner.doc;filename=doc.FileName
    if doc.isTouched() or any(set(o.State)&{'Touched','Invalid','Error','Recompute'} for o in doc.Objects):
        raise ValueError('문서 재계산과 편집을 마친 뒤 적층 입력을 준비하세요.')
    original_hash=sha(Path(filename)) if filename and Path(filename).is_file() else None
    folder=Path(owner.export_root).resolve()/owner.document_id/('F'+uuid.uuid4().hex)
    folder.mkdir(parents=True,exist_ok=False);snapshot=folder/'snapshot.json'
    try:
        doc.saveCopy(str(folder/'editable.FCStd'))
        editor._object(draft['mesh_id']).FemMesh.writeABAQUS(str(folder/'native_mesh.inp'),1,False,
            volVariant='standard',faceVariant='shell',edgeVariant='beam')
        native_text=read_bytes(folder/'native_mesh.inp').decode('ascii')
        nodes,elements=native_mesh(native_text);_,live_nodes,live_elements=editor._mesh(draft)
        if set(nodes)!=set(live_nodes) or elements!=live_elements or any(
            not all(_serialized_coordinate_close(a,b) for a,b in zip(live_nodes[n],xyz)) for n,xyz in nodes.items()):
            raise ValueError('Native 8절점 메시 내보내기가 원 좌표·연결과 다릅니다.')
        model={'schema_version':'1','kind':MESH_KIND,'profile':PROFILE,
               'units':{'position':'mm','stress':'MPa','force':'N'},
               'source_nodes':{str(n):xyz for n,xyz in nodes.items()},
               'source_elements':{str(e):list(c) for e,c in elements.items()},
               'native_mesh':native_text,'draft':draft,'applied':record['applied'],'fixed_nodes':fixed,
               'output_contract':{'DAT':'GLOBAL S,E; 8 native IP per layer; two thickness IP per layer',
                   'FRD':'GLOBAL nodal extrapolated/averaged per expanded layer solid',
                   'COORD':'NOT_REQUESTED','RF':'NOT_REQUESTED','layer_order':'UI top(+normal) first; native bottom(-normal) first'}}
        deck,_=build(model);(folder/'composite.inp').write_bytes(deck.encode('ascii'));save_json(folder/'mesh.json',model)
        retained=saved.get('retained_project')
        if not retained:raise ValueError('편집 가능한 .caepre 저장본을 먼저 저장하세요.')
        shutil.copyfile(retained,folder/'editable.caepre')
        if (owner.generation!=generation or editor._native_state(draft)!=before or doc.FileName!=filename or
            doc.isTouched() or original_hash and sha(Path(filename))!=original_hash):
            raise ValueError('입력 준비 도중 원 모델이 바뀌었습니다. 실패 파일을 보존합니다.')
        require_ready_model(doc,owner=owner)
        manifest={'schema_version':'1','kind':KIND,'id':folder.name,'analysis_id':analysis_id,
                  'native_version':list(owner.App.Version()),'input_file':'composite.inp',
                  'editable_project':'editable.caepre','applied_sha256':digest(record['applied']),
                  'files':[{'relative':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(folder.iterdir()) if p.is_file()],
                  'solver_execution':'NOT_PERFORMED','qualification':'UNKNOWN'}
        save_json(snapshot,manifest);validate_snapshot(snapshot)
    except Exception as error:
        if snapshot.exists():snapshot.rename(folder/'snapshot.failed.json')
        save_json(folder/'preparation_failure.json',{'type':type(error).__name__,'message':str(error)})
        raise
    return {'snapshot_relative':snapshot.relative_to(owner.export_root).as_posix(),
            'label':doc.Label+' 적층 셸','backend':BACKEND,'input_prepared':True,
            'solver_execution':'NOT_PERFORMED','applied_sha256':digest(record['applied'])}
