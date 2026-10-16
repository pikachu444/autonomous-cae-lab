"""Read the pinned native RBODY initialization before starting Engine."""
from pathlib import Path
import math
import re

NUMBER=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?'


def expected_bodies(m,mapping,fe_model=None):
    """Input-derived *nodal lumped* native body initialization, not volume J."""
    coords=dict(mapping['nodes']);half_mass=m['connector_mass_Mg']/2;half_j=m['connector_inertia_Mg_mm2']/2
    result=[];lumped={}
    if m['fe'] is not None:
        from .connector_model import sub,cross,dot
        for eid,element in fe_model['elements'].items():
            p=[fe_model['nodes'][n] for n in element['nodes']]
            det=dot(sub(p[1],p[0]),cross(sub(p[2],p[0]),sub(p[3],p[0])))
            if det<=0:raise ValueError('원 C3D4의 유향 체적이 양수가 아닙니다.')
            density=fe_model['materials'][fe_model['assignment'][eid]]['DENSITY'][0][0]
            mass=density*det/24
            for n in element['nodes']:lumped[n]=lumped.get(n,0.)+mass
    for i,link in enumerate(mapping['attachments']):
        if m['fe'] is None:
            e=m['endpoints'][i];center=e['reference_mm'];mass=e['mass_Mg']+half_mass
            tensor=[v+(half_j if j<3 else 0.) for j,v in enumerate(e['inertia_Mg_mm2'])]
            body=link['rigid_body'];main=link['main_node'];members=link['secondary_nodes']
        else:
            body=link['body'];main=link['native_cog_main'];members=link['secondary_nodes'];rp=link['connector_reference']
            points=[(lumped[n],coords[n]) for n in link['source']['native_node_ids']]
            points.extend([(half_mass,coords[rp]),(1e-20,coords[main])])
            mass=math.fsum(v for v,p in points)
            center=[math.fsum(v*p[j] for v,p in points)/mass for j in range(3)]
            tensor=[half_j]*3+[0.]*3
            for weight,p in points:
                x,y,z=[a-b for a,b in zip(p,center)]
                for j,v in enumerate((y*y+z*z,x*x+z*z,x*x+y*y,-x*y,-y*z,-z*x)):
                    tensor[j]+=weight*v
        result.append({'body':body,'main_node':main,'position_mm':center,'mass_Mg':mass,
                       'inertia_Mg_mm2':tensor,'secondary_nodes':list(members),
                       'source':'native FE nodal lumped mass + explicit spring endpoint mass/inertia once' if m['fe'] else
                                'declared body + explicit spring endpoint mass/inertia once'})
    return result


def _printed_close(a,b,scale):
    # Pinned NEW X/J/MASS uses G14.7: half a last printed decimal plus an
    # arithmetic rounding budget, not an engineering relative tolerance.
    quantum=10.**(math.floor(math.log10(abs(b)))-6) if b else 0.
    return abs(a-b)<=quantum/2+64*2**-52*max(abs(a),abs(b),scale)


def _values(text,label,count):
    match=re.search(r'^\s*'+re.escape(label)+r'\s+('+r'\s+'.join([NUMBER]*count)+r')\s*$',text,re.M)
    if not match:raise ValueError('Starter의 실제 강체 초기화 '+label+' 기록이 없습니다.')
    values=[float(v.replace('D','E').replace('d','e')) for v in match[1].split()]
    if any(not math.isfinite(v) for v in values):raise ValueError('Starter의 실제 강체 질량·관성·좌표가 유한하지 않습니다.')
    return values


def read_bodies(path,mapping,*,fe):
    text=Path(path).read_text(encoding='ascii')
    blocks=re.split(r'RIGID BODY INITIALIZATION',text)[1:];found={}
    for block in blocks:
        ident=re.search(r'RIGID BODY ID\s+(\d+)',block);main=re.search(r'PRIMARY NODE\s+(\d+)',block)
        if not ident or not main:raise ValueError('실제 강체 초기화의 ID·main node가 없습니다.')
        key=int(ident[1])
        if key in found:raise ValueError('실제 강체 초기화 ID가 중복됐습니다.')
        found[key]={'body':key,'main_node':int(main[1]),'position_mm':_values(block,'NEW X,Y,Z',3),
                    'mass_Mg':_values(block,'NEW MASS',1)[0],
                    'inertia_Mg_mm2':_values(block,'NEW INERTIA xx yy zz',3)+_values(block,'NEW INERTIA xy yz zx',3),
                    'principal_inertia_Mg_mm2':_values(block,'PRINCIPAL INERTIA',3)}
        tail=block.split('SECONDARY NODES',1)
        if len(tail)!=2:raise ValueError('실제 강체의 secondary 절점 목록이 없습니다.')
        members=[]
        for line in tail[1].splitlines():
            tokens=line.split()
            if not tokens:
                if members:break
                continue
            if not all(re.fullmatch(r'[0-9]+',v) for v in tokens):break
            members.extend(map(int,tokens))
        if len(members)!=len(set(members)):raise ValueError('실제 강체의 secondary 절점이 중복됐습니다.')
        found[key]['secondary_nodes']=members
    expected={r['body'] if fe else r['rigid_body']:r for r in mapping['attachments']}
    if set(found)!=set(expected):raise ValueError('Starter의 실제 강체 목록과 원 부착 영역이 다릅니다.')
    for key,row in found.items():
        link=expected[key];main=link['native_cog_main'] if fe else link['main_node']
        if row['main_node']!=main or row['mass_Mg']<=0 or min(row['principal_inertia_Mg_mm2'])<=0:
            raise ValueError('native가 회전 전달에 필요한 실제 양의 질량·관성을 만들지 못했습니다.')
        # CoG relocation is permitted ONLY for the new internal main in the FE
        # path; the connector RP stays a secondary at the original source point.
        expected_rows={v['body']:v for v in mapping.get('expected_native_bodies',[])}
        if key not in expected_rows:raise ValueError('원 입력에서 계산한 정확한 강체 질량·관성 근거가 없습니다.')
        expected_row=expected_rows[key]
        if set(row['secondary_nodes'])!=set(expected_row['secondary_nodes']):
            raise ValueError('native가 실제 부착 영역의 secondary 절점 목록을 바꿨습니다.')
        position_scale=max([abs(v) for v in expected_row['position_mm']]+[1.])
        if any(not _printed_close(a,b,position_scale) for a,b in zip(expected_row['position_mm'],row['position_mm'])):
            raise ValueError('native 강체의 실제 기준점·질량중심 위치가 원 질량 근거와 다릅니다.')
        if not _printed_close(expected_row['mass_Mg'],row['mass_Mg'],expected_row['mass_Mg']):
            raise ValueError('native 강체 질량이 원 질량 근거와 다릅니다.')
        inertia_scale=max(abs(v) for v in expected_row['inertia_Mg_mm2'])
        if any(not _printed_close(a,b,inertia_scale) for a,b in zip(expected_row['inertia_Mg_mm2'],row['inertia_Mg_mm2'])):
            raise ValueError('native 강체 관성이 원 절점·질량·추가 관성 근거와 다릅니다.')
    return {'status':'PASS','source':'native Starter RIGID BODY INITIALIZATION',
            'bodies':[found[k] for k in sorted(found)],'precision':'native G14.7/G20.13 printed values',
            'qualification':'UNKNOWN','mass_policy':'native resolved values retained; no silent input repair'}
