"""FreeCADCmd entry point for its installed native FRD/VTK converter."""
import json
import os
from pathlib import Path
import shutil
import traceback


def main():
    request = json.loads(Path(os.environ["CAELAB_FRD_CONVERSION"]).read_text(encoding="utf-8"))
    output = Path(request["output"])
    temporary = output / "native.frd"
    result = {}
    try:
        import FreeCAD
        import Fem
        shutil.copyfile(request["source"], temporary)
        Fem.frdToVTK(str(temporary), False)
        result["native_version"] = list(FreeCAD.Version())
        if not list(output.rglob("*.vtu")):
            raise ValueError("The installed FreeCAD converter produced no VTU result")
    except Exception as error:
        result["error"] = str(error)
        traceback.print_exc()
    finally:
        if temporary.is_file():
            temporary.unlink()
        (output / "converted.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


main()
