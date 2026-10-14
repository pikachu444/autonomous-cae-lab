# E1 Windows 실행 확인표

이 파일 자체는 실행 증거가 아니다. 작성 환경의 actual Windows/FreeCAD/CalculiX 실행은 **NOT_PERFORMED**다. Codex가 기존 Windows 설치에서 아래 항목을 직접 실행하고 실제 경로·로그·화면을 남긴다. 프로그램 실행 성공과 공학적 수치 승인을 분리한다.

| 순서 | 직접 할 작업 | 통과 기준 / 보존할 증거 |
|---|---|---|
| 1 | `integration.patch`를 기준 브랜치와 대조해 적용하고 관련 pytest 실행 | 공통 hook 9개 파일, 기존 solid/J2/contact/M3 코드 교체 없음; 실제 pytest 원출력 |
| 2 | 기존 Pre에서 `OpenPlate.FCMacro`로 새 파일 생성 | native Plane·8절점 면 메시·분석 객체 존재. 실제 FreeCAD 버전/화면. 생성기 이름 외의 새 문서/객체 Label도 시험 |
| 3 | 면 선택 및 요소 표 부분 선택 → 미리보기 → 취소/적용 | native 강조 표시, 선택 수, 취소 전후 원 draft 같음; 일부 선택이면 deck에도 그 요소만 존재 |
| 4 | 두께2, offset0.25, 재료·압력·고정 지정, 법선 확인, 적용, 입력 준비 | FreeCAD native writer 실제 실행. `snapshot.json`, `native_mesh.inp`, `shell.inp`, native sections가 2 mm/offset0.25. 계산 아직 없음 |
| 5 | 준비한 입력 실행 | 기존 JobManager의 새 job/folder, native version2.22, 원 `.12d/.frd/.dat/.sta/.cvg` 및 stdout/stderr. 응력/변형률과 좌표의 출력 format을 parser 가정과 직접 대조 |
| 6 | 3mm 적용 → 새 준비 → 새 실행 | 새 section thickness3. 이전2mm 입력·결과 hash/bytes 그대로. 같은 command 재조회는 새 job을 만들지 않음 |
| 7 | 공간상 압력 방향 유지로 법선 반전 | 실제 S8 순서와 offset/pressure 부호가 함께 반전. `.12d` + FRD top/bottom 이름 교환과 물리적 점/traction 방향 유지. 공학적 허용차를 별도 정해 실제 응답도 비교 |
| 8 | 두께0 및1e를 각각 입력, 오류행에서 저장 → native 프로젝트 닫고 다시 열기 | raw 문자가 그대로; 입력 준비/실행 차단. 취소·실패가 이전 적용/입력을 덮지 않음 |
| 9 | 원 면 참조 상실 또는 형상 변경, 메시 교체, 솔버/재료/단면/압력 객체 교체 | 잘못된 위치/객체 표시. 초안 저장 가능. 재선택 미리보기 취소는 원초안 유지. 적용 복구와 방향 확인 전 실행 차단 |
| 10 | FreeCAD 기존 Ctrl+S/SaveAll/Close 및 연결 끊김 저장 | 셸 raw buffer, 기존 motion editor가 함께 보존. 닫기 취소시 둘 다 유지. 연결 회복 중 새 사용자 편집은 버리지 않음 |
| 11 | 실패/중단/재시도 | 새 folder 사용, 중단된 native process tree 정리 확인, 이전 성공 결과 보존. 원 로그가 남고 부분 결과는 원 상태 유지 |
| 12 | 결과에서 실제 top/bottom U/S/E 조회 | `ShellSide` ±1, 원S8/확장nodeID와 rawFRD 일치. FRD 응력은 recovered nodal, DAT는 internal로 명시. 표면 적분점이라는 허위 label 없음 |
| 13 | `post/` 전체를 새 폴더로 복사하고 FreeCAD/ccx가 없는 환경에서 재열기 | ParaView에서 VTU/PVD 열기, `check_saved_result`에서 실제 원자료 검증. 새 `.frd` 생성이나 solver process 실행 없음 |
| 14 | native 창 넓이400/720, 긴 한국어 Label, 오류행·키보드 포커스 검사 | 잘린 조작 없이 스크롤/선택/적용 가능. 실제 native 스크린샷. HTML/합성 화면을 증거로 쓰지 않음 |

공학적 수치 승인은 별도다. 평판 얇음비·메시 수렴·응력 평가 위치·경계조건 및 부호를 정하고 신뢰할 수 있는 해석해/독립 모델과 비교한다. 이번 2→3mm 검사는 카드 반영과 자료 연계를 확인할 뿐, 굽힘 이론과의 일치 또는 사용자 모델의 설계 안전성을 자동 승인하지 않는다. 정확한 표면 적분점 채널 및 비평균 요소측 표면 결과는 아직 미지원 잔여다.
