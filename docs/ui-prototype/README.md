# CAE Lab interaction study

2026-10-10에 만든 조작 가능한 UI 설계 시안입니다. 제품 소스 기준은
`a10f2023a2084512839b5e0af8ab0adc0aeb9293`이며, 기존 앱을 교체하거나
Core·solver·FreeCAD·ParaView·LLM에 연결하지 않습니다. 모든 형상, 결과,
대화, 실행 상태는 합성 예시입니다.

## 열기

배포된 `index.html` 한 파일을 브라우저에서 엽니다. CDN이나 서버 연결은
필요하지 않습니다. 창 너비 1100px 이상을 권장합니다. 상단 선택기는
여섯 작업 배치를 한 파일에서 검토하기 위한 것이며 제품의 독립 앱
launcher를 구현한 것은 아닙니다.

소스에서 다시 만들려면 이 디렉터리에서 실행합니다.

```powershell
npm ci
npm run check
npm run build
python -m http.server 8941 --bind 127.0.0.1 --directory dist
```

브라우저에서 `http://127.0.0.1:8941`을 엽니다. 마지막 명령은 검토용
로컬 정적 서버이며 종료는 해당 터미널에서 Ctrl+C로 합니다.
`dist/index.html`은 모든 스크립트·스타일을 포함합니다.

## 직접 확인할 조작

- Pre: 치수 편집 중 다른 부품 선택, 자료 행·배율·사용 구간 변경,
  재료점/PDE 전환, 저장 실패 후 재시도.
- Post: Source A/B 선택, 연산별 입력, B 누락 복구, 카메라·시간·색
  범위 연결. 분석 생성은 정의 저장 예시이며 native 계산은 하지 않습니다.
- Runner: 새 초안→입력 검사→준비→제출. 응답 유실 후 같은 요청 조회,
  제출 입력 읽기, 선택한 실행만 취소.
- Optimization: 범위 셀 편집→명시 적용. 후보표·Pareto 점·상세·응답 곡선은
  같은 후보 ID를 선택합니다. 예측·실패·결측을 구별합니다.
- Expert: 발언별 원문, 논점별 답글 초안, 계획 변경 전후 비교, 특정 job
  취소. 전송은 미리 작성된 대화에 로컬 예시 발언을 추가합니다.
- Workbench: 노드·포트·연결 선택, 포트 연결, 형식/스키마 오류,
  원본 revision과 연결 저장 실패 복구. 앱 열기는 시안 내 화면 전환입니다.
- 공통: 경계 드래그로 크기 조절, 작업창 확대/복원, 이동 메뉴,
  배치 저장·재열기. 고정 명령 영역과 스크롤 본문을 구분합니다.

배치와 예시 입력은 `cae-design-v2:` 브라우저 저장소에 남습니다. 저장
실패 시 현재 창에 남은 변경과 재시도를 표시합니다. 실패 시험은 같은
저장 처리 경로에 주입한 오류이며 실제 디스크·quota 오류 검증은 아닙니다.
저장을 복구하기 전 재열기는 미저장 입력을 잃을 수 있습니다.

## 검증과 기술 선택

[REVIEW.md](REVIEW.md)에 실제 관찰, 독립 검수와 미검증 범위를 기록했습니다.
[DESIGN.md](DESIGN.md)는 배치와 구현 경계입니다. 소스·lockfile은 Git에,
생성 번들과 캡처는 Page 첨부 및 검증 기록의 SHA-256으로 보존합니다.

Dockview 5.2.0, AG Grid Community 36.2.0, React Flow 12.12.0,
Plotly basic 3.7.0, React 19.3.0, Three.js 0.180.0, Lucide 0.468.0을
사용합니다. 빌드는 TypeScript 5.9.3과 esbuild 0.25.12입니다.
무료 배포 기능만 사용했으며 제품 패키지의 최종 채택 결정은 아닙니다.
제품 Pre/Post의 native 선택·property·transaction·렌더러는 해당 host를
재사용해야 합니다. 합성 Three.js 장면은 native 통합을 대체하지 않습니다.

실제 공통 문서 저장, source별 부분 복구, exact-open, JobManager·reader,
native 재메시·조건 검증, 회사/물리 승인과 52개 전체 요구의 수용은
별도 작업입니다. UNKNOWN/NOT_RELEASED를 유지합니다.
