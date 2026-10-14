"""Native ParaView acceptance using *existing* retained beam results; no solve.

Run write and reopen with two separate installed pvpython processes. This script
uses real native readers, ColorBy and PVSM; tests/test_beam_post_support.py does
not participate. A GUI screenshot is optional, not a claim of Windows testing.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def blocks(value):
    if value is None:
        return []
    if value.IsA('vtkDataSet'):
        return [value]
    if value.IsA('vtkCompositeDataSet'):
        iterator = value.NewIterator(); iterator.InitTraversal(); result = []
        while not iterator.IsDoneWithTraversal():
            result.extend(blocks(iterator.GetCurrentDataObject())); iterator.GoToNextItem()
        return result
    raise ValueError('Expected a native beam dataset, not a table or another format')


def check_components(source):
    from paraview import simple as p, servermanager
    from apps.desktop_post import external
    from caelab.beam_inspection import validate_metadata
    from caelab.beam_results import CHANNELS, channels
    declaration = external._source_metadata(source)
    bundle = validate_metadata(external.reader_input_files(source)[0], declaration)
    expected_order = sorted(n['id'] for n in bundle['data']['model']['nodes'])
    checked = []
    for frame in bundle['data']['observed']['frames']:
        coefficient = frame['static']['load_parameter']
        expected = channels(frame)
        for name, entry in CHANNELS.items():
            selected = external.select_array(source, 'POINTS', name, time=coefficient)
            datasets = blocks(servermanager.Fetch(source))
            if len(datasets) != 1:
                raise ValueError('One original beam grid is required at each load parameter')
            grid = datasets[0]
            ids = grid.GetPointData().GetArray('NativeNodeId')
            values = grid.GetPointData().GetArray(name)
            assert ids and values and ids.GetNumberOfTuples() == len(expected_order)
            assert [int(ids.GetTuple1(i)) for i in range(len(expected_order))] == expected_order
            assert all(grid.GetCellType(i) == 21 for i in range(grid.GetNumberOfCells()))
            assert [values.GetTuple1(i) for i in range(len(expected_order))] == [expected[name]['values'][n] for n in expected_order]
            assert selected['units'] == entry[2] and selected['metadata_status'] == 'DECLARED'
            assert selected['location'] == 'ORIGINAL_BEAM_NODES'
            assert selected['time_units'] == '1' and selected['time_semantics'] == 'STATIC_LOAD_PARAMETER'
            assert selected['beam']['selected_static'] == frame['static']
            bar = p.GetScalarBar(p.GetColorTransferFunction(name), p.GetActiveView())
            assert bar.Title == entry[4] + ' [' + entry[2] + ']'
            checked.append({'component': name, 'load_parameter': coefficient, 'unit': entry[2],
                            'native_node_count': len(expected_order)})
    external.select_array(source, 'POINTS', 'U_mm', component='UZ', time=coefficient)
    # End on a scalar with mixed-unit S-slot meaning; verify it after new-process LoadState.
    external.select_array(source, 'POINTS', 'M1', time=coefficient)
    return checked


def write(bundle_path, output, screenshot=False):
    from paraview import simple as p
    from apps.desktop_post import external
    from caelab.beam_inspection import explicit_manifest
    from caelab.native_inputs import register_native_input
    view, metadata = explicit_manifest(bundle_path)
    output = Path(output).absolute(); output.mkdir(parents=True, exist_ok=False)
    registered_root = output / 'registered'
    receipt = register_native_input(registered_root, view.parent, view, 'D'+uuid.uuid4().hex,
        root_id='beam-native-acceptance', relative=view.name, limit=2*1024**3, native_metadata=metadata)
    copied = registered_root / receipt['file']
    pins = [{'path':str(registered_root/r['file']), 'bytes':r['bytes'], 'sha256':r['sha256']} for r in receipt['files']]
    project = external.open_result(copied, output/'project', receipt['id'], pins, receipt['native_metadata'])
    source = p.GetActiveSource(); checked = check_components(source)
    view = p.GetActiveView()
    # Render at an actual desktop view size; scaling a default 300px view to
    # 1440px would enlarge all legends and hide whether the labels fit.
    view.ViewSize = [1440,900]
    for representation in view.Representations:
        if representation.GetXMLName() == 'ScalarBarWidgetRepresentation':
            expected = representation.LookupTable == p.GetColorTransferFunction('M1')
            assert bool(representation.Visibility) == expected
    saved = external.save_project(project, json.loads(project.read_text(encoding='utf-8')))
    if screenshot:
        p.SaveScreenshot(str(output/'beam-native-post.png'), p.GetActiveView(), ImageResolution=[1440,900])
    report = {'native_paraview':str(p.GetParaViewVersion()), 'project':str(saved), 'checked':checked,
              'state':'SAVED_REOPEN_PENDING', 'solver_executed':False, 'windows_gui_verified':False}
    (output/'beam_post_write.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(saved)
    return report


def reopen(project, output):
    from paraview import simple as p
    from apps.desktop_post import external
    project = Path(project).absolute(); doc = json.loads(project.read_text(encoding='utf-8'))
    os.environ['CAE_POST_PROJECT'] = str(project)
    external.restore_workspace(project, doc)
    source = p.GetActiveSource(); view = p.GetActiveView()
    if source is None or view is None:
        raise ValueError('Saved active source/view was not restored')
    display = p.GetDisplayProperties(source, view=view)
    selection = list(display.ColorArrayName)
    assert selection == ['POINTS','M1'], selection
    bar = p.GetScalarBar(p.GetColorTransferFunction('M1'), view)
    assert bar.Title == '1축 굽힘 모멘트 [Nmm]'
    declaration = external._source_metadata(source)
    assert float(p.GetAnimationScene().AnimationTime) == declaration['time']['values'][-1]
    assert 'rotation_rad' in declaration['beam']['unavailable']
    assert 'support_reaction_moment_Nmm' in declaration['beam']['unavailable']
    checked = check_components(source)
    report = {'native_paraview':str(p.GetParaViewVersion()), 'project':str(project), 'checked':checked,
              'state':'NEW_PROCESS_REOPENED', 'solver_executed':False, 'windows_gui_verified':False}
    output = Path(output).absolute()
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='보존 빔 결과의 실제 ParaView 등록·성분·저장·재열기 검사')
    sub = parser.add_subparsers(dest='operation', required=True)
    first = sub.add_parser('write'); first.add_argument('bundle', type=Path); first.add_argument('output', type=Path)
    first.add_argument('--screenshot', action='store_true')
    second = sub.add_parser('reopen'); second.add_argument('project', type=Path); second.add_argument('output', type=Path)
    args = parser.parse_args(argv)
    if args.operation == 'write': return write(args.bundle,args.output,args.screenshot)
    return reopen(args.project,args.output)


if __name__ == '__main__':
    main()
