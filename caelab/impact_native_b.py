"""Exact retained TYPE24 history cards in the existing elastic native subset.

This projects source cards into B's existing definition. It never generates,
removes or rewrites a card, and does not establish output units or qualification.
"""
from copy import deepcopy

from . import impact_bulk_deck, impact_interface, impact_bulk_results


def run_name(settings):
    if settings.get('source',{}).get('format')!='RAD':return 'impact'
    from .impact_native import parse_source
    return parse_source(settings['source'])['name']


def definition(starter, text, model, settings, material_projection=None):
    from .impact_native import _error, _rows, _tail, _integer
    contacts=[c for c in starter if c['key'].startswith('/INTER/TYPE24/')]
    exact={int(c['key'].rsplit('/',1)[1]):i for i,c in enumerate(contacts)}
    groups=[]; source_cards={}; seen=set(); titles=set()
    for card in starter:
        if not card['key'].startswith('/TH/INTER/'):continue
        rows=_rows(card,3);title=rows[0].strip()
        if not title or len(title)>100 or title in titles:
            _error(card,'접촉쌍 이력 제목이 비어 있거나 중복되었습니다')
        _tail(rows[1],60,card)
        tokens=[rows[1][i:i+10].strip() for i in range(0,60,10)]
        if tokens!=list(impact_bulk_deck.PAIR_TOKENS):
            _error(card,'첫 native 접촉쌍 이력은 FNX FNY FNZ FTX FTY FTZ 순서의 명시 여섯 성분입니다')
        _tail(rows[2],10,card);member=_integer(rows[2][:10],card)
        if member not in exact or member in seen:
            _error(card,'접촉쌍 이력은 실제 TYPE24 한 쌍을 중복 없이 참조해야 합니다')
        index=exact[member];pair=settings['contacts'][index]
        groups.append({'id':int(card['key'].rsplit('/',1)[1]),'type':101,'kind':'pair',
            'title':title,'members':[member],'tokens':tokens,'pair':deepcopy(pair),'contact_index':index,
            'normal_tangent':'signed native components, global axes, not sum of absolute values',
            'surface_order':{'surface1':pair['b'],'surface2':pair['a']},
            'native_store_semantics':'CUMULATIVE_IMPULSE_REQUIRES_PINNED_PRODUCER',
            'converter_source_commit':'NOT_PROVEN_BY_RELEASE'})
        source_cards[card['key']]=rows;seen.add(member);titles.add(title)
    if material_projection is not None:
        from .impact_native_material_cards import receipts
        bulk,cohesive,interface=receipts(starter,text,model,settings,material_projection)
    else:
        unchanged,bulk=impact_bulk_deck.apply(text,model,[])
        cohesive={'elements':{},'geometry':{},'status':'NOT_REQUESTED_NATIVE_ELASTIC'}
        unchanged,interface=impact_interface.apply(unchanged,model,settings,cohesive)
        if unchanged!=text:raise ValueError('native 출력 정의 투영이 원문을 변경했습니다')
    for card in starter:
        if not card['key'].startswith('/TH/BRIC/'):continue
        rows=_rows(card,4);title=rows[0].strip()
        if not title or len(title)>100 or title in titles:_error(card,'벌크 이력 제목이 비거나 중복됩니다')
        tokens=[]
        for row in rows[1:3]:
            _tail(row,100,card)
            tokens.extend(row[i:i+10].strip() for i in range(0,len(row.rstrip()),10))
        if tokens!=list(impact_bulk_deck.BRICK_TOKENS):_error(card,'기존 단일 IP 벌크 이력 성분과 순서를 보존하세요')
        member=_integer(rows[3][:10],card)
        if rows[3][10:20].strip() or len(rows[3])>120:_error(card,'벌크 이력은 명시 단일 요소와 원 이름만 지원합니다')
        if str(member) not in bulk['elements']:_error(card,'벌크 이력은 원 INIEVO 벌크 요소를 참조해야 합니다')
        if any(g['kind']=='bulk' and g['members']==[member] for g in groups):_error(card,'원 요소 이력의 중복 배정입니다')
        groups.append({'id':int(card['key'].rsplit('/',1)[1]),'type':1,'kind':'bulk','title':title,
            'members':[member],'tokens':tokens,'ip_scope':'native HEPH single material IP; no generic reduction',
            'material_id':bulk['elements'][str(member)]['material_id']})
        source_cards[card['key']]=rows;titles.add(title)
    if not groups and not bulk['elements'] and not cohesive['elements']:return None
    from .impact_b import model_identity,verify
    result={'version':1,'model_identity':model_identity(model),'bulk':bulk,'cohesive':cohesive,
        'interface':interface,'outputs':{'groups':groups,'generated_cards':source_cards,
            'unavailable':['bulk_damage_dissipation','native_temperature_failure_axis','TYPE24_SFW','TYPE24_CE_DAMP']},
        'native_acceptance':'NOT_RUN'}
    verify(text,model,settings,result)
    return result


def validate_selections(model, settings, native_definition):
    impact_bulk_results.validate(model,settings)
    declared={g['contact_index']:g for g in (native_definition or {}).get('outputs',{}).get('groups',[]) if g['kind']=='pair'}
    bulk={g['members'][0] for g in (native_definition or {}).get('outputs',{}).get('groups',[]) if g['kind']=='bulk'}
    for row in settings.get('b_responses',[]):
        if row['scope']=='interface':
            if str(row['identity']) not in (native_definition or {}).get('cohesive',{}).get('elements',{}):
                raise ValueError('원 LAW117 요소를 선택하세요')
            continue
        if row['scope']=='bulk':
            if row['identity'] not in bulk:raise ValueError('원 TH/BRIC 이력이 있는 벌크 요소를 선택하세요')
            continue
        if row['identity'] not in declared:
            raise ValueError('원 /TH/INTER 카드가 있는 정확한 접촉쌍 응답을 선택하세요')
        if row['component'] not in declared[row['identity']]['tokens']:
            raise ValueError('원 접촉쌍 카드에 선택 성분이 없습니다')


def select_response(settings, *, native_contact_id, quantity, component, name, replace_name=None):
    """Explicitly select an actual native member; no default response is invented."""
    from .impact_native import parse_source,validate_settings
    validate_settings(settings)
    parsed=parse_source(settings['source'])
    if type(native_contact_id) is not int:raise ValueError('실제 native 접촉쌍을 선택하세요')
    groups=[g for g in (parsed['b_definition'] or {}).get('outputs',{}).get('groups',[])
            if g['kind']=='pair' and g['members']==[native_contact_id]]
    if len(groups)!=1:raise ValueError('선택한 native 접촉쌍의 원 이력 카드가 없습니다')
    result=deepcopy(settings);rows=result.setdefault('b_responses',[])
    row={'name':name,'scope':'pair','identity':groups[0]['contact_index'],'quantity':quantity,'component':component}
    if replace_name is None:rows.append(row)
    else:
        matches=[i for i,r in enumerate(rows) if r['name']==replace_name]
        if len(matches)!=1:raise ValueError('수정할 기존 응답을 명시적으로 선택하세요')
        rows[matches[0]]=row
    # An explicit selection replaces its old receipt through the existing review.
    from .impact_reference_bindings import KEY,snapshot
    if KEY in result:
        result[KEY]=snapshot(result)
    validate_settings(result)
    return result


def select_material_response(settings, *, scope, native_element_id, quantity, component, name, replace_name=None):
    """Select only an actual retained bulk history member or LAW117 element."""
    from .impact_native import parse_source,validate_settings
    validate_settings(settings);parsed=parse_source(settings['source'])
    if type(native_element_id) is not int or scope not in ('bulk','interface'):
        raise ValueError('벌크 또는 계면의 실제 원 요소를 선택하세요')
    definition=parsed['b_definition'] or {}
    admitted=({g['members'][0] for g in definition.get('outputs',{}).get('groups',[]) if g['kind']=='bulk'}
              if scope=='bulk' else {int(e) for e in definition.get('cohesive',{}).get('elements',{})})
    if native_element_id not in admitted:raise ValueError('원 재료/이력 카드에 선택 요소가 없습니다')
    result=deepcopy(settings);rows=result.setdefault('b_responses',[])
    row={'name':name,'scope':scope,'identity':native_element_id,'quantity':quantity,'component':component}
    if replace_name is None:rows.append(row)
    else:
        matches=[i for i,r in enumerate(rows) if r['name']==replace_name]
        if len(matches)!=1:raise ValueError('수정할 기존 응답을 명시적으로 선택하세요')
        rows[matches[0]]=row
    from .impact_reference_bindings import KEY,snapshot
    if KEY in result:result[KEY]=snapshot(result)
    validate_settings(result)
    return result
