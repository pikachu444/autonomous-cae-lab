"""Page derived response values without corrupting frozen sample provenance.

The grid/channel DAG remains the complete immutable evidence. Only per-response
view arrays and segments are paged. Selecting samples does not adopt a Plan mask.
"""
from copy import deepcopy
import numpy as np


def select_sample_indexes(response, selection, selected, expand):
    for key in ('sample_ids', 'coordinate_sample_ids'):
        if key not in selection:
            continue
        requested = selection[key]
        if (not isinstance(requested, list) or not 1 <= len(requested) <= 4096
                or any(not isinstance(s, str) or not s for s in requested)
                or len(set(requested)) != len(requested)):
            raise ValueError('Select at most 4096 distinct explicit sample identities')
        available = response.get(key)
        if available is None:
            raise ValueError('This response has no ' + key)
        available = list(expand(available))
        if len(set(available)) != len(available) or set(requested) - set(available):
            raise ValueError('Requested sample identities are absent or ambiguous; no raw-row substitution')
        selected = selected[np.isin(np.asarray(available)[selected], requested)]
    return selected


def page_sample_metadata(response, selected, expand):
    if 'sample_ids' not in response:
        return False
    ids = list(expand(response['sample_ids']))
    selected = [int(i) for i in selected]
    if len(set(ids)) != len(ids) or any(not 0 <= i < len(ids) for i in selected):
        raise ValueError('Cannot page an inconsistent frozen sample response')
    for key in ('sample_ids', 'coordinate_sample_ids', 'source_row_dependencies'):
        if key not in response:
            continue
        values = expand(response[key])
        if len(values) != len(ids):
            raise ValueError('Per-sample metadata length differs: ' + key)
        response[key] = [deepcopy(values[i].tolist() if isinstance(values[i], np.ndarray) else values[i]) for i in selected]
    shown = {original: page for page, original in enumerate(selected)}
    segments = []
    for segment in response.get('segments', []):
        low, high = (int(x) for x in expand(segment['rows']))
        indexes = [i for i in selected if low <= i < high]
        # Disjoint selections cannot become a continuous plotted curve.
        starts = [0, *[j for j in range(1, len(indexes)) if indexes[j] != indexes[j-1] + 1], len(indexes)]
        for a, b in zip(starts[:-1], starts[1:]):
            chunk = indexes[a:b]
            if not chunk:
                continue
            row = {k: deepcopy(v) for k, v in segment.items() if k not in ('rows', 'sample_ids', 'source_rows')}
            row.update(rows=[shown[chunk[0]], shown[chunk[-1]] + 1], sample_ids=[ids[i] for i in chunk])
            if 'source_rows' in segment:
                raw = expand(segment['source_rows'])
                if len(raw) != high - low:
                    raise ValueError('Segment raw-row length differs from its samples')
                row['source_rows'] = [int(raw[i-low]) for i in chunk]
            segments.append(row)
    if 'segments' in response:
        response['segments'] = segments
    response['sample_view'] = {'original_response_count': len(ids), 'selected_indexes': selected,
        'frozen_grid_and_lineage_unchanged': True, 'plan_mask_modified': False}
    return True
