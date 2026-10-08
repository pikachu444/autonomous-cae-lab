# OpenCourant 20261006 explicit-runtime qualification

The original OpenRadioss `latest-20260728` release endpoint returned HTTP 404
in the exact `acbe38c` CI explicit job. The original 82,648,350-byte archive,
SHA-256 `598ed7b2905a7bacc8d1781470c250ac79d7558c39ba962768edf3644644fe33`,
and all historical acceptance records remain preserved. That failed CI job did
not reach a numerical solver test. A fresh local extraction of the preserved
archive repeated the expected `PARTIAL` freeflight/ideal-wall verdict; it did
not restore the remote installer.

The newly qualified replacement is the community successor
[OpenCourant `latest-20261006`](https://github.com/OpenCourant/OpenCourant/releases/tag/latest-20261006),
source commit `33e685176cccf0c539a3ce07aa2096985a284e2a`, Linux x86-64 asset
[`OpenCourant_linux64.zip`](https://github.com/OpenCourant/OpenCourant/releases/download/latest-20261006/OpenCourant_linux64.zip),
83,937,337 bytes, SHA-256
`9d67531de156dd9beba05fbfe710dcdc2bcecbdf3dc3a12642cf85dcece80081`.
The newly downloaded local ZIP matched that release digest. It was extracted
without replacing the old runtime at
`/home/pikachu444/.local/share/autonomous-cae-lab/opencourant-latest-20261006/OpenCourant`.
The package declares AGPL-3.0-or-later and bundles third-party license notices;
company redistribution, license and security approval remain open.

The original 20260728 runtime pin is still admitted by the adapter for its
retained experiments. The new pin checks the ZIP, Starter
`122c09311ecf6155fb998cd980d4c478c01734fdd1d4287e6f7a817b62e39db8`,
Engine `9e2a9c0a674765c20d997f2205431477ad871839268f26b46b700bca3d2b20df`,
reader/APR/H3D libraries and configuration fingerprint
`eb3da6fefb68d156460f06d1132afe5275492b8c32df54b0b3cebd9723c0a90f`.
The three critical reader/APR/H3D library hashes are byte-identical to the
20260728 package. Starter reports source commit `33e6851` and reader build
`20260710_d899773e`. The existing `CAELAB_OPENRADIOSS_ROOT` setting names the
qualified root for either pin; provenance stores the actual release and hashes.

The new source's `engine/source/output/th/hist1.F` declares 23 global TH40
channels, and `hist2.F` adds an energy-balance value at channel 23. Channels
1–22 retain their positions. The parser admits 23 only for the exact new archive
SHA and source commit, verifies the additional value against the source-defined
energy equation within TH40 ASCII rounding, and continues to require 22 for the
original pin. Unknown identity, wrong count and corrupted balance are rejected.
No engineering acceptance limit, response definition or failed historical
metric was relaxed.

Clean source commit `7f50fa6e1373e34e6e5cda6c6249731e8688fdb7` passed
133 focused OpenRadioss parser/transport tests. Both new native campaigns
record `core_dirty=false` and that exact commit:

| Fresh WSL run store | Report SHA-256 | Verdict |
| --- | --- | --- |
| `runs/opencourant-flight-clean-7f50fa6-20261008-01` | `5c8f51e67f7289b87cba3fcb713612c0aed5e78d7c7cfdb46de09d65f5f7f4c7` | `PARTIAL`, five flight cases pass, both ideal-wall cases remain `REJECTED`, invalid input rejected; `NOT_RELEASED` |
| `runs/opencourant-compliant-clean-7f50fa6-20261008-01` | `ff6343e434f387361c80ef94b0b04d264eab0a3f8de993b64fe92c4f53785248` | `PASS`, three finite-force contact/rebound cases pass and two invalid inputs are rejected; `NOT_RELEASED` |

The first compliant case retains actual impulse `8.956353901 N s`, restitution
`1.000004642` and mechanical-energy error `0.000232984 J` against the original
independent equations and unchanged limits. The ideal-wall postimpact failure
remains visible, and physical contact, strength, material, failure and durability
validations remain `UNKNOWN`. Core still owns the common evidence, experiment
and release gates; OpenScience remains an interpretation/control plane. A new CI
run of the exact commit containing the installer change is the next remote gate;
the local results above are not a claim of CI success.
