# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 1998-2015 Guido Dhondt
# Python translation and independent file CLI changes: Autonomous CAE Lab, 2026.
# Source: CalculiX 2.22, cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54,
# src/attach_2d.f and src/distattach_2d.f. See NOTICE.md and COPYING.
# This program is free software under GPL version 2, without any warranty.
"""Standalone six-node face projection; no CAE application or Qt imports."""
import argparse
import json
import math
from pathlib import Path


def project(face, point):
    def evaluate(xg, yg):
        if xg + yg <= 0.:
            x, y = (xg + 1.) / 2., (yg + 1.) / 2.
        else:
            x, y = (1. - yg) / 2., (1. - xg) / 2.
        a = 1. - x - y
        a2, x2, y2 = 2.*a, 2.*x, 2.*y
        weights = [a*(a2-1.), x*(x2-1.), y*(y2-1.), x2*a2, x2*y2, y2*a2]
        p = [0., 0., 0.]
        for i in range(3):
            for j in range(6):
                p[i] = p[i] + weights[j]*face[j][i]
        distance = (point[0]-p[0])**2 + (point[1]-p[1])**2 + (point[2]-p[2])**2
        return distance, p, weights

    center = (0., 0.)
    minimum = evaluate(*center)[0]
    im, jm = 0, 0
    delta = 1.
    grid = {}
    for level in range(8):
        delta = delta / 10.
        for i in range(-1, 2):
            for j in range(-1, 2):
                if i == 0 and j == 0:
                    continue
                location = (center[0]+i*delta, center[1]+j*delta)
                grid[i,j] = location
                if all(-1. <= v <= 1. for v in location):
                    distance = evaluate(*location)[0]
                    if distance < minimum:
                        minimum, im, jm = distance, i, j
        while im != 0 or jm != 0:
            center = grid[im,jm]
            old_i, old_j = im, jm
            im, jm = 0, 0
            for i in range(-1, 2):
                for j in range(-1, 2):
                    if not (-1 <= i+old_i <= 1 and -1 <= j+old_j <= 1):
                        location = (center[0]+i*delta, center[1]+j*delta)
                        grid[i,j] = location
                        if all(-1. <= v <= 1. for v in location):
                            distance = evaluate(*location)[0]
                            if distance < minimum:
                                minimum, im, jm = distance, i, j
    _, position, weights = evaluate(*center)
    return {'point':position, 'weights':weights}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    try:
        raw = args.input.read_bytes()
        if len(raw)>32*1024**2:
            raise ValueError('Input exceeds 32 MiB')
        data = json.loads(raw)
        if set(data) != {'cases'} or not isinstance(data['cases'],list) or len(data['cases'])>100000:
            raise ValueError('Input requires a bounded cases list')
        results = []
        for row in data['cases']:
            if set(row) != {'face','point'} or len(row['face'])!=6 or len(row['point'])!=3:
                raise ValueError('Each case requires six 3D face nodes and one 3D point')
            if any(len(p)!=3 for p in row['face']):
                raise ValueError('Face nodes need three coordinates')
            values = [v for p in row['face'] for v in p]+row['point']
            if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
                raise ValueError('Coordinates must be finite numbers')
            results.append(project(row['face'],row['point']))
        with args.output.open('x',encoding='utf-8') as stream:
            json.dump({'projections':results},stream,allow_nan=False)
        return 0
    except (ValueError,TypeError,KeyError,OverflowError,OSError) as error:
        parser.exit(2,str(error)+'\n')


if __name__ == '__main__':
    raise SystemExit(main())
