"""Retained iteration diagnostics. No solver, interpolation or acceptance inference."""
from copy import deepcopy
import math
from PySide6 import QtCore as C, QtWidgets as W
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

SOURCE_STATUS = {'missing':'기록 없음', 'empty':'빈 파일', 'no_iterations':'반복 기록 없음',
    'records':'읽음', 'unsupported_scope':'미지원 물리장', 'partial_eof':'끝부분 미완성', 'corrupt':'내부 손상', 'unreadable':'읽기 불가'}
DECISION = {'converged':'수렴', 'not_converged':'미수렴', 'unrecorded':'판정 미기록'}
ATTEMPT = {'converged':'수렴 증분', 'rejected':'거절 시도', 'unconfirmed':'수렴 여부 미확인', 'conflict':'기록 대응 오류'}
METRICS = (
    ('잔차력 비율', 'cvg', 'residual_force_pct', '%'),
    ('변위 보정 비율', 'cvg', 'correction_disp_pct', '%'),
    ('최대 잔차력', 'stdout', 'residual_force', 'N'),
    ('평균력', 'stdout', 'average_force', 'N'),
    ('시간 평균력', 'stdout', 'time_average_force', 'N'),
    ('최대 증분 변위', 'stdout', 'increment_disp', 'mm'),
    ('최대 변위 보정', 'stdout', 'correction_disp', 'mm'),
    ('접촉 line search 배율', 'stdout', 'line_search_factor', '1'),
)
RAW_NAMES = {key: (name, unit) for name, src, key, unit in METRICS if src == 'stdout'}
PAGE_SIZE = 200


def metric_value(row, source, key):
    """None is missing/unusable, never a physical zero."""
    if row.get('identity_conflict'):
        return None
    data = row.get(source) or {}
    if key in data.get('sentinel_channels', []):
        return None
    value = data.get('values', {}).get(key)
    if isinstance(value, dict):
        value = value.get('value')
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


class ConvergenceView(W.QWidget):
    def __init__(self, history=None, parent=None):
        super().__init__(parent)
        self.setMinimumSize(0, 0)
        self.history, self.rows, self.key, self.offset = {}, [], None, 0
        outer = W.QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        self.status = W.QLabel()
        self.status.setWordWrap(True)
        self.status.setMinimumWidth(0)
        self.status.setSizePolicy(W.QSizePolicy.Ignored, W.QSizePolicy.Preferred)
        outer.addWidget(self.status)
        bar = W.QHBoxLayout()
        self.metric = W.QComboBox()
        self.metric.setAccessibleName('수렴 그래프의 물리량')
        for name, source, key, unit in METRICS:
            self.metric.addItem(name+' ['+unit+']', (source, key))
        bar.addWidget(self.metric, 1)
        self.log_scale = W.QCheckBox('대칭 로그')
        self.log_scale.setToolTip('실제 0은 0으로 유지합니다. 결측값은 선으로 이어 붙이지 않습니다.')
        bar.addWidget(self.log_scale)
        outer.addLayout(bar)
        self.criterion = W.QCheckBox('입력 기준 표시 (native 판정과 다름)')
        self.criterion.setToolTip('Rn/Rp 또는 Cn의 입력값입니다. 영하중·접촉·미소 잔차의 예외 및 native 내부 조정은 재판정하지 않습니다.')
        outer.addWidget(self.criterion)
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        self.figure = Figure(layout='constrained')
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumSize(0, 160)
        self.canvas.setSizePolicy(W.QSizePolicy.Ignored, W.QSizePolicy.Expanding)
        outer.addWidget(self.canvas, 3)
        self.tables = W.QTabWidget()
        self.tables.setMinimumHeight(246)
        self.ratios = W.QTableWidget(0, 5)
        self.ratios.setHorizontalHeaderLabels(['반복', '잔차력\n[%]', '보정 변위\n[%]', '접촉 요소\n[개]', 'native 판정'])
        self.raw = W.QTableWidget(0, 5)
        self.raw.setHorizontalHeaderLabels(['선택 반복의 원값', '값', '단위', '절점', 'DOF'])
        self.config = W.QTableWidget(0, 4)
        self.config.setHorizontalHeaderLabels(['선택 계산의 설정', '값', '단위', '출처'])
        self.sources = W.QTableWidget(0, 3)
        self.sources.setHorizontalHeaderLabels(['원 로그', '줄', '기록 / 진단'])
        for table in (self.ratios, self.raw, self.config, self.sources):
            table.setEditTriggers(W.QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(W.QAbstractItemView.SelectRows)
            table.setSelectionMode(W.QAbstractItemView.SingleSelection)
            table.setMinimumSize(0, 100)
            table.horizontalHeader().setStretchLastSection(True)
        self.tables.addTab(self.ratios, '반복 비율')
        self.tables.addTab(self.raw, '원값 / 위치')
        self.tables.addTab(self.config, '입력 기준')
        self.tables.addTab(self.sources, '원문')
        outer.addWidget(self.tables, 2)
        bar = W.QHBoxLayout()
        self.previous = W.QPushButton('이전 반복')
        self.next = W.QPushButton('다음 반복')
        self.page = W.QLabel()
        bar.addWidget(self.previous);bar.addWidget(self.next);bar.addWidget(self.page, 1)
        outer.addLayout(bar)
        self.metric.currentIndexChanged.connect(self.draw)
        self.log_scale.toggled.connect(self.draw)
        self.criterion.toggled.connect(self.draw)
        self.ratios.itemSelectionChanged.connect(self.show_raw)
        self.previous.clicked.connect(lambda: self.paginate(-PAGE_SIZE))
        self.next.clicked.connect(lambda: self.paginate(PAGE_SIZE))
        self.set_history(history or {})

    def set_history(self, history):
        self.history = deepcopy(history)
        self.select_attempt(self.key)
        from caelab.calculix_controls import GROUPS
        config = []
        for group, specs in GROUPS.items():
            if group == 'line_search' and not history.get('line_search_applicable', False):
                continue
            for key, symbol, caption, default, unit, _ in specs:
                row = history.get('controls', {}).get(group, {}).get(key)
                if row:
                    config.append((symbol+' '+caption, format(row['value'],'.12g'), unit,
                        '입력' if row['source']=='input' else 'solver 기본값'))
        config.append(('정적 안정화 에너지', '미지원', '—', 'CalculiX 2.22 STATIC'))
        self.fill(self.config, config)

    @staticmethod
    def fill(table, rows):
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = W.QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                table.setItem(i, j, item)
        table.resizeColumnsToContents()
        # Keep the table usable in a narrow task window: long names remain in
        # tooltips and can be scrolled, not an enforced dialog minimum width.
        for j in range(table.columnCount()):
            table.setColumnWidth(j, min(table.columnWidth(j), 230))

    def select_attempt(self, key):
        self.key = tuple(key) if key is not None else None
        self.rows = [r for r in self.history.get('rows', [])
                     if (r['step'], r['increment'], r['attempt']) == self.key]
        self.offset = max(0, ((len(self.rows)-1)//PAGE_SIZE)*PAGE_SIZE)
        self.refresh_table()
        sources = self.history.get('sources', {})
        text = ' / '.join(label+': '+SOURCE_STATUS.get(sources.get(key,{}).get('status','missing'),'상태 미확인')
                           for key, label in (('cvg','CVG'),('stdout','stdout')))
        attempt_status = ATTEMPT.get(self.rows[0]['attempt_status'], '') if self.rows else '선택 시도의 반복 기록 없음'
        unresolved = sum(r.get('step') is None for r in sources.get('stdout', {}).get('rows', []))
        if unresolved:
            text += f' / 단계 대응 불가 {unresolved}행 (그래프 제외)'
        self.status.setText(attempt_status+' — '+text)
        self.draw()

    def paginate(self, delta):
        self.offset = max(0, min(self.offset+delta, max(0,len(self.rows)-1)//PAGE_SIZE*PAGE_SIZE))
        self.refresh_table()

    def refresh_table(self):
        values=[]
        for row in self.rows[self.offset:self.offset+PAGE_SIZE]:
            cvg = row.get('cvg') or {}
            def value(key):
                if key in cvg.get('sentinel_channels', []):
                    return '분모 극소 표식'
                v = metric_value(row,'cvg',key)
                return format(v,'.8g') if v is not None else '미기록'
            decision = DECISION.get(row['iteration_status'], '판정 미기록')
            if row.get('identity_conflict'):
                decision = '기록 대응 오류'
            elif row.get('stdout', {}).get('record_status') not in (None,'complete'):
                decision += ' / 부분 기록'
            values.append((row['iteration'], value('residual_force_pct'), value('correction_disp_pct'),
                           cvg.get('contact_elements','미기록'), decision))
        self.fill(self.ratios, values)
        self.previous.setEnabled(self.offset>0)
        self.next.setEnabled(self.offset+PAGE_SIZE<len(self.rows))
        self.page.setText(f'{self.offset+1}–{min(self.offset+PAGE_SIZE,len(self.rows))} / {len(self.rows)}' if self.rows else '0행')
        if values:
            self.ratios.selectRow(len(values)-1)
        else:
            self.show_raw()

    def show_raw(self):
        i = self.ratios.currentRow()+self.offset
        row = self.rows[i] if 0 <= i < len(self.rows) else {}
        raw = row.get('stdout') or {}
        values=[]
        for key, (caption, unit) in RAW_NAMES.items():
            item = raw.get('values', {}).get(key)
            values.append((caption, item['token'] if item else '미기록', unit,
                           item.get('node') or '—' if item else '—', item.get('dof') or '—' if item else '—'))
        self.fill(self.raw, values)
        source=[]
        if row.get('cvg'):
            r=row['cvg'];source.append(('CVG',r['line'],r['raw']))
        for value in raw.get('values', {}).values():
            source.append(('stdout',value['line'],value['raw']))
        if raw.get('decision_line'):
            source.append(('stdout',raw['decision_line'],raw['decision_raw']))
        for name, info in self.history.get('sources', {}).items():
            for diagnostic in info.get('diagnostics', []):
                source.append((name, diagnostic.get('line','—'), diagnostic['message']))
            # Unmatched raw rows are inspectable but never attributed to a step.
            for r in info.get('rows', []):
                if r.get('identity_status') == 'unresolved_step':
                    source.append((name, r['line'], '단계 대응 불가: 증분 '+str(r['increment'])+' / 시도 '+str(r['attempt'])+' / 반복 '+str(r['iteration'])))
        self.fill(self.sources, source[:1000])

    def draw(self, *_):
        name, src, key, unit = METRICS[self.metric.currentIndex()]
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        # Include NaN at every missing recorded iteration; never bridge a hole.
        points = [(r['iteration'], metric_value(r,src,key)) for r in self.rows]
        if any(v is not None for _,v in points):
            ax.plot([x for x,_ in points], [v if v is not None else math.nan for _,v in points],
                    marker='o', markersize=4, label=name)
        else:
            ax.text(.5,.5,'기록된 값 없음',ha='center',va='center',transform=ax.transAxes)
        self.criterion.setEnabled(src == 'cvg')
        if src == 'cvg' and self.criterion.isChecked() and points:
            try:
                controls=self.history['controls'];field=controls['field']
                ip=controls['iterations']['ip']['value']
                reference=[100*field['can']['value'] if key=='correction_disp_pct' else
                           100*field['ran' if x<=ip else 'rap']['value'] for x,_ in points]
                ax.plot([x for x,_ in points],reference,linestyle='--',label='입력 기준 (판정 아님)')
                ax.legend(fontsize='small')
            except KeyError:
                pass
        ax.set_xlabel('반복 [회]')
        ax.set_ylabel(name+' ['+unit+']')
        ax.xaxis.set_major_locator(MaxNLocator(integer=True,nbins=5))
        if self.log_scale.isChecked():
            ax.set_yscale('symlog',linthresh=1e-6)
        else:
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
        ax.grid(alpha=.2)
        self.canvas.draw_idle()
