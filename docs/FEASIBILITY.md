# Fussion — Feasibility Assessment

An honest record of what is realistic, written at the point of handing implementation to
Claude Code. Read this alongside the architecture documents, which describe a
*destination*; this describes what is reachable and what should be cut to reach it.

**Date:** 2026-09-11 · **Basis:** full read of Design Phases 1–9 and the implemented
codebase.

---

## 1. The premise is sound — because it is narrow

Automatically modifying arbitrary customer repositories correctly is an unsolved problem.
Products with large funded teams struggle with the general form of it.

**Fussion is not attempting the general form.** It injects one widget into a known
framework's application shell. That is a constrained, well-specified transformation with
a small output surface, a human approval gate, and a branch/PR safety net. It is
achievable precisely *because* it is narrow.

The corresponding risk: every step toward generality multiplies difficulty
disproportionately. "Also fix their build config", "also add an API route", "also handle
any repository" are each a different product. **The narrowness is the asset. Protect it.**

---

## 2. The main risk is not architectural

The architecture is sound. The gap between what the design documents describe and what
can actually be built is the real risk.

Twenty-seven design phases plus a nineteen-phase roadmap describe a system sized for a
funded team of ten to twenty engineers: durable workflow engines, MCP infrastructure,
container sandboxes, multi-provider gateways, preview environments, OpenTelemetry,
billing, SSO, multi-region replication.

Actual capacity is one developer with AI tooling, alongside university and running a
company.

**The architecture does not need to shrink. The schedule implied by the documents does.**
Design for the destination; build a much smaller subset; let the boundaries make the
remainder additive rather than a rewrite. That is what the module layout and Protocol
seams are for.

---

## 3. Realistic timeline

Assuming focused part-time work with AI assistance, and that "focused" is doing real work
in that sentence:

| Step | Scope | Realistic |
|---|---|---|
| **A. Truth & safety** | layout-overwrite fix, workspace clone+read, one roadmap, rename, key removal, 05–08 decision | **3–5 days** |
| **B. Runtime plane** | public key, origins, tenant resolver, session, conversation, one model provider, streaming, real embeddings, pgvector, rate limits | **3–4 weeks** |
| **C. Analyst + harness + skills + evals** | WebsiteAnalyst, thin harness, tool gateway, 2 skill packages, 5-case eval corpus | **4–5 weeks** |
| **D. Coding agent** | write capability, generated-code scan, ChangeSet → PR, bounded repair | **2–3 weeks** *(without build validation)* · **6–8 weeks** *(with container sandbox)* |

**A demonstrable, sellable MVP: roughly three months.** Not nineteen phases.

The nineteen-phase roadmap is not wrong as a map of the territory. It is wrong as a plan.

---

## 4. The container sandbox is the most likely thing to stall this

It needs a Docker or gVisor host, CPU and memory limits, network egress control, audited
teardown between runs, and it costs money per execution. For a small team without
dedicated infrastructure, it is the single heaviest dependency in the plan — and it sits
on the critical path only because Phase 1 §7 listed "automated build/test validation" as
MVP scope.

**Recommendation: cut build validation from the MVP.**

Ship: static validation + generated-code security scan + the pull request, with an
explicit, honest statement in the PR body — *"Fussion did not execute your build. Please
verify locally before merging."*

You lose little credibility, because a human is reviewing and merging the PR anyway. You
remove the hardest infrastructure dependency from the path to a working product. The
`SandboxProvider` Protocol still gets defined, and `LocalWorkspaceProvider.run()` still
raises, so adding the container later is one implementation.

This is the single highest-value cut available.

---

## 5. Unit economics need deciding before the runtime plane ships

This is a product-viability question, not an engineering one, and it is currently
unanswered.

**Engineering side:** an integration run with a strong model over a real repository is
plausibly $1–4 in tokens. Project memory and prompt caching bring re-runs down sharply,
but the first run is the expensive one.

**Runtime side:** each visitor conversation costs fractions of a cent, but volume
multiplies it, and a single enthusiastic visitor can generate dozens of turns.

**The question to answer:** what will a target customer actually pay per month? If the
honest answer is in the range a small business in Fort Portal can sustain, then a flat
monthly subscription with uncapped conversations is not viable at current model prices.

Options worth modelling before committing:

- **One-time integration fee** (covering the expensive run) plus a small monthly runtime
  fee — matches where the cost actually sits
- **Hard conversation caps** per tier, enforced in the gateway from day one
- **A cheap model** for the runtime assistant; retrieval quality matters more than model
  strength for grounded Q&A
- **A different target market** — diaspora businesses, or international SMBs — where
  price tolerance is higher, using the same product

FR-073–FR-075 exist so this is measurable from the first run rather than discovered later.
Instrument it early and let real numbers decide.

---

## 6. What I would cut from my own documents

These were written as the right destination. They are not realistic for MVP:

| Requirement | Honest position |
|---|---|
| FR-116 full OpenTelemetry tracing | Structured logs + `AgentRun` records first. OTel when there is something to correlate across. |
| FR-122 security anomaly detection | Post-MVP. The write allowlist and generated-code scan carry the real risk. |
| Container sandbox / scope item #12 | Post-MVP. See §4. |
| GitHub App migration | PAT is acceptable considerably longer than implied — **once the hardcoded key is out of source**. App registration and installation flow is meaningful work for modest gain at this stage. |
| Eval corpus of 10–15 repositories | Start with **5**, one of which must be a refusal case. Grow it from real failures. |
| Ten-agent roster | Never. Two agents and a pipeline is the answer, not a waypoint. |
| Design-token extraction | Two tokens (primary colour, radius) beats none. Do not build style inference. |
| pgvector | Needed, but only once real embeddings land. Full-scan cosine is fine at a few hundred chunks. |

Everything in Part D of the requirements YAGNI register stands, and this table extends it.

---

## 7. The pattern that actually endangers this project

Phases 01 through 11 shipped in roughly two days. The tracker records each as
**COMPLETED · Deviations: None · Blockers: None.**

During those same two days:

- Phase 11 shipped a defect that replaces a customer's root layout with a stub, and the
  PR body it generates announces *"Sandbox validation: PASSED."*
- Phases 05–08 produced five migrations, five models, five endpoint modules and most of
  the test suite — for a subsystem the MVP path does not reference at all.
- The README stayed frozen at "Phase 01 Complete" while eleven phases landed.

**Velocity was never the problem. Verification was.**

Claude Code will move at least as fast. If the review gate is not real, in two weeks
there will be twenty phases, three more orphaned subsystems, and a tracker that says
everything is fine.

This is why `.claude/agents/fussion-reviewer.md` exists, why the definition of done is
conditional, and why the eval corpus is required from agent #1 rather than a later
hardening phase. **Use them. They are the only thing standing between this codebase and
the same outcome at higher speed.**

Two concrete rules worth holding to:

- **Nothing is marked COMPLETED in the tracker without the reviewer having passed it.**
- **"Deviations: None" is almost always false.** If a phase genuinely had none, say what
  was checked to establish that.

---

## 8. What success looks like

Not a completed roadmap. This:

> One real business. One real website. The widget live on it, answering questions grounded
> in that business's own documents. The integration performed by the platform rather than
> by hand.

Everything else — preview environments, multi-provider routing, billing tiers, ten agents,
WhatsApp, enterprise runtimes — is decoration until that exists. Once it exists, the
architecture here is built to carry the rest without a rewrite, which is the entire point
of having done this design work up front.

---

## 9. Honest confidence

| Claim | Confidence |
|---|---|
| The narrow premise is technically achievable | **High** |
| The architecture scales to the stated long-term scope | **High** |
| Three months to a demonstrable MVP, if build validation is cut | **Moderate** |
| Three months to a demonstrable MVP, with container sandbox in scope | **Low** |
| Unit economics work at a local-SME price point without a pricing change | **Low — needs modelling** |
| The codebase stays coherent if the review gate is skipped | **Very low** |
