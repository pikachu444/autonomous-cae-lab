"""Native save/close/workbench gates and a small project/results dock.

FreeCAD 1.1.4 Action.cpp names QActions with the command ID. DocumentPyImp.cpp
exposes Gui.Document.Modified. Commands, native canvas and Tasks remain native;
we substitute managed Save actions, not their geometry/solver implementation.
"""
from pathlib import Path


def _saved(owner):
    check = getattr(owner.project, 'is_saved', None)
    return check() if check is not None else owner.saved_generation == owner.generation


def _motion_controller(connection, owner):
    dock = getattr(connection, 'panels', {}).get(owner.doc.Name, {}).get('motion')
    try: return getattr(dock.widget(), 'motion_controller', None) if dock is not None and hasattr(dock, 'widget') else None
    except RuntimeError: return None  # The native dock may already have been destroyed.


def _close_version(owner, connection=None):
    from .shell_controls import editor_token
    graph = getattr(owner.project, 'graph_version', None)
    controller = _motion_controller(connection, owner) if connection is not None else None
    return (owner.generation, graph() if graph is not None else None,
            controller.editor_token() if controller is not None else None,
            editor_token(connection, owner) if connection is not None else None)


def install(connection, open_model):
    QtCore, QtWidgets = connection.QtCore, connection.QtWidgets
    Gui, App = connection.Gui, connection.App
    main = Gui.getMainWindow()
    from PySide import QtGui
    QAction = getattr(QtWidgets, 'QAction', None) or QtGui.QAction
    command_names = {'Std_Save', 'Std_SaveAs', 'Std_SaveAll', 'Std_Close', 'Std_CloseAll', 'Std_Export'}
    workbenches = {'PartWorkbench', 'PartDesignWorkbench', 'SketcherWorkbench', 'AssemblyWorkbench', 'FemWorkbench'}

    class Guards(QtCore.QObject):
        def __init__(self):
            super().__init__(main)
            self.replacements, self.closing, self.bypass = {}, False, set()
            self.approved_close = {}
            self.old_workbench = None
            QtWidgets.QApplication.instance().installEventFilter(self)
            self.toolbar = QtWidgets.QToolBar('CAE Lab', main)
            self.toolbar.setObjectName('CAELabNativeTools')
            main.addToolBar(self.toolbar)
            for title, callback in [('모델 열기…', open_model), ('프로젝트 저장', self.save),
                    ('다른 이름으로 저장…', lambda: self.save(as_new=True)),
                    ('설계 변수', lambda: connection.show_panel('parameters')),
                    ('조립 운동', lambda: connection.show_panel('motion')),
                    ('해석 설정', lambda: connection.show_panel('fem')),
                    ('프로젝트', lambda: connection.show_panel('project'))]:
                action = self.toolbar.addAction(title)
                action.triggered.connect(lambda checked=False, callback=callback: self.invoke(callback))
            self.refresh()

        def saved(self, owner):
            from .shell_controls import has_unsaved_editor
            controller = _motion_controller(connection, owner)
            return (_saved(owner) and (controller is None or not controller.has_unsaved_editor())
                    and not has_unsaved_editor(connection, owner))

        def invoke(self, callback):
            try: callback()
            except Exception as error: connection.message.setText(str(error))

        def refresh(self):
            self.approved_close = {owner.document_id: version for owner, _, _ in connection.owners.values()
                                   if (version := self.approved_close.get(owner.document_id)) == _close_version(owner, connection)}
            # A native workbench may rebuild menus/toolbars. Replace only the
            # exact known QAction occurrences, preserving shortcuts/menu order.
            for action in main.findChildren(QAction):
                name = action.objectName()
                if name not in command_names: continue
                previous = self.replacements.get(name)
                if previous is None:
                    proxy = QAction(action.icon(), action.text(), main)
                    proxy.setObjectName('CAELabManaged_' + name)
                    proxy.setShortcuts(action.shortcuts())
                    proxy.setToolTip(action.toolTip() + '\nCAE Lab 프로젝트와 연결된 편집 문서를 함께 저장합니다.')
                    proxy.triggered.connect(lambda checked=False, name=name: self.invoke(lambda: self.trigger(name)))
                else:
                    proxy = previous[1]
                    if action.shortcuts():
                        proxy.setShortcuts(action.shortcuts())
                action.setShortcuts([])
                self.replacements[name] = (action, proxy)
                # A workbench can create a new QAction with the same command
                # name. Replace every live occurrence, not just the first
                # object seen in this native session.
                widgets = action.associatedObjects() if hasattr(action, 'associatedObjects') else action.associatedWidgets()
                for widget in list(widgets):
                    if not hasattr(widget, 'actions'): continue
                    actions = widget.actions()
                    if action in actions:
                        index = actions.index(action)
                        next_action = actions[index + 1] if index + 1 < len(actions) else None
                        widget.removeAction(action)
                        widget.insertAction(next_action, proxy)
                proxy.setEnabled(bool(connection.owners))

        def save(self, *, owner=None, as_new=False, after=None):
            owner = owner or connection.active_owner()
            if as_new or owner.project.path is None:
                default = owner.project.path or owner.export_root / owner.document_id / (owner.doc.Name + '.caepre')
                path, _ = QtWidgets.QFileDialog.getSaveFileName(main, '프로젝트 저장', str(default),
                                                              'CAE 프로젝트 (*.caepre)')
                if not path: return False
                if not path.lower().endswith('.caepre'): path += '.caepre'
                previous = owner.project.path
                owner.project.path = Path(path).resolve()
            else: previous = owner.project.path
            submitted_session = owner.session_id
            controller = _motion_controller(connection, owner)
            editor_version = controller.editor_token() if controller is not None else None
            def saved(value):
                if value.get('status') == 'FAILED':
                    owner.project.path = previous
                    connection.message.setText('저장하지 못했습니다. 이전 프로젝트와 현재 편집을 유지합니다. ' + value['error'].get('message', ''))
                    self.closing = False
                    return
                # Native FCStd file paths did not change. The editable state is
                # safely published in .caepre, so the native close prompt must
                # not offer a second unbundled save of the same state.
                current = _motion_controller(connection, owner)
                if (owner.closed or owner.session_id != submitted_session or not self.saved(owner)
                        or (current.editor_token() if current is not None else None) != editor_version):
                    self.closing = False
                    connection.message.setText('요청한 내용은 저장했지만 대기 중 편집이 바뀌었습니다. '
                        '새 편집은 열린 상태로 유지합니다. 다시 저장하거나 닫기를 선택하세요.')
                    return
                Gui.getDocument(owner.doc.Name).Modified = False
                if after: after()
            try:
                connection.submit_native('document.save', {}, on_done=saved, owner=owner)
            except Exception:
                owner.project.path = previous
                raise
            return True

        def trigger(self, name):
            if not connection.owners:
                self.replacements[name][0].trigger(); return
            if name == 'Std_Save': self.save(); return
            if name == 'Std_SaveAs': self.save(as_new=True); return
            if name in ('Std_SaveAll', 'Std_CloseAll'):
                owners = [item[0] for item in connection.owners.values()]
                if name == 'Std_SaveAll':
                    def advance():
                        if owners: self.save(owner=owners.pop(0), after=advance)
                    advance()
                else: self.close_owners(owners, lambda: self.replacements[name][0].trigger())
                return
            owner = connection.active_owner()
            if name == 'Std_Close':
                self.close_owners([owner], lambda: self.replacements[name][0].trigger()); return
            if name == 'Std_Export':
                owner.before_design_action('native export')
                selected = Gui.Selection.getSelection()
                if not selected: raise ValueError('Select the actual native objects to export')
                for obj in selected:
                    if obj.Document is not owner.doc or not hasattr(obj, 'Shape') or obj.Shape.isNull() or not obj.Shape.isValid():
                        raise ValueError('Invalid/foreign selected geometry cannot be exported; the editable draft is retained')
                self.replacements[name][0].trigger()

        def prepare_reconnect(self, owners, after):
            if self.closing: return
            self.closing = True
            pending, accepted = list(owners), []
            def advance():
                if not pending:
                    if any(_close_version(owner, connection) != version for owner, version in accepted):
                        self.closing = False
                        connection.message.setText('다시 연결 준비 중 편집이 바뀌었습니다. 현재 문서와 편집을 유지합니다.'); return
                    self.closing = False; after(); return
                owner = pending.pop(0)
                controller = _motion_controller(connection, owner)
                from .shell_controls import has_unsaved_editor
                if (controller is None or not controller.has_unsaved_editor()) and not has_unsaved_editor(connection, owner):
                    advance(); return
                version = _close_version(owner, connection)
                choice = QtWidgets.QMessageBox.question(main, '다시 연결하기 전에 편집을 저장하시겠습니까?',
                    owner.doc.Label + '\n저장하면 미완성 입력도 유지됩니다. 버리면 마지막 저장한 편집으로 돌아갑니다.',
                    QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
                    QtWidgets.QMessageBox.Save)
                if choice == QtWidgets.QMessageBox.Cancel:
                    self.closing = False; return
                if _close_version(owner, connection) != version:
                    self.closing = False; connection.message.setText('편집이 바뀌었습니다. 현재 문서와 편집을 유지합니다.'); return
                if choice == QtWidgets.QMessageBox.Discard:
                    accepted.append((owner, version)); advance(); return
                try:
                    def saved_choice():
                        accepted.append((owner, _close_version(owner, connection))); advance()
                    if not self.save(owner=owner, after=saved_choice): self.closing = False
                except Exception as error:
                    self.closing = False; connection.message.setText(str(error))
            advance()

        def close_owners(self, owners, after):
            if self.closing: return
            self.closing = True
            pending = list(owners)
            accepted = []
            def unchanged(choice):
                owner, session, version = choice
                return not owner.closed and owner.session_id == session and _close_version(owner, connection) == version
            def advance():
                if not pending:
                    if not all(unchanged(choice) for choice in accepted):
                        self.closing = False
                        connection.message.setText('닫기 선택 후 편집이 바뀌었습니다. 모든 문서를 열어 둡니다. '
                            '새 편집을 확인한 뒤 다시 닫으세요.')
                        return
                    for owner, _, version in accepted:
                        self.approved_close[owner.document_id] = version
                        Gui.getDocument(owner.doc.Name).Modified = False
                    self.closing = False
                    after(); return
                owner = pending.pop(0)
                if owner.closed: advance(); return
                try: owner.before_design_action('close')
                except Exception as error:
                    self.closing = False; connection.message.setText(str(error)); return
                decision = (owner, owner.session_id, _close_version(owner, connection))
                if self.saved(owner):
                    accepted.append(decision)
                    advance(); return
                choice = QtWidgets.QMessageBox.question(main, '프로젝트를 저장하시겠습니까?',
                    owner.doc.Label + '\n관절과 운동의 미적용 편집을 포함해 저장한 뒤 닫으시겠습니까?',
                    QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
                    QtWidgets.QMessageBox.Save)
                if choice == QtWidgets.QMessageBox.Cancel:
                    self.closing = False; return
                if not unchanged(decision):
                    self.closing = False
                    connection.message.setText('닫기 확인 중 편집이 바뀌었습니다. 새 편집을 열어 둡니다. '
                        '현재 내용을 확인한 뒤 다시 선택하세요.')
                    return
                if choice == QtWidgets.QMessageBox.Discard:
                    # Do not clear native dirty state if a later document's
                    # prompt cancels Close All.
                    accepted.append(decision)
                    advance(); return
                try:
                    def saved_choice():
                        accepted.append((owner, owner.session_id, _close_version(owner, connection)))
                        advance()
                    if not self.save(owner=owner, after=saved_choice): self.closing = False
                except Exception as error:
                    self.closing = False; connection.message.setText(str(error))
            advance()

        def eventFilter(self, watched, event):
            if event.type() == QtCore.QEvent.Close:
                if watched in self.bypass:
                    self.bypass.remove(watched); return False
                is_main = watched is main
                is_view = isinstance(watched, QtWidgets.QMdiSubWindow)
                if (is_main or is_view) and connection.owners:
                    if is_view:
                        area = watched.mdiArea()
                        if area is not None: area.setActiveSubWindow(watched)
                        try: owners = [connection.active_owner()]
                        except ValueError: return False
                    else: owners = [item[0] for item in connection.owners.values()]
                    if all(self.approved_close.get(owner.document_id) == _close_version(owner, connection) for owner in owners):
                        return False
                    event.ignore()
                    def proceed():
                        self.bypass.add(watched)
                        QtCore.QTimer.singleShot(0, watched.close)
                    self.close_owners(owners, proceed)
                    return True
            # The native selector is a combo containing workbench IDs. Restore
            # before mouse/keyboard interaction, instead of reacting only after
            # FemWorkbench has already been activated.
            if event.type() in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.KeyPress) and isinstance(watched, QtWidgets.QComboBox):
                try:
                    choices = {watched.itemData(i) for i in range(watched.count()) if isinstance(watched.itemData(i), str)}
                    if choices & workbenches:
                        connection.active_owner().before_design_action('workbench switch')
                except Exception as error:
                    connection.message.setText(str(error)); return True
            return False
    return Guards()


def project_panel(connection, owner):
    QtWidgets, QtCore = connection.QtWidgets, connection.QtCore
    panel = QtWidgets.QWidget(); layout = QtWidgets.QVBoxLayout(panel)
    state = QtWidgets.QLabel(); state.setWordWrap(True); layout.addWidget(state)
    table = QtWidgets.QTableWidget(0, 4)
    table.setHorizontalHeaderLabels(['Job', 'Frozen input', 'State when retained', 'Design generation'])
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    table.horizontalHeader().setStretchLastSection(True); layout.addWidget(table, 1)
    controls = QtWidgets.QHBoxLayout()
    def refresh():
        if owner.closed: panel.setEnabled(False); return
        info = owner.project.descriptor()
        state.setText((info['project_file'] or 'Not saved as a Lab project') +
            '\nNative design g' + str(owner.generation) + (' · modified' if not _saved(owner) else ' · saved') +
            ('\n' + info['save_error'] if info['save_error'] else '') + '\nEngineering release: UNKNOWN')
        links = info['links']; selected = table.currentRow()
        table.setRowCount(len(links))
        for row, link in enumerate(links):
            values = [link['job_id'], link['origin'].get('input_id', ''), link.get('state_when_recorded', ''), link['origin'].get('generation', '')]
            for col, value in enumerate(values): table.setItem(row, col, QtWidgets.QTableWidgetItem(str(value)))
        if 0 <= selected < len(links): table.selectRow(selected)
    def job():
        row = table.currentRow()
        if row < 0: raise ValueError('Select a retained calculation')
        return table.item(row, 0).text()
    for text, action in [('Refresh', refresh), ('Save', lambda: connection.guards.save(owner=owner)),
            ('Save as…', lambda: connection.guards.save(owner=owner, as_new=True)),
            ('Runner / diagnostics', lambda: connection.open_runner(job())),
            ('Open exact result in Post', lambda: connection.open_post(job())),
            ('Retain current job state', lambda: connection.submit_native('pre.links.record', {'job_id': job()}, owner=owner,
                                                                         on_done=lambda result: refresh()))]:
        button = QtWidgets.QPushButton(text)
        def clicked(checked=False, action=action):
            try: action()
            except Exception as error: state.setText(str(error))
        button.clicked.connect(clicked); controls.addWidget(button)
    layout.addLayout(controls); refresh()
    return panel
