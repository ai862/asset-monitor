#!/usr/bin/env python3
"""Export per-asset guidance JSON for GitHub Pages (Agent-fetchable URLs).

Reads data/ai-web.json, writes assets/ai-web/{去重键}.json for rows that have
启动指引 or 研判状态=已研判, sets 指引URL on those rows, and removes stale
files under assets/ai-web/ only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "ai-web.json"
OUT_DIR = ROOT / "assets" / "ai-web"
PAGES_BASE = "https://ai862.github.io/asset-monitor"
SAFE_KEY = re.compile(r"^[a-zA-Z0-9._-]+$")


def guidance_url(key: str) -> str:
    return f"{PAGES_BASE}/assets/ai-web/{key}.json"


def should_export(row: dict) -> bool:
    if not row.get("去重键"):
        return False
    if row.get("启动指引"):
        return True
    if row.get("研判状态") == "已研判":
        return True
    return False


def build_payload(row: dict) -> dict[str, Any]:
    key = str(row["去重键"])
    url = guidance_url(key)
    payload = dict(row)
    payload["source"] = "ai-web"
    payload["schemaVersion"] = row.get("schemaVersion") or 2
    payload["指引URL"] = url
    if row.get("agentHint"):
        payload["agentHint"] = row["agentHint"]
    return payload


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def export(update_data: bool = True) -> int:
    if not DATA_PATH.exists():
        print(f"missing {DATA_PATH}", file=sys.stderr)
        return 1

    rows: list[dict] = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    kept: set[str] = set()
    exported = 0
    skipped_unsafe = 0
    data_changed = False

    for row in rows:
        if not should_export(row):
            # Clear stale 指引URL on non-guided rows if present
            if row.get("指引URL"):
                row.pop("指引URL", None)
                data_changed = True
            continue
        key = str(row["去重键"]).strip()
        if not SAFE_KEY.match(key):
            print(f"skip unsafe key: {key!r}", file=sys.stderr)
            skipped_unsafe += 1
            continue
        url = guidance_url(key)
        if row.get("指引URL") != url:
            row["指引URL"] = url
            data_changed = True
        payload = build_payload(row)
        out = OUT_DIR / f"{key}.json"
        write_json(out, payload)
        kept.add(f"{key}.json")
        exported += 1

    # Remove stale files only under assets/ai-web/
    removed = 0
    for p in sorted(OUT_DIR.glob("*.json")):
        if p.name not in kept:
            p.unlink()
            removed += 1
            print(f"removed stale {p.relative_to(ROOT)}")

    if update_data and data_changed:
        write_json(DATA_PATH, rows)
        print(f"updated {DATA_PATH.relative_to(ROOT)} 指引URL fields")

    print(
        f"exported {exported} guidance asset(s) → {OUT_DIR.relative_to(ROOT)}/"
        + (f"; removed {removed} stale" if removed else "")
        + (f"; skipped unsafe {skipped_unsafe}" if skipped_unsafe else "")
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Export AI Web guidance JSON for Pages")
    ap.add_argument(
        "--no-update-data",
        action="store_true",
        help="Do not write 指引URL back into data/ai-web.json",
    )
    args = ap.parse_args()
    return export(update_data=not args.no_update_data)


if __name__ == "__main__":
    raise SystemExit(main())
