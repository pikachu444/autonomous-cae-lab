"""Validate connector exports with the existing frozen native input registrar."""
from pathlib import Path
import json
from .dynamic_result_store import verify_pin
from .connector_model import model

KIND='freecad-connector-frozen'


def validate_snapshot(path):
    path=Path(path).resolve(strict=True)
    if path.stat().st_size>8*1024**2:raise ValueError('연결요소 입력 목록이 허용 크기를 넘습니다.')
    manifest=json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('kind')!=KIND or manifest.get('schema_version')!='1' or manifest.get('input_file')!='input.json':
        raise ValueError('완료된 연결요소 입력을 선택하세요.')
    files=manifest.get('files',[]);names=[p.get('relative') for p in files]
    if len(names)!=len(set(names)) or any(not isinstance(n,str) or Path(n).name!=n or any(c in n for c in '/\\:\x00') for n in names):
        raise ValueError('연결요소 입력의 파일 목록이 잘못됐습니다.')
    for pin in files:verify_pin(path.parent,pin)
    settings=json.loads((path.parent/'input.json').read_text(encoding='utf-8'))
    if set(settings)!= {'connector'}:raise ValueError('동결 입력의 연결요소 설정이 다릅니다.')
    m=model(settings['connector'])
    expected={'input.json','editable.caepre'}|({'original-fe.inp'} if m['fe'] else {'connector_0000.rad','connector_0001.rad'})
    if set(names)!=expected:raise ValueError('편집 원본·원 FE 입력·native 생성 입력이 누락됐습니다.')
    if manifest.get('source_selections')!=[e['selection'] for e in m['endpoints']]:
        raise ValueError('원 CAD/메시 선택과 동결 입력이 다릅니다.')
    if m['fe']:
        from .impact_model import render
        expected_text,_=render(m['fe']['settings'])
        if (path.parent/'original-fe.inp').read_text(encoding='ascii')!=expected_text:
            raise ValueError('원 탄성 FE 입력과 동결 설정이 다릅니다.')
    else:
        from .connector_deck import starter,engine
        for name,text in [('connector_0000.rad',starter(m)),('connector_0001.rad',engine(m))]:
            if (path.parent/name).read_text(encoding='ascii')!=text:raise ValueError('동결 native 연결요소 입력이 다릅니다.')
    return manifest,m,settings,[path,*[path.parent/n for n in names]]


def resolve(settings):
    if set(settings)=={'data_id','snapshot_path'}:
        _,_,value,_=validate_snapshot(settings['snapshot_path'])
        return value
    return settings
