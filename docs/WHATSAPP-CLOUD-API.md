# WhatsApp Cloud API — what this integration relies on

Working reference for `app/channels/whatsapp.py` and `app/channels/delivery.py`. Kept in-repo
because the code depends on it and a link that rots is worse than a file that is wrong visibly.

**Provenance is marked per item.** Meta's own documentation was unreachable from the build
environment (`developers.facebook.com` refused connections), so the integration was written against
an offline brief. Everything below is tagged, and the `NEEDS VERIFY` items are the ones to confirm
against live Meta documentation before this carries production traffic.

---

## Verified — from the supplied brief

| Fact | Value |
|---|---|
| Graph base URL | `https://graph.facebook.com/v21.0` |
| Authentication | `Authorization: Bearer {ACCESS_TOKEN}` |
| Send endpoint | `POST /{PHONE_NUMBER_ID}/messages` |
| Text body | `{"messaging_product":"whatsapp","to":"<digits>","type":"text","text":{"body":"…"}}` |
| Interactive buttons | `type: "interactive"` → `interactive.type: "button"` |
| Verification | `GET` with `hub.mode`, `hub.verify_token`, `hub.challenge`; echo the challenge as `text/plain` |
| Receive path | `entry[0].changes[0].value.messages[0]` |
| 24-hour window | free-form replies close 24 h after the guest's last inbound message; templates required after |
| Pricing | stated as 1000 free service replies per number per month, then utility rate |

## `NEEDS VERIFY` — implemented from knowledge, not from the brief

The brief **omitted all three**. Each is load-bearing.

### 1. `X-Hub-Signature-256` — the security boundary

HMAC-SHA256 of the **raw request bytes**, keyed on the **app secret**, compared with
`hmac.compare_digest`. Header form `sha256=<hex>`.

Implemented in `verify_signature()`. Three properties the code depends on:

- **Raw bytes, not the parsed body.** Re-serialising the JSON fails on any whitespace or key-order
  difference, and fails *silently* — every delivery stops matching with nothing in the logs.
- **The key is the app secret, not the tenant token.** A per-tenant key would make it impossible to
  authenticate a request *before* knowing which tenant sent it. This ordering constraint is why
  `WHATSAPP_APP_SECRET` is a platform setting.
- **Fail closed.** No configured secret → 401. `test_no_configured_app_secret_refuses_everything`.

The deprecated `X-Hub-Signature` (sha1) is **not** accepted as a fallback.

### 2. `value.metadata` — the only routing information in the payload

```json
"metadata": { "display_phone_number": "+256772123456", "phone_number_id": "1234567890" }
```

The brief documented only `messages[0].from`, which is the **guest's** number and identifies
nothing about which tenant was contacted. A change with no `phone_number_id` is skipped
(`test_a_change_without_metadata_is_skipped`).

### 3. `messages[].id` — the `wamid`, for idempotency

Providers retry webhooks. `Message.external_message_id` and its partial unique index
`(conversation_id, external_message_id)` already exist for this; without the `wamid` being populated
a retry appends a second turn to the transcript.

## Also needed, and absent from the brief

- `contacts[]` → `[{ "wa_id": "…", "profile": { "name": "Amina" } }]`. Matched on `wa_id`, not
  positionally — `contacts[0]` corresponds to `messages[0]` only in the simple case, and two guests
  in one batch is normal.
- `statuses[]` → delivery receipts. Parsed as "nothing to answer" and acknowledged with 200, so Meta
  does not retry forever.
- Group ids are `<digits>-<digits>@g.us`; a direct chat is `…@c.us`. A group id is **not** a person —
  keyed like one it creates a single shared "guest" conversation merging every member's messages.

## Known corrections to the brief

**`entry[0].changes[0]` is a bug, not a simplification.** WhatsApp sends multiple `entry` items,
each with multiple `changes`. Indexing `[0]` drops every message after the first, with no error and
no log — a hotel silently stops answering guests under load. `parse_webhook()` iterates;
`test_a_batch_keeps_every_message` is the regression test, mutation-verified to fail
(`['first','second']` vs `['first','second','third','fourth']`) when the shortcuts are reinstated.

## Version and pricing staleness

`v21.0` shipped around **May 2024**. The brief is dated Oct 2026, so the pinned version is over two
years of deprecations behind and is very likely retired. The brief's pricing model ("1000 free
service replies, then utility rate") also predates Meta's move to **per-message template pricing**.

Both are why `WHATSAPP_GRAPH_API_VERSION` is a **setting** rather than a literal, and why
`WHATSAPP_GRAPH_BASE_URL` exists — a future version may need a different host. Confirm the current
version before relying on v21.0 in production.

## Not implemented (deliberate)

- **Media.** Only `type: "text"` is answered. A caption is not a photo; answering "thanks, got it"
  to a passport image is worse than silence.
- **Message templates.** Required for anything outside the 24-hour window — which is the normal case
  for the Follow-up tab. `OutboundWindowClosed` is raised so the limit is explicit rather than a
  silent provider rejection.
- **Interactive buttons.** The brief documents the shape; the auto-menu is a product decision.
- **Status receipts.** `DeliveryStatus.ACCEPTED` means "the provider took it", deliberately not
  `delivered` — that would assert something nobody has verified.
- **Email.** Refused in `resolve_channel_tenant`, for reasons documented there.

## Onboarding

`Embedded Signup` / Tech Provider enrollment is **phase 2** and needs Meta approval that cannot be
accelerated: a new app is *Development* tier, where `whatsapp_business_messaging` reaches only the
app's allowlisted test numbers. Advanced Access requires business verification and app review.

The schema is ready for it — `channel_registrations.encrypted_access_token` stores a tenant's
system-user token via the existing `SecretStore`, so Embedded Signup fills in a column rather than
reshaping the schema. A new `channel_credentials` table is deliberately **not** created;
`accounts.encrypted_access_token` already answers this.