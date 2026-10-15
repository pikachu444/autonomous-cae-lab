"""One explicitly selected owned native check. Not an automatic campaign."""
from pathlib import Path
import json
import os
import traceback


def read_saved_project(root, project, kind, analysis_id, *, expected_record=None):
    """Open the committed project member using the existing verified restore path."""
    import FreeCAD as App
    import FreeCADGui as Gui
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.projects import remember_open
    from caelab import native_cad
    from caelab.storage import canonical_hash
    root,project=Path(root),Path(project)
    manifest,entry=native_cad.unpack_project(project,root/'cold-project')
    expected=manifest['metadata']['shells' if kind=='shell' else 'beams'][analysis_id]
    owner=doc=None
    try:
        doc=App.openDocument(str(entry));doc.UndoMode=1
        remember_open(doc,manifest,project)
        owner=Owner(doc,root/'cold-exports',App=App,Gui=Gui)
        record=owner.shell._record(analysis_id) if kind=='shell' else owner.beam._get(analysis_id)
        applied_key='applied' if kind=='shell' else 'applied_draft_hash'
        for key in ('draft',applied_key):
            if key not in record or key not in expected:
                raise ValueError('Saved project has no '+key+' record')
            if canonical_hash(record.get(key))!=canonical_hash(expected.get(key)):
                raise ValueError('Saved project '+key+' differs from the committed member')
            if expected_record is not None and canonical_hash(record.get(key))!=canonical_hash(expected_record.get(key)):
                raise ValueError('Cold '+key+' differs from the original owner')
        state=owner.shell.inspect(analysis_id) if kind=='shell' else owner.beam.inspect(analysis_id)
        if kind=='shell':
            rows=state['records']
            if len(rows)!=1 or not rows[0]['applied'] or not rows[0]['ready']:
                raise ValueError('Cold shell record is missing, unapplied, or not ready: '+str(state))
        elif not state.get('can_freeze'):
            raise ValueError('Cold beam record is not ready: '+str(state))
        return {'project':str(project),'inspection':state,'draft_equal':True,'applied_equal':True,
            'regions':record['draft'].get('regions'),'axis_regions':record['draft'].get('axis_regions')}
    finally:
        if owner is not None:owner.close()
        if doc is not None:App.closeDocument(doc.Name)


def run():
    if os.environ.get('CAELAB_B13_OWNED_CHECK')!='PRO-B13-SHELL-BEAM-20261015-03-DIRECT':
        raise RuntimeError('Launch this check through examples/b13/run_native_check.py, not an existing user GUI')
    import FreeCAD as App
    import FreeCADGui as Gui
    from examples.b13.models import create_shell,create_beam,beam_reference
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.shell_freeze import freeze as freeze_shell
    from apps.desktop_pre.beam_native import freeze as freeze_beam
    from caelab.storage import save_json
    root=Path(os.environ['CAELAB_B13_CHECK_ROOT']).absolute()
    options=json.loads((root/'options.json').read_text(encoding='utf-8'))
    owned_before=set(App.listDocuments());owner=None
    report={'execution':'NOT_RUN','native_engineering_acceptance':False,'windows_acceptance':False}
    try:
        if options['kind']=='shell':owner,analysis=create_shell(root/'model',reverse_second=options['reverse_second'])
        else:
            owner,analysis=create_beam(root/'model',case=options['case'],angle=options['angle'],
                                      output_mode=options['output_mode'],regional_axes=options['regional_axes'])
            save_json(root/'reference-before-run.json',beam_reference(options['angle'],options['case']))
        info=(freeze_shell(owner.shell,analysis) if options['kind']=='shell' else freeze_beam(owner,owner.beam._get(analysis)))
        report.update(prepared=info,execution='PREPARED_NOT_RUN')
        frozen=Path(owner.export_root)/info['snapshot_relative']
        # Explicit opt-in only. Existing adapter/process owner, no replacement solver.
        if options['run']:
            if options['kind']=='shell':
                from caelab.adapters.shell_fem import ShellFemCalculixAdapter as Adapter
            else:from caelab.adapters.beam_fem import BeamFemCalculixAdapter as Adapter
            result=Adapter().run({'snapshot_path':str(frozen)},output=root/'run')
            report.update(execution=result['execution_status'],result=result)
        # Close only the document created above; independently reopen the saved
        # native document under a new existing Owner. No hidden repair/rebind.
        # Lab Save publishes a checked .caepre; FileName can still be the older
        # standalone FCStd saved before the editing metadata existed.
        project=owner.project.path
        if project is None:raise ValueError('No committed project was saved')
        expected_record=(owner.shell._record(analysis) if options['kind']=='shell' else owner.beam._get(analysis))
        name=owner.doc.Name;owner.close();owner=None
        App.closeDocument(name)
        cold=read_saved_project(root,project,options['kind'],analysis,expected_record=expected_record)
        report['fresh_owner_inspection']=cold['inspection'];report['cold_read']=cold
    except BaseException as exc:
        report.update(execution='FAILED',error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc())
    finally:
        # Product-owned process tree cleanup is the outer Windows Job's finally.
        # This inner check releases only its own owners/documents, on every exit.
        try:
            if owner is not None:owner.close()
        except Exception as exc:report['owner_cleanup_error']=str(exc)
        for name in set(App.listDocuments())-owned_before:
            try:App.closeDocument(name)
            except Exception as exc:report.setdefault('document_cleanup_errors',[]).append(str(exc))
        save_json(root/'b13-native-observation.json',report)
        Gui.getMainWindow().close()
