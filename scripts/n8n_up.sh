#!/usr/bin/env bash
# Quick Tunnel を起動し、その URL を WEBHOOK_URL にして n8n を起動する。
# トンネルが動いていれば同じ URL を使い続ける (止まっていた場合だけ URL が変わる)。
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
compose=(docker compose -f "${root}/n8n/docker-compose.yml")
env_file="${root}/n8n/.env"

"${compose[@]}" up -d tunnel

# ログは再起動しても残るため、今回の起動以降のログだけから URL を探す (前回の URL を拾わないように)
started_at="$(docker inspect --format '{{.State.StartedAt}}' "$("${compose[@]}" ps -q tunnel)")"

url=""
for _ in $(seq 1 30); do
  url="$("${compose[@]}" logs --since "${started_at}" tunnel 2>/dev/null | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -n 1 || true)"
  [[ -n "${url}" ]] && break
  sleep 1
done
if [[ -z "${url}" ]]; then
  echo "トンネルの URL を取得できませんでした。'just n8n-logs tunnel' でログを確認してください" >&2
  exit 1
fi

previous="$(sed -n 's/^WEBHOOK_URL=//p' "${env_file}" 2>/dev/null || true)"
# WEBHOOK_URL の行だけを書き換え、他の行 (SLACK_SIGNING_SECRET など) は残す
touch "${env_file}"
chmod 600 "${env_file}"
{ grep -v '^WEBHOOK_URL=' "${env_file}" || true; echo "WEBHOOK_URL=${url}/"; } > "${env_file}.tmp"
mv "${env_file}.tmp" "${env_file}"

# WEBHOOK_URL が変わっていれば compose が n8n を作り直す
"${compose[@]}" up -d n8n

echo
echo "エディタ:   http://localhost:5678"
echo "公開 URL:   ${url}/"
if [[ "${previous}" != "${url}/" ]]; then
  echo
  echo "公開 URL が変わりました。Slack App の Event Subscriptions / Interactivity の Request URL を更新してください。"
fi
