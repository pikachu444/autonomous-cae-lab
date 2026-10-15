# C3A 이동 사본: 보관 원문에서 현재 편집 이어가기

시험 데이터·재료·수치 계획을 다른 폴더나 PC에서 이어 쓰려면 원 편집 자료를 보관한 뒤
선택 연결창에서 이동 사본을 만드세요. 사본에서는 **파일 → 이동 사본의 원 편집 자료…**로
입력을 읽고, **현재 사본에서 이어가기**를 선택합니다. 보정 자료와 미완성 셀도 함께
보존하며 원래 폴더 없이 다시 저장할 수 있습니다. 아래 [실제 사용자 동선](#실제-사용자-동선)을
따라가세요. 해석·보고서·CAD/후처리 파일의 이동은 아직 추가 개발 중입니다.

요청: PRO-PORTABLE-CONNECTION-20261015-C3A-02. 이 인도는 첨부 원본에서 새로 작성한 코드다. 과거 C3 작성본의 복원이나 재포장이 아니다.

## 범위와 상태

Data, Material, 실제로 다른 두 Numerical Plan의 saved / acknowledged 전체 문서 / 미적용 raw / 선언 assets / 부분 저장 receipt를 명시 선택하여 이동한다. 원 store를 제거한 별도 프로세스에서 원 입력·결과를 읽고 현재 owner의 승인·CAS로 편집을 이어간다. 현재 사본 저장과 새 Keep, 새 프로세스 재열기, 다시 사본 만들기를 포함한다. 기존 C2 세 owner와 선택 연결창을 확장했으며 새 store, owner, coordinator, solver는 만들지 않았다.

원 Pro 작성 환경에서는 Linux 실제 owner·파일·HTTP·CLI 검사를 실행했고 PySide6가 없어 Qt/Windows/native는 NOT_RUN이었다. 이후 Windows 통합에서 기존 Qt 편집기의 실제 메뉴·명시 이어가기·미완성 셀/포커스, 두 Plan 분리 복원과 작은 cold/재복사를 확인했다. 구체적 범위와 남은 결함은 [Windows 확인 기록](WINDOWS_VERIFICATION_KO.md)에 구별한다. FreeCAD/ParaView/native와 C3B의 나머지 owner 이동은 이번 확인에 포함하지 않았으며 전체 C3 완료가 아니다.

## 통합

정확한 기준은 입력 ZIP의 공개 Git 60471159c1bd21b871eca2d6a37bafa49ad38ca3 및 동봉 manifest의 overlay를 합친 source 트리다. 이후 public main 4dac8c2는 사용자 제공 정보이며 이 인도에서 조회·적용 검사하지 않았다.

먼저 해당 기준에서 `git apply --check product.patch`, `git apply product.patch`를 수행한다. 이어 `git apply --check integration.patch`, `git apply integration.patch`를 수행한다. 두 패치는 분리되어 있지만 이 기능에는 둘 다 필요하다. 현재 병렬 main에서는 root가 최소 hunk를 검토하여 통합해야 한다. 옛 공유 파일 전체를 복사하지 않는다. 전달 source/에는 전용 변경 파일만 있으며 공유 파일 대체본은 없다.

integration.patch는 Workbench, Client, strict HTTP routes, Data 저장 retention, 기존 recovery asset의 원 Data 실행 검증, Data/Material 메뉴 진입점에만 작은 hunk를 추가한다. 기존 원 파일의 CRLF를 보존한다. 수치·CAS·CAPTURE·승인·native 계산 엔진은 변경하지 않는다.

## 실제 사용자 동선

원 Data/Material/각 Plan 편집기에서 미확정 입력을 기존 「편집 원문 보관」으로 Keep한다. 복사 버튼은 아직 Keep하지 않은 셀·위젯·QSettings를 수집하지 않는다. 원문 목록에 없는 입력을 옮기려면 먼저 해당 owner의 기존 보관 절차를 거친다.

기존 선택 연결창에서 문서를 선택하고 이동 사본 검토를 연다. 「함께 옮길 보관 원문 선택」에서 필요한 보관본을 직접 체크한다. 기본값은 모두 해제다. 원 저장소 보관본과 이전 사본이 가진 원 archive를 구별한다. 저장본, 당시 반영 문서, 미확정 셀, 관련 저장 기록을 함께 검증하여 stage에 복사하고 마지막 manifest로 발행한다. 성공한 목적지나 원본을 덮어쓰지 않는다.

사본을 연 뒤 기존 Data/Material 편집기의 「이동 사본의 원 편집 자료…」에서 읽는다. Material에 실제 Plan 둘이 연결되어 있으면 대상 편집 owner를 고른다. 저장값·당시 반영값·원문·단위·원 자료·기록된 결과 및 부분 저장 상태를 확인한다. 원 store가 없어도 archive의 기존 Data reader와 owner fingerprint/asset 검증으로 읽는다.

「현재 사본에서 이어가기」는 읽기와 별개의 명시 승인이다. 현재 owner/session/generation/input/saved 상태, 전체 acknowledged 문서, 현재 편집 buffer token을 대조한다. 이 GUI 구현은 **깨끗한 현재 대상 편집기에서만** 원문을 복구한다. 다른 미확정 buffer가 있으면 먼저 현재 원문을 보관하고 깨끗한 편집기를 열도록 거절한다. 묵시적 Keep·폐기·delegate commit으로 덮어쓰지 않는다. 검토 중 편집 변경·다른 Plan·늦은 응답은 거절한다.

승인하면 기존 owner UPDATE로 당시 acknowledged draft의 typed 편집 projection만 반영하고, `1e`, 빈칸, invalid 및 local_draft/포커스/선택은 기존 편집기의 raw 복구 함수로만 돌려준다. raw를 숫자로 해석하거나 물리적으로 유효하다고 적용하지 않는다. 계산·저장·CAPTURE는 자동 실행하지 않는다. 원 Undo/Redo·receipt는 불변 archive에 남고 현재 owner의 새 Undo는 기존 UPDATE가 만든다. 원 명령 이력을 현재 undo journal이나 승인으로 설치하지 않는다.

사용자는 셀을 수정하여 기존 적용·저장 동작을 수행하거나 미완성 상태로 보관할 수 있다. 현재 acknowledged 문서를 저장할 경우 **저장 후 그 현재 상태에 대해 다시 Keep**하고 닫는다. Keep 이후 저장해 saved base가 달라지면 기존 recovery CAS는 그대로 거절하며, 이전 Keep를 현재 것으로 승격하지 않는다. 새 프로세스에서는 새 사본의 현재 Keep를 기존 명시 session-change 확인으로 복구한다. 원 archive의 recover/discard 권한을 사용하지 않는다.

재복사에서도 필요한 이전 원 archive와 현재 새 Keep를 직접 선택한다. 원 Q/ack/raw/receipt 파일 bytes는 그대로 두고 현재 편집 owner의 탐색 mapping만 추가한다. 예제는 원 archive 4개, 첫 사본에서 새로 Keep한 4개를 함께 포함하여 두 번째 사본에 8개를 보존한다.

## 실패와 경계

누락·변조·선언 밖 경로·다른 owner receipt·invalid marker·stale CAS·buffer 변경은 보존한 원 자료를 고치지 않고 실패한다. legacy acknowledged base 누락과 DISCARDED는 읽기 전용이다. 미완료 J는 원 RUNNING/NOT_PUBLISHED 그대로이며 실패 결과를 성공으로 바꾸지 않는다.

기존 C2 Data 사본 중 원 import 실행 proof를 보존하지 않은 과거 사본은 새로운 raw-resumable 사본/Keep에 필요한 원 제출 증명이 없다. 이 경우 해당 작업을 명시 거절한다. 현재 정보를 과거 제출값으로 위장하여 통과시키지 않는다. 원 자료에서 새 C3A 사본을 만들면 별도 원 import proof를 보존하여 현재 Keep/저장/재복사까지 검증한다. raw 선택이 없는 기존 C2의 일반 복사·원 결과 읽기를 새 정책으로 재작성하지 않는다.

일반 요청 128 KiB, upload 16 MiB, create 8 MiB, JSON 16 MiB, 전체 20 GiB/100000파일, 기존 raw 512 KiB 한도를 변경하지 않았다. 명시 보관본 선택은 최대 128개, navigation/proof는 기존 32 hop 한도를 사용한다. 원문을 잘라 성공 처리하지 않는다.

## 재현

저장소 루트에서 다음을 각각 실행한다. 새 예제 출력 폴더는 기존 폴더가 아니어야 한다.

```sh
python -B tests/public_probes/c3a_baseline_probe.py
python -B -m pytest -q tests/test_portable_recovery_c3a.py
python -B -m pytest -q tests/test_portable_recovery_c3a_http.py
python -B -m examples.portable_connection_c3a_public --output ./c3a-public-new
python -B -m pytest -q tests/test_portable_recovery_c3a_ui.py
```

마지막 검사는 설치된 PySide6 환경에서 실행한다. 현재 실행 기록의 skip를 GUI PASS로 바꾸지 않는다. 예제는 자신이 새로 만든 공개 synthetic 원 store와 첫 사본만 제거하여 접근 불가 cold를 만든다. 모든 새 Workbench, HTTP 서버, 창 및 subprocess는 각 테스트/예제의 finally에서 닫는다. 기존 C2 bound 경로의 timeout과 초기 RED/fixture 실패는 logs에 별도 보존한다.
