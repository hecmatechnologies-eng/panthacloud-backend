# Feasible Solution: Fussion as a Multi-Tenant Business-Agent Platform, Instantiated for K Hotels

## 1. Framing

Fussion is not a chatbot product and not a K Hotels system. It is a **multi-tenant platform that deploys and operates goal-conditioned business agents**, one (or more) per tenant. K Hotels Entebbe is **Tenant #1** — the reference tenant that proves the model. Every design decision below must satisfy two masters: solve K Hotels' two problem statements now, and keep the platform generic enough that Tenant #2 (a clinic, a school, a tour operator) onboards without platform changes.

The tenant's needs evolve; the platform's contracts stay stable. That separation is the whole architecture.

## 2. Platform architecture (tenant-agnostic core)

**Tenant layer** (evolves per business, no redeploy): knowledge content, custom skills, channel bindings, approval policies, budgets/quotas, branding, staff roles.

**Platform core** (shared, versioned, evolves slowly): control plane (identity, orgs, RBAC, JWT, audit); knowledge plane (ingest, extract, chunk, embed, retrieve over pgvector); model gateway (provider-agnostic LLM plus embeddings, spend caps); tool gateway (auth scoping, budgets, rate limits, audit log); agent harness (bounded execution, budgets, memory tiers); channel framework (adapter interface for ingress and egress); skills runtime (versioned SKILL.md spec, detector, sandbox validation); evals (accuracy, hallucination, escalation precision); observability (per-tenant metrics, SSE activity, cost attribution).

**Tenant lifecycle** (all assisted-or-self-serve, no code deploy):

1. **Onboard** — create org, connect site/repo, load knowledge, bind channels, define goal plus policies.
2. **Operate** — agent runs, staff approves commitments, metrics accumulate.
3. **Evolve** — add skills, bind new channels, tune policies, raise autonomy tiers as evals justify it.

**Isolation guarantees** (non-negotiable for multi-tenancy): org-scoped rows everywhere, per-tenant vector namespaces, per-tenant encrypted secrets (channel tokens, API keys), per-tenant spend caps. A second tenant must never see, spend, or leak through the first.

## 3. K Hotels as Tenant #1: the concrete instantiation

**Tenant goal (declared, measurable):** convert enquiries into revenue — qualified bookings plus attached services (dining, events, transfers, spa).

**Knowledge:** rooms (48, categories, amenities), rates and seasonality, restaurant plus rooftop, conferencing, pool, spa and fitness, transfers, policies (check-in and check-out, cancellation, children), event packages. Versioned; stale-rate detection flags answers sourced from outdated chunks.

**Tenant skills:** room-catalog, event-package builder, transfer rules, Booking.com reservation awareness (see section 4), upsell rules (for example, lake-view plus spa on stays of two or more nights).

**Staff roles** (front-desk operators, not an IT team): front-desk (approval queue, escalations), manager (knowledge edits, metrics, policy thresholds), vendor/Hecma (platform ops, channel health). Memberships and RBAC already exist in the backend; this is a frontend wiring task.

## 4. Booking.com: the honest integration design

Fact that shapes everything: **Booking.com's Connectivity API is certified for channel managers and PMS partners, not individual properties.** K Hotels having an extranet account does not equal API access. So the integration is tiered — each tier feasible, in this order:

| Tier | What | Feasibility | Covers |
|---|---|---|---|
| A. Reservation-email ingestion (MVP) | Booking.com sends confirmation, modification and cancellation emails; the Gmail adapter ingests them and a parser extracts property, dates, guest, rate and status, producing reservation awareness in knowledge and tools | High — no partnership needed, read-only, uses the Gmail connector already planned | Know who is coming and when: pre-arrival upsell, transfer offers, stay-aware follow-up |
| B. Channel-manager passthrough | If K Hotels uses (or adopts) a channel manager, integrate to it; it already synchronises Booking.com availability, rates and reservations | High if a channel manager exists — this becomes the availability source of truth | Live availability plus rates, so the agent can quote confidently |
| C. Availability calendar (staff-assisted) | Simple availability feed (iCal or manual board) maintained by front desk until tier B lands | Medium — human-maintained, so quotes stay in the approval-gated tier | No hallucinated availability in the interim |
| D. Certified 2-way connectivity (later) | Via a connectivity partner for direct availability, rates, inventory plus reservation push | Low for MVP — partnership, certification, cost | Full book, modify and cancel through the agent |

**Rule the agent enforces:** availability and rate claims are commitment-tier actions. If the claim is sourced from Tier B (live feed), it may send with logging; if sourced from Tier A or C or pure knowledge, it drafts and a human approves. This single rule eliminates the highest-risk failure (wrong availability promise) regardless of integration maturity. As tiers graduate, policy thresholds move — that is tenant evolution working as designed.

## 5. Channels and the autonomy model

**Channels** (each a platform adapter, bound per tenant): web widget (existing runtime), WhatsApp Cloud API (primary guest channel for this market), Gmail (ingest the 1,000-plus backlog and ongoing mail; send follow-ups), SMS via aggregator (confirmations and time-critical nudges only — priced per message).

**Two-tier autonomy** (platform-wide contract, thresholds per tenant):

| Tier | Actions | Example | Gate |
|---|---|---|---|
| Inform (autonomous) | answer, qualify, capture, summarise, draft | FAQ answer, lead scoring, follow-up draft, stay summary | logged, budgeted, evaluated |
| Commit (gated) | promises, money, inventory, outbound-at-scale | rate quote, availability claim, booking action, discount, bulk send | human approval; auto-escalates on timeout with SLA timer |

Channel-policy compliance is enforced in the egress path, not trusted to the model: WhatsApp 24-hour window plus approved templates beyond it, email throttling plus unsubscribe handling, SMS cost cap per tenant per day.

## 6. Closing Problem 2 properly (the follow-up engine)

Problem 2's "segmentation, targeted messaging, structured follow-up" is a pipeline, and the solution names each stage's owner:

1. **Capture plus qualify** — agent (all channels) produces a structured lead (party size, dates, budget band, intent, source).
2. **Segment** — deterministic rules first (date flexibility, value band, event versus leisure), model-assisted later. Rules are auditable; that matters for the risk assessment.
3. **Follow-up** — timed nudges with template-checked drafts (24h, 72h, pre-arrival, post-stay review request), channel-aware, every send logged with its approving policy.
4. **Sync out** — qualified leads and outcomes exported (or a minimal built-in pipeline if the hotel has no CRM). The agent feeds the funnel; it does not grade its own homework — conversion metrics are computed from outcomes, not agent self-reports.

## 7. Data, privacy, and governance (scored explicitly by the challenge)

- Guest PII (names, contacts, stay dates, passport or ID at check-in) is tenant-confidential: encrypted at rest, org-scoped, excluded from embeddings unless explicitly approved, with a retention policy per the pilot MoU.
- NDA before data access; pilot MoU scoping the MVP's data; IP clauses covering tenant skills versus platform core (tenant owns its content and custom skills; platform owns the core).
- Every commitment-tier action carries an audit trail (who approved, what source, which policy version) — this is the artifact the two-week risk assessment will actually inspect.
- Cost attribution per tenant (model plus channel spend) so the commercial pathway (pilot to paid contract) has numbers, not estimates.

## 8. Proving it: evals and metrics tied to the problem statements

- **Evals (before autonomy expands):** rate-quote accuracy versus source feed, availability-claim grounding (every claim traceable to Tier A, B or C, or flagged), escalation precision and recall, template-compliance rate, PII-leak probes.
- **Live metrics (the pitch-day numbers):** median first-response time (target at or under 12 minutes across bound channels), enquiry-to-qualified rate, qualified-to-booking rate, upsell attach rate, approval-queue latency, cost per converted booking.
- No metric moves on agent self-reporting; all derive from channel events and booking outcomes.

## 9. MVP plan (fits the one-month window)

- **Week 1:** Tenant scaffold (org, roles, knowledge load with real hotel content); Gmail ingestion plus reservation-email parser (Tier A); approval queue; PMS and channel-manager discovery (determines Tier B viability).
- **Week 2:** Web widget plus WhatsApp live; quote-draft to approval to send loop; metrics dashboard; availability policy wired to whichever tier exists.
- **Week 3:** Follow-up engine (segments, nudges, templates); evals running on quote accuracy and grounding; SMS confirmations if justified.
- **Week 4:** Hardening plus risk-assessment pack (PII handling, WhatsApp compliance, failure drills: feed down, knowledge stale, model provider outage) plus pitch-day demo script (enquiry to instant answer to qualification to approval to confirmed interest, with metrics on screen).

Explicitly deferred: SMS marketing, booking-write (goes through staff confirmation), Tier D connectivity, second tenant (designed for, not built).

## 10. Risks, stated plainly

- No live availability feed means all quotes stay human-gated (slower, but honest).
- WhatsApp policy or Gmail scope friction means web plus email carry the MVP.
- Knowledge staleness is countered by versioning plus source-citation on every rate answer, with the manager owning updates.
- Model or provider outage triggers deterministic fallbacks (capture plus queue) so no enquiry is ever dropped silently.
- Scope creep into "platform rebuild" is blocked: tenant evolution uses existing extension points (skills, policies, adapters); platform core is frozen during the pilot except for fixes.

## Bottom line

Fussion's multi-tenant shape — stable platform core, fast-evolving tenant layer — is exactly what lets K Hotels be Tenant #1 without becoming a one-off consulting build: everything K Hotels needs (knowledge, skills, channels, policies, staff UI) is tenant configuration on shared machinery, and Tenant #2 reuses all of it. The Booking.com account becomes useful on day one through reservation-email awareness, graduates to live availability via a channel manager, and only later justifies certified connectivity. Autonomy is bounded by the inform-or-commit split from the start, so the agent can pursue revenue aggressively where it is safe (speed, qualification, follow-up) and never where it is not (promises, prices, inventory) until the feeds and evals earn it.
