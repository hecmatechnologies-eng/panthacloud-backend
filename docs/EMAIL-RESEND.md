# Email via Resend

How the email channel is wired, what was verified from Resend's documentation, and what is
assumed. Kept next to the code because the code depends on all of it.

## What is different from WhatsApp

Email is the second channel and the first with no provider gate. WhatsApp needed a Meta app, a
business-verified account, Advanced Access and a phone number before a single guest could be
answered. Email needs one MX record.

**Email also has no waiting period.** WhatsApp will not let you message a guest more than 24 hours
after they wrote, and anything outside that needs an approved template. Email has no such rule.
That makes it the **only channel where the Follow-up list works today** — and it is why email was
chosen before WhatsApp's remaining work.

## Addressing, and why routing uses `To`

Each connected account gets one address. The part before the `@` identifies the tenant:

```
entebbe@ai-mwalimu.com   ->  the Entebbe property
reservations@ai-mwalimu.com  ->  whatever that hotel chose
```

Routing keys on **the address the mail was sent to**, never on the sender. This is the point at
which email stops being the hard case it looked like. A reply is sent to us again, so `To` is
stable across a whole conversation while `From` varies — and a guest may reply from an address
nobody has ever seen. Keying on `From` would drop those replies; keying on `To` treats a new sender
as a new guest for the same hotel, which is correct.

This is why `resolve_channel_tenant` can treat email exactly like WhatsApp. `ChannelRegistration`
and `ProjectChannel` are reused unchanged.

## Verified from Resend's documentation

Read on 2026-10-17, not recalled.

- **Receiving on a custom domain** needs an MX record. Verified by the record showing *verified*,
  not merely added — DNS takes time to spread.
- **A custom receiving domain is catch-all**: mail to *any* address on it is delivered. This is what
  makes per-hotel addresses possible. From the receiving introduction: *"you will receive emails
  through Resend for any address at that domain."*
- **Sending requires a domain you own.** *"You must add and verify at least one domain to send
  emails with Resend."* The account-managed `<id>.resend.app` is for receiving.
- **The `email.received` webhook carries no body.** *"Webhooks do not include the email body,
  headers, or attachments, only their metadata."* The body is a second call to the Receiving API.
  This is the one real cost of choosing Resend over Postmark, and it is what `fetch_email` does.
- **Webhooks are signed with Svix**, not with a bearer token. Headers `svix-id`,
  `svix-timestamp`, `svix-signature`; signed content is
  `{svix_id}.{svix_timestamp}.{raw_body}`; multiple space-separated signatures so a key can rotate.
- **Svix documentation itself warns** to verify against the *raw* body, because frameworks that
  parse and re-stringify break verification silently.
- Resend also offers threaded replies, forwarding, and stores received mail even when the webhook
  is down.

## Two credentials, different jobs

| Setting | Purpose | Where it comes from |
|---|---|---|
| `RESEND_API_KEY` | authenticates **our** calls to Resend | Resend → API Keys |
| `RESEND_WEBHOOK_SECRET` | authenticates **their** calls to us | Resend → Webhooks → the webhook → Signing Secret |
| `RESEND_RECEIVING_DOMAIN` | the domain receiving mail | ours, e.g. `ai-mwalimu.com` |

Using the API key to verify webhooks is the obvious mistake and a real one: the API key travels in
outbound request headers, the signing secret never leaves Resend's side. `RESEND_API_KEY` and
`RESEND_WEBHOOK_SECRET` are unset in production configuration, so an unconfigured deployment
**refuses** webhooks rather than accepting them.

Both live in `.env`, which is gitignored. They are never returned by any endpoint — the channel read
schema has `has_access_token` and no token field.

## The DNS footgun

Resend's documentation warns twice, and it fails *silently*:

> *You will not receive emails at Resend if the required MX record is not the lowest priority
> value for the domain.*

If `ai-mwalimu.com` already received mail through another provider, Resend would receive **nothing**
while the dashboard continued to look correct. It does not, so the domain is used directly. If that
ever changes, the documented remedy is a subdomain (`inbound.ai-mwalimu.com`), which leaves the
existing mail untouched.

## Quoted replies

The reason `app/channels/email/threading.py` exists. When a guest presses Reply, their client
copies the whole previous exchange underneath their new words. Left in, the model reads our own
output back as the guest speaking and answers the hotel's own sentence.

No standard exists for this — every client formats its own way — so it is layered, most-trusted
first: `On <date> <someone> wrote:` attribution, `-----Original Message-----`, Outlook's underscore
divider, then `>` lines. An unfamiliar format returns the body **unchanged**: a message with its
history attached is far better than no message.

## Deliverability: what actually decides it

VERIFIED 2026-10-17 against a live Gmail recipient.

Every reply was landing in the junk folder while SPF, DKIM and DMARC were all correct and every
send reported `delivered`. Adding DMARC did not change it. The reason is worth writing down,
because the instinct afterwards is to go back to DNS, and DNS is not where the answer was.

**Authentication is not reputation.** Those records stop a message being *rejected*. They say
nothing about whether a filter *wants* to deliver it. Checked on the day: `_dmarc` visible from
8.8.8.8, 1.1.1.1 and 9.9.9.9; no bounce and no complaint recorded for the recipient address; nine
consecutive sends with `last_event: delivered`. Gmail accepted the mail and then chose to junk it.

**The replies were the spam.** Each one read *"I do not have that information. Is there something
else I can help with?"* — automated, to a mailbox with no prior relationship with the domain, with
no useful content, seconds after the guest wrote. That profile is close to the definition of the
thing, and authentication does not offset it.

Two changes followed, both of them real design rather than tricks:

- `EMAIL_REPLY_DELAY_SECONDS` (default 90). A reply two seconds after the guest wrote is itself a
  signal, because no human types that fast. The wait happens **after** the webhook is acknowledged,
  in a background task — Resend's own timeout is far shorter than the delay, so blocking would turn
  every delivery into a retry and each retry into another turn. The honest cost: a process restart
  during the wait loses that send, though the transcript still holds the answer for staff to resend.
- **An answer worth receiving.** See below. This is the larger lever, because a substantive reply to
  the question just asked is about as far from spam as a message can get.

`resend suppressions list` shows four addresses, all bounced in June and September 2026 — months
before this domain existed, from other senders on the same account. They are unrelated to this mail
and are not suppressing anything here.

## Two ways an assistant with content still says nothing

Both VERIFIED 2026-10-17 on the live system, and both look identical from the outside: the assistant
says it has no information.

**1. The knowledge base was embedded with the wrong model.** `KnowledgeBase.embedding_model`
defaults to `deterministic-hash-384`, the development provider that hashes text into pseudo-random
vectors — stable for identical text, meaningless for meaning. "Deluxe King Room" and "what rooms
cost extra" land in unrelated places, so retrieval can never match a question to the passage that
answers it.

To be accurate about where the fault sits: the platform's own creation path is fine. `get_or_create`
in `app/api/deps.py` calls `build_default_embedding_provider()` and stores its `model_id` and
`dimension`, so a knowledge base created through the API or the widget gets `gemini-embedding-001`
at 768. The base that broke was built by a script that constructed `KnowledgeBase(...)` directly and
omitted the field — the kind of thing a seeding script, a data import or a future code path does,
and nothing warns about.

It still matters beyond a data-entry mistake, because `query_knowledge_base` embeds the question with
the base's **stored** model. The field therefore decides *both* sides of the comparison, and a
mismatch compares a Gemini question vector against hash passage vectors and returns confident
nonsense rather than an error. Worth a guard at construction time; listed below.

**2. One message was embedded as one question.** A guest asked three things in one email — room
types and rates, check-out time, and whether there is a pool. Retrieval returned five passages, all
of them room types and check-in policy, and no facilities passage at all. The vector for the whole
message lands wherever the message as a whole points, which is dominated by the longest topic. The
assistant then correctly reported no knowledge of the pool, because no pool text had reached it.

Fixed in `_query_variants` (`app/runtime/chat.py`): split the message at sentence and blank-line
boundaries, drop greetings and sign-offs, search once per surviving question, merge by
`(document_id, chunk_index)` keeping the strongest score. Punctuation is preserved deliberately —
the text handed to the embedder should be the text the guest wrote.

Two bounds, both in `app/core/config.py`:

| Setting | Default | Why |
| --- | --- | --- |
| `RETRIEVAL_MAX_QUERIES` | 4 | Caps embedding calls, which cost money and latency. |
| `RETRIEVAL_MAX_CHUNKS` | 12 | Caps the merge. **Larger than `RETRIEVAL_TOP_K` on purpose** — holding the total to the per-question limit would let the loudest question's passages evict the quieter questions', which is the original bug reintroduced one step later. |

A single ordinary question still produces exactly one search, so the common case is unchanged.

## Not built yet

- Attachments and HTML-only rendering (`_html_to_text` is a deliberate fallback, not a parser)
- Follow-up scheduling; the address is already captured, so this is unblocked for email
- Bounce and complaint handling — a bounce should mark the address unreachable
- A guard on creating a knowledge base with the default `embedding_model`, so the silent failure in
  the section above cannot recur