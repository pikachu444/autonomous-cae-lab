# 처음 해볼 작업

먼저 [설치 안내](INSTALL_KO.md)를 따라 기본 환경을 준비하세요. 아래 예제는 저장소에
들어 있는 공개 자료를 사용합니다. 개발자의 로컬 `runs` 폴더가 없어도 시작할 수 있습니다.

## 1. CAD 예제를 열고 치수 바꾸기

FreeCAD를 설치했다면 소스 폴더에서 다음 명령을 실행합니다. 실행 파일 경로는 실제 설치
위치로 바꾸세요.

```powershell
.\scripts\start_cae_pre.ps1 -FreeCADExe 'C:\Tools\FreeCAD\bin\freecad.exe' -Source '.\examples\contact\two-feet.FCStd'
```

모델은 받침대 `Base`와 두 발이 있는 `Bridge`입니다. `Bridge`는 `Stock`에서
`Notch`를 뺀 편집 가능한 형상입니다.

1. 모델 트리에서 `Stock`을 선택합니다.
2. 속성의 `Length`를 **20 mm에서 22 mm**로 바꿉니다.
3. 다시 계산한 형상을 확인합니다. 최종 형상을 보려면 `Stock`, `Notch`는 숨기고
   `Base`, `Bridge`를 표시합니다.
4. 다른 이름으로 저장한 뒤 닫고 다시 열어 치수가 남아 있는지 확인합니다.

이 예제 파일에는 재료, 하중, 접촉, 메시와 해석 결과가 들어 있지 않습니다.
형상을 편집한 것과 해석을 마친 것은 구분해서 확인하세요.

접촉 해석을 준비하려면 FEM의 Analysis에서 **Contact**를 엽니다. 두 발의 아래 면을
A로, 받침대의 위 면을 B로 선택하고 **Show faces**로 확인한 뒤 **Apply draft**를 누릅니다.
재료·구속·하중을 지정하고 **Prepare separate body meshes**와 Mesh 탭에서 각 물체의
메시를 만듭니다. Gmsh와 CalculiX 연결이 필요합니다.

개발 때 사용한 공개 예제 조건은 다음과 같습니다.

| 항목 | 값 |
|---|---|
| 탄성계수 / 포아송비 | 210,000 MPa / 0.3 |
| 구속 | 받침대 바닥 고정 |
| 지정 변위 | Bridge 윗면 (0, 0, -0.3) mm |
| 힘 | 두 발에 합계 100 N, -Z 방향 |
| 초기 형상 간극 | 0.2 mm |

연결 동작을 확인하기 위한 합성 조건이며 실제 설계 권장값은 아닙니다.
실행 방법, 결과 열기와 형상 변경 후 참조 복구 절차는
[접촉 작업 안내](CONTACT_WORKFLOW.md)에 있습니다. 형상을 바꾼 뒤에는 옛 면 번호만 믿지 말고 실제 면을 다시 확인하세요.

## 2. 자료를 넣고 연구 질문 저장하기

```powershell
.\Start-CAE-Lab.cmd -Tool expert
```

1. **New discussion…**으로 새 논의를 만듭니다.
2. **Add file…**에서 저장소의 `README.md`를 선택합니다.
3. 가져온 자료를 확인하고 질문을 적습니다. 예: “CAD 예제를 해석하려면 무엇을 준비해야 하는가?”
4. **Apply edits**, **Save discussion**으로 저장합니다.
5. **Open discussion…**으로 다시 열고 질문과 자료를 확인합니다.
   **Read source**로 원문을 읽을 수 있습니다.

이 예제에서는 자료와 질문을 정리합니다. **Request round**로 실제 응답을 받으려면
모델·역할·인증·전송 권한 설정이 필요합니다. 연결되지 않았다면 응답을 받은 것으로
처리하지 않습니다. 기존 구독 연결 기능의 진행 상태는 [현재 개발 상태](../CURRENT_STATE.md)에 있습니다.

## 3. 실제 수치 계산과 결과 파일 만들기

`examples/workbench_numerical.py`는 합성 재료 데이터의 피팅과 검증 구간 비교,
DOE·최적화·불확실성 계산을 수행합니다. CAD, 외부 솔버, AI 계정 없이 실행합니다.
먼저 기본 Research 설치를 마친 뒤 소스 폴더에서 실행하세요.

```powershell
$caePython = Join-Path $env:LOCALAPPDATA 'AutonomousCAELab\windows-runtime\venv\Scripts\python.exe'
$exampleOutput = Join-Path (Get-Location) ('runs\first-study-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
& $caePython .\examples\workbench_numerical.py --output $exampleOutput
```

결과를 덮어쓰지 않도록 매번 새 폴더를 사용합니다. 실행이 끝나면 해당 폴더를 엽니다.

| 결과 | 확인할 내용 |
|---|---|
| `fit-holdout.png` | 피팅과 별도 검증 구간의 곡선 비교 |
| `fit`, `callable-doe`, `optimization` | 계산별 입력·결과 |
| `uq`, `epsilon` | 불확실성·다목적 계산 결과 |
| `summary` | 연구 요약 |

2026-10-13 Windows의 전용 실행 환경에서 이 예제를 끝까지 실행해 위 파일 생성을 확인했습니다.
해당 실행은 약 11초였으며 PC에 따라 달라집니다.

계산은 실제 수치 엔진을 사용하지만 입력은 합성 예제입니다. 사용자 재료의 물성을
검증한 결과는 아닙니다. 이 예제는 Python 사용 경로이며 GUI 전체 사용성 완료를 뜻하지 않습니다.

## 내 모델과 결과로 이어가기

기존 결과는 ParaView Post에서 직접 열 수 있습니다. FreeCAD 모델이나 AI 연결을
먼저 만들 필요는 없습니다. [설치 안내의 Post 실행 명령](INSTALL_KO.md#cad와-후처리-열기)에
사용할 결과 파일을 넣으세요.

MCP는 별도 클라이언트 설정 후 같은 로컬 문서와 명령을 호출하는 선택적 연결입니다.
“모델링부터 해석·전문가 토론까지 전부 자동 완료”하는 설치본을 제공하지는 않습니다.
문헌 검색도 연결된 도구의 지원 범위 안에서 공개 자료를 조회하며, 유료 원문을 구매하지 않습니다.

현재 가능한 작업과 개발 중인 연결은 [현재 개발 상태](../CURRENT_STATE.md), Python·CLI
상세 예시는 [영문 기술 참고](REFERENCE_EN.md)에서 확인할 수 있습니다.
