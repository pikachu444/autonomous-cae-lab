# Dynamic R2-C1: Windows native 파일 식별과 정확한 frame 선택

요청: `PRO-NS2-N3-RETAINED-RESULT-C2-20261015-01-R2-C1`

## 적용 범위와 기준

공식 R2 ZIP의 SHA256은 `2151bc261cd7fc63bd963e8a76defce628d41f476941e6d40a9aee23521149d6`이다.
첨부 Windows probe의 두 core 파일과 그 ZIP의 bytes가 같다. 이번 증분은 그 두 파일만 교정한다.
현재 root main 전체 또는 Workbench/GUI를 복원·교체하는 패치가 아니다. root가 별도로 보존한
FN05 연결, Numerical GUI, Data/Expert/M4/Sol 변경은 대상에 없다. 공통 integration.patch는 필요 없다.

원 Windows 실행은 81 tests 중 22 passed / 24 failed / 35 errors, exit 1이다.
이 결과와 원 R2의 221 pass·합성 400frame 측정은 수정하거나 이번 검사에 더하지 않는다.
제공된 probe는 정상 파일의 path/fd dev·ino·size·mtime·birthtime이 같고 ctime만 다른 사례와
ctime도 같은 사례를 담는다. OS/Python의 특정 버그나 LF/CRLF를 원인으로 단정하지 않는다.

## 1. NativeLines 파일 식별 정책

경로와 열린 descriptor 사이의 공통 비교는 `(dev, ino, size, mtime_ns, birthtime_ns)`이다.
birthtime이 없는 플랫폼은 그 항목을 None으로 유지하며 ctime으로 대체하지 않는다.
한쪽만 birthtime을 제공하거나 값이 다르면 동일 stamp가 아니다. inode가 0이거나 일반 파일이
아니면 안정 식별이 확인되지 않으므로 거절한다. 큰 Windows inode를 축소하거나 timestamp를 반올림하지 않는다.

ctime 검사를 삭제한 것이 아니다. 최초 path.stat과 이후 path.stat, 최초 fstat과 이후 fstat은
각각 자기 API의 ctime까지 정확하게 비교한다. 서로 다른 API의 ctime만 직접 같다고 요구하지 않는다.
atime은 읽기 자체가 바꿀 수 있어 identity에 사용하지 않는다.

첫 pass의 열린 handle을 읽기 전에 경로와 대조하고, scan 종료 시 다시 검사한다. 둘째 pass의
새 handle도 첫 fstat 기준 및 원 경로와 비교한다. finish 전후와 prefix 복사 전후에도 검사한다.
경로 및 모든 상위 경로의 symlink와 지원되는 junction을 다시 확인한다. O_NOFOLLOW가 있는
플랫폼에서는 leaf open에도 사용한다. Windows에서는 같은 path/handle 전후 검사로 검증한다.

두 pass의 SHA256, 실제 scan byte 수와 stat size의 일치, 두 번째 pass의 EOF 검사는 유지한다.
metadata를 그대로 보이게 한 같은 크기 변조도 두 번째 pass의 bytes 해시에서 거절해야 한다.
취소·예외 시 파일 handle과 transient spool을 정리한다. 원 출력에는 쓰지 않는다.

이는 별도 파일 lock, 새 신뢰 cache 또는 모든 시점의 전역 무결성 인증이 아니다. 읽기 완료 후
원 파일이 바뀌면 기존 source pin/selected payload 검증이 계속 필요하다. strict FRD grammar,
failed-prefix cut 규칙, raw hash와 parsed_pin 관계, 원 정밀도·응답·단위는 변경하지 않았다.

정책 판단에 참고한 외부 자료는 Python 3.13 공식 os 문서이다. 문서는 Windows ctime의 의미가
이행 중임을 설명하고 생성 시각에는 birthtime을 구분하며, nonzero ino와 dev의 파일 식별 의미를
설명한다. 이는 호환 정책의 근거이지 이번 설치 환경의 정확한 내부 원인을 확인한 증거는 아니다.
출처: https://docs.python.org/3.13/library/os.html#os.stat_result
확인일: 2026-10-15.

## 2. 선택과 metadata 조회의 허용 경계

`select_frame(attempt, frame_index, *, expected_native=None, **expected)`의 signature는 유지한다.
metadata_only 생략 또는 정확한 Python bool False만 허용한다. True, 0/1, None, 문자열 및 컨테이너는
파일을 읽기 전에 ValueError로 명시 거절한다. False와 정수 0을 같은 옵션으로 암묵 변환하지 않는다.

```python
from caelab.dynamic_result_store import describe_attempt, select_frame, verify_attempt

# catalogue: index와 identity/path/size 검사. 미선택 frame와 원 source bytes는 DEFERRED.
view = describe_attempt(attempt, expected_job_id=job_id, expected_snapshot_id=snapshot_id)

# 실제 frame: topology + 선택 frame의 bytes/hash 및 exact native identity를 검사한 뒤 반환.
selected = select_frame(
    attempt, 1, metadata_only=False, verification='selected',
    expected_job_id=job_id, expected_snapshot_id=snapshot_id,
    expected_native=view['frames'][1]['native'],
)

# 명시 전체 audit: 원 source를 포함한 전체 referenced bytes를 읽는다.
audit = verify_attempt(attempt, expected_job_id=job_id)
```

`verification='selected'/'full'`, `expected_result`, `expected_job_id`, `expected_snapshot_id`,
`expected_record`, `expected_native`는 기존 의미 그대로다. 모르는 옵션은 기존 signature 검사로
거절한다. `select_frame(..., metadata_only=True)`는 full audit 옵션과 함께 줘도 거절한다.
metadata navigation은 `describe_attempt()` 또는 `read_attempt(metadata_only=True)`를 사용한다.
GUI disable이 아니라 core API의 gate이므로 Python/CLI/service의 직접 호출에도 적용된다.

성공한 select만 `selected_frame_bytes='VERIFIED'`를 반환한다. selected 모드의 미선택 payload 및
raw source는 DEFERRED다. full 모드는 전체 bytes 검사 후 그 범위를 보고한다. 원 execution_status,
UNKNOWN qualification, 원 job/snapshot/result/native identity 및 failed partial은 그대로 유지한다.

## 적용 및 좁은 검증

root는 별도 검토 트리의 두 core가 `BASE_AND_FILES.json`의 before hash와 일치하는지 확인한다.
그 상태에 이번 `product.patch`만 check/apply한다. 원 R2 패치를 이번 증분으로 바꾸지 않는다.
현재 core가 달라져 있다면 전체 파일을 덮지 말고 두 hunk를 기존 변경과 대조한다.
패치에 공통 파일·GUI·수치 policy는 없다. 예시는 root/Codex 통합용이다.

```powershell
git apply --check C:\delivery\R2-C1\product.patch
git apply C:\delivery\R2-C1\product.patch
python -m pytest tests/test_dynamic_r2_c1_native_identity.py tests/test_dynamic_r2_c1_selection.py -q
```

먼저 위 직접 반례를 실행한다. 이후 streaming/integrity/recovery, retained R1 및 correction Post의
작은 회귀를 검증한다. 새 테스트는 기존 R2의 `test_dynamic_r2_integrity` fixture와 기존 synthetic
adapter/JobManager를 재사용한다. native process는 대역이며 새 ccx를 호출하지 않는다.
전용 JSON test fixture는 원 probe의 줄바꿈만 LF로 정리한 동일 값 copy다. 원 probe ZIP bytes는
인도 provenance에 그대로 보존한다. Windows stat의 정확 레코드 unit 비교와 ctime/birthtime을 주입한 LF·CRLF 실제 파일 읽기를
구별한다. 후자는 Linux 호스트 검사이지 실제 Windows stat의 새 관측이 아니다.
symlink 생성 권한이 없는 Windows 환경에서는 해당 테스트만 이유를 기록하며 skip한다.
나머지 검사는 자동으로 성공 처리하지 않는다.

## 미실행·남은 수용

이번 호스트의 Windows 재검사, native ccx/WRITE→READ, 원 full400 처리, FreeCAD/ParaView/PySide6
실제 화면 조작, continuous/split 물리 수용은 NOT_RUN이다. 새 400frame size campaign도 하지 않는다.
기존 tolerance/comparator와 수치 policy UNKNOWN을 유지한다. E3–E6/C1–C6, explicit FN16–17 및
broader law/contact 수용을 이 두 결함 교정으로 완료 처리하지 않는다.
