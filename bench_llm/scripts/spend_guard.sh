#!/usr/bin/env bash
# Stop all Silsila vLLM apps on Modal once their GPU spend since START reaches LIMIT dollars.
# Usage (from bench_llm/):  LIMIT=120 nohup bash scripts/spend_guard.sh > runs/logs/spend_guard.log 2>&1 &
LIMIT="${LIMIT:-120}"
START="${START:-2026-11-14}"
cd "$(dirname "$0")/.." || exit 1

# The report covers complete days only, so add today's partial day from "--for today".
spent_now() {
  { timeout 120 uv run modal billing report --start "$START" --json 2>/dev/null
    timeout 120 uv run modal billing report --for today --json 2>/dev/null; } | python3 -c '
import json, sys
dec = json.JSONDecoder(); text = sys.stdin.read().strip(); rows = []; i = 0
try:
    while i < len(text):
        obj, i = dec.raw_decode(text, i)
        rows += obj
        while i < len(text) and text[i].isspace():
            i += 1
except Exception:
    print("?"); sys.exit()
seen = set(); total = 0.0
for r in rows:
    key = json.dumps(r, sort_keys=True)
    if key in seen or not str(r.get("description", "")).startswith("silsila-vllm"):
        continue
    seen.add(key); total += float(r.get("cost", 0))
print(round(total, 2))'
}

while true; do
  spent="$(spent_now)"
  echo "$(date -u +%H:%M) spend=$spent limit=$LIMIT"
  if [ "$spent" != "?" ] && python3 -c "import sys; sys.exit(0 if float(sys.argv[1]) >= float(sys.argv[2]) else 1)" "$spent" "$LIMIT"; then
    echo "LIMIT REACHED: stopping Modal apps and self-hosted runs"
    for a in jais-3-7b jais-3-32b bimedix2-8b llama3-med42-8b k2-think-v2; do
      uv run modal app stop -y "silsila-vllm-$a" >/dev/null 2>&1
    done
    pkill -f "silsila_bench.run --model (jais|bimedix|llama3|k2)"
    exit 0
  fi
  sleep 1200
done
