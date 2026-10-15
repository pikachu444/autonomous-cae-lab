> C1 기록은 아래에 보존합니다. 현재 C2 추가 내용은 [C2_README_KO.md](C2_README_KO.md)을 참조하세요.

# 이동 가능한 작업 초안과 선택 연결 보기 — C1

요청 **PRO-PORTABLE-CONNECTION-20261015-C1**. 이번 코드는 Data·Material·Numerical의 저장 base와 owner가 받아들인 미저장 초안을 함께 복사하고, 기존 owner에서 편집·Undo·저장을 재개한다. 연결 창에는 기존 typed 참조 포트의 추가·취소·영향·복구·해제와 프로젝트별 배치 저장을 추가했다. 원 결과를 다시 계산하지 않는다.

## 무엇을 적용하는가

`source-dedicated.zip`은 portable/connection 전용 소스·검사·예제·문서다. 전체 main이나 다른 팀의 소스 사본이 아니다. `product.patch`는 **첨부 C1 source/**의 전용 코드에 대한 변경이다. 공유 파일은 포함하지 않는다.

`integration.patch`는 **첨부 current-common-context/**에 최초 common4 연결과 C1 연결을 합친 최소 패치다. 현재 root의 다른 변경을 되돌리지 않는다. 수정 파일은 workbench, client, routes, desktop, native_commands 다섯 개다. `integration-on-c1-packet.patch`는 최초 common4가 이미 반영된 **첨부 source/**를 재현할 때만 사용하는 C1 공통 증분이다. 두 integration 패치를 함께 적용하지 않는다. root가 그 뒤 변경한 main에는 패치 문맥을 확인하고 통합한다. 공유 파일 전체 덮어쓰기는 금지한다.

첨부 `SOURCE_BASE.md`의 90d/dynamic 표기는 실제 C1 기준이 아니다. 실제 전달 정보는 fbcfb37 검사 baseline, 현재 공통 참조 커밋 `1e3025f565c2246c2746c8cedd300f95e21e0408`, 원 인도 ZIP 및 이번 입력 ZIP의 해시를 구분한 `SOURCE_MANIFEST.json`을 따른다. `history/PRE_C1_*`는 수정 전 문서의 보존본으로 현재 기능 설명이 아니다.

## 제품에서 초안을 이동하는 순서

이미 사용하는 Windows 제품 Python과 로컬 서비스를 사용한다. 연결 창이나 Workbench GUI는 Data/Material/PDE/Numerical/Runner/Post 독립 창의 선행 조건이 아니다. 새 웹 화면, 계정, 유료 SDK, WSL 또는 provider를 설치하지 않는다.

```powershell
python -m apps.research.desktop --service http://127.0.0.1:8766 connection
```

원래 도구에서 Material E 등을 편집하고 owner가 입력을 받아들인 뒤 저장하지 않은 상태로 둔다. 연결 창 왼쪽에서 Data·Material·관련 Plan을 체크한다. **파일 → 선택 문서를 새 작업 사본으로…**는 기본적으로 **받아들인 초안 + 현재 저장 base**를 포함한다. 정확한 문서와 보존 파일 목록을 보고 **복사할 문서와 보존 파일 목록을 확인했습니다.**를 체크한다. 새 목적지 이름을 지정한다. 빈 폴더도 이미 존재하면 덮어쓰지 않는다.

누락 의존 문서나 원자료, 읽을 수 없는 초안 결과가 있으면 발행을 거절하고 위치와 이유를 표시한다. 자동으로 초안을 빼거나 저장하지 않는다. 사용자가 초안 제외를 선택하려면 별도 **파일 → 저장본만 새 사본으로…**를 사용한다. 이 흐름에서는 제외 경고를 표시하며 저장본 전용 사본임을 기록한다. 이미 검사한 포함 목록 뒤에 입력·Undo 이력·저장 base·파일이 변하면 다시 검사해야 한다.

만들어진 폴더 전체를 한글·공백 경로로 옮긴다. 원 서비스와 동시에 사용할 때는 다른 포트의 기존 제품 서비스를 사본 폴더에 연결한다.

```powershell
python -m apps.lab.server --store "D:\공학 작업\옮긴 작업 초안" --port 8767
python -m apps.research.desktop --service http://127.0.0.1:8767 connection
```

원문서를 열면 저장 base는 옛 값이고 dirty 초안은 이동 직전 owner가 받아들인 값이다. 원 owner에서 다시 편집하고 Undo하면 그 acknowledged 초안으로 돌아온다. 저장은 사용자 명령으로 수행한다. Data의 새 원자료, 이전 성공·실패, 단위, UNKNOWN/빈 값/invalid payload도 보존한다. 원입력·결과의 원본 영역은 변경하지 않는다. 새 문서·개정·입력 ID를 갖는 편집용 사본의 알려진 내부 typed 참조만 대응시킨다. 옛 절대 경로가 오류/출처 문자열에 남아 있어도 파일을 찾는 대체 경로로 사용하지 않는다.

이 기능은 **owner가 이미 받아들인 초안**을 옮긴다. 위젯 안에만 남아 owner 명령으로 전달되지 않은 `1e`, blank, 셀 선택·편집 버퍼는 다른 층이다. DataMaterial C01 capsule API는 `NOT_INTEGRATED`다. 이 구현은 QSettings, 위젯 트리, registry, 계정 파일을 검색해 버퍼를 추측하지 않는다. owner가 실제로 받아들인 `1e`/blank/UNKNOWN은 그대로 옮긴다.

## 관계를 편집하는 순서

중앙 **연결 그래프 / 같은 연결 목록**은 동일한 선택과 command를 사용한다. 문서 또는 연결 카드를 선택하고 **연결 → 연결 추가…**에서 대상 포트와 허용된 실제 원본을 고른다. 원본 선택은 저장 개정, 현재 acknowledged 입력, 보존 결과를 구분한다. 새 시험 행·재료값·단계·필드 매핑은 이 창에서 만들지 않고 원 도구에 위임한다.

**영향 확인**에는 현재 참조, 저장 base의 참조, 제안 참조, 원본 이름/개정·입력 상태, 관련 문서, 이전 결과의 입력 일치 여부와 진단을 표시한다. 확인 전 Esc/취소는 변경을 남기지 않는다. 명시적으로 반영하면 원 owner의 세대 검사 update가 참조 한 곳만 변경하며, owner Undo 이력에 들어간다. 이전 저장 개정과 결과는 남는다. 새 입력이 미완성/진단 오류 상태이면 그대로 표시하며 물리 승인이나 계산 성공으로 바꾸지 않는다.

원본이 바뀌면 **연결 영향 보기…**로 현재/저장 참조를 비교한다. **원본 참조 복구…**는 새 정확한 원본을 명시 선택하고 영향 확인 후 바꾸는 동작이다. **연결 해제…**는 참조만 제거한다. 원문서·파일·결과를 삭제하지 않는다. 끊긴 참조를 최신값으로 자동 교체하지 않는다. 다른 store의 같은 문서 ID나 다른 결과/입력은 같은 원본이 아니다.

| 동작 | 메뉴/키보드 | 상태 변경 |
| --- | --- | --- |
| 원문서 또는 실행 기록 열기 | Enter | 기존 desktop owner 열기 |
| 정확한 저장 참조 열기 | Ctrl+Enter | 기존 ReferenceWindow; 초안으로 대체하지 않음 |
| 연결 추가 | Ctrl+L | 선택·preview 후 명시 반영만 owner update |
| 원본 참조 복구 | Ctrl+R | 정확한 참조를 명시 교체 |
| 연결 해제 | Ctrl+Delete | 참조만 해제, 결과 유지 |
| 영향 보기 | Alt+I | 읽기 전용 |
| 선택/대화 취소 | Esc | 반영 전 변경 없음 |
| 그래프/목록 | Alt+1 / Alt+2 | 보기만 변경 |
| 프로젝트 배치 저장 | Ctrl+S | 도메인 문서 저장이 아니라 view state 저장 |

원 도구에서 동시에 입력이 바뀌면 STALE_SOURCE/STALE_TARGET으로 거절한다. 원본 선택은 유지되며 **현재 자료로 연결 다시 확인…**에서 새 상태의 영향을 다시 확인한다. 응답을 못 받은 쓰기는 **같은 연결 요청 결과 확인**으로 같은 command ID를 재조회한다. 반영 여부가 미확정이면 새로운 변경을 자동 실행하지 않는다. 이미 반영된 owner 변경을 Esc로 몰래 Undo하지도 않는다.

## 배치 재개

카드 드래그, 선택, 문서 체크와 그래프 필터, 검색어, 그래프/목록 탭, 문서 도크 표시·너비, 확대율을 해당 프로젝트의 `workbench/views/connection.json`에 저장한다. 창에서 잠시 조작을 멈추면 배치를 저장하며 Ctrl+S로 직접 저장할 수도 있다. 이는 도메인 문서 save가 아니다. 도메인 입력 hash나 결과 파일을 바꾸지 않는다.

새 창/서비스 프로세스가 같은 프로젝트를 열면 배치를 읽는다. 작업 사본을 만들 때에는 view key를 유지하고 참조 문서 ID를 새 사본으로 대응시킨다. 이동 뒤 옛 store 경로나 옛 문서 ID로 노드를 찾지 않는다. 두 창이 동시에 배치를 저장하면 세대 충돌을 알리고 현재 선택/배치를 보존한다. **배치 충돌 확인 / 다시 읽기…**에서 서버 배치를 읽거나 현재 배치를 명시적으로 유지한다. 알 수 없는 binary/global 설정을 복원하지 않는다.

## 누락 파일 복구와 ZIP

**파일 → 작업 사본 확인 / 누락 파일 복구…**에서 필요한 파일의 위치와 오류를 본다. 명시적으로 지정한 파일이 기록된 바이트 수·SHA-256과 같은 경우만 복구한다. 다른 파일로 의미를 바꾸는 관계 복구와 동일 바이트 파일 복구는 별도 동작이다. 손상 파일은 복구 이력에 보존한다. 새 폴더 발행 실패는 `.incomplete.json`을 남기며 정상 사본처럼 열리지 않는다.

```powershell
python -m caelab.portable_project verify "D:\공학 작업\작업 초안"
python -m caelab.portable_project extract "portable-c1-public-working-copy.zip" "D:\공학 작업\새 공개 예제"
```

압축 해제는 플랫폼에서 정규화된 filename뿐 아니라 원래 ZIP 이름 `orig_filename`을 검사한다. raw backslash, 절대 경로, `..`, 별칭·장치 이름·symlink는 목적지 발행 전에 거절한다. 이 교정은 Windows에서 외부 경로 탈출을 실증했다는 주장이 아니다.

## CLI와 전송 한도

사본 명령의 자연스러운 옵션은 `--inventory-confirmed`다. 옛 `--approved-public-files`는 같은 뜻의 호환 alias이며 공개자료만 허용한다는 뜻이 아니다. `--saved-only`가 없으면 acknowledged 초안을 포함한다. 살아 있는 원 서비스에는 `--service`로 접속한다. `--workspace`는 서비스가 실행 중이지 않은 보관소를 직접 사용하는 별도 방식이다.

```powershell
python -m caelab.portable_project copy --service http://127.0.0.1:8766 --document "실제Data문서ID" --document "실제Material문서ID" --document "실제Plan문서ID" --destination "D:\공학 작업\새 작업 초안" --inventory-confirmed --command-id Cunique_copy
python -m caelab.connection_graph_commands catalog --service http://127.0.0.1:8766 --target "실제Plan문서ID"
```

진단용 CLI는 같은 loopback Client의 graph/catalog/impact/preview/apply/view/view-save를 호출한다. apply는 확인한 proposal, 같은 재시도용 command ID, `--confirmed`가 필요하다. 다른 팀 API나 global CLI/MCP registry를 대체하지 않는다.

일반 JSON command는 128 KiB, 기존 업로드는 16 MiB, portable create의 포함 목록 metadata는 8 MiB다. 문서 owner에 원래 있던 draft용 별도 한도도 그대로 유지한다. 서버가 이미 허용한 local input root에서 명시 등록한 큰 원자료는 **서버 내부에서 파일로 복사**한다. 원자료 bytes를 JSON/base64에 넣거나 일반 전송 한도를 확대하지 않는다. 너무 큰 metadata/command는 거절되며 자동 chunk 전송이나 우회 업로드를 하지 않는다. portable 파일 한도 20 GiB/100000개 전체를 실제 Windows에서 검증한 것은 아니다.

로컬 작업 사본에는 사용자가 선택한 회사/개인 공학 자료도 사용할 수 있다. 비공개 자료·자격증명을 외부 Pro나 공개 Git으로 보내는 것은 별도로 금지한다. 확장자 `.key/.pem/.pfx/.p12`만 보고 모든 공학 자료를 금지하지 않는다. 명시 credential/operator 설정 이름의 자동 수집은 차단하지만 파일명만으로 비밀 유무를 판정하는 기능은 아니다. 포함 목록 검토가 필요하다.

## 공개 재현과 실행 상태

```powershell
python -m examples.portable_connection_c1_public --output "D:\공개 검증\새 C1 검사"
```

이 스크립트는 새 출력 폴더에 만든 **합성 원 보관소만** 삭제한다. 이미 존재하는 출력 폴더는 거절한다. 저장 E와 다른 acknowledged E, Data 성공 2건/실패 2건, invalid Data/Plan, 단위와 배치를 만들고 복사→원본 삭제→한글 이동→별도 프로세스에서 읽기/편집/Undo/저장을 검사한다. 제공된 작업 사본 ZIP도 기존 owner가 여는 실제 파일이다. CSV 가져오기 결과를 물리 solver 결과로 표시하지 않는다.

C1의 Qt 창 코드는 작성했지만 이 환경에는 PySide6가 없어 실제 widget/QTest는 NOT_RUN이다. C1에서 설치 다운로드를 시도하거나 SDK를 추가하지 않았다. Windows Qt 6.9.1에서의 기존 baseline 검사는 C1의 새 dialog/배치 동작 검증이 아니다. 실행 명령과 실제 검사 수치는 `VERIFICATION_KO.md`를 따른다. OS mouse/native FreeCAD·ParaView activation, 전체 설치, 물리 승인, FN02-02 관련 저장/C01 capsule, FN26 remote는 이 인도 완료 항목이 아니다.
