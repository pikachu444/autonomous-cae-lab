import os, sys
sys.path.insert(0, os.environ["CAE_POST_HOME"])
from pathlib import Path
from paraview import simple as p
if p.FindSource("B | 200 N | native U [mm]") is None:
    startup = Path(os.environ["CAE_POST_HOME"]) / "startup.py"
    exec(compile(startup.read_text(encoding="utf-8"), str(startup), "exec"))
from commands import show_candidate
show_candidate()
