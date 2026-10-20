#!/usr/bin/env python3
"""Resolve git conflict markers in config.json by keeping max updatedAt."""
from __future__ import annotations

import json
import re
from pathlib import Path

MARK_OURS = "<" * 7
MARK_MID = "=" * 7
MARK_THEIRS = ">" * 7

def main() -> None:
    p = Path("config.json")
    t = p.read_text()
    if MARK_OURS not in t:
        json.loads(t)  # validate
        return
    pat = re.compile(
        re.escape(MARK_OURS) + r"[^\n]*\n(.*?)\n"
        + re.escape(MARK_MID) + r"\n(.*?)\n"
        + re.escape(MARK_THEIRS) + r"[^\n]*",
        re.S,
    )
    m = pat.search(t)
    if not m:
        raise SystemExit("unrecognized config.json conflict")
    def parse(s: str):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None
    a, b = parse(m.group(1)), parse(m.group(2))
    if not a or not b:
        # prefer second side (incoming during rebase = ours commit)
        p.write_text(m.group(2) if m.group(2).strip().startswith("{") else m.group(1))
        json.loads(p.read_text())
        return
    cfg = b if str(b.get("updatedAt", "")) >= str(a.get("updatedAt", "")) else a
    if not cfg.get("sources"):
        cfg["sources"] = a.get("sources") or b.get("sources")
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    print("resolved config.json updatedAt=", cfg.get("updatedAt"))

if __name__ == "__main__":
    main()
