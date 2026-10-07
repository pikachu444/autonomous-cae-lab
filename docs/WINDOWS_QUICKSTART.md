# Windows에서 설치하고 첫 계산하기

## 시작

1. 저장소의 **Code → Download ZIP**으로 내려받아 사용자 폴더에 압축을 푼다.
2. **Start-CAE-Lab.cmd**를 더블클릭한다. 첫 실행은 인터넷에서 uv, 전용
   Python 3.12와 수치·재료 패키지를 설치하므로 시간이 걸린다.
3. 열린 브라우저에서 **시험·해석 파일 읽고 비교** 또는 **재료 동정·조건 탐색**을 고른다.

Windows 10/11 x64의 기본 Windows PowerShell 5.1을 사용한다. WSL, Git,
미리 설치한 Python, 관리자 권한이 필요하지 않다. 설치에는 GitHub와 Python
패키지·런타임 다운로드 서버에 대한 인터넷 접근이 필요하다. 회사의 실행·통신
정책이 이를 막는 경우 해당 정책을 우회하지 않는다.

다시 더블클릭하면 동일한 설정으로 실행 중인 작업대를 다시 연다. 소스나 설정이
바뀌면 이전 서버에 조용히 연결하지 않고 재시작이 필요하다고 알린다.
압축을 푼 소스 폴더를 계속 보관해야 한다. 설치된 환경이 그 코드를 사용한다.

## 첫 작업

**파일 비교:** CSV/TXT 파일 추가 → 표 미리보기에서 축·응답 열 확인 → 단위,
성분, 위치 입력 → **지정한 열로 결과 읽기**. 두 번째 파일도 읽은 뒤 결과의
**저장 곡선 두 개 비교**에서 파일명과 응답을 선택한다. 결과에는 중첩 곡선,
RMSE와 평균절대오차가 표시된다. 원본 솔버를 다시 실행하지 않는다.
NaN/Inf가 있는 수치 행은 머리글로 버리지 않고 오류로 남긴다.

**재료 계산:** 재료 법칙, E/ν와 시간별 변형구배를 편집 → **현재 조건 평가**.
**합성 교육용 이력**은 조작을 익히기 위한 입력이며 실제 시험 자료가 아니다.
이는 FELUPE 재료점 계산이다. 유한요소 경계조건 해석이나 실제 재료 적합성
승인을 대신하지 않는다. 결과를 연 뒤 **연구 보고서 미리보기/저장**을 사용할 수 있다.

연구 이름은 작업 기록에 남는다. 표의 단위·성분·위치는 자동으로 확정하지 않는다.
결과 그래프를 일부 행으로 좁혀도 오차 지표는 전체 비교에 대한 기존 값이다.
결과의 **완료 결과로 후속 질문**은 해당 결과를 전문가 상담에 선택한다.
전문가를 별도로 설정하지 않은 설치에서는 **설정된 전문가 없음**이 표시된다.

## 지금 설치되는 범위

| 기능 | Windows 기본 설치 |
|---|---|
| 파일 읽기·저장 결과 재열람·비교·HTML 보고서 | 포함, 실제 실행 확인 |
| SciPy DOE·동정·최적화의 공통 수치 기능 | 포함; 계산할 모델은 별도 요구조건을 따른다 |
| FELUPE 재료점 응력·탄젠트 | 포함, 실제 실행 확인 |
| FreeCAD/CadQuery, Gmsh/CalculiX | 별도 네이티브 설치와 고정 upstream 필요; 이 설치 시험으로 Windows 전체 경로를 검증한 것은 아니다 |
| Code_Aster, DOLFINx, MFront/MGIS, OpenCourant | 별도 실행환경 필요; 현재 Linux/WSL 실험 기록과 Windows 설치 지원을 혼동하지 않는다 |
| OpenScience·자료 검색·LLM 전문가 | 선택 설치·계정 설정 필요; 기본 계산에는 필요하지 않다 |

기존 CAD·구조 작업 화면은 시작 화면의 링크로 이동한다. GitHub ZIP에는
submodule 내용이 없으므로 그 링크가 보이는 것만으로 CAD 실행 준비가 된 것은 아니다.
Code_Aster 정준 반력 검증과 물리적·회사 배포 승인은 여전히 미완료다.

## 저장 위치와 운영

- 전용 도구/Python/로그: `%LOCALAPPDATA%\AutonomousCAELab\windows-runtime`
- 계산·원본·결과: `%LOCALAPPDATA%\AutonomousCAELab\research-store`
- 선택적 운영자 설정: `%LOCALAPPDATA%\AutonomousCAELab\workbench-config.json`

설치·서버 시작 기록은 전용 런타임 폴더에 남는다. 원본·실험을 덮어쓰거나
시스템 Python/PATH를 변경하지 않는다. 서버는 127.0.0.1에만 연결한다.
브라우저를 닫아도 계산 서버는 계속 실행된다.

PowerShell에서 다른 포트·저장소를 선택할 수 있다:

```powershell
.\Start-CAE-Lab.cmd -Port 8770 -Store 'D:\CAE Research\runs'
# 브라우저 없이 설치만 확인
.\Start-CAE-Lab.cmd -InstallOnly -NoBrowser
```

서버를 종료할 때는 작업 완료를 확인한 후 실행한다. 이 명령은 실행 중인 작업을
중단할 수 있으며 이 시작 스크립트가 소유한 서버만 종료한다. 데이터는 보존한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop-windows.ps1 -Force
```

다른 포트/런타임으로 시작했다면 종료 시에도 같은 `-Port`/`-RuntimeRoot`를 지정한다.

## 선택 근거와 이후 확장

Python 설치·패키지 의존성 관리는 기존 **uv**를 재사용한다. 직접 패키지 관리자를
만들지 않았다. [uv 설치](https://docs.astral.sh/uv/getting-started/installation/)와
[관리형 Python](https://docs.astral.sh/uv/guides/install-python/)의 공식 기능을
전용 사용자 폴더에 연결한다. uv 실행파일은 고정 버전과 SHA-256으로 검사한다.
uv는 MIT/Apache-2.0이며, 설치되는 각 수치 패키지의 라이선스는 별도로 적용된다.

2026-10-08 사용자 결정: **온라인 Windows 단독 실행을 먼저**, 이후 Windows
화면과 Linux 계산 서버의 연결을 확장한다. Windows/Linux 각각 독립 실행은
각 OS에 앱과 필요한 계산환경을 따로 설치한다는 뜻이다. 세 번째 별도 런타임이 아니다.
Linux/WSL에서 검증한 솔버가 자동으로 Windows에서도 지원되는 것은 아니다.

오프라인 배포는 향후 고정 의존성·플랫폼별 바이너리·라이선스·해시를 묶는
방식으로 고려한다. **이번 작업에서는 오프라인 묶음을 구현하거나 배포하지 않았다.**
