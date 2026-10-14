"""Retained native motion samples, CSV/Data handoff and injected Qt drawing."""
from copy import deepcopy
import csv
import io
import json
import math
from importlib import import_module
from urllib.parse import quote
from .motion import NATIVE_CLOCK


def sample_time(path,row):
    return row.get('time') if path.get('clock')==NATIVE_CLOCK else row['nominal_time']


def time_label(path):
    return '계산 시각 [s]' if (path or {}).get('clock')==NATIVE_CLOCK else '출력격자 시간 [s]'


def clock_notice(path):
    if path.get('clock')==NATIVE_CLOCK and not path.get('clock_source',{}).get('complete',True):
        return '계산 시각 미확인: '+str(path.get('clock_source',{}).get('reason','native 출력 시각을 확인할 수 없습니다.'))+' 원좌표는 보존됩니다.'
    return ('운동 계산의 출력 시각입니다. 설계 자세에는 물리 시각이 없습니다. 끝 출력 시각은 설정 끝과 다를 수 있습니다.'
        if path.get('clock')==NATIVE_CLOCK else '시간은 설정한 출력 간격으로 환산한 기존 기록이며 실제 계산 시각 기록이 아닙니다.')


def merge_path(previous, page):
    """Join bounded pages only within the same native calculation and trace."""
    result = deepcopy(page)
    same = previous and (previous['calculation_id'], previous['trace_id']) == (page['calculation_id'], page['trace_id'])
    if same and previous['total_frames'] != page['total_frames']: raise ValueError('같은 계산의 프레임 범위가 바뀌었습니다. 이전 자료는 남아 있습니다.')
    if same and previous.get('clock')!=page.get('clock'): raise ValueError('같은 계산의 시각 기록 방식이 바뀌었습니다. 이전 자료는 남아 있습니다.')
    rows = {row['frame']: deepcopy(row) for row in previous['rows']} if same else {}
    for row in page['rows']:
        if type(row['frame']) is not int or not 0 <= row['frame'] < page['total_frames']:
            raise ValueError('경로의 프레임 번호가 계산 범위를 벗어났습니다.')
        time=sample_time(page,row)
        design=page.get('clock')==NATIVE_CLOCK and ((row.get('frame_kind')=='design' and row['frame']==0)
            or (row.get('frame_kind')=='unknown' and page.get('clock_source',{}).get('complete') is False))
        if page.get('clock')==NATIVE_CLOCK and (row.get('frame_kind') not in ('design','simulation','unknown')
                or (row.get('frame_kind')=='design' and (row['frame']!=0 or time is not None))):
            raise ValueError('설계 자세와 계산 출력의 시각 종류를 확인할 수 없습니다. 이전 자료는 남아 있습니다.')
        if (len(row['point']) != 3 or not all(type(v) in (int, float) and math.isfinite(v) for v in row['point'])
                or (time is None and not design) or (time is not None and (type(time) not in (int,float) or not math.isfinite(time)))):
            raise ValueError('경로의 시간 또는 좌표가 유효하지 않습니다. 이전 자료는 남아 있습니다.')
        rows[row['frame']] = deepcopy(row)
    result['rows'] = [rows[index] for index in sorted(rows)]
    result['complete'] = len(rows) == page['total_frames']
    return result


def _csv_records(path):
    records, gaps, untimed = [], [], []
    previous = None
    for sample in path['rows']:
        if previous is not None and sample['frame'] > previous+1:
            gaps.append({'csv_row': len(records)+2, 'after_frame': previous, 'before_frame': sample['frame'],
                'unread_frames': [previous+1, sample['frame']-1]})
            records.append(['nan']*5)
        time=sample_time(path,sample)
        if time is None: untimed.append({'csv_row':len(records)+2,'frame':sample['frame'],'kind':sample.get('frame_kind')})
        records.append([sample['frame'], 'nan' if time is None else time, *sample['point']])
        previous = sample['frame']
    return records, gaps, untimed


def csv_payload(path):
    if not path.get('rows'): raise ValueError('먼저 계산된 경로를 읽으세요.')
    records, gaps, untimed = _csv_records(path)
    stream = io.StringIO(newline='')
    source = {key: deepcopy(value) for key, value in path.items() if key != 'rows'}
    source['sampled_frames'] = [row['frame'] for row in path['rows']]
    if gaps: source.update(gap_markers=gaps, csv_row_kind='physical_line_zero_based')
    if untimed: source.update(non_time_frames=untimed, csv_row_kind='physical_line_zero_based')
    # The existing Data preview refuses quotes even in comments. Keep the
    # lossless source JSON URL-encoded so the ordinary numeric preview works.
    stream.write('# motion_source_json_urlencoded=' + quote(json.dumps(source, ensure_ascii=False, separators=(',', ':'), allow_nan=False), safe='') + '\n')
    writer = csv.writer(stream)
    writer.writerow(['native_frame', 'time_s' if path.get('clock')==NATIVE_CLOCK else 'nominal_time_s', 'world_x_mm', 'world_y_mm', 'world_z_mm'])
    writer.writerows(records)
    return stream.getvalue().encode('utf-8')


def data_draft(path, data_id):
    _, gaps, untimed = _csv_records(path)
    columns = {}
    for name, column, unit, component, measure in [('X', 2, 'mm', 'x', 'position'),
            ('Y', 3, 'mm', 'y', 'position'), ('Z', 4, 'mm', 'z', 'position'),
            ('프레임', 0, '1', 'frame_index', 'native_frame_index')]:
        columns[name] = {'column': column, 'unit': unit, 'component': component,
            'location': 'trace_point:' + path['trace_id'], 'measure': measure, 'frame': 'document_global',
            'axis': {'column': 1, 'name': 'time' if path.get('clock')==NATIVE_CLOCK else 'nominal_time', 'unit': 's'}}
        if gaps or untimed:
            reasons = {str(gap['csv_row']): '미읽기 경로 구간: 프레임 ' + str(gap['unread_frames'][0])
                + '–' + str(gap['unread_frames'][1]) + ' / 좌표·시간 측정 없음' for gap in gaps}
            reasons.update({str(row['csv_row']):'설계 자세: 좌표는 보존되며 물리 시각은 없습니다.' if row['kind']=='design'
                else '계산 시각 미확인: 원좌표는 보존되며 시간 분석에서 제외합니다.' for row in untimed})
            columns[name]['row_selection'] = {'exclude_rows': [int(row) for row in reasons],
                'quality_rows': [int(row) for row in reasons], 'reasons': reasons, 'quality_reasons': deepcopy(reasons)}
    return {'data_id': data_id, 'mapping': {'delimiter': ',', 'skip_header': 2, 'columns': columns},
        'test_metadata': {'protocol': '조립 운동학 경로. '+clock_notice(path)+' '
            + f"읽은 프레임 {len(path['rows'])}/{path['total_frames']}. 원 프레임과 출처는 CSV에 보존됩니다."}}


def save_data_document(client, path, *, document=None, on_created=None):
    """Save the uploaded source with the ordinary Data owner; retry keeps its ID."""
    if document is None:
        receipt = client.upload('motion-path.csv', csv_payload(path))
        document = client.document_open(kind='data', title='조립 경로 ' + path['trace_id'],
            draft=data_draft(path, receipt.get('data_id', receipt.get('id'))))
    if on_created is not None: on_created(document)
    document = client.document_read(document['id'])
    return client.document_command(document['id'], 'document.save', {},
        session_id=document['session_id'], expected_generation=document['generation'])['document']


def make_plot(QtCore, Q):
    Gui = import_module(QtCore.__name__.rsplit('.', 1)[0] + '.QtGui')
    class Plot(Q.QWidget):
        selected = QtCore.Signal(int)
        def __init__(self):
            super().__init__(); self.rows = []; self.path = {}; self.mode = 'time'; self.index = -1; self.points = []
            self.setMinimumHeight(230); self.setMouseTracking(True)
            self.setAccessibleName('점 경로 곡선. 곡선의 점을 누르면 같은 프레임 행을 선택합니다.')
        def paintEvent(self, event):
            painter = Gui.QPainter(self); painter.setRenderHint(Gui.QPainter.Antialiasing)
            painter.fillRect(self.rect(), Gui.QColor('white'))
            area = QtCore.QRectF(72, 35, max(1, self.width()-94), max(1, self.height()-82))
            painter.setPen(Gui.QColor('#b8c2cd')); painter.drawRect(area)
            self.points = []
            if not self.rows:
                painter.setPen(Gui.QColor('#536373')); painter.drawText(area, QtCore.Qt.AlignCenter, '경로를 읽으면 곡선이 표시됩니다.'); return
            if self.mode == 'time':
                series = [[(i,sample_time(self.path,r),r['point'][axis]) for i,r in enumerate(self.rows)
                    if sample_time(self.path,r) is not None] for axis in range(3)]
                xlabel, ylabel = time_label(self.path), '세계 좌표 [mm]'
            else:
                a, b = {'xy': (0, 1), 'xz': (0, 2), 'yz': (1, 2)}[self.mode]
                series = [[(i,r['point'][a],r['point'][b]) for i,r in enumerate(self.rows)]]
                xlabel, ylabel = '세계 ' + 'xyz'[a] + ' [mm]', '세계 ' + 'xyz'[b] + ' [mm]'
            xs = [p[1] for line in series for p in line]; ys = [p[2] for line in series for p in line]
            if not xs:
                painter.drawText(area,QtCore.Qt.AlignCenter,'물리 시각이 없는 자세입니다. 표 또는 공간 경로에서 확인하세요.'); return
            xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
            if xmin == xmax: xmin -= .5; xmax += .5
            if ymin == ymax: ymin -= .5; ymax += .5
            if self.mode != 'time':
                ratio = area.width()/area.height(); width = xmax-xmin; height = ymax-ymin
                if width/height > ratio:
                    middle = (ymin+ymax)/2; ymin, ymax = middle-width/ratio/2, middle+width/ratio/2
                else:
                    middle = (xmin+xmax)/2; xmin, xmax = middle-height*ratio/2, middle+height*ratio/2
            painter.setPen(Gui.QColor('#3d4d5e'))
            painter.drawText(8, 23, ylabel)
            painter.drawText(int(area.left()), self.height()-8, xlabel)
            painter.drawText(int(area.left()), int(area.bottom()+18), f'{xmin:.5g}')
            painter.drawText(int(area.right()-60), int(area.bottom()+18), f'{xmax:.5g}')
            painter.drawText(4, int(area.top()+5), f'{ymax:.5g}')
            painter.drawText(4, int(area.bottom()), f'{ymin:.5g}')
            for axis, line in enumerate(series):
                color = ['#246aa4', '#22805c', '#ba5736'][axis]
                painter.setPen(Gui.QPen(Gui.QColor(color), 1.8))
                previous = None
                for index, x, y in line:
                    point = QtCore.QPointF(area.left()+(x-xmin)/(xmax-xmin)*area.width(), area.bottom()-(y-ymin)/(ymax-ymin)*area.height())
                    if (previous is not None and self.rows[index]['frame'] == self.rows[prior_index]['frame']+1
                            and self.rows[prior_index].get('frame_kind')!='design'): painter.drawLine(previous, point)
                    painter.drawEllipse(point, 2, 2); self.points.append((index, point))
                    if index == self.index:
                        painter.setBrush(Gui.QColor(color)); painter.drawEllipse(point, 5, 5); painter.setBrush(QtCore.Qt.NoBrush)
                    previous = point; prior_index=index
                if self.mode == 'time': painter.drawText(int(area.right()-135+45*axis), 23, 'xyz'[axis])
        def mousePressEvent(self, event):
            if self.points:
                pos = event.position() if hasattr(event, 'position') else event.localPos()
                index, point = min(self.points, key=lambda item: (item[1].x()-pos.x())**2+(item[1].y()-pos.y())**2)
                self.selected.emit(index)
    return Plot()


class PathBrowser:
    def __init__(self, QtCore, Q, layout, show_pose, open_data):
        self.Q = Q; self.QtCore = QtCore; self.open_data = open_data; self.show_pose = show_pose
        self.datasets = {}; self.live_id = None; self.path_value = None; self._loading = False
        self._handoffs = {}; self._handoff_busy = False
        row = Q.QHBoxLayout(); self.results = Q.QComboBox(); row.addWidget(Q.QLabel('읽은 경로')); row.addWidget(self.results, 1)
        self.mode = Q.QComboBox()
        for label, key in [('시간–X/Y/Z', 'time'), ('공간 경로 X–Y', 'xy'), ('공간 경로 X–Z', 'xz'), ('공간 경로 Y–Z', 'yz')]: self.mode.addItem(label, key)
        row.addWidget(self.mode); layout.addLayout(row)
        self.notice = Q.QLabel('경로점과 계산 결과를 선택하여 경로를 읽으세요.'); self.notice.setWordWrap(True); layout.addWidget(self.notice)
        self.plot = make_plot(QtCore, Q); layout.addWidget(self.plot)
        self.table = Q.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['프레임', '출력격자 시간 [s]', '세계 X [mm]', '세계 Y [mm]', '세계 Z [mm]'])
        self.table.setEditTriggers(Q.QAbstractItemView.NoEditTriggers); self.table.setSelectionBehavior(Q.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(Q.QAbstractItemView.SingleSelection); self.table.setMinimumHeight(190)
        self.table.verticalHeader().hide()
        for column, width in enumerate((65, 160, 125, 125, 125)): self.table.setColumnWidth(column, width)
        self.table.horizontalHeader().setStretchLastSection(True); self.table.setAlternatingRowColors(True); layout.addWidget(self.table)
        self.message = Q.QLabel(); self.message.setWordWrap(True); self.message.hide(); layout.addWidget(self.message)
        row = Q.QHBoxLayout(); self.pose_button = Q.QPushButton('선택 프레임의 3D 자세 보기')
        self.csv_button = Q.QPushButton('CSV 저장…'); self.data_button = Q.QPushButton('Data에서 열기')
        for button in (self.pose_button, self.csv_button, self.data_button): row.addWidget(button)
        layout.insertLayout(4, row)
        self.results.currentIndexChanged.connect(self._selected_result)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.table.currentCellChanged.connect(self._selected_row)
        self.plot.selected.connect(self.table.selectRow)
        self.pose_button.clicked.connect(self._pose); self.csv_button.clicked.connect(self._csv); self.data_button.clicked.connect(self._data)
        self._update_buttons()

    def refresh(self, summaries, live_id, *, latest=None, can_preview=True):
        self.live_id = live_id; self.can_preview = can_preview
        selected = self.results.currentData()
        if latest is not None: selected = (latest['calculation_id'], latest['trace_id'])
        datasets = {}; labels = []
        for number, summary in enumerate(summaries):
            for trace, path in summary.get('paths', {}).items():
                key = (summary['id'], trace)
                value = deepcopy(path); value['source_status'] = summary.get('source_status', 'UNKNOWN')
                datasets[key] = value
                labels.append((key, trace + (' / 현재 계산' if summary['id'] == live_id else ' / 보존 결과 '+str(number+1))))
        if datasets == self.datasets and selected == self.results.currentData() and [self.results.itemText(i) for i in range(self.results.count())] == [label for key, label in labels]:
            self._update_buttons(); return
        self.datasets = datasets
        self._loading = True
        self.results.blockSignals(True); self.results.clear()
        for key, label in labels: self.results.addItem(label, key)
        index = next((i for i in range(self.results.count()) if self.results.itemData(i) == selected), 0)
        self.results.setCurrentIndex(index)
        self.results.blockSignals(False); self._loading = False
        self._selected_result()

    def _selected_result(self, *args):
        if self._loading: return
        selected_frame = self.table.item(self.table.currentRow(), 0)
        frame = int(selected_frame.text()) if selected_frame else None
        self.path_value = self.datasets.get(self.results.currentData())
        self.table.setHorizontalHeaderItem(1,self.Q.QTableWidgetItem(time_label(self.path_value)))
        rows = (self.path_value or {}).get('rows', []); self.table.blockSignals(True); self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, value in enumerate([row['frame'], sample_time(self.path_value,row), *row['point']]):
                text = ('설계 자세' if row.get('frame_kind')=='design' else '시각 미확인') if value is None else str(value) if column == 0 else format(value, '.9g')
                if value is not None and column and '.' not in text and 'e' not in text: text += '.0'
                item = self.Q.QTableWidgetItem(text); item.setToolTip(str(value)); self.table.setItem(index, column, item)
        self.table.blockSignals(False); self.plot.rows = rows; self.plot.path=self.path_value or {}
        row = next((i for i, value in enumerate(rows) if value['frame'] == frame), 0 if rows else -1)
        self.table.setCurrentCell(row, 0); self._selected_row(row)
        if rows:
            path = self.path_value; frames = {row['frame'] for row in rows}
            missing = path['total_frames']-len(frames)
            state = '모델·구동 변경 — 과거 원자료' if path['source_status'] == 'STALE' else '출처 확인 불가 — 보존 원자료' if path['source_status'] == 'UNKNOWN' else '계산된 원자료'
            self.notice.setText(f"{state} / 읽은 프레임 {len(rows)}/{path['total_frames']}" + (f' / 미읽기·누락 {missing}' if missing else ' / 전체 경로') + '\n위치는 세계 좌표 [mm]입니다. '+clock_notice(path))
        else: self.notice.setText('아직 읽은 경로가 없습니다. 경로 읽기는 운동을 다시 계산하지 않습니다.')
        self._update_buttons()

    def _selected_row(self, row, *args):
        self.plot.index = row; self.plot.update(); self._update_buttons()

    def _mode_changed(self, *args):
        self.plot.mode = self.mode.currentData(); self.plot.update()

    def current_view(self):
        if not self.path_value or self.table.currentRow() < 0: return None
        return {'calculation_id': self.path_value['calculation_id'], 'trace_id': self.path_value['trace_id'],
            'frame': self.path_value['rows'][self.table.currentRow()]['frame'], 'projection': self.mode.currentData()}

    def restore_view(self, view):
        key = (view['calculation_id'], view['trace_id'])
        index = next((i for i in range(self.results.count()) if self.results.itemData(i) == key), -1)
        if index < 0: return
        self.results.setCurrentIndex(index); self.mode.setCurrentIndex(self.mode.findData(view['projection']))
        row = next((i for i, sample in enumerate(self.path_value['rows']) if sample['frame'] == view['frame']), -1)
        if row >= 0: self.table.setCurrentCell(row, 0)

    def _update_buttons(self):
        path = self.path_value or {}; ready = bool(path.get('rows'))
        self.csv_button.setEnabled(ready)
        self.data_button.setEnabled(ready and self.open_data is not None and not self._handoff_busy)
        self.pose_button.setEnabled(ready and self.table.currentRow() >= 0 and path.get('calculation_id') == self.live_id and getattr(self, 'can_preview', True) and path.get('source_status') == 'CURRENT')
        self.pose_button.setToolTip('보존 경로는 계산 없이 읽습니다. 3D 자세는 현재 문서에 같은 계산 프레임이 남아 있을 때만 볼 수 있습니다.')

    def _pose(self):
        if self.pose_button.isEnabled(): self.show_pose(self.path_value['calculation_id'], self.path_value['rows'][self.table.currentRow()]['frame'])

    def _csv(self):
        path, _ = self.Q.QFileDialog.getSaveFileName(self.table, '읽은 경로 CSV 저장', 'motion-path.csv', 'CSV (*.csv)')
        if not path: return
        try:
            payload = csv_payload(self.path_value); output = self.QtCore.QSaveFile(path)
            if not output.open(self.QtCore.QIODevice.WriteOnly): raise OSError(output.errorString())
            if output.write(payload) != len(payload):
                output.cancelWriting(); raise OSError(output.errorString())
            if not output.commit(): raise OSError(output.errorString())
            self._message('읽은 경로와 원 프레임·출처를 CSV에 저장했습니다.\n' + path)
        except Exception as error: self._message('CSV 저장 실패: ' + str(error))

    def _message(self, text):
        self.message.setText(text); self.message.setVisible(bool(text))

    def _data(self):
        if not self.data_button.isEnabled(): return
        snapshot = deepcopy(self.path_value); key = json.dumps(snapshot, sort_keys=True)
        self._handoff_busy = True; self._update_buttons()
        def done(reply):
            self._handoff_busy = False; self._update_buttons()
            if reply.get('document'): self._handoffs[key] = reply['document']
            if self.path_value != snapshot: return
            if reply.get('error'): self._message('Data 열기 실패: ' + str(reply['error']) + '\n원 경로는 남아 있습니다. Data에서 열기를 다시 누르세요.')
            else: self._message('경로 원본과 열 설정을 저장했습니다. Data 창에서 가져오기와 분석을 이어가세요.')
        try: self.open_data(snapshot, done, self._handoffs.get(key))
        except Exception as error: done({'error': str(error)})
