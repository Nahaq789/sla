"""Issue 案を作るロジック本体。

Bedrock の Converse API を 1 回呼び、会話から Issue 案 (または質問) を作る。
DynamoDB や Lambda のことは知らない (会話の保存は history.py、入口は lambda_app.py)。
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")

TOOL_NAME = "submit_result"

LABELS = ["bug", "enhancement", "documentation", "refactor", "test", "chore"]

# モデルに返させる結果の形。Converse の toolChoice でこのツールの呼び出しを強制し、JSON で受け取る
RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ready", "need_more_info"]},
        "issue": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "background": {"type": "string"},
                "tasks": {"type": "array", "items": {"type": "string"}},
                "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                "labels": {"type": "array", "items": {"type": "string", "enum": LABELS}},
            },
            "required": ["title", "background", "tasks", "acceptance_criteria", "labels"],
        },
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "questions"],
}

MAX_TOKENS = 4096
TEMPERATURE = 0.2


class InvalidModelOutputError(Exception):
    """モデルの出力が期待する形になっていない"""


@dataclass(frozen=True)
class Message:
    """会話の 1 発言。role は "user" か "assistant"、text はモデルに渡す本文"""

    role: str
    text: str


def first_user_text(repo: str, message: str) -> str:
    """最初のユーザー発言。リポジトリ名を含める (システムプロンプトはキャッシュのため固定にする)"""
    return f"リポジトリ: {repo}\n\n依頼:\n{message}"


def assistant_text(result: dict[str, Any]) -> str:
    """整理役の結果を、次の呼び出しで会話に含める本文にする"""
    return json.dumps(result, ensure_ascii=False)


def organize(
    messages: list[Message],
    *,
    bedrock: Any,
    model_id: str,
    tracer: Any = None,
) -> dict[str, Any]:
    """会話から Issue 案を作る。

    messages は user から始まり user で終わり、user と assistant が交互に並ぶこと。
    戻り値は {"status", "issue"(ready のときのみ), "questions"}。
    tracer には Langfuse クライアントを渡す (None ならトレースしない)。
    """
    _check_alternation(messages)

    request = {
        "modelId": model_id,
        # cachePoint より前 (システムプロンプト、ツール定義) をプロンプトキャッシュの対象にする
        "system": [{"text": SYSTEM_PROMPT}, {"cachePoint": {"type": "default"}}],
        "messages": [{"role": m.role, "content": [{"text": m.text}]} for m in messages],
        "inferenceConfig": {"maxTokens": MAX_TOKENS, "temperature": TEMPERATURE},
        "toolConfig": {
            "tools": [
                {
                    "toolSpec": {
                        "name": TOOL_NAME,
                        "description": "整理した結果 (Issue 案または質問) を返す",
                        "inputSchema": {"json": RESULT_SCHEMA},
                    }
                },
                {"cachePoint": {"type": "default"}},
            ],
            "toolChoice": {"tool": {"name": TOOL_NAME}},
        },
    }

    generation_context = (
        tracer.start_as_current_observation(
            as_type="generation",
            name="bedrock-converse",
            model=model_id,
            input=[{"role": m.role, "content": m.text} for m in messages],
            model_parameters={"maxTokens": MAX_TOKENS, "temperature": TEMPERATURE},
        )
        if tracer
        else nullcontext(None)
    )

    with generation_context as generation:
        response = bedrock.converse(**request)
        tool_input = _extract_tool_input(response)
        if generation:
            usage = response.get("usage", {})
            generation.update(
                output=tool_input,
                usage_details={
                    "input": usage.get("inputTokens", 0),
                    "output": usage.get("outputTokens", 0),
                    "cache_read_input_tokens": usage.get("cacheReadInputTokens", 0),
                    "cache_creation_input_tokens": usage.get("cacheWriteInputTokens", 0),
                },
            )

    return _normalize(tool_input)


def _check_alternation(messages: list[Message]) -> None:
    if not messages or messages[-1].role != "user":
        raise ValueError("会話は user の発言で終わる必要があります")
    for i, message in enumerate(messages):
        expected = "user" if i % 2 == 0 else "assistant"
        if message.role != expected:
            raise ValueError("会話は user から始まり、user と assistant が交互に並ぶ必要があります")


def _extract_tool_input(response: dict[str, Any]) -> dict[str, Any]:
    content = response.get("output", {}).get("message", {}).get("content", [])
    for block in content:
        tool_use = block.get("toolUse")
        if tool_use and tool_use.get("name") == TOOL_NAME:
            return tool_use.get("input") or {}
    raise InvalidModelOutputError(
        f"{TOOL_NAME} の呼び出しがありません (stopReason={response.get('stopReason')})"
    )


def _normalize(tool_input: dict[str, Any]) -> dict[str, Any]:
    """モデルの出力を検証し、n8n に返す形に揃える"""
    status = tool_input.get("status")
    questions = _string_list(tool_input.get("questions", []), "questions")

    if status == "need_more_info":
        if not questions:
            raise InvalidModelOutputError("need_more_info なのに questions が空です")
        return {"status": status, "issue": None, "questions": questions}

    if status == "ready":
        issue = tool_input.get("issue")
        if not isinstance(issue, dict):
            raise InvalidModelOutputError("ready なのに issue がありません")
        title = issue.get("title")
        background = issue.get("background")
        if not isinstance(title, str) or not title.strip():
            raise InvalidModelOutputError("issue.title が空です")
        if not isinstance(background, str):
            raise InvalidModelOutputError("issue.background が文字列ではありません")
        tasks = _string_list(issue.get("tasks"), "issue.tasks")
        criteria = _string_list(issue.get("acceptance_criteria"), "issue.acceptance_criteria")
        if not tasks or not criteria:
            raise InvalidModelOutputError("issue.tasks と issue.acceptance_criteria は 1 件以上必要です")
        labels = [label for label in _string_list(issue.get("labels", []), "issue.labels") if label in LABELS]
        return {
            "status": status,
            "issue": {
                "title": title.strip(),
                "background": background,
                "tasks": tasks,
                "acceptance_criteria": criteria,
                "labels": labels,
            },
            "questions": [],
        }

    raise InvalidModelOutputError(f"status が不正です: {status!r}")


def _string_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise InvalidModelOutputError(f"{field} は文字列の配列である必要があります")
    return [v for v in value if v.strip()]
