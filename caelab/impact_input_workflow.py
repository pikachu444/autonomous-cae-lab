"""GUI-neutral commands for the EXISTING Simulation owner.

All values are ordinary settings/drafts accepted by the existing document API.
No private workspace, command queue, solver lookup or second owner is created.
The caller must explicitly apply a returned definition via simulation.update.
"""
from copy import deepcopy
from .impact_source import capture,resolve,SourceError,export_effective
from .impact_model import default_settings,model_from_settings,validate_settings,BACKEND
from .impact_input_edits import view,replace_range,original_offset
from .storage import canonical_hash


LABELS={'X':'X 위치','Y':'Y 위치','Z':'Z 위치','rho':'밀도','density':'밀도','E':'탄성계수','nu':'푸아송 비',
        'VX':'X 속도','VY':'Y 속도','VZ':'Z 속도','end_s':'종료 시간',
        'field_interval_s':'장면 출력 간격','history_interval_s':'이력 출력 간격',
        'scale':'CFL 계수','target_step_s':'질량 스케일링 목표 증분','friction':'마찰계수'}


def open_definition(entry,root,*,engine=None,units=None):
    source=capture(entry,root,engine=engine,units=units)
    settings=default_settings();settings['source']=source
    if source['format']=='RAD':
        from .impact_native import settings_from_source
        try:settings=settings_from_source(source)
        except (ValueError,KeyError,TypeError):pass # retain an editable, explicitly blocked draft
    return {'backend':BACKEND,'settings':settings}


def admitted_guard_paths(settings):
    """Only verified *logical source member names*, never executable paths."""
    source=settings.get('source')
    if not isinstance(source,dict):raise ValueError('원 입력 정의를 확인하세요')
    resolve(source)
    files=source.get('bundle',{}).get('files',[])
    return frozenset(('source','bundle','files',i,'path') for i in range(len(files)))


def _review_scope(source,error):
    """Conservative review scope, NOT a claim to interpret an unsupported card."""
    result=deepcopy(getattr(error,'impact',{}))
    result.update(file=getattr(error,'file',None),line=getattr(error,'line',None),
                  occurrence=getattr(error,'occurrence',None),execution='BLOCKED')
    if source.get('format')=='RAD':
        result['affected_decks']=['Starter','Engine'];return result
    try:
        text,spans=resolve(source)
        from .impact_assembly import tokenize
        blocks=tokenize(text,spans)
        result['review_instances']=[b['options'] for b in blocks if b['card']=='INSTANCE']
        result['review_sets']=[{'card':b['card'],'options':b['options'],'source':b['origin']} for b in blocks if b['card'] in ('NSET','ELSET','SURFACE')]
        result['review_conditions']=[{'card':b['card'],'source':b['origin']} for b in blocks if b['card'] in ('BOUNDARY','CLOAD','DLOAD','INITIAL CONDITIONS','CONTACT PAIR')]
        result['scope_semantics']='보수적 재검토 범위; 미지원 카드의 물리 영향을 계산한 목록이 아님'
    except (ValueError,KeyError,TypeError):pass
    return result


def inspect(settings):
    """A table/source/error view is available even for a non-runnable draft."""
    source=settings.get('source',{});files=source.get('bundle',{}).get('files',[])
    table=[{'file':f.get('path'),'bytes':len(f.get('text','').encode('ascii',errors='replace')),
            'edited':any(h.get('file')==f.get('path') for h in source.get('edits',[]))} for f in files]
    report={'title':source.get('title','충격 입력'),'route':'원 RAD 직접 실행' if source.get('format')=='RAD' else '계층 INP 변환 실행',
            'files':table,'source_revision':canonical_hash(source),'readiness':'BLOCKED','runtime':'NOT_PROBED',
            'save_draft':True,'blockers':[],'fields':[],'targets':[],'instances':[]}
    try:
        validate_settings(settings);model=model_from_settings(settings)
        report.update(readiness='INPUT_ADMITTED_RUNTIME_NOT_PROBED',node_count=len(model['nodes']),element_count=len(model['elements']))
        for kind,label in (('nsets','절점 집합'),('elsets','요소 집합'),('surfaces','면')):
            for key,values in model[kind].items():
                lineage=model.get('lineage',{}).get(kind,{}).get(key,{})
                report['targets'].append({'key':key,'label':lineage.get('qualified_name',lineage.get('label',key)),
                    'kind':kind,'kind_label':label,'count':len(values),'source':deepcopy(lineage)})
        report['instances']=[{'name':name,**deepcopy(value)} for name,value in model.get('lineage',{}).get('instances',{}).items()]
        if source.get('format')=='RAD':
            from .impact_native import parse_source
            parsed=parse_source(source)
            report['fields']=[{**deepcopy(f),'label':f.get('label',LABELS.get(f['field'],f['field']))} for f in parsed['fields']]
        report['source_lineage']=deepcopy(model.get('lineage',{}))
        from .impact_initial_state import describe
        if source.get('format')=='RAD':initial=parsed['initial']
        else:
            from .impact_model import render
            _,initial=render(settings)
        report['initial_state']=describe(model,initial,settings)
    except (ValueError,KeyError,TypeError,OverflowError) as error:
        report['blockers'].append({'message':str(error),'severity':'error','next_action':'원문 위치 열기 → 명시 수정 → 적용',
                                   **_review_scope(source,error)})
    return report


def source_view(settings,file):return view(settings['source'],file)


def apply_text(settings,*,file,start,end,replacement,reason,expected_definition_sha256):
    if canonical_hash(settings)!=expected_definition_sha256:raise SourceError('화면을 연 뒤 입력 정의가 바뀌었습니다. 다시 읽고 적용하세요')
    result=deepcopy(settings)
    from .impact_reference_bindings import KEY,preserve_before_edit
    try: result[KEY]=preserve_before_edit(settings)
    except (ValueError,KeyError,TypeError):
        if any(settings.get(k) for k in ('motions','contacts','responses')):
            raise SourceError('원 대상 대응이 확인되지 않는 초안입니다. 먼저 대상 선택을 비우거나 원문을 복구하세요')
    result['source']=replace_range(settings['source'],file,start,end,replacement,reason=reason,
                                  expected_source_sha256=canonical_hash(settings['source']))
    if result['source']['format']=='RAD':
        from .impact_native import settings_from_source
        try:
            projected=settings_from_source(result['source'])
            for key in ('time','gravity_mm_s2','motions','contacts'):result[key]=projected[key]
            for key in ('cohesive','bulk_damage','interface_controls'):result[key]=deepcopy(projected.get(key,[]))
        except (ValueError,KeyError,TypeError):pass # explicit incomplete draft, not an execution bypass
    return {'settings':result,'inspection':inspect(result),'applied_to_document':False}


def apply_effective_text(settings,*,file,start,end,replacement,reason,expected_definition_sha256):
    source=settings['source']
    return apply_text(settings,file=file,start=original_offset(source,file,start),end=original_offset(source,file,end),
                      replacement=replacement,reason=reason,expected_definition_sha256=expected_definition_sha256)


def apply_native_field(settings,field_id,value,*,reason,expected_definition_sha256):
    if canonical_hash(settings)!=expected_definition_sha256:raise SourceError('현재 입력 정의가 바뀌었습니다. 다시 읽고 적용하세요')
    from .impact_native import edit_field
    updated=edit_field(settings,field_id,value,reason=reason,expected_source_sha256=canonical_hash(settings['source']))
    return {'settings':updated,'inspection':inspect(updated),'applied_to_document':False}


def response_for_source(settings,*,quantity,component,association,name=None,instance=None,local_id=None,native_id=None):
    model=model_from_settings(settings)
    if instance is not None:
        if native_id is not None:raise ValueError('instance/local 또는 native ID 중 한 가지를 선택하세요')
        from .impact_assembly import exact_entity
        identity=exact_entity(model,association,instance,local_id)
    else:
        identity=native_id
    from .impact_responses import QUANTITIES,validate
    if quantity not in QUANTITIES or QUANTITIES[quantity][1]!=association:raise ValueError('응답의 절점/요소 위치 종류를 확인하세요')
    if name is None:
        used={r['name'] for r in settings.get('responses',[])};index=1
        while 'selected_'+str(index) in used:index+=1
        name='selected_'+str(index) # internal key; GUI shows source instance/local ID and physical label
    row={'name':name,'quantity':quantity,'component':component,'identity':identity}
    validate(model,[row]);return row


def entities(settings,*,association,start=0,count=128,instance=None):
    if type(start) is not int or type(count) is not int or start<0 or not 1<=count<=512:raise ValueError('표 페이지 범위를 확인하세요')
    if association not in ('POINTS','CELLS'):raise ValueError('절점 또는 요소 표를 선택하세요')
    model=model_from_settings(settings);kind='nodes' if association=='POINTS' else 'elements'
    lineage=model.get('lineage',{}).get(kind,{})
    ids=[n for n in sorted(model[kind]) if instance is None or lineage.get(str(n),{}).get('instance')==instance.upper()]
    return {'total':len(ids),'start':start,'rows':[{'native_id':n,'value':deepcopy(model[kind][n]),
        'source':deepcopy(lineage.get(str(n),{}))} for n in ids[start:start+count]]}


def export(settings,path):return export_effective(settings,path)


def declare_native_units(settings, *, units, acknowledged, expected_definition_sha256):
    """An explicit declaration, never a conversion or automatic unit repair."""
    if canonical_hash(settings)!=expected_definition_sha256 or acknowledged is not True:
        raise SourceError('원 INPUT/WORK 단위를 확인하고 명시적으로 적용하세요')
    if settings.get('source',{}).get('format')!='RAD' or units!='Mg/mm/s':
        raise SourceError('다른 native 단위의 자동 변환은 지원하지 않습니다')
    result=deepcopy(settings);result['source']['units']=units
    result['source'].setdefault('provenance',{})['units_declared_by_user']=True
    from .impact_native import settings_from_source
    projected=settings_from_source(result['source']) # actual source rows must agree
    for key in ('time','gravity_mm_s2','motions','contacts'):result[key]=projected[key]
    for key in ('cohesive','bulk_damage','interface_controls'):result[key]=deepcopy(projected.get(key,[]))
    return {'settings':result,'inspection':inspect(result),'applied_to_document':False}


def editor_buffer(settings, file):
    """Text for Qt's LF-normalized view; offsets stay private to the adapter.

    Imported source is ASCII, so a Qt UTF-16 cursor position equals a displayed
    character position. CRLF still counts as ONE displayed newline, TWO bytes.
    """
    from .impact_input_edits import original_files, edited_files
    source=settings['source'];original=original_files(source);effective=edited_files(source)
    if file not in effective:raise SourceError('선택한 원 입력 파일이 없습니다',file)
    normalize=lambda value:value.decode('ascii').replace('\r\n','\n').replace('\r','\n')
    return {'file':file,'original_text':normalize(original[file]),'effective_text':normalize(effective[file]),
            'definition_sha256':canonical_hash(settings),'source_revision':canonical_hash(source),
            'selection_semantics':'ASCII_QT_DISPLAY_CHARACTERS_NOT_RAW_BYTES'}


def apply_display_range(settings, *, file, start, end, replacement, reason, expected_definition_sha256):
    """Replace an explicitly selected source range from the familiar text view.

    Only the selected range changes; Qt newline normalization never rewrites the
    rest of the file. New lines in the replacement use the next original line's
    terminator (or the file's first terminator at EOF). No GUI sends byte offsets.
    """
    import re
    from .impact_input_edits import edited_files
    if type(start) is not int or type(end) is not int or not 0<=start<=end:
        raise SourceError('원문에서 바꿀 범위를 선택하세요',file)
    if not isinstance(replacement,str):raise SourceError('수정 원문은 텍스트여야 합니다',file)
    try:replacement.encode('ascii')
    except UnicodeEncodeError as error:raise SourceError('INP/RAD 원문은 ASCII입니다. 설명은 한글 메모에 입력하세요',file) from error
    current=editor_buffer(settings,file)
    if end>len(current['effective_text']):raise SourceError('표시된 원문 범위를 벗어났습니다',file)
    raw=edited_files(settings['source'])[file];positions={};display=0;offset=0
    while offset<=len(raw):
        if display in (start,end):positions[display]=offset
        if display==end:break
        offset+=2 if raw[offset:offset+2]==b'\r\n' else 1
        display+=1
    a,b=positions[start],positions[end]
    delimiter=re.search(b'\r\n|\r|\n',raw[a:]) or re.search(b'\r\n|\r|\n',raw)
    eol=delimiter.group().decode('ascii') if delimiter else '\n'
    replacement=replacement.replace('\r\n','\n').replace('\r','\n').replace('\n',eol)
    return apply_effective_text(settings,file=file,start=a,end=b,replacement=replacement,reason=reason,
                               expected_definition_sha256=expected_definition_sha256)
