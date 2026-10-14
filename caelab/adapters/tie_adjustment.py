"""Independent CAE admission/file glue; never imports the GPL projection program."""
from pathlib import Path
import hashlib
import json
import sys
import sysconfig
import numpy as np

from ..contact import number
from ..contact_deck import FACES
from ..execution_control import run_owned_command, check_cancelled


def cases(model, nodes, elements):
    adjusted = [p for p in model['contacts'] if p['draft']['normal_law']=='tie' and p['draft'].get('tie_adjust',False)]
    if not adjusted:
        return [], []
    surface_nodes = lambda side:{elements[e][i] for e,f in side['element_faces'] for i in FACES[f]}
    all_masters = set().union(*(surface_nodes(p['b']) for p in model['contacts']))
    requested, rows, seen = [], [], set()
    for pair in adjusted:
        slaves = surface_nodes(pair['a'])
        if slaves & (seen | all_masters):
            raise ValueError('조정할 A면 절점이 다른 접합이나 기준 면과 겹칩니다. 연쇄 조정은 지원하지 않습니다.')
        seen.update(slaves)
        triangles=[]
        for e,f in pair['b']['element_faces']:
            points=np.asarray([nodes[elements[e][i]] for i in FACES[f]],dtype=float)
            a=points[0]; basis=np.column_stack((points[1]-a,points[2]-a))
            scale=max(float(np.max(np.abs(points))),float(np.max(np.abs(basis))),1.)
            roundoff=128*np.finfo(float).eps*scale
            expected=(points[:3]+points[[1,2,0]])/2
            if np.max(np.abs(points[3:]-expected))>roundoff:
                raise ValueError('면에 맞춤은 평면의 직선 중간절점을 가진 C3D10 면만 지원합니다.')
            normal=np.cross(basis[:,0],basis[:,1]); length=float(np.linalg.norm(normal))
            if length<=roundoff*max(float(np.linalg.norm(basis)),1.):
                raise ValueError('조정 기준 면의 삼각형이 퇴화했습니다. 메시를 수정하세요.')
            normal/=length
            triangles.append((points,a,basis,normal))
        reference=triangles[0]
        for points,a,basis,normal in triangles:
            scale=max(float(np.max(np.abs(points))),1.)
            if np.max(np.abs((points-reference[1])@reference[3]))>128*np.finfo(float).eps*scale:
                raise ValueError('면에 맞춤은 하나의 평면에 있는 B면 집합만 지원합니다.')
        for node in sorted(slaves):
            original=np.asarray(nodes[node],dtype=float)
            candidates=[]
            for points,a,basis,normal in triangles:
                distance=float((original-a)@normal)
                projected=original-distance*normal
                uv=np.linalg.solve(basis.T@basis,basis.T@(projected-a))
                margin=128*np.finfo(float).eps*max(1.,float(np.linalg.cond(basis)))
                if min(float(uv[0]),float(uv[1]),float(1.-uv.sum()))>margin:
                    if abs(distance)<=number(pair['draft']['tie_tolerance_mm']):
                        candidates.append(points.tolist())
            if len(candidates)!=1:
                raise ValueError('A면 절점을 허용거리 안의 B면 내부 한 곳에 대응시킬 수 없습니다. 경계·중복 면·큰 간극을 확인하세요.')
            requested.append({'face':candidates[0],'point':original.tolist()})
            rows.append({'node_id':node,'pair_id':pair['object_id'],'original_mm':original.tolist()})
    return requested,rows


def expected_coordinates(model,nodes,elements,folder):
    """Run the standalone numerical command with generic files, before ccx."""
    from .frozen_fem import _jacobian_gates, _read, _sha
    requests,rows=cases(model,nodes,elements)
    if not requests:
        return nodes,None
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=False)
    source=Path(__file__).resolve().parents[2]/'third_party/calculix_projection/projection.py'
    installed=Path(sysconfig.get_path('data'))/'share/autonomous-cae-lab/calculix_projection/projection.py'
    program=source if source.is_file() else installed
    if not program.is_file():
        raise ValueError('절점 맞춤 계산 도구가 없습니다. 설치 파일을 다시 확인하세요.')
    input_path=folder/'points.json'; output_path=folder/'projected.json'
    input_path.write_text(json.dumps({'cases':requests},allow_nan=False),encoding='utf-8')
    program_sha=_sha(program); input_sha=_sha(input_path)
    completed=run_owned_command([sys.executable,'-I',str(program),'--input',str(input_path),'--output',str(output_path)],folder,'tie_projection')
    if completed.returncode:
        raise ValueError('절점 맞춤 계산이 실패했습니다. 원 입력과 오류 기록은 보존됩니다.')
    check_cancelled()
    if _sha(program)!=program_sha or _sha(input_path)!=input_sha:
        raise ValueError('절점 맞춤 도구 또는 입력이 계산 중 변경됐습니다.')
    payload=json.loads(_read(output_path))
    results=payload['projections']
    if len(results)!=len(rows):
        raise ValueError('절점 맞춤 결과 개수가 입력과 다릅니다.')
    expected={n:list(xyz) for n,xyz in nodes.items()}
    for row,result in zip(rows,results):
        if set(result)!={'point','weights'} or len(result['point'])!=3 or len(result['weights'])!=6:
            raise ValueError('절점 맞춤 결과 형식이 잘못됐습니다.')
        row.update(expected_mm=[number(v) for v in result['point']],weights=[number(v) for v in result['weights']])
        expected[row['node_id']]=row['expected_mm']
    quality=_jacobian_gates(expected,elements)
    receipt={'method':'CalculiX_2.22_attach_2d_six_node','upstream_commit':'cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54',
             'tool_sha256':program_sha,'input_sha256':input_sha,'output_sha256':_sha(output_path),
             'units':'mm','displacement_reference':'adjusted_solver_initial_coordinates',
             'original_model_sha256':hashlib.sha256(json.dumps(model,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
             'expected_quality':quality,'rows':rows}
    (folder/'expected.json').write_text(json.dumps(receipt,allow_nan=False),encoding='utf-8')
    return expected,receipt


def retained_coordinates(model,nodes,elements,folder):
    """Use the pinned previous projection, never recompute with a changed tool."""
    from .frozen_fem import _jacobian_gates, _read, _sha
    folder=Path(folder)
    requests,rows=cases(model,nodes,elements)
    receipt=json.loads(_read(folder/'expected.json'))
    digest=hashlib.sha256(json.dumps(model,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if (receipt.get('original_model_sha256')!=digest or receipt.get('units')!='mm' or
            receipt.get('input_sha256')!=_sha(folder/'points.json') or receipt.get('output_sha256')!=_sha(folder/'projected.json')):
        raise ValueError('저장된 절점 맞춤 입력·결과가 원 모델과 다릅니다.')
    if json.loads(_read(folder/'points.json'))!={'cases':requests} or len(receipt['rows'])!=len(rows):
        raise ValueError('저장된 절점 맞춤 요청이 원 면 선택과 다릅니다.')
    projected=json.loads(_read(folder/'projected.json'))['projections']
    if len(projected)!=len(rows):
        raise ValueError('저장된 절점 맞춤 결과 개수가 다릅니다.')
    expected={n:list(xyz) for n,xyz in nodes.items()}
    for retained,row,result in zip(receipt['rows'],rows,projected):
        if any(retained.get(k)!=row[k] for k in ('node_id','pair_id','original_mm')) or retained['expected_mm']!=result['point'] or retained['weights']!=result['weights']:
            raise ValueError('저장된 절점 맞춤 좌표가 같은 원 절점을 가리키지 않습니다.')
        expected[row['node_id']]=[number(v) for v in retained['expected_mm']]
    _jacobian_gates(expected,elements)
    return expected,receipt
