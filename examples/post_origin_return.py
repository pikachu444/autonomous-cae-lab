"""Explicit fixture creation + exact retained Data return + cold re-open.

    python -m examples.post_origin_return <new-empty-output-directory>

The existing examples.post_curves.create performs ONE explicit CSV import and
snapshot during setup. Return/cold-return only read that saved result; no import,
fit, snapshot export, native process, provider or solver runs during navigation.
A is a manufactured demonstration curve, NOT a saved native measurement/fullpin.
"""
from copy import deepcopy
import json
from pathlib import Path
import argparse
from caelab.workbench import Workbench
from caelab.post_curves import load_curve, from_response, compare
from caelab.post_curve_origin import targets, read_data
from examples.post_curves import create


def run(directory):
    root = Path(directory).resolve()
    inputs = create(root)
    wb = Workbench(root/'store')
    try:
        before = len(wb.manager.list())
        native = wb.native_input(inputs['curve_input']['id'])
        b, _ = load_curve(native['path'], native['native_metadata'])
        a = from_response({'kind':'series', 'value':[0.,2.,4.], 'unit':'N', 'quantity':'force',
            'component':'x','location':'manufactured demonstration','measure':'force','frame':'global',
            'axes':[{'name':'time','unit':'s','values':[0.,.5,1.]}]},
            origin={'demonstration':'not a native saved measurement'}, title='제작 예제 A — native 저장본 아님')
        # Existing Data fixture has UNKNOWN quantity. This is the EXPLICIT example
        # comparison declaration, not a rewrite of the saved response or its hash.
        recipe = {'version':3,'a':{},'b':{'declaration':{'quantity':'force'}},'axis_kind':'physical_time',
            'axis_origins':{'a':'trigger','b':'DAQ start'},'b_axis_offset':-.1,
            'alignment':'bracket','axis_tolerance':0.,'max_gap':1.,'target_unit':'N',
            'locations_confirmed':True}
        compared = compare(a,b,recipe)  # Existing math; no new interpolation here.
        if compared['blocked'] is not None:
            raise ValueError(compared['blocked'])
        originals = {tag:[{'row_index':i,**row,
            'common_x':compared['b_axis'][i] if tag=='b' else row['x'],
            'common_y':compared[tag+'_values'][i]}
            for i,row in enumerate(compared[tag]['rows'])] for tag in ('a','b')}
        payload = {'semantics':'retained_curve_comparison','rows':compared['rows'],'originals':originals,
            'summary':{'recipe':recipe,'sources':{tag:{key:compared[tag][key] for key in
                ('title','origin','declaration','axis','selected_rows')} for tag in ('a','b')}}}
        selected = [t for t in targets(payload,'aligned',1) if t['side']=='b']
        records = [read_data(wb,t) for t in selected]
        assert len(wb.manager.list()) == before
        rows = [r['row'] for r in records]
        assert [r['raw_x'] for r in rows] == [100.,1100.]
        assert [r['raw_y'] for r in rows] == [0.,.004]
    finally:
        if not wb.shutdown()['joined']:
            raise RuntimeError('Example-owned Workbench did not join')
    reopened = Workbench(root/'store')
    try:
        cold = [read_data(reopened,t)['row'] for t in selected]
        assert cold == rows and len(reopened.manager.list()) == before
    finally:
        if not reopened.shutdown()['joined']:
            raise RuntimeError('Cold-example Workbench did not join')
    result = {'status':'DATA_RETURN_AND_COLD_READ_VERIFIED','fixture_setup':'one explicit existing Data import/snapshot',
        'native_gui':'NOT_RUN','a':'manufactured example only; no full origin',
        'b_reference':inputs['reference'],'aligned':compared['rows'][1],
        'original_b_rows':rows,'cold_rows_equal':True,'navigation_jobs_added':0,
        'native_or_solver_or_provider_processes_started':0}
    (root/'origin-return-observed.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.directory),ensure_ascii=False,allow_nan=False,indent=2))
