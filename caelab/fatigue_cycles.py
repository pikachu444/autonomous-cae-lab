"""Original-sample loop association alongside, NOT instead of, pinned rainflow.

The pinned counter remains authoritative. The replay carries sampled branches
through exactly the same stack contractions, and asserts each emitted tuple.
A closure between samples is recorded as a bracket, never interpolated. Shared
boundary samples are kept; already contracted loop interiors are not re-used.
"""
from __future__ import annotations

from .execution_control import check_cancelled

ASSOCIATION_VERSION = 'sampled-contracted-branches-v1'
MAX_MEMBERSHIPS = 4_000_000


def associate_cycles(strain):
    from .fatigue import _counter
    from ._vendor.rainflow import reversals
    authoritative = iter(_counter()(strain))
    points, edges, records = [], [], []
    memberships = 0

    def emit(a, b, count, members, *, closure=None, bracket=None, trigger=None, kind):
        nonlocal memberships
        check_cancelled()
        actual = (abs(strain[a] - strain[b]), (strain[a] + strain[b]) / 2, count, a, b)
        if next(authoritative, None) != actual:
            raise ValueError('Pinned rainflow / loop association mismatch; no SWT assessment admitted')
        unique = sorted(set(members))
        memberships += len(unique)
        if memberships > MAX_MEMBERSHIPS:
            raise ValueError('cycle 원행 membership 한도를 넘었습니다. 이력을 명시적으로 나누어 검토하세요')
        records.append({'range': actual[0], 'mean': actual[1], 'count': count,
                        'start_row': a, 'end_row': b, 'member_indices': unique,
                        'closure_index': closure, 'closure_bracket_indices': bracket,
                        'closing_reversal_index': trigger, 'association': kind,
                        'association_version': ASSOCIATION_VERSION})

    for index, _ in reversals(strain):
        check_cancelled()
        if points:
            edges.append(list(range(points[-1], index + 1)))
        points.append(index)
        while len(points) >= 3:
            a, b, c = points[-3:]
            if abs(strain[c] - strain[b]) < abs(strain[a] - strain[b]):
                break
            if len(points) == 3:
                emit(a, b, .5, edges[0], kind='OBSERVED_INITIAL_HALF_BRANCH')
                points.pop(0)
                edges.pop(0)
            else:
                outgoing, returning = edges[-2:]
                direction = 1 if strain[a] >= strain[b] else -1
                crossing = next((j for j in range(1, len(returning))
                                 if direction * (strain[returning[j]] - strain[a]) >= 0), None)
                if crossing is None:
                    raise ValueError('SWT return branch has no bracketed closure')
                hit = returning[crossing]
                exact = strain[hit] == strain[a]
                included = returning[:crossing + 1] if exact else returning[:crossing]
                emit(a, b, 1.0, outgoing + included,
                     closure=hit if exact else None,
                     bracket=[hit, hit] if exact else [returning[crossing-1], hit],
                     trigger=c, kind='CLOSED_SAMPLED_LOOP' if exact else 'BRACKETED_SAMPLED_LOOP')
                # Share A/closure boundaries with the enclosing branch, while
                # excising the interior of this counted loop. Never start:end.
                remainder = returning[crossing:]
                joined = list(dict.fromkeys(edges[-3] + remainder))
                points[-3:] = [c]
                edges[-3:] = [joined]
    while len(points) > 1:
        emit(points[0], points[1], .5, edges[0], kind='OBSERVED_RESIDUAL_HALF_BRANCH')
        points.pop(0)
        edges.pop(0)
    if next(authoritative, None) is not None:
        raise ValueError('Pinned rainflow has unassociated cycles; no SWT assessment admitted')
    return records
