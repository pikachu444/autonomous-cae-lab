"""Neo-Hooke SIMULATED UI; raw-input plots and state transitions, no physics solve."""
from pathlib import Path
import json
from PySide6.QtCore import QFile, QIODevice, Qt, QEvent
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QMessageBox, QStyledItemDelegate, QLineEdit,
    QAbstractItemDelegate, QAbstractItemView, QScrollArea, QDialog, QDialogButtonBox,
)
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from state_model import DraftSession, PlanningStore, load_samples, reference


class BufferDelegate(QStyledItemDelegate):
    """Enter submits a recoverable owner draft; Escape cancels only the cell buffer."""
    def __init__(self, domain, fields, window, parent):
        super().__init__(parent)
        self.domain, self.fields, self.window = domain, fields, window

    def createEditor(self, parent, option, index):
        pending = self.window.session.buffer
        field = self.fields[index.row()]
        if field not in DraftSession.editable.get(self.domain, set()):
            return None
        if pending and (pending['domain'], pending['field']) != (self.domain, field):
            self.window.message = 'Resolve the pending buffer before editing another cell.'
            self.window.update_status()
            return None
        self.window.focus_owner = self.domain
        editor = QLineEdit(parent)
        editor.setProperty('field', field)
        editor.textEdited.connect(lambda text: self.window.update_buffer(self.domain, field, text))
        return editor

    def setEditorData(self, editor, index):
        pending = self.window.session.buffer
        editor.setText(pending['text'] if pending else str(index.data()))
        editor.selectAll()

    def setModelData(self, editor, model, index):
        pass  # No silent focus-loss commit.

    def eventFilter(self, editor, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.window.update_buffer(self.domain, editor.property('field'), editor.text())
                self.window.session.commit_buffer()
                self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)
                self.window.message = 'Enter acknowledged owner draft. Invalid raw strings remain diagnosed; no numeric zero substitution.'
                self.window.refresh()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.window.session.discard_buffer()
                self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.RevertModelCache)
                self.window.refresh()
                return True
            if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                return True
        return super().eventFilter(editor, event)


class MaterialDemo(QMainWindow):
    def __init__(self, artifact_root, store_path, parent=None):
        super().__init__(parent)
        self.root = Path(artifact_root)
        self.samples, self.raw = load_samples(self.root / 'data')
        imports = {s['source']: s['source_sha256'] for s in self.samples}
        self.store = PlanningStore(store_path, imports)
        self.session = DraftSession(self.store)
        self.session.samples = self.samples
        self.selected_id = self.samples[0]['id'] if self.samples else None
        self.focus_owner = 'Material'
        self.updating = False
        self.message = 'SIMULATED neo-Hooke scene: Material r17 mu=.85 MPa, externally fixed lmbda=12 MPa; Plan r8 start=.85, bounds .4..1.4. Actual traction-free solver NOT IMPLEMENTED / NOT RUN.'
        self.setWindowTitle('SIMULATED UI • Neo-Hooke Material / Plan / recovery')
        handle = QFile(str(Path(__file__).with_name('material_demo.ui')))
        if not handle.open(QIODevice.OpenModeFlag.ReadOnly):
            raise OSError(handle.errorString())
        loader = QUiLoader()
        self.form = loader.load(handle, self)
        handle.close()
        if self.form is None:
            raise RuntimeError(loader.errorString())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.form)
        self.setCentralWidget(scroll)
        self.resize(1480, 1040)
        self.figure = Figure(figsize=(6, 3), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setProperty('planningOwner', 'Data')
        plot_layout = QVBoxLayout(self.widget('plotContainer', QWidget))
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.addWidget(self.canvas)
        self.canvas.mpl_connect('pick_event', self.plot_pick)
        self.setup_tables()
        self.bind_actions()
        self.refresh()
        if self.store.recovery_path.exists():
            self.message = 'A separate recovery capsule exists. Saved revisions were opened; use Restore recovery to inspect raw buffer / owner drafts / original bases. No automatic restore or run.'
            self.update_status()

    def widget(self, name, kind):
        result = self.form.findChild(kind, name)
        if result is None:
            raise RuntimeError(f'Designer form missing {name}')
        return result

    @staticmethod
    def fill_table(table, headers, rows, editable_column=None, editable_rows=None):
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem(f'{value:.6g}' if isinstance(value, float) else str(value))
                if j != editable_column or (editable_rows is not None and i not in editable_rows):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(i, j, item)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

    def setup_tables(self):
        self.raw_tables = {}
        for source in ('A', 'B'):
            table = self.widget('raw' + source, QTableWidget)
            rows = self.raw[source]
            columns = list(rows[0]) if rows else []
            self.fill_table(table, columns, [[row[key] for key in columns] for row in rows])
            table.itemSelectionChanged.connect(lambda s=source: self.raw_selected(s))
            self.raw_tables[source] = table
            table.setProperty('planningOwner', 'Data')
        self.normalized = self.widget('normalizedTable', QTableWidget)
        self.normalized.setProperty('planningOwner', 'Data')
        self.normalized.itemSelectionChanged.connect(self.normalized_selected)
        self.material_fields = ['mu_MPa', 'lmbda_MPa']
        self.plan_fields = ['mu_start_MPa', 'mu_min_MPa', 'mu_max_MPa', 'lmbda_fixed_MPa']
        for name, domain, fields in (('coefficientTable', 'Material', self.material_fields), ('boundsTable', 'Plan', self.plan_fields)):
            table = self.widget(name, QTableWidget)
            table.setProperty('planningOwner', domain)
            table.setItemDelegateForColumn(1, BufferDelegate(domain, fields, self, table))
            table.currentCellChanged.connect(lambda row, col, oldrow, oldcol, d=domain: self.set_focus_owner(d))
        self.candidate_table = self.widget('candidateTable', QTableWidget)
        self.candidate_table.setProperty('planningOwner', 'Plan')
        self.candidate_table.itemSelectionChanged.connect(self.inspect_candidate)
        for table in (*self.raw_tables.values(), self.normalized,
                      self.widget('coefficientTable', QTableWidget),
                      self.widget('boundsTable', QTableWidget), self.candidate_table):
            table.installEventFilter(self)
            table.viewport().setProperty('planningOwner', table.property('planningOwner'))
            table.viewport().installEventFilter(self)
        self.canvas.installEventFilter(self)
        self.widget('mappingLabel', QLabel).setText('Synthetic A/B different specimens; extensometer gauge extension. L0=50 mm, A0=20 mm²: e11=extension/L0, axial stretch=1+e11, nominal first-Piola P11=force/A0 [N/mm²=MPa]. B: µm×.001, kN×1000, ms×.001. Canonical absolute temperature: A °C+273.15→K; B K unchanged. No J=1/Cauchy assumption.')

    def set_focus_owner(self, domain):
        if self.updating:
            return
        self.focus_owner = domain
        if hasattr(self, 'candidate_table'):
            self.update_status()

    def focused_owner(self):
        # Resolve actual focus ancestry, including editor/viewport children;
        # re-clicking an already selected cell need not emit currentCellChanged.
        focused = QApplication.focusWidget()
        while focused is not None:
            owner = focused.property('planningOwner')
            if owner in self.session.saved:
                self.focus_owner = owner
                return owner
            focused = focused.parentWidget()
        return self.focus_owner

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FocusIn:
            owner = watched.property('planningOwner')
            if owner in self.session.saved:
                self.focus_owner = owner
                self.update_status()
        return super().eventFilter(watched, event)

    def bind_actions(self):
        actions = {
            'toggleMaskButton': lambda: self.toggle_mask('Data', 'quality_excluded'),
            'planMaskButton': lambda: self.toggle_mask('Plan', 'inclusion_excluded'),
            'hideButton': lambda: self.toggle_mask('View', 'display_hidden'),
            'undoMaskButton': self.undo_edit, 'commitBufferButton': self.commit_buffer,
            'discardBufferButton': self.discard_buffer,
            'saveDataButton': lambda: self.save_domain('Data'),
            'saveMaterialButton': lambda: self.save_domain('Material'),
            'savePlanButton': lambda: self.save_domain('Plan'),
            'saveAllButton': self.save_all, 'partialSaveButton': lambda: self.save_all(True),
            'injectConflictButton': self.inject_conflict,
            'reloadMaterialButton': lambda: self.reload_domain('Material'),
            'reopenButton': self.cold_reopen, 'adoptButton': self.preview_adoption,
            'newProposalButton': lambda: self.resolve_adoption('new_proposal'),
            'applyProposalButton': lambda: self.resolve_adoption('apply'),
            'branchButton': lambda: self.resolve_adoption('branch'),
            'cancelAdoptionButton': lambda: self.resolve_adoption('cancel'),
            'refreshSourceButton': self.refresh_source, 'simulateRunButton': self.simulate_run,
            'evaluateDetailsButton': self.evaluate_details,
            'restoreRecoveryButton': self.restore_recovery,
            'preserveRecoveryButton': self.preserve_recovery,
        }
        for name, action in actions.items():
            self.widget(name, QPushButton).clicked.connect(lambda checked=False, fn=action: fn())
        owners = {
            'toggleMaskButton': 'Data', 'saveDataButton': 'Data',
            'planMaskButton': 'Plan', 'savePlanButton': 'Plan', 'refreshSourceButton': 'Plan',
            'simulateRunButton': 'Plan', 'evaluateDetailsButton': 'Plan',
            'saveMaterialButton': 'Material', 'adoptButton': 'Material',
            'newProposalButton': 'Material', 'applyProposalButton': 'Material',
            'branchButton': 'Material', 'cancelAdoptionButton': 'Material',
            'reloadMaterialButton': 'Material', 'injectConflictButton': 'Material',
        }
        for name, owner in owners.items():
            self.widget(name, QPushButton).setProperty('planningOwner', owner)
        for key, action in (('Ctrl+S', lambda: self.save_domain(self.focused_owner())), ('Ctrl+Z', self.undo_edit), ('Esc', self.discard_buffer)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(action)

    def update_buffer(self, domain, field, text):
        self.session.begin_buffer(domain, field, text)
        self.update_status()

    def commit_buffer(self):
        self.session.commit_buffer()
        self.message = 'Cell text submitted to owner draft; invalid text is preserved with diagnostics. Saved revision unchanged.'
        self.refresh()

    def discard_buffer(self):
        self.session.discard_buffer()
        self.message = 'Only pending cell buffer discarded; acknowledged owner drafts retained.'
        self.refresh()

    def refresh(self):
        selected_candidate = self.selected_candidate_id() if self.candidate_table.rowCount() else 'c017'
        self.updating = True
        data, plan = self.session.draft['Data'], self.session.draft['Plan']
        rows = [[s['id'], s['source_row'], s['time_s'], s['e11'], s['axial_stretch'], s['P11_MPa'], s['temperature_K'],
                 'EXCLUDED' if s['id'] in data['quality_excluded'] else 'valid',
                 'included' if s['operation_valid'] else 'INVALID stretch',
                 'EXCLUDED' if s['id'] in plan['inclusion_excluded'] else 'included',
                 'hidden' if s['id'] in self.session.view_hidden else 'visible'] for s in self.samples]
        self.fill_table(self.normalized, ['Exact raw sample ID', 'Row', 't [s]', 'e11 [-]', 'λ1 [-]', 'P11 [MPa]', 'T [K]', 'Data quality', 'Operation', 'Plan include', 'Display only'], rows)
        for name, domain, fields in (('coefficientTable', 'Material', self.material_fields), ('boundsTable', 'Plan', self.plan_fields)):
            rows = [[field, self.session.draft[domain][field], self.session.saved[domain]['value'][field]] for field in fields]
            self.fill_table(self.widget(name, QTableWidget), [domain + ' field', 'Owner draft', 'Saved base'], rows, 1,
                            {i for i, field in enumerate(fields) if field in DraftSession.editable[domain]})
        document = self.store.read()
        rows = [[c['id'], c['mu_MPa'], c['train_objective'], c['status'], c['detail'], c['holdout'], c['evaluation_id'] or '—'] for c in document['candidates']]
        self.fill_table(self.candidate_table, ['SIMULATED candidate', 'μ [MPa]', 'Train objective', 'Status', 'Original detail', 'Original holdout', 'Original evaluation ID'], rows)
        index = next((i for i, c in enumerate(document['candidates']) if c['id'] == selected_candidate), 0)
        self.candidate_table.selectRow(index)
        self.updating = False
        self.select_sample(self.selected_id)
        self.inspect_candidate()
        self.show_adoption()
        self.update_status()

    def update_status(self):
        current = self.store.read()['domains']
        states = []
        for name, base in self.session.saved.items():
            invalid = '; INVALID_DRAFT' if self.session.diagnostics(name) else ''
            states.append(f'{name}: saved base r{base["revision"]}, current saved r{current[name]["revision"]}, draft g{self.session.generations[name]} {"DIRTY" if self.session.dirty(name) else "unchanged"}{invalid}')
        buffer = self.session.buffer
        buffer_text = f'{buffer["domain"]}.{buffer["field"]} raw={buffer["text"]!r}' if buffer else 'none'
        owner = self.focused_owner()
        undo_command = self.session.undo_label(owner)
        self.widget('stateLabel', QLabel).setText(' | '.join(states) + f'\nCell buffer: {buffer_text} | Ctrl+S / Ctrl+Z owner: {owner} | next Undo: {undo_command} | Redo: NOT IMPLEMENTED')
        self.widget('undoMaskButton', QPushButton).setText(f'Undo {owner}: {undo_command} (Ctrl+Z)')
        plan = self.session.draft['Plan']
        refs = ', '.join(f'{domain} r{ref["revision"]} / {ref["input_sha256"][:10]}' for domain, ref in plan['source_refs'].items())
        self.widget('sourceRefsLabel', QLabel).setText(f'Plan starts μ={plan["mu_start_MPa"]!r}, bounds={plan["mu_min_MPa"]!r}..{plan["mu_max_MPa"]!r}; Material current draft μ={self.session.draft["Material"]["mu_MPa"]!r}. Plan sources: {refs}\nPlan protocol: {plan["protocol"]}; λ_L={plan["lmbda_fixed_MPa"]} MPa externally fixed. Traction-free solver remains unsupported; run/detail buttons trace PROPOSED FUTURE state only; current execution BLOCKED.')
        diagnostics = self.session.diagnostics('Material') + self.session.diagnostics('Plan')
        self.widget('messageLabel', QLabel).setText(self.message + ('\nDIAGNOSTICS: ' + '; '.join(diagnostics) if diagnostics else ''))
        try:
            roles = self.session.frozen_mask(self.session.draft['Data'], plan)
            counts = ', '.join(f'{source} {value["role"]}: {value["count"]}' for source, value in roles.items())
        except ValueError as exc:
            counts = str(exc)
        self.widget('selectionLabel', QLabel).setText(f'Linked selection: {self.selected_id or "none"}. Draft quality ∩ operation-valid ∩ Plan inclusion: {counts}. Display hiding never changes these counts.')

    def select_sample(self, sample_id):
        self.selected_id = sample_id
        self.updating = True
        for row, sample in enumerate(self.samples):
            if sample['id'] == sample_id:
                self.normalized.selectRow(row)
                self.raw_tables[sample['source']].selectRow(sample['source_index'])
                self.widget('rawTabs', QTabWidget).setCurrentIndex(0 if sample['source'] == 'A' else 1)
                break
        self.updating = False
        self.plot()
        self.update_status()

    def normalized_selected(self):
        row = self.normalized.currentRow()
        if not self.updating and row >= 0:
            self.focus_owner = 'Data'
            self.select_sample(self.samples[row]['id'])

    def raw_selected(self, source):
        row = self.raw_tables[source].currentRow()
        if not self.updating and row >= 0:
            sample = next(s for s in self.samples if s['source'] == source and s['source_index'] == row)
            self.focus_owner = 'Data'
            self.select_sample(sample['id'])

    def plot(self):
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        data, plan = self.session.draft['Data'], self.session.draft['Plan']
        self.pick_ids = {}
        for source, color in (('A', '#11796b'), ('B', '#2768a4')):
            samples = [s for s in self.samples if s['source'] == source and s['id'] not in self.session.view_hidden]
            # Preserve raw markers; break the connected line at quality/operation gaps.
            ys = [s['P11_MPa'] if s['id'] not in data['quality_excluded'] and s['operation_valid'] else float('nan') for s in samples]
            axes.plot([s['e11'] for s in samples], ys, '-', color=color)
            artist, = axes.plot([s['e11'] for s in samples], [s['P11_MPa'] for s in samples], 'o', color=color, label=f'Synthetic {source} ({plan["roles"][source]})', picker=6)
            self.pick_ids[artist] = [s['id'] for s in samples]
        for sample in self.samples:
            if sample['id'] in self.session.view_hidden:
                continue
            if sample['id'] in data['quality_excluded'] or sample['id'] in plan['inclusion_excluded']:
                axes.plot(sample['e11'], sample['P11_MPa'], 'x', color='#c74534', markersize=10)
            if sample['id'] == self.selected_id:
                axes.plot(sample['e11'], sample['P11_MPa'], 'o', markerfacecolor='none', markeredgecolor='#ec9b25', markersize=16, markeredgewidth=2)
        axes.set(xlabel='Engineering strain e11 = extension / 50 mm [-]', ylabel='Nominal P11 = force / 20 mm² [MPa]', title='SIMULATED inputs • first Piola / material frame; time remains an independent channel')
        axes.grid(alpha=.2)
        axes.legend(loc='best')
        self.canvas.draw_idle()

    def plot_pick(self, event):
        ids = self.pick_ids.get(event.artist, [])
        if ids and len(event.ind):
            self.select_sample(ids[int(event.ind[0])])

    def toggle_mask(self, owner, field):
        if self.selected_id:
            if owner != 'View':
                self.focus_owner = owner
            self.session.toggle_mask(self.selected_id, owner, field)
            self.message = f'{owner}.{field} changed; raw sample retained. View hiding changes no owner input generation or mask counts. No fit/objective calculation.'
            self.refresh()

    def undo_edit(self):
        owner = self.focused_owner()
        changed = self.session.undo(owner)
        self.message = f'Focused-owner Undo {owner}: {changed}; other owners and pending buffer retained. Redo NOT IMPLEMENTED in this harness.'
        self.refresh()

    def call(self, action):
        try:
            result = action()
            self.message = str(result)
        except (RuntimeError, ValueError, OSError) as exc:
            self.message = str(exc)
        self.refresh()

    def save_domain(self, domain):
        self.focus_owner = domain
        self.call(lambda: f'SIMULATED {domain}: {self.session.save(domain)}. Source refs in Plan were NOT auto-refreshed.')

    def save_all(self, partial=False):
        self.call(lambda: 'SIMULATED independent outcomes: ' + json.dumps(self.session.save_all(partial)))

    def inject_conflict(self):
        self.message = f'SIMULATED other client saved Material r{self.store.inject_external_change()} μ=.90 plus protocol change. Candidate .862 remains tied to r17. Preview adoption differences before any mutation.'
        self.refresh()

    def selected_candidate_id(self):
        row = self.candidate_table.currentRow()
        item = self.candidate_table.item(row, 0) if row >= 0 else None
        return item.text() if item else 'c017'

    def inspect_candidate(self):
        if self.updating:
            return
        candidate = self.session.inspect_candidate(self.selected_candidate_id())
        document = self.store.read()
        extra = [(key, value) for key, value in document['evaluations'].items() if key.startswith('SIM-EVAL-') and value['candidate_id'] == candidate['id']]
        original = candidate['evaluation_id']
        details = f'{candidate["id"]}: μ={candidate["mu_MPa"]}; original detail={candidate["detail"]}; original holdout={candidate["holdout"]}; original eval={original or "none"}; fit source Material r{candidate["base_ref"]["revision"]}, Plan r{candidate["frozen_plan"]["revision"]}.\n'
        if original and original in document['evaluations']:
            details += 'Retained SIMULATED selected fixture: A=train, B=holdout, holdout RMSE=.014 MPa. Identity/illustrative number only; no prediction/residual arrays or solver calculation fabricated.\n'
        elif candidate['detail'] == 'PARTIAL_FIXTURE_ONLY':
            details += 'Partial fixture record/log only; complete response remains INVALID or incomplete. Holdout NOT_EVALUATED; no numerical partial curve or evaluation fabricated.\n'
        else:
            details += 'No retained original curves/holdout for this row. Selection does not evaluate or replace it with best curves.\n'
        details += 'Separate explicit simulated detail IDs: ' + (', '.join(key for key, value in extra) or 'none')
        self.widget('candidateDetailLabel', QLabel).setText(details)

    def evaluate_details(self):
        self.call(lambda: 'Explicit SIMULATED detail created: ' + self.session.simulate_detail_evaluation(self.selected_candidate_id()) + '. Frozen candidate source refs retained; original run availability unchanged. No solver execution.')

    def preview_adoption(self):
        self.call(lambda: 'SIMULATED adoption preview only: ' + self.session.preview_adoption(self.selected_candidate_id())['phase'] + '. Material unchanged.')

    def show_adoption(self):
        proposal = self.session.pending_adoption or self.session.pending_adoption_receipt
        rows = [[row['field'], row['base'], row['current'], row['proposed']] for row in proposal['differences']] if proposal else []
        self.fill_table(self.widget('adoptionDiffTable', QTableWidget), ['Field', 'Fit base r17', 'Current saved target', 'New proposed value'], rows)
        if self.session.pending_adoption_receipt is not None:
            label = f'SIMULATED acknowledged dirty Material draft: {proposal["candidate_id"]}, expected saved r{proposal["current_ref"]["revision"]} still unchanged. Use explicit Save Material to publish the next revision/receipt. Plan sources remain frozen.'
        else:
            label = 'No adoption prepared. Select a candidate and Preview.' if proposal is None else f'SIMULATED {proposal["phase"]}: {proposal["candidate_id"]}; base r{proposal["candidate_base_ref"]["revision"]} → current r{proposal["current_ref"]["revision"]}. Apply checks fresh revision/hash and acknowledges a dirty draft only; conflict requires New proposal on current, Branch or Cancel.'
        self.widget('adoptionLabel', QLabel).setText(label)

    def resolve_adoption(self, choice):
        self.call(lambda: json.dumps(self.session.resolve_adoption(choice), ensure_ascii=False))

    def refresh_source(self):
        try:
            preview = self.session.preview_source_refresh()
            dialog = QDialog(self)
            dialog.setWindowTitle('SIMULATED Plan source refresh • explicit differences')
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel('Apply changes Plan draft only. Save Plan afterwards. Cancel retains old refs/starts/bounds.'))
            table = QTableWidget()
            fields = ['source_refs', 'mu_start_MPa', 'mu_min_MPa', 'mu_max_MPa', 'lmbda_fixed_MPa', 'protocol']
            self.fill_table(table, ['Plan field', 'Existing Plan', 'Proposed from saved owners'], [[key, preview['old'][key], preview['proposed'][key]] for key in fields])
            layout.addWidget(table)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
            buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            dialog.resize(1120, 430)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.session.apply_source_refresh()
                self.message = 'Explicit source refresh applied to Plan draft. Bounds retained; starts/source/protocol copied as previewed. Save Plan before simulated run.'
            else:
                self.session.cancel_source_refresh()
                self.message = 'Source refresh cancelled. Prior Plan refs/starts/bounds unchanged.'
        except (RuntimeError, ValueError, OSError) as exc:
            self.message = str(exc)
        self.refresh()

    def simulate_run(self):
        self.call(lambda: json.dumps(self.session.simulate_run()) + ' — PROPOSED FUTURE SIMULATED state transition only. Current execution BLOCKED; traction-free solver NOT IMPLEMENTED / NOT RUN.')

    def confirm_discard(self, text):
        return QMessageBox.question(self, 'Unsaved planning edits', text + '\nDiscard these local drafts/buffer?', QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Discard

    def reload_domain(self, domain):
        has_buffer = self.session.buffer is not None and self.session.buffer['domain'] == domain
        if (self.session.dirty(domain) or has_buffer) and not self.confirm_discard('Reload saved ' + domain):
            return
        self.session.reload_domain(domain, True)
        self.message = f'Saved {domain} loaded; other owner drafts and buffers retained.'
        self.refresh()

    def cold_reopen(self):
        if (any(self.session.dirty(d) for d in self.session.saved) or self.session.buffer) and not self.confirm_discard('Cold reopen saved JSON. Preserve recovery first if needed.'):
            return
        self.session = DraftSession(self.store)
        self.session.samples = self.samples
        self.message = 'Cold reopened saved revisions only. Recovery capsule remains separate. No fit, detail evaluation, run or job cancel.'
        self.refresh()

    def preserve_recovery(self):
        self.call(lambda: 'Separate recovery capsule saved: ' + str(self.session.preserve_recovery()) + '; no saved revision advanced.')

    def restore_recovery(self):
        if (any(self.session.dirty(d) for d in self.session.saved) or self.session.buffer) and not self.confirm_discard('Restore recovery will replace current in-memory drafts/buffer.'):
            return
        self.call(lambda: 'Recovery restored: ' + self.session.restore_recovery()['kind'] + '; raw text/original bases retained; saved revision unchanged.')

    def closeEvent(self, event):
        if any(self.session.dirty(d) for d in self.session.saved) or self.session.buffer:
            dialog = QMessageBox(self)
            dialog.setWindowTitle('Close SIMULATED UI • buffer / owner drafts / saved refs')
            dialog.setText('Unsaved buffers/drafts exist. Keep a separate recovery capsule to preserve invalid raw text. Closing does not cancel or start any job.')
            preserve = dialog.addButton('Keep recovery and close', QMessageBox.ButtonRole.AcceptRole)
            discard = dialog.addButton('Discard drafts and close', QMessageBox.ButtonRole.DestructiveRole)
            stay = dialog.addButton('Return to editing', QMessageBox.ButtonRole.RejectRole)
            dialog.setDefaultButton(preserve)
            dialog.exec()
            if dialog.clickedButton() == stay or dialog.clickedButton() is None:
                event.ignore()
                return
            if dialog.clickedButton() == preserve:
                try:
                    self.session.preserve_recovery()
                except OSError as exc:
                    QMessageBox.warning(self, 'Recovery failed — window remains open', str(exc))
                    event.ignore()
                    return
            self.session = DraftSession(self.store)
            self.session.samples = self.samples
            self.message = 'Closed drafts reset; saved revisions and any preserved recovery capsule remain distinct.'
            self.refresh()
        event.accept()
