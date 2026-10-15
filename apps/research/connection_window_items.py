"""Graphics items for the selected-connection view; positions are view state only."""
from __future__ import annotations
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsObject, QGraphicsPathItem, QGraphicsView


class ConnectionNode(QGraphicsObject):
    WIDTH, HEIGHT = 252., 100.

    def __init__(self, row, on_move=None):
        super().__init__()
        self.row, self.links, self.on_move = row, [], on_move
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
                      QGraphicsItem.GraphicsItemFlag.ItemIsFocusable |
                      QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setData(0, row['key'])
        self.setToolTip('\n'.join(filter(None, [row['label'], row.get('subtitle'), row['status_label']])))
        self.setZValue(1)

    def boundingRect(self):
        return QRectF(0, 0, self.WIDTH, self.HEIGHT)

    def paint(self, painter, option, widget=None):
        palette = QApplication.palette()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(palette.base())
        pen = QPen(palette.highlight().color() if self.isSelected() else palette.mid().color(),
                   2.5 if self.isSelected() else 1.)
        if self.row['status'] == 'BROKEN':
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRoundedRect(self.boundingRect().adjusted(2, 2, -2, -2), 7, 7)
        font = QApplication.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(palette.text().color())
        metrics = QFontMetricsF(font)
        title = metrics.elidedText(self.row['label'], Qt.TextElideMode.ElideRight, self.WIDTH - 24)
        painter.drawText(QRectF(12, 9, self.WIDTH - 24, 26), Qt.AlignmentFlag.AlignVCenter, title)
        font.setBold(False)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        subtitle = metrics.elidedText(self.row.get('subtitle', ''), Qt.TextElideMode.ElideRight, self.WIDTH - 24)
        painter.drawText(QRectF(12, 37, self.WIDTH - 24, 24), Qt.AlignmentFlag.AlignVCenter, subtitle)
        # Status has a text label; failure/recency never relies only on colour.
        painter.drawText(QRectF(12, 65, self.WIDTH - 24, 25), Qt.AlignmentFlag.AlignVCenter,
                         self.row['status_label'])

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for link in self.links:
                link.update_path()
            if self.on_move:
                self.on_move(self.row['key'], value)
        return super().itemChange(change, value)


class ConnectionEdge(QGraphicsPathItem):
    def __init__(self, source, target, row):
        super().__init__()
        self.source, self.target, self.row = source, target, row
        source.links.append(self)
        target.links.append(self)
        self.setZValue(-1)
        self.setToolTip(row['label'])
        pen = QPen(QApplication.palette().mid().color(), 1.5)
        if row.get('status') == 'BROKEN':
            pen.setStyle(Qt.PenStyle.DashLine)
        self.setPen(pen)
        self.update_path()

    def update_path(self):
        forward = self.target.scenePos().x() >= self.source.scenePos().x()
        start = self.source.mapToScene(QPointF(self.source.WIDTH if forward else 0, self.source.HEIGHT / 2))
        end = self.target.mapToScene(QPointF(0 if forward else self.target.WIDTH, self.target.HEIGHT / 2))
        delta = max(60., abs(end.x() - start.x()) / 2) * (1 if forward else -1)
        path = QPainterPath(start)
        path.cubicTo(start + QPointF(delta, 0), end - QPointF(delta, 0), end)
        self.setPath(path)

    def boundingRect(self):
        return super().boundingRect().adjusted(-85, -16, 85, 16)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        path = self.path()
        end, before = path.pointAtPercent(1), path.pointAtPercent(.985)
        angle = math.atan2(end.y() - before.y(), end.x() - before.x())
        points = [end, end - QPointF(9 * math.cos(angle - .45), 9 * math.sin(angle - .45)),
                  end - QPointF(9 * math.cos(angle + .45), 9 * math.sin(angle + .45))]
        painter.setBrush(self.pen().color())
        painter.drawPolygon(QPolygonF(points))
        center = path.pointAtPercent(.5)
        label = QRectF(center.x() - 80, center.y() - 13, 160, 26)
        painter.fillRect(label, QApplication.palette().window())
        painter.setFont(QApplication.font())
        painter.setPen(QApplication.palette().text().color())
        metrics = QFontMetricsF(QApplication.font())
        painter.drawText(label, Qt.AlignmentFlag.AlignCenter,
                         metrics.elidedText(self.row['label'], Qt.TextElideMode.ElideRight, 155))


class ConnectionView(QGraphicsView):
    def __init__(self, scene, parent=None, on_open=None):
        super().__init__(scene, parent)
        self.on_open = on_open
        self.on_view_change = None
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setAccessibleName('선택 문서 연결 그래프')
        self.setToolTip('문서를 선택하고 Enter로 엽니다. 카드를 끌어 배치합니다. Ctrl+휠로 확대합니다.')

    def zoom(self, factor):
        current = self.transform().m11()
        target = min(2., max(.25, current * factor))
        self.scale(target / current, target / current)
        if self.on_view_change:
            self.on_view_change()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
        else:
            super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, ConnectionNode):
            self.scene().clearSelection()
            item.setSelected(True)
            if self.on_open:
                self.on_open()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)
