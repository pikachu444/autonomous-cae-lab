"""Known generated captions only; saved/user strings remain untouched."""
from copy import deepcopy
from apps.research import study_presentation as labels


def generated():
    return {'title':'Follow-up — Joriginal','draft':{'question':labels.LEGACY_QUESTION,
        'evidence':[{'id':'Eresult','kind':'result','label':'Joriginal','note':labels.LEGACY_NOTE,
            'reference':{'kind':'result','job_id':'Joriginal'}}]}}


def test_known_generated_text_is_displayed_in_korean_without_rewriting_source():
    document=generated();before=deepcopy(document);draft=document['draft'];row=draft['evidence'][0]
    assert labels.title(document)==labels.TITLE
    assert labels.question(document,draft)==labels.QUESTION
    assert labels.question_value(document,draft,labels.QUESTION)==labels.LEGACY_QUESTION
    assert labels.evidence_label(row)==labels.LABEL and labels.evidence_note(row)==labels.NOTE
    assert document==before


def test_user_titles_questions_labels_and_notes_remain_exact():
    document=generated();document['title']='시험 조건 A 검토'
    draft=document['draft'];draft['question']='사용자가 이미 고친 연구 질문'
    row=draft['evidence'][0];row.update(label='원 시험 비교',note='이미 작성한 판단 메모')
    assert labels.title(document)=='시험 조건 A 검토'
    assert labels.question(document,draft)=='사용자가 이미 고친 연구 질문'
    assert labels.evidence_label(row)=='원 시험 비교' and labels.evidence_note(row)=='이미 작성한 판단 메모'
    assert labels.question_value(document,draft,'새 질문')=='새 질문'


def test_unrelated_lookalike_title_does_not_trigger_generated_document_translation():
    document=generated();document['title']='Follow-up — Jother'
    assert labels.title(document)=='Follow-up — Jother'
    assert labels.question(document,document['draft'])==labels.LEGACY_QUESTION
