# Next.js App Router — edge cases

## `src/` layout

The layout lives at `src/app/layout.tsx`. Generated files go beside that tree, and imports between
them are **relative** — never a `@/` alias Fussion has not read.

## Custom provider stacks

The root layout may wrap `{children}` in providers. Insert `<FussionAssistant />` inside `<body>`
after the provider tree, not inside it, so a provider error cannot unmount the widget.

## Server components

The root layout is a server component. `FussionAssistant` is a `'use client'` component, which is
why the import must sit below any `'use client'` directive when one is present.

## Monorepos

If `package.json` and the `app/` tree are in different packages, the target is the package that
contains `app/layout.tsx`; the source root is derived from that path.
