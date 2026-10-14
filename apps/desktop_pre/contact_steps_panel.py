"""Native Qt step table and selected-condition curve. No solver is called here."""
from copy import deepcopy
import importlib
import math
import uuid

def add_steps_page(panel, W, C):
    G = importlib.import_module(W.__package__ + '.QtGui')
    class Plot(W.QWidget):
        def __init__(self):
            super().__init__()
            self.points, self.unit, self.axis_label = [], '', ''
            self.setMinimumHeight(170)
        def paintEvent(self, event):
            painter = G.QPainter(self)
            painter.fillRect(self.rect(),self.palette().base())
            r = self.rect().adjusted(55,15,-20,-35)
            painter.setPen(self.palette().text().color())
            painter.drawLine(r.bottomLeft(),r.bottomRight())
            painter.drawLine(r.bottomLeft(),r.topLeft())
            painter.drawText(5,18,self.unit)
            painter.drawText(55,self.height()-8,self.axis_label)
            try:
                points = [(float(x),float(y)) for x,y in self.points]
                if not points or any(not math.isfinite(x) or not math.isfinite(y) for x,y in points):
                    return
                xmin,xmax = min(x for x,y in points),max(x for x,y in points)
                ymin,ymax = min(y for x,y in points),max(y for x,y in points)
                if xmax==xmin: xmax=xmin+1
                if ymax==ymin: ymax=ymin+1
                painter.drawText(2,r.top()+12,format(ymax,'.5g'))
                painter.drawText(2,r.bottom(),format(ymin,'.5g'))
                painter.drawText(r.left(),r.bottom()+16,format(xmin,'.5g'))
                painter.drawText(r.right()-45,r.bottom()+16,format(xmax,'.5g'))
                pen = G.QPen(self.palette().highlight().color()); pen.setWidthF(2.)
                painter.setPen(pen)
                xy = [C.QPointF(r.left()+(x-xmin)*r.width()/(xmax-xmin),
                      r.bottom()-(y-ymin)*r.height()/(ymax-ymin)) for x,y in points]
                for a,b in zip(xy,xy[1:]): painter.drawLine(a,b)
                for p in xy: painter.drawEllipse(p,3.,3.)
            except (ValueError,TypeError):
                pass

    class Page(W.QWidget):
        keys = ('label','duration','initial','minimum','maximum','increments','output_frequency')
        def __init__(self):
            super().__init__()
            self.info, self.buffer, self.loading, self.modified = None,None,False,False
            self.loaded_analysis = None
            layout = W.QVBoxLayout(self)
            row = W.QHBoxLayout()
            self.procedure = W.QComboBox()
            self.procedure.addItem('정적 하중 단계','static')
            self.procedure.addItem('암시적 동적 해석','dynamic')
            self.procedure.currentIndexChanged.connect(self.procedure_changed)
            row.addWidget(self.procedure,1)
            panel._button('단계 추가',self.add,row)
            panel._button('단계 삭제',self.remove,row)
            layout.addLayout(row)
            self.steps = W.QTableWidget(0,7)
            self.steps.setObjectName('contactSteps')
            self.steps.setHorizontalHeaderLabels(['단계','길이','초기 증분','최소 증분','최대 증분','최대 횟수','출력 간격'])
            self.steps.setSelectionBehavior(W.QAbstractItemView.SelectionBehavior.SelectRows)
            self.steps.setSelectionMode(W.QAbstractItemView.SelectionMode.SingleSelection)
            self.steps.horizontalHeader().setStretchLastSection(True)
            self.steps.itemChanged.connect(self.step_changed)
            self.steps.itemSelectionChanged.connect(self.select_step)
            self.steps.setMaximumHeight(190)
            layout.addWidget(self.steps)
            self.condition = W.QComboBox()
            self.condition.setObjectName('contactStepCondition')
            self.condition.currentIndexChanged.connect(self.select_curve)
            layout.addWidget(self.condition)
            self.mode = W.QComboBox()
            for label,value in [('곡선 지정','curve'),('이전 단계 끝값 유지','hold'),('조건 해제','release')]:
                self.mode.addItem(label,value)
            self.mode.currentIndexChanged.connect(self.mode_changed)
            layout.addWidget(self.mode)
            split = W.QSplitter(C.Qt.Orientation.Horizontal)
            left = W.QWidget(); column = W.QVBoxLayout(left)
            self.points = W.QTableWidget(0,2)
            self.points.setObjectName('contactCurvePoints')
            self.points.horizontalHeader().setStretchLastSection(True)
            self.points.itemChanged.connect(self.points_changed)
            column.addWidget(self.points,1)
            buttons = W.QHBoxLayout()
            panel._button('점 추가',self.add_point,buttons)
            panel._button('점 삭제',self.remove_point,buttons)
            column.addLayout(buttons)
            split.addWidget(left)
            self.plot = Plot(); split.addWidget(self.plot); split.setSizes([230,400])
            layout.addWidget(split,1)
            actions = W.QHBoxLayout()
            panel._button('단계 적용',self.apply,actions,name='contactStepsApply')
            panel._button('수정 취소',self.discard,actions,mutate=False)
            self.state = W.QLabel()
            actions.addWidget(self.state,1)
            layout.addLayout(actions)
            panel.tabs.addTab(self,'해석 단계')
            panel.analysis.currentIndexChanged.connect(lambda *_: self.refresh(load_forms=True))
        def mark(self):
            if not self.loading:
                self.modified=True; panel._edited(); self.state.setText('미적용')
        def refresh(self, *, load_forms):
            aid=panel.analysis.currentData()
            if not aid or self.modified:
                return
            if not load_forms and aid==self.loaded_analysis:
                return
            try:
                self.info=panel.editor.contact.step_inputs(panel.editor.owner._object(aid))
                self.loaded_analysis=aid
                self.buffer=deepcopy(self.info['draft'])
                self.populate()
            except Exception as error:
                self.state.setText(str(error))
        def populate(self):
            self.loading=True
            try:
                index=self.procedure.findData(self.buffer.get('procedure'))
                if index<0:
                    self.procedure.addItem('미지원 해석',self.buffer.get('procedure')); index=self.procedure.count()-1
                self.procedure.setCurrentIndex(index)
                self.steps.setRowCount(len(self.buffer['steps']))
                for i,row in enumerate(self.buffer['steps']):
                    for j,key in enumerate(self.keys):
                        self.steps.setItem(i,j,W.QTableWidgetItem(str(row.get(key,''))))
                self.steps.setColumnWidth(0,150)
                self.steps.selectRow(0)
                self.state.setText('적용됨' if self.info.get('applied') else '새 단계 초안')
            finally:
                self.loading=False
            self.select_step()
        def current_step(self):
            i=self.steps.currentRow()
            return self.buffer['steps'][i] if self.buffer and 0<=i<len(self.buffer['steps']) else None
        def current_curve(self):
            row=self.current_step(); i=self.condition.currentData()
            return row['curves'][i] if row and type(i) is int and 0<=i<len(row['curves']) else None
        def step_changed(self,item):
            if self.loading: return
            self.buffer['steps'][item.row()][self.keys[item.column()]]=item.text()
            self.mark(); self.select_curve()
        def procedure_changed(self,*_):
            if self.loading or not self.buffer: return
            self.buffer['procedure']=self.procedure.currentData()
            self.mark(); self.select_curve()
        def select_step(self):
            if self.loading: return
            self.condition.blockSignals(True); self.condition.clear()
            row=self.current_step()
            names={c['object_id']:c['label'] for c in (self.info or {}).get('conditions',[])}
            if row:
                for i,c in enumerate(row['curves']):
                    suffix='하중' if c.get('component')==0 else '변위 '+'XYZ'[int(c['component'])-1] if c.get('component') in (1,2,3) else '성분 확인'
                    self.condition.addItem(names.get(c.get('condition_id'),'누락된 조건')+' / '+suffix+' ['+str(c.get('unit',''))+']',i)
            self.condition.blockSignals(False); self.select_curve()
        def mode_changed(self,*_):
            if self.loading: return
            c=self.current_curve()
            if c:
                c['mode']=self.mode.currentData(); self.mark(); self.select_curve()
        def select_curve(self,*_):
            self.loading=True
            try:
                c=self.current_curve()
                mode=c.get('mode','curve') if c else 'curve'
                self.mode.setCurrentIndex(self.mode.findData(mode))
                self.points.setEnabled(bool(c) and mode=='curve')
                points=c.get('points',[]) if c and mode=='curve' else []
                self.points.setRowCount(len(points))
                unit=c.get('unit','') if c else ''
                label='단계 시간 [s]' if self.procedure.currentData()=='dynamic' else '단계 진행값 [1]'
                self.points.setHorizontalHeaderLabels([label,'조건값 ['+unit+']'])
                for i,p in enumerate(points):
                    for j,v in enumerate(p): self.points.setItem(i,j,W.QTableWidgetItem(str(v)))
                self.plot.points=deepcopy(points); self.plot.unit=unit; self.plot.axis_label=label; self.plot.update()
            finally:
                self.loading=False
        def points_changed(self,item):
            if self.loading: return
            c=self.current_curve()
            if c:
                c['points'][item.row()][item.column()]=item.text()
                self.mark(); self.plot.points=deepcopy(c['points']); self.plot.update()
        def add_point(self):
            c=self.current_curve()
            if c: c['points'].append(['','']); self.mark(); self.select_curve()
        def remove_point(self):
            c=self.current_curve(); i=self.points.currentRow()
            if c and 0<=i<len(c['points']): c['points'].pop(i); self.mark(); self.select_curve()
        def add(self):
            if self.buffer is None: return
            row=deepcopy(self.current_step() or (self.buffer['steps'][-1] if self.buffer['steps'] else self.info['step_defaults']))
            row['id']='Step'+uuid.uuid4().hex[:16]; row['label']='새 단계'
            # Carry the preceding endpoint explicitly as a constant starting curve.
            for c in row['curves']:
                v=c['points'][-1][1] if c.get('points') else ''
                c['points']=[[0,v],[row['duration'],v]]
            self.buffer['steps'].append(row); self.mark(); self.populate()
            self.steps.selectRow(len(self.buffer['steps'])-1); self.state.setText('미적용')
        def remove(self):
            i=self.steps.currentRow()
            if self.buffer and 0<=i<len(self.buffer['steps']):
                self.buffer['steps'].pop(i); self.mark(); self.populate(); self.state.setText('미적용')
        def discard(self):
            self.modified=False
            self.refresh(load_forms=True)
        def apply(self):
            if not self.buffer or panel.analysis.currentData()!=self.loaded_analysis:
                raise ValueError('편집한 해석을 다시 선택한 뒤 적용하세요')
            aid,serial=self.loaded_analysis,panel._edit_serial
            def done(result):
                if panel.analysis.currentData()==aid and panel._edit_serial==serial:
                    self.modified=False; self.info=result; self.buffer=deepcopy(result['draft']); self.populate()
                else:
                    self.state.setText('이전 초안 적용됨 / 현재 수정 유지')
            panel._send('pre.contact.steps_set',{'draft':deepcopy(self.buffer)},aid,on_done=done)
    return Page()
