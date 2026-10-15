# 이동 가능한 작업 사본과 선택 연결 보기

요청: **PRO-PORTABLE-CONNECTION-20261015-01**. 이 인도는 FN01-02와 FN31의 전용 코드 및 공통 연결 패치다. FN02-02 관련 부분 저장, FN26 원격 계산, 다른 팀의 dynamic/GUI/설치 코드 구현을 포함하지 않는다. 입력 ZIP의 SOURCE_BASE.md에 남은 dynamic 작업 문장은 이번 요청의 소유 범위가 아니다.

## 인도 상태

원자료를 실제로 가져온 Data, 저장된 Material, 서로 다른 두 Numerical 문서를 작업 사본으로 만들고, **예제 생성에 사용한 원 보관소 전체를 삭제한 뒤 별도 Python 프로세스에서 읽기·편집·재저장**했다. 폴더의 한글·공백 경로 이동도 검사했다. 성공/실패는 실제 CSV 가져오기의 성공 및 잘못된 열 번호로 발생한 실패다. 물리 솔버 성공/실패를 흉내 낸 기록이 아니다.

Qt 창 코드는 작성했지만 이 Linux 환경에는 PySide6가 없고 설치 다운로드의 DNS 연결이 실패했다. 따라서 두 창 크기, 실제 마우스/키보드 이벤트, 한국어 글꼴, Windows FreeCAD/ParaView 활성화는 **미검증**이다. Qt 전용 실행 검사와 캡처 명령을 함께 제공하며 실행하지 않은 결과를 통과나 화면 승인으로 표시하지 않는다. 제품 전체 완료, Windows 설치 완료, FN33 전체 완료, 물리 승인도 선언하지 않는다.

## 제품에서 사용하는 순서

소스 ZIP에는 두 패치를 적용한 코드가 들어 있다. 아래 명령은 제품 소스 폴더에서 기존 제품 Python으로 실행한다. `python` 대신 이미 사용하는 제품 환경의 Python 실행 파일을 지정해도 된다. 이 기능은 기존 제품 서비스와 원래 문서 owner를 사용하며 새 데이터베이스나 계산 스케줄러를 만들지 않는다.

이미 서비스가 실행 중이면 그 주소에 연결 창만 연다. Workbench 브라우저나 Workbench GUI를 먼저 열 필요는 없다.

```powershell
python -m apps.research.desktop --service http://127.0.0.1:8766 connection
```

창 왼쪽에는 실제 문서가 표시된다. 서로 다른 Numerical 문서들은 실제 서로 다른 문서 ID로 구별된다. 필요한 문서들을 체크하고 **체크한 문서의 연결 보기**를 누른다. 중앙의 **연결 그래프 / 같은 연결 목록**은 같은 선택 대상을 사용한다. 메뉴와 도구 모음에서 현재 원문서, 정확한 저장 참조, 사본 생성을 선택한다. 진단 ID와 hash는 기본 제목에 붙이지 않는다.

그래프 카드는 마우스로 이동할 수 있다. 이 배치는 해당 창의 보기 상태이며 문서 입력이나 관계를 수정하지 않는다. Enter는 선택 원문서 또는 계산 기록을, Ctrl+Enter는 검증된 저장 참조를 연다. Alt+1/Alt+2는 그래프/목록 전환, F5는 다시 읽기, Ctrl+휠은 확대/축소다. 문서 도크는 보기 메뉴에서 숨길 수 있다. 정확한 참조가 끊기면 그 참조의 열기를 비활성화하며, 현재 원문서로 몰래 바꾸어 읽지 않는다.

사본을 만들 때는 **선택 문서를 새 작업 사본으로…**를 누른다. 문서와 보존 파일 목록, 누락 위치, 미저장 편집 제외 경고를 확인한 뒤 목록 확인란을 선택한다. 로컬 사본은 선택한 비공개 공학 자료도 사용할 수 있다. 기존 폴더가 아닌 새 폴더 이름을 선택한다. 연결된 원문서가 선택에서 빠지면 자동 수집하지 않고 생성을 막는다. 현재 첫 인도 코드는 저장 개정만 복사하므로 미저장 편집은 원래 문서에 남는다. acknowledged 작업 초안을 별도로 보존하고 재개하는 기능은 후속 Pro 수정 대상이며, 이 제한을 전체 이동 기능 완료로 표시하지 않는다.

새 사본을 별도로 사용하려면 기존 제품 서비스를 **사본 폴더**에 연결한다. 원본 서비스가 계속 실행 중이면 다른 포트를 사용한다.

```powershell
python -m apps.lab.server --store "D:\공개 작업\옮긴 작업 사본" --port 8767
python -m apps.research.desktop --service http://127.0.0.1:8767 connection
```

새 서비스에서 사본의 Data·Material·Numerical 원문서를 열면 원래 도구의 편집/Undo/저장 동작을 사용한다. 사본 전체 폴더를 함께 이동한다. `workbench`, `portable`, `portable-project.json`을 따로 떼지 않는다. 원본 보관소와 원자료 경로가 없어도 보존 원자료/결과를 읽을 수 있다. 재열기는 계산이나 provider 호출을 실행하지 않는다. 새로운 계산은 각 도구에서 별도로 실행해야 하며 필요한 솔버의 설치 상태와 물리적 타당성은 별개의 조건이다.

## 누락 및 실패 복구

**파일 → 작업 사본 확인 / 누락 파일 복구…**에서 폴더를 선택한다. 누락/변경 파일의 정확한 위치와 복구 방법을 확인한다. 사용자가 지정한 대체 파일의 바이트 수와 SHA-256이 원본 기록과 정확히 같을 때만 복구한다. 다르면 거절한다. 손상된 기존 파일은 사본 안의 `portable/repair-history`에 남기고 복구한다. 다른 파일로 의미를 바꾸는 재연결이나 주변 폴더 검색은 하지 않는다. 복구 후 다시 전체 검사를 한다.

사본 생성 응답을 받지 못했다면 같은 창의 **사본 생성 응답 확인 / 같은 요청 재시도**를 사용한다. 동일한 요청은 완성된 같은 사본의 receipt를 반환한다. 서로 다른 요청이나 기존의 빈 폴더도 덮어쓰지 않는다. 중간 발행 실패는 `.incomplete.json`으로 남아 정상 사본처럼 열리지 않는다. 원본에서 **다른 새 폴더**로 다시 생성한다. 서비스 세션이나 포함 문서의 입력/개정이 바뀌었다면 포함 목록부터 다시 확인한다.

명령행 복구도 같은 전용 API를 쓴다.

```powershell
python -m caelab.portable_project verify "D:\공개 작업\작업 사본"
python -m caelab.portable_project repair "D:\공개 작업\작업 사본" "portable/originals/문서/개정/sources/원자료/source.csv" "D:\명시적으로 선택한 동일 파일.csv" --approve-exact-file
```

위 복구 상대 경로는 예시다. 실제 검사 결과에 표시된 사본 내부 파일 위치를 사용한다. 초기 사본의 보존 목록에 없는 파일이나 manifest 자체를 임의의 값으로 다시 작성하는 복구는 지원하지 않는다.

## 공개 파일 예제와 재현

인도 패키지의 `portable-public-working-copy.zip`은 코드 예시 JSON이 아니라 이미 생성·검사한 **기존 문서 owner가 여는 실제 작업 폴더**다. 빈 새 경로로 풀고 기존 서비스의 `--store`로 연다.

```powershell
python -m caelab.portable_project extract "portable-public-working-copy.zip" "D:\공개 작업\예제 사본"
```

새 공개 예제를 만들고 원본을 삭제하는 검사를 직접 재현하는 명령이다. 삭제 대상은 이 스크립트가 새 출력 경로 안에 직접 만든 예제 보관소뿐이다. 이미 있는 출력 폴더는 거절한다.

```powershell
python -m examples.portable_connection_public --output "D:\공개 검증\새 검사 폴더"
```

이 스크립트는 공개 합성 CSV, 저장 재료, 연결된 피팅 계획과 별도의 계수 탐색 계획을 만든다. 원본을 삭제하고 한글·공백 폴더로 이동한 뒤 다른 프로세스에서 원자료/성공/실패를 읽고 재료와 Data 메타데이터를 편집·저장한다. `public-check.json`에 실제 결과를 쓴다. 회사 파일, 개인 인증정보, 외부 provider, 원격 계산은 사용하지 않는다.

## 검사 실행

```powershell
python -m pytest -q tests/test_portable_project.py tests/test_connection_graph.py tests/test_portable_connection_http.py tests/test_connection_window_qt.py -ra
python -m examples.connection_window_check --output "D:\공개 검증\Qt 실제 검사"
```

두 번째 명령은 PySide6가 있을 때 실제 Qt 검사와 QWidget 캡처를 실행한다. PySide6가 없으면 `BLOCKED`, 종료 코드 2, `captures_created=false`를 기록한다. offscreen 통과도 Windows OS 입력/창 활성화의 증거는 아니다. 실제 Windows 확인에는 정상 크기 1200×780과 제한 크기 820×600, 선택/드래그, Tab/Enter/메뉴, 한글 글꼴, 누락 복구, 서비스 오류, 읽기 중 닫기와 쓰기 중 닫기 보호를 같은 공개 자료로 확인해야 한다.

## 지원 범위와 명시적 제한

첫 사본 대상은 Data·Material·Numerical이다. 연결 보기는 기존 다른 연구 owner의 명시적 저장 참조도 읽는다. 등록된 native 문서는 마지막 owner 보고와 Pre의 명시적 계산 연결만 표시한다. 그 표시가 FCStd/PVSM 파일 전체의 무결성 검사나 살아 있는 native GUI 확인을 뜻하지 않는다. VTK proxy ID나 도구 catalog key를 제품 문서 ID로 추정하지 않는다.

Numerical의 `files.table` 전역 data_id, frozen CAD/FE 입력, 문서 소유자 없는 legacy job_id 입력은 이 사본 계약 밖이다. 이 경우 생성을 막는다. Data의 보존 결과와 typed `result_refs`로 명시적으로 연결하거나 해당 owner 팀의 별도 보존 계약이 필요하다. 다른 owner로 몰래 연결하거나 전역 입력 보관소를 함께 복사하지 않는다.

체크섬은 보존 무결성 확인이지 발행자 인증이나 회사 자료 탐지기가 아니다. 로컬 작업 사본은 사용자가 선택한 비공개 공학 자료도 취급한다. 복사 전에 포함 문서와 파일 목록을 확인한다. 비공개 자료나 자격증명을 외부 Pro 대화 또는 공개 Git에 전송하는 것은 별개의 금지 사항이다. 공개 예제는 이 인도 검사를 위한 합성 자료다. 실행 파일·솔버·환경설정·인증정보·전역 실행 큐는 자동 묶음 대상이 아니다. 원본 결과의 진단 문자열/출처 경로는 과거 기록으로 그대로 남을 수 있지만 그것을 현재 파일 위치로 따라가지 않는다.
