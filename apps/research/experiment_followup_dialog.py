"""Explicit next-observation selection from a retained analysis; no execution."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QListWidget,QListWidgetItem,
    QPlainTextEdit,QDialogButtonBox)
from caelab.experiment_analysis_reporting import suggested_questions


class NextObservationDialog(QDialog):
    def __init__(self,result,parent=None):
        super().__init__(parent)
        self.setWindowTitle('다음 관측과 시험 질문');self.resize(760,590)
        layout=QVBoxLayout(self)
        explanation=QLabel('보존한 진단을 근거로 확인할 질문을 고르거나 직접 작성하세요. 판단과 새 계산은 자동으로 만들지 않습니다.')
        explanation.setWordWrap(True);layout.addWidget(explanation)
        layout.addWidget(QLabel('질문 예시 — 선택하면 아래에서 수정할 수 있습니다.'))
        self.questions=QListWidget();self.questions.setWordWrap(True);self.questions.addItems(suggested_questions(result))
        self.questions.setCurrentRow(-1);layout.addWidget(self.questions,1)
        self.question=QPlainTextEdit();self.question.setPlaceholderText('확인할 질문을 직접 작성하거나 위 예시를 선택하세요.')
        self.question.setMaximumHeight(100);layout.addWidget(self.question)
        layout.addWidget(QLabel('이 질문에서 참고할 기존 관측 — 선택 사항, 새 관측값이 아닙니다.'))
        self.observations=QListWidget();self.observations.setWordWrap(True);layout.addWidget(self.observations,1)
        p=result.get('experiment_analysis',{}).get('source_problem',{})
        entries=p.get('fit_input',{}).get('inputs',{}).get('experiments',[])
        for i,entry in enumerate(entries):
            obs=entry.get('observations',{})
            role='별도 확인' if entry.get('role')=='holdout' else '피팅'
            # The ordinal stays unambiguous even when saved trials share a name.
            label=str(i+1)+'. '+(entry.get('title') or entry.get('name') or '시험')+' / '+entry.get('response','')+' ['+obs.get('unit','')+'] / '+role
            item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,entry['id'])
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Unchecked)
            self.observations.addItem(item)
        self.observations.setVisible(bool(entries))
        self.note=QPlainTextEdit();self.note.setMaximumHeight(80)
        self.note.setPlaceholderText('시험 조건 또는 고정 계수에 대한 확인 목적 (선택 사항)');layout.addWidget(self.note)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText('Study에 기록')
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.questions.currentTextChanged.connect(self.question.setPlainText)
        self.question.textChanged.connect(lambda:self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(self.question.toPlainText().strip())))
        # QListWidget taking initial focus can select its first row on show.
        self.question.setFocus(Qt.FocusReason.OtherFocusReason)

    def selection(self):
        selected=[self.observations.item(i) for i in range(self.observations.count())
            if self.observations.item(i).checkState()==Qt.CheckState.Checked]
        note=self.note.toPlainText().strip()
        if selected:note+='\n참고한 기존 관측: '+'; '.join(item.text() for item in selected)
        return {'question':self.question.toPlainText().strip(),'note':note.strip(),
            'observation_ids':[item.data(Qt.ItemDataRole.UserRole) for item in selected]}


def choose_next_observation(result,parent):
    dialog=NextObservationDialog(result,parent)
    return dialog.selection() if dialog.exec()==QDialog.DialogCode.Accepted else None
