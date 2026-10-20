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
    document = None
    try:
        import FreeCAD
        if request.get('mode') == 'model_context':
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from apps.desktop_pre.native_context import model_snapshot
            document = FreeCAD.openDocument(request['source'])
            result['model'] = model_snapshot(document)
            return
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
        if document is not None:
            FreeCAD.closeDocument(document.Name)
        if temporary.is_file():
            temporary.unlink()
        (output / "converted.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


main()
