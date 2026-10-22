#!/usr/bin/env python3
"""One-shot / maintenance: split intel.json X items into data/x-daily/ + prune intel."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Reuse helpers from upsert_intel
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from upsert_intel import (  # noqa: E402
    CONFIG,
    INTEL,
    INTEL_KEEP_DAYS,
    X_DAILY,
    X_STATUSES,
    item_date,
    prune_intel,
    rebuild_x_daily_index,
    shanghai_iso,
    upsert_rows,
    write_json,
)


def main() -> None:
    ap = argparse.ArgumentParser(description="Rebuild data/x-daily from intel.json")
    ap.add_argument(
        "--prune-intel",
        action="store_true",
        default=True,
        help="prune intel.json to last N days (default: on)",
    )
    ap.add_argument(
        "--no-prune-intel",
        action="store_false",
        dest="prune_intel",
        help="keep full intel.json",
    )
    ap.add_argument("--keep-days", type=int, default=INTEL_KEEP_DAYS)
    args = ap.parse_args()

    if not INTEL.exists():
        raise SystemExit(f"missing {INTEL}")

    rows = json.loads(INTEL.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit("intel.json must be a JSON array")

    by_day: dict[str, list[dict]] = {}
    skipped = 0
    for item in rows:
        if item.get("状态") not in X_STATUSES:
            continue
        day = item_date(item)
        if not day:
            skipped += 1
            print(f"warn: skip X item without date: {item.get('去重键')}", file=sys.stderr)
            continue
        by_day.setdefault(day, []).append(item)

    X_DAILY.mkdir(parents=True, exist_ok=True)
    # Clear old day files that we will rewrite; keep unrelated? rewrite all from intel.
    for old in X_DAILY.glob("????-??-??.json"):
        old.unlink()

    for day, items in sorted(by_day.items()):
        merged, _, _ = upsert_rows([], items)
        merged = [r for r in merged if r.get("状态") in X_STATUSES]
        merged.sort(
            key=lambda r: (str(r.get("首次写入") or ""), str(r.get("去重键") or "")),
            reverse=True,
        )
        write_json(X_DAILY / f"{day}.json", merged)

    index = rebuild_x_daily_index()

    pruned = 0
    if args.prune_intel:
        kept, pruned = prune_intel(rows, keep_days=args.keep_days)
        write_json(INTEL, kept)
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        cfg["updatedAt"] = shanghai_iso()
        write_json(CONFIG, cfg)
        intel_total = len(kept)
    else:
        intel_total = len(rows)

    print(
        f"rebuild_x_daily days={len(index)} x_items={sum(e['total'] for e in index)} "
        f"skipped_no_date={skipped} intel_total={intel_total} pruned={pruned}"
    )
    for e in index:
        print(
            f"  {e['date']} 赏金技巧={e['赏金技巧']} 推荐流={e['推荐流']} total={e['total']}"
        )


if __name__ == "__main__":
    main()
