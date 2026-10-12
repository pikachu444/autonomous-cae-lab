# Codex 회수 인계 — D1 원본 / Penpot 제외

요청 **PRO-DESKTOP-DESIGN-20261012-03**. 같은 실제 Pro 작업에서 작성한 D1의 파일 전달과 Penpot 제외 교정만 수행한다. 모델/공급자/설정 전환, 새 전체 설계, 제품 구현을 시작하지 않는다.

## 1. 원본 회수

이 부록 README의 ZIP 링크 또는 별도 `design/pro-desktop-d1-20261012` 브랜치에서 원본을 회수한다. 원 ZIP은 13,407,914 bytes이고 SHA256은 다음과 같다.

```text
d65fe390dcaa5d35f4bc8c06fdb2ddd897cf6b014c417c3288b6c3f60a49bed1
```

Windows에서 `Get-FileHash -Algorithm SHA256`으로 받은 ZIP을 대조한다. 압축을 풀면 287개 member가 모두 `docs/design/20261012-desktop-planning/pro-authored/` 아래에 있다. 원 ARCHIVE_MANIFEST의 286개 파일 해시와 manifest 자체를 보존한다. 기존 로컬 사용자 변경이 있으면 새 디렉터리/별도 checkout에 풀고 비교한다. 충돌 파일을 덮어쓰거나 force push하지 않는다.

이 `delivery-20261012-03/` 부록은 원 ZIP에 포함되지 않은 최신 전달 기록이다. 원 D1을 다시 생성할 필요가 없다. 화면 generation script 실행이나 기존 시안 재생성으로 원본 해시를 바꾸지 않는다.

## 2. 최신 검토 경로

**Penpot 계정·로그인·편집·native export는 제거된 과제다.** 계정 생성을 제안하거나 도구 재연결을 기다리지 않는다. 원 D1 인계에 남은 Penpot 지시는 이 문서와 DECISIONS 부록으로 대체한다.

1. `screens/*.svg`, `screens/screens.json`, `.drawio`, `.ui`와 원본 Python을 실제 파일로 연다.
2. 기존 Windows PySide6 6.9.1·Matplotlib 환경을 지정해 D1의 `prototype/Start-PlanningPrototype.ps1`을 실행한다. 기본은 gallery, `-MaterialOnly`는 별도 Material harness다. 이미 설치된 환경을 사용하고 새 유료 의존성을 추가하지 않는다.
3. D1 `PROTOTYPE_SCENARIOS.md`의 실제 화면/핫스팟 ID로 작업을 따라간다. 실제 Qt 클릭·focus·keyboard·선택·draft/save/reopen과 정적 화면 전이 설계를 분리해 기록한다.
4. 원 D1·최신 사용자 요구·이 Penpot 제외 부록·기준 소스·실제 확인 자료를 별도 Astra 전체 독립 검토에 전달한다. 기존 D1 리뷰는 보존하며 새로운 Windows 수용을 대신하지 않는다.
5. 발견한 차이만 의미 있는 correction으로 연결한다. 전체 설계를 처음부터 다시 작성하거나 변경하지 않은 solver 캠페인을 재실행하지 않는다.

## 3. Codex 별도 spike 기록과 D1의 구별

이번 요청은 Codex가 자신의 Qt spike에 Astra 8개 교정 및 실제 Windows file chooser/selection/adoption/Undo/dock/save/cold-reopen을 확인했다고 전달했다. 공개 main `313679843813b63dee44409de5c5abc43c8a373b`의 CURRENT_STATE에서도 해당 spike 기록과 D1 ZIP 미회수를 구분하고 있다.

이는 Codex spike의 기존 증거다. D1 전체 Qt 소스/새 화면의 실행 통과로 표시하지 않는다. D1은 별도 source와 hash를 기준으로 실제 확인한 조작을 추가 기록한다. solver/provider 연결 없는 SIMULATED UI 표기를 유지한다.

## 4. 저장소와 다음 상태 갱신

이 게시 작업의 변경 범위는 `docs/design/20261012-desktop-planning/pro-authored/`에 추가한 D1 원본과 전달 부록뿐이다. main, production code, 설정, threshold, CURRENT_STATE를 수정하지 않는다. PR 생성이나 workflow 실행도 요청하지 않는다.

Codex가 파일을 실제 회수한 뒤 자신의 운영 범위에서 CURRENT_STATE/Space의 “ZIP 미회수” 상태를 사실에 맞게 갱신한다. 다운로드 확인·원본 정합·새 독립 검토·실제 Qt 확인·사용자 검토 제출을 구분한다. 제품 본구현은 사용자의 개발 시작 지시 이후다.
