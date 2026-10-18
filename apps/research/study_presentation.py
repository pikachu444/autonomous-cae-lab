"""Display only the known legacy generated result-followup captions in Korean."""
LEGACY_QUESTION='What does this retained result support, and what observation could distinguish competing explanations?'
LEGACY_NOTE='Exact retained input and result; no engineering approval inferred.'
TITLE='계산 결과 검토'
QUESTION='이 결과가 뒷받침하는 판단은 무엇이며, 다음 시험에서 무엇을 확인할까요?'
LABEL='보존한 계산 결과'
NOTE='원 입력과 계산 결과를 보존했습니다. 공학적 승인을 뜻하지 않습니다.'
STATUS_LABELS = {'UNKNOWN': '미판단', 'PROVISIONAL': '잠정 판단', 'SUPPORTED': '지지 자료 있음',
    'CONFLICTED': '자료가 상충함', 'REFUTED': '반증됨', 'REJECTED': '기각',
    'NOT_RELEASED': '미승인', 'PLANNED': '확인 예정', 'OBSERVED': '관찰 기록됨'}


def generated_evidence(row):
    ref=row.get('reference',{})
    return (row.get('kind')=='result' and ref.get('kind')=='result'
        and isinstance(ref.get('job_id'),str) and row.get('label')==ref['job_id']
        and row.get('note')==LEGACY_NOTE)


def generated_document(document):
    return any(row.get('kind')=='result' and row.get('reference',{}).get('kind')=='result'
        and row.get('note')==LEGACY_NOTE and isinstance(row['reference'].get('job_id'),str)
        and document.get('title')=='Follow-up — '+row['reference']['job_id']
        for row in document.get('draft',{}).get('evidence',[]))


def title(document):
    return TITLE if generated_document(document) else document['title']


def question(document,draft):
    value=draft.get('question','')
    return QUESTION if generated_document(document) and value==LEGACY_QUESTION else value


def question_value(document,draft,text):
    # Editing another field does not translate or rewrite the saved original.
    return draft.get('question','') if text==question(document,draft) else text


def evidence_label(row):return LABEL if generated_evidence(row) else str(row.get('label','자료'))
def evidence_note(row):
    return NOTE if (row.get('kind')=='result' and row.get('reference',{}).get('kind')=='result'
        and row.get('note')==LEGACY_NOTE) else str(row.get('note',''))
