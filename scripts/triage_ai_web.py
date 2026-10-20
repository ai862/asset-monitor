#!/usr/bin/env python3
"""Triage AI Web assets into v2 guidance fields via DeepWiki + OpenRouter.

Reads OPENROUTER_API_KEY from the environment only. Never prints the key.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "ai-web.json"
CONFIG_PATH = ROOT / "config.json"

DEEPWIKI_MCP = "https://mcp.deepwiki.com/mcp"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_REFERER = "https://ai862.github.io/asset-monitor/"
OPENROUTER_TITLE = "asset-monitor-triage"

MODEL_CHAIN = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openrouter/free",
]

TZ_SH = timezone(timedelta(hours=8), name="Asia/Shanghai")

V2_KEYS = (
    "搭建难度",
    "研判状态",
    "研判时间",
    "启动指引",
    "开工前先看",
    "建议追问",
    "已知坑",
    "成功标准",
    "DeepWiki",
    "研判摘要",
    "推荐启动",
    "研判来源",
    "schemaVersion",
    "agentHint",
)

UNTRIAGED = {"", "未研判", "索引缺失", None}


def now_shanghai() -> str:
    return datetime.now(TZ_SH).replace(microsecond=0).isoformat()


def log(msg: str) -> None:
    print(msg, flush=True)


def github_owner_repo(url: str) -> str | None:
    if not url or not isinstance(url, str):
        return None
    try:
        p = urlparse(url.strip())
    except Exception:
        return None
    if p.netloc.lower() not in {"github.com", "www.github.com"}:
        return None
    parts = [x for x in p.path.strip("/").split("/") if x]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"{owner}/{repo}"


def is_untriaged(row: dict) -> bool:
    st = row.get("研判状态")
    if st in UNTRIAGED or st is None:
        return True
    if not row.get("启动指引") and st != "已研判":
        return True
    return False


def select_targets(
    rows: list[dict], keys: list[str] | None, limit: int, force: bool
) -> list[dict]:
    by_key = {r.get("去重键"): r for r in rows if r.get("去重键")}
    if keys:
        out = []
        for k in keys:
            k = k.strip()
            if not k:
                continue
            row = by_key.get(k)
            if not row:
                log(f"warn: key not found: {k}")
                continue
            if force or is_untriaged(row):
                out.append(row)
            else:
                log(f"skip already triaged: {k} (use --force)")
        return out[:limit]
    out = []
    for r in rows:
        if force or is_untriaged(r):
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


def parse_sse_jsonrpc(text: str) -> Any:
    """Extract JSON-RPC result from SSE `data:` lines or plain JSON."""
    text = text.strip()
    if not text:
        return None
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    payloads = []
    for line in text.splitlines():
        if line.startswith("data:"):
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                payloads.append(json.loads(chunk))
            except json.JSONDecodeError:
                continue
    if not payloads:
        return None
    # Prefer last message that has result or error
    for obj in reversed(payloads):
        if isinstance(obj, dict) and ("result" in obj or "error" in obj):
            return obj
    return payloads[-1]


def extract_mcp_text(rpc: Any) -> str:
    if not isinstance(rpc, dict):
        return ""
    if rpc.get("error"):
        return f"[mcp error] {rpc['error']}"
    result = rpc.get("result")
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts = []
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(str(c.get("text") or ""))
                elif isinstance(c, str):
                    parts.append(c)
            return "\n".join(parts)
        if "text" in result:
            return str(result["text"])
    return json.dumps(result, ensure_ascii=False)[:8000]


def deepwiki_ask(repo: str, question: str) -> str:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "ask_question",
            "arguments": {"repoName": repo, "question": question},
        },
    }
    status, raw = http_json(
        DEEPWIKI_MCP,
        method="POST",
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        body=body,
        timeout=180,
    )
    if status >= 400:
        log(f"  DeepWiki HTTP {status}")
        return ""
    rpc = parse_sse_jsonrpc(raw)
    return extract_mcp_text(rpc)


def fetch_readme(owner_repo: str) -> str:
    """Fallback: raw README from common branches."""
    for branch in ("main", "master"):
        for name in ("README.md", "readme.md", "README.MD"):
            url = f"https://raw.githubusercontent.com/{owner_repo}/{branch}/{name}"
            status, raw = http_json(url, timeout=30)
            if status == 200 and raw.strip():
                return raw[:12000]
    return ""


def gather_context(row: dict, owner_repo: str) -> tuple[str, str]:
    """Return (context_text, deepwiki_status) where status is ok|缺失."""
    questions = [
        f"How do I install and start {row.get('产品') or owner_repo}? "
        "Include pip/npm/docker commands, default ports, and required env vars.",
        "What are common pitfalls, auth/token setup, and how do I verify a successful start?",
        "Summarize Web UI / gateway / API endpoints and any reverse-proxy notes.",
    ]
    parts: list[str] = []
    ok = False
    for q in questions[:3]:
        log(f"  DeepWiki: {q[:72]}…")
        ans = deepwiki_ask(owner_repo, q)
        if ans and not ans.startswith("[mcp error]"):
            ok = True
            parts.append(f"Q: {q}\nA: {ans}")
        elif ans:
            parts.append(ans)
    status = "ok" if ok else "索引缺失"
    if not ok:
        log("  DeepWiki miss — trying README fallback")
        readme = fetch_readme(owner_repo)
        if readme:
            parts.append(f"README fallback:\n{readme}")
    return "\n\n---\n\n".join(parts)[:28000], status


def extract_json_object(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    # Strip markdown fences
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Find outermost { }
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
            "temperature": 0.2,
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
        cost = usage.get("cost")
        log(f"  ok model={payload.get('model')} cost={cost}")
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


SYSTEM_PROMPT = """你是资产研判助手。根据给定的仓库资料，输出【仅一个 JSON 对象】，不要 markdown，不要解释。
字段（中文键名必须一致）：
- 搭建难度: 仅 "易" | "中" | "难" | "未知"
- 启动指引: 字符串，含最短启动路径、端口、环境变量、鉴权要点（中文）
- 开工前先看: [{ "title": "...", "url": "https://..." }, ...] 最多 8 条
- 建议追问: 字符串数组，3～6 条中文问题
- 已知坑: 字符串
- 成功标准: 字符串，可自测的检查项
- 研判摘要: 一两句中文摘要
- 推荐启动: 可选，一行命令
- agentHint: 一句短中文提示给 Agent
事实不足时搭建难度用"未知"，不要编造端口或命令。"""


def build_user_prompt(row: dict, owner_repo: str, context: str) -> str:
    identity = {
        "产品": row.get("产品"),
        "去重键": row.get("去重键"),
        "GitHub": row.get("GitHub"),
        "官网": row.get("官网"),
        "文档": row.get("文档"),
        "下载条件": row.get("下载条件"),
        "部署方式": row.get("部署方式"),
        "备注": row.get("备注"),
        "owner_repo": owner_repo,
        "DeepWiki": f"https://deepwiki.com/{owner_repo}",
    }
    return (
        "资产信息：\n"
        + json.dumps(identity, ensure_ascii=False, indent=2)
        + "\n\n仓库资料：\n"
        + (context or "(无)")
    )


def merge_v2(row: dict, fields: dict, deepwiki_status: str, owner_repo: str) -> None:
    row["搭建难度"] = fields.get("搭建难度") or "未知"
    if row["搭建难度"] not in {"易", "中", "难", "未知"}:
        row["搭建难度"] = "未知"
    if deepwiki_status == "索引缺失" and not fields.get("启动指引"):
        row["研判状态"] = "索引缺失"
    else:
        row["研判状态"] = "已研判" if fields.get("启动指引") else "索引缺失"
    row["研判时间"] = now_shanghai()
    if fields.get("启动指引"):
        row["启动指引"] = str(fields["启动指引"])
    links = fields.get("开工前先看")
    if isinstance(links, list):
        clean = []
        for it in links[:8]:
            if isinstance(it, dict) and it.get("url"):
                clean.append(
                    {"title": str(it.get("title") or it["url"]), "url": str(it["url"])}
                )
        if clean:
            row["开工前先看"] = clean
    qs = fields.get("建议追问")
    if isinstance(qs, list):
        row["建议追问"] = [str(x) for x in qs if x][:8]
    for k in ("已知坑", "成功标准", "研判摘要", "推荐启动", "agentHint"):
        if fields.get(k):
            row[k] = str(fields[k])
    row["DeepWiki"] = f"https://deepwiki.com/{owner_repo}"
    row["研判来源"] = "openrouter+deepwiki"
    row["schemaVersion"] = 2
    if not row.get("agentHint"):
        row["agentHint"] = "先读启动指引与开工前先看，再按成功标准自测。"


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


def triage_one(row: dict, api_key: str | None, dry_run: bool) -> bool:
    key = row.get("去重键") or "?"
    gh = row.get("GitHub") or ""
    owner_repo = github_owner_repo(gh)
    log(f"triage {key} ({owner_repo or 'no-github'})")
    if not owner_repo:
        row["研判状态"] = "索引缺失"
        row["研判时间"] = now_shanghai()
        row["搭建难度"] = row.get("搭建难度") or "未知"
        row["研判来源"] = "openrouter+deepwiki"
        row["schemaVersion"] = 2
        row["研判摘要"] = row.get("研判摘要") or "无有效 GitHub 地址，无法 DeepWiki 取材。"
        return True

    if dry_run:
        log("  dry-run: skip network")
        return False

    context, dw_status = gather_context(row, owner_repo)
    if not api_key:
        log("  ERROR: OPENROUTER_API_KEY missing")
        row["研判状态"] = dw_status if dw_status == "索引缺失" else "未研判"
        row["研判时间"] = now_shanghai()
        row["DeepWiki"] = f"https://deepwiki.com/{owner_repo}"
        row["schemaVersion"] = 2
        row["研判来源"] = "openrouter+deepwiki"
        return True

    fields = openrouter_complete(
        api_key, SYSTEM_PROMPT, build_user_prompt(row, owner_repo, context)
    )
    if not fields:
        row["研判状态"] = "索引缺失" if dw_status == "索引缺失" else "未研判"
        row["研判时间"] = now_shanghai()
        row["DeepWiki"] = f"https://deepwiki.com/{owner_repo}"
        row["搭建难度"] = row.get("搭建难度") or "未知"
        row["研判来源"] = "openrouter+deepwiki"
        row["schemaVersion"] = 2
        row["研判摘要"] = row.get("研判摘要") or "OpenRouter 未能生成有效 JSON。"
        return True

    merge_v2(row, fields, dw_status, owner_repo)
    if dw_status == "索引缺失" and row.get("研判状态") == "已研判":
        # README fallback still produced guidance — keep 已研判 but note in 摘要
        pass
    log(f"  done 难度={row.get('搭建难度')} 状态={row.get('研判状态')}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Triage AI Web assets (DeepWiki + OpenRouter)")
    ap.add_argument("--keys", default="", help="Comma-separated 去重键")
    ap.add_argument("--limit", type=int, default=3, help="Max assets (cap 10)")
    ap.add_argument("--force", action="store_true", help="Re-triage even if 已研判")
    ap.add_argument("--dry-run", action="store_true", help="Select targets only, no network write")
    args = ap.parse_args()

    limit = max(1, min(int(args.limit), 10))
    keys = [k.strip() for k in args.keys.split(",") if k.strip()] or None

    api_key = os.environ.get("OPENROUTER_API_KEY") or ""
    # Never print the key. Mask for Actions if present.
    if api_key and os.environ.get("GITHUB_ACTIONS"):
        print(f"::add-mask::{api_key}", flush=True)

    rows: list[dict] = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    targets = select_targets(rows, keys, limit, args.force)
    log(f"selected {len(targets)} / limit {limit}")
    if not targets:
        log("nothing to do")
        return 0

    changed = False
    for row in targets:
        if triage_one(row, api_key if not args.dry_run else None, args.dry_run):
            changed = True

    if args.dry_run:
        log("dry-run complete (no write)")
        return 0

    if changed:
        write_json(DATA_PATH, rows)
        update_config_timestamp()
        log(f"wrote {DATA_PATH.relative_to(ROOT)} and updated config.json")
    else:
        log("no changes")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"fatal: {e}", file=sys.stderr)
        raise SystemExit(1)
