# K Hotels Entebbe — AI Guest Response & Conversion Solution: Proposal

## 1. Executive summary

K Hotels Entebbe loses revenue twice: first when a guest enquiry waits 4–6 hours for a reply, and again when 1,000-plus enquiries convert poorly for lack of qualification and follow-up. This proposal offers one system to close both gaps: a **goal-conditioned AI guest agent** that answers enquiries in seconds on the hotel's own channels, qualifies every lead into structured form, drafts quotes and follow-ups for one-tap staff approval, and learns the hotel's rooms, rates, packages, and Booking.com reservations as its working knowledge. Target outcome: **median first response at or under 12 minutes** and a **measurable lift in enquiry-to-booking conversion** within the pilot.

## 2. Understanding of K Hotels

Boutique four-star hotel in Entebbe, Uganda, near Lake Victoria, serving leisure travellers, business visitors, and event guests. The commercial asset base the agent must know cold:

- 48 rooms across categories, with amenities and seasonal rates
- Restaurant and rooftop dining, conference and event facilities
- Swimming pool, fitness centre, spa services
- Airport transfer services for international and domestic arrivals

Demand already exists — the problem is not visibility but **handling**: speed of first response and quality of follow-through. The hotel also holds a **Booking.com extranet account**, which becomes the reservation-awareness feed (see section 5).

## 3. The two problems, restated as targets

| # | Problem | Baseline | Target |
|---|---|---|---|
| 1 | Slow guest response time; bookings lost to faster competitors | 4–6 hour average reply | Reliable response **within 12 minutes**, accurate and consistent across channels |
| 2 | High enquiry volume, low conversion, generic communication | 1,000-plus enquiries and emails, low booking and upsell conversion | **Segmented enquiries, targeted messaging, structured follow-up**, higher conversion per enquiry |

## 4. Proposed solution

A single guest agent with one declared goal — **convert enquiries into revenue (bookings plus attached services: dining, events, transfers, spa)** — operating on three principles:

1. **Answer instantly, commit carefully.** The agent acts freely on information tasks (answer, qualify, capture, summarise, draft) and always routes commitment tasks (rate quotes, availability claims, booking actions, discounts, bulk sends) through a **one-tap staff approval queue**. No guest ever receives a promise the hotel did not approve or a live feed did not confirm.
2. **Meet guests where they already ask.** Web chat on the hotel site, **WhatsApp** (the dominant business-messaging channel in this market), **Gmail** (where the 1,000-plus backlog already sits), and SMS for confirmations and time-critical nudges only.
3. **Every enquiry becomes a structured lead.** Party size, dates, budget band, intent, source — captured once, then segmented, followed up, and synced out. Nothing stays as an unstructured email thread.

## 5. Booking.com integration (tiered, honest)

The hotel's Booking.com extranet account does not itself grant API access (connectivity APIs are certified for channel managers and PMS partners, not individual properties). The integration therefore proceeds in tiers, each useful on its own:

| Tier | What | Pilot relevance |
|---|---|---|
| A. Reservation-email awareness (MVP) | Booking.com confirmation, modification, and cancellation emails are ingested and parsed into reservation awareness: who is coming, when, at what rate | Pre-arrival upsell, transfer offers, stay-aware follow-up from day one |
| B. Channel-manager passthrough | If the hotel uses or adopts a channel manager, connect through it as the live availability-and-rates source of truth | Agent quotes confidently instead of drafting for approval |
| C. Staff-maintained availability (interim) | Simple calendar maintained by front desk until Tier B lands | No hallucinated availability meanwhile; quotes stay approval-gated |
| D. Certified two-way connectivity (post-pilot) | Via a connectivity partner for direct availability, rates, inventory, and reservation actions | Full book, modify, and cancel through the agent |

## 6. What the staff see (front desk and manager, not IT)

- **Approval queue:** quote and availability drafts arrive with their source attached; one tap sends, edits, or rejects. Escalations and SLA timers included.
- **Knowledge editor:** rooms, rates, packages, policies, event menus — updated by the manager, versioned, with stale-rate flagging so the agent never quotes last season's price.
- **Metrics dashboard:** median first-response time, enquiry-to-qualified rate, qualified-to-booking rate, upsell attach rate, approval latency, cost per converted booking.

## 7. Follow-up engine (answers Problem 2 directly)

1. Capture and qualify every enquiry into a structured lead.
2. Segment by auditable rules first (date flexibility, value band, event versus leisure), model-assisted later.
3. Send timed, template-checked nudges (24 hours, 72 hours, pre-arrival, post-stay review request), channel-aware and policy-compliant (WhatsApp windows and templates, email throttling, SMS cost caps).
4. Sync qualified leads and outcomes out to the hotel's tools, and compute conversion from outcomes — never from the agent's self-report.

## 8. Data, privacy, and IP (aligned to the challenge terms)

- NDA signed before any hotel data or workflow access; pilot MoU defines scope, duration, and responsibilities.
- Guest PII (names, contacts, stay dates, ID documents) is encrypted at rest, strictly scoped to the hotel, excluded from embeddings unless explicitly approved, with retention per the MoU.
- IP clauses distinguish hotel-owned content and configuration from platform-owned core; the hotel's data is never used beyond the agreed scope.
- Every approved commitment carries an audit trail (approver, source, policy version) — the artifact the risk-assessment phase inspects.

## 9. Delivery plan (aligned to the challenge phases)

- **Bootcamp:** knowledge modelling with hotel content, channel inventory, PMS and channel-manager discovery (decides Tier B viability), approval-queue prototype.
- **One-month build and mentorship:** week 1 — tenant setup, Gmail ingestion plus reservation-email parser, approval queue; week 2 — web chat plus WhatsApp live, quote-draft to approval to send loop, metrics dashboard; week 3 — follow-up engine plus accuracy evals and SMS confirmations if justified; week 4 — hardening and failure drills (feed down, stale knowledge, provider outage).
- **Risk assessment:** PII handling evidence, WhatsApp and email compliance, eval results on quote accuracy and availability grounding, audit-trail demonstration.
- **Pitch day (live at K Hotels):** end-to-end demonstration — real enquiry, instant answer, qualification, one-tap approval, confirmed interest — with the pilot metrics on screen.

Explicitly deferred from the pilot: SMS marketing, booking-write without staff confirmation, Tier D connectivity.

## 10. Success criteria and commercial pathway

Pilot success is declared against the problem statements' own numbers: median first response at or under 12 minutes across bound channels, and a measured uplift in enquiry-to-qualified and qualified-to-booking rates versus the pre-pilot baseline, with approval latency and cost per converted booking reported alongside. On meeting these, the defined commercial pathway converts the pilot into a paid contract: per-property subscription covering platform operation, channels, and support, with the hotel owning its content and configuration and the vendor operating the platform as a managed service.

## 11. Risks and mitigations

- No live availability feed: all quotes stay human-gated — slower, but honest.
- WhatsApp policy or Gmail scope friction: web plus email carry the pilot.
- Stale rates or packages: versioning plus source citation on every rate answer; manager owns updates.
- Provider outage: deterministic fallbacks (capture plus queue) so no enquiry is ever dropped silently.
- Over-automation of commitments: the inform-or-commit split is contractual, not advisory — the agent cannot send a promise the policy did not allow.
