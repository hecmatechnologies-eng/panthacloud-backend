# Step E — GitHub App connection, sliced

Step E, from `GAP-CLOSURE-PLAN.md` Phase 6. It is the requirements' **first post-MVP item**
(`MVP-REQUIREMENTS-V2.md` scope item #3) and is deliberately sequenced **after** the integration
pipeline is validated on a real repository through the current PAT flow: the connection UX and the
integration engine are independent, and a failure should point at one of them.

Each slice declares its rigour tier per `CLAUDE.md` §9.0. Propose no work outside the current slice.

Deliverable: a Railway-style connection — a **Connect GitHub** button, a GitHub App installation
screen, and a card list of the repositories the installation may reach, from which the user selects
one. The user never types an owner, a repository, a branch or a token.

| # | Slice | Tier | Done when |
|---|---|---|---|
| E1 | GitHub App config, `GitHubInstallation` model + migration, install URL, callback, installation-token minting, repository listing | 1 | An organization installs the app; the callback verifies a signed `state` and records the installation; a short-lived installation access token is minted and cached until expiry; `GET /github/repositories` lists what the installation can reach, tenant-scoped, paginated |
| E2 | Studio repository picker replacing the PAT form | 1 | "Connect GitHub" → install → a searchable repository card list → select → the integration is created from the selection with the repository's default branch; no PAT is entered |

## The architectural change

The platform stops storing a user credential. A GitHub App has no user token; the platform mints a
**short-lived installation access token**: sign a JWT with the app private key (`iss` = app id),
exchange it at `POST /app/installations/{installation_id}/access_tokens`, and cache it until shortly
before expiry. That resolver replaces `_decrypt_token` (analysis) and `_decrypt_github_token`
(control plane). The model never holds the token (`CLAUDE.md` §4.2); the service/tool layer resolves
it.

`GitHubProvider` itself does not change: it already takes a token string per call.

## Config and setup

New settings: `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY` (PEM, secret), `GITHUB_APP_SLUG` (for the
install URL), and optionally `GITHUB_APP_CLIENT_ID` / `GITHUB_APP_CLIENT_SECRET` to confirm the
acting user. Registering the app is a one-time manual step in GitHub settings: permissions
**Contents: read/write** and **Pull requests: read/write**, a callback URL, and a generated private
key. For local development the callback points at the local backend.

## Decisions

- **GitHub App, not an OAuth App.** Per-repository permissions and short-lived tokens, rather than a
  broad, long-lived user token. This matches the Railway experience and the requirement.
- **The PAT path is kept during E1 and removed in E2**, so the pipeline can still be exercised while
  the App flow is built.
- **Existing PAT integrations are not migrated automatically.** A re-connect through the App is the
  path; the stored PAT stays until then.

## Deliberately not built

- Webhook-driven repository sync — the list is fetched live until a real need appears.
- GitHub Enterprise hosts.
- A token cache shared across processes — a per-process cache is adequate until there is more than
  one worker.
