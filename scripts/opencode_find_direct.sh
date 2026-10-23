#!/usr/bin/env bash
# Ask OpenCode (IMKAI DeepSeek by default) for publicly documented direct download URLs.
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

MODEL="${OPENCODE_MODEL:-imkai/DeepSeek-V4-Flash}"
# Load key from secrets file; never echo it
if [[ -z "${IMKAI_API_KEY:-}" ]] && [[ -f /home/box/.config/secrets/imkai_api_key ]]; then
  IMKAI_API_KEY="$(cat /home/box/.config/secrets/imkai_api_key)"
  export IMKAI_API_KEY
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
- Do NOT use any tools, web search, or shell. Answer from known public docs only.
- Output ONLY a JSON array of strings, no markdown, no explanation.
EOF
)

# --auto: non-interactive; --format default: plain text out
OUT="$("$OPENCODE_BIN" run --standalone --auto --agent plan -m "$MODEL" --format default "$PROMPT" 2>/tmp/opencode_find_direct.err)" || {
  echo "opencode run failed: $(head -c 400 /tmp/opencode_find_direct.err)" >&2
  exit 1
}

# Prefer a JSON array in the output
if [[ "$OUT" =~ \[.*\] ]]; then
  # Extract from first [ to last ]
  python3 -c '
import sys, re, json
text = sys.stdin.read()
m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
blob = m.group(1).strip() if m else text
s, e = blob.find("["), blob.rfind("]")
if s < 0 or e <= s:
    print("[]")
    sys.exit(0)
arr = json.loads(blob[s:e+1])
if not isinstance(arr, list):
    print("[]")
    sys.exit(0)
clean = []
for x in arr:
    if isinstance(x, str) and (x.startswith("http") or x.lower().startswith("docker pull ")):
        clean.append(x.strip())
print(json.dumps(clean, ensure_ascii=False))
' <<<"$OUT"
else
  echo "[]"
fi
