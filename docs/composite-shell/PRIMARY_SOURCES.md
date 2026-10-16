# E3 적층 셸 CAE 결정 근거

2026-10-16 · Astra 자문 · 구현 담당 Sol과 직접 협의. 이 문서는 소스와 물리 의미에 대한 자문이며 native 실행 또는 독립 통합검토의 PASS가 아니다. 제품 소스와 native 실행은 변경·수행하지 않았다.

검토 시작 제품 소스는 `d9e25c45c17d8439d4bca081cabbbd539a2a6518`, pinned upstream은 `3e48bf6138f495299f45b1af254bfb4aaff307b8`이다. 아래 native source는 공식 CalculiX 2.22의 `cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54`에 고정했다. 현재 E1의 균질 S8/27 IP 경로를 유지하고, E3는 **CalculiX 2.22 S8R COMPOSITE 전용 profile**로 연결한다. S6는 이번 구현 범위가 아니다. SPEC-PREFE-001 E3/FN-12의 서로 다른 재료 0/90 두 층, 두께·각도·순서·국부축 편집, 재정렬 Undo/저장, 실제 native 층별 응답 대응을 대상으로 했다.

## 1. 재료·방향·입력 계약

- 적층은 section의 층 목록이다. 각 층은 기존 재료 소유자의 안정된 참조와 실행 시 고정한 물성/원자료 참조를 보존한다. 새 재료 registry 또는 층마다 복제한 별도 물성 소유자를 만들 이유가 없다. 두께·각도·층 순서는 section의 속성이다.
- Native section 한 행은 `thickness, [unused], material_name, orientation_name`이다. material name은 native deck 식별자이며 제품 재료 참조와의 대응을 남긴다. 양수 유한 두께와 해석 가능한 재료가 없는 required 층은 실행을 차단한다. 잘못된 draft의 편집·저장은 유지한다. [Manual §7.117, p.589](https://www.dhondt.de/ccx_2.22.pdf)
- 직교이방성 3D 선형 탄성은 `*ELASTIC, TYPE=ENGINEERING CONSTANTS`의 첫 행 `E1,E2,E3,nu12,nu13,nu23,G12,G13`, 다음 행 `G23`이다. 온도 의존성을 지원하지 않는 첫 profile에서는 뒤 온도 필드를 임의로 생성하지 않는다. 평면응력 4상수만 받아 E3/G13/G23을 추측하면 이 native 물성 모델을 충족하지 못한다. [elastics.f](https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/elastics.f#L201-L219)
- `nu21=nu12*E2/E1`, `nu31=nu13*E3/E1`, `nu32=nu23*E3/E2`로 reciprocity를 지킨다. 독립 Poisson 비 6개를 서로 모순되게 저장하지 않는다. 등방성의 `nu<0.5` 상한을 이방성에 적용하지 않는다.
- 안정성은 양수·유한 `Ei,Gij`에 더해 전체 symmetric engineering compliance의 positive definiteness로 판정한다. normal 3×3 block의 대각은 `1/E1,1/E2,1/E3`, 상삼각 비대각은 `-nu12/E1,-nu13/E1,-nu23/E2`; shear 대각은 `1/G12,1/G13,1/G23`이다. Cholesky 등의 실제 SPD 검사를 쓰고 jitter/clamp로 통과시키지 않는다. 단위 영향을 줄이려면 normal block을 `D*S*D`, `D=diag(sqrt(Ei))`로 congruence 정규화할 수 있다. pair별 Poisson 조건만으로는 충분하지 않다: 모든 E가 같고 세 독립 nu가 0.6이면 pair product는 0.36이나 전체 normal block은 SPD가 아니다. 반대로 `E=(100,10,10), nu=(0.6,0.6,0.2)`는 안정한 예다. 이는 native 상호관계와 탄성 에너지 조건에서 도출한 검증 기준이다.

법선 `n`은 ordered S8 geometry에서 계산한 단위 법선이다. 사용자 reference axis를 shell-center 접평면에 투영·정규화해 `e1`을 얻고 `e2=n×e1`로 둔다. 각도 θ는 +n에 대한 오른손 방향이며 다음 orthonormal basis를 사용한다.

```text
a1 = cos(theta)*e1 + sin(theta)*e2
a2 = -sin(theta)*e1 + cos(theta)*e2
a3 = n
Q = [a1 a2 a3]       # columns expressed in GLOBAL coordinates
```

Native `*ORIENTATION, SYSTEM=RECTANGULAR`에 a1/a2의 global vector를 명시한다. 2.22는 orientation의 첫 축을 shell center 접평면에 다시 투영하며, normal에 너무 가까우면 세 번째 축으로 fallback한다. 따라서 제품에서 접선/normal 퇴화를 검출하고, 최종 사용한 element/ply별 Q를 결과 source와 보존한다. 곡면에서 IP마다 임의의 새 normal을 만들어 변환하면 native center basis와 다를 수 있다. [gen3dfrom2d.f 522–689](https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/gen3dfrom2d.f#L522-L689), [transformatrix.f](https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/transformatrix.f)

## 2. UI 위·아래와 native 층 순서

제품 표의 위층은 **+n 면**, 아래층은 **−n 면**으로 정의하고, 화면은 위→아래 순서로 둔다. Native 2.22의 입력 첫 층은 −n 쪽이다. 총두께 T, offset o, native 층 l의 두께 h_l에 대해 reference surface에서 측정한 층 경계는 다음과 같다.

```text
z_lower(l) = sum(h_k for k<l) - T*(0.5 + o)
z_upper(l) = z_lower(l) + h_l
```

따라서 **UI top→bottom 목록을 역순으로 native section에 쓴다.** `native_layer(1-based) ↔ stable ply_id ↔ UI position ↔ material reference ↔ h ↔ Q`를 저장한다. material 번호만으로 층을 추정하지 않는다. 같은 재료가 여러 층에 반복될 수 있다. [gen3dfrom2d.f 231–292](https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/gen3dfrom2d.f#L231-L292)

기존 reuse ANSWER의 p.74 “top에서 bottom” 문구는 그 **보 예제의 물리 방향**이다. 매뉴얼은 방향이 node order의 normal에 달렸다고 설명한다. 이 문구를 일반 규칙 “native 첫 층=+n”으로 읽으면 안 된다. source의 위 식과 실제 확장 좌표를 기준으로 한다. [Manual example pp.74–75](https://www.dhondt.de/ccx_2.22.pdf)

법선 반전은 물리적 적층 배치를 바꿀 수 있는 편집이다. 구현 담당자는 첫 기능에서 이 의미를 명시하기로 했다. 만약 향후 **물리 배치와 하중을 보존하는 반전**을 제공한다면 동일 reference axis 기준으로 법선뿐 아니라 층 순서, θ 부호, offset 부호, pressure 부호도 함께 대응시켜야 한다. 일부만 뒤집고 동일 모델이라고 주장하지 않는다.

## 3. DAT 원 적분점: S8R COMPOSITE만의 고정 대응

2.22 내부 expanded label은 `C3D20RLC`이며 층마다 2×2×2=8 IP를 가진다. native 출력 ordinal j는 1부터 `8*n_layers`까지다. [printoutint.f](https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/printoutint.f), [gauss.f](https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/gauss.f)

```text
native_layer = (j-1)//8 + 1
within_layer = (j-1)%8 + 1
inplane_ip = (j-1)%4 + 1
thickness_ip = ((j-1)%8)//4 + 1
g = 1/sqrt(3)
```

| within_layer | xi | eta | ply-local zeta | thickness position |
|---:|---:|---:|---:|---|
| 1 | −g | −g | −g | lower |
| 2 | +g | −g | −g | lower |
| 3 | −g | +g | −g | lower |
| 4 | +g | +g | −g | lower |
| 5 | −g | −g | +g | upper |
| 6 | +g | −g | +g | upper |
| 7 | −g | +g | +g | upper |
| 8 | +g | +g | +g | upper |

The source Gauss literal is `0.577350269189626`. Whole-shell natural coordinate is `zeta_shell=2*(sum(h_before)+(zeta_ply+1)*h_l/2)/T-1`; physical signed coordinate is `z=z_lower+(zeta_ply+1)*h_l/2` for the admitted constant-thickness profile. Values are interior points, not layer faces. A separately derived coordinate must be labelled derived, not native COORD output. Native source uses this same layer sum in `printoutint.f:274–295`.

Use `*EL PRINT, ..., GLOBAL=YES` and `S,E` for the first reader. S/E GLOBAL lines are exactly `element, j, xx, yy, zz, xy, xz, yz`, with native format `(i10,1x,i3,1p,6(1x,e13.6))`. There is no layer column. LOCAL output adds an orientation-name suffix; do not silently parse that as the same frame. [printoutint.f 383–487](https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/printoutint.f#L383-L487)

Store original shell ID, native j, original numeric tokens/values, result step/time, output frame, solver/profile/source identity and the above explicit mapping. Reject missing, duplicate, out-of-range or unexpected rows instead of filling them from another layer. This is separate from E1's 27-IP reader.

Native GLOBAL stress remains GLOBAL. Derived ply components require constructing symmetric S from native order and calculating `S_ply=Q^T*S_global*Q`. The same transformation applies to E as a symmetric strain tensor; native E shear components are tensor shear, so engineering shear display is a separate ×2 conversion. Preserve raw and derived fields separately. Native `printoutint` performs this matrix transformation for LOCAL S/E; merely renaming GLOBAL xx to ply-11 is incorrect.

**Source limitation:** this 2.22 `printoutint.f` declares `coords(3,27)`, yet composite loops can contain `8*n_layers` IP. Its coordinate calculation is entered for LOCAL/oriented output or COORD, so ≥4 layers can exceed that fixed dimension in that path. This is a source-level risk, not an observed binary failure here. GLOBAL S/E with no COORD takes `iorien=0` and skips that coordinate calculation (lines 71–84/coordinate branch and 383–457). Do not claim a universal three-layer solver limit; constrain the chosen output route and verify the actual binary/profile. Do not request COORD or LOCAL merely to check mapping in the first native bundle.

## 4. .12d and FRD mean different topology and sampling

- `.12d` records the original shell ID/eight nodes and **one whole-thickness 20-node expansion**, label `C3D20RLC`. `gen3delem.f:370–373` changes the first seven label characters to `C3D20RL`, retaining composite character C. Lines 399–403 write original nodes `kon(index+20+j)` and whole expansion `kon(index+j)`. It does not write a separate repeated shell element for each ply. [gen3delem.f](https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/gen3delem.f#L370-L403)
- FRD emits **one separate 20-node brick for each ply**, type 4/group 0/material `ielmat[layer,shell]`. `nemax` starts at `ne0`; each encountered ply increments it, so its ID is a new native output ID, not the original shell ID. Element iteration and native layer order determine the sequence. Preserve and validate that relation against admitted deck IDs, actual FRD material and physical layer coordinates; do not infer ply identity from material alone. [frd.c 315,391–429](https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/frd.c#L391-L429)
- Each ply uses native connectivity `kon[index+28+20*k+j]` for zero-based k. FRD writes native zero-based node positions `[0..11,16,17,18,19,12,13,14,15]`. Do not compare FRD ply connectivity directly to the whole-thickness `.12d` topology or inherit E1's hard-coded material=1 check.
- GLOBAL S/E FRD values are **nodal extrapolated values**, not raw IP data. For each ply, the 8 IP values are trilinearly extrapolated to the 8 corner nodes; the 12 midside values are corner averages. Contributions at a shared output node are averaged. Preserve FRD's sampling/frame meaning independently of DAT. [extrapolate.f 853–903,973–990,1030–1061](https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/extrapolate.f#L853-L1061)
- Composite FRD always expands layers regardless of OUTPUT=3D. **RF cannot be requested in composite FRD.** NODAL THICKNESS and error estimators are also unsupported. E1's FRD-RF requirement/equilibrium calculation must not be copied. Any reaction check needs its own supported native channel and evidence; absent reactions are not zero forces and cannot imply equilibrium. [Manual p.109](https://www.dhondt.de/ccx_2.22.pdf)

## 5. Minimal implementation acceptance bundle

The implementation owner should gather the following in one bounded native acceptance bundle; this adviser has not run it.

1. Actual 2.22 executable identity/hash, emitted S8R COMPOSITE deck and source document/revision; two distinct admitted materials, unequal layer thicknesses and 0/90 angles make accidental swapping observable. Record explicit +n/top convention and native reverse order.
2. Successful native output plus strict `.12d`/FRD mapping. Check each layer's material and physical signed coordinates against the written h/offset/order; confirm lower/upper sides and separate FRD output IDs. An exit code alone does not establish mapping.
3. DAT S/E GLOBAL has exactly `8*n_layers` valid original IP records per expected shell/output block. Compare the reader's raw six components with original text values without regenerated values. Check selected Q transforms numerically, including tensor invariants, and display raw GLOBAL and derived ply-local with their correct provenance.
4. Reorder the two plies, Undo, save/reopen, and ensure stable ply/material references, total thickness, native mapping and result/source revision association remain correct. If a second run after reorder is used to prove physical output association, it gets a new run/store and retains the first result.
5. Missing material, zero/nonfinite thickness and non-SPD constants block required export/run while preserving editable drafts. Unrelated E1 tests must keep S8 and 27-IP behavior. Preserve actual failures and predeclared comparison tolerances; this bundle establishes supported behavior, not general laminate strength/durability qualification.

For the pure admitted S8R profile, a small mesh is enough to establish these contracts. Broad native campaigns, new provider calls and a new review gate are unnecessary. A separate independent integrated review remains the lead's responsibility after the implementation bundle is meaningful.
