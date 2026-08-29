#!/usr/bin/env python3
"""Launch the Trading Signal system (API + dashboard + scheduler)."""
import os
import sys

# Ensure project root is on path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import uvicorn


def main() -> None:
    # Koyeb / PaaS inject PORT; always bind 0.0.0.0 for public HTTP
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "0") == "1"
    print(f"Starting Signal Desk on {host}:{port}", flush=True)
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
        access_log=True,
    )


if __name__ == "__main__":
    main()
