"""Editable native example: 3 sliders, 2 flexible depths, 4 repeated CAD Links.

Run inside FreeCAD 1.1.4, with this repository on sys.path. This file delegates
ALL motion calculation and acceptance to the existing native M1/M2/M3 code.
It never supplies calculated poses, a substitute solver or a claimed pass.
"""
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path: sys.path.insert(0, str(REPOSITORY))


def create(output):
    import FreeCAD as App
    import FreeCADGui as Gui
    from PySide import QtCore
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.assembly_pose_candidate import _hold, _release
    from apps.desktop_pre.motion_occurrence import unique_path, world_placement
    from apps.desktop_pre.motion import _pose
    from caelab.storage import save_json
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    Gui.activateWorkbench('AssemblyWorkbench')
    doc = App.newDocument('M4NestedSliders'); _hold(doc)
    doc.Label = '선택 자세 예제 — 중첩 슬라이더'
    owner = None
    try:
        part = doc.addObject('Part::Box', 'SliderBlock')
        part.Label = '공통 원부품'; part.Length = 12.; part.Width = 8.; part.Height = 6.
        definitions = doc.addObject('App::DocumentObjectGroup', 'Definitions')
        definitions.Label = '편집 가능한 원부품과 모듈'; definitions.addObject(part)
        def assembly(name, label):
            obj = doc.addObject('Assembly::AssemblyObject', name); obj.Type = 'Assembly'; obj.Label = label
            obj.newObject('Assembly::JointGroup', name+'Joints'); return obj
        def link(container, source, name, value=None, flexible=False):
            obj = container.newObject('Assembly::AssemblyLink' if flexible else 'App::Link', name)
            obj.LinkedObject = source
            if hasattr(obj, 'LinkTransform'): obj.LinkTransform = False
            if value is not None: obj.Placement = value
            if flexible: obj.Rigid = False
            obj.recompute(); return obj
        inner = assembly('InnerDefinition', '안쪽 모듈 원본'); definitions.addObject(inner)
        for i in range(2):
            obj = link(inner, part, 'RepeatedBlock', App.Placement(App.Vector(0,20*i,0), App.Rotation()))
            obj.Label = '슬라이더'
        outer = assembly('OuterDefinition', '바깥 모듈 원본'); definitions.addObject(outer)
        link(outer, inner, 'InnerOccurrence', App.Placement(App.Vector(30,0,0), App.Rotation(App.Vector(1,0,0),20)), True)
        link(outer, part, 'ThirdBlock', App.Placement(App.Vector(0,40,0), App.Rotation()))
        root = assembly('WorkingAssembly', '3개 슬라이더 조립')
        base = link(root, part, 'Base'); base.Label = '기구 기준 부품'
        link(root, outer, 'OuterOccurrence', App.Placement(App.Vector(40,0,0), App.Rotation(App.Vector(0,0,1),30)), True)
        # Explicit outside transform tests the stored WORLD-root contract too.
        enclosure = doc.addObject('App::Part', 'Mount'); enclosure.Label = '조립 배치'
        enclosure.addObject(root)
        enclosure.Placement = App.Placement(App.Vector(100,25,15), App.Rotation(App.Vector(0,0,1),15))
        doc.recompute()
        owner = Owner(doc, output/'exchange', App=App, Gui=Gui); owner.QtCore = QtCore
        motion = owner.motion; target = {'assembly_id': root.Name}
        leaves = [obj for obj in motion._parts(root) if obj.isDerivedFrom('App::Link')
                  and obj.getLinkedObject().isDerivedFrom('Part::Feature') and obj is not base]
        paths = [unique_path(root, obj)['path'] for obj in leaves]
        if len(leaves) != 3 or not any(len(path) >= 4 for path in paths):
            raise RuntimeError('설치 native의 두 깊이 가동 조립과 세 배치를 확인하지 못했습니다. 생성 문서를 보존합니다.')
        motion.dispatch('pre.joint.create', {'type':'Grounded', 'occurrence_id':base.Name}, target)
        drives, traces = [], []
        for index, obj in enumerate(sorted(leaves,key=lambda item: unique_path(root,item)['path']), 1):
            # Coincident JCS at the starting geometry; translational motion is
            # along this exact local Z. No offset/pose is inferred from a trace.
            ground_jcs = world_placement(root,base).inverse().multiply(world_placement(root,obj))
            def connector(part, value):
                p = _pose(value)
                return {'object_id':part.Name, 'subelement':'', 'placement':{
                    'translation':p[:3], 'quaternion':p[3:], 'unit':'mm','frame':'reference_local'}}
            created = motion.dispatch('pre.joint.create', {'type':'Slider','connectors':[
                connector(base, ground_jcs), connector(obj, App.Placement())]}, target)
            drives.append({'joint_id':created['joint_id'], 'type':'Linear', 'formula':str(index*4.)+'*time', 'unit':'mm'})
            traces.append({'id':'Tip'+str(index), 'occurrence_id':obj.Name, 'point':[6.,4.,3.],
                'frame':'occurrence_local','coordinate_unit':'mm','output_frame':'document_global'})
        definition = {'time':{'start':0.,'end':1.,'step':.25,'unit':'s'}, 'fps':20,
                      'native_error_tolerance':1.e-6, 'drives':drives, 'traces':traces}
        motion.dispatch('pre.motion.configure', {'definition':definition}, target)
        result = motion.dispatch('pre.motion.calculate', {}, target)
        retained = motion._saved_result(root, result['id'])
        if retained.get('accepted') is not True:
            raise RuntimeError('native 운동 결과의 관절 검사가 충족되지 않았습니다. 실패/원결과를 보존합니다.')
        for obj in definitions.Group:
            if hasattr(obj,'ViewObject'): obj.ViewObject.Visibility=False
        definitions.ViewObject.Visibility=False
        root.ViewObject.Visibility=True; enclosure.ViewObject.Visibility=True
        saved = owner.project.save(output/'nested-sliders.caepre')
        selection = {'assembly_id':root.Name,'calculation_id':result['id'],'frame':result['frame_count']-1}
        save_json(output/'selected-frame.json', selection)
        save_json(output/'example-result.json', {'state':'NATIVE_MOTION_ACCEPTED', 'project':saved,
            'selected':selection,'occurrences':paths,'solver':'FreeCAD native Assembly','FEM_execution':'NOT_PERFORMED'})
        App.setActiveDocument(doc.Name); Gui.activeDocument().activeView().viewAxonometric(); Gui.activeDocument().activeView().fitAll()
        return selection
    except Exception as error:
        if owner is not None:
            try: owner.project.save(output/'example-failed.caepre')
            except Exception as save_error: App.Console.PrintError('실패 사본 저장 확인 필요: '+str(save_error)+'\n')
        else:
            doc.saveCopy(str(output/'example-failed.FCStd'))
        save_json(output/'example-result.json', {'state':'FAILED', 'error':str(error),'FEM_execution':'NOT_PERFORMED'})
        raise
    finally:
        if owner is not None: owner.close()
        _release(doc)


def main():
    import FreeCADGui as Gui
    from PySide import QtGui
    try: from PySide import QtWidgets
    except ImportError: QtWidgets = QtGui
    folder = QtWidgets.QFileDialog.getExistingDirectory(Gui.getMainWindow(),'예제 저장 폴더 선택')
    if folder: create(folder)

if __name__ == '__main__': main()
