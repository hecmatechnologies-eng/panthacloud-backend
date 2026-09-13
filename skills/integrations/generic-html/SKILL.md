---
name: generic-html
description: >-
  Integrates the Fussion assistant widget into a static HTML site by injecting the loader script
  before the closing body tag. Use when the widget target is an .html file and no supported
  framework is detected.
compatibility: Requires the target to be a static HTML file.
metadata:
  fussion.framework: generic-html
  fussion.version: "1.0.0"
  fussion.schema_version: "1"
  fussion.protected-paths: ".htaccess,robots.txt,sitemap.xml"
---

# Static HTML integration

## When this skill applies

- The widget target is an `.html` file.
- No supported JavaScript framework is detected.

Run `scripts/detect.py <repo-root>` for the deterministic match before using this skill.

## What to change

1. **Read the real target file** before editing it.
2. Insert the loader script immediately before the closing `</body>` tag.
3. If the file has no `</body>`, refuse rather than guess where to insert it.

## Never modify

- `.htaccess`, `robots.txt`, `sitemap.xml` — server configuration and crawler directives.
- Any path outside the declared change set.

## Templates

- `assets/widget-snippet.html.j2` — the loader script tag.

## Edge cases

See `references/EDGE-CASES.md` for multiple `</body>` candidates, single-page apps, and CSP.
