#!/usr/bin/env python3
"""Fill 直连下载 URLs for ICS / 信创 assets from official download pages.

Default: only write URL metadata (直连下载 / 直连核验时间). Does not invent URLs.
Optional --upload-drive downloads packages ≤200MB (unless --force-large) and
records Drive路径 metadata (actual Drive MCP upload is left to parent routine).

OpenCode assist: --opencode runs scripts/opencode_find_direct.sh for 1–3 keys
when HTML scrape finds nothing; falls back silently if opencode unavailable.
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"
SOURCE_PATHS = {
    "ics": ROOT / "data" / "ics.json",
    "xinchuang": ROOT / "data" / "xinchuang.json",
}
OPENCODE_HELPER = ROOT / "scripts" / "opencode_find_direct.sh"

TZ_SH = timezone(timedelta(hours=8), name="Asia/Shanghai")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 "
    "asset-monitor-direct/1.0"
)

BINARY_EXT = re.compile(
    r"\.(exe|msi|dmg|pkg|iso|zip|rar|7z|tar\.gz|tgz|tar\.bz2|tar\.xz|tar|gz|bz2|xz|"
    r"deb|rpm|apk|bin|run|img|AppImage)(\?|$)",
    re.I,
)
DOCKER_REF = re.compile(
    r"(?:docker\s+pull\s+|^\s*)([a-z0-9]+(?:[./_-][a-z0-9]+)+:[a-z0-9._-]+)",
    re.I | re.M,
)
STATUS_FILL = {"可下", "待核"}
MAX_DEFAULT_BYTES = 200 * 1024 * 1024  # 200 MiB soft guard for --upload-drive


def now_shanghai() -> str:
    return datetime.now(TZ_SH).replace(microsecond=0).isoformat()


def log(msg: str) -> None:
    print(msg, flush=True)


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def update_config_timestamp() -> None:
    if not CONFIG_PATH.exists():
        return
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    cfg["updatedAt"] = now_shanghai()
    write_json(CONFIG_PATH, cfg)


def has_direct(row: dict) -> bool:
    v = row.get("直连下载")
    if v is None or v == "" or v == []:
        return False
    if isinstance(v, list):
        return any(str(x).strip() for x in v)
    return bool(str(v).strip())


def needs_direct(row: dict, force: bool) -> bool:
    if force:
        return True
    st = (row.get("状态") or "").strip()
    if st not in STATUS_FILL and st != "商务墙":
        # still allow 可下/待核 only by default
        return False
    if st == "商务墙":
        return False
    if has_direct(row):
        return False
    page = (row.get("下载页") or row.get("官网") or "").strip()
    return bool(page and page.startswith("http"))


def select_targets(
    rows: list[dict], keys: list[str] | None, limit: int, force: bool
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
            if force or needs_direct(row, False):
                out.append(row)
            else:
                log(f"skip (has 直连 or no page): {k}")
        return out[:limit]
    out = []
    for r in rows:
        if needs_direct(r, force):
            out.append(r)
        if len(out) >= limit:
            break
    return out


def fetch_html(url: str, timeout: int = 25) -> tuple[str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        final = resp.geturl()
        raw = resp.read()
        ctype = (resp.headers.get("Content-Type") or "").lower()
        charset = "utf-8"
        if "charset=" in ctype:
            charset = ctype.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        try:
            text = raw.decode(charset, errors="replace")
        except LookupError:
            text = raw.decode("utf-8", errors="replace")
        return final, text


def extract_hrefs(html: str, base: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'(?is)(?:href|src|data-url|data-href|data-download)\s*=\s*["\']([^"\']+)["\']',
        html,
    ):
        href = html_lib.unescape(m.group(1).strip())
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        abs_url = urljoin(base, href).split("#")[0]
        if abs_url in seen:
            continue
        seen.add(abs_url)
        urls.append(abs_url)
    # bare http(s) ending with binary ext in text
    for m in re.finditer(r"https?://[^\s\"'<>]+", html):
        u = m.group(0).rstrip(").,;]")
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def score_candidate(url: str) -> int:
    try:
        path = urlparse(url).path.lower()
    except ValueError:
        return -100
    score = 0
    if BINARY_EXT.search(path) or BINARY_EXT.search(url):
        score += 50
    for bad in ("crack", "pirate", "serial", "keygen", "百度网盘", "lanzou"):
        if bad in url.lower():
            score -= 100
    for good in ("release", "download", "dist", "artifact", "github.com", "gitlab"):
        if good in url.lower():
            score += 5
    # prefer shorter query / cleaner CDN links slightly
    if "?" not in url:
        score += 2
    return score


def github_release_assets(page_url: str) -> list[str]:
    """If URL looks like github.com/owner/repo[...], list latest release asset URLs."""
    m = re.match(
        r"https?://(?:www\.)?github\.com/([^/]+)/([^/]+)(?:/|$)",
        page_url,
        re.I,
    )
    if not m:
        return []
    owner, repo = m.group(1), m.group(2)
    if repo.endswith(".git"):
        repo = repo[:-4]
    api = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    req = urllib.request.Request(
        api,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        log(f"  github api fail: {e}")
        return []
    out: list[str] = []
    for asset in data.get("assets") or []:
        u = asset.get("browser_download_url") or ""
        if u.startswith("http"):
            out.append(u)
    # also tarball/zipball
    for k in ("tarball_url", "zipball_url"):
        u = data.get(k) or ""
        if u.startswith("http"):
            out.append(u)
    return out


def extract_docker_refs(html: str) -> list[str]:
    refs: list[str] = []
    for m in DOCKER_REF.finditer(html):
        ref = m.group(1).strip()
        if "/" in ref and ":" in ref:
            refs.append(f"docker pull {ref}")
    return refs


def candidates_from_page(page_url: str) -> tuple[list[str], str]:
    """Return (ranked candidate URLs / docker refs, note)."""
    note = ""
    try:
        final, html = fetch_html(page_url)
    except Exception as e:
        return [], f"fetch fail: {e}"

    hrefs = extract_hrefs(html, final)
    found: list[str] = []
    for u in hrefs:
        try:
            path = urlparse(u).path or ""
        except ValueError:
            continue
        if BINARY_EXT.search(path) or BINARY_EXT.search(u):
            found.append(u)
    found.extend(github_release_assets(page_url))
    found.extend(github_release_assets(final))
    # docker as text OK
    found.extend(extract_docker_refs(html))

    # de-dupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for u in found:
        if u not in seen:
            seen.add(u)
            uniq.append(u)

    uniq.sort(key=score_candidate, reverse=True)
    if not uniq:
        # login wall heuristics
        low = html.lower()
        if any(
            x in low
            for x in (
                "login",
                "sign in",
                "登录",
                "注册后下载",
                "申请试用",
                "联系销售",
                "contact sales",
            )
        ):
            note = "页面疑似登录/留资墙，未见公开直链"
        else:
            note = "页面未解析到公开安装包直链"
    return uniq[:12], note


def run_opencode(row: dict) -> list[str]:
    if not OPENCODE_HELPER.exists():
        return []
    env = os.environ.copy()
    cmd = [
        "bash",
        str(OPENCODE_HELPER),
        str(row.get("产品") or ""),
        str(row.get("厂商") or ""),
        str(row.get("官网") or ""),
        str(row.get("下载页") or ""),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
            cwd=str(ROOT),
        )
    except Exception as e:
        log(f"  opencode helper fail: {e}")
        return []
    if proc.returncode != 0:
        log(f"  opencode exit={proc.returncode}: {(proc.stderr or '')[:200]}")
        return []
    out = (proc.stdout or "").strip()
    # parse JSON array or loose URLs
    urls: list[str] = []
    try:
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", out)
        blob = fence.group(1).strip() if fence else out
        start, end = blob.find("["), blob.rfind("]")
        if start >= 0 and end > start:
            arr = json.loads(blob[start : end + 1])
            if isinstance(arr, list):
                for x in arr:
                    if isinstance(x, str) and x.startswith("http"):
                        urls.append(x.strip())
                    elif isinstance(x, str) and x.lower().startswith("docker pull "):
                        urls.append(x.strip())
    except json.JSONDecodeError:
        pass
    if not urls:
        for m in re.finditer(r"https?://[^\s\"'<>]+", out):
            u = m.group(0).rstrip(").,;]")
            if BINARY_EXT.search(u) or "github.com" in u:
                urls.append(u)
    def _looks_direct(u: str) -> bool:
        lu = u.lower()
        if lu.startswith("docker pull "):
            return True
        if not u.startswith("http"):
            return False
        if BINARY_EXT.search(u):
            return True
        if "/releases/download/" in lu:
            return True
        if "api.github.com" in lu and ("tarball" in lu or "zipball" in lu):
            return True
        # reject bare HTML pages / download centers
        path = urlparse(u).path.lower()
        if path.endswith((".html", ".htm", ".php", ".aspx", "/")) or path.endswith("index"):
            return False
        return False

    # never invent: only keep package-like http(s) / docker pull
    out: list[str] = []
    for u in urls:
        try:
            if _looks_direct(u):
                out.append(u)
        except ValueError:
            continue
    return out[:8]


def pick_best(cands: list[str]) -> str | list[str] | None:
    if not cands:
        return None
    # Prefer single best binary; if several top-scored, store list of top 3
    scored = sorted(cands, key=score_candidate, reverse=True)
    top = [u for u in scored if score_candidate(u) >= 50][:3]
    if not top:
        top = scored[:1]
    if len(top) == 1:
        return top[0]
    return top


def head_content_length(url: str) -> int | None:
    if url.lower().startswith("docker pull "):
        return None
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            cl = resp.headers.get("Content-Length")
            return int(cl) if cl and cl.isdigit() else None
    except Exception:
        return None


def stub_drive_upload(
    row: dict, url: str, force_large: bool
) -> tuple[str | None, str | None]:
    """Download to /tmp and record Drive路径 metadata. No real Drive API here."""
    if url.lower().startswith("docker pull "):
        log("  skip drive upload for docker ref")
        return None, None
    size = head_content_length(url)
    if size is not None and size > MAX_DEFAULT_BYTES and not force_large:
        log(f"  skip large file ({size} bytes > 200MB); use --force-large")
        return None, None
    vendor = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", str(row.get("厂商") or "unknown"))[:40]
    product = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", str(row.get("产品") or "pkg"))[:60]
    name = Path(urlparse(url).path).name or "package.bin"
    name = urllib.parse.unquote(name)[:120]
    drive_path = f"{vendor}/{product}/{name}"
    dest = Path("/tmp") / f"asset-monitor-{row.get('去重键')}-{name}"
    log(f"  download → {dest} (Drive stub path {drive_path})")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as f:
            # stream with soft size guard
            total = 0
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DEFAULT_BYTES and not force_large:
                    log("  abort download: exceeded 200MB mid-stream")
                    dest.unlink(missing_ok=True)
                    return None, None
                f.write(chunk)
        log(f"  saved {total} bytes; parent routine should UploadFile to Drive → {drive_path}")
        # Drive文件ID left empty until MCP upload
        return drive_path, None
    except Exception as e:
        log(f"  download fail: {e}")
        return None, None


def apply_direct(
    row: dict,
    value: str | list[str] | None,
    note: str,
    *,
    upload_drive: bool,
    force_large: bool,
) -> bool:
    """Write fields; return True if 直连下载 changed."""
    changed = False
    if value:
        row["直连下载"] = value
        row["直连核验时间"] = now_shanghai()
        changed = True
        if upload_drive:
            url = value if isinstance(value, str) else value[0]
            dpath, did = stub_drive_upload(row, url, force_large)
            if dpath:
                row["Drive路径"] = dpath
                if did:
                    row["Drive文件ID"] = did
                changed = True
    else:
        # leave 直连 empty; brief note
        if note:
            cond = (row.get("下载条件") or "").strip()
            tag = f"；直连：{note}"
            if tag not in cond:
                row["下载条件"] = (cond + tag) if cond else note
                changed = True
            remark = (row.get("备注") or "").strip()
            brief = note[:80]
            if brief and brief not in remark:
                row["备注"] = (remark + "；" + brief) if remark else brief
                changed = True
        row["直连核验时间"] = now_shanghai()
        changed = True
    return changed


def process_source(
    source: str,
    keys: list[str] | None,
    limit: int,
    force: bool,
    use_opencode: bool,
    upload_drive: bool,
    force_large: bool,
    dry_run: bool,
) -> tuple[int, int]:
    path = SOURCE_PATHS[source]
    rows: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    targets = select_targets(rows, keys, limit, force)
    log(f"[{source}] selected {len(targets)} / limit {limit}")
    filled = 0
    touched = 0
    for row in targets:
        key = row.get("去重键") or "?"
        page = (row.get("下载页") or row.get("官网") or "").strip()
        log(f"[{source}] direct {key} ← {page}")
        if dry_run:
            log("  dry-run: skip network")
            continue
        try:
            cands, note = candidates_from_page(page)
            if not cands and use_opencode:
                log("  HTML empty → try OpenCode")
                cands = run_opencode(row)
                if cands:
                    note = "via OpenCode"
            best = pick_best(cands)
            if best:
                log(f"  → 直连={best if isinstance(best, str) else best[:3]}")
                if apply_direct(
                    row, best, note, upload_drive=upload_drive, force_large=force_large
                ):
                    filled += 1
                    touched += 1
                    if not dry_run:
                        write_json(path, rows)
                        log(f"  checkpoint wrote {path.relative_to(ROOT)}")
            else:
                log(f"  → no direct ({note})")
                if apply_direct(
                    row, None, note, upload_drive=False, force_large=force_large
                ):
                    touched += 1
                    if not dry_run:
                        write_json(path, rows)
        except Exception as e:
            log(f"  ERROR {key}: {e}")
            continue

    if not dry_run and touched:
        write_json(path, rows)
        log(f"[{source}] wrote {path.relative_to(ROOT)}")
    return filled, touched


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Fill 直连下载 for ICS / 信创 from official pages"
    )
    ap.add_argument("--source", choices=("ics", "xinchuang", "both"), default="both")
    ap.add_argument("--keys", default="", help="Comma-separated 去重键")
    ap.add_argument("--limit", type=int, default=3, help="Max assets per source (cap 10)")
    ap.add_argument("--force", action="store_true", help="Re-fill even if 直连下载 set")
    ap.add_argument(
        "--opencode",
        action="store_true",
        help="If HTML finds nothing, ask OpenCode (local) for public direct URLs",
    )
    ap.add_argument(
        "--upload-drive",
        action="store_true",
        help="Download package ≤200MB to /tmp and set Drive路径 stub for parent upload",
    )
    ap.add_argument(
        "--force-large",
        action="store_true",
        help="Allow >200MB when --upload-drive",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    limit = max(1, min(int(args.limit), 10))
    keys = [k.strip() for k in args.keys.split(",") if k.strip()] or None
    sources = ["ics", "xinchuang"] if args.source == "both" else [args.source]

    total_filled = total_touched = 0
    for src in sources:
        filled, touched = process_source(
            src,
            keys,
            limit,
            args.force,
            args.opencode,
            args.upload_drive,
            args.force_large,
            args.dry_run,
        )
        total_filled += filled
        total_touched += touched

    if not args.dry_run and total_touched:
        update_config_timestamp()

    log(
        f"=== summary filled_direct={total_filled} rows_touched={total_touched} "
        f"dry_run={args.dry_run}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"fatal: {e}", file=sys.stderr)
        raise SystemExit(1)
