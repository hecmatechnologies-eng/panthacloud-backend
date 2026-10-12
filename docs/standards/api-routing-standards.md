# API and routing standards

The rules every new endpoint and route in this project is held to. Written to be checked
against, not admired — if an endpoint cannot satisfy section 3, the deviation goes in
section 6 with a reason, rather than being quietly justified in review.

Last reviewed: 2026-10-12. Audited against the live surface at that date: **89 operations**.

## 1. Sources

Verified against primary sources, not blog posts.

| What | Source |
|---|---|
| HTTP methods, status codes, semantics | [RFC 9110](https://www.rfc-editor.org/info/rfc9110/) |
| Problem details (errors) | [RFC 9457](https://www.rfc-editor.org/info/rfc9457/) — obsoletes RFC 7807 |
| Media types | [RFC 9110 §8.3](https://www.rfc-editor.org/rfc/rfc9110#name-content-type) |
| Idempotent methods | [RFC 9110 §9.2.2](https://www.rfc-editor.org/rfc/rfc9110#name-idempotent-methods) |
| Conditional requests / ETags | [RFC 9110 §13](https://www.rfc-editor.org/rfc/rfc9110#name-conditional-requests) |
| Caching | [RFC 9111](https://www.rfc-editor.org/info/rfc9111/) |
| OpenAPI description | OpenAPI 3.1 — served live at `/openapi.json` |
| URL path segments | [RFC 3986](https://www.rfc-editor.org/info/rfc3986/) |

## 2. REST or GraphQL

**REST, for everything.** This is a decision, not a default.

The reasons, in the order they actually mattered:

1. **The primary consumer is not us.** The assistant widget, the Studio's BFF and the
   generated integration all speak plain HTTP. A GraphQL endpoint would mean a second auth
   model, a second error model and a second client library for no gain.
2. **Every resource is owned and authorised by path.** `/organizations/{org_id}/...` carries
   the scope *in the URL*. A GraphQL client could ask for `/organizations/{id}/members` with
   a mismatched `projectId` argument, and the authorisation check would have to be
   argument-aware rather than path-aware. The path-scoped form makes the permission check
   structural instead of remembered.
3. **Caching is free.** ETags and `Cache-Control` work because GET is a URL. A single
   GraphQL POST with a different body is a different resource as far as any cache is
   concerned.
4. **89 operations with an average of one caller each.** The usual GraphQL argument is that
   it removes over-fetching when a client needs many resources at once. Here it would mostly
   be moving joins to the server that did not need them.

**GraphQL would be justified** if we later expose a public, third-party read API over a large
graph of related resources where clients need ad-hoc selection — for example a customer
portal querying sessions, guests, replies and follow-ups in one round trip. If that appears,
it gets its own `/api/graphql`, authenticated with the same tokens, and coexists with the
REST surface rather than replacing it. Adopting it before that exists would be paying the
complexity for a use case we do not have.

## 3. The rules

### 3.1 Resource naming

- **Plural nouns** for collections. `organizations`, not `organization`. `members`, not `member`.
- **Lowercase, hyphen-separated.** `website-integrations`, not `WebsiteIntegrations`.
- **No verbs in paths.** The method is the verb. `POST /integrations`, not `POST /create-integration`.
- **IDs in the path, not the body**, for anything addressable.
- **Nest only where the child cannot exist without the parent.**
  `/organizations/{org_id}/projects/{project_id}/documents/{document_id}` is correct nesting.
  Six segments is acceptable; past that, flatten and filter.

### 3.2 Methods

| Method | Meaning | Safe | Idempotent |
|---|---|---|---|
| GET | Read. Never has a side effect. | yes | yes |
| POST | Create, or an action that is not a state transition. | no | no |
| PUT | Full replace. Client supplies the whole resource. | no | **yes** |
| PATCH | Partial update. Only the fields supplied change. | no | **yes** |
| DELETE | Remove. Must succeed on an already-absent resource. | no | **yes** |

POST must not be used where PUT or PATCH expresses the intent. `PUT /assistant` replacing the
whole configuration is correct; a second `POST /assistant` doing the same thing is not.

Where a genuine non-CRUD action exists — cancel a run, confirm an origin — POST on a sub-path
naming that action is the accepted exception. These are listed in section 6.

### 3.3 Status codes

- `200` — read, or update that returned a body
- `201` — created. Must carry a `Location` header.
- `204` — succeeded, nothing to return. No body.
- `400` — malformed request the client could fix
- `401` — not authenticated · `403` — authenticated, not permitted
- `404` — not found, **or** present but invisible to this caller. Distinguishing the two leaks
  existence across tenants.
- `409` — conflicts with current state (duplicate email, already-connected repository)
- `422` — well-formed but semantically invalid, carrying per-field errors
- `422` vs `400`: use `400` for unparseable input, `422` for parseable input that fails
  validation. Do not use `400` for both.
- `429` — rate limited. Must carry `Retry-After`.
- `5xx` — our fault, never the caller's

### 3.4 Errors

Every error, on every endpoint, one shape:

```json
{
  "detail": "Request validation failed",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "A human-readable sentence.",
    "details": [{ "loc": ["body", "email"], "msg": "value is not a valid email address" }]
  }
}
```

`code` is a stable machine token; `message` is for humans and may be reworded freely;
`details[].loc` mirrors the field path used by Pydantic so the client can attach errors to
inputs.

**This is deliberately not RFC 9457 Problem Details.** That standard would have us emit
`application/problem+json` with `type`/`title`/`status`/`detail`. It is the better standard and
is worth adopting — but adopting it is a breaking change for `src/lib/api/envelope.ts` and
every existing client, so it is a decision to take deliberately rather than a tidying to slip
in. Recorded in section 6.

### 3.5 Pagination

Collections are paginated with `limit` and an opaque cursor, never `offset`. An offset shifts
under concurrent writes, which produces duplicates and gaps in exactly the live activity feeds
this product has.

```
GET /projects?limit=50&cursor=<opaque>
→ [ ... ]                                    # still a bare array
   Link: </projects?limit=50&cursor=eyJ...>; rel="next"
```

The next page is advertised in an RFC 8288 `Link` header, not wrapped in an envelope. The
`{ "items": [...], "next_cursor": ... }` shape is the better design and remains the right target
for a future API version, but it is not what shipped, for one reason: **these collections are
already live.** Every one returns a bare JSON array to the Studio's `resources.ts` and to
deployed integrations. Changing the body to an envelope would break eleven endpoints to satisfy
a document written a week later. `Link` is what GitHub does for the same reason.

Three properties make this non-breaking, and each is asserted in `test_pagination.py`:

- **`limit` has no default.** A default would silently truncate every existing caller. Omitting
  it returns everything, as before.
- **The body does not move.** A paginated response is the same array a client already parses.
- **Opaqueness is enforced by construction.** The client is given a `cursor` value, never a URL
  to follow, so the encoding stays an implementation detail we may change without a contract
  change. See `nextCursorFromLink` in the Studio, which extracts the parameter for this reason.

A `Link` header is sent only when another page genuinely exists. It is computed by fetching
`limit + 1` rows and treating the extra one as the signal, because on a large table a `COUNT`
costs more than the page it is counting.

Rejected input is a **400**, not a 422: the request was well-formed, the cursor simply was not
one we issued. The message tells the client to restart without a cursor rather than leaving it
to guess whether to retry.

### 3.6 Idempotency

- PUT, PATCH and DELETE **must** be idempotent. Retrying a DELETE after a timeout returns 204,
  not 404.
- Non-idempotent POSTs that a client may retry (payments, dispatches) accept an
  `Idempotency-Key` header and replay the stored response.

### 3.7 Versioning

Version lives in the path (`/api/v1`). Not in a header, not in a query parameter.

Adding a field to a response is not a breaking change and does not bump the version. Removing a
field, renaming one, narrowing a type or tightening validation all are.

### 3.8 Naming consistency

One convention, enforced by `ruff` and by the lint rules on the frontend. **snake_case** for
Python and for every JSON key crossing the wire. The frontend converts to camelCase at the type
boundary and nowhere else.

Mixing the two in one payload is a defect. `full_name` and `org_name` in the auth request are
correct; a payload containing both `firstName` and `first_name` is not.

## 4. Frontend routes

Same principle, applied to pages and to the Next.js BFF:

- **Paths mirror the folder tree.** `app/(auth)/auth/login/page.tsx` serves `/auth/login`. If a
  page's state needs encoding, that is a smell that it wants its own route.
- **No state in the query string for anything that is not shareable.** `?next=` is shareable and
  belongs there. A mode toggle is navigation, not a parameter.
- **Redirects preserve the query string.** `redirect("/auth/login")` inside a request for
  `/login?oauth_token=X` throws `X` away. Use `forwardAuthQuery` from `lib/auth/redirect.ts`.
  This is not theoretical — it shipped once and broke OAuth silently.
- **BFF routes under `/api/`** (`/api/auth/session`, `/api/backend/*`) are the frontend's own
  and are exempt from the `/api/v1` prefix rule, because they are not the backend API.

## 5. Checklist for a new endpoint

1. Is it a resource? Name it as a plural noun, lowercase and hyphenated.
2. Can the method express it? Reach for POST only when it genuinely is an action.
3. What is the status code on success, and does `201` carry `Location`?
4. Does the error body use the one shape in 3.4?
5. Is the collection paginated with a cursor?
6. Is it idempotent, or does it need an `Idempotency-Key`?
7. Is it version-safe — can I add it without breaking a deployed client?
8. Do the JSON keys use snake_case?
9. Is it in the OpenAPI schema? (`/openapi.json` is generated, so a missing schema is a bug.)

## 6. Known deviations

Recorded rather than fixed, each with a reason. New deviations get added here.

| # | Deviation | Why it stands |
|---|---|---|
| 1 | Errors are not RFC 9457 Problem Details | The custom envelope predates this standard being adopted deliberately. It is coherent and the frontend parses it in one place (`envelope.ts`). Switching is a breaking change and should be a decision, not a tidy-up. |
| 2 | Nine endpoints use a verb in the path | `knowledge/query`, `assistant/reset`, `snapshots/{id}/inspect`, `website-integrations/{analyze,validate}`, `origins/{id}/confirm`, `runs/{id}/cancel`, `auth/oauth/exchange`. Each is a genuine action rather than a state transition, which is what 3.2 permits. `query` and `search` are conventionally POST even on otherwise-REST APIs. |
| 3 | `/api/v1/public/widget.js` is a static asset served by the API | Deliberate. One file reaches every customer, so a fix is a deploy rather than a pull request per repository. See `app/api/v1/endpoints/public_widget.py`. |
| 4 | Response cache TTL is 300s | Chosen so a widget fix reaches customers within five minutes. Revisit when the widget is served from a CDN with proper invalidation. |
| 5 | 10 collections are not yet cursor-paginated | §3.5 is the rule. `/projects` is done end to end and is the worked example — copy it. The rest stay unpaginated because none has yet grown large enough for unbounded reads to hurt; they should be migrated as each is next touched, not in one sweep, so each is verified against its own consumers. |
| 6 | `POST /auth/register` returns 201 with no `Location` | It returns a token, not a representation of the user, and there is no addressable `/users/{id}`. RFC 9110 §15.3.2 permits omitting `Location` when the created resource is not separately addressable. Pointing it at `/auth/me` would name *the current user's* resource rather than the one created, which is worse than omitting it. |

Every other 201 now carries a `Location`, declared in the OpenAPI schema (`CREATED_RESPONSE`)
and set at runtime (`created()` in `endpoints/_location.py`). The two halves do different jobs:
the schema is what a client reads, the runtime call is what goes over the wire.

### 6.1 Duplicate root mounts — found and fixed

`app/main.py` mounted `github_app.router` bare **and** included it inside `api_v1_router`
under `/api/v1`, which published three org-scoped routes at two addresses each.

The bare mount is not pointless — GitHub redirects to whatever URL is configured in the GitHub
App's settings, so `/github/callback` and `/github/oauth/callback` must stay at fixed,
unversioned root paths. The bug was mounting the *whole* router to achieve that.

**The fix:** `github_app` now exposes a `callback_router` holding only those two routes.
`main.py` mounts that bare; `api_v1_router` includes it too, so `/api/v1/github/callback`
keeps working for clients that address the versioned API like everything else.

Two addresses for the callbacks is correct and externally mandated. Two addresses for
`/organizations/{org_id}/github/*` was not, and is gone.

```
GET /organizations/{org_id}/github/install-url    -> /api/v1/... only
GET /organizations/{org_id}/github/installations -> /api/v1/... only
GET /organizations/{org_id}/github/repositories  -> /api/v1/... only
GET /github/callback                              -> root AND /api/v1 (GitHub's config)
GET /health                                      -> root, deliberate
```

Operation count 89 -> 86. Suite: 862 passed, 2 pre-existing failures unrelated to this.

**Rule for new code:** mount only through `api_v1_router`. A bare `app.include_router(...)` is
how this happened. The only legitimate exceptions are registered in `main.py` with a comment
saying what external system fixes the path.