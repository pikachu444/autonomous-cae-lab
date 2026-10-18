"""Actual ParaView saved-result rendering/cold reopen, never a solver caller."""
from pathlib import Path
import json,os,traceback


def run(config_path, *, cold=False):
    import ctypes
    from ctypes import wintypes
    from paraview import simple as p,servermanager
    from paraview.numpy_support import vtk_to_numpy
    from apps.desktop_post import external
    from apps.desktop_post.bridge import Owner
    from apps.desktop_post.native_controls import _Windows
    config=json.loads(Path(config_path).read_text(encoding='utf-8'))
    out=Path(config['output']);owner=None;report={'solver_executions':0,'cold':cold,'pid':os.getpid()}
    try:
        if cold:
            project=Path(config['project']);doc=json.loads(project.read_text(encoding='utf-8'))
            os.environ['CAE_POST_PROJECT']=str(project);external.restore_workspace(project,doc)
            owner=Owner();assert not owner.workspace.restore_issues,owner.workspace.restore_issues
        else:
            native=config['native_input']
            external.open_result(native['path'],out/'project',input_id=native['id'],
                source_pins=native['source_pins'],native_metadata=native['native_metadata'],
                registration_origin=native.get('registration_origin'))
            owner=Owner()
        source=p.FindSource(owner.workspace.document['sources']['result']['reader_name'])
        data=servermanager.Fetch(source)
        ids=vtk_to_numpy(data.GetPointData().GetArray('NativeNodeId')).tolist()
        vectors=vtk_to_numpy(data.GetPointData().GetArray('U_mm'))
        internal=vectors[ids.index(35)].tolist()
        assert internal==[.00125,.000125,.000125],internal
        assert len(ids)==35 and data.GetNumberOfCells()==8
        view=p.GetActiveView();display=p.Show(source,view)
        display.Representation='Surface With Edges';p.ColorBy(display,('POINTS','U_magnitude_mm'))
        display.SetScalarBarVisibility(view,True)
        bar=p.GetScalarBar(p.GetColorTransferFunction('U_magnitude_mm'),view)
        bar.Title='Displacement magnitude [mm]';bar.ComponentTitle='';bar.TitleFontSize=14;bar.LabelFontSize=12
        bar.Orientation='Horizontal';bar.WindowLocation='Lower Center';bar.ScalarBarLength=.7
        p.GetColorTransferFunction('U_magnitude_mm').RescaleTransferFunction(0.,.005)
        view.CameraParallelProjection=1
        view.CameraPosition=[20.,3.,2.];view.CameraFocalPoint=[2.5,.25,.25];view.CameraViewUp=[0.,0.,1.]
        p.ResetCamera(view)
        view.CameraParallelScale*=.6
        if not cold:
            text=p.Text(registrationName='Transfer result meaning')
            text.Text='Reference geometry / static load parameter 1\nU check: PASS / nodal stress check: FAIL\nIP stress: not output / qualification: UNKNOWN'
            label=p.Show(text,view);label.FontSize=14;label.WindowLocation='Upper Left Corner'
        layout=p.GetLayout(view)
        for width in (1440,900):
            p.RenderAllViews()
            p.SaveScreenshot(str(out/(('cold-' if cold else '')+'post-U-'+str(width)+'.png')),layout,
                ImageResolution=[width,900],FontScaling='Do not scale fonts')
        project=owner.save_project() if not cold else Path(config['project'])
        report.update(status='READ',nodes=35,elements=8,internal_node35_U_mm=internal,project=str(project),
            native_static=config['native_input']['native_metadata'].get('static'),
            clock=config['native_input']['native_metadata'].get('time'),
            selected_load_parameter=float(view.ViewTime),
            numerical_displacement='PASS',numerical_nodal_stress='FAIL',integration_point_stress='UNKNOWN_NOT_OUTPUT',
            qualification='UNKNOWN')
    except Exception as error:report.update(status='FAILED',error=str(error),traceback=traceback.format_exc())
    finally:
        if owner is not None:owner.close()
        (out/('cold-post-result.json' if cold else 'post-result.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
        platform=_Windows();window=platform.main_window()
        if window:
            platform.user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
            platform.user.PostMessageW.restype=wintypes.BOOL
            platform.user.PostMessageW(window,0x10,0,0)
    return report
