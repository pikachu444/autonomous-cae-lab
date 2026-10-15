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
        restore_workspace(allow_repair=report_origin is None)
        if report_origin is not None:
            select_restored_source(report_origin)
        from paraview import simple as p, servermanager
        log("loaded", sources=[key[0] for key in p.GetSources()], views=[view.GetXMLName() for view in p.GetViews()], connection=str(servermanager.ActiveConnection))
        if os.environ.get("CAE_POST_SERVICE_URL"):
            try:
                from bridge import start
                # Keep the native timer/owner alive for this actual application session.
                cae_post_bridge = start(os.environ["CAE_POST_SERVICE_URL"], log=log)
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
