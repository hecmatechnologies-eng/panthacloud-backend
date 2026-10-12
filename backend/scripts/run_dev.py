"""Run the API on Windows against the real Postgres.

psycopg's async driver cannot run on asyncio's default Windows event loop: it needs a selector
loop, and `uvicorn` installs Proactor by default. The result is a backend that starts cleanly,
answers `/health` with 503, and logs

    Psycopg cannot use the 'ProactorEventLoop' to run in async mode

which reads like a database problem and is not one. Postgres is up and reachable; only the
event loop is wrong.

Rather than work around it per session with an env var nobody remembers, this is the documented
entry point for Windows:

    python scripts/run_dev.py

On Linux and macOS, `uvicorn app.main:app` is correct and this script is unnecessary - the
default loop there already works. The selector loop is installed only on Windows, so this file
does not change behaviour anywhere else.
"""

import asyncio
import selectors
import sys
from pathlib import Path

import uvicorn

# Make `app` importable when run as `python scripts/run_dev.py` from the backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    host = "127.0.0.1"
    port = 8000

    if sys.platform == "win32":
        # `loop="none"` stops uvicorn installing Proactor, so the loop we create below is the
        # one that serves. Setting the policy alone is not enough: uvicorn overrides it.
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        asyncio.set_event_loop(loop)
        config = uvicorn.Config(
            "app.main:app", host=host, port=port, log_level="info", loop="none", reload=False
        )
        server = uvicorn.Server(config)
        try:
            loop.run_until_complete(server.serve(sockets=None))
        finally:
            loop.close()
        return

    uvicorn.run("app.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
