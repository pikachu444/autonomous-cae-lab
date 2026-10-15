# 원격 실행 작성 중 체크포인트

> 아래는 2026-10-15 중단 당시의 보존 기록이다. 2026-10-16 재개한 구현과
> 확인/미확인 구분은 [현재 인도 기록](DELIVERY.md)과 [사용법](USAGE_KO.md)을 따른다.

2026-10-15. 최신 사용자 지시 **전후처리 연결 후 추가 개발**에 따라 작성 중인
B8.4/FN-26 작업을 보존하고 담당 파일 소유를 root에 반환한다.
이 기록은 완료 판정이나 새 작업 우선순위가 아니다. 현재 배정의 원본은 CURRENT_STATE다.

## 현재 파일

- `caelab/remote_schedulers.py`: Slurm/OpenPBS 제출 argv·ID/상태 파서와, 기존 SSH를 통해
  한 명령씩 실행하는 POSIX helper 초안. 제출 전 atomic claim, 같은 token 재조회,
  취소 요청과 종료 확인 분리, 명시 파일 회수와 SHA 검사 흐름을 작성했다.
  SSH 직접 실행에는 작업 수명 동안만 동작하는 foreground supervisor 초안이 있다.
- `caelab/remote_transport.py`: 기존 `execution_control.run_owned_command`와 Windows Job/
  POSIX group 소유를 이용하는 SSH pipe 초안. 기존 인증·known_hosts를 사용하며
  자격증명 설정·agent 전달·호스트 설치 경로는 추가하지 않았다.
- `caelab/remote_execution.py`: 기존 JobManager의 callback으로 사용할 run/reconnect/cancel,
  순수 catalog/preview/status와 전용 CLI 초안. 원 입력은 기존 job 결과 폴더 안에 보존하고
  export/import_batch의 exchange/case/candidate/typed values 검증을 호출한다.

세 파일은 **미검증·미통합 초안**이다. 제품의 사용 가능한 원격 기능으로 표시하지 않는다.
신규 backend/owner/store/scheduler framework나 공통 파일 변경은 없다.

## 재사용과 예정 공통 연결

- `caelab/jobs.py`: 기존 request_id/request_hash, 작업·결과 저장, 중단 후 INTERRUPTED,
  취소 요청과 CLEANUP_PENDING 수명을 유지한다.
- `caelab/numerical.py`: 기존 export_batch/import_batch로 원 후보·미회수 행을 검증한다.
- `caelab/adapters/external_files.py`: 등록된 argv·입력 파일/템플릿·출력 읽기를 재사용할
  remote batch worker는 아직 작성하지 않았다. 별도 수치 엔진으로 대체하지 않는다.
- 공통 root patch는 아직 작성하지 않았다. 예정 접점은 Workbench OPERATIONS/submit의
  원격 인자 admission와 명시 stable request_id 요구, `_execute`의 전용 callback,
  `/api/workbench/remote`의 순수 catalog/preview/status route, Runner의 전용 창 메뉴다.
  기존 `Client.submit/job/cancel/result`와 기존 HTTP 인증 경계를 재사용한다.
- 운영자 설정의 `remote_hosts`에서 기존 승인 host·scheduler·queue/account·runtime·
  작업 root와 예산을 선택하는 초안이다. 사용자 요청으로 실행 명령·인증 설정을 받지 않는다.

## 이어서 끝낼 항목

1. 공개 명령 fixtures와 실제 기존 JobManager를 묶은 최소 runnable/tests를 작성한다.
   아직 Python 구문 검사·단위 검사·HTTP/CLI·프로세스 실행을 하나도 수행하지 않았다.
   작성한 코드의 분기나 예외 처리에 결함이 남을 수 있다.
2. 특히 제출 응답 유실/claim과 cancel 경쟁/같은 ID 재조회, 종료 불명·accounting 없음,
   출력 checksum/경로/누락/duplicate/stale/단위/실패 행과 cold 재접속을 검사한다.
3. 재접속의 retained record/token/origin과 원 job 인자 간 tamper 방지 검증을 보강한다.
   remote response의 `data_ref`는 현재 자동으로 안전한 로컬 배열로 수리되지 않는다.
   임의 참조는 거절하거나 검증된 회수 파일만 읽도록 명확히 정한 뒤 검사해야 한다.
4. 등록된 foreground runtime의 자식 프로세스 종료 계약과 remote supervisor를 검토한다.
   SSH 접속 종료·qdel/scancel 성공·프로세스 PID 부재만으로 실제 종료를 주장하지 않는다.
   Slurm/PBS 버전별 명령·history 출력과 공유 경로 조건도 fixtures로 확정한다.
5. 기존 ExternalFilesAdapter를 사용하는 최소 batch worker/결과 envelope와 한글 사용법,
   root용 최소 공통 통합 patch, 새 remote 전용 Qt dialog를 작성한다.
6. root가 공통 연결을 적용한 뒤 영향 범위의 최소 검사와 실제 Qt 사용 흐름을 확인하고
   끝 묶음에서 독립 검토 한 번을 받는다. 새 계산 campaign은 선행조건이 아니다.

## 실행·외부 입력 상태

코드/문서 작성과 관련 소스·공식 문서 읽기만 수행했다. 승인 host 없음, SSH/Slurm/PBS
호출·provider·solver·설치·Qt·테스트·CI·stage·commit은 **모두 실행하지 않았다**.
사용자 SSH 설정과 다른 작성자의 파일은 바꾸지 않았다. 테스트 창·서버·원격 작업도 만들지 않았다.

기존 승인 host·queue/account·전송 권한·runtime·실제 작업 경로가 제공되기 전에는
live 제출/중지/재접속/회수를 NOT_RUN으로 남긴다. 이는 원 요구의 삭제나 전체 기능 완료가 아니다.

## 확인한 공식 계약

- [Slurm sbatch](https://slurm.schedmd.com/sbatch.html): parsable 제출 ID, 자원·queue/account,
  제출 성공과 실제 실행의 구별.
- [Slurm squeue](https://slurm.schedmd.com/squeue.html),
  [sacct](https://slurm.schedmd.com/sacct.html),
  [scancel](https://slurm.schedmd.com/scancel.html): 조회·accounting·취소를 별도 단계로 사용.
- [OpenPBS qstat 원문](https://github.com/openpbs/openpbs/blob/master/doc/man1/qstat.1B):
  JSON 상세 출력과 종료 history, 전체 job ID 사용. 원문/구현을 복사해 vendoring하지 않았다.
