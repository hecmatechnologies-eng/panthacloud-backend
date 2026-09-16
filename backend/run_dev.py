"""Start the API for local development, with an event loop psycopg can use.

psycopg's async driver cannot run on Windows' default ProactorEventLoop (CLAUDE.md §8). Uvicorn
0.52 forces Proactor on Windows unless it is running a subprocess, so the loop policy alone is not
enough; `app.core.loop:selector_loop_factory` is passed as a custom loop.

Run from anywhere:

    backend/.venv/Scripts/python.exe backend/run_dev.py

Reload is on, because a running server otherwise keeps whatever code it imported at startup and a
backend fix silently does not apply. Two things make it safe:

- the app is passed as an import string, which the reloader's spawned process re-imports;
- watching is limited to the backend's own sources, minus `data/` — cloned repositories land in
  `WORKSPACE_BASE_DIR` (``./data/workspaces``, relative to the working directory) and contain
  ``.py`` files, so watching them would restart the server mid-analysis.

This is a development convenience; production runs on Linux under a process manager.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent

# Make `app` importable regardless of the working directory. Runs in the reloader's child too,
# which re-imports this module as `__mp_main__` before resolving the app import string.
sys.path.insert(0, str(BACKEND_DIR))

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        loop="app.core.loop:selector_loop_factory",
        reload=True,
        reload_dirs=[str(BACKEND_DIR)],
        reload_excludes=[str(BACKEND_DIR / "data"), str(BACKEND_DIR / ".venv")],
        # The Studio proxies /api/v1/* to this process (next.config.mjs). Trusting the forwarded
        # host/scheme is what makes `request.url_for(...)` produce the *public* origin, which the
        # GitHub App callbacks depend on. Dev-only: production restricts the trusted proxies.
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
