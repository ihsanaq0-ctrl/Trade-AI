"""
Cleanup script: delete all stale bot rows from bot_settings.

Deletes rows where status = 'error' or status = 'stopped', leaving the
database completely empty for a fresh start (all 18 stale test rows).

Run:  cd backend && .venv/Scripts/activate && python cleanup_bots.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.database import supabase


def main():
    print("=" * 60)
    print("TradeAI Pro — bot_settings cleanup")
    print("=" * 60)

    # 1. Show what exists
    result = supabase.table("bot_settings").select("id, strategy, pair, status").execute()
    rows = result.data or []
    print(f"\nCurrent bot_settings rows: {len(rows)}")
    for b in rows:
        print(f"  {b['id'][:8]}  {b['strategy']:15s} {b['pair']:8s} {b['status']}")

    # 2. Delete stale rows (error + stopped) — NOT 'running' (there should be none)
    deleted = 0
    for status in ("error", "stopped"):
        r = supabase.table("bot_settings").delete().eq("status", status).execute()
        n = len(r.data or [])
        deleted += n
        print(f"\nDeleted status={status}: {n} rows")

    # 3. Verify empty
    remaining = supabase.table("bot_settings").select("id").execute()
    print(f"\nRemaining bot_settings rows: {len(remaining.data or [])}")
    if remaining.data:
        print("  WARNING: some rows remain (should be none):")
        for b in remaining.data:
            print(f"    {b['id'][:8]}")
    else:
        print("  CLEAN — database is empty for a fresh start.")

    print("\nDone.")


if __name__ == "__main__":
    main()
