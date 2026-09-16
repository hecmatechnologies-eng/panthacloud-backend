# Static HTML — edge cases

## Multiple `</body>` candidates

A string or a comment can contain `</body>`. When the target has more than one candidate, refuse
rather than guess — the conservative patcher does the same.

## Single-page applications

A framework-free SPA still has one `index.html`; the widget script loads on the first paint, which
is correct for a script tag.

## Content-Security-Policy

A site with a restrictive CSP will block an unlisted `script-src`/`connect-src`. The widget must
degrade visibly rather than fail silently; the customer is told which origins to allow.
