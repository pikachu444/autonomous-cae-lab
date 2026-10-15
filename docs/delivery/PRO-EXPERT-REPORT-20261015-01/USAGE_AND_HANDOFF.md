# 사용 순서, 통합 소유와 남은 원행

## 사용 순서

1. 기존 Study에 가설·판단·다음 연구를 작성하고 저장한다. 기존 Report의 '저장된 연구 적용…'으로 해당
   저장 Study와 선택된 증거를 가져온다. 기존 '저장된 연구 적용…'은 섹션 재구성 작업이므로 이미지를
   추가한 뒤 다시 실행할 때는 기존 확인/Undo 동작을 따른다. Study를 먼저 구성하고 이미지를 추가하는 순서를 권한다.
2. 연결된 native Post에서 원자료를 열고 필요한 3D filter/공간 comparison을 적용하여 표시하고 저장한다.
   원하는 정확 프레임, field, association, component를 확인한다. 카메라/배율/범례는 실제 값을 캡처한다.
   다른 dataset/주석이 같은 view에 있으면 해당 결과만 보이는 별도 view를 사용한다.
3. Report의 자료 메뉴 → '3D 결과 이미지 추가…'를 누르고 연결된 적용 결과를 선택한다.
   '선택한 결과 캡처'는 solver나 provider를 실행하지 않는다. 완료 후 그림과 실제 field/time/unit/배율 및
   미확인 판정을 확인하고 '이 이미지 적용'을 누른다. '적용하지 않고 닫기'는 기존 문서를 유지한다.
4. 기존 섹션 설명, 포함 체크, 순서 이동을 사용한다. 편집 메뉴의 이미지 표시/크기는 종횡비를 유지한다.
   교체는 이미지 섹션을 선택하고 '선택 이미지 교체…'로 별도 캡처한 뒤 명시 적용한다. 기존 설명은 유지한다.
   설명을 편집 중이면 먼저 기존 '설명 적용' 또는 '수정 취소'를 사용한다. 미적용 설명을 버리지 않는다.
5. 기존 Undo/Redo, 저장, 닫기/다시 열기, preview, PDF/Markdown 출력을 사용한다. 저장 후 Post의
   선택이 바뀌어도 보고서는 다시 캡처하지 않는다. 원자료 제거는 출처 경고와 보존 이미지를 함께 표시한다.

메뉴의 구현 문자열은 `report_window.py`의 integration.patch가 기준이다. ID/hash/raw JSON은
이미지/출처 dialog의 선택 진단에만 둔다. 제품/창 제목에는 revision suffix나 •를 추가하지 않았다.

## root와 Sol의 소유

원본 파일 전체 교체본은 배포하지 않는다. 다음 5파일만 최소 integration.patch이다.

| 기존 파일 | 변경 내용 | 통합 소유 |
|---|---|---|
| `apps/desktop_post/workspace.py` | export의 선택 report_snapshot 인수와 신규 helper 호출 | root/Post |
| `caelab/report_document.py` | Report-local image reference, 기존 asset 보관, 손상 image-only 본문 읽기 | root |
| `caelab/workbench.py` | 기존 report_capture에서 저장된 command_id를 trusted receipt로 해석 | root |
| `apps/research/report_pages.py` | 기존 blocks/preview/PDF/Markdown에 image 분기 | Sol Expert/root |
| `apps/research/report_window.py` | 메뉴, 보존 cache, source dialog, stale preview 출력 차단 | Sol Expert/root |

6개 신규 전용 제품 모듈 및 전용 테스트/문서는 additions.patch와 new-files 트리로 제공한다.
기존 Post bridge/exit/Core/registry/desktop, NumericalWindow/RequestPlanWindow,
Data/Material 핵심, Sol 문헌 복구 GUI는 수정하지 않았다. 나머지 팀의 최신 변경은 읽었다고 가정하지 않는다.

기준 소스는 430개 entry의 선별 ZIP이다. full Workbench bootstrap에 필요한 `apps.desktop_pre`,
`apps.lab` 등이 포함되어 있지 않다. 이를 가짜 모듈로 대체하거나 mutable main을 가져와 통합 성공이라고
하지 않았다. Workbench.report_capture 자체는 실제 메서드를 시험하지만 native status는 모의 receipt다.
전체 앱 bootstrap/실제 transport는 root의 완전한 작업 사본에서 확인해야 한다.

## 다음 큰 인도 — 완료로 바꾸지 않은 원행

| 원행/SPEC | 이번 변경 여부 | 남은 구체적인 인도와 의존 |
|---|---|---|
| FN32 / SPEC-EXPERT-002 / FUNCTION_SPEC 보고서 | 본문 코드 인도 | root의 같은 Windows ParaView 프로세스에서 실제 capture, 정확 saved frame, preview/PDF/Markdown 수용. 여러 representation/병렬·특수 VTK 등은 별도 범위 판단 |
| FN05 / SPEC-EXPERIMENT-001 | 계산/GUI 핵심 미변경 | 제공 표준·확장 불확실성/k/상관/단위에 한정한 전파와 측정위치·방향·좌표·시간 대응. 미제공을 0/독립으로 채우지 않음. actuator travel→specimen strain 추정 금지. 원행/원값/교정값/fit/holdout/mask 분리 유지 |
| FN05 robust/DE 국소 진단 | 미변경 | 실제 마지막 채택 parameter 및 원 evaluator/fit rows/transform/weight/normalization에 귀속된 국소 Jacobian 진단. 기존 diagnose 재사용, 추가 평가 비용/명시 실행 정책을 Numerical 팀 detail_eval과 합의. 읽기만으로 계산하지 않음. 실패/중단/고정변수/active bound 구분 |
| FN29/FN30 / SPEC-EXPERT-002 | 기존 Co-STORM 재작성 안 함 | 기존 실제 journal/부분 응답/중단 요청-확인/재개 단계/동일 provider-model/늦은 응답 보호를 full user flow로 대조. 계산 Plan 명시 실행과 exact result 환류 유지. scripted LM은 실제 계정 증거가 아님 |
| FN35 / SPEC-EXPERIMENT-001 | 실장비 연결 안 함 | 실제 장비 모델/무료 maintained driver/통신/물리 stop 규약이 선행 입력. 기존 파일 수집·교정 경로는 유지. mock driver로 물리 수집/정지 완료를 주장하지 않음 |

다음 독립 핵심 단위는 FN05의 제공 불확실성·측정 위치 대응과 robust/DE 최종 채택점 진단이다.
이번 새 모듈에는 그 계산 엔진을 넣지 않았다. Numerical 팀의 최종 평가/추가 평가 정책과 공통 API를
분리해야 중복 evaluator나 암묵 재계산을 피할 수 있다. 이는 우선 FN32를 코드로 끝내라는 요청에 따른
인도 구분이지 원행 삭제나 사용자 재승인 대기가 아니다.

## root native 수용 검사 (작성되었으나 미실행)

추가 물리계산/provider 호출 없이 공개 보관 결과를 사용한다. 자기 ParaView GUI owner process에서
실행하고 결과 receipt·생성 PNG·보고서 저장 개정·출력 파일을 보관한다.

- 실제 retained RenderView에서 저장한 exact 시각/field/component/association/unit과 카메라/범례/warp를
  기록한다. export의 SaveScreenshot 1회와 broker 완료를 확인한다. 일반 PNG export는 report proof가 아님을 확인한다.
- 저장 후 view time을 바꿔 다른 frame을 표시했을 때 새 이미지가 거부되는지 확인한다. 정확 프레임을
  저장한 뒤 동일 조건은 통과해야 한다. 정적 자료는 0초라고 표시하면 실패다.
- 이미지 추가, 설명 작성, Study 판단 공존, 섹션 포함/순서/크기, 새 캡처 교체/취소/Undo/Redo,
  저장·cold reopen·한글/공백 경로 이동을 확인한다. 후속 Post 선택이 저장 보고서를 바꾸면 실패다.
- PNG/원입력/결과/PVSM hash 변경 및 파일 제거, native unavailable/FAILED/UNKNOWN, 전송 응답 손실,
  캡처 중 변경, dialog 닫기/늦은 응답을 확인한다. 기존 본문/판단/자산 및 기존 출력이 유지되어야 한다.
- 원자료 폴더 제거 후 보존 이미지와 출처 경고를 확인한다. 보존 image blob만 손상된 경우 본문을
  읽되 이미지 누락을 표시해야 한다. 손상 원자료나 새 PNG로 이전 해시를 몰래 갱신하면 실패다.
- Qt preview와 PDF에서 그림/가설/판단/다음 연구가 함께 보이는지 실제 화면과 페이지를 확인한다.
  Markdown의 data URI는 보존 PNG의 원바이트와 같아야 한다. native 캡처 시험과 Qt 출력 시험은 별개다.

Post File>Exit/X/Alt-F4와 native 생명주기 gate는 다른 Pro 인도 범위다. 이 패치 때문에 그 변경을
되돌리거나 수용 검사를 대신하지 않는다.
