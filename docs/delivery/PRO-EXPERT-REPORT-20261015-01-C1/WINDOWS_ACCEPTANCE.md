# Pro 제출 당시의 Windows 수용 목록

아래는 Pro가 제출할 때 미실행이었던 수용 계획이다. 이후 Codex의 실제 확인과
남은 범위는 [Windows 확인 기록](WINDOWS_CHECKS_20261015.md)을 따른다.

첫 인도 Windows Qt 성공과 C1 native 수용은 다르다. 본 목록은 통합 담당자의 기존 설치/공개 analytic
자료에서 수행할 검사이며 새 provider/solver/장비 실행 승인을 포함하지 않는다. 제품 main에 적용하기
전 별도 사본에 첫 인도+C1+Sol viewport-fit을 병합한다. 실제 binary/version/pid/owner session과
프로세스 receipt를 남기고 해당 자기 process만 종료한다. 다른 Post Exit 코드는 변경하지 않는다.

## 축 의미와 저장된 데이터

physical_time 0.25 s, STATIC_LOAD_PARAMETER 0.25 unit1, DIMENSIONLESS_MODEL_TIME 0.25 unit1,
semantics UNKNOWN 또는 미제공 VTK clock, static(step2,increment9,load_parameter0.25,timeNone)를
각각 저장·적용하고 캡처한다. 물리시간으로 임의 표시되는 경우가 없어야 한다. static/frozen 비교는
원 step/increment 및 정확한 이전 history의 관측 축을 보인다. 원 upstream current selection을 바꾼
후에도 과거 bindings의 선언을 읽어야 한다. 서로 충돌한 frozen/recipe/static/단위 조합의 새 채택은
거절하고 이전 그림·본문·Study 판단·Undo 상태를 그대로 보존해야 한다.

기존 /1 자산은 원바이트로 재열고 legacy block 미검증 경고를 보인다. /1 receipt를 새 캡처 결과로
채택하지 않는다. /2 적용/취소/교체/Undo/Redo와 원파일 삭제 뒤 cold reopen을 확인한다.

## 실제 native block 반례

실제 composite representation을 포함하는 저장된 지원 pipeline과 RenderView에서 수행한다.
ParaView ColorBlocksBy를 사용하여 전역 stress/MPa와 일부 block temperature 또는 별도 RGB를
섞고 범례를 숨긴다. 전역 stress 하나로 새 그림이 채택되면 실패다. 다른 association, 독립 LUT,
독립 component, 직접 RGB, BlockColors, 다른 opacity/interpolation도 각각 거절해야 한다.
선택된 block/선택 해제/parent selector/비표시 block 여부로 우회되지 않는지 확인한다.

reset/빈 override 및 동일 field+association+전역 shared LUT는 정상 수용한다. 같은 shared LUT의
component를 바꾸면 전역 component도 바뀌므로 caption은 실제 전역 component를 기록해야 한다.
별도지만 우연히 같은 LUT는 이번 경계에서 거절한다. 현재 비표시 block의 다른 설정도 거절하는
보수적 제한을 확인한다. 캡처 전후 사이 override 변경은 새 asset 채택을 막아야 한다.

실제 SaveScreenshot 결과, PNG pin, 같은 시점 scene/audit/axis_context/result fingerprint가 보존되어야
한다. mock SaveScreenshot/analytic PNG로 이 항목을 통과 처리하지 않는다. 지원 exact version은
5.13.2/6.2.0이며 그 외 버전 또는 API가 없는 representation은 ‘검증 불가’로 실패해야 한다.

## 실제 원자료 열기

정확한 연결 원창: Report에서 원자료 버튼을 눌러 native post.report_image_verify 응답과 원값
fingerprint를 확인한다. Properties/Spreadsheet View로 실제 원값을 검토한다. document.activate가
있는 owner만 자동 활성화 성공으로 표시한다. 없는 owner는 SOURCE_VERIFIED/NOT_PERFORMED다.

변경된 원창: time/active source/field/camera/pending Properties/content generation 중 하나를 바꾸고
다시 요청한다. 기존 원창을 덮거나 다른 창을 fallback으로 실행하지 않아야 한다. 현재 창을 별도 저장
또는 취소하고 정상 종료한 뒤, Report가 가리키는 정확한 saved project를 여는 동선을 확인한다.

닫힌 원창: 원 PID의 종료가 확인된 상태에서 기존 launcher의 post --project 복원을 사용한다.
새 연결된 owner의 exact result/data 응답 전에는 LAUNCH_REQUESTED/UNCONFIRMED다. helper PID만으로
성공 처리하지 않는다. 저장된 proxy/view가 없는 project는 자동 repair/다른 결과 대체가 아니라 실패다.
과거 카메라 자동 재구성은 수용 조건이 아니다.

실패: 원project/workspace/result/source 삭제·내용 변경, 새 session 경쟁, PID liveness UNKNOWN,
native capability 없음, ParaView 실행파일 부재/선택 취소, process-creation 실패, spawn 이후 응답
소실, native startup 실패를 시험한다. 기존 Report를 유지하고 실패/복구 안내를 확인한다. launch
중복을 만들지 않는다. 검증 receipt 소실은 같은 command ID로만 상태 확인하며, activation receipt
소실은 자동 activation 재전달을 하지 않는다. native 오류는 기존 helper 오류창/native log에서
확인한다. 그 증거 없이 Report 측 미확인을 확정 실패 원인으로 추정하지 않는다.

## Qt, PDF, 좁은 화면

기존 test_report_image_qt.py의 5검사 및 새 test_report_image_qt_c1.py의 8검사를 실제 PySide6에서
실행한다. C1 총 13개 Qt case다. 실제 Report의 본문·Study 판단·이미지 크기/순서·축 caption을 preview,
Markdown, PDF에서 대조한다. PDF는 실제 이미지 embedding뿐 아니라 한글 glyph/줄바꿈/잘림까지
렌더해서 확인한다. QPrinter 진단 유무와 PDF 생성 성공, 일반 native 인쇄 수용은 별도로 기록한다.

원자료 대화상자에서 Tab/버튼, 정상·좁은 창, worker 진행 중 닫기/늦은 응답을 검사한다. ImageView는
Sol viewport-fit 보완을 그대로 병합한다. C1은 그 widget의 과거 fixed size 본문을 덮어쓰지 않는다.
원자료 실패 때도 직전 Report 이미지/본문/판단/출력이 유지되는지 확인한다.
