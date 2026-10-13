"""Bounded native LAW117 cohesive extension; original converter deck is retained.

Positive-thickness paired COH3D8, volume density and displacement-based envelope
damage. No cyclic fatigue, automatic reclosure, or energy-dissipation inference.
"""
import math
import re
from copy import deepcopy

KEYS={'material','law','normal_strength_mpa','shear_strength_mpa','mode_I_n_mm','mode_II_n_mm',
      'criterion','power_exponent','bk_exponent','gamma','deletion_points'}


def default_law(material):
    return {'material':material,'law':'LAW117','normal_strength_mpa':'','shear_strength_mpa':'',
        'mode_I_n_mm':'','mode_II_n_mm':'','criterion':'POWER','power_exponent':1.,
        'bk_exponent':1.,'gamma':1.,'deletion_points':1}


def sub(a,b):return [x-y for x,y in zip(a,b)]
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
def length(v):return math.sqrt(dot(v,v))


def geometry(model,eid):
    element=model['elements'][eid];points=[model['nodes'][n] for n in element['nodes']]
    normal=cross(sub(points[1],points[0]),sub(points[3],points[0]));area=length(normal)
    if area<=0:raise ValueError('응집 요소의 아래 면이 퇴화했습니다')
    normal=[v/area for v in normal]
    delta=sub(points[4],points[0]);height=dot(delta,normal);scale=max(length(sub(p,points[0])) for p in points)
    tol=max(scale*1e-9,1e-12)
    if height<=tol:raise ValueError('응집 요소는 양의 실제 두께와 올바른 아래/위 절점 순서가 필요합니다')
    if length(sub(delta,[height*n for n in normal]))>tol:raise ValueError('응집 요소 두 면의 정상 대응을 확인하세요')
    for i in range(4):
        if abs(dot(sub(points[i],points[0]),normal))>tol or length(sub(sub(points[i+4],points[i]),delta))>tol:
            raise ValueError('이 경로는 평행한 두 평면과 일대일 대응하는 COH3D8을 지원합니다')
    # Strict convex consistently oriented corner polygon.
    for i in range(4):
        if dot(cross(sub(points[(i+1)%4],points[i]),sub(points[(i+2)%4],points[(i+1)%4])),normal)<=0:
            raise ValueError('응집 면의 접힘/뒤집힘을 수리하세요')
    return {'lower_nodes':element['nodes'][:4],'upper_nodes':element['nodes'][4:],
        'normal':normal,'thickness_mm':height,'frame':'initial_interface_basis'}


def validate(model,laws):
    from .impact_model import number
    if not isinstance(laws,list):raise ValueError('응집 손상 법칙 목록을 확인하세요')
    cohesive={model['assignment'][eid] for eid,row in model['elements'].items() if row['type']=='COH3D8'}
    if {row.get('material') for row in laws if isinstance(row,dict)}!=cohesive or len(laws)!=len(cohesive):
        raise ValueError('각 응집 재료에 명시 LAW117 법칙 하나가 필요합니다')
    for row in laws:
        if set(row)!=KEYS or row['law']!='LAW117':raise ValueError('지원 응집 법칙은 명시 LAW117입니다')
        for key in ('normal_strength_mpa','shear_strength_mpa','mode_I_n_mm','mode_II_n_mm','power_exponent','bk_exponent','gamma'):
            number(row[key],key,True)
        if row['criterion'] not in ('POWER','BK') or type(row['deletion_points']) is not int or not 1<=row['deletion_points']<=4:
            raise ValueError('혼합 모드와 1~4개의 소실 적분점을 명시하세요')
        material=model['materials'][row['material']]
        en,et,_,_=material['ELASTIC'][0]
        if row['mode_I_n_mm']<=row['normal_strength_mpa']**2/(2*en) or row['mode_II_n_mm']<=row['shear_strength_mpa']**2/(2*et):
            raise ValueError('파괴 에너지가 초기 탄성 에너지보다 커야 합니다. Starter의 자동 계수 수리는 사용하지 않습니다')
    return {str(e):geometry(model,e) for e,row in model['elements'].items() if row['type']=='COH3D8'}


def law_card(ident,name,material,law):
    def real(v):return f'{v:20.12e}'
    en,et,_,_=material['ELASTIC'][0]
    return '\n'.join([f'/MAT/LAW117/{ident}',name,real(material['DENSITY'][0][0]),
        real(en)+real(et)+f"{2:10d}{law['deletion_points']:10d}{1 if law['criterion']=='POWER' else 2:10d}",
        f'{0:10d}{0:10d}'+real(law['normal_strength_mpa'])+real(law['shear_strength_mpa'])+real(1),
        ''.join(real(law[key]) for key in ('mode_I_n_mm','mode_II_n_mm','power_exponent','bk_exponent','gamma'))])+'\n'


def apply_laws(text,model,laws):
    from .adapters.impact_admission import cards,_int,_real,_same
    geometry_receipt=validate(model,laws);b=cards(text);replacements={};law_by_element={}
    materials={row['material']:row for row in laws}
    for key,rows in b.items():
        if not key.startswith('/BRICK/'):continue
        part=int(key.rsplit('/',1)[1]);part_rows=b.get('/PART/'+str(part),[])
        if len(part_rows)!=2:raise ValueError('응집 part의 재료 배정이 없습니다')
        prop,mid=_int(part_rows[1][:10]),_int(part_rows[1][10:20])
        values=[int(row[i:i+10]) for row in rows for i in range(0,len(row),10) if row[i:i+10].strip()]
        eids=values[::9]
        if not any(model['elements'][eid]['type']=='COH3D8' for eid in eids):continue
        if any(model['elements'][eid]['type']!='COH3D8' for eid in eids):raise ValueError('응집/벌크 요소의 part가 합쳐졌습니다')
        names={model['assignment'][eid] for eid in eids}
        if len(names)!=1:raise ValueError('응집 part에 서로 다른 재료가 배정됐습니다')
        name=next(iter(names));material=model['materials'][name];law=materials[name]
        property_rows=b.get('/PROP/TYPE43/'+str(prop),[])
        if len(property_rows)!=2 or _int(property_rows[1][:10])!=-1 or property_rows[1][10:].strip():
            raise ValueError('응집 TYPE43 유한변형 설정이 변경됐습니다')
        original='/MAT/LAW59/'+str(mid);native=b.get(original,[])
        if len(native)!=4 or native[0].strip().upper()!=name:raise ValueError('정확한 원 응집 재료를 찾을 수 없습니다')
        _same(_real(native[1][:20]),material['DENSITY'][0][0])
        for index,expected in enumerate(material['ELASTIC'][0][:2]):_same(_real(native[2][20*index:20*(index+1)]),expected)
        if native[2][40:].strip() or any(_real(v) for v in native[3].split()):raise ValueError('원 응집 법칙에 추가 옵션이 있습니다')
        replacements[original]=law_card(mid,name,material,law)
        for eid in eids:law_by_element[str(eid)]={'law':'LAW117','material':name,'material_id':mid,'part_id':part,'property_id':prop}
    if set(law_by_element)!=set(geometry_receipt):raise ValueError('응집 요소의 native 법칙 적용 범위가 다릅니다')
    # Replace only exact admitted material blocks. Keep mandatory header and
    # untouched native byte ranges, including the raw source unit card.
    matches=list(re.finditer(r'(?m)^/[^\r\n]+',text))
    for i in reversed(range(len(matches))):
        match=matches[i];key=match.group(0).strip()
        if key in replacements:
            end=matches[i+1].start() if i+1<len(matches) else len(text)
            text=text[:match.start()]+replacements[key]+text[end:]
    return text,{'elements':law_by_element,'geometry':geometry_receipt,
        'reclosure':'Separate opposing-bulk TYPE24 contact required after deletion',
        'mass_definition':'volume density Mg/mm3','evolution':'irreversible envelope, no fatigue'}


def verify_laws(text,model,laws,receipt):
    from .adapters.impact_admission import cards
    b=cards(text);seen=set()
    for item in receipt['elements'].values():
        mid=item['material_id']
        if mid in seen:continue
        seen.add(mid);name=item['material']
        law=next(row for row in laws if row['material']==name)
        expected=cards(law_card(mid,name,model['materials'][name],law))
        key='/MAT/LAW117/'+str(mid)
        if b.get(key)!=expected[key]:raise ValueError('유효 응집 재료 카드가 입력과 다릅니다')
    if any(k.startswith('/FAIL/') for k in b):raise ValueError('이 LAW117 경로는 추가 FAIL 카드를 적용하지 않습니다')
