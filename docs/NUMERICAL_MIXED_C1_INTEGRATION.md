# C1 통합 계약과 적용 순서

요청: PRO-NUMERICAL-MIXED-DOMAINS-20261015-01-C1.
원 ZIP SHA256: `7c387e2384931deefe41dfc1d40257dbc624d19deae8b1ca19c788d46f115723` (897767 bytes).
원 소스: `ec502f3cdfa24e0b09cf1af672e2b4417d98bfb9`, pinned `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
현재 자료: 첨부 current-public-common.zip의 읽기 전용 working-copy 파일과 고정 `68aa3e1c490e761226529ad7e781bc159c69ca8f`에서 추가 확인한 네 파일. 다른 팀 working tree를 대체하지 않는다.

## 서로 다른 두 patch 기준 — 둘 다 적용하지 않는다

**A. 원 혼합 변수 ZIP의 11 전용 파일과 15 공통 patch를 이미 합성한 사본**

`c1.patch`를 확인하고 적용한다. 이는 그 상태에 대한 공통 5개 파일의 C1 증분만 담는다. 그 다음 `files/`의 전용 5개 파일을 같은 상대 경로에 복사한다. `variable_binding.py`만 기존 전용 소스의 교체이며, 나머지 검사·예제·문서는 새 파일이다. `integration.patch`는 적용하지 않는다.

```text
git apply --check C1/c1.patch
git apply C1/c1.patch
```

**B. 아직 원 ZIP을 통합하지 않은 현재 root 공통 소스**

원 ZIP의 전용 파일을 쓰되 `variable_binding.py`는 C1 `files/`의 것으로 사용한다. 원 ZIP의 공통 patch 중 **`caelab/model_parameters.py` 절은 적용하지 않는다.** 그 절을 포함해 이번 공통 5개 경계를 `integration.patch`로 적용한다. 현재 자료의 `model_parameters.py`는 원 mixed 변경 전이므로 이 파일의 hunk에는 원 typed admission과 C1 교정이 함께 들어 있다. 다른 네 파일에는 C1 변경만 있다.

원 ZIP의 나머지 14개 공통 변경은 root가 최신 소스와 별도로 통합한다. C1은 그 변경이나 Portable/Data/Expert/GUI working-copy를 다시 제공하거나 통째 교체하지 않는다. 기존 변경을 이미 합성한 파일에 이 B patch를 중복 적용하지 않는다.

```text
git apply --check C1/integration.patch
git apply C1/integration.patch
```

두 경로 모두 `files/`에는 공통 원파일 전체가 없다. 해시가 다른 파일은 원본 확인 없이 덮지 않는다. `MANIFEST.json`의 raw SHA256와 LF-normalized SHA256로 내용 변경과 CRLF/LF 차이를 구별한다. root의 현재 추가 변경은 해당 hunk만 수동 병합하고 다시 검사한다.

## 실제 변경 범위

| 경계 | C1 변경 |
|---|---|
| `caelab/variable_binding.py` | checked description에서 ID로 numeric Candidate 선택, enum 등록 안내, 기존 descriptor 수 한도 함수 재사용 |
| `caelab/model_parameters.py` | 전체 descriptor 검증·해시는 유지하고 Candidate view에서만 enum 제외 |
| `caelab/engine.py` | 등록 시 위 선택 helper 호출. 기존 probe/effect/registry write는 그대로 |
| `caelab/model_doe.py` | 저장 Plan을 읽을 때 전체 descriptor의 유효성·해시를 유지하고 numeric advertised map만 필터 |
| `schemas/model-doe-plan.schema.json`, `schemas/optimization-plan.schema.json` | ODE의 기존 숫자 32개 + 정확한 solver-method enum 1개 저장 슬롯만 보존 |

뒤의 세 경계는 실제 재현 중 드러난 추가 연결 결함을 고친다. 원 describe 거절만 없애면 저장 DOE가 enum에서 `lower/upper`를 읽다 실패한다. 또한 원래 가능하던 숫자 descriptor 32개에 enum 하나가 추가되면 저장 schema의 32개 한도에 걸린다. 새 schema는 다른 backend의 32개 한도, 숫자 32개 한도, 숫자 변수·후보 수·예산 한도를 늘리지 않는다. ODE typed descriptor의 기존 64 숫자 + enum 한도도 바꾸지 않는다. 64개 숫자 descriptor를 legacy 캠페인으로 가져오는 별도 확장은 이번에 하지 않는다.

## 소비 API

```python
from caelab.model_parameters import describe
from caelab.variable_binding import legacy_numeric_candidate

full = describe(lab, backend, settings)
# full['descriptors']: enum 포함 전체 목록. source 해시에 항상 이 목록을 사용.
# full['candidates']: legacy 숫자 후보 목록. 전체 목록과 zip/enumerate로 대응 금지.
selected = legacy_numeric_candidate(full, input_id)
# source/path/descriptor는 describe가 검증한다. 이 helper는 재계산/적용/저장을 하지 않는다.
# 실제 등록은 Lab.register_model_parameter가 기존 probe/effect 뒤에 수행한다.
```

`legacy_numeric_candidate`는 enum ID를 선택하면 CapabilityUnavailable과 typed Request Plan 안내를 반환한다. 미광고 ID·중복 Candidate·선택된 숫자 descriptor와 값/단위/범위가 다른 Candidate는 거절한다. enum 표시명/선택지 순서/실제 값은 source에서 지우지 않는다. source 변경 시 numeric binding도 무효가 된다.

`descriptor_limit(backend)`는 기존 ODE 65 / 나머지 32 정책이다. frozen DOE 읽기는 이 한도와 저장 설명을 검증할 뿐 adapter의 describe/bind/probe/solve를 부르지 않는다. 새 owner, store, setter, scheduler, optimizer, AST, savehook을 만들지 않았다.

## 검사와 증거의 구분

`validation/status.json`은 명령, 소스 기준, 실행 환경, 통과/건너뜀/실패를 기록한다. `validation/actual-c1/`는 실제 작은 Lab DOE의 원 입력과 결과다. `validation/numeric-reference-comparison.json`은 원 baseline과 C1의 같은 네 numeric 후보/전체 온도 이력을 대조한다. 원 mixed ZIP의 실패도 별도 로그로 남긴다. 이 예제는 원 evaluation ODE를 Lab에서 시험하기 위한 명시적 예제 facade를 사용하며, 기본 backend 등록을 새로 제공하지 않는다.

새 C1 집중 검사에는 실제 ODE DE, 각 저장 입력의 해석해 비교, enum stale 거절, source 및 설정·선언 위치 비교, 읽기 중 실행 차단과 별도 프로세스 이동 저장소 읽기가 포함된다. 원 mixed 76개는 실제 ODE, enum 입력, DE, owner 채택/저장/cold와 continuous 분석 경계를 다시 검사한다. 기존 numeric/owner 검사와 C2 근거 누락 4건의 before/after도 별도로 기록한다.

`c1.patch`는 원 ZIP 합성본에, `integration.patch`는 첨부 현재 공통 파일 및 명시한 고정 source bytes에 각각 `git apply --check`/실제 적용/최종 hash 대조를 수행했다. 실행 검사는 원 ZIP 합성본 + C1과 그 깨끗한 재적용 사본에서 수행한다. 현재 working-copy 전체를 최종 통합·실행했다는 뜻이 아니다.

Windows·Qt·FELUPE·전체 HTTP/제품 수용과 최신 main 통합/독립 검토는 NOT_RUN이다. 기존 C2 evidence/detail/CAS/saved publication hook, Data canonical 처리, Portable 사본 연결, Workbench, GUI, domain_candidate의 기존 기대값은 변경하지 않는다. FN-20-01 전체 GUI나 UQ/adjoint/MDO/mapping 완료로 확대하지 않는다.
