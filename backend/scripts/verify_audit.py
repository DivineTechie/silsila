"""Verify the audit-log hash chain. For operators (e.g. a nightly job).

Uses the same environment as the API (SILSILA_DATABASE_URL for PostgreSQL, else SILSILA_DB).
Prints one JSON line and exits 0 if the chain is intact, 1 if it is broken.

Run: uv run python scripts/verify_audit.py
"""

from __future__ import annotations

import json
import sys

from silsila.api.store import Store


def main() -> int:
    store = Store()
    try:
        result = store.verify_chain()
    finally:
        store.close()
    print(json.dumps({"backend": store.backend, "database": store.path, **result}))
    return 0 if result["intact"] else 1


if __name__ == "__main__":
    sys.exit(main())
