"""Executed by native paraview --script; sources are checked before state load."""
import os
import sys
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

project_path = Path(os.environ.get("CAE_POST_PROJECT", Path.cwd() / "project.json"))
log_path = project_path.parent / "native_startup.jsonl"


def log(event, **detail):
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(), "event": event, **detail}) + "\n")

try:
    log("entered", executable=sys.executable, argv=sys.argv, project=str(project_path), app_home=os.environ.get("CAE_POST_HOME"))
    sys.path.insert(0, os.environ["CAE_POST_HOME"])
    from commands import restore_workspace
    log("module_loaded", module=restore_workspace.__module__)
    restore_workspace()
    from paraview import simple as p, servermanager
    log("loaded", sources=[key[0] for key in p.GetSources()], views=[view.GetXMLName() for view in p.GetViews()], connection=str(servermanager.ActiveConnection))
except BaseException:
    log("failed", traceback=traceback.format_exc())
    raise
