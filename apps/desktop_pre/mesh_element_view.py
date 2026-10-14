"""Transient element display in the existing FreeCAD 3D view, without model edits.

FreeCAD 1.1.4 FEM's native builder supplies the geometry. Only its plain display
subtree is retained; document-linked selection roots are not copied to the view.
"""
import re
import uuid

from .fem_edit import _mesh_hash, _positive_id
from .mesh_binding import global_placement


def selected_element_ids(owner, mesh):
    """Read original FEM pick names; resolving them loses FEM-only subelements."""
    owner.assert_thread()
    identifiers = set()
    for row in owner.Gui.Selection.getSelectionEx(owner.doc.Name, 0):
        if row.Object is not mesh:
            continue
        for name in row.SubElementNames:
            match = re.fullmatch(r'Elem([1-9][0-9]*)F[1-9][0-9]*', name)
            if match and int(match[1]) in mesh.FemMesh.Volumes:
                identifiers.add(int(match[1]))
    return sorted(identifiers)


def _native_geometry(owner, mesh, identifiers):
    import Fem
    from pivy import coin
    subset = Fem.FemMesh()
    nodes = mesh.FemMesh.Nodes
    inverse_own_pose = mesh.Placement.inverse()
    element_nodes = {i: tuple(mesh.FemMesh.getElementNodes(i)) for i in identifiers}
    for ids in element_nodes.values():
        if len(ids) not in (4, 10) or len(set(ids)) != len(ids):
            raise ValueError('이 요소의 연결은 표시할 수 없습니다. 사면체 절점 연결을 확인하세요.')
    for i in sorted({i for ids in element_nodes.values() for i in ids}):
        # Native Nodes already includes FemMeshObject.Placement (1.1.4).
        p = inverse_own_pose.multVec(nodes[i])
        subset.addNode(p.x, p.y, p.z, i)
    for i, ids in element_nodes.items():
        subset.addVolume(list(ids), i)
    active = owner.App.ActiveDocument
    temporary = None
    try:
        # Native temporary documents cannot be saved and have no 3D window.
        temporary = owner.App.newDocument('CAELabElement' + uuid.uuid4().hex, hidden=True, temp=True)
        obj = temporary.addObject('Fem::FemMeshObject', 'Elements')
        obj.FemMesh = subset
        obj.ViewObject.ShowInner = True
        obj.ViewObject.BackfaceCulling = False
        obj.ViewObject.ShapeColor = (0.14, 0.40, 0.64)
        obj.ViewObject.LineWidth = 2.0
        obj.ViewObject.DisplayMode = 'Faces & Wireframe'
        obj.ViewObject.Visibility = True
        temporary.recompute()
        root = obj.ViewObject.RootNode
        modes = [root.getChild(i) for i in range(root.getNumChildren())
                 if isinstance(root.getChild(i), coin.SoSwitch) and root.getChild(i).whichChild.getValue() >= 0]
        if len(modes) != 1:
            raise ValueError('설치된 FreeCAD에서 요소 표시 모드를 확인하지 못했습니다.')
        return modes[0].getChild(modes[0].whichChild.getValue()).copy()
    finally:
        if temporary is not None:
            owner.App.closeDocument(temporary.Name)
        if active is not None and owner.App.ActiveDocument is not active:
            owner.App.setActiveDocument(active.Name)


class MeshElementView:
    def __init__(self, owner, mesh):
        self.owner, self.mesh, self.doc = owner, mesh, owner.doc
        self._session = owner.session_id
        self._overlay = self._scene = self._view = None
        self._camera = self._selection = None
        self._switches = []
        self._hidden = []
        self._hash = self._pose = self._generation = None
        self.element_ids = []
        self._building = False
        self._closed = False
        owner.App.addDocumentObserver(self)

    @property
    def active(self):
        return self._overlay is not None

    def _validate(self, expected_hash):
        self.owner.assert_thread()
        if (self.owner.closed or self.owner.doc is not self.doc or self.owner.session_id != self._session or
                self.doc.getObject(self.mesh.Name) is not self.mesh):
            self.restore()
            raise ValueError('문서 또는 메시가 바뀌었습니다. 열린 문서에서 품질을 다시 읽으세요.')
        if self.owner.App.ActiveDocument is not self.doc:
            self.restore()
            raise ValueError('다른 문서가 활성화되어 있습니다. 원 메시 문서로 돌아와 다시 선택하세요.')
        if getattr(self.owner.fem, '_pending', {}):
            self.restore()
            raise ValueError('메시 생성 중에는 요소 보기를 바꿀 수 없습니다. 생성이 끝난 뒤 품질을 다시 읽으세요.')
        if not isinstance(expected_hash, str) or _mesh_hash(self.mesh.FemMesh) != expected_hash:
            self.restore()
            raise ValueError('품질 조회 뒤 메시가 바뀌었습니다. 품질을 다시 읽고 요소를 선택하세요.')

    def _capture(self):
        from pivy import coin
        self._view = self.owner.Gui.activeDocument().activeView()
        self._scene = self._view.getSceneGraph()
        self._camera = self._view.getCamera()
        self._selection = [(row.Object, list(row.SubElementNames))
                           for row in self.owner.Gui.Selection.getSelectionEx(self.doc.Name, 0)]
        self._switches = []
        for obj in self.doc.Objects:
            if hasattr(obj, 'ViewObject'):
                root = obj.ViewObject.RootNode
                for i in range(root.getNumChildren()):
                    node = root.getChild(i)
                    if isinstance(node, coin.SoSwitch):
                        self._switches.append((node, int(node.whichChild.getValue())))

    def _clear_scene(self):
        if self._overlay is not None:
            if self._scene.findChild(self._overlay) >= 0:
                self._scene.removeChild(self._overlay)
            self._overlay = None
        for node, value in self._hidden:
            node.whichChild = value
        self._hidden = []

    def select(self, identifiers, expected_hash):
        self._validate(expected_hash)
        if not set(identifiers) <= set(self.mesh.FemMesh.Volumes):
            raise ValueError('선택한 요소가 현재 메시에서 없어졌습니다. 품질을 다시 읽으세요.')
        if self._scene is None:
            self._capture()
        self.owner.Gui.Selection.clearSelection(self.doc.Name)
        for i in identifiers:
            self.owner.Gui.Selection.addSelection(self.mesh, 'Elem' + str(_positive_id(i)) + 'F1')
        self._hash, self._pose = expected_hash, global_placement(self.mesh)
        self._generation = self.owner.generation

    def show(self, element_ids, expected_mesh_sha256, *, isolate=False, fit=False):
        from pivy import coin
        self._validate(expected_mesh_sha256)
        if not isinstance(element_ids, list) or not 1 <= len(element_ids) <= 4096:
            raise ValueError('표 또는 모델에서 표시할 요소를 선택하세요. 한 번에 최대 4096개를 표시합니다.')
        identifiers = sorted({_positive_id(i) for i in element_ids})
        if not set(identifiers) <= set(self.mesh.FemMesh.Volumes):
            raise ValueError('선택한 요소가 현재 메시에서 없어졌습니다. 품질을 다시 읽으세요.')
        self._building = True
        try:
            geometry = _native_geometry(self.owner, self.mesh, identifiers)
        finally:
            self._building = False
        if self._scene is None:
            self._capture()
        self._clear_scene()
        try:
            overlay = coin.SoSeparator()
            pick = coin.SoPickStyle()
            pick.style = coin.SoPickStyle.UNPICKABLE
            overlay.addChild(pick)
            pose = self.mesh.getGlobalPlacement()
            transform = coin.SoTransform()
            transform.translation = (pose.Base.x, pose.Base.y, pose.Base.z)
            transform.rotation = tuple(pose.Rotation.Q)
            overlay.addChild(transform)
            overlay.addChild(geometry)
            if isolate:
                self._hidden = list(self._switches)
                for node, _ in self._switches:
                    node.whichChild = coin.SO_SWITCH_NONE
            self._overlay = overlay
            self._scene.addChild(overlay)
            self.owner.Gui.Selection.clearSelection(self.doc.Name)
            for i in identifiers:
                self.owner.Gui.Selection.addSelection(self.mesh, 'Elem' + str(i) + 'F1')
            if fit:
                # Fit only the retained selected geometry, not all scene objects.
                self._view.getCameraNode().viewAll(overlay, coin.SbViewportRegion(*self._view.getSize()), 1.2)
            self._hash, self._pose = expected_mesh_sha256, global_placement(self.mesh)
            self._generation = self.owner.generation
            self.element_ids = identifiers
        except Exception:
            self.restore()
            raise
        return {'mesh_id': self.mesh.Name, 'element_ids': identifiers, 'isolated': bool(isolate)}

    def check_current(self):
        if self._scene is None:
            return True
        try:
            self._validate(self._hash)
            if (self.owner.generation != self._generation or global_placement(self.mesh) != self._pose or
                    self.owner.Gui.activeDocument().activeView().getSceneGraph() != self._scene):
                self.restore()
                return False
            return True
        except Exception:
            self.restore()
            return False

    def restore(self, *, document_closing=False):
        """Remove transient geometry, restoring view and original raw selection."""
        try:
            if document_closing:
                if self._overlay is not None and self._scene.findChild(self._overlay) >= 0:
                    self._scene.removeChild(self._overlay)
            else:
                self._clear_scene()
            if self._view is not None and not self.owner.closed and not document_closing:
                self._view.setCamera(self._camera)
            if self._selection is not None and not self.owner.closed and not document_closing:
                self.owner.Gui.Selection.clearSelection(self.doc.Name)
                for obj, names in self._selection:
                    if self.doc.getObject(obj.Name) is obj:
                        for name in names or ['']:
                            self.owner.Gui.Selection.addSelection(obj, name)
        finally:
            self._overlay = self._scene = self._view = None
            self._camera = self._selection = None
            self._switches = []
            self._hidden = []
            self._hash = self._pose = self._generation = None
            self.element_ids = []

    def slotChangedObject(self, obj, prop=None):
        if not self._building and obj.Document is self.doc and self._scene is not None:
            self.restore()

    slotDeletedObject = slotChangedObject

    def slotDeletedDocument(self, doc):
        if doc is self.doc:
            self.restore(document_closing=True)

    def slotActivateDocument(self, doc):
        if not self._building and doc is not self.doc and self._scene is not None:
            self.restore()

    def slotStartSaveDocument(self, doc):
        if doc is self.doc:
            self.restore()

    def close(self):
        if self._closed:
            return
        self.restore()
        self.owner.App.removeDocumentObserver(self)
        self._closed = True


def get_view(owner, mesh):
    """One transient element view per owner, shared by GUI and typed commands."""
    view = getattr(owner, '_mesh_element_view', None)
    if view is None or view.mesh is not mesh or view._closed:
        if view is not None:
            view.close()
        view = owner._mesh_element_view = MeshElementView(owner, mesh)
    return view


def dispatch(owner, arguments, target):
    owner.assert_thread()
    if not isinstance(arguments, dict) or set(arguments) - {'mode', 'element_ids', 'mesh_sha256'}:
        raise ValueError('요소 보기에는 표시 방식과 선택 요소, 조회한 메시를 지정하세요.')
    mesh = owner.fem._mesh(target)
    view = get_view(owner, mesh)
    mode = arguments.get('mode')
    if mode == 'restore' and set(arguments) == {'mode'}:
        view.restore()
        return {'mesh_id': mesh.Name, 'element_ids': [], 'isolated': False}
    if mode == 'read_selection' and set(arguments) == {'mode'}:
        return {'mesh_id': mesh.Name, 'element_ids': selected_element_ids(owner, mesh)}
    if mode not in ('show', 'isolate', 'fit') or set(arguments) != {'mode', 'element_ids', 'mesh_sha256'}:
        raise ValueError('표시 또는 격리·확대할 요소와 현재 메시 품질을 지정하세요.')
    return view.show(arguments['element_ids'], arguments['mesh_sha256'], isolate=mode in ('isolate', 'fit'), fit=mode == 'fit')
