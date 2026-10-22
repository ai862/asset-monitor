#!/usr/bin/env python3
"""Export one day of X archive to markdown (stdout or exports/)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
X_DAILY = ROOT / "data" / "x-daily"
EXPORTS = ROOT / "exports"

ORDER = ("SRC速报", "赏金技巧", "推荐流")


def main() -> None:
    ap = argparse.ArgumentParser(description="Export x-daily day to markdown")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument(
        "--out",
        type=Path,
        help="write to this path (default: exports/x-daily-DATE.md; use - for stdout)",
    )
    args = ap.parse_args()
    day = args.date
    path = X_DAILY / f"{day}.json"
    if not path.exists():
        raise SystemExit(f"missing {path}")

    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit("day file must be a JSON array")

    lines = [f"# 当日 X 监控归档 · {day}", "", f"共 {len(rows)} 条", ""]
    seen: set[int] = set()
    for st in ORDER:
        group = [r for r in rows if r.get("状态") == st]
        if not group:
            continue
        for r in group:
            seen.add(id(r))
        lines.append(f"## {st}（{len(group)}）")
        lines.append("")
        for r in group:
            title = r.get("产品") or "—"
            url = r.get("官网") or ""
            note = (r.get("备注") or "").strip()
            vendor = r.get("厂商") or ""
            if url:
                lines.append(f"- [{title}]({url})" + (f" — {vendor}" if vendor else ""))
            else:
                lines.append(f"- {title}" + (f" — {vendor}" if vendor else ""))
            if note:
                lines.append(f"  - {note}")
        lines.append("")

    other = [r for r in rows if id(r) not in seen]
    if other:
        lines.append(f"## 其他（{len(other)}）")
        lines.append("")
        for r in other:
            title = r.get("产品") or "—"
            url = r.get("官网") or ""
            st = r.get("状态") or ""
            vendor = r.get("厂商") or ""
            suffix = f" [{st}]" if st else ""
            if url:
                lines.append(f"- [{title}]({url}){suffix}" + (f" — {vendor}" if vendor else ""))
            else:
                lines.append(f"- {title}{suffix}" + (f" — {vendor}" if vendor else ""))
        lines.append("")

    text = "\n".join(lines).rstrip() + "\n"
    out = args.out
    if out is None:
        EXPORTS.mkdir(parents=True, exist_ok=True)
        out = EXPORTS / f"x-daily-{day}.md"
    if str(out) == "-":
        sys.stdout.write(text)
    else:
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out} ({len(rows)} items)", file=sys.stderr)


if __name__ == "__main__":
    main()
