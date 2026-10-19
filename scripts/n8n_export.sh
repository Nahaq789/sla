#!/usr/bin/env bash
# n8n のワークフローを n8n/workflows/<ワークフロー名>.json に書き出す。
# - 認証情報の値は含まれない (名前と ID だけ)
# - pinData (編集画面に固定したテスト用のデータ。Slack の発言本文などが入る) は取り除く
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
compose=(docker compose -f "${root}/n8n/docker-compose.yml")
out="${root}/n8n/workflows"
tmp="/tmp/n8n-export.json"

"${compose[@]}" exec -T n8n n8n export:workflow --all --pretty --output="${tmp}" >/dev/null
"${compose[@]}" exec -T n8n cat "${tmp}" | python3 -I -c '
import json, re, sys
from pathlib import Path

out = Path(sys.argv[1])
for wf in json.load(sys.stdin):
    wf.pop("pinData", None)
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", wf["name"]).strip("-") or wf["id"]
    path = out / f"{name}.json"
    path.write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n")
    print(f"書き出し: {path.relative_to(out.parent.parent)}")
' "${out}"
"${compose[@]}" exec -T n8n rm -f "${tmp}"
