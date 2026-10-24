"""実装役 (AgentCore Runtime) の入口。

呼ばれたら入力を検証してすぐに "accepted" を返し、作業は裏のスレッドで続ける。
終わったら結果を callback_url (n8n の Wait ノードの再開用 URL) に POST する。
作業中は add_async_task で登録しておき、/ping が HealthyBusy を返すようにする
(Healthy のまま 15 分経つとセッションが止められるため)。

今は骨組みで、作業の代わりに数秒待つだけ。

入力:
    {
      "callback_url": "作業結果の送り先 (n8n の $execution.resumeUrl)",
      "repo": "owner/repo",
      "issue_number": 12,
      "thread_ts": "Slack スレッドの ts (n8n が結果をどのスレッドに返すかに使う)"
    }
すぐに返す応答:
    {"status": "accepted", "repo", "issue_number", "thread_ts"}
    入力が不正なら {"status": "error", "error": {"code": "invalid_request", "message"}}
    (この場合は callback_url に何も送らない)
callback_url に送る結果:
    {"status": "done" | "error", "repo", "issue_number", "thread_ts", "summary" | "error"}
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from callback import post_result

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REPO_PATTERN = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
CALLBACK_URL_PATTERN = re.compile(r"^https?://\S+$")

app = BedrockAgentCoreApp()


class InvalidRequestError(Exception):
    pass


@app.entrypoint
def invoke(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        job = parse_payload(payload)
    except InvalidRequestError as e:
        logger.warning("invalid request: %s", e)
        return {"status": "error", "error": {"code": "invalid_request", "message": str(e)}}

    task_id = app.add_async_task("implement", {"repo": job["repo"], "issue_number": job["issue_number"]})
    threading.Thread(target=run_job, args=(job, task_id), daemon=True).start()
    return {"status": "accepted", **_job_ids(job)}


def parse_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InvalidRequestError("payload must be a JSON object")

    callback_url = payload.get("callback_url")
    if not isinstance(callback_url, str) or not CALLBACK_URL_PATTERN.match(callback_url):
        raise InvalidRequestError("callback_url must be an http(s) URL")

    repo = payload.get("repo")
    if not isinstance(repo, str) or not REPO_PATTERN.match(repo):
        raise InvalidRequestError("repo must be in the form owner/repo")

    issue_number = payload.get("issue_number")
    # bool は int のサブクラスなので明示的に除く
    if not isinstance(issue_number, int) or isinstance(issue_number, bool) or issue_number < 1:
        raise InvalidRequestError("issue_number must be a positive integer")

    thread_ts = payload.get("thread_ts")
    if not isinstance(thread_ts, str) or not thread_ts:
        raise InvalidRequestError("thread_ts is required")

    return {
        "callback_url": callback_url,
        "repo": repo,
        "issue_number": issue_number,
        "thread_ts": thread_ts,
    }


def run_job(job: dict[str, Any], task_id: int) -> None:
    try:
        try:
            result = {"status": "done", **_job_ids(job), "summary": do_work(job)}
        except Exception as e:  # noqa: BLE001 - どんな失敗でも n8n に知らせる
            logger.exception("job failed")
            result = {
                "status": "error",
                **_job_ids(job),
                "error": {"code": "internal_error", "message": str(e)},
            }
        post_result(job["callback_url"], result)
    finally:
        app.complete_async_task(task_id)


def do_work(job: dict[str, Any]) -> str:
    # 骨組み: 本物の作業 (clone → 修正 → テスト → Draft PR) の代わりに待つだけ
    seconds = float(os.environ.get("SKELETON_SLEEP_SECONDS", "5"))
    time.sleep(seconds)
    return f"(骨組み) {job['repo']}#{job['issue_number']} の作業を {seconds:g} 秒で終えたことにしました"


def _job_ids(job: dict[str, Any]) -> dict[str, Any]:
    return {"repo": job["repo"], "issue_number": job["issue_number"], "thread_ts": job["thread_ts"]}


if __name__ == "__main__":
    app.run()
