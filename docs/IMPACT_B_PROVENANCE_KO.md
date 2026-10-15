# B 구현 근거와 확인 수준

## 정확한 입력

공개 제품 ce9ec3aefc6b7bc759b7b6bda23177595dbd3cd1, fixture 3e48bf6138f495299f45b1af254bfb4aaff307b8. 직접 ZIP은 5,509,863 bytes, SHA256 b50179874335dc311e902729076bfe3e0854adcbeef6add85113836ac04827e7, 936 entries다. unpacked 원문과 새 작업본을 분리했다. 정확한 추가/수정 파일의 before/after는 반환 BASE_AND_FILES.json을 따른다.

## Primary source와 적용

모든 아래 native 경로의 기준은 OpenCourant cb760c206e346eff12161a2268b134ef9d48a4ef이다. 원문 source와 기존 LICENSE/COPYRIGHT 및 개별 header를 ZIP의 references에 그대로 보존한다. 버전이 다른 최신 도움말을 release binary 실행 증거로 사용하지 않는다.

| 원문 | 확인·사용한 내용 |
|---|---|
| starter/source/materials/fail/inievo/hm_read_fail_inievo.F, radioss2022/FAIL/fail_inievo.cfg | NINIEVO/INITYPE/EVOTYPE/EVOSHAP/ILEN/FAILIP/TAB_ID/SR_REF/ENER의 실제 읽기 순서와 fixed field width. |
| engine/source/materials/mat_share/mulaw.F90, mmain.F90 | LAW36→mstrain_rate(EPSD,IDEV1), stress 계산과 IRUPT42 solid fail_inievo_s hook, actual deletion/state buffer 전달. |
| engine/source/materials/fail/inievo/fail_inievo_s.F | solid만의 initial V^(1/3), [-1,1] eta clip, EPSD/SR_REF table 좌표, initiation/evolution 저장 및 factor2·YLD0 energy-linear branch. |
| mat036/sigeps36.F, starter mat036 reader/CFG | NRATE1에서는 rate-hardening interpolation 없음. 원 VP0/Fsmooth0와 자체 cutoff 비활성 유지. |
| mat117/sigeps117.F90, hm_read_mat117.F90, radioss2612/MAT/mat117.cfg | envelope/unload와 압축 branch, fork 추가 fields와 이전 fallback 구분. 기존 material engine을 새로 작성하지 않음. |
| engine/source/output/th/hist1.F, hist2.F | actual TFILE/4 framing, title length, group/member/variable, actual timestep sample의 complete record layout. |
| radioss2025/OUTPUTBLOCK/th_bric.cfg | OFF, IE density, PLAS, VOL, DAMA sum, PLSR 이름/범위. 고유 damage dissipation을 생성하지 않음. |
| radioss110/OUTPUTBLOCK/th_inter.cfg | FN/FT signed components와 groups. 절대합·새 CE 필드의 현재 binary 지원은 별도. |
| tools/anim_to_vtk/README.md, tools/th_to_csv/README.md | converter source가 별도 Tools repository로 이동했음. release에 고정된 binary와 임의 Tools commit을 동일 source로 취급하지 않음. |

공식 보조 설명은 Altair /TABLE/1, /PROP/TYPE14 SOLID, /FAIL/INIEVO, /MAT/LAW36, /MAT/LAW117 및 2021 /TH/INTER다. TABLE/1 dim1/dim2 fixed serialization 및 HEPH single-point 설명은 보조 문서와 대조했다. Starter/Engine 실측으로 승격하지 않았다. table 경계 밖은 교정 UNKNOWN이며 native TABLE_VINTERP 구현의 모든 외삽 정책을 이 Python 코드가 대체하거나 인증하지 않는다.

## rate 해석 정정

작성 도중 EPSD/SR_REF도 [-1,1]로 clip한다는 잘못된 중간 설명이 있었다. **최종 코드는 그렇게 처리하지 않는다.** exact fail_inievo_s는 eta를 clip하고 두 번째 좌표에 EPSP/SR_REF를 대입한다. 온도는 이 함수의 실제 table 좌표가 아니다. 원 calibration range, raw eta, clipped eta, normalized rate를 분리한 회귀를 포함한다. 미확인 TABLE_VINTERP 내부 정책을 발명하지 않는다.

## 증거 등급

`CODE_AND_PYTHON_CONVERTER`: 실제 배포된 Python inp2rad 원문과 제품 postflight/card 작성 코드의 실행. `SYNTHETIC_NATIVE_FORMAT`: pinned framing/배열 계약으로 직접 작성한 fixture의 strict reader·재후처리. `EXISTING_OWNER_COLD_PROCESS`: 실제 기존 owner/jobs/revision/assets와 새 Python 프로세스 사용, 원 native data만 synthetic. `NOT_RUN`: Windows/Starter/Engine/converter binary/Qt/native material campaign.

어느 등급도 calibrated material strength/durability certification이 아니다. qualification은 UNKNOWN, engineering decision은 NOT_RELEASED다. 기존 실패와 허용치를 고치지 않았다. 개발 중 실패한 테스트/잘못된 fixture/API 호출 기록은 verification/development에 남기며 최종 통과 수에 합산하지 않는다.

## 라이선스

반환 references의 OpenCourant source는 원 AGPL-3.0 LICENSE.md, COPYRIGHT.md 및 개별 notice를 유지한다. CFG 파일의 개별 Siemens/Altair notice가 있으며 AGPL이라는 이유로 CFG/번들 binary 재배포 허가를 일반화하지 않는다. CFG를 수정·생성해 배포하지 않는다. Python 제품 helper는 runtime/CFG를 패키징하거나 설치하지 않는다.

inp2rad.py에 실제 포함된 MIT copyright/permission header와 CAELAB_NOTICE.md를 그대로 포함한다. 별도 LICENSE 파일이 있는 것으로 가정하지 않는다. 사용자 제품 전체의 최상위 LICENSE는 이 source packet에서 확인하지 못했으므로 임의로 MIT/AGPL 또는 다른 라이선스를 붙이지 않는다. 신규 작성물의 저장소 라이선스 적용과 외부 배포 판단은 기존 프로젝트 정책과 원 source 의무를 확인해야 한다. font·binary·새 유료 의존성은 포함하지 않는다.

## 현재 소스에 통합할 때의 경계

2026-10-16 `ade0ca6503d1f4101758bd7c7ebb5dc666a6fa7f` 위에서 Sol이 원 Pro 전용19파일을 재사용했다. 원25파일 중 최근 `impact_recovery`와 중복되는 이전 재후처리 본체3개·검사3개는 원 회수 자료에 보존하고 제품에 중복 추가하지 않았다. 전용 facade는 이전 `b_readback` 초안의 우회 실행을 명시 거절하며, 공통 Workbench/Simulation dispatch를 새로 만들지 않는다. 원 B 수용표·native NOT_RUN·pair 및 계면 반복 이력 잔여는 그대로다.

공통 소스는 root가 현재 main의 A admission·부분 읽기·원 참조 보호와 정합할 최소 hunk로 분리한다. Pro의 수치/법칙 코드가 본체이며 Sol의 변경은 현재 API에 대한 통합과 검사 의존 분리다. 아래 native 물리 기준을 완화하거나 결과를 재분류하지 않았다.

현재 통합의 첫 국소 확인은 기존 Windows Python 3.12.14에서 전용4검사 파일 20개 통과다. 실제 pinned Python inp2rad child 변환과 postflight/카드 검증, 합성 TH/VTK의 typed readback을 실행했다.

후속 통합은 기존 `impact_retained`의 선택적 B 정의 pin과 `impact_recovery`의 기존 입력 복사/검증, A 부분 읽기 뒤의 B 전용 scope만 연결한다. 별도 reprocess 모듈·store·operation은 추가하지 않았다. `impact_reference_bindings`의 기존 receipt·원 대상·검토·명시 적용도 B 응답과 재료 적용집합에 재사용했다. Pro 작성 벌크 법칙·카드·이력 문법·물리 응답·계면 본체5파일은 그대로이며, Sol은 현행 owner 통합과 그 반례를 작성했다.

현재 Windows의 새 B 보존 검사6개는 정상 일반 응답 선택, 실패 TH prefix와 중간 프레임 gap, 잘못된 채널, B 정의 없음, B 정의 pin 변조, 일반 strict reader의 거절을 포함한다. 원 작업 상태와 새 읽기 상태·NATIVE/DERIVED를 구분하며, 저장 후 새 Python 프로세스에서 결과·작업 개수가 동일함을 확인했다. 새 binding 검사7개와 영향을 받는 기존 A 경계5개도 통과했다. 개발 중 source-edit 검사1건은 fixture가 inline 입력을 capture 없이 편집하려다 실패했고, 실제 보존 source bundle을 쓰도록 fixture를 고친 뒤 통과했다. 실패 기록은 삭제하지 않았다. `scripts/native_check.py`의 소유 Job은 모두 종료했고 최종 통과 실행은 exit0/job_empty다.

이 확인의 원출력은 합성 데이터다. Starter·Engine·converter binary·Qt·실제 native 손상 물리 캠페인은 이 백엔드 통합에서 NOT_RUN이다. pair 저장 의미, 부분 손상·압축·재접촉의 물리 잔여는 그대로다. 요구 연결은 기존 SPEC-IMPACT-001의 004/005(법칙·벌크/계면 결과), 007(동일 결과 보존)의 부분 구현이며 명세나 요구 상태를 새로 완료 처리하지 않는다.
