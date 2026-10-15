# FN32 C1 Windows 검사 기록

Pro의 원 ZIP과 교정 ZIP을 보존하고 공개 main `0045f5fd5e18f0047f557363bf1b996664b948b1`의 별도 사본에
첫 인도, C1, Sol의 미리보기 크기 보완 순서로 적용했다. 공통 파일의 main 통합은 root가 소유한다.
이 기록의 검사 결과와 실제 GUI·native 전체 인도 완료는 구별한다.

Windows의 기존 private Python에서 영향 검사 결과는 **209 passed, 1 failed, 3 modules skipped**였다.
실패 한 건은 정상 `--script=C:\…\apps\desktop_post\startup.py` 인자를 POSIX 슬래시 문자열 suffix로
검사하던 테스트였다. 실행 코드 대신 테스트를 정확한 `Path.resolve()` 동등성 비교로 고쳤고 해당 한 건을
다시 실행하여 **1 passed**를 확인했다. 변경 없는 209건을 반복 실행하지 않았다.

실제 PySide6 Qt 13건은 실행됐다. VTK, native export contract, origin native contract 세 모듈은
private Python에 VTK가 없어 모듈 전체가 skip됐다. Pro의 Linux 실행 집계와 합산하지 않는다.
기존 Windows QPrinter 진단과 PDF 생성 성공은 별개이며 일반 native 인쇄 완료를 뜻하지 않는다.

정상 1000×800과 좁은 800×700 원자료 대화상자를 실제 Windows Qt로 표시하여 한글과 그림 맞춤,
Tab 포커스, 변경된 원창의 명시 거절, 창을 닫고 명시적으로 다시 연 복구, 기존 보고서 보존을 확인했다.
이 GUI 검사는 공개 합성 PNG와 모의 native receipt를 사용했다. 실제 native 열기 응답을 대신하지 않는다.

설치된 stock ParaView **6.2.0 Windows Python3.12**의 별도 `pvpython` 프로세스에서는 다음 작은 왕복을
실제로 수행했다. provider·solver·장비나 사용자의 기존 창은 사용하지 않았다.

- 공개 manufactured PVD를 직접 열고 Clip을 적용·저장한 뒤 기존 `Workspace.export`로 실제 PNG를 저장했다.
  `/2` snapshot의 원결과·배열·표시조건 검증과 같은 Owner의 `verify_live`가 성공했다.
- 새 프로세스에서 정확한 saved PVSM을 `allow_repair=False`로 복원하고 보존 pipeline/view를 선택하여
  원값을 다시 검증했다. 원 PNG의 바이트 해시는 그대로였다.
- 직접 파일에는 검증된 등록 선언이 없어 단위·축 의미를 미확인으로 유지했다. 첫 시도에서 선언만 전달한
  입력은 기존 registered receipt gate가 거절했으며, 그 실패도 보존했다. 임의 receipt를 만들지 않았다.

모든 실행은 `scripts/native_check.py`의 독립 Windows Job으로 관리했다. Qt, 경로 테스트,
native 생성·cold reopen의 최종 receipt는 모두 exit 0, `cleanup=job_empty`였다.
원 실패 기록과 보완 patch는 무시되는 팀 작업 폴더에 보존했다.

아직 수행하지 않은 범위는 실제 broker/GUI `document.activate`, 닫힌 원창의 launcher부터 Report까지의
전체 왕복, composite 블록 override의 전체 실제 캡처 반례, 선언된 물리·정적·고정 축의 모든 native 사례,
출력 PDF의 전체 글리프 렌더 대조다. 위 작은 성공으로 이 범위를 통과 처리하지 않는다.
FN05 불확실성·측정위치·최종 피팅점 진단, FN30 전체 중단·재개, FN35 실장비 인도도 별도 잔여다.

복합 블록의 실제 SM API를 확인하려던 추가 한정 검사에서는 stock ParaView가
`0xC0000005`로 종료했다. 원 검사와 Render를 제외하고 flush 경계를 추가한 한 번의 좁은 재확인
모두 `cleanup=job_empty`였으며 stdout/stderr는 비어 있었다. 최초 checkpoint는 두 XML reader와
`GroupDatasets.UpdatePipeline()` 뒤에 두었으므로 그 이전 구간의 정확한 실패 호출은 미확인이다.
`report_image_blocks.inspect`, `ColorBlocksBy`, Render에 도달했다는 증거가 없어 어느 것을 원인으로
단정하지 않는다. 원 하네스·공개 입력·실패 receipt를 보존하고 이 native 검사를 반복하지 않았다.
따라서 composite의 전체 실제 렌더·캡처 수용은 미확인으로 남는다.
