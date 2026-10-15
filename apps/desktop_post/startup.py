"""Native ParaView startup, isolated from ProgrammableSource globals."""


def _cae_post_startup():
    import os
    import sys
    import json
    import traceback
    from datetime import datetime, timezone
    from pathlib import Path
    
    cae_post_bridge = None
    project_path = Path(os.environ.get("CAE_POST_PROJECT", Path.cwd() / "project.json"))
    log_path = Path(os.environ.get("CAE_POST_LAUNCH_DIR", project_path.parent)) / "native_startup.jsonl"
    
    
    def log(event, **detail):
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(), "event": event, **detail}) + "\n")
    
    try:
        log("entered", executable=sys.executable, argv=sys.argv, project=str(project_path), app_home=os.environ.get("CAE_POST_HOME"))
        sys.path.insert(0, os.environ["CAE_POST_HOME"])
        sys.path.insert(0, str(Path(os.environ["CAE_POST_HOME"]).resolve().parents[1]))
        native_open = None
        if os.environ.get('CAE_POST_NATIVE_OPEN'):
            if os.environ.get('CAE_POST_MEASUREMENT') or os.environ.get('CAE_POST_REPORT_ORIGIN'):
                raise ValueError('An exact native project and an origin review cannot share one launch')
            from caelab.portable_project_native import resume_open_ticket, verify_opened, _native_open_readback
            from apps.desktop_post.portable_project import restore_bound_project, select_bound_target
            context, ticket = resume_open_ticket(os.environ['CAE_POST_NATIVE_OPEN'])
            log('native_project_verified', open_id=ticket.binding.open_id)
            if ticket.status == 'ADOPTION_REQUIRED':
                raise ValueError('MANAGED_SAVE_REQUIRED: explicitly adopt this raw state before opening a managed analysis project')
            action = json.loads(context.open_actions[ticket.binding.open_id].read_text(encoding='utf-8'))
            import paraview
            log('native_project_restore_begin', open_id=ticket.binding.open_id, legacy_from_gui=getattr(paraview, 'fromGUI', None))
            opened = restore_bound_project(ticket.verified_input, ticket.binding,
                allow_partial=action['request']['allow_partial'], _gui_state=True)
            for diagnostic in opened.get('native_state_diagnostics', []):
                log('native_project_gui_state', **diagnostic)
            readback = opened['readback']
            if action['request']['selection'] is not None:
                selected_readback = select_bound_target(opened['owner'], action['request']['selection'],
                    verified_input=ticket.verified_input, binding=ticket.binding)
                readback = _native_open_readback({**readback.payload, **selected_readback})
            native_open = context, ticket, opened
            project_path = Path(opened['project_path'])
            opened['owner']._native_project_context = context
            opened['owner'].native_project_context = context
            opened['owner']._native_project_ticket = ticket
            # Completion is written only after native reader/selection readback.
            log('native_project_opened', **verify_opened(context, ticket.binding.open_id, readback))
        selected = None
        if os.environ.get("CAE_POST_MEASUREMENT"):
            from caelab.post_observation import verify_origin
            selected = json.loads(Path(os.environ["CAE_POST_MEASUREMENT"]).read_text(encoding="utf-8"))
            verify_origin(selected)
            if Path(selected["project"]["path"]).resolve() != project_path.resolve():
                raise ValueError("Selected measurement belongs to another saved Post project")
        report_origin = None
        if os.environ.get("CAE_POST_REPORT_ORIGIN"):
            from report_image_origin_native import startup_request, select_restored_source
            report_origin = startup_request(os.environ["CAE_POST_REPORT_ORIGIN"], project_path)
        if selected is not None and report_origin is not None:
            raise ValueError("A measurement and Report origin cannot share one launch")
        from commands import restore_workspace
        log("module_loaded", module=restore_workspace.__module__)
        if native_open is None:
            restore_workspace(allow_repair=report_origin is None)
        if report_origin is not None:
            select_restored_source(report_origin)
        from paraview import simple as p, servermanager
        log("loaded", sources=[key[0] for key in p.GetSources()], views=[view.GetXMLName() for view in p.GetViews()], connection=str(servermanager.ActiveConnection))
        try:
            from bridge import start
            # Keep the native timer/owner alive for this actual application session.
            cae_post_bridge = start(os.environ.get("CAE_POST_SERVICE_URL"), log=log,
                owner=native_open[2]['owner'] if native_open else None,
                _portable_binding=native_open[1].binding if native_open else None)
            if selected is not None:
                verify_origin(selected)
                cae_post_bridge[0].workspace.measurement_open(origin=selected)
                log("measurement_restored", object_ref=selected["object_ref"], revision=selected["revision"])
            log("bridge_timer_installed", document_id=cae_post_bridge[0].document_id,
                session_id=cae_post_bridge[0].session_id, gui_dispatch_verified=False)
        except Exception:
            log("bridge_unavailable", traceback=traceback.format_exc())
    except BaseException:
        log("failed", traceback=traceback.format_exc())
        raise
    return cae_post_bridge


# Keep the native owner and timer alive after the script returns.
cae_post_bridge = _cae_post_startup()
