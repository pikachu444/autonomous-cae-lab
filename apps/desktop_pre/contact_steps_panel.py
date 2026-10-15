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
            metrics = painter.fontMetrics()
            line = metrics.height()
            try:
                points = [(float(x),float(y)) for x,y in self.points]
                if any(not math.isfinite(x) or not math.isfinite(y) for x,y in points):
                    points = []
            except (ValueError,TypeError):
                points = []
            left = 55
            if points:
                xmin,xmax = min(x for x,y in points),max(x for x,y in points)
                ymin,ymax = min(y for x,y in points),max(y for x,y in points)
                if xmax==xmin: xmax=xmin+1
                if ymax==ymin: ymax=ymin+1
                ytop,ybottom = format(ymax,'.5g'),format(ymin,'.5g')
                left = max(55,metrics.horizontalAdvance(ytop)+16,metrics.horizontalAdvance(ybottom)+16)
            # Font-sized margins keep scientific notation and units apart at desktop scaling.
            r = self.rect().adjusted(left,line+12,-20,-(2*line+18))
            painter.setPen(self.palette().text().color())
            painter.drawLine(r.bottomLeft(),r.bottomRight())
            painter.drawLine(r.bottomLeft(),r.topLeft())
            painter.drawText(8,metrics.ascent()+4,self.unit)
            painter.drawText(r.left(),self.height()-5,self.axis_label)
            if points:
                painter.drawText(r.left()-8-metrics.horizontalAdvance(ytop),r.top()+metrics.ascent(),ytop)
                painter.drawText(r.left()-8-metrics.horizontalAdvance(ybottom),r.bottom(),ybottom)
                painter.drawText(r.left(),r.bottom()+line+2,format(xmin,'.5g'))
                xtop = format(xmax,'.5g')
                painter.drawText(r.right()-metrics.horizontalAdvance(xtop),r.bottom()+line+2,xtop)
                pen = G.QPen(self.palette().highlight().color()); pen.setWidthF(2.)
                painter.setPen(pen)
                xy = [C.QPointF(r.left()+(x-xmin)*r.width()/(xmax-xmin),
                      r.bottom()-(y-ymin)*r.height()/(ymax-ymin)) for x,y in points]
                for a,b in zip(xy,xy[1:]): painter.drawLine(a,b)
                for p in xy: painter.drawEllipse(p,3.,3.)

    class Page(W.QWidget):
        keys = ('label','duration','initial','minimum','maximum','increments','output_frequency')
        def __init__(self):
            super().__init__()
            self.info, self.buffer, self.loading, self.modified = None,None,False,False
            self.loaded_analysis = None
            self.pending_request = None
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
            self.state_control = W.QCheckBox('단계별 접촉쌍 활성 상태를 명시')
            self.state_control.setObjectName('contactStateControl')
            self.state_control.toggled.connect(self.enable_states)
            layout.addWidget(self.state_control)
            self.pair_states = W.QTableWidget(0, 2)
            self.pair_states.setObjectName('contactStepPairStates')
            self.pair_states.setHorizontalHeaderLabels(['접촉쌍', '선택 단계의 상태'])
            self.pair_states.horizontalHeader().setStretchLastSection(True)
            self.pair_states.setMaximumHeight(150)
            layout.addWidget(self.pair_states)
            note = W.QLabel('비활성은 접촉쌍 계산에서 제외하는 입력 상태입니다. 실제 벌어짐/접촉 상태가 아닙니다. '
                            '묶음 해제는 초안만 저장되며 *TIE 실행은 차단됩니다.')
            note.setWordWrap(True)
            layout.addWidget(note)
            self.condition = W.QComboBox()
            self.condition.setObjectName('contactStepCondition')
            self.condition.currentIndexChanged.connect(self.select_curve)
            self.condition.setSizeAdjustPolicy(W.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            self.condition.setMinimumContentsLength(12)
            condition_row = W.QHBoxLayout()
            condition_row.addWidget(self.condition,1)
            panel._button('조건 새로 읽기',self.reconcile,condition_row,name='contactStepsReconcile')
            layout.addLayout(condition_row)
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
            panel._button('미확인 요청 재시도',self.retry,actions,name='contactStepsRetry')
            self.state = W.QLabel()
            self.state.setWordWrap(True)
            self.state.setMinimumWidth(0)
            self.state.setSizePolicy(W.QSizePolicy.Policy.Ignored,W.QSizePolicy.Policy.Preferred)
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
                self.state_control.setChecked(any('contact_states' in x for x in self.buffer['steps']))
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
            self.condition.blockSignals(False); self.select_curve(); self.show_states()
        def enable_states(self, enabled):
            if self.loading or self.buffer is None:
                return
            if not enabled:
                yes = W.QMessageBox.StandardButton.Yes
                if W.QMessageBox.question(self, '활성 상태 표 해제',
                        '모든 단계의 접촉쌍 상태 표를 없애고 기존 전체 활성 방식으로 돌아갑니다. 계속할까요?',
                        yes | W.QMessageBox.StandardButton.Cancel, W.QMessageBox.StandardButton.Cancel) != yes:
                    self.state_control.blockSignals(True); self.state_control.setChecked(True); self.state_control.blockSignals(False)
                    return
            pairs = (self.info or {}).get('contact_pairs', [])
            for row in self.buffer['steps']:
                if enabled:
                    row.setdefault('contact_states', [{'pair_id': p['pair_id'], 'state': 'active'} for p in pairs])
                else:
                    row.pop('contact_states', None)
            self.mark(); self.show_states()
        def show_states(self):
            step = self.current_step()
            rows = step.get('contact_states', []) if step else []
            names = {p['pair_id']: p for p in (self.info or {}).get('contact_pairs', [])}
            self.pair_states.setRowCount(len(rows))
            self.pair_states.setEnabled(bool(step) and self.state_control.isChecked())
            for i, row in enumerate(rows):
                pair = names.get(row.get('pair_id'), {})
                name = pair.get('label', '삭제되거나 다시 연결할 접촉쌍')
                if pair.get('normal_law') == 'tie':
                    name += ' / 묶음'
                item = W.QTableWidgetItem(name)
                item.setFlags(item.flags() & ~C.Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(str(row.get('pair_id')))
                self.pair_states.setItem(i, 0, item)
                combo = W.QComboBox()
                for text, value in [('활성', 'active'), ('비활성', 'inactive'), ('묶음 해제 — 실행 미지원', 'released')]:
                    combo.addItem(text, value)
                index = combo.findData(row.get('state'))
                if index < 0:
                    combo.addItem('원래 값 — 수정 필요', row.get('state')); index = combo.count()-1
                combo.setCurrentIndex(index)
                combo.currentIndexChanged.connect(lambda _, r=row, w=combo: self.change_state(r, w.currentData()))
                self.pair_states.setCellWidget(i, 1, combo)
        def change_state(self, row, state):
            if not self.loading:
                row['state'] = state; self.mark()
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
        def reconcile(self):
            if self.buffer is None or panel.analysis.currentData()!=self.loaded_analysis:
                self.state.setText('편집한 해석을 다시 선택하세요')
                return
            from caelab.contact_steps import reconcile_program
            selected_step=self.current_step()
            selected_id=selected_step.get('id') if selected_step else None
            selected_curve=self.current_curve()
            key=(selected_curve.get('condition_id'),selected_curve.get('component'),selected_curve.get('unit')) if selected_curve else None
            try:
                info=panel.editor.contact.step_inputs(panel.editor.owner._object(self.loaded_analysis))
                updated=reconcile_program(self.buffer,info['conditions'])
                names={r['object_id']:r['label'] for r in self.info.get('conditions',[])}
                names.update({r['object_id']:r['label'] for r in info['conditions']})
                differences=[]
                for before,after in zip(self.buffer['steps'],updated['steps']):
                    old={(c.get('condition_id'),c.get('component'),c.get('unit')) for c in before['curves']}
                    new={(c.get('condition_id'),c.get('component'),c.get('unit')) for c in after['curves']}
                    for action,keys in (('추가',new-old),('정리',old-new)):
                        for cid,component,unit in sorted(keys,key=str):
                            physical='하중' if component==0 else '변위 '+'XYZ'[component-1] if component in (1,2,3) else '성분'
                            differences.append(str(before.get('label','단계'))+' / '+action+': '+names.get(cid,'삭제된 조건')+' '+physical+' ['+str(unit)+']')
                if differences:
                    message='\n'.join(differences)+'\n\n같은 조건의 곡선과 미완성 입력은 유지합니다. 현재 초안에 반영할까요?'
                    yes=W.QMessageBox.StandardButton.Yes
                    if W.QMessageBox.question(self,'조건 변경',message,yes|W.QMessageBox.StandardButton.Cancel,W.QMessageBox.StandardButton.Cancel)!=yes:
                        return
            except (ValueError,TypeError,KeyError) as error:
                self.state.setText(str(error))
                return
            self.info=info; self.buffer=updated; self.populate()
            for index,step in enumerate(updated['steps']):
                if step.get('id')==selected_id:
                    self.steps.selectRow(index)
                    break
            for index,row in enumerate((self.current_step() or {}).get('curves',[])):
                if (row.get('condition_id'),row.get('component'),row.get('unit'))==key:
                    self.condition.setCurrentIndex(index)
                    break
            self.mark()
            self.state.setText('현재 조건을 읽었습니다 / 미적용')
        def discard(self):
            self.modified=False
            self.refresh(load_forms=True)
        def apply(self):
            if self.pending_request:
                self.state.setText('이전 미확인 요청을 먼저 재시도하세요. 현재 수정은 유지됩니다.')
                return
            if not self.buffer or panel.analysis.currentData()!=self.loaded_analysis:
                raise ValueError('편집한 해석을 다시 선택한 뒤 적용하세요')
            self.pending_request = (self.loaded_analysis, {'draft': deepcopy(self.buffer),
                'expected_revision': self.info['revision'], 'request_id': uuid.uuid4().hex})
            self.retry()
        def retry(self):
            if not self.pending_request:
                raise ValueError('미확인 요청이 없습니다.')
            aid, args = self.pending_request
            if panel.analysis.currentData() != aid:
                raise ValueError('원래 편집한 해석을 선택하세요.')
            serial = panel._edit_serial
            submitted_draft = deepcopy(args['draft'])
            def done(result):
                self.pending_request = None
                if (panel.analysis.currentData()==aid and panel._edit_serial==serial
                        and self.buffer == submitted_draft):
                    self.modified=False; self.info=result; self.buffer=deepcopy(result['draft']); self.populate()
                else:
                    self.state.setText('이전 초안 적용됨 / 현재 수정 유지. 현재 문서를 다시 읽은 뒤 이어서 적용하세요.')
            def failed(error):
                if getattr(error, 'native_terminal', False):
                    self.pending_request = None
                self.state.setText(str(error)+' / 미적용 초안 유지')
            panel._send('pre.contact.steps_set', deepcopy(args), aid, on_done=done, on_error=failed)
    return Page()
