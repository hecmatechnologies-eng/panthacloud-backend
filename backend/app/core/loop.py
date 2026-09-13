"""Event-loop factory for local development on Windows.

psycopg's async driver cannot run on Windows' default `ProactorEventLoop`. Uvicorn 0.52 forces
`ProactorEventLoop` on Windows unless it is running a subprocess, so setting the event-loop policy
is not enough — a custom loop factory must be passed to uvicorn:

    loop="app.core.loop:selector_loop_factory"

See `backend/run_dev.py`. Production runs on Linux, where this is unnecessary.
"""

import asyncio


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()
