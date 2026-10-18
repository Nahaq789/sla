#!/usr/bin/env bash
# Quick Tunnel を起動し、その URL を WEBHOOK_URL にして n8n を起動する。
# トンネルが動いていれば同じ URL を使い続ける (止まっていた場合だけ URL が変わる)。
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
compose=(docker compose -f "${root}/n8n/docker-compose.yml")
env_file="${root}/n8n/.env"

"${compose[@]}" up -d tunnel

url=""
for _ in $(seq 1 30); do
  url="$("${compose[@]}" logs tunnel 2>/dev/null | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -n 1 || true)"
  [[ -n "${url}" ]] && break
  sleep 1
done
if [[ -z "${url}" ]]; then
  echo "トンネルの URL を取得できませんでした。'just n8n-logs tunnel' でログを確認してください" >&2
  exit 1
fi

previous="$(sed -n 's/^WEBHOOK_URL=//p' "${env_file}" 2>/dev/null || true)"
echo "WEBHOOK_URL=${url}/" > "${env_file}"

# WEBHOOK_URL が変わっていれば compose が n8n を作り直す
"${compose[@]}" up -d n8n

echo
echo "エディタ:   http://localhost:5678"
echo "公開 URL:   ${url}/"
if [[ "${previous}" != "${url}/" ]]; then
  echo
  echo "公開 URL が変わりました。Slack App の Event Subscriptions / Interactivity の Request URL を更新してください。"
fi
