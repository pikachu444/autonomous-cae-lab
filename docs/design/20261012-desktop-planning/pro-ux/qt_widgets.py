"""Native Qt widgets used only by the desktop review prototype."""
from __future__ import annotations
import math

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QColor, QPen, QPainter, QPainterPath, QPolygonF, QFont
from PySide6.QtWidgets import (
    QApplication, QWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem,
    QGraphicsItem, QGraphicsPathItem, QStyledItemDelegate, QLineEdit,
)

INK = "#263442"
BLUE = "#286998"
TEAL = "#218b81"
ORANGE = "#bd702b"
RED = "#b5433b"
PALE = "#e7f0f7"


class EngineeringTextDelegate(QStyledItemDelegate):
    """Keep exponent notation, signed numbers and incomplete drafts as text.

    The default float delegate is a two-decimal spin box. It must never edit an
    engineering coefficient, step size or tolerance in this prototype.
    """
    def createEditor(self,parent,option,index):
        editor=QLineEdit(parent);editor.setFrame(False);return editor

    def setEditorData(self,editor,index):
        value=index.data(Qt.ItemDataRole.EditRole)
        editor.setText("" if value is None else str(value));editor.selectAll()

    def setModelData(self,editor,model,index):
        model.setData(index,editor.text(),Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self,editor,option,index):
        editor.setGeometry(option.rect)


def make_table(headers, rows, editable=(), select_rows=True):
    table = QTableWidget(len(rows), len(headers))
    table.value_delegate=EngineeringTextDelegate(table)
    table.setItemDelegate(table.value_delegate)
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
        self.cursor_x = None
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
        rect = QRectF(70, 38, max(10, self.width()-100), max(10, self.height()-122))
        self._plot = rect
        values = [(x, y) for s in self.series for x, y in zip(s["x"], s["y"])
                  if isinstance(y, (float, int)) and math.isfinite(y)]
        if values:
            xs, ys = zip(*values)
            x0, x1, y0, y1 = min(xs), max(xs), min(0, min(ys)), max(ys)
            self._limits = (x0, x1 if x1>x0 else x0+1, y0, y1*1.08 if y1>y0 else y0+1)
        x0, x1, y0, y1 = self._limits
        font = QFont(self.font());font.setPointSize(9);p.setFont(font)
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
                if s.get("scatter"):
                    p.setBrush(color);p.drawEllipse(point,4,4)
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
            if not s.get("scatter"):p.drawPath(path)
            p.drawLine(legend_x, 15+n*17, legend_x+20, 15+n*17)
            p.drawText(legend_x+26, 19+n*17, s.get("name", "Curve"))
        if self.cursor_x is not None and x0 <= self.cursor_x <= x1:
            cx=self._point(self.cursor_x,y0).x()
            p.setPen(QPen(QColor(ORANGE),1.5,Qt.PenStyle.DashLine))
            p.drawLine(QPointF(cx,rect.top()),QPointF(cx,rect.bottom()))
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


class ReportPage(QWidget):
    """Vector-painted native review page, shared by preview and Qt PDF."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setMinimumSize(420,440)
        self.title="Research report";self.section={};self.page_number=1;self.page_count=1

    def set_page(self,title,section,number,count):
        self.title=title;self.section=section;self.page_number=number;self.page_count=count;self.update()

    def paint_page(self,p,target):
        p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale=min(target.width()/720,target.height()/1018)
        p.translate(target.center().x()-360*scale,target.center().y()-509*scale);p.scale(scale,scale)
        p.fillRect(QRectF(0,0,720,1018),QColor("white"))
        def font(size,bold=False):
            f=QFont(self.font());f.setPixelSize(size);f.setBold(bold);p.setFont(f)
        font(12);p.setPen(QColor("#62717d"))
        p.drawText(QRectF(48,30,624,24),Qt.AlignmentFlag.AlignLeft,"AUTONOMOUS CAE LAB   /   REVIEW DRAFT")
        font(25,True);p.setPen(QColor(INK))
        p.drawText(QRectF(48,69,624,70),Qt.TextFlag.TextWordWrap,self.title)
        p.setPen(QPen(QColor("#b8c9d6"),1));p.drawLine(48,148,672,148)
        section=self.section;font(20,True);p.setPen(QColor(INK))
        p.drawText(QRectF(48,168,624,66),Qt.TextFlag.TextWordWrap,section.get("title","No included section"))
        font(14)
        if section.get("unavailable"):
            p.setPen(QColor(RED))
            p.drawText(QRectF(48,256,624,200),Qt.TextFlag.TextWordWrap,
                       "Evidence unavailable\n\nThis section has no available source. Other sections remain editable.")
        elif section.get("kind")=="text":
            p.drawText(QRectF(48,252,624,634),Qt.TextFlag.TextWordWrap,section.get("text",""))
        elif section.get("kind")=="table":
            headers=section.get("headers",[]);rows=section.get("rows",[])
            widths=[max(6,len(str(h))) for h in headers]
            for row in rows:
                for i,value in enumerate(row[:len(widths)]):widths[i]=max(widths[i],min(28,len(str(value))))
            total=sum(widths) or 1;widths=[624*w/total for w in widths]
            x=48;y=252;p.fillRect(QRectF(48,y,624,52),QColor("#eaf0f5"));font(12,True)
            for width,header in zip(widths,headers):
                p.setPen(QColor(INK));p.drawText(QRectF(x+7,y+5,width-14,42),
                    Qt.TextFlag.TextWordWrap|Qt.AlignmentFlag.AlignVCenter,str(header));x+=width
            y+=52;font(13)
            for n,row in enumerate(rows):
                if n%2==0:p.fillRect(QRectF(48,y,624,28),QColor("#f7f9fb"))
                x=48
                for width,value in zip(widths,row):
                    p.setPen(QColor(INK));p.drawText(QRectF(x+7,y,width-14,28),
                        Qt.AlignmentFlag.AlignVCenter,str(value) if value is not None else "Unavailable");x+=width
                y+=28
            font(12);p.setPen(QColor("#62717d"))
            p.drawText(QRectF(48,y+20,624,82),Qt.TextFlag.TextWordWrap,section.get("caption",""))
        elif section.get("kind")=="curve":
            series=section.get("series",[])
            points=[(x,y) for s in series for x,y in zip(s["x"],s["y"])
                    if isinstance(x,(int,float)) and isinstance(y,(int,float)) and math.isfinite(x) and math.isfinite(y)]
            if points:
                xs,ys=zip(*points);x0,x1=min(xs),max(xs);y0,y1=min(0,min(ys)),max(ys)
                if x0==x1:x1=x0+1
                if y0==y1:y1=y0+1
                area=QRectF(104,294,544,410);font(12)
                def point(x,y):
                    return QPointF(area.left()+(x-x0)/(x1-x0)*area.width(),area.bottom()-(y-y0)/(y1-y0)*area.height())
                for i in range(6):
                    x=area.left()+area.width()*i/5;y=area.bottom()-area.height()*i/5
                    p.setPen(QPen(QColor("#e3e9ee"),1))
                    p.drawLine(QPointF(x,area.top()),QPointF(x,area.bottom()))
                    p.drawLine(QPointF(area.left(),y),QPointF(area.right(),y))
                    p.setPen(QColor(INK))
                    p.drawText(QRectF(x-28,area.bottom()+8,56,24),Qt.AlignmentFlag.AlignCenter,f"{x0+(x1-x0)*i/5:.3g}")
                    p.drawText(QRectF(46,y-12,50,24),Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter,f"{y0+(y1-y0)*i/5:.3g}")
                for n,s in enumerate(series):
                    color=QColor(s.get("color",BLUE));p.setPen(QPen(color,2))
                    path=QPainterPath();started=False
                    for x,y in zip(s["x"],s["y"]):
                        if not isinstance(x,(int,float)) or not isinstance(y,(int,float)) or not math.isfinite(x) or not math.isfinite(y):
                            started=False;continue
                        position=point(x,y)
                        if s.get("scatter"):
                            p.setBrush(color);p.drawEllipse(position,4,4)
                        elif started:path.lineTo(position)
                        else:path.moveTo(position);started=True
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    if not s.get("scatter"):p.drawPath(path)
                    if s.get("scatter"):
                        p.setBrush(color);p.drawEllipse(QPointF(94,778+20*n),3,3);p.setBrush(Qt.BrushStyle.NoBrush)
                    else:p.drawLine(84,778+20*n,100,778+20*n)
                    p.drawText(108,782+20*n,s.get("name","Curve"))
                p.setPen(QColor(INK));font(14)
                p.drawText(QRectF(104,738,544,26),Qt.AlignmentFlag.AlignCenter,section.get("xlabel",""))
                p.drawText(48,268,section.get("ylabel",""))
            font(12);p.setPen(QColor("#62717d"))
            p.drawText(QRectF(48,866,624,60),Qt.TextFlag.TextWordWrap,section.get("caption",""))
        font(11);p.setPen(QColor("#62717d"));p.drawLine(48,942,672,942)
        p.drawText(QRectF(48,954,560,22),Qt.AlignmentFlag.AlignLeft,"Synthetic review content / UNKNOWN / NOT_RELEASED")
        p.drawText(QRectF(609,954,63,22),Qt.AlignmentFlag.AlignRight,f"{self.page_number} / {self.page_count}")
        p.restore()

    def paintEvent(self,event):
        painter=QPainter(self);painter.fillRect(self.rect(),QColor("#dce3e9"))
        self.paint_page(painter,QRectF(self.rect()).adjusted(20,14,-20,-14));painter.end()


class EngineeringView(QWidget):
    """Selectable, rotatable QPainter illustration, explicitly not a native host."""
    faceSelected = Signal(str)
    sketchLineAdded = Signal(list)
    pointSelected = Signal(str)
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
        self.model_width, self.model_height = 72, 28
        self.geometry_type, self.instances = "Clamp", 2
        self.through_hole = False
        self.sketch = False
        self.conditions = []
        self.field_max, self.field_available = .31, True
        self.filter_mode, self.deformation_scale = "Surface", 10
        self.annotation = ""
        self.warp_magnitude = .31
        self.joint_angle, self.joint_type, self.moving_part = 15, "Revolute", "Clamp"
        self.mesh_size, self.mesh_type, self.selected_element = 2.0, "Tet4", None
        self.draw_line, self.sketch_line_start, self.sketch_segments = False, None, []
        self.point_pick=False;self.plane_axis="X";self.plane_offset=0.0
        self.label = "Native host illustration" if mode in ("cad","post") else "Domain illustration"

    def set_geometry(self, geometry):
        for field,attr in (("width","model_width"),("height","model_height"),("thickness","thickness"),
                           ("geometry_type","geometry_type"),("instances","instances"),("through_hole","through_hole")):
            if field in geometry:setattr(self,attr,geometry[field])
        self.conditions=geometry.get("conditions",[])
        self.sketch_segments=geometry.get("sketch",{}).get("lines",[])
        self.moving_part=geometry.get("selected_part","Clamp")
        self.joint_type=geometry.get("joint",{}).get("type","Revolute")
        self.joint_angle=geometry.get("joint",{}).get("angle",15)
        self.mesh_size=geometry.get("mesh",{}).get("size",2)
        self.mesh_type=geometry.get("mesh",{}).get("type","Tet4")
        self.update()

    def set_selected(self, name):
        self.selected = name
        self.update()

    def _project(self, v):
        x,y,z=v
        xx=x*math.cos(self.yaw)-y*math.sin(self.yaw)
        yy=x*math.sin(self.yaw)+y*math.cos(self.yaw)
        scale = min(self.width()/(150+max(0,self.instances-2)*30), self.height()/(115+max(0,self.instances-2)*20))*self.zoom
        return QPointF(self.width()/2+xx*scale,
                       self.height()*.58+(yy*math.sin(self.pitch)-z*math.cos(self.pitch))*scale)

    def _part_point(self,v,name):
        if self.mode not in ("cad","post") or not name.startswith(self.moving_part+"/"):return v
        x,y,z=v;a=math.radians(self.joint_angle)
        if self.joint_type=="Slider":return (x+self.joint_angle/4,y,z)
        if self.joint_type=="Fixed":return v
        return (x*math.cos(a)+(z-8)*math.sin(a),y,8-x*math.sin(a)+(z-8)*math.cos(a))

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
            boxes = [((-self.model_width/2,-self.model_height/2,0),(self.model_width/2,self.model_height/2,3),"Left edge","#abc3d4")]
        if self.mode in ("cad","post"):
            w=max(.1,self.model_width);h=max(.1,self.model_height);t=max(.1,self.thickness)
            if self.geometry_type in ("Plate","Block"):
                boxes=[((-w/2,-h/2,0),(w/2,h/2,t),"Plate/Pad/Face6","#b9c8d4")]
            else:
                boxes=[((-w*.65,-h,0),(w*.65,h,8),"Base/Face2","#a7b4c0"),
                       ((-w*.49,-h*.4,8),(-w*.28,h*.4,h+6),"Clamp/Leg/Face1","#95a6b5"),
                       ((w*.28,-h*.4,8),(w*.49,h*.4,h+6),"Clamp/Leg/Face2","#95a6b5"),
                       ((-w*.53,-h*.57,h+6),(w*.53,h*.57,h+6+t),"Clamp/Pad/Face6","#c3cdd5")]
            if self.geometry_type=="Clamp":
                if self.instances==1:boxes=boxes[:1]
                elif self.instances>2:
                    assembly=list(boxes[1:])
                    for index in range(2,self.instances):
                        offset=(index-1)*(h*1.3)
                        for lo,hi,name,color in assembly:
                            boxes.append(((lo[0],lo[1]+offset,lo[2]),(hi[0],hi[1]+offset,hi[2]),name.replace("Clamp/","Clamp "+str(index)+"/"),color))
            if self.sketch:
                p.fillRect(self.rect(),QColor("#f4f6f8"));r=QRectF(self.width()*.2,self.height()*.25,min(self.width()*.7,w*self.width()/140),min(self.height()*.5,h*self.height()/100))
                p.setPen(QPen(QColor(TEAL),2));p.setBrush(QColor("#dcebe7"));p.drawRect(r)
                font=QFont(self.font());font.setPointSize(11);p.setFont(font);p.drawText(QRectF(r.left(),r.bottom()+10,r.width(),30),Qt.AlignmentFlag.AlignCenter,f"Width {w:g} mm")
                p.drawText(20,int(r.center().y()),f"Height {h:g} mm")
                p.drawText(20,30,"Rectangle sketch · dimension illustration")
                p.setPen(QPen(QColor(BLUE),2))
                for x1,y1,x2,y2 in self.sketch_segments:
                    p.drawLine(QPointF(60+x1*4,80+y1*4),QPointF(60+x2*4,80+y2*4))
                p.end();return
        if self.mode=="post" and self.filter_mode=="Clip":
            axis={"X":0,"Y":1,"Z":2}[self.plane_axis];clipped=[]
            for lo,hi,name,color in boxes:
                if lo[axis]>=self.plane_offset:continue
                upper=list(hi);upper[axis]=min(hi[axis],self.plane_offset);clipped.append((lo,tuple(upper),name,color))
            boxes=clipped
        elif self.mode=="post" and self.filter_mode=="Slice":
            axis={"X":0,"Y":1,"Z":2}[self.plane_axis];lo=[-48,-28,0];hi=[48,28,48]
            lo[axis]=self.plane_offset-.4;hi[axis]=self.plane_offset+.4;boxes=[(tuple(lo),tuple(hi),"Slice plane","#89b9b1")]
        elif self.mode=="post" and self.filter_mode=="Warp by vector":
            boxes=[(lo,(hi[0],hi[1],hi[2]+self.warp_magnitude*self.deformation_scale*(hi[2]/48)),name,color) for lo,hi,name,color in boxes]
        self.faces=[]
        for lo,hi,name,color in boxes:
            x0,y0,z0=lo; x1,y1,z1=hi
            polygons=[[(x0,y0,z0),(x1,y0,z0),(x1,y0,z1),(x0,y0,z1)],
                      [(x1,y0,z0),(x1,y1,z0),(x1,y1,z1),(x1,y0,z1)],
                      [(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]]
            for n, vs in enumerate(polygons):
                poly=QPolygonF([self._project(self._part_point(v,name)) for v in vs])
                self.faces.append((poly,name))
                fill=QColor(color)
                if self.mode=="post":
                    fill=QColor(([TEAL,"#81c7b4","#e6c56b"][n] if self.field_max else "#91b9ce") if self.field_available else "#c5cbd0")
                if name==self.selected and self.mode!="post":
                    fill=QColor("#9fc5e0")
                p.setBrush(fill.darker(110) if n==0 else fill)
                p.setPen(QPen(QColor(BLUE if name==self.selected else "#6f818e"),2 if name==self.selected else 1))
                p.drawPolygon(poly)
                if self.mesh or self.mode in ("pde","thermal","thermoelastic","post"):
                    p.save()
                    clip=QPainterPath(); clip.addPolygon(poly); p.setClipPath(clip)
                    bounds=poly.boundingRect()
                    p.setPen(QPen(QColor("#638697"),.7))
                    for i in range(int(bounds.left())-100,int(bounds.right())+100,max(8,int(self.mesh_size*12))):
                        p.drawLine(QPointF(i,bounds.top()),QPointF(i+100,bounds.bottom()))
                        if self.mesh_type!="Hex illustration":p.drawLine(QPointF(i,bounds.top()),QPointF(i-100,bounds.bottom()))
                    p.restore()
        if self.mesh and self.selected_element is not None:
            point=self._project((15 if self.selected_element==314 else -15,0,self.model_height+6+self.thickness))
            p.setPen(QPen(QColor(ORANGE),3));p.setBrush(QColor(245,180,80,110));p.drawEllipse(point,15,15)
        if self.point_pick:
            p.setPen(QPen(QColor(ORANGE),2));p.setBrush(QColor("white"))
            for name,x in (("Gauge left",-25),("Gauge right",25),("Clamp centre",0)):
                point=self._project((x,0,50));p.drawEllipse(point,5,5);p.drawText(point+QPointF(8,-8),name)
        if self.through_hole and self.mode in ("cad","post"):
            centre=self._project(self._part_point((0,0,self.model_height+6+self.thickness),"Clamp/Pad/Face6"))
            p.setBrush(QColor("#637986"));p.setPen(QPen(QColor("#34556b"),2));p.drawEllipse(centre,22*self.zoom,11*self.zoom)
        if self.conditions and self.mode=="cad":
            point=self._project((0,0,self.model_height+6+self.thickness))
            p.setPen(QPen(QColor(ORANGE),3));p.drawLine(point+QPointF(0,-65),point+QPointF(0,-10))
            p.drawLine(point+QPointF(0,-10),point+QPointF(-6,-20));p.drawLine(point+QPointF(0,-10),point+QPointF(6,-20))
        if self.mode in ("pde","thermal","thermoelastic"):
            x=self.model_width/2;y=self.model_height/2
            edges={"Left edge":((-x,-y,3),(-x,y,3)),"Right edge":((x,-y,3),(x,y,3)),"Top edge":((-x,y,3),(x,y,3)),"Bottom edge":((-x,-y,3),(x,-y,3))}
            if self.selected in edges:
                p.setPen(QPen(QColor(ORANGE),4));a,b=edges[self.selected];p.drawLine(self._project(a),self._project(b))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor(INK))
        font=QFont(self.font());font.setPointSize(10);p.setFont(font)
        p.drawText(18,28,self.field if self.mode=="post" else self.selected)
        p.setPen(QColor("#74818c"))
        p.drawText(QRectF(12,self.height()-28,self.width()-24,20),Qt.AlignmentFlag.AlignLeft,self.label+" · synthetic")
        if self.annotation:p.drawText(18,52,self.annotation)
        if self.mode=="post" and self.field_available and self.field_max==0:
            p.fillRect(self.width()-68,65,15,35,QColor("#91b9ce"));p.drawText(self.width()-48,85,"0")
        if self.mode=="post" and self.field_available and self.field_max!=0:
            for i in range(7):
                p.fillRect(self.width()-68,65+i*25,15,25,QColor.fromHsv(170-i*24,145,205))
                p.drawText(self.width()-48,78+i*25,f"{self.field_max*(6-i)/6:.3g}")
        p.setPen(QPen(QColor("#aa4850"),2)); p.drawLine(45,self.height()-65,85,self.height()-65)
        p.drawText(90,self.height()-61,"X")
        p.setPen(QPen(QColor(TEAL),2)); p.drawLine(45,self.height()-65,45,self.height()-105)
        p.drawText(39,self.height()-112,"Z")
        p.end()

    def mousePressEvent(self,event):
        self.setFocus()
        self.drag=event.position()
        if event.button()==Qt.MouseButton.LeftButton and self.sketch and self.draw_line:
            self.sketch_line_start=event.position();return
        if event.button()==Qt.MouseButton.LeftButton and self.mode in ("pde","thermal","thermoelastic"):
            x=self.model_width/2;y=self.model_height/2
            edges={"Left edge":((-x,-y,3),(-x,y,3)),"Right edge":((x,-y,3),(x,y,3)),
                   "Top edge":((-x,y,3),(x,y,3)),"Bottom edge":((-x,-y,3),(x,-y,3))}
            def distance(pair):
                a,b=[self._project(v) for v in pair];v=b-a;p=event.position()-a
                length=v.x()*v.x()+v.y()*v.y();t=max(0,min(1,(p.x()*v.x()+p.y()*v.y())/length)) if length else 0
                return (event.position()-(a+v*t)).manhattanLength()
            self.selected=min(edges,key=lambda key:distance(edges[key]));self.faceSelected.emit(self.selected);self.update();return
        if event.button()==Qt.MouseButton.LeftButton and self.point_pick:
            choices=[(name,self._project((x,0,50))) for name,x in (("Gauge left",-25),("Gauge right",25),("Clamp centre",0))]
            chosen=min(choices,key=lambda pair:(pair[1]-event.position()).manhattanLength())[0]
            self.pointSelected.emit(chosen);return
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
        if self.sketch_line_start is not None:
            a=self.sketch_line_start;b=event.position()
            self.sketch_line_start=None;self.draw_line=False
            self.sketchLineAdded.emit([round((a.x()-60)/4,2),round((a.y()-80)/4,2),round((b.x()-60)/4,2),round((b.y()-80)/4,2)])
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
    """Paint the label in the node itself; no transient child text wrapper."""
    def __init__(self,key,label,x,y,callback):
        super().__init__(0,0,170,58)
        self.key, self.label, self.callback = key, str(label), callback
        self.setPos(x,y);self.setBrush(QColor("#ffffff"));self.setPen(QPen(QColor("#9cb0c0"),1))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setToolTip(label)

    def paint(self,painter,option,widget=None):
        super().paint(painter,option,widget)
        painter.save();font=QFont(QApplication.font());font.setPointSize(10)
        painter.setFont(font);painter.setPen(QColor(INK))
        painter.drawText(QRectF(10,5,150,48),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,self.label)
        painter.setPen(QPen(QColor(BLUE),1));painter.setBrush(QColor("#f4f8fc"))
        painter.drawEllipse(QPointF(0,29),4,4);painter.drawEllipse(QPointF(170,29),4,4);painter.restore()

    def itemChange(self,change,value):
        if change==QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.scene():self.callback()
        return super().itemChange(change,value)


class NodeView(QGraphicsView):
    chosen = Signal(str)
    opened = Signal(str)
    moved = Signal(dict)
    edgeChosen = Signal(str,str)
    portChosen = Signal(str,str)
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

    def set_positions(self,positions):
        for key,xy in positions.items():
            if key in self.nodes:self.nodes[key].setPos(float(xy[0]),float(xy[1]))
        self.redraw()

    def select_node(self,key):
        self.scene().clearSelection()
        if key in self.nodes:self.nodes[key].setSelected(True)

    def set_links(self,links):
        for edge in self.edges:self.scene().removeItem(edge)
        self.links=list(links);self.edges=[]
        for a,b in links:
            edge=QGraphicsPathItem();edge.setPen(QPen(QColor("#91a6b5"),1.7));edge.setZValue(-1)
            edge.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,True);edge.setData(0,(a,b))
            self.scene().addItem(edge);self.edges.append(edge)
        self.redraw()

    def _selection(self):
        for item in self.scene().selectedItems():
            if isinstance(item,GraphNode):
                self.chosen.emit(item.key); break
            if isinstance(item,QGraphicsPathItem) and item.data(0):
                a,b=item.data(0);self.edgeChosen.emit(a,b);break

    def mousePressEvent(self,event):
        point=self.mapToScene(event.position().toPoint())
        for key,node in self.nodes.items():
            local=node.mapFromScene(point)
            for port,x in (("input",0),("output",170)):
                if (local-QPointF(x,29)).manhattanLength()<12:
                    self.select_node(key);self.portChosen.emit(key,port);return
        super().mousePressEvent(event)

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
