#!/usr/bin/env python3
"""Find / verify official download pages for ICS & 信创 assets via browser + OpenRouter.

Reads OPENROUTER_API_KEY from the environment only. Never prints the key.
Never invents package URLs — only catalogs public product / download-center pages.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
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

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_REFERER = "https://ai862.github.io/asset-monitor/"
OPENROUTER_TITLE = "asset-monitor-downloads"

MODEL_CHAIN = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openrouter/free",
]

TZ_SH = timezone(timedelta(hours=8), name="Asia/Shanghai")

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 "
    "asset-monitor-downloads/1.0"
)

DOWNLOAD_HINT = re.compile(
    r"(download|试用|下载|release|soft|安装|trial|demo|获取|get[\s_-]?started|"
    r"software|资源|镜像|iso|docker|community|免费|free[\s_-]?trial|"
    r"download[\s_-]?center|下载中心|产品下载|软件下载)",
    re.I,
)

BINARY_EXT = re.compile(
    r"\.(exe|msi|dmg|pkg|iso|zip|rar|7z|tar|gz|bz2|xz|deb|rpm|apk|bin|run|img)(\?|$)",
    re.I,
)

STATUS_OK = {"可下", "待核", "商务墙"}


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


def same_host_homepage(dl: str, site: str) -> bool:
    """True if 下载页 is effectively the homepage of 官网."""
    if not dl or not site:
        return False
    try:
        p_dl = urlparse(dl.strip())
        p_site = urlparse(site.strip())
    except Exception:
        return False
    if not p_dl.netloc or not p_site.netloc:
        return False
    if p_dl.netloc.lower().lstrip("www.") != p_site.netloc.lower().lstrip("www."):
        return False
    path = (p_dl.path or "/").rstrip("/") or "/"
    return path == "/"


def needs_download_check(row: dict, force: bool) -> bool:
    if force:
        return True
    st = (row.get("状态") or "").strip()
    dl = (row.get("下载页") or "").strip() if row.get("下载页") else ""
    site = (row.get("官网") or "").strip() if row.get("官网") else ""
    if st == "待核":
        return True
    if not dl:
        return True
    if site and same_host_homepage(dl, site):
        return True
    return False


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
            if force or needs_download_check(row, False):
                out.append(row)
            else:
                log(f"skip already checked: {k} (use --force)")
        return out[:limit]
    out = []
    for r in rows:
        if needs_download_check(r, force):
            out.append(r)
        if len(out) >= limit:
            break
    return out


def http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    body: dict | None = None,
    timeout: int = 120,
) -> tuple[int, str]:
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return e.code, raw


_playwright_available: bool | None = None


def has_playwright() -> bool:
    global _playwright_available
    if _playwright_available is not None:
        return _playwright_available
    try:
        import playwright  # noqa: F401

        _playwright_available = True
    except ImportError:
        _playwright_available = False
    return _playwright_available


def fetch_html_urllib(url: str, timeout: int = 20) -> tuple[str, str]:
    """Return (final_url, html). Raises on hard failure."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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


def fetch_html_playwright(url: str, timeout_ms: int = 20000) -> tuple[str, str]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(800)
            return page.url, page.content()
        finally:
            browser.close()


def fetch_html(url: str) -> tuple[str, str, str]:
    """Return (final_url, html, backend). Skip binary URLs."""
    if BINARY_EXT.search(urlparse(url).path or ""):
        raise ValueError(f"skip binary URL: {url}")
    if has_playwright():
        try:
            final, html = fetch_html_playwright(url)
            return final, html, "playwright"
        except Exception as e:
            log(f"  playwright fail ({e}); fallback urllib")
    final, html = fetch_html_urllib(url)
    return final, html, "urllib"


def strip_scripts(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    return html


def extract_title(html: str) -> str:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if not m:
        return ""
    return re.sub(r"\s+", " ", html_lib.unescape(m.group(1))).strip()[:200]


def extract_links(html: str, base_url: str, limit: int = 40) -> list[dict[str, str]]:
    """Collect candidate download-ish anchors (text + absolute href)."""
    cleaned = strip_scripts(html)
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(
        r'(?is)<a\s+[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', cleaned
    ):
        href = html_lib.unescape(m.group(1).strip())
        text = re.sub(r"<[^>]+>", " ", m.group(2))
        text = re.sub(r"\s+", " ", html_lib.unescape(text)).strip()[:120]
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        abs_url = urljoin(base_url, href)
        parsed = urlparse(abs_url)
        if parsed.scheme not in ("http", "https"):
            continue
        # Prefer download-hinted; still keep a few same-site nav links early
        hinted = bool(DOWNLOAD_HINT.search(text) or DOWNLOAD_HINT.search(href))
        if BINARY_EXT.search(parsed.path or ""):
            # Catalog the *page* that points to binary, not the binary itself
            # Keep as candidate but mark — LLM should prefer the parent page
            pass
        key = abs_url.split("#")[0]
        if key in seen:
            continue
        if not hinted and len(candidates) >= 12:
            # After some general links, only keep hinted
            continue
        if not hinted and not DOWNLOAD_HINT.search(key):
            # allow first few same-host links for navigation context
            if len(candidates) >= 8:
                continue
        seen.add(key)
        candidates.append({"text": text or "(no text)", "href": key, "hinted": str(hinted)})
        if len(candidates) >= limit:
            break
    # Sort hinted first while preserving relative order within groups
    hinted_list = [c for c in candidates if c["hinted"] == "True"]
    other = [c for c in candidates if c["hinted"] != "True"]
    ordered = hinted_list + other
    for c in ordered:
        c.pop("hinted", None)
    return ordered[:limit]


def duckduckgo_search(query: str, limit: int = 8) -> list[dict[str, str]]:
    """HTML search via DuckDuckGo (no API key). Prefer official domains later."""
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    results: list[dict[str, str]] = []
    try:
        _, html = fetch_html_urllib(url, timeout=25)
    except Exception as e:
        log(f"  DDG search fail: {e}")
        return results
    # result links: <a class="result__a" href="...">
    for m in re.finditer(
        r'(?is)<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html,
    ):
        href = html_lib.unescape(m.group(1).strip())
        title = re.sub(r"<[^>]+>", " ", m.group(2))
        title = re.sub(r"\s+", " ", html_lib.unescape(title)).strip()[:160]
        # DDG sometimes wraps redirects
        if "uddg=" in href:
            qs = urllib.parse.parse_qs(urlparse(href).query)
            if qs.get("uddg"):
                href = urllib.parse.unquote(qs["uddg"][0])
        if not href.startswith("http"):
            continue
        results.append({"title": title, "href": href.split("#")[0]})
        if len(results) >= limit:
            break
    if not results:
        # Fallback: Bing CN lite
        bing = "https://www.bing.com/search?" + urllib.parse.urlencode(
            {"q": query, "setlang": "zh-CN"}
        )
        try:
            _, bhtml = fetch_html_urllib(bing, timeout=25)
            for m in re.finditer(
                r'(?is)<li class="b_algo".*?<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                bhtml,
            ):
                href = html_lib.unescape(m.group(1).strip())
                title = re.sub(r"<[^>]+>", " ", m.group(2))
                title = re.sub(r"\s+", " ", html_lib.unescape(title)).strip()[:160]
                if href.startswith("http"):
                    results.append({"title": title, "href": href.split("#")[0]})
                if len(results) >= limit:
                    break
        except Exception as e:
            log(f"  Bing search fail: {e}")
    return results


def extract_json_object(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            return None
    return None


def openrouter_complete(api_key: str, system: str, user: str) -> dict | None:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": OPENROUTER_TITLE,
        "Referer": OPENROUTER_REFERER,
    }
    last_err = ""
    for model in MODEL_CHAIN:
        body = {
            "model": model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        log(f"  OpenRouter model={model}")
        status, raw = http_json(
            OPENROUTER_URL, method="POST", headers=headers, body=body, timeout=180
        )
        if status >= 400:
            last_err = f"HTTP {status}: {raw[:300]}"
            log(f"  fail {last_err}")
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            last_err = "invalid JSON response"
            continue
        usage = payload.get("usage") or {}
        log(f"  ok model={payload.get('model')} cost={usage.get('cost')}")
        choices = payload.get("choices") or []
        if not choices:
            last_err = "no choices"
            continue
        content = (choices[0].get("message") or {}).get("content") or ""
        obj = extract_json_object(content)
        if obj:
            return obj
        last_err = "could not parse JSON from content"
        log(f"  {last_err}")
    log(f"  OpenRouter exhausted: {last_err}")
    return None


SYSTEM_PROMPT = """你是工控/信创软件「官方下载页」核查助手。根据给定的页面标题、候选链接与搜索结果，输出【仅一个 JSON 对象】，不要 markdown，不要解释。

字段：
- action: "open" | "finish"
- url: action=open 时，下一步要打开的页面绝对 URL（优先站内下载中心/试用页）
- 下载页: 最佳官方下载/试用中心页 URL；不确定则空字符串
- 下载条件: 一句短中文说明（如何获取安装包；登录后下 / 填表 / 仅商务等）
- 状态: 仅 "可下" | "待核" | "商务墙"
- confidence: 0.0～1.0
- notes: 可选短备注

判定规则：
- 可下 = 能自助获取安装包 / ISO / Docker / 社区试用，且存在可达的下载中心页（需登录后再下也可以，只要页面就是下载中心）
- 商务墙 = 只能联系销售 / 预约演示 / 商务洽谈，没有可自助安装包
- 待核 = 不确定、验证码挡、找到了产品页但未确认安装包入口
- 绝不编造 .exe/.iso 等包直链；只给官方网页 URL
- 优先厂商官方域名，回避第三方网盘/破解站/非官方镜像
- action=open 仅用于跟进有希望的站内下载中心；证据足够时用 finish
- 若搜索与页面都显示仅「申请试用/联系我们」而无下载中心 → 状态=商务墙，下载页可留空或产品页"""


def build_step_prompt(
    row: dict,
    page_url: str,
    title: str,
    links: list[dict[str, str]],
    search_hits: list[dict[str, str]],
    step: int,
    max_steps: int,
    history: list[str],
) -> str:
    identity = {
        "产品": row.get("产品"),
        "厂商": row.get("厂商"),
        "去重键": row.get("去重键"),
        "官网": row.get("官网"),
        "当前下载页": row.get("下载页"),
        "当前状态": row.get("状态"),
        "下载条件": row.get("下载条件"),
        "备注": row.get("备注"),
    }
    return (
        f"步骤 {step}/{max_steps}\n"
        f"资产：\n{json.dumps(identity, ensure_ascii=False, indent=2)}\n\n"
        f"当前打开：{page_url}\n标题：{title}\n"
        f"候选链接（最多 40）：\n{json.dumps(links, ensure_ascii=False, indent=2)}\n\n"
        f"网络搜索结果：\n{json.dumps(search_hits, ensure_ascii=False, indent=2)}\n\n"
        f"已访问：{history}\n"
        "请输出 JSON：action=open|finish …"
    )


def normalize_finish(decision: dict, row: dict) -> dict:
    status = str(decision.get("状态") or "待核").strip()
    if status not in STATUS_OK:
        status = "待核"
    dl = str(decision.get("下载页") or "").strip()
    if dl and not dl.startswith("http"):
        dl = ""
    if BINARY_EXT.search(urlparse(dl).path or ""):
        # Never store package binary as 下载页 — keep parent if we have 官网
        dl = ""
        if status == "可下":
            status = "待核"
    cond = str(decision.get("下载条件") or "").strip()[:300]
    if not cond:
        if status == "商务墙":
            cond = "需联系厂商/预约演示，未见自助安装包入口"
        elif status == "可下":
            cond = "官方下载中心可自助获取（以页面实际流程为准）"
        else:
            cond = "未能确认可自助下载入口，待人工复核"
    conf = decision.get("confidence")
    try:
        conf_f = float(conf)
    except (TypeError, ValueError):
        conf_f = 0.0
    return {
        "下载页": dl or None,
        "下载条件": cond,
        "状态": status,
        "confidence": max(0.0, min(1.0, conf_f)),
        "notes": str(decision.get("notes") or "")[:400],
    }


def agent_find_download(
    row: dict, api_key: str, max_steps: int
) -> dict | None:
    """Run browse + LLM loop; return normalized finish fields or None on hard fail."""
    site = (row.get("官网") or "").strip()
    start = (row.get("下载页") or "").strip() if row.get("下载页") else ""
    if start and start.startswith("http") and not same_host_homepage(start, site):
        current = start
    elif site and site.startswith("http"):
        current = site
    else:
        log("  no usable 官网/下载页 URL")
        return {
            "下载页": None,
            "下载条件": "无有效官网 URL，无法自动核验",
            "状态": "待核",
            "confidence": 0.0,
            "notes": "missing site",
        }

    product = row.get("产品") or ""
    vendor = row.get("厂商") or ""
    query = f"{product} {vendor} 下载 试用 OR download".strip()
    log(f"  search: {query}")
    search_hits = duckduckgo_search(query, limit=8)
    if site and search_hits:
        site_host = ""
        try:
            site_host = urlparse(site).netloc.lower().lstrip("www.")
        except Exception:
            site_host = ""

        def _hit_rank(h: dict) -> int:
            try:
                host = urlparse(h["href"]).netloc.lower().lstrip("www.")
            except Exception:
                return 2
            if site_host and (host == site_host or host.endswith("." + site_host)):
                return 0
            return 1

        search_hits = sorted(search_hits, key=_hit_rank)

    history: list[str] = []
    last_links: list[dict[str, str]] = []
    last_title = ""
    last_url = current
    decision: dict | None = None

    for step in range(1, max_steps + 1):
        log(f"  step {step}: open {current}")
        try:
            final, html, backend = fetch_html(current)
            log(f"  fetched via {backend} → {final} ({len(html)} bytes)")
        except Exception as e:
            log(f"  fetch error: {e}")
            history.append(f"{current} [error]")
            # Ask LLM with search only / previous context
            final, html, last_title, last_links = current, "", "", []
        else:
            last_url = final
            last_title = extract_title(html)
            last_links = extract_links(html, final, limit=40)
            history.append(final)

        decision = openrouter_complete(
            api_key,
            SYSTEM_PROMPT,
            build_step_prompt(
                row, last_url, last_title, last_links, search_hits, step, max_steps, history
            ),
        )
        if not decision:
            break
        action = str(decision.get("action") or "finish").lower().strip()
        if action == "open" and step < max_steps:
            nxt = str(decision.get("url") or "").strip()
            if nxt.startswith("http") and nxt not in history and not BINARY_EXT.search(
                urlparse(nxt).path or ""
            ):
                current = nxt
                continue
            # invalid open → treat as finish with given fields
            action = "finish"
        if action != "open":
            return normalize_finish(decision, row)

    # max steps or LLM fail — finish with best effort from last decision or pending
    if decision:
        return normalize_finish(decision, row)
    return {
        "下载页": row.get("下载页"),
        "下载条件": (row.get("下载条件") or "") + "；自动核验未完成（LLM/网络失败）",
        "状态": row.get("状态") or "待核",
        "confidence": 0.0,
        "notes": "agent incomplete",
    }


def apply_result(row: dict, result: dict) -> None:
    if result.get("下载页"):
        row["下载页"] = result["下载页"]
    elif result.get("状态") == "商务墙":
        # keep existing or clear if was homepage-only noise — leave as-is if set
        pass
    if result.get("下载条件"):
        row["下载条件"] = result["下载条件"]
    if result.get("状态") in STATUS_OK:
        row["状态"] = result["状态"]
    row["下载核验时间"] = now_shanghai()
    row["下载核验来源"] = "openrouter+browser"


def process_source(
    source: str,
    api_key: str,
    keys: list[str] | None,
    limit: int,
    force: bool,
    max_steps: int,
    dry_run: bool,
) -> tuple[int, dict[str, int]]:
    path = SOURCE_PATHS[source]
    rows: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    targets = select_targets(rows, keys, limit, force)
    log(f"[{source}] selected {len(targets)} / limit {limit}")
    counts = {"可下": 0, "待核": 0, "商务墙": 0, "updated": 0}
    if not targets:
        return 0, counts

    changed = 0
    for row in targets:
        key = row.get("去重键") or "?"
        log(f"[{source}] find {key} ({row.get('产品')})")
        if dry_run:
            log("  dry-run: skip network")
            continue
        result = agent_find_download(row, api_key, max_steps)
        if not result:
            log(f"  no result for {key}")
            continue
        apply_result(row, result)
        st = row.get("状态") or "待核"
        if st in counts:
            counts[st] += 1
        counts["updated"] += 1
        changed += 1
        log(
            f"  → 状态={row.get('状态')} 下载页={row.get('下载页')} "
            f"条件={row.get('下载条件')}"
        )

    if dry_run:
        return 0, counts
    if changed:
        write_json(path, rows)
        log(f"[{source}] wrote {path.relative_to(ROOT)}")
    return changed, counts


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Find official download pages for ICS / 信创 (OpenRouter + browser)"
    )
    ap.add_argument(
        "--source",
        choices=("ics", "xinchuang", "both"),
        default="both",
        help="Which dataset to process",
    )
    ap.add_argument("--keys", default="", help="Comma-separated 去重键")
    ap.add_argument("--limit", type=int, default=3, help="Max assets per source (cap 8)")
    ap.add_argument("--force", action="store_true", help="Re-check even if already 可下")
    ap.add_argument("--max-steps", type=int, default=6, help="Max browse steps per asset")
    ap.add_argument("--dry-run", action="store_true", help="Select targets only")
    args = ap.parse_args()

    limit = max(1, min(int(args.limit), 8))
    max_steps = max(1, min(int(args.max_steps), 10))
    keys = [k.strip() for k in args.keys.split(",") if k.strip()] or None

    api_key = os.environ.get("OPENROUTER_API_KEY") or ""
    if api_key and os.environ.get("GITHUB_ACTIONS"):
        print(f"::add-mask::{api_key}", flush=True)

    if not args.dry_run and not api_key:
        log("ERROR: OPENROUTER_API_KEY missing")
        return 1

    sources = ["ics", "xinchuang"] if args.source == "both" else [args.source]
    total_changed = 0
    summary_lines: list[str] = []

    log(f"browser backend: {'playwright' if has_playwright() else 'urllib'}")

    for src in sources:
        # When --keys given with both, still try each source (missing keys warn)
        changed, counts = process_source(
            src, api_key, keys, limit, args.force, max_steps, args.dry_run
        )
        total_changed += changed
        summary_lines.append(
            f"{src}: updated={counts['updated']} 可下={counts['可下']} "
            f"待核={counts['待核']} 商务墙={counts['商务墙']}"
        )

    if args.dry_run:
        log("dry-run complete (no write)")
        for line in summary_lines:
            log(line)
        return 0

    if total_changed:
        update_config_timestamp()
        log("updated config.json updatedAt")

    log("=== summary ===")
    for line in summary_lines:
        log(line)
    log(f"total rows changed: {total_changed}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"fatal: {e}", file=sys.stderr)
        raise SystemExit(1)
