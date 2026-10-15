# 세 결함과 교정 계약

## 1. VTK 축값과 물리 의미를 분리

첫 인도는 DATA_TIME이면 semantics와 무관하게 ‘실제 시각’으로 표시했다. 잘못된 표시다.
C1은 report_image_axis의 동일 caption 함수를 Report 본문/preview/Markdown/PDF/원자료 대화상자에서
사용한다. DATA_TIME_STEP은 값의 존재를 나타낼 뿐 물리시간 선언을 대신하지 않는다.

| 보존 선언 | 표시와 수용 |
|---|---|
| 명시한 물리시간 의미 + s/ms/us/min/h | 물리시간 및 실제 값/단위. 별도 시간 기준 문자열도 보존 |
| STATIC_LOAD_PARAMETER 또는 load_parameter + 1 | 정적 하중 매개변수, 물리시간 아님 |
| DIMENSIONLESS_MODEL_TIME + 1 | 무차원 모델시간, 물리시간 아님 |
| 의미 None/빈값/UNKNOWN | 축 의미 미제공. 단위가 s이어도 물리시간을 추정하지 않음 |
| static={step,increment,load_parameter}, time=None | 정적 단계/증분/하중 매개변수. 0초로 바꾸지 않음 |
| frozen_clock | 고정 관측 축을 별도로 표시. 원래 static/이전 처리 결과의 고정 축도 함께 보존 |

reserved 정적/모델시간에 s를 쓰거나 알려진 시간 의미에 1을 쓰는 조합은 거절한다. static+time,
frozen/time 값·단위·의미 충돌, 필터가 입력 축을 다른 물리 의미로 변경하는 선언도 거절한다.
새 시각 보간/변환/계산은 하지 않는다. 기존 metadata/recipe가 제공한 것만 읽는다.

축 선언은 현재 Post 선택/현재 upstream history position에서 보충하지 않는다. 기존
source_records/retained_analyses를 재사용하여 각 bindings의 정확한 해시가 가리키는 과거 record를
찾고 summary.declarations와 그 입력 native_metadata를 축 문맥으로 복사한다. comparison recipe의
원 frozen_clock과 출력 선언 관계도 검사한다. adoption 단계에서 이 문맥을 다시 원 저장본과 대조한다.
이후 Report caption은 보존 snapshot만 읽는다. 원파일 삭제 뒤 current 선택으로 복구하거나 의미를
추정하지 않는다. 유효하지 않은 새 채택은 기존 asset, 본문, Study 판단, Undo 이력을 대체하지 않는다.

## 2. 단일 필드 block 색상 계약

다른 block별 의미를 모두 캡션에 합치는 방식 대신 이번 bounded single-field 경로에서는 전역 필드와
동일함을 검증할 수 없는 block 설정을 거절한다. 검토한 API는 ParaView 5.13.2와 6.2.0이며, 설치된
runtime의 정확한 version과 SM property type/width를 검사한다. 미검토 버전은 캡처 채택을 거절한다.

실제 property는 BlockColorArrayNames(3개씩 selector/association/array), BlockLookupTables,
BlockColors(4개씩), BlockMapScalars, BlockInterpolateScalarsBeforeMappings, BlockOpacities,
BlockUseSeparateColorMaps(각 2개씩)다. ith LUT와 ith field triple의 selector 대응은 Kitware 원문에
있다. VectorMode/VectorComponent는 LUT의 속성이다. 자세한 태그/원문 위치는 SOURCES.md에 기록했다.

‘현재 선택된 block’인 SelectedBlockSelectors를 검사 대상으로 쓰지 않는다. 모든 설정된 selector의
field/association 및 실제 LUT proxy 동일성을 확인한다. block LUT가 전역 LUT와 같은 객체면 성분,
범위, mapping이 같은 실제 상태다. 별도 LUT는 숫자/색이 우연히 같아도 동등하다고 간주하지 않는다.
BlockColors 또는 직접 RGB, 다른 opacity/interpolation도 이 경로에서 거절한다. reset/빈 설정과
전역 동일 array/association/shared LUT/전역 동일 표시 설정은 허용한다.

단순하고 보수적인 경계: selector reachability/inheritance를 임의 재현하지 않는다. 현재 보이지 않는
block의 다른 override도 해제하기 전에는 거절한다. block 전체 의미를 지원했다고 주장하지 않는다.
캡처 전후에 이 audit를 포함해 scene를 대조하므로 캡처 도중 override 변경 역시 새 그림 채택을 막는다.
SaveScreenshot은 기존 Workspace.export가 호출하며 다른 캡처 backend/store는 만들지 않았다.

## 3. 실제 원자료 검토와 불변 Report

보고서 그림의 확인 창을 native 원자료 열기 완료로 세지 않는다. 기존 Report content가 반환한
asset hash/reference와 snapshot을 먼저 확인한다. 그 다음 project/workspace/원입력/결과 pin 및
정확한 record/recipe/bindings를 검사한다.

살아 있는 원창은 session/content/view generation, saved revision, applied record가 일치해야 한다.
현재 선택이 바뀌었거나 pending native 편집이 있으면 원창을 변경하지 않고 거절한다. native
post.report_image_verify는 owner 스레드에서 pin/기록을 다시 검사하고 현재 source의 Fetch 데이터와
저장 결과를 기존 정확 VTK fingerprint로 대조한다. 단순 배열 개수/범위 비교가 아니다. 이 명령은
읽기 전용이며 source/time/camera/field/사용자 입력 파일을 변경하지 않는다.

연결된 정확 owner는 기존 desktop.launch_tool(post,document_id)를 통해 활성화한다. 검증 뒤와
활성화 뒤에도 generation/pin을 검사한다. 문서 activation capability가 없으면 SOURCE_VERIFIED와
activation NOT_PERFORMED로 구분한다. 자동 창 활성화를 성공했다고 꾸미지 않는다.

닫힌 원창의 PID가 확실히 종료된 때만 기존 helper/Qt launch claim/post --project를 재사용한다.
CLI --report-image는 새 project 입력 방식이 아니라 정확 Report asset을 조회해 기존 --project에
전달하는 최소 진입점이다. 원파일 복구를 허용하지 않는 restore_workspace 호출 후 저장된 proxy/view를
선택하고 기존 Render를 호출한다. 새 reader/view/renderer를 만들지 않는다. 과거 카메라 자동재구성은
하지 않는다. 정확한 복구 proxy/view가 없다면 임의 결과로 대체하지 않고 실패한다.

같은 기존 transient launcher 디렉터리 안 report-origin.json은 bounded 전달 요청이다. Report 저장소나
추가 capture 저장소가 아니다. 기존 launch claim/marker는 중복 실행과 미확인 launch 재실행을 막는 데
재사용한다. confirmed process-creation failure 전에는 marker를 정리할 수 있지만 spawn 이후 불확실성은
남긴다. 실제 native owner/data 응답으로만 confirmed 처리한다.

| 상태 | 뜻 |
|---|---|
| LAUNCH_REQUESTED | helper/native 실행 요청. 실제 원자료 성공 미확인 |
| LAUNCH_UNCONFIRMED | 연결/기존 요청 상태 확인만 함. 재실행하지 않음 |
| SOURCE_VERIFIED | native exact data 검증. 자동 창 활성화는 별도 |
| SOURCE_OPENED | exact native 검증 + 확인한 기존 활성화 또는 child의 실제 launch 확인 |
| FAILED/UNKNOWN/불일치 | 이전 Report 유지. 다른 창/다른 파일로 fallback하지 않음 |

helper가 시작됐으나 설치 실행파일 선택 취소/원파일 경쟁 변경/native startup 오류가 발생하면 기존
helper 오류창/native 로그에 실패를 남긴다. Report 측은 연결된 owner 증거가 없으므로 미확인으로
표시한다. helper PID만으로 정확한 실패 원인이나 native 성공을 추정하지 않는다. 원파일 복원,
실행파일/오류창 확인, 기존 원창 연결 복구가 필요하다. 새 status backend는 만들지 않았다.

## 기존 asset 호환성과 한계

새 receipt는 snapshot format /2이며 exact axis_context와 block audit를 요구한다. /1은 이미 보관한
자산 읽기만 지원한다. caption은 보존된 축 의미를 재해석하여 잘못된 ‘실제 시각’을 쓰지 않고,
block 의미 미검증 경고를 붙인다. 과거 snapshot/PNG byte/hash를 몰래 마이그레이션하지 않는다.
/1 receipt의 새 채택은 거절하고 C1 native에서 다시 캡처하도록 안내한다. /1 자산의 원자료 열기는
현재 native 검증을 새로 거치지만 과거 이미지의 block 의미 검증을 소급 주장하지 않는다.

첫 인도의 단일 RenderView/저장·적용된 3D filter 또는 공간 comparison, PNG 5 MiB, 최대 pixel 수,
정확 데이터 대조 512 MiB 제한은 유지한다. 일반 임의 PNG, 지원 밖 pipeline/VTK 유형, raw reader를
수치결과 증거로 새로 승인하는 경로가 아니다. 전체 Workbench bootstrap/native 배포는 이 선별 소스와
Linux 검사만으로 증명하지 않는다. 공학 승인·수치 검증·프로그램 동작은 별개다.
