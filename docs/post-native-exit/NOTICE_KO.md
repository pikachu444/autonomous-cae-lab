# 라이선스와 재배포 notice

신규 작성 파일의 license는 native/post_exit/LICENSE의 BSD-3-Clause다. 이 묶음은
ParaView/Qt/Python binary/SDK/font를 포함하지 않는다. 기존 프로젝트 파일 두 개의
integration patch는 해당 원래 프로젝트 license와 함께 유지한다.

ParaView v6.2.0의 확인한 plugin/Qt source는 BSD-3-Clause SPDX를 표시한다. 실제
ParaView/VTK를 함께 배포하면 전체 배포판의 각 third-party license/notice를 보존한다.
프로젝트가 가져오는 VTK submodule을 임의 최신 VTK로 대체하지 않는다.

Qt6.9.0의 open-source Core/Gui/Widgets 등 실제 사용 모듈에 맞는 LGPL/GPL license를
선택하고 적용 조건을 검토한다. dynamic DLL 사용만으로 모든 LGPL 의무가 자동으로
충족되는 것은 아니다. binary 재배포 시 해당 license/notice, 대응 source의 제공 방법,
교체/수정한 Qt와의 재링크 가능성, 필요한 installation information 및 허용되는 reverse
engineering/debugging을 방해하지 않는 조건을 확인한다. 단순 최신 Qt 홈페이지 링크를
대응 소스 제공의 전부로 삼지 않는다. QtTools의 build 도구 license와 runtime에 실제로
링크/배포하는 module license를 구분한다. 불필요한 GPL-only runtime 모듈은 추가하지 않는다.

공식 MS Build Tools의 무료 OSS 빌드 범위와 Windows SDK 조건을 적용한다. compiler/SDK를
제품 소스 ZIP에 재배포하지 않는다. MSVC runtime은 실제 toolchain의 재배포 조건에 따른다.
Python runtime을 배포하면 Python license/third-party notices도 해당 버전대로 포함한다.

원본 다운로드/빌드/배포 담당이 실제 소스 archive, tag/commit, module 목록, license
파일과 변경분을 보관해야 한다. 본 문서는 실제 바이너리 배포의 법률 적합성 인증서가 아니다.
