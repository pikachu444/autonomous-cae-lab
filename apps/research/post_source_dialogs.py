"""Explicit changed-result preview and fresh native Post project handoff."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import uuid

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QDialog, QFileDialog, QInputDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QPlainTextEdit)
from apps.desktop_post.source_change import preview_change


def inspect_replacement(client, input_id, original):
    from .desktop import _executable
    context = client.desktop_context()
    receipt = client.native_input(input_id)
    executable = _executable(context, 'paraview_executable', interactive=False)
    pvpython = executable.with_name('pvpython.exe' if executable.suffix.lower() == '.exe' else 'pvpython')
    folder = Path(context['export_root']) / 'desktop' / ('source-preview-' + uuid.uuid4().hex)
    folder.mkdir(parents=True, exist_ok=False)
    incoming, result = folder/'input.json', folder/'preview.json'
    incoming.write_text(json.dumps(receipt, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    script = Path(__file__).resolve().parents[1] / 'desktop_post' / 'source_repair.py'
    with (folder/'stdout.log').open('wb') as stdout, (folder/'stderr.log').open('wb') as stderr:
        completed = subprocess.run([str(pvpython), '--force-offscreen-rendering', str(script), str(incoming), str(result)],
            stdout=stdout, stderr=stderr, timeout=120, check=False,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if completed.returncode or not result.is_file():
        raise RuntimeError('새 결과를 읽지 못했습니다. 기존 프로젝트는 그대로입니다. 진단 파일: ' + str(folder/'stderr.log'))
    return {'input_id': input_id, 'receipt': receipt, 'executable': str(executable),
        'impact': preview_change(original, receipt, json.loads(result.read_text(encoding='utf-8')))}


def open_fresh_project(client, input_id, output, *, prepared=None, executable=None, expected=None):
    """Reuse native preparation/save, then open only that new saved project."""
    from .desktop import _arguments, _post
    native = ['--executable', executable] if executable else []
    if prepared is None:
        if expected is not None:
            current = client.native_input(input_id)
            if any(current.get(key) != expected.get(key) for key in ('id', 'path', 'format', 'source_pins', 'native_metadata')):
                raise ValueError('미리보기 후 등록 자료가 바뀌었습니다. 새 자료를 다시 미리보기 하세요.')
        prepared = _post(client, _arguments(['--service', client.url, 'post', '--input-id', input_id,
            '--output', output, '--prepare-only', *native]))
    try:
        launched = _post(client, _arguments(['--service', client.url, 'post', '--project', prepared['project'], *native]))
        return {'prepared': prepared, 'launched': launched}
    except Exception as error:
        return {'prepared': prepared, 'error': str(error)}


class SourceUpdateDialog(QDialog):
    def __init__(self, window, source):
        super().__init__(window)
        self.window = window; self.source = deepcopy(source); self.client = window.client
        self.context = (window.document_id, window.session_id, source['source_ref'], source['source_revision'])
        self.preview = None; self.prepared = None; self._launched = False; self._busy = False; self._applying = False; self._closed = False
        self.setWindowTitle('변경된 자료를 새 프로젝트로 열기'); self.setWindowModality(Qt.WindowModal); self.resize(850, 680)
        layout = QVBoxLayout(self)
        self.original = QLabel('기존 원자료: ' + source.get('entry_name', source.get('label', '결과 파일')))
        self.original.setWordWrap(True); layout.addWidget(self.original)
        form = QFormLayout(); self.roots = QComboBox(); self.file = QLineEdit(); self.folder = QLineEdit()
        self.file.setPlaceholderText('등록 폴더 안의 결과 파일 경로')
        self.file_button = QPushButton('파일 선택…'); self.folder_button = QPushButton('폴더 선택…')
        row = QHBoxLayout(); row.addWidget(self.file, 1); row.addWidget(self.file_button)
        form.addRow('원자료 폴더', self.roots); form.addRow('새 결과 파일', row)
        row = QHBoxLayout(); row.addWidget(self.folder, 1); row.addWidget(self.folder_button)
        form.addRow('새 프로젝트 폴더', row); layout.addLayout(form)
        self.notice = QLabel('새 파일을 읽어 달라진 파일·필드·시각을 확인한 뒤 새 프로젝트를 여세요.')
        self.notice.setWordWrap(True); layout.addWidget(self.notice)
        self.preview_button = QPushButton('변경 내용 미리보기'); layout.addWidget(self.preview_button)
        tabs = self.tabs = QTabWidget(); layout.addWidget(tabs, 1)
        self.files = QTableWidget(0, 2); self.files.setHorizontalHeaderLabels(['파일', '기존 자료와 비교'])
        self.arrays = QTableWidget(0, 4); self.arrays.setHorizontalHeaderLabels(['필드', '위치', '기존 저장 정보', '새 자료 첫 시각'])
        for table, name in ((self.files, '파일'), (self.arrays, '필드')):
            table.setEditTriggers(QTableWidget.NoEditTriggers); table.verticalHeader().hide()
            table.horizontalHeader().setStretchLastSection(True); table.setAlternatingRowColors(True)
            tabs.addTab(table, name)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True); tabs.addTab(self.details, '진단 상세'); tabs.setTabVisible(2, False)
        self.files.setColumnWidth(0, 390); self.arrays.setColumnWidth(0, 160); self.arrays.setColumnWidth(1, 55); self.arrays.setColumnWidth(2, 220)
        self.time = QLabel(); self.time.setWordWrap(True); layout.addWidget(self.time)
        counts = {kind: sum(obj.get('kind') == kind for obj in window._objects()) for kind in ('filter', 'measurement', 'comparison')}
        self.retained = QLabel('이전 프로젝트에 유지: 필터 '+str(counts['filter'])+'개, 측정 '+str(counts['measurement'])+'개, 비교 '+str(counts['comparison'])+'개.\n'
            '새 프로젝트에는 이 자료의 원본만 엽니다. 이전 측정·비교와 물리량 선언을 새 결과로 옮기지 않습니다.')
        self.retained.setWordWrap(True); layout.addWidget(self.retained)
        row = QHBoxLayout(); self.apply_button = QPushButton('새 프로젝트 열기'); self.cancel_button = QPushButton('취소')
        row.addStretch(); row.addWidget(self.apply_button); row.addWidget(self.cancel_button); layout.addLayout(row)
        self.file_button.clicked.connect(self._choose_file); self.folder_button.clicked.connect(self._choose_folder)
        self.preview_button.clicked.connect(self._preview); self.apply_button.clicked.connect(self._apply); self.cancel_button.clicked.connect(self.reject)
        self.file.textChanged.connect(self._edited); self.roots.currentIndexChanged.connect(self._edited)
        self.folder.textChanged.connect(self._folder_edited)
        self._update_buttons(); QTimer.singleShot(0, self._load)

    def _current(self):
        if self._closed or self.window._closed: return False
        source = next((row for row in self.window._sources() if row['source_ref'] == self.source['source_ref']), {})
        return self.window._source_ref == self.source['source_ref'] and self.context == (self.window.document_id, self.window.session_id, source.get('source_ref'), source.get('source_revision'))

    def _call(self, call, accepted, *, applying=False):
        if self._busy or not self._current(): return
        self._busy = True; self._applying = applying; self._update_buttons()
        def guarded():
            try: return {'value': call()}
            except Exception as error: return {'error': str(error)}
        def done(reply):
            self._busy = self._applying = False
            if not self._current():
                self._update_buttons(); return
            if reply.get('error'):
                self.details.setPlainText(reply['error']); self.tabs.setTabVisible(2, True)
                self.notice.setText('작업을 완료하지 못했습니다. 원파일·등록 폴더·ParaView 설정을 확인하세요.\n'
                    '기존 창과 원자료는 유지됩니다. 준비가 실패한 폴더는 보존하며 새 빈 폴더로 다시 시도하세요.')
            else: accepted(reply['value'])
            self._update_buttons()
        if not self.window._call(guarded, done):
            self._busy = self._applying = False; self.notice.setText('진행 중인 문서 작업이 끝난 뒤 다시 누르세요.'); self._update_buttons()

    def _load(self):
        def loaded(value):
            for root in value['roots'].get('roots', []): self.roots.addItem(root.get('path', root['id']), root)
            parent = Path(value['context']['export_root']) / 'desktop'
            folder = parent / '새 후처리 프로젝트'; number = 2
            while folder.exists(): folder = parent / ('새 후처리 프로젝트 '+str(number)); number += 1
            self.folder.setText(str(folder))
            if not self.roots.count(): self.notice.setText('원자료를 읽을 등록 폴더가 없습니다. 등록 폴더를 설정한 뒤 다시 여세요.')
        self._call(lambda: {'roots': self.client.local_roots(), 'context': self.client.desktop_context()}, loaded)

    def _edited(self, *args):
        if self.prepared: return
        self.preview = None; self.files.setRowCount(0); self.arrays.setRowCount(0); self.time.clear(); self._update_buttons()

    def _folder_edited(self, *args):
        self._update_buttons()

    def _choose_file(self):
        root = self.roots.currentData()
        if not root: return
        self._choose_directory(root['id'])

    def _choose_directory(self, root_id, relative='', cursor=0):
        def listed(payload):
            if (self.roots.currentData() or {}).get('id') != root_id: return
            choices = [('상위 폴더', 'parent')] if relative else []
            choices += [(('폴더: ' if item['directory'] else '') + item['name'], item) for item in payload['entries']
                if item['directory'] or item['name'].lower().endswith(('.vtu', '.pvd')) or item['name'] in ('contact-inspection.json','shell_inspection.json','beam_inspection.json')]
            if payload.get('next_cursor') is not None: choices.append(('다음 파일 목록…', 'next'))
            if not choices:
                self.notice.setText('이 폴더에 읽을 후처리 파일이 없습니다.'); return
            name, accepted = QInputDialog.getItem(self, '변경된 원자료 선택',
                '등록 폴더 / ' + (relative or '최상위'), [label for label, _ in choices], editable=False)
            if not accepted or not self._current(): return
            selected = next(item for label, item in choices if label == name)
            if selected == 'parent': self._choose_directory(root_id, relative.rpartition('/')[0])
            elif selected == 'next': self._choose_directory(root_id, relative, payload['next_cursor'])
            elif selected['directory']: self._choose_directory(root_id, selected['relative'])
            else: self.file.setText(selected['relative'])
        self._call(lambda: self.client.local_inputs(root_id, relative, cursor=cursor), listed)

    def _choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, '비어 있는 새 프로젝트 폴더 선택', self.folder.text())
        if folder: self.folder.setText(folder)

    def _preview(self):
        root = self.roots.currentData(); relative = self.file.text()
        if not root or not relative: return
        self._edited()
        self.notice.setText('새 파일의 첫 시각 필드와 전체 시각 목록을 읽는 중… 기존 창은 바꾸지 않습니다.')
        def read():
            receipt = self.client.register_local_input(root['id'], relative)
            return inspect_replacement(self.client, receipt['id'], self.source)
        def loaded(value):
            if ((self.roots.currentData() or {}).get('id'), self.file.text()) != (root['id'], relative):
                self.notice.setText('선택한 파일이 바뀌었습니다. 다시 미리보기를 누르세요.'); return
            self.preview = value; impact = value['impact']
            self.notice.setText('원자료 내용이 달라졌습니다. 새 프로젝트로 열어 연구를 이어갈 수 있습니다.' if impact['content_changed'] else
                '파일 내용은 같습니다. 위치만 바뀌었다면 원파일 다시 연결을 사용하세요. 새 프로젝트로 별도 열 수도 있습니다.')
            self.files.setRowCount(len(impact['files']))
            for index, file in enumerate(impact['files']):
                for column, text in enumerate((file['name'], {'same':'동일', 'changed':'내용 변경', 'added':'추가', 'missing':'새 자료에 없음'}[file['change']])):
                    self.files.setItem(index, column, QTableWidgetItem(text))
            self.arrays.setRowCount(len(impact['arrays']))
            def field(row):
                if row is None: return '없음'
                return str(row['components'])+'성분\n'+str(row.get('units') or '단위 미지정')+'\n범위 '+str(row.get('range', []))
            for index, row in enumerate(impact['arrays']):
                for column, text in enumerate((row['name'], {'POINTS':'점','CELLS':'셀','FIELD':'공통'}.get(row['association'], row['association']), field(row['before']), field(row['after']))):
                    item = QTableWidgetItem(text); item.setToolTip(text); self.arrays.setItem(index, column, item)
            self.arrays.resizeRowsToContents()
            def clock(metadata):
                times = metadata.get('timesteps') or []
                return str(len(times))+'개 ('+str(times[0])+' ~ '+str(times[-1])+')' if times else '시각 기록 없음'
            self.time.setText('시각: 기존 '+clock(impact['before'])+' → 새 자료 '+clock(impact['after'])+'\n'
                '메시: 기존 점 '+str(impact['before'].get('points', '?'))+' / 셀 '+str(impact['before'].get('cells', '?'))+
                ' → 새 자료 점 '+str(impact['after'].get('points', '?'))+' / 셀 '+str(impact['after'].get('cells', '?')))
        self._call(read, loaded)

    def _apply(self):
        if not self.preview or not self._current(): return
        output = self.folder.text(); path = Path(output)
        if self.prepared is None and (not output or path.exists() and (not path.is_dir() or any(path.iterdir()))):
            self.notice.setText('기존 자료를 덮어쓰지 않도록 새 폴더 또는 비어 있는 폴더를 선택하세요.'); return
        prepared = self.prepared
        self.notice.setText('새 자료로 프로젝트를 저장하고 후처리 창을 여는 중…')
        def opened(result):
            self.prepared = result['prepared']
            if result.get('error'):
                self.details.setPlainText(result['error']); self.tabs.setTabVisible(2, True)
                self.notice.setText('프로젝트는 저장했지만 후처리 창을 열지 못했습니다.\n'
                    +self.prepared['project']+'\n저장한 새 프로젝트 열기를 다시 누르세요.')
            else:
                self._launched = True
                self.notice.setText('새 프로젝트를 저장하고 별도 후처리 창 열기를 요청했습니다.\n'+self.prepared['project'])
                self.apply_button.setEnabled(False)
                self.cancel_button.setText('닫기')
        self._call(lambda: open_fresh_project(self.client, self.preview['input_id'], output,
            prepared=prepared, executable=self.preview.get('executable'), expected=self.preview['receipt']), opened, applying=True)

    def _update_buttons(self):
        active = not self._busy and self._current()
        for widget in (self.roots, self.file, self.file_button): widget.setEnabled(active and self.prepared is None)
        self.folder.setEnabled(active and self.prepared is None); self.folder_button.setEnabled(active and self.prepared is None)
        self.preview_button.setEnabled(active and self.prepared is None and bool(self.roots.currentData()) and bool(self.file.text()))
        self.apply_button.setEnabled(active and not self._launched and self.preview is not None and bool(self.folder.text()))
        self.apply_button.setText('저장한 새 프로젝트 열기' if self.prepared else '새 프로젝트 열기')
        self.cancel_button.setEnabled(not self._applying)

    def reject(self):
        if self._applying: return
        self._closed = True; super().reject()
