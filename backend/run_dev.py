"""Start the API for local development, with an event loop psycopg can use.

psycopg's async driver cannot run on Windows' default ProactorEventLoop (CLAUDE.md §8). Uvicorn
0.52 forces Proactor on Windows unless it is running a subprocess, so the loop policy alone is not
enough; `app.core.loop:selector_loop_factory` is passed as a custom loop.

Run from anywhere:

    backend/.venv/Scripts/python.exe backend/run_dev.py

This is a development convenience; production runs on Linux under a process manager.
"""

import sys
from pathlib import Path

# Make `app` importable regardless of the working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn

from app.main import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        loop="app.core.loop:selector_loop_factory",
    )
