#!/usr/bin/env python3
"""Enrich thin 备注 / optional 直连下载 for ICS assets via OpenCode (IMKAI DeepSeek).

Does NOT invent URLs. Only merges longer notes into 备注; if 直连下载 empty and
OpenCode returns trusted http(s)/docker candidates, write them.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
ICS_PATH = ROOT / "data" / "ics.json"
CONFIG_PATH = ROOT / "config.json"
OPENCODE_BIN = Path(
    os.environ.get("OPENCODE_BIN")
    or (
        "/home/box/.opencode/bin/opencode"
        if Path("/home/box/.opencode/bin/opencode").is_file()
        else "opencode"
    )
)
MODEL = os.environ.get("OPENCODE_MODEL", "imkai/DeepSeek-V4-Flash")
KEY_FILE = Path("/home/box/.config/secrets/imkai_api_key")
TZ_SH = timezone(timedelta(hours=8), name="Asia/Shanghai")

BINARY_EXT = re.compile(
    r"\.(exe|msi|dmg|pkg|iso|zip|rar|7z|tar\.gz|tgz|tar\.bz2|tar\.xz|tar|gz|"
    r"deb|rpm|apk|bin|run|img|AppImage)(\?|$)",
    re.I,
)
TRUSTED_HOST_HINTS = (
    "github.com",
    "githubusercontent.com",
    "apache.org",
    "sourceforge.net",
    "gitlab.com",
    "docker.io",
    "gitee.com",
    "siemens.com",
    "rockwellautomation.com",
    "schneider-electric.com",
    "abb.com",
    "honeywell.com",
    "emerson.com",
    "advantech.com",
    "thingsboard.io",
    "inductiveautomation.com",
)


def now_shanghai() -> str:
    return datetime.now(TZ_SH).replace(microsecond=0).isoformat()


def log(msg: str) -> None:
    print(msg, flush=True)


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def ensure_api_key(env: dict[str, str]) -> dict[str, str]:
    if env.get("IMKAI_API_KEY"):
        return env
    if KEY_FILE.is_file():
        env = env.copy()
        env["IMKAI_API_KEY"] = KEY_FILE.read_text(encoding="utf-8").strip()
    return env


def is_dup(row: dict) -> bool:
    key = str(row.get("去重键") or "")
    note = str(row.get("备注") or "")
    return key.endswith("-DUP") or "【重复】" in note


def has_direct(row: dict) -> bool:
    v = row.get("直连下载")
    if v is None or v == "" or v == []:
        return False
    if isinstance(v, list):
        return any(str(x).strip() for x in v)
    return bool(str(v).strip())


def select_targets(
    rows: list[dict], keys: list[str] | None, limit: int, min_note: int
) -> list[dict]:
    by_key = {r.get("去重键"): r for r in rows if r.get("去重键")}
    if keys:
        out: list[dict] = []
        for k in keys:
            k = k.strip()
            if not k:
                continue
            row = by_key.get(k)
            if not row:
                log(f"warn: key not found: {k}")
                continue
            if is_dup(row):
                log(f"skip dup: {k}")
                continue
            out.append(row)
        return out[:limit]

    # Prefer 可下, then 待核; shortest notes first among those still thin
    cands = [
        r
        for r in rows
        if not is_dup(r) and len(str(r.get("备注") or "").strip()) < min_note
    ]
    status_rank = {"可下": 0, "待核": 1, "商务墙": 2}

    def sort_key(r: dict) -> tuple:
        st = (r.get("状态") or "").strip()
        return (
            status_rank.get(st, 9),
            len(str(r.get("备注") or "").strip()),
            str(r.get("去重键") or ""),
        )

    cands.sort(key=sort_key)
    return cands[:limit]


def build_prompt(row: dict) -> str:
    return f"""你是工控/ICS 软件资产编目助手。根据公开资料，为下列产品写结构化信息。
禁止臆造任何 URL；不确定的链接字段留空数组或空字符串。不要写利用/PoC/攻击步骤。
不要使用任何工具、网页搜索或 shell；仅凭已知公开资料作答。

产品: {row.get('产品') or ''}
厂商: {row.get('厂商') or ''}
官网: {row.get('官网') or ''}
下载页: {row.get('下载页') or ''}
文档: {row.get('文档') or ''}
现状备注: {row.get('备注') or ''}
状态: {row.get('状态') or ''}
Web服务: {row.get('Web服务') or ''}
部署方式: {row.get('部署方式') or ''}
行业: {row.get('行业') or ''}

请只输出一个 JSON 对象（不要 markdown 围栏），字段如下：
{{
  "简介": "2-5句中文，说明产品定位、典型场景、是否含 Web 控制台/HMI",
  "Web控制台": "端口或访问路径说明；未知则空字符串",
  "安装要点": "公开安装/部署要点摘要；勿编造命令细节",
  "下载条件补全": "注册/试用/商务等获取条件；未知则空",
  "文档要点": "官方文档入口或关键能力摘要；未知则空",
  "直连候选": ["仅公开可验证的 http(s) 安装包或 GitHub release 直链，或 docker pull image:tag；没有则 []"]
}}
"""


def extract_json_obj(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    candidates: list[str] = []
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        candidates.append(fence.group(1).strip())
    # unclosed fence
    fence2 = re.search(r"```(?:json)?\s*([\s\S]+)$", text)
    if fence2:
        candidates.append(fence2.group(1).strip())
    candidates.append(text)
    for blob in candidates:
        start, end = blob.find("{"), blob.rfind("}")
        if start < 0 or end <= start:
            continue
        try:
            obj = json.loads(blob[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def run_opencode_enrich(row: dict) -> dict | None:
    env = ensure_api_key(os.environ.copy())
    prompt = build_prompt(row)
    cmd = [
        str(OPENCODE_BIN),
        "run",
        "--standalone",
        "--auto",
        "--agent",
        "plan",
        "-m",
        MODEL,
        "--format",
        "default",
        prompt,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=240,
            env=env,
            cwd=str(ROOT),
        )
    except Exception as e:
        log(f"  opencode fail: {e}")
        return None
    if proc.returncode != 0:
        err = (proc.stderr or "")[:300]
        log(f"  opencode exit={proc.returncode}: {err}")
        return None
    obj = extract_json_obj(proc.stdout or "")
    if not obj:
        log(f"  no JSON in opencode out (len={len(proc.stdout or '')})")
        # dump a short preview for debug (no secrets)
        preview = (proc.stdout or "").replace("\n", " ")[:200]
        log(f"  preview: {preview}")
    return obj


def trusted_url(u: str) -> bool:
    u = u.strip()
    if u.lower().startswith("docker pull "):
        return True
    if not u.startswith("http://") and not u.startswith("https://"):
        return False
    try:
        parsed = urlparse(u)
        host = (parsed.hostname or "").lower()
        path = (parsed.path or "").lower()
    except Exception:
        return False
    if not host:
        return False
    # reject HTML/download-center pages
    if path.endswith((".html", ".htm", ".php", ".aspx")) or path.rstrip("/").endswith("index"):
        if "/releases/download/" not in u.lower() and not BINARY_EXT.search(u):
            return False
    if BINARY_EXT.search(u):
        return True
    if "github.com" in host and "/releases/download/" in u.lower():
        return True
    if "api.github.com" in host and ("tarball" in u.lower() or "zipball" in u.lower()):
        return True
    # docker hub style only via docker pull above; allow known CDN package hosts with binary ext only
    if any(h in host for h in TRUSTED_HOST_HINTS) and BINARY_EXT.search(u):
        return True
    return False


def compose_note(row: dict, info: dict) -> str:
    parts: list[str] = []
    for key in ("简介", "Web控制台", "安装要点", "下载条件补全", "文档要点"):
        val = str(info.get(key) or "").strip()
        if not val:
            continue
        label = {
            "简介": "",
            "Web控制台": "Web控制台",
            "安装要点": "安装",
            "下载条件补全": "下载条件",
            "文档要点": "文档",
        }[key]
        if label:
            parts.append(f"{label}：{val}")
        else:
            parts.append(val)
    new_body = "；".join(parts).strip()
    old = str(row.get("备注") or "").strip()
    # Prefer the longer, richer note; keep old unique facts if new is short
    if len(new_body) <= len(old):
        # still allow append of structured bits not in old
        return old
    stamp = f"信息充实时间：{now_shanghai()}；来源：OpenCode/IMKAI"
    if stamp not in new_body:
        new_body = f"{new_body}；{stamp}"
    # If old has unique short signals (e.g. fetch fail), keep a brief tail once
    if old and old not in new_body and len(old) < 120:
        # avoid duplicating when old is just a subset
        if old[:20] not in new_body:
            new_body = f"{new_body}；原备注：{old}"
    return new_body


def apply_enrich(row: dict, info: dict) -> dict[str, Any]:
    """Mutate row; return summary of changes."""
    summary: dict[str, Any] = {"key": row.get("去重键"), "note_len": None, "direct": None}
    new_note = compose_note(row, info)
    old_note = str(row.get("备注") or "").strip()
    if len(new_note) > len(old_note):
        row["备注"] = new_note
        summary["note_len"] = len(new_note)

    # optional download condition field
    cond = str(info.get("下载条件补全") or "").strip()
    if cond:
        old_cond = str(row.get("下载条件") or "").strip()
        if len(cond) > len(old_cond):
            row["下载条件"] = cond

    # optional Web服务 snippet
    web = str(info.get("Web控制台") or "").strip()
    if web:
        old_web = str(row.get("Web服务") or "").strip()
        if len(web) > len(old_web):
            row["Web服务"] = web

    cands = info.get("直连候选") or []
    if not isinstance(cands, list):
        cands = []
    trusted = [str(u).strip() for u in cands if isinstance(u, str) and trusted_url(u)]
    trusted = list(dict.fromkeys(trusted))[:5]
    if trusted and not has_direct(row):
        row["直连下载"] = trusted if len(trusted) > 1 else trusted[0]
        row["直连核验时间"] = now_shanghai()
        summary["direct"] = row["直连下载"]

    return summary


def update_config_timestamp() -> None:
    if not CONFIG_PATH.exists():
        return
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg["updatedAt"] = now_shanghai()
    write_json(CONFIG_PATH, cfg)


def main() -> int:
    ap = argparse.ArgumentParser(description="Enrich ICS product notes via OpenCode")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--keys", default="", help="Comma-separated 去重键")
    ap.add_argument("--min-note", type=int, default=80, help="Enrich if 备注 shorter")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    limit = max(1, min(int(args.limit), 20))
    keys = [k.strip() for k in args.keys.split(",") if k.strip()] or None
    rows: list[dict] = json.loads(ICS_PATH.read_text(encoding="utf-8"))
    targets = select_targets(rows, keys, limit, args.min_note)
    log(f"[ics-enrich] selected {len(targets)} / limit {limit} min_note={args.min_note}")

    results: list[dict] = []
    changed = 0
    for row in targets:
        key = row.get("去重键") or "?"
        log(f"[ics-enrich] {key} (备注 {len(str(row.get('备注') or ''))} 字)")
        if args.dry_run:
            log("  dry-run: skip OpenCode")
            continue
        info = run_opencode_enrich(row)
        if not info:
            results.append({"key": key, "ok": False})
            continue
        summary = apply_enrich(row, info)
        summary["ok"] = bool(summary.get("note_len") or summary.get("direct"))
        if summary["ok"]:
            changed += 1
        results.append(summary)
        log(
            f"  → note_len={summary.get('note_len')} direct={summary.get('direct') is not None}"
        )

    if not args.dry_run and changed:
        write_json(ICS_PATH, rows)
        update_config_timestamp()
        log(f"[ics-enrich] wrote {ICS_PATH.relative_to(ROOT)} changed={changed}")

    # machine-readable summary line for parent
    log("=== ENRICH_SUMMARY " + json.dumps(results, ensure_ascii=False))
    log(f"=== summary enriched={changed} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"fatal: {e}", file=sys.stderr)
        raise SystemExit(1)
