/* SPDX-License-Identifier: BSD-3-Clause */
#pragma once
#include <cstdint>
#include <limits>
namespace cae {
/* Qt-independent permission lifecycle. An allow is a single-use lease, not a
   future-close bypass. The widget/owner is not retired by an allow decision. */
class CloseTransaction {
public:
  enum class Phase { Idle, Deciding, AwaitingReview, Reviewed };
  bool begin() noexcept {
    if (Active != Phase::Idle || Sequence == std::numeric_limits<std::uint64_t>::max())
      return false;
    ++Sequence;
    Active = Phase::Deciding;
    return true;
  }
  bool decide(int decision) noexcept {
    if (Active != Phase::Deciding) return false;
    if (decision != 1) { abort(); return false; }
    Active = Phase::AwaitingReview;
    return true;
  }
  bool review(bool accepted, int decision) noexcept {
    if (Active != Phase::AwaitingReview) return false;
    if (!accepted || decision != 1) { abort(); return false; }
    Active = Phase::Reviewed;
    return true;
  }
  void abort() noexcept { Active = Phase::Idle; }
  bool active() const noexcept { return Active != Phase::Idle; }
  bool reviewed() const noexcept { return Active == Phase::Reviewed; }
  Phase phase() const noexcept { return Active; }
  std::uint64_t attempt() const noexcept { return Sequence; }
private:
  Phase Active = Phase::Idle;
  std::uint64_t Sequence = 0;
};
}
