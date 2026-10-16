"""Index the sample knowledge base (knowledge_base/en and knowledge_base/ne).

Usage (from the backend folder, with the database running and migrated):

    python scripts/ingest_kb.py                # uses KNOWLEDGE_BASE_PATH (default ../knowledge_base)
    python scripts/ingest_kb.py /path/to/docs  # any folder of .md / .pdf / .txt files

Safe to run repeatedly: already-indexed files are skipped.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db.base import async_session_factory  # noqa: E402
from app.rag.kb_loader import ingest_folder  # noqa: E402
from app.utils.logger import configure_logging  # noqa: E402


async def main() -> int:
    configure_logging()
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    else:
        configured = Path(get_settings().knowledge_base_path)
        root = configured if configured.exists() else Path(__file__).resolve().parents[2] / "knowledge_base"
    print(f"Indexing documents from {root} ... (the first run downloads the embedding model)")
    summary = await ingest_folder(async_session_factory, root)
    for key in ("ingested", "skipped", "failed"):
        print(f"{key:>9}: {len(summary[key])}  {', '.join(summary[key])}")
    if "error" in summary:
        print("error:", summary["error"])
        return 1
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
