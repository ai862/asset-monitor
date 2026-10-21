#!/usr/bin/env python3
"""Merge daily intel items into data/intel.json by 去重键; bump config updatedAt."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
INTEL = ROOT / "data" / "intel.json"
CONFIG = ROOT / "config.json"

STATUS_OK = {"SRC速报", "赏金技巧", "推荐流"}


def shanghai_iso() -> str:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    s = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    return s[:-2] + ":" + s[-2:]


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
    key = str(item.get("去重键") or "").strip()
    if not key:
        raise SystemExit(f"item missing 去重键: {item.get('产品')!r}")
    out = dict(item)
    out["去重键"] = key
    st = out.get("状态") or "SRC速报"
    if st not in STATUS_OK:
        print(f"warn: unexpected 状态 {st!r} for {key}", file=sys.stderr)
    out.setdefault("文档", "")
    out.setdefault("实用价值", "")
    out.setdefault("备注", "")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Upsert items into data/intel.json")
    ap.add_argument("--file", "-f", type=Path, help="JSON array file (default: stdin)")
    args = ap.parse_args()

    incoming = [normalize(x) for x in load_items(args.file)]
    if INTEL.exists():
        existing = json.loads(INTEL.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            existing = []
    else:
        existing = []

    by_key: dict[str, dict] = {}
    for row in existing:
        k = str(row.get("去重键") or "").strip()
        if k:
            by_key[k] = row

    added = updated = 0
    for item in incoming:
        k = item["去重键"]
        if k in by_key:
            # newer overwrites; keep 首次写入 if incoming omits it
            old = by_key[k]
            merged = {**old, **item}
            if not item.get("首次写入") and old.get("首次写入"):
                merged["首次写入"] = old["首次写入"]
            by_key[k] = merged
            updated += 1
        else:
            by_key[k] = item
            added += 1

    rows = list(by_key.values())
    rows.sort(
        key=lambda r: (str(r.get("首次写入") or ""), str(r.get("去重键") or "")),
        reverse=True,
    )
    INTEL.parent.mkdir(parents=True, exist_ok=True)
    INTEL.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["updatedAt"] = shanghai_iso()
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
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"intel.json total={len(rows)} added={added} updated={updated} "
        f"incoming={len(incoming)} updatedAt={cfg['updatedAt']}"
    )


if __name__ == "__main__":
    main()
