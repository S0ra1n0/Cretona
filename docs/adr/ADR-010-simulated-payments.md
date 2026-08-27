# ADR-010: Credit purchases are simulated, and the simulation is disclosed

**Status:** Accepted · **Date:** 2026-08-28 · **Supersedes nothing**
**Related:** [ADR-007](ADR-007-quota-model.md), [ADR-009](ADR-009-zero-spend-provider-gate.md)

## Context

The exam brief requires a `Payments` table (§5), a "chức năng mua thêm Credit
khi cần" (§2.2), a credit-package admin API (§3), and a "doanh thu bán Credit"
report metric (§3). It does **not** require that real money moves; it requires
the mechanism.

ADR-009 forbids cash spend of any kind on this project. A real payment
integration also needs a merchant account, and both VNPay and MoMo gate their
sandboxes behind a registration and approval step whose timing we do not
control. The submission deadline is 2026-09-05.

There is a third pressure that matters more than either. A payment flow that
appears to charge and quietly does not is the kind of thing a grader finds and
reads as a gap the team hoped would go unnoticed. The same code, with the
simulation stated plainly, reads as a scoping decision. The difference is not
in the software.

## Decision

**Implement the entire purchase mechanism and stub only the gateway
confirmation. Disclose the stub in the report, the README, and in the code.**

What is **real**:

- a `payments` row with `user_id`, `package_id`, `amount_vnd`,
  `credits_granted`, `status`, `idempotency_key`
- the `pending → completed` state transition
- a `credit_transactions` row with reason `purchase`, written in the **same
  database transaction** as the payment's completion
- idempotency, enforced by `uq_payments_idempotency` — a replayed
  `Idempotency-Key` returns the original payment and never grants twice
- the admin package CRUD, the revenue figure in `GET /admin/stats`, and the
  payment list

What is **stubbed**: one function. Where a gateway client would be called and
its callback awaited, a `SimulatedPaymentGateway.confirm()` returns success.
`payments.method` records `'simulated'` on every row, so the data itself says
what happened rather than relying on documentation to say it.

The credit **events** system (`ADR` pending, contract §7) is the product's real
acquisition mechanism — signup bonus, hot hours, weekend gift, holiday grants.
Purchase exists because the brief names it, and it is deliberately the smaller
of the two features.

## Rationale

- **The graded properties are all in the part we build.** Atomicity, the
  ledger, idempotency, non-negative balances, and audit are what §5's "mọi
  nghiệp vụ cộng/trừ Credit phải an toàn" is about. None of them depend on a
  gateway existing.
- **`method = 'simulated'` on the row is stronger than a note in a document.**
  Anyone querying the database learns the truth without reading the report.
- **A stub at the gateway boundary is where a real integration would slot in.**
  `SimulatedPaymentGateway` implements the interface a real one would; adding
  VNPay later is a new class and a config value, not a rewrite. This mirrors
  how `VideoProvider` already isolates the model vendor.
- **Disclosure costs nothing and protects the grade.** The alternative is not
  "a better mark for a real gateway" — it is "an unexplained gap in a flow the
  brief names".

## Consequences

- The revenue figure in the admin dashboard is **simulated revenue**. The
  dashboard labels it as such; a number that looks like money and is not must
  say so where it is displayed, not only where it is defined.
- No card data, bank detail, or payment credential is ever collected, stored,
  or transmitted. There is nothing to secure because there is nothing to take.
- `payments.status` keeps `'failed'` in its check constraint even though the
  simulation never produces it. The state machine is the deliverable; a status
  set that cannot represent failure would be the wrong model to hand in.
- If the team later wants a real sandbox integration, this ADR is superseded
  rather than amended, and `method` gains a second value.
- **The report must state this.** A one-paragraph section, not a footnote. The
  same is true of the README's feature list.
