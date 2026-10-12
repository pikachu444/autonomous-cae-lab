"""Native Qt widgets used only by the desktop review prototype."""
from __future__ import annotations
import math

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPen, QPainter, QPainterPath, QPolygonF, QFont
from PySide6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem,
    QGraphicsItem, QGraphicsPathItem,
)

INK = "#263442"
BLUE = "#286998"
TEAL = "#218b81"
ORANGE = "#bd702b"
RED = "#b5433b"
PALE = "#e7f0f7"


def make_table(headers, rows, editable=(), select_rows=True):
    table = QTableWidget(len(rows), len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(True)
    table.verticalHeader().setDefaultSectionSize(27)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.horizontalHeader().setStretchLastSection(True)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows if select_rows
                               else QAbstractItemView.SelectionBehavior.SelectItems)
    table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                          QAbstractItemView.EditTrigger.EditKeyPressed |
                          QAbstractItemView.EditTrigger.AnyKeyPressed)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem()
            item.setData(Qt.ItemDataRole.DisplayRole, "" if value is None else value)
            if c not in editable:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    return table


class CurveView(QWidget):
    """A plotted synthetic curve with real point/range selection."""
    samplesSelected = Signal(list)
    def __init__(self, parent=None, xlabel="Time [s]", ylabel="Response"):
        super().__init__(parent)
        self.setMinimumSize(260, 180)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.series = []
        self.xlabel, self.ylabel = xlabel, ylabel
        self.selected_ids, self.excluded_ids = set(), set()
        self.drag_start = None
        self.drag_end = None
        self.caption = "Synthetic illustration"
        self._limits = (0, 1, 0, 1)
        self._plot = QRectF()

    def set_series(self, series):
        self.series = series
        self.update()

    def select_ids(self, ids, excluded=None):
        self.selected_ids = set(ids)
        if excluded is not None:
            self.excluded_ids = set(excluded)
        self.update()

    def _point(self, x, y):
        x0, x1, y0, y1 = self._limits
        return QPointF(self._plot.left() + (x-x0)/(x1-x0)*self._plot.width(),
                       self._plot.bottom() - (y-y0)/(y1-y0)*self._plot.height())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#ffffff"))
        rect = QRectF(70, 38, max(10, self.width()-100), max(10, self.height()-100))
        self._plot = rect
        values = [(x, y) for s in self.series for x, y in zip(s["x"], s["y"])
                  if isinstance(y, (float, int)) and math.isfinite(y)]
        if values:
            xs, ys = zip(*values)
            x0, x1, y0, y1 = min(xs), max(xs), min(0, min(ys)), max(ys)
            self._limits = (x0, x1 if x1>x0 else x0+1, y0, y1*1.08 if y1>y0 else y0+1)
        x0, x1, y0, y1 = self._limits
        p.setFont(QFont("Segoe UI", 9))
        for i in range(6):
            x = rect.left() + rect.width()*i/5
            y = rect.bottom() - rect.height()*i/5
            p.setPen(QPen(QColor("#e8edf1"), 1))
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            p.setPen(QColor("#62717d"))
            p.drawText(QRectF(x-25, rect.bottom()+5, 50, 20), Qt.AlignmentFlag.AlignCenter, f"{x0+(x1-x0)*i/5:.3g}")
            p.drawText(QRectF(5, y-10, 57, 20), Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter, f"{y0+(y1-y0)*i/5:.3g}")
        p.setPen(QPen(QColor("#9daab5"), 1))
        p.drawRect(rect)
        p.setPen(QColor(INK))
        p.drawText(QRectF(rect.left(), rect.bottom()+28, rect.width(), 24), Qt.AlignmentFlag.AlignCenter, self.xlabel)
        p.drawText(12, 21, self.ylabel)
        legend_x = max(170, self.width()-300)
        for n, s in enumerate(self.series):
            color = QColor(s.get("color", BLUE))
            p.setPen(QPen(color, 2))
            path = QPainterPath()
            active = False
            ids = s.get("ids", [])
            for i, (x, y) in enumerate(zip(s["x"], s["y"])):
                if not isinstance(y, (float, int)) or not math.isfinite(y):
                    active = False
                    continue
                point = self._point(x, y)
                if not active:
                    path.moveTo(point)
                    active = True
                else:
                    path.lineTo(point)
                if i < len(ids) and ids[i] in self.selected_ids:
                    p.setBrush(QColor(ORANGE))
                    p.drawEllipse(point, 3, 3)
                if i < len(ids) and ids[i] in self.excluded_ids:
                    p.setPen(QPen(QColor(RED), 1.5))
                    p.drawLine(point+QPointF(-3,-3), point+QPointF(3,3))
                    p.drawLine(point+QPointF(-3,3), point+QPointF(3,-3))
                    p.setPen(QPen(color, 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.drawLine(legend_x, 15+n*17, legend_x+20, 15+n*17)
            p.drawText(legend_x+26, 19+n*17, s.get("name", "Curve"))
        if self.drag_start is not None and self.drag_end is not None:
            p.fillRect(QRectF(min(self.drag_start,self.drag_end), rect.top(),
                             abs(self.drag_end-self.drag_start), rect.height()), QColor(40,105,152,35))
        p.setPen(QColor("#7e8a95"))
        p.drawText(QRectF(0, self.height()-20, self.width()-10, 18),
                   Qt.AlignmentFlag.AlignRight, self.caption)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()
            self.drag_start = event.position().x()
            self.drag_end = self.drag_start

    def mouseMoveEvent(self, event):
        if self.drag_start is not None:
            self.drag_end = event.position().x()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.drag_start is None or not self.series:
            return
        a, b = sorted((self.drag_start, event.position().x()))
        s = self.series[0]
        points = [(i, self._point(x, y).x()) for i,(x,y) in enumerate(zip(s["x"],s["y"]))
                  if isinstance(y, (int,float)) and math.isfinite(y)]
        if abs(a-b) < 4 and points:
            selected = [min(points, key=lambda pair:abs(pair[1]-a))[0]]
        else:
            selected = [i for i,x in points if a<=x<=b]
        ids = s.get("ids", [str(i) for i in range(len(s["x"]))])
        chosen = {ids[i] for i in selected}
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            chosen |= self.selected_ids
        self.selected_ids = chosen
        self.samplesSelected.emit(list(chosen))
        self.drag_start = self.drag_end = None
        self.update()

    def keyPressEvent(self, event):
        if not self.series:
            return super().keyPressEvent(event)
        ids = self.series[0].get("ids", [])
        if ids and event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            current = next((ids.index(x) for x in self.selected_ids if x in ids), 0)
            offset = 1 if event.key()==Qt.Key.Key_Right else -1
            chosen = ids[max(0,min(len(ids)-1,current+offset))]
            self.selected_ids = {chosen}
            self.samplesSelected.emit([chosen])
            self.update()
        else:
            super().keyPressEvent(event)


class EngineeringView(QWidget):
    """Selectable, rotatable QPainter illustration, explicitly not a native host."""
    faceSelected = Signal(str)
    def __init__(self, mode="cad", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.setMinimumSize(400, 300)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.selected = "Clamp/Pad/Face6"
        self.yaw = -.52
        self.pitch = .48
        self.zoom = 1.0
        self.drag = None
        self.faces = []
        self.mesh = False
        self.field = "Displacement [mm]"
        self.thickness = 14
        self.label = "Native host illustration" if mode in ("cad","post") else "Domain illustration"

    def set_selected(self, name):
        self.selected = name
        self.update()

    def _project(self, v):
        x,y,z=v
        xx=x*math.cos(self.yaw)-y*math.sin(self.yaw)
        yy=x*math.sin(self.yaw)+y*math.cos(self.yaw)
        scale = min(self.width()/150, self.height()/115)*self.zoom
        return QPointF(self.width()/2+xx*scale,
                       self.height()*.58+(yy*math.sin(self.pitch)-z*math.cos(self.pitch))*scale)

    def paintEvent(self, event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#f4f6f8"))
        p.setPen(QPen(QColor("#e4e9ed"),1))
        for i in range(-90,91,15):
            p.drawLine(self._project((i,-60,0)), self._project((i,60,0)))
            p.drawLine(self._project((-90,i,0)), self._project((90,i,0)))
        boxes = [((-48,-28,0),(48,28,8),"Base/Face2", "#a7b4c0"),
                 ((-35,-12,8),(-20,12,34),"Clamp/Leg/Face1","#95a6b5"),
                 ((20,-12,8),(35,12,34),"Clamp/Leg/Face2","#95a6b5"),
                 ((-38,-16,34),(38,16,34+self.thickness),"Clamp/Pad/Face6","#c3cdd5")]
        if self.mode in ("pde","thermal","thermoelastic"):
            boxes = [((-50,-32,0),(50,32,3),"Left edge","#abc3d4")]
        self.faces=[]
        for lo,hi,name,color in boxes:
            x0,y0,z0=lo; x1,y1,z1=hi
            polygons=[[(x0,y0,z0),(x1,y0,z0),(x1,y0,z1),(x0,y0,z1)],
                      [(x1,y0,z0),(x1,y1,z0),(x1,y1,z1),(x1,y0,z1)],
                      [(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]]
            for n, vs in enumerate(polygons):
                poly=QPolygonF([self._project(v) for v in vs])
                self.faces.append((poly,name))
                fill=QColor(color)
                if self.mode=="post":
                    fill=QColor([TEAL,"#81c7b4","#e6c56b"][n])
                if name==self.selected:
                    fill=QColor("#9fc5e0")
                p.setBrush(fill.darker(110) if n==0 else fill)
                p.setPen(QPen(QColor(BLUE if name==self.selected else "#6f818e"),2 if name==self.selected else 1))
                p.drawPolygon(poly)
                if self.mesh or self.mode in ("pde","thermal","thermoelastic","post"):
                    p.save()
                    clip=QPainterPath(); clip.addPolygon(poly); p.setClipPath(clip)
                    bounds=poly.boundingRect()
                    p.setPen(QPen(QColor("#638697"),.7))
                    for i in range(int(bounds.left())-100,int(bounds.right())+100,24):
                        p.drawLine(QPointF(i,bounds.top()),QPointF(i+100,bounds.bottom()))
                        p.drawLine(QPointF(i,bounds.top()),QPointF(i-100,bounds.bottom()))
                    p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor(INK))
        p.setFont(QFont("Segoe UI",10))
        p.drawText(18,28,self.field if self.mode=="post" else self.selected)
        p.setPen(QColor("#74818c"))
        p.drawText(QRectF(12,self.height()-28,self.width()-24,20),Qt.AlignmentFlag.AlignLeft,self.label+" · synthetic")
        if self.mode=="post":
            for i in range(7):
                p.fillRect(self.width()-68,65+i*25,15,25,QColor.fromHsv(170-i*24,145,205))
                p.drawText(self.width()-48,78+i*25,f"{.31*(6-i)/6:.2f}")
        p.setPen(QPen(QColor("#aa4850"),2)); p.drawLine(45,self.height()-65,85,self.height()-65)
        p.drawText(90,self.height()-61,"X")
        p.setPen(QPen(QColor(TEAL),2)); p.drawLine(45,self.height()-65,45,self.height()-105)
        p.drawText(39,self.height()-112,"Z")
        p.end()

    def mousePressEvent(self,event):
        self.setFocus()
        self.drag=event.position()
        if event.button()==Qt.MouseButton.LeftButton:
            for poly,name in reversed(self.faces):
                if poly.containsPoint(event.position(),Qt.FillRule.OddEvenFill):
                    self.selected=name; self.faceSelected.emit(name); self.update(); break

    def mouseMoveEvent(self,event):
        if self.drag is not None and event.buttons() & (Qt.MouseButton.RightButton|Qt.MouseButton.MiddleButton):
            delta=event.position()-self.drag
            self.yaw+=delta.x()*.008
            self.pitch=max(.1,min(1.3,self.pitch+delta.y()*.008))
            self.drag=event.position(); self.update()

    def mouseReleaseEvent(self,event):
        self.drag=None

    def wheelEvent(self,event):
        self.zoom=max(.45,min(2.0,self.zoom*(1.1 if event.angleDelta().y()>0 else .9)))
        self.update()

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_F:
            self.zoom=1; self.update()
        else:
            super().keyPressEvent(event)


class GraphNode(QGraphicsRectItem):
    def __init__(self,key,label,x,y,callback):
        super().__init__(0,0,170,58)
        self.key, self.callback = key, callback
        self.setPos(x,y)
        self.setBrush(QColor("#ffffff")); self.setPen(QPen(QColor("#9cb0c0"),1))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        text=QGraphicsTextItem(label,self); text.setDefaultTextColor(QColor(INK)); text.setPos(9,8)
        text.setFont(QFont("Segoe UI",10)); text.setTextWidth(151)
        self.setToolTip(label)

    def itemChange(self,change,value):
        if change==QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():
            self.callback()
        return super().itemChange(change,value)


class NodeView(QGraphicsView):
    chosen = Signal(str)
    opened = Signal(str)
    moved = Signal(dict)
    def __init__(self,nodes,links,parent=None):
        super().__init__(parent)
        scene=QGraphicsScene(self); self.setScene(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#f4f6f8"))
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.nodes={}; self.links=links; self.edges=[]
        for key,label,x,y in nodes:
            node=GraphNode(key,label,x,y,self.redraw)
            self.nodes[key]=node; scene.addItem(node)
        for a,b in links:
            edge=QGraphicsPathItem(); edge.setPen(QPen(QColor("#91a6b5"),1.7)); edge.setZValue(-1)
            edge.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,True)
            edge.setData(0,(a,b)); scene.addItem(edge); self.edges.append(edge)
        self.redraw()
        scene.selectionChanged.connect(self._selection)
        self.setMinimumSize(240,200)

    def redraw(self):
        if not hasattr(self,"edges"): return
        for edge,(a,b) in zip(self.edges,self.links):
            if a not in self.nodes or b not in self.nodes: continue
            start=self.nodes[a].pos()+QPointF(170,29)
            end=self.nodes[b].pos()+QPointF(0,29)
            path=QPainterPath(start); distance=max(45,abs(end.x()-start.x())*.45)
            path.cubicTo(start+QPointF(distance,0),end-QPointF(distance,0),end)
            edge.setPath(path)

    def _selection(self):
        for item in self.scene().selectedItems():
            if isinstance(item,GraphNode):
                self.chosen.emit(item.key); break

    def mouseDoubleClickEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if isinstance(item,QGraphicsTextItem): item=item.parentItem()
        if isinstance(item,GraphNode): self.opened.emit(item.key)
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        self.moved.emit({key:[node.pos().x(),node.pos().y()] for key,node in self.nodes.items()})

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):
            for item in self.scene().selectedItems():
                if isinstance(item,GraphNode): self.opened.emit(item.key); return
        super().keyPressEvent(event)
