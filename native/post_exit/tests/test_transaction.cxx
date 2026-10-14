/* SPDX-License-Identifier: BSD-3-Clause */
#include "CloseTransaction.h"
#include "cae_post_exit_abi.h"
#include <cstddef>
#include <iostream>
#include <stdexcept>
#define CHECK(condition) do { if (!(condition)) throw std::runtime_error(#condition); } while (false)
int main() {
  using T = cae::CloseTransaction;
  T transaction;
  CHECK(!transaction.active());
  CHECK(!transaction.review(true, CAE_ALLOW));
  for (int decision : std::initializer_list<int>{CAE_BLOCK, CAE_UNKNOWN, 2, 127, -9}) {
    CHECK(transaction.begin());
    CHECK(!transaction.begin()); // Reentrancy must not steal a pending request.
    CHECK(!transaction.decide(decision));
    CHECK(!transaction.active());
  }
  for (int cycle = 0; cycle < 3; ++cycle) {
    CHECK(transaction.begin());
    const auto id = transaction.attempt();
    CHECK(transaction.decide(CAE_ALLOW));
    CHECK(!transaction.review(false, CAE_ALLOW)); // Downstream stock veto.
    CHECK(!transaction.active());
    CHECK(transaction.begin());
    CHECK(transaction.attempt() > id);
    CHECK(transaction.decide(CAE_ALLOW));
    CHECK(!transaction.review(true, CAE_UNKNOWN)); // State lost before hide.
    CHECK(transaction.begin());
    CHECK(transaction.decide(CAE_ALLOW));
    CHECK(transaction.review(true, CAE_ALLOW));
    CHECK(transaction.reviewed());
    CHECK(!transaction.begin());
    transaction.abort(); // Actual close/detach or downstream ignore invalidates lease.
    CHECK(!transaction.active());
    CHECK(!transaction.decide(CAE_ALLOW));
  }
  CHECK(sizeof(cae_exit_status) == 96);
  CHECK(offsetof(cae_exit_status, pid) == 8);
  CHECK(offsetof(cae_exit_status, client) == 40);
  CHECK(offsetof(cae_exit_status, ready) == 48);
  CHECK(offsetof(cae_exit_status, last_decision) == 88);
  std::cout << "PASS: close transaction retry/reentrancy/veto and C ABI layout\n";
}
