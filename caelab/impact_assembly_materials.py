"""Assembly material/section emission; physical rules stay in impact_model.parse_inp."""
from copy import deepcopy
from .impact_model import NAME

MATERIAL_CARDS = {'MATERIAL', 'DENSITY', 'ELASTIC', 'PLASTIC'}
SECTION_CARDS = {'SOLID SECTION', 'COHESIVE SECTION'}


def material_name(value, block, fail):
    # Preserve the existing flat namespace; never sanitize distinct source names.
    if not isinstance(value, str) or not NAME.fullmatch(value):
        fail(block, '재료 이름은 기존 flat 경로와 같은 영문·영숫자·_ 64자 이하로 지정하세요')
    return value


def emit_section(block, *, instance, part, element_keys, local_sets, element_origins,
                 lineage, emit, fail, label):
    options = block['options']
    source_set = label(options.get('ELSET'), block)
    material = material_name(options.get('MATERIAL'), block, fail)
    if source_set not in element_keys:
        fail(block, 'section의 local ELSET이 없습니다', instances=[instance])
    effective_set = element_keys[source_set]
    emit('*'+block['card']+',ELSET='+effective_set+',MATERIAL='+material, block['origin'])
    for row in block['rows']:
        emit(row['text'], row['origin'])
    lineage['sections'].append({
        'card': block['card'], 'origin': deepcopy(block['origin']),
        'part': part, 'instance': instance, 'material': material,
        'source_elset': source_set, 'effective_elset': effective_set,
        'assignments': [{'element_id': effective, 'local_id': local,
                         'element_origin': deepcopy(element_origins[local])}
                        for local, effective in sorted(local_sets.items())]
    })


def emit_globals(blocks, *, lineage, emit, fail):
    current = None
    for block in blocks:
        card, options = block['card'], block['options']
        if card == 'BOUNDARY':
            continue
        if card == 'MATERIAL':
            current = material_name(options.get('NAME'), block, fail)
            if current in lineage['materials']:
                fail(block, '중복 재료 정의입니다')
            lineage['materials'][current] = {'origin': deepcopy(block['origin']), 'cards': [], 'assignments': []}
        if card in MATERIAL_CARDS and current is not None:
            lineage['materials'][current]['cards'].append({
                'card': card, 'options': deepcopy(options), 'origin': deepcopy(block['origin']),
                'rows': deepcopy(block['rows'])})
        emit('*'+card+''.join(','+key+'='+str(value) for key,value in options.items()), block['origin'])
        for row in block['rows']:
            emit(row['text'], row['origin'])


def bind_assignments(model, lineage):
    """Only after the shared flat parser has accepted every physical assignment."""
    for section in lineage['sections']:
        material = section['material']
        lineage['materials'][material]['assignments'].append(deepcopy(section))
        for row in section['assignments']:
            element = lineage['elements'][str(row['element_id'])]
            element.update(material=model['assignment'][row['element_id']],
                           material_origin=deepcopy(lineage['materials'][material]['origin']),
                           section_origin=deepcopy(section['origin']), section_card=section['card'])
