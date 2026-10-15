"""Read retained UQ samples; selecting an interval never executes a model."""
from copy import deepcopy
import math

from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from caelab.numerical import _scalar, EvaluationFailed
from .runner_window import candidate_state
from .numerical_methods import STATE, CHOICE_LABELS


def exclusion_label(row, definition, reason):
    if row.get('prediction_status') == 'PREDICTED' or row.get('execution_status') == 'PREDICTED':
        return '예측값 제외: 실제 계산 결과를 선택하세요.'
    if 'response unit differs from the declared unit' in str(reason):
        response = row.get('responses', {}).get(definition.get('response'), {})
        return '응답 단위 불일치: 원값 ' + str(response.get('unit', '?')) + ' / 선언 ' + str(definition.get('unit', '?'))
    if row.get('execution_status') in {'FAILED', 'REJECTED'}:
        return '계산 실패: 실행 기록을 확인하세요.'
    return reason


class NumericalUQWindow(QDialog):
    def __init__(self, result, *, title='불확실성 분석', parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.result = deepcopy(result)
        self.setWindowTitle(title + ' 분포')
        self.resize(1000, 760)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.response = QComboBox()
        self.response.setAccessibleName('분포 응답')
        for item in self.result.get('probability_statistics', []):
            definition = item.get('threshold', {})
            name = str(item.get('response', '?'))
            reduction = definition.get('reduction')
            if reduction:
                name += ' / ' + CHOICE_LABELS.get(reduction, str(reduction))
            self.response.addItem(name + ' [' + str(item.get('unit', '?')) + ']', item)
        controls.addWidget(QLabel('응답'))
        controls.addWidget(self.response, 1)
        layout.addLayout(controls)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        from .numerical_extension_widgets import joint_summary
        joint = joint_summary(self.result.get('sampling',{}))
        if joint:
            description=QLabel(joint)
            description.setWordWrap(True)
            description.setToolTip('분포 근거: '+str(self.result.get('sampling',{}).get('source',{}).get('reference','')))
            layout.addWidget(description)
            matrix_button=QPushButton('입력 공분산과 상관 보기…')
            matrix_button.clicked.connect(self._show_joint)
            layout.addWidget(matrix_button)
        interval = QHBoxLayout()
        self.lower, self.upper = QLineEdit(), QLineEdit()
        self.lower.setAccessibleName('선택 구간 하한')
        self.upper.setAccessibleName('선택 구간 상한')
        self.unit = QLabel()
        self.select_button = QPushButton('구간 선택')
        self.clear_button = QPushButton('선택 해제')
        for widget in (QLabel('구간'), self.lower, QLabel('~'), self.upper, self.unit,
                       self.select_button, self.clear_button):
            interval.addWidget(widget)
        layout.addLayout(interval)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        from .appearance import configure_plot_fonts
        configure_plot_fonts()
        self.figure = Figure(constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setMinimumHeight(220)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['후보', '실행 상태', '응답 값', '실패 또는 제외 이유'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.canvas)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([360, 240])
        layout.addWidget(splitter, 1)
        self.response.currentIndexChanged.connect(self._show_response)
        self.select_button.clicked.connect(self.select_interval)
        self.clear_button.clicked.connect(self.table.clearSelection)
        self.lower.returnPressed.connect(self.select_interval)
        self.upper.returnPressed.connect(self.select_interval)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.canvas.mpl_connect('pick_event', self._bin_picked)
        self._show_response()

    def _show_joint(self):
        from .numerical_extension_widgets import JointDistributionEditor
        from PySide6.QtWidgets import QDialogButtonBox
        sampling=self.result['sampling']
        dialog=QDialog(self)
        dialog.setWindowTitle('입력 결합분포')
        dialog.resize(780,450)
        layout=QVBoxLayout(dialog)
        editor=JointDistributionEditor(sampling,self.result['variables'],dialog)
        editor.setEnabled(False)
        layout.addWidget(editor)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.close);layout.addWidget(buttons)
        dialog.exec()

    def _show_response(self, *_):
        item = self.response.currentData() or {}
        definition = item.get('threshold') or {'response': item.get('response'), 'unit': item.get('unit')}
        self._values = {}
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setRowCount(len(self.result.get('candidates', [])))
        for index, row in enumerate(self.result.get('candidates', [])):
            reason = row.get('failure_reason') or ''
            predicted = row.get('prediction_status') == 'PREDICTED' or row.get('execution_status') == 'PREDICTED'
            status = 'PREDICTED' if predicted else row.get('execution_status')
            try:
                self._values[index] = _scalar(row, definition)
            except (EvaluationFailed, ValueError, KeyError, TypeError) as error:
                reason = reason or str(error)
            cells = [f'후보 {index + 1}', STATE.get(status, '미확인'),
                     format(self._values[index], '.17g') if index in self._values else '없음',
                     exclusion_label(row, definition, reason) if index not in self._values else reason]
            for column, value in enumerate(cells):
                cell = QTableWidgetItem(str(value))
                cell.setData(Qt.ItemDataRole.UserRole, row.get('candidate_id'))
                self.table.setItem(index, column, cell)
            self.table.item(index, 0).setToolTip(str(row.get('candidate_id', '')))
            self.table.item(index, 1).setToolTip(candidate_state(row))
            self.table.item(index, 3).setToolTip(str(reason))
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        self.unit.setText('[' + str(item.get('unit', '?')) + ']')
        def retained(value):
            return format(value, '.6g') if type(value) in (int, float) and math.isfinite(value) else '없음'
        quantiles = item.get('quantiles', {})
        summary = ('전체 ' + str(item.get('total_count',len(self.result.get('candidates',[])))) +
            ' / 유효 ' + str(item.get('valid_count', 0)) + ' / 실패·제외 ' +
            str(item.get('failed_count', 0)) + '    평균 ' + retained(item.get('mean')) +
            '    표준편차 ' + retained(item.get('std')) + '\n보존 분위수 5% / 50% / 95%: ' +
            ' / '.join(retained(quantiles.get(key)) for key in ('q05', 'q50', 'q95')) +
            '    성공한 평가에 조건부인 통계')
        fraction=item.get('exceedance_fraction_valid')
        if fraction is not None:
            threshold=item.get('threshold',{})
            summary += ('\n초과 조건: '+str(threshold.get('operator','>'))+' '+retained(threshold.get('limit'))+
                ' ['+str(item.get('unit','?'))+']    유효 표본 기준 '+format(100*fraction,'.6g')+
                '% (분모 '+str(item.get('valid_count',0))+')')
            bounds=item.get('exceedance_fraction_total_bounds')
            if bounds is not None:
                summary += ('    전체 표본 기준 '+format(100*bounds[0],'.6g')+'~'+format(100*bounds[1],'.6g')+
                    '% (실패값 미확인)')
        self.summary.setText(summary)
        self.figure.clear()
        self.axis = self.figure.add_subplot(111)
        self._patch_rows = {}
        self._selected_bars = {}
        if self._values:
            values = list(self._values.values())
            _, edges, patches = self.axis.hist(values, bins=min(20, max(1, math.ceil(math.sqrt(len(values))))),
                                               color='tab:blue', edgecolor='white', picker=True, label='전체 유효 표본')
            for index, patch in enumerate(patches):
                self._patch_rows[patch] = [row for row, value in self._values.items()
                    if edges[index] <= value and (value < edges[index + 1] or
                       index == len(patches) - 1 and value <= edges[index + 1])]
                self._selected_bars[patch] = self.axis.bar(patch.get_x(), 0, width=patch.get_width(),
                    align='edge', color='tab:orange', label='선택 표본' if index == 0 else None)[0]
            self.lower.setText(format(min(values), '.17g'))
            self.upper.setText(format(max(values), '.17g'))
        else:
            self.axis.text(.5, .5, '이 응답에 보존된 유효 표본이 없습니다.', ha='center', transform=self.axis.transAxes)
            self.lower.clear()
            self.upper.clear()
        self.axis.set_xlabel(self.response.currentText())
        self.axis.set_ylabel('표본 수')
        self.axis.yaxis.set_major_locator(MaxNLocator(integer=True))
        if self._values:
            self.axis.legend(fontsize=9)
        self.axis.grid(axis='y', alpha=.2)
        self.select_button.setEnabled(bool(self._values))
        self._selection_changed()

    def selected_candidate_ids(self):
        return [self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                for row in sorted({index.row() for index in self.table.selectedIndexes()})]

    def _select_rows(self, rows):
        self.table.blockSignals(True)
        self.table.clearSelection()
        model = self.table.selectionModel()
        for row in rows:
            model.select(self.table.model().index(row, 0), QItemSelectionModel.SelectionFlag.Select |
                         QItemSelectionModel.SelectionFlag.Rows)
        if rows:
            self.table.scrollToItem(self.table.item(rows[0], 0))
        self.table.blockSignals(False)
        self._selection_changed()

    def select_interval(self):
        try:
            lower, upper = float(self.lower.text()), float(self.upper.text())
            if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
                raise ValueError()
        except ValueError:
            self.message.setText('유한한 하한과 상한을 입력하세요. 하한은 상한보다 클 수 없습니다.')
            return False
        self._select_rows([row for row, value in self._values.items() if lower <= value <= upper])
        return True

    def _bin_picked(self, event):
        if event.artist in self._patch_rows:
            self.lower.setText(format(event.artist.get_x(), '.17g'))
            self.upper.setText(format(event.artist.get_x() + event.artist.get_width(), '.17g'))
            self._select_rows(self._patch_rows[event.artist])
            last = event.artist is list(self._patch_rows)[-1]
            self.message.setText(self.message.text() + ('    마지막 막대는 양끝 포함' if last else '    막대의 우측 경계 제외'))

    def _selection_changed(self):
        rows = {index.row() for index in self.table.selectedIndexes()}
        for patch, members in self._patch_rows.items():
            self._selected_bars[patch].set_height(len(rows.intersection(members)))
        selected_valid = len(rows.intersection(self._values))
        self.message.setText('선택 ' + str(len(rows)) + '개 / 응답 값 있음 ' + str(selected_valid) + '개')
        self.canvas.draw_idle()
