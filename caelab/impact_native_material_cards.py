"""Read retained B cards into existing domain definitions; never export a new deck."""
from copy import deepcopy
import re
from . import impact_bulk, impact_bulk_deck, impact_damage, impact_interface

FAMILIES = (r'/MAT/(?:PLAS_TAB|LAW36|LAW117)/[1-9][0-9]*',
            r'/FAIL/INIEVO/[1-9][0-9]*', r'/TABLE/1/[1-9][0-9]*',
            r'/BRICK/[1-9][0-9]*', r'/PROP/TYPE43/[1-9][0-9]*', r'/TH/BRIC/[1-9][0-9]*')


def _match(card, expected, widths):
    """Check the existing writer's fixed fields, including reserved blank ranges."""
    from .impact_native import _rows, _tail, _error
    from .adapters.impact_admission import _same
    rows = _rows(card, len(expected))
    for actual, wanted, layout in zip(rows, expected, widths):
        if layout is None:
            if actual.strip() != wanted.strip(): _error(card, '원 native 제목/법칙이 다릅니다')
            continue
        _tail(actual, sum(layout), card)
        offset = 0
        for width in layout:
            a, b = actual[offset:offset+width].strip(), wanted[offset:offset+width].strip()
            offset += width
            if not b:
                if a: _error(card, '지원하지 않는 예약 필드/옵션입니다')
            else:
                try:
                    if width==10:
                        if not re.fullmatch(r'[+-]?[0-9]+',a) or int(a)!=int(b):raise ValueError('정수 필드')
                    else:_same(float(a), float(b))
                except (ValueError, TypeError): _error(card, '고정 native 법칙 필드와 다릅니다')


def project(starter, model, material_ids, field):
    from .impact_native import _rows, _real, _integer, _tail, _title, _error
    table = {c['key']: c for c in starter}
    result = {'bulk_damage': [], 'cohesive': [], 'functions': set(), 'tables': set(), 'materials': {}}
    def function(fid, *, title=None, hardening=False):
        key = '/FUNCT/'+str(fid)
        if key not in table: raise ValueError('원 재료의 정확한 FUNCT가 없습니다: '+key)
        card = table[key]; rows = _rows(card, minimum=3); values=[]
        for index, row in enumerate(rows[1:], 1):
            _tail(row, 40, card)
            values.append([_real(row[:20], card), _real(row[20:40], card)])
            label=title or _title(card)
            field(card,index,'function_x',0,20,label=label+' / '+('소성변형률' if hardening else '삼축도'))
            field(card,index,'function_y',20,40,unit='MPa' if hardening else '1',label=label+' / '+('경화 응력' if hardening else '시작 소성변형률'))
        result['functions'].add(fid)
        return values
    for card in starter:
        key = card['key']
        if not re.fullmatch(r'/MAT/(?:PLAS_TAB|LAW36|LAW117)/[1-9][0-9]*', key): continue
        mid = int(key.rsplit('/',1)[1]); name = _title(card)
        if mid in material_ids or name in model['materials']: _error(card, '재료 번호/제목이 중복됩니다')
        rows = _rows(card, 5 if '/LAW117/' in key else 8)
        rho = _real(rows[1][:20],card)
        if rho <= 0: _error(card, '양의 체적 밀도 [Mg/mm³]가 필요합니다')
        field(card,1,'density',0,20,unit='Mg/mm^3',label=name+' / 체적 밀도')
        material = {'DENSITY': [[rho]]}
        if '/LAW117/' in key:
            en, et = _real(rows[2][:20],card), _real(rows[2][20:40],card)
            if min(en,et) <= 0: _error(card, '양의 계면 EN/ET [MPa/mm]가 필요합니다')
            law = impact_damage.default_law(name)
            criterion = _integer(rows[2][60:70],card)
            if criterion not in (1,2): _error(card, 'POWER 또는 BK 기준을 명시하세요')
            law.update(criterion='POWER' if criterion==1 else 'BK', deletion_points=_integer(rows[2][50:60],card))
            for label,start in (('normal_strength_mpa',20),('shear_strength_mpa',40)):
                law[label]=_real(rows[3][start:start+20],card)
                field(card,3,label,start,start+20,unit='MPa',label=name+' / '+('정상 강도' if start==20 else '전단 강도'))
            for index,label in enumerate(('mode_I_n_mm','mode_II_n_mm','power_exponent','bk_exponent','gamma')):
                law[label]=_real(rows[4][20*index:20*(index+1)],card)
                shown=('모드 I 파괴 에너지','모드 II 파괴 에너지','거듭제곱 지수','BK 지수','BK 가중 지수')[index]
                field(card,4,label,20*index,20*(index+1),unit='N/mm' if index<2 else '1',label=name+' / '+shown)
            material.update(ELASTIC=[[en,et,et,0.]], _elastic_type='TRACTION')
            expected=impact_bulk_deck.cards(impact_damage.law_card(mid,name,material,law))[key]
            expected[0]=rows[0] # Titles are retained metadata; the logical material key is uppercase.
            _match(card,expected,[None,[20],[20,20,10,10,10],[10,10,20,20,20],[20]*5])
            field(card,2,'EN',0,20,unit='MPa/mm',label=name+' / 정상 탄성')
            field(card,2,'ET',20,40,unit='MPa/mm',label=name+' / 전단 탄성')
            result['cohesive'].append(law)
        else:
            e,nu=_real(rows[2][:20],card),_real(rows[2][20:40],card)
            if e<=0 or not -1<nu<.5: _error(card,'양의 E와 -1 < ν < 0.5를 지정하세요')
            fid=_integer(rows[5][:10],card); curve=function(fid,title=name,hardening=True)
            if (curve[0][0]!=0 or any(x<0 or y<=0 for x,y in curve)
                    or any(b[0]<=a[0] or b[1]<a[1] for a,b in zip(curve,curve[1:]))):
                _error(card,'기존 단조 경화 표: 첫 소성변형률 0·양의 응력·증가 축이 필요합니다')
            material.update(ELASTIC=[[e,nu]], PLASTIC=[[y,x] for x,y in curve])
            for row,width in zip(rows[1:],[40,100,100,80,50,100,100]): _tail(row,width,card)
            field(card,2,'E',0,20,unit='MPa',label=name+' / 탄성계수')
            field(card,2,'nu',20,40,label=name+' / 포아송비')
        material_ids[mid]=name; model['materials'][name]=material
        model['lineage']['materials'][name]={'native_id':mid,'origin':deepcopy(card['origin']),'card':key}
        result['materials'][mid]=card
    for card in starter:
        if not card['key'].startswith('/FAIL/INIEVO/'): continue
        mid=int(card['key'].rsplit('/',1)[1]); name=material_ids.get(mid)
        if name is None or 'PLASTIC' not in model['materials'][name]: _error(card,'INIEVO는 정확한 LAW36 벌크 재료만 참조해야 합니다')
        rows=_rows(card,5);tid=_integer(rows[2][:10],card);table_key='/TABLE/1/'+str(tid)
        if table_key not in table: _error(card,'INIEVO의 원 TABLE/1이 없습니다')
        law=impact_bulk.default_law(name); ref=_real(rows[2][10:30],card)
        tab=table[table_key]; data=_rows(tab,minimum=4); dimension=_integer(data[1][:10],tab)
        _tail(data[1],10,tab)
        if dimension==1:
            points=[]
            for index,row in enumerate(data[2:],2):
                _tail(row,40,tab);points.append([_real(row[:20],tab),_real(row[20:40],tab)])
                field(tab,index,'eta',0,20,label=name+' / 시작 삼축도')
                field(tab,index,'initiation_strain',20,40,label=name+' / 시작 소성변형률')
            eta=[p[0] for p in points]; rates=[]; values=[[p[1] for p in points]]; fids=[]
        elif dimension==2:
            points=[];rates=[];values=[];fids=[]
            for index,row in enumerate(data[2:],2):
                fid=_integer(row[:10],tab); points.append(function(fid,title=name)); fids.append(fid)
                rates.append(_real(row[20:40],tab)*ref)
                field(tab,index,'normalized_rate',20,40,label=name+' / 정규화 EPSD')
            eta=[p[0] for p in points[0]]
            if any([p[0] for p in line]!=eta for line in points): _error(tab,'각 rate의 동일 eta 축을 명시하세요')
            values=[[p[1] for p in line] for line in points]
        else: _error(tab,'기존 시작표는 eta 및 선택 EPSD의 1/2차원입니다')
        law['initiation'].update(eta=eta,rates_s_inv=rates,plastic_strain=values,sr_ref_s_inv=ref)
        law['evolution']['gf_n_mm']=_real(rows[4][40:60],card)
        law['calibration']['source']='원 native 카드 '+card['origin']['file']+':'+str(card['origin']['line'])+'; 실물 교정·온도 적용조건 UNKNOWN'
        expected=impact_bulk_deck.cards(impact_bulk_deck.inievo_card(mid,tid,law))[card['key']]
        _match(card,expected,[[10,10,10,40,10,20],[10]*4,[10,20,20,20],[10,20,20],[20]*3])
        generated=impact_bulk_deck.cards(impact_bulk_deck.initiation_cards(tid,fids,law))
        # Titles are metadata; every typed numeric field/blank remains verified.
        generated[table_key][0]=data[0]
        _match(tab,generated[table_key],[None,[10]]+([[20,20]]*len(data[2:]) if dimension==1 else [[10,10,20,40,20]]*len(data[2:])))
        field(card,4,'gf_n_mm',40,60,unit='N/mm',label=name+' / 파괴 에너지 Gf')
        field(card,2,'sr_ref_s_inv',10,30,unit='1/s',label=name+' / 기준 EPSD')
        result['tables'].add(tid); result['bulk_damage'].append(law)
        result.setdefault('bulk_cards',{})[name]={'mid':mid,'table_id':tid,'function_ids':fids}
    for card in starter:
        if card['key'].startswith('/TABLE/') and int(card['key'].rsplit('/',1)[1]) not in result['tables']:
            _error(card,'참조되지 않은 재료 시작표는 실행 검증 대상이 아닙니다')
    for card in starter:
        if card['key'].startswith('/FUNCT/') and int(card['key'].rsplit('/',1)[1]) in result['tables']:
            _error(card,'FUNCT와 TABLE은 같은 native 번호 공간을 공유합니다')
    return result


def physics_text(text, model, projection):
    """Existing pre-extension physical gate only. Export always uses original bytes."""
    replacements={}
    for mid,card in projection['materials'].items():
        name=model['materials'][card['rows'][0]['text'].strip().upper()]
        if '/LAW117/' in card['key']:
            en,et=name['ELASTIC'][0][:2]
            replacements[card['key']]=f'/MAT/LAW59/{mid}\n'+card['rows'][0]['text']+'\n'+impact_bulk_deck.real(name['DENSITY'][0][0])+'\n'+impact_bulk_deck.real(en)+impact_bulk_deck.real(et)+'\n0 0 0 0 0\n'
        elif '/LAW36/' in card['key']:
            replacements[card['key']]=card['key'].replace('/LAW36/','/PLAS_TAB/')+'\n'+'\n'.join(r['text'] for r in card['rows'])+'\n'
    for card in projection.get('delayed_contacts',[]):
        rows=[r['text'] for r in card['rows']]
        rows[4]=rows[4][:40]+impact_bulk_deck.real(0)+rows[4][60:]
        replacements[card['key']]=card['key']+'\n'+'\n'.join(rows)+'\n'
    return impact_bulk_deck.replace_blocks(text,replacements) if replacements else text


def project_controls(starter, model, settings, projection, field):
    from .impact_native import _real
    contacts=[card for card in starter if card['key'].startswith('/INTER/TYPE24/')]
    for law in settings.get('cohesive',[]):
        control=next(row for row in settings['interface_controls'] if row['material']==law['material'])
        elements=[eid for eid,name in model['assignment'].items() if name==law['material']]
        matching=set()
        for index,pair in enumerate(settings['contacts']):
            a,b=impact_interface._face_nodes(model,pair['a']),impact_interface._face_nodes(model,pair['b'])
            for eid in elements:
                geo=impact_damage.geometry(model,eid);lower=set(geo['lower_nodes']);upper=set(geo['upper_nodes'])
                if lower in a and upper in b or lower in b and upper in a:matching.add(index)
        if len(matching)==1:
            index=next(iter(matching));card=contacts[index]
            start=_real(card['rows'][4]['text'][40:60],card)
            control.update(reclosure='DELAYED_TYPE24_REQUIRE_DELETION',contact_index=index,contact_start_s=start)
            projection.setdefault('delayed_contacts',[]).append(card)
            field(card,4,'contact_start_s',40,60,unit='s',label=card['rows'][0]['text'].strip()+' / 접촉 시작 시각')
    impact_interface.validate(model,settings)


def receipts(starter, text, model, settings, projection):
    """Reuse B's writers/validators on a private check copy; bind actual native IDs."""
    impact_bulk.validate(model,settings.get('bulk_damage',[]))
    geometry=impact_damage.validate(model,settings.get('cohesive',[]))
    blocks=impact_bulk_deck.cards(text); assignment=impact_bulk_deck._bulk_assignment(blocks,model)
    cohesive={'elements':{},'geometry':geometry,'mass_definition':'volume density Mg/mm3','evolution':'irreversible envelope, no fatigue'}
    cohesive['native_cards']={card['key']:deepcopy(blocks[card['key']])
        for card in projection['materials'].values() if card['key'].startswith('/MAT/LAW117/')}
    for eid,element in model['elements'].items():
        if element['type']=='COH3D8': cohesive['elements'][str(eid)]={**assignment[eid],'material':model['assignment'][eid],'law':'LAW117'}
    removable={key:'' for key in blocks if key.startswith('/FAIL/INIEVO/') or key.startswith('/TH/BRIC/')
        or key.startswith('/TABLE/1/') and int(key.rsplit('/',1)[1]) in projection['tables']
        or key.startswith('/FUNCT/') and any(int(key.rsplit('/',1)[1]) in row['function_ids'] for row in projection.get('bulk_cards',{}).values())}
    check=impact_bulk_deck.replace_blocks(text,removable) if removable else text
    _,bulk=impact_bulk_deck.apply(check,model,settings.get('bulk_damage',[]))
    actual_generated={}
    for name,row in projection.get('bulk_cards',{}).items():
        mid=row['mid'];keys=['/FAIL/INIEVO/'+str(mid),'/TABLE/1/'+str(row['table_id'])]+['/FUNCT/'+str(v) for v in row['function_ids']]
        actual_generated.update({key:blocks[key] for key in keys})
        bulk['materials'][str(mid)].update(table_id=row['table_id'],function_ids=row['function_ids'])
    bulk['generated_cards']=actual_generated
    impact_bulk_deck.verify(text,model,settings.get('bulk_damage',[]),bulk)
    # Native contact cards already contain their source clock. Never invoke INP's rewrite.
    controls=[]; cards={}
    impact_interface.validate(model,settings)
    for row in settings.get('interface_controls',[]):
        entry={**deepcopy(row),'elements':[int(e) for e,v in cohesive['elements'].items() if v['material']==row['material']],
               'native_isym':0,'native_format':'2025 retained fallback','envelope':'irreversible maximum history; not cyclic fatigue'}
        if row['reclosure']=='DELAYED_TYPE24_REQUIRE_DELETION':
            contact=[c for c in starter if c['key'].startswith('/INTER/TYPE24/')][row['contact_index']]
            entry.update(native_contact_id=int(contact['key'].rsplit('/',1)[1]),required_postflight='cohesive deletion must be observed strictly before activation',gate='explicit native Tstart, not event-driven deletion')
            cards[contact['key']]=blocks[contact['key']]
        controls.append(entry)
    interface={'controls':controls,'cards':cards,'automatic_event_gate':'NOT_IMPLEMENTED','native_loop_acceptance':'NOT_RUN'}
    return bulk,cohesive,interface
