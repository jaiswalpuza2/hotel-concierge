"""Start the API (use this on Windows).

psycopg's async mode (used for LangGraph's PostgreSQL checkpointer) cannot run on
Windows' default Proactor event loop. ``python run.py`` switches to the Selector loop
*before* uvicorn starts. On Linux/macOS/Docker it simply runs uvicorn.
"""
from __future__ import annotations

import asyncio
import sys

import uvicorn

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload="--reload" in sys.argv, loop="asyncio")
