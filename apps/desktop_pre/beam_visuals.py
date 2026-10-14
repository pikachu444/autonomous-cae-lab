"""Small native paint views. No web view, plotting service or CAD replacement."""
import math
from caelab.beam_model import number


def qt_gui():
    try:
        from PySide import QtGui
    except ImportError:
        from PySide6 import QtGui
    return QtGui


def section_view(W, C):
    G=qt_gui()
    class SectionView(W.QWidget):
        def __init__(self):
            super().__init__();self.setMinimumSize(250,220)
            self.setSizePolicy(W.QSizePolicy.Expanding,W.QSizePolicy.Expanding)
            self.values=None;self.setAccessibleName('직사각 빔 단면과 방향')
        def set_section(self,width,height,angle):
            try:
                w,h,a=number(width),number(height),number(angle)
                self.values=(w,h,a) if w>0 and h>0 else None
            except ValueError:self.values=None
            self.update()
        def paintEvent(self,event):
            p=G.QPainter(self);p.setRenderHint(G.QPainter.Antialiasing)
            p.fillRect(self.rect(),self.palette().base())
            p.setPen(self.palette().text().color())
            if self.values is None:
                p.drawText(self.rect(),C.Qt.AlignCenter,'단면 치수를 확인하세요');p.end();return
            w,h,angle=self.values
            available=min(self.width()-120,self.height()-95)
            scale=max(1.,available)/math.hypot(w,h)
            cx,cy=self.width()/2,self.height()/2+5
            a=math.radians(angle);v1=(math.cos(a),-math.sin(a));v2=(-math.sin(a),-math.cos(a))
            def xy(x,y):return C.QPointF(cx+scale*(x*v1[0]+y*v2[0]),cy+scale*(x*v1[1]+y*v2[1]))
            p.setPen(G.QPen(self.palette().mid().color(),1,C.Qt.DashLine))
            p.drawLine(C.QPointF(20,cy),C.QPointF(self.width()-20,cy))
            p.drawLine(C.QPointF(cx,38),C.QPointF(cx,self.height()-25))
            section_ink=G.QColor('#88baff' if self.palette().base().color().value()<128 else '#2468a2')
            p.setPen(G.QPen(section_ink,2))
            fill=G.QColor(section_ink);fill.setAlpha(35);p.setBrush(fill)
            p.drawPolygon(G.QPolygonF([xy(-w/2,-h/2),xy(w/2,-h/2),xy(w/2,h/2),xy(-w/2,h/2)]))
            p.setBrush(C.Qt.NoBrush)
            for label,dx,dy in [('1',w*.65,0),('2',0,h*.65)]:
                dest=xy(dx,dy);p.drawLine(C.QPointF(cx,cy),dest)
                p.drawText(C.QRectF(dest.x()-12,max(40,dest.y()-25),50,20),label)
            p.setPen(self.palette().text().color())
            p.drawText(C.QRectF(12,8,self.width()-24,25),C.Qt.AlignCenter,f'폭 {w:g} × 높이 {h:g} mm')
            p.drawText(C.QRectF(12,self.height()-25,self.width()-24,22),C.Qt.AlignCenter,f'단면 회전 {angle:g}°  |  1축: 폭   2축: 높이')
            p.end()
    return SectionView()


def curve_view(W,C):
    G=qt_gui()
    class Curve(W.QWidget):
        def __init__(self):
            super().__init__();self.points=[];self.caption='';self.selected=None;self.on_select=None
            self.setMinimumSize(280,180);self.setFocusPolicy(C.Qt.StrongFocus)
            self.setAccessibleName('빔 길이에 따른 선택 성분 그래프')
        def set_values(self,points,caption):
            self.points=points;self.caption=caption;self.selected=None;self.update()
        def value_limits(self):
            y=[r[2] for r in self.points]
            lo,hi=min(y),max(y)
            if hi==lo:
                pad=max(abs(lo),1)*.08;lo-=pad;hi+=pad
            return lo,hi
        def coordinates(self):
            if not self.points:return []
            x=[r[1] for r in self.points];y=[r[2] for r in self.points]
            lo,hi=self.value_limits()
            xspan=max(max(x)-min(x),1e-12);yspan=hi-lo
            return [(65+(xx-min(x))/xspan*max(10,self.width()-90),
                self.height()-40-(yy-lo)/yspan*max(10,self.height()-80)) for _,xx,yy in self.points]
        def paintEvent(self,event):
            p=G.QPainter(self);p.setRenderHint(G.QPainter.Antialiasing);p.fillRect(self.rect(),self.palette().base())
            p.setPen(self.palette().text().color());p.drawText(12,21,self.caption or '성분을 선택하세요')
            p.drawText(self.width()-115,self.height()-10,'빔 길이 [mm]')
            xy=self.coordinates()
            if xy:
                p.setPen(G.QPen(self.palette().mid().color(),1))
                p.drawLine(65,35,65,self.height()-40);p.drawLine(65,self.height()-40,self.width()-20,self.height()-40)
                p.setPen(G.QPen(self.palette().link().color(),2))
                p.drawPolyline(G.QPolygonF([C.QPointF(*point) for point in xy]))
                for j,(x,y) in enumerate(xy):
                    radius=5 if j==self.selected else 2.5;p.drawEllipse(C.QPointF(x,y),radius,radius)
                p.setPen(self.palette().text().color())
                lo,hi=self.value_limits()
                p.drawText(4,47,f'{hi:.4g}');p.drawText(4,self.height()-41,f'{lo:.4g}')
                if self.selected is not None:
                    n,x,y=self.points[self.selected]
                    p.drawText(C.QRectF(70,27,self.width()-85,22),f'절점 {n}: {y:.7g}')
            p.end()
        def mousePressEvent(self,event):
            pos=event.position() if hasattr(event,'position') else event.pos()
            xy=self.coordinates()
            if not xy:return
            self.selected=min(range(len(xy)),key=lambda j:(xy[j][0]-pos.x())**2+(xy[j][1]-pos.y())**2)
            if self.on_select:self.on_select(self.selected)
            self.setFocus();self.update()
        def keyPressEvent(self,event):
            if event.key() in (C.Qt.Key_Left,C.Qt.Key_Right) and self.points:
                delta=-1 if event.key()==C.Qt.Key_Left else 1
                self.selected=max(0,min(len(self.points)-1,(self.selected or 0)+delta))
                if self.on_select:self.on_select(self.selected)
                self.update()
            else:super().keyPressEvent(event)
    return Curve()
