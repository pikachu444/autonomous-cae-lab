"""Exact declared response choices shared by research pickers, not an evaluator."""
from copy import deepcopy


def response_choices(metadata, *, limit=512):
    """Bounded scalar/curve names plus explicitly advertised native locations."""
    choices, seen = [], set()
    def add(selector, descriptor, label):
        if not isinstance(selector, str) or not selector or selector in seen or len(choices) >= limit:
            return
        seen.add(selector)
        choices.append({'selector': selector, 'label': label + ' [' + str(descriptor.get('unit', '?')) + ']',
                        'definition': deepcopy(descriptor)})
    for descriptor in metadata.get('responses', []):
        if isinstance(descriptor, dict) and descriptor.get('kind') in ('scalar', 'series'):
            add(descriptor.get('response'), descriptor, str(descriptor.get('response')))
    for name, descriptor in metadata.get('native_channels', {}).items():
        if not isinstance(descriptor, dict):
            continue
        if descriptor.get('selectors'):
            for row in descriptor['selectors']:
                add(row.get('selector'), descriptor, str(name) + ' · ' + str(row.get('label')))
        elif descriptor.get('node_ids'):
            template = descriptor.get('selector_template')
            if isinstance(template, str) and template.count('<node_id>') == 1:
                for node in descriptor['node_ids']:
                    add(template.replace('<node_id>', str(node)), descriptor, str(name) + ' · native node ' + str(node))
        else:
            add(descriptor.get('source', {}).get('selector'), descriptor, str(name))
    return choices
