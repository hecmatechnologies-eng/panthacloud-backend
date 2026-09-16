---
name: nextjs-app-router
description: >-
  Integrates the Fussion assistant widget into a Next.js App Router project by patching the root
  layout. Use when package.json depends on next >= 13 and an app/ directory with layout.tsx is
  present.
compatibility: Requires a Node project with a resolvable package manager lockfile.
metadata:
  fussion.framework: nextjs
  fussion.router: app
  fussion.version: "1.0.0"
  fussion.schema_version: "1"
  fussion.protected-paths: "next.config.js,next.config.mjs,next.config.ts,middleware.ts"
---

# Next.js App Router integration

## When this skill applies

- `package.json` declares `next` at version 13 or newer.
- An App Router tree exists: `app/layout.tsx` or `src/app/layout.tsx`.
- The Pages Router is not the primary shell.

Run `scripts/detect.py <repo-root>` for the deterministic match before using this skill.

## What to change

1. **Read the real root layout** (`app/layout.tsx` or `src/app/layout.tsx`) before editing it.
2. Add the generated `FussionAssistant` client component beside the app tree.
3. Render `<FussionAssistant />` inside `<body>`, after `{children}`.
4. Add the generated `config.ts` beside the component.
5. Insert the import block **below** any `'use client'` directive.

## Never modify

- `next.config.*` and `middleware.ts` — request configuration and authentication enforcement.
- Any path outside the declared change set.

## Templates

- `assets/FussionAssistant.tsx.j2` — the client component.
- `assets/config.ts.j2` — the widget configuration.

## Edge cases

See `references/EDGE-CASES.md` for the `src/` layout, custom provider stacks, and monorepos.
