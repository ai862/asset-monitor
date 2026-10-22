#!/usr/bin/env python3
"""Merge daily intel items into data/intel.json + data/x-daily/; prune intel to 14 days.

x-daily is a loose full daily archive of all X-sourced intel (SRC速报 / 赏金技巧 /
推荐流 / any future 状态). Unknown statuses are kept in day files (soft-warn only).
Extra item keys are always preserved on merge.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
INTEL = ROOT / "data" / "intel.json"
X_DAILY = ROOT / "data" / "x-daily"
CONFIG = ROOT / "config.json"

# Soft-known statuses for warn-only checks. Day archive accepts any 状态.
STATUS_OK = {"SRC速报", "赏金技巧", "推荐流"}
# All intel is X-sourced; archive every item that has a calendar date.
X_STATUSES = STATUS_OK  # kept for import compatibility; day archive no longer filters by this
TZ = ZoneInfo("Asia/Shanghai")
INTEL_KEEP_DAYS = 14


def shanghai_iso() -> str:
    now = datetime.now(TZ)
    s = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    return s[:-2] + ":" + s[-2:]


def shanghai_today() -> date:
    return datetime.now(TZ).date()


def item_date(item: dict) -> str | None:
    """Calendar date from 批次 or 首次写入 (YYYY-MM-DD)."""
    for key in ("批次", "首次写入"):
        raw = str(item.get(key) or "").strip()
        if not raw:
            continue
        day = raw[:10]
        if len(day) == 10 and day[4] == "-" and day[7] == "-":
            try:
                date.fromisoformat(day)
                return day
            except ValueError:
                continue
    return None


def load_items(path: Path | None) -> list[dict]:
    if path is None:
        raw = sys.stdin.read()
    else:
        raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise SystemExit("input must be a JSON array of items")
    return data


def normalize(item: dict) -> dict:
    """Require 去重键; preserve every extra key (loose schema)."""
    key = str(item.get("去重键") or "").strip()
    if not key:
        raise SystemExit(f"item missing 去重键: {item.get('产品')!r}")
    out = dict(item)  # shallow copy — keep unknown fields
    out["去重键"] = key
    st = out.get("状态") or "SRC速报"
    if st not in STATUS_OK:
        print(f"warn: unexpected 状态 {st!r} for {key}", file=sys.stderr)
    out.setdefault("文档", "")
    out.setdefault("实用价值", "")
    out.setdefault("备注", "")
    return out


def upsert_rows(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], int, int]:
    """Merge by 去重键; incoming wins on overlapping keys; preserve extras from either side."""
    by_key: dict[str, dict] = {}
    for row in existing:
        k = str(row.get("去重键") or "").strip()
        if k:
            by_key[k] = dict(row)

    added = updated = 0
    for item in incoming:
        k = item["去重键"]
        if k in by_key:
            old = by_key[k]
            merged = {**old, **item}
            if not item.get("首次写入") and old.get("首次写入"):
                merged["首次写入"] = old["首次写入"]
            by_key[k] = merged
            updated += 1
        else:
            by_key[k] = dict(item)
            added += 1

    rows = list(by_key.values())
    rows.sort(
        key=lambda r: (str(r.get("首次写入") or ""), str(r.get("去重键") or "")),
        reverse=True,
    )
    return rows, added, updated


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_day_file(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def day_counts(rows: list[dict]) -> dict:
    n_src = sum(1 for r in rows if r.get("状态") == "SRC速报")
    n_skill = sum(1 for r in rows if r.get("状态") == "赏金技巧")
    n_feed = sum(1 for r in rows if r.get("状态") == "推荐流")
    n_other = len(rows) - n_src - n_skill - n_feed
    return {
        "SRC速报": n_src,
        "赏金技巧": n_skill,
        "推荐流": n_feed,
        "other": n_other,
        "total": len(rows),
    }


def rebuild_x_daily_index() -> list[dict]:
    """Scan all YYYY-MM-DD.json under x-daily and write index.json (newest first)."""
    X_DAILY.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    for path in sorted(X_DAILY.glob("????-??-??.json"), reverse=True):
        day = path.stem
        try:
            date.fromisoformat(day)
        except ValueError:
            continue
        rows = load_day_file(path)
        counts = day_counts(rows)
        entries.append(
            {
                "date": day,
                **counts,
                "file": path.name,
            }
        )
    write_json(X_DAILY / "index.json", entries)
    return entries


def upsert_x_daily(incoming: list[dict]) -> list[str]:
    """Upsert all dated intel items into per-day files. Returns touched dates."""
    by_day: dict[str, list[dict]] = {}
    for item in incoming:
        day = item_date(item)
        if not day:
            print(
                f"warn: item missing date (批次/首次写入): {item.get('去重键')}",
                file=sys.stderr,
            )
            continue
        st = item.get("状态")
        if st not in STATUS_OK:
            print(
                f"warn: archiving unexpected 状态 {st!r} for {item.get('去重键')}",
                file=sys.stderr,
            )
        by_day.setdefault(day, []).append(item)

    touched: list[str] = []
    for day, items in sorted(by_day.items()):
        path = X_DAILY / f"{day}.json"
        existing = load_day_file(path)
        rows, _a, _u = upsert_rows(existing, items)
        # Keep all statuses (loose daily archive); do not filter
        rows.sort(
            key=lambda r: (str(r.get("首次写入") or ""), str(r.get("去重键") or "")),
            reverse=True,
        )
        write_json(path, rows)
        touched.append(day)

    if touched or not (X_DAILY / "index.json").exists():
        rebuild_x_daily_index()
    return touched


def prune_intel(rows: list[dict], keep_days: int = INTEL_KEEP_DAYS) -> tuple[list[dict], int]:
    cutoff = shanghai_today() - timedelta(days=keep_days - 1)
    kept: list[dict] = []
    pruned = 0
    for r in rows:
        day = item_date(r)
        if not day:
            kept.append(r)
            continue
        try:
            d = date.fromisoformat(day)
        except ValueError:
            kept.append(r)
            continue
        if d >= cutoff:
            kept.append(r)
        else:
            pruned += 1
    return kept, pruned


def ensure_intel_source(cfg: dict) -> None:
    ids = {s["id"] for s in cfg.get("sources", [])}
    if "intel" not in ids:
        cfg.setdefault("sources", []).append(
            {
                "id": "intel",
                "name": "每日情报",
                "data": "data/intel.json",
                "notion": "",
                "accent": "#af52de",
            }
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Upsert items into data/intel.json and data/x-daily/")
    ap.add_argument("--file", "-f", type=Path, help="JSON array file (default: stdin)")
    ap.add_argument(
        "--keep-days",
        type=int,
        default=INTEL_KEEP_DAYS,
        help=f"keep intel.json items within N Asia/Shanghai days (default {INTEL_KEEP_DAYS})",
    )
    args = ap.parse_args()

    incoming = [normalize(x) for x in load_items(args.file)]
    if INTEL.exists():
        existing = json.loads(INTEL.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            existing = []
    else:
        existing = []

    rows, added, updated = upsert_rows(existing, incoming)
    touched = upsert_x_daily(incoming)
    rows, pruned = prune_intel(rows, keep_days=args.keep_days)
    write_json(INTEL, rows)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["updatedAt"] = shanghai_iso()
    ensure_intel_source(cfg)
    write_json(CONFIG, cfg)

    print(
        f"intel.json total={len(rows)} added={added} updated={updated} "
        f"pruned={pruned} incoming={len(incoming)} "
        f"x-daily dates={touched or '[]'} updatedAt={cfg['updatedAt']}"
    )


if __name__ == "__main__":
    main()
