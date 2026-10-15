# FN32 C1 교정 인도

요청 ID: PRO-EXPERT-REPORT-20261015-01-C1

기준은 첨부 public-source-4ac2e2a.zip에 첫 인도의 additions.patch와 integration.patch를 적용한 트리다.
사용자 원본 ZIP/소스/첫 인도는 바꾸지 않았다. 현재 main 5f6aede, 다른 팀 작업 또는 별도
Sol gui-fit.patch가 이 사본에 적용되어 있다고 가정하지 않는다. 저장소 게시도 하지 않았다.

## 전달물과 소유

| 파일 | 상대 기준과 역할 |
|---|---|
| correction.patch | 첫 인도 전용 파일의 변경 + 새 전용 제품/검사/문서. 공통 파일을 포함하지 않음 |
| integration.patch | root 소유 startup.py/workspace.py/desktop.py의 최소 연결. 첫 통합본 대비 증분 |
| gui-integration.patch | Sol 소유 report_image_dialog.py의 show_origin 함수만 위임. ImageView/크기/viewport-fit은 건드리지 않음 |
| changed-files/ | 변경한 전용 파일 및 새 전용 파일의 원문. 검토용이며 일괄 덮어쓰기용 아님 |
| validation/ | 실제 실행 stdout, 환경, 적용 검사, 파일별 소유/이전·이후 SHA, 무결성 기록 |
| request/ | 이번 CORRECTION.md/PUBLIC_CONTRACTS.txt의 정확한 첨부 원문 |
| MANIFEST.sha256 | 패키지 파일 무결성. 이 manifest 자체만 제외 |

correction.patch를 적용했다면 같은 파일을 changed-files에서 다시 복사하지 않는다.
기존 공통 파일과 report_image_dialog.py 전체 교체본은 포함하지 않았다. root는 현재 통합 트리와
context를 대조하여 공통 패치를 병합한다. Sol은 GUI hunk를 별도 viewport-fit 보완과 함께 병합한다.
패치가 안 맞으면 강제 적용/전체 파일 복사로 해결하지 않는다. 첫 인도 패치를 C1로 대체하지 않는다.

## 정확한 기준 사본에서 재현

다음은 root/Codex의 검사 명령이며 사용자에게 수작업 Git 운용을 요구하는 것이 아니다.
이미 첫 인도가 통합된 검사용 트리에서 세 C1 패치를 적용한다.

```text
git apply --check <C1>/correction.patch <C1>/integration.patch <C1>/gui-integration.patch
git apply <C1>/correction.patch <C1>/integration.patch <C1>/gui-integration.patch
```

처음부터 검증할 때는 public-source-4ac2e2a.zip의 소스 루트에 첫 인도 additions.patch 및
integration.patch를 먼저 적용한다. 그 다음 위 C1 패치를 적용한다. 공유 Python 파일은 원래
CRLF를 유지했다. 시험 사본의 기존 바이너리 캐시/생성 파일은 패치에 넣지 않았다.

## 사용자 동선

저장·적용된 Post 결과를 기존 Report 캡처 대화상자에서 선택하고, 새 그림과 축 의미를 확인한 뒤
명시 적용한다. Report에서는 이미지뿐 아니라 Study 판단과 본문이 같은 소유자의 자산/초안/저장
개정에 보존된다. 기존 교체/취소/Undo/Redo/저장·재열기/PDF/Markdown 경로를 유지한다.

‘원자료 열기’에서는 보존 이미지와 실제 원자료 검토를 구분한다. ‘원 Post에서 원값·처리조건 검토’를
누르면 Report 자산과 project/workspace/result/source pin을 검사한다. 정확한 살아 있는 owner는
읽기 전용 원값 검증 후 기존 native activation을 사용한다. 다른 상태의 살아 있는 원창은 덮지 않는다.
그 창의 편집을 별도로 저장/취소하고 정상 종료한 뒤 정확한 보존 project를 다시 열도록 안내한다.
원창이 닫힌 것이 확인된 경우만 기존 post --project 경로로 연다. 요청 접수는 native 성공이 아니다.
‘같은 열기 요청 상태 확인’은 새 창을 다시 실행하지 않으며, 응답을 잃은 검증도 같은 command ID만
조회한다. 활성화 응답이 사라졌을 때도 자동 재전달하지 않는다.

원 Post의 선택된 pipeline에서 Properties를 읽고 Spreadsheet View로 원값을 검토한다.
과거 카메라/색상을 자동 재구성하는 기능은 아니다. 원창에 document.activate capability가 없는
기준 소스에서는 데이터 검증과 창 활성화를 분리하여 표시하며 기존 ParaView 창을 선택하게 한다.

복구할 원파일이 없거나 hash가 다르면 실제 원자료는 열 수 없지만 보존 이미지/본문/판단은 유지된다.
새 provider/solver/실장비 호출, 새 renderer/store, 웹브라우저/JSON editor 대체 열기는 없다.

## 남은 범위

C1의 실제 Windows ParaView capture/원자료 재열기 및 C1 Qt/PDF 검사는 WINDOWS_ACCEPTANCE.md에
남겼다. 사용자 전달의 첫 인도 Windows 결과를 C1 실행 증거로 승격하지 않는다. FN05 제공 불확실성·
측정 위치·최종 피팅점 진단은 다음 독립 큰 인도이며 Numerical detail_eval/adoption을 복제하지 않는다.
FN30 부분/중단/재개 전체 동선과 FN35 실제 장비/driver/physical stop도 이번 교정으로 완료하지 않는다.
