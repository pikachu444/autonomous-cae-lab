"""Public editable input geometry for the NS1 native Windows check.

Run with FreeCADCmd.exe, or call create(output) from FreeCAD's Python console.
This creates geometry only. It neither generates a mesh nor starts a solver.
The generator has not been executed in the remote NS1 implementation environment.
"""
from pathlib import Path


def create(output):
    import FreeCAD as App
    path = Path(output).expanduser().resolve()
    if path.exists():
        raise FileExistsError('Existing model is preserved: ' + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = App.newDocument('NS1SingleSolid')
    try:
        specimen = doc.addObject('Part::Box', 'Specimen')
        specimen.Label = '인장 시편'
        specimen.Length, specimen.Width, specimen.Height = 10., 10., 20.
        doc.recompute()
        if not specimen.Shape.isValid() or len(specimen.Shape.Solids) != 1:
            raise ValueError('Generated solid is invalid')
        if abs(specimen.Shape.Volume - 2000.) > 1e-7:
            raise ValueError('Unexpected input geometry volume')
        doc.saveAs(str(path))
    finally:
        App.closeDocument(doc.Name)
    reopened = App.openDocument(str(path))
    try:
        if reopened.Specimen.TypeId != 'Part::Box':
            raise ValueError('Editable box was not retained')
        if abs(reopened.Specimen.Height.Value - 20.) > 1e-9:
            raise ValueError('Saved height differs from the original input')
    finally:
        App.closeDocument(reopened.Name)
    return path


if __name__ == '__main__':
    print(create(Path(__file__).with_name('single-solid.FCStd')))
