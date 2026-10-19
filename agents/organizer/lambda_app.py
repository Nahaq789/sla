"""整理役 Lambda の入口。

入力の検証、部品 (Bedrock・DynamoDB・Langfuse) の組み立て、結果の整形だけを行い、
Issue 案を作るロジックは core.py、会話の保存は history.py に任せる。

入力 (整理する。action は省略可):
    {
      "message": "ユーザーの発言",
      "thread_ts": "Slack スレッドの ts (会話のキー、Langfuse の session_id)",
      "repo": "owner/repo",
      "message_ts": "ユーザー発言の Slack ts (省略可。同じ値で再送されたら前回の結果を返す。ready の案の draft_id になる)"
    }
出力:
    {"status": "ready" | "need_more_info", "repo", "thread_ts", "issue", "questions"}
    ready のときは "draft_id" (message_ts。省略された場合は null) も返す

入力 (保存済みの Issue 案を取り出す。Slack の [作成] ボタン用):
    {"action": "get_issue", "thread_ts": "...", "draft_id": "..."}
出力:
    {"status": "ready", "repo", "thread_ts", "draft_id", "issue"}

失敗時: {"status": "error", "repo", "thread_ts", "error": {"code", "message"}}
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import ExitStack
from typing import Any

import boto3
from botocore.exceptions import ClientError

import core
from history import ConflictError, ConversationStore

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REPO_PATTERN = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
MAX_MESSAGE_LENGTH = 4000

# Lambda の実行環境は使い回されるため、クライアントはモジュールレベルで 1 回だけ作る
_clients: dict[str, Any] = {}


class InvalidRequestError(Exception):
    pass


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    tracer = _langfuse()
    try:
        return handle(
            event,
            store=ConversationStore(_dynamodb_table()),
            bedrock=_bedrock(),
            model_id=os.environ["BEDROCK_MODEL_ID"],
            tracer=tracer,
        )
    finally:
        # Lambda は応答後に停止するため、トレースを送り切ってから返す
        if tracer:
            tracer.flush()


def handle(
    event: dict[str, Any],
    *,
    store: ConversationStore,
    bedrock: Any,
    model_id: str,
    tracer: Any = None,
) -> dict[str, Any]:
    """1 回分の依頼を処理する (テストから部品を差し替えて呼べるよう、入口と分けている)"""
    thread_ts = event.get("thread_ts") if isinstance(event, dict) else None
    repo = event.get("repo") if isinstance(event, dict) else None

    action = event.get("action", "organize") if isinstance(event, dict) else "organize"
    if action == "get_issue":
        return _get_issue(event, store)
    if action != "organize":
        return _error(repo, thread_ts, "invalid_request", f"action が不正です: {action}")

    try:
        message, thread_ts, repo, message_ts = _parse(event)
    except InvalidRequestError as e:
        return _error(repo, thread_ts, "invalid_request", str(e))

    with ExitStack() as stack:
        span = None
        if tracer:
            from langfuse import propagate_attributes

            stack.enter_context(
                propagate_attributes(
                    session_id=thread_ts,
                    tags=[repo],
                    metadata={"repo": repo},
                    trace_name="organizer",
                )
            )
            span = stack.enter_context(
                tracer.start_as_current_observation(as_type="span", name="organizer", input=event)
            )

        result = _process(message, thread_ts, repo, message_ts, store, bedrock, model_id, tracer)
        if span:
            if result["status"] == "error":
                span.update(output=result, level="ERROR", status_message=result["error"]["code"])
            else:
                span.update(output=result)
        return result


def _process(message, thread_ts, repo, message_ts, store, bedrock, model_id, tracer) -> dict[str, Any]:
    conversation = store.load(thread_ts)

    # Slack の再送などで同じ発言が届いた場合は、Bedrock を呼ばずに前回の結果を返す
    if message_ts and message_ts == conversation.last_message_ts and conversation.last_result:
        logger.info("同じ発言の再送のため前回の結果を返します: thread_ts=%s", thread_ts)
        return _response(repo, thread_ts, message_ts, conversation.last_result)

    user_text = core.first_user_text(repo, message) if not conversation.messages else message
    user_message = core.Message(role="user", text=user_text)

    try:
        result = core.organize(
            conversation.messages + [user_message], bedrock=bedrock, model_id=model_id, tracer=tracer
        )
    except core.InvalidModelOutputError as e:
        logger.exception("モデルの出力が不正です")
        return _error(repo, thread_ts, "invalid_model_output", str(e))
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code == "AccessDeniedException":
            # 予算超過で Budgets アクションが Deny ポリシーを付けた場合もここに来る
            logger.exception("Bedrock の呼び出しが拒否されました")
            return _error(repo, thread_ts, "bedrock_access_denied", "Bedrock の呼び出しが拒否されました (予算超過の可能性があります)")
        raise

    try:
        store.save(
            conversation,
            repo=repo,
            new_messages=[user_message, core.Message(role="assistant", text=core.assistant_text(result))],
            message_ts=message_ts,
            result=result,
        )
    except ConflictError:
        logger.warning("同じスレッドが同時に処理されました: thread_ts=%s", thread_ts)
        return _error(repo, thread_ts, "conflict", "同じスレッドの依頼が同時に処理されました。もう一度送ってください")

    return _response(repo, thread_ts, message_ts, result)


def _response(repo: str, thread_ts: str, message_ts: str | None, result: dict[str, Any]) -> dict[str, Any]:
    response = {"repo": repo, "thread_ts": thread_ts, **result}
    if result["status"] == "ready":
        response["draft_id"] = message_ts
    return response


def _get_issue(event: dict[str, Any], store: ConversationStore) -> dict[str, Any]:
    """保存済みの Issue 案を取り出す (Bedrock は呼ばない)"""
    thread_ts = event.get("thread_ts")
    draft_id = event.get("draft_id")
    if not isinstance(thread_ts, str) or not thread_ts.strip():
        return _error(None, thread_ts, "invalid_request", "thread_ts は空でない文字列である必要があります")
    if not isinstance(draft_id, str) or not draft_id.strip():
        return _error(None, thread_ts, "invalid_request", "draft_id は空でない文字列である必要があります")

    conversation = store.load(thread_ts)
    issue = conversation.drafts.get(draft_id)
    if issue is None:
        return _error(conversation.repo, thread_ts, "draft_not_found", "指定された Issue 案が見つかりません (30 日以上前の案や、1 スレッド 10 件を超えた古い案は削除されます)")

    return {
        "status": "ready",
        "repo": conversation.repo,
        "thread_ts": thread_ts,
        "draft_id": draft_id,
        "issue": issue,
    }


def _parse(event: Any) -> tuple[str, str, str, str | None]:
    if not isinstance(event, dict):
        raise InvalidRequestError("入力は JSON オブジェクトである必要があります")

    message = event.get("message")
    thread_ts = event.get("thread_ts")
    repo = event.get("repo")
    message_ts = event.get("message_ts")

    if not isinstance(message, str) or not message.strip():
        raise InvalidRequestError("message は空でない文字列である必要があります")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise InvalidRequestError(f"message は {MAX_MESSAGE_LENGTH} 文字以内にしてください")
    if not isinstance(thread_ts, str) or not thread_ts.strip():
        raise InvalidRequestError("thread_ts は空でない文字列である必要があります")
    if not isinstance(repo, str) or not REPO_PATTERN.match(repo):
        raise InvalidRequestError('repo は "owner/repo" 形式である必要があります')
    if message_ts is not None and (not isinstance(message_ts, str) or not message_ts.strip()):
        raise InvalidRequestError("message_ts は空でない文字列である必要があります")

    return message.strip(), thread_ts, repo, message_ts


def _error(repo: Any, thread_ts: Any, code: str, message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "repo": repo,
        "thread_ts": thread_ts,
        "error": {"code": code, "message": message},
    }


def _bedrock() -> Any:
    if "bedrock" not in _clients:
        _clients["bedrock"] = boto3.client("bedrock-runtime")
    return _clients["bedrock"]


def _dynamodb_table() -> Any:
    if "table" not in _clients:
        _clients["table"] = boto3.resource("dynamodb").Table(os.environ["CONVERSATIONS_TABLE_NAME"])
    return _clients["table"]


def _langfuse() -> Any:
    """Langfuse クライアント。鍵が未設定 (ダミー値) か取得に失敗した場合は None (トレースなしで動く)"""
    if "langfuse" in _clients:
        return _clients["langfuse"]

    client = None
    try:
        ssm = boto3.client("ssm")
        public_key = _ssm_value(ssm, os.environ["LANGFUSE_PUBLIC_KEY_PARAM"])
        secret_key = _ssm_value(ssm, os.environ["LANGFUSE_SECRET_KEY_PARAM"])
        if public_key.startswith("pk-lf-") and secret_key.startswith("sk-lf-"):
            from langfuse import Langfuse

            client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                base_url=os.environ["LANGFUSE_HOST"],
            )
        else:
            logger.warning("Langfuse の鍵が未設定のため、トレースを送りません")
    except Exception:
        logger.exception("Langfuse の初期化に失敗したため、トレースを送りません")

    _clients["langfuse"] = client
    return client


def _ssm_value(ssm: Any, name: str) -> str:
    return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
