#!/usr/bin/env bash
# Ask local OpenCode for publicly documented direct download URLs.
# Args: product vendor site_url download_page_url
# Prints JSON array of URL strings on stdout. Exit non-zero on failure.
set -euo pipefail

PRODUCT="${1:-}"
VENDOR="${2:-}"
SITE="${3:-}"
DLPAGE="${4:-}"

OPENCODE_BIN="${OPENCODE_BIN:-}"
if [[ -z "$OPENCODE_BIN" ]]; then
  if [[ -x /home/box/.opencode/bin/opencode ]]; then
    OPENCODE_BIN=/home/box/.opencode/bin/opencode
  elif command -v opencode >/dev/null 2>&1; then
    OPENCODE_BIN="$(command -v opencode)"
  else
    echo "opencode not found" >&2
    exit 2
  fi
fi

PROMPT=$(cat <<EOF
You are helping catalog official software downloads for an asset inventory.
Product: ${PRODUCT}
Vendor: ${VENDOR}
Official site: ${SITE}
Download page (if any): ${DLPAGE}

Task: list ONLY publicly documented direct download URLs (http/https to packages such as .exe .msi .dmg .zip .tar.gz .deb .rpm .iso, or GitHub release asset URLs, or a single "docker pull image:tag" string). 
Rules:
- Do NOT invent URLs. If unsure, return [].
- Prefer vendor official / GitHub release assets.
- No cracked / third-party mirror / Baidu pan links.
- Output ONLY a JSON array of strings, no markdown, no explanation.
EOF
)

# Prefer non-interactive; --format json if supported — we parse loose stdout either way.
set +e
OUT="$("$OPENCODE_BIN" run --auto --format default "$PROMPT" 2>/tmp/opencode-find-direct.err)"
RC=$?
set -e
if [[ $RC -ne 0 ]]; then
  cat /tmp/opencode-find-direct.err >&2 || true
  exit "$RC"
fi
printf '%s\n' "$OUT"
