"""会話の履歴を DynamoDB に読み書きする。

1 スレッド (thread_ts) = 1 アイテム。整理役の 1 回の呼び出しごとに、
ユーザー発言と整理役の結果を 1 組ずつ追記していく。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from core import Message

# 古い会話は TTL で自動削除する
TTL_SECONDS = 30 * 24 * 60 * 60

# 1 スレッドに保存する発言数の上限 (DynamoDB のアイテム上限 400KB を超えないようにする)
MAX_STORED_MESSAGES = 40


class ConflictError(Exception):
    """同じスレッドの会話が、読み込み後に別の呼び出しで更新されていた"""


@dataclass
class Conversation:
    thread_ts: str
    messages: list[Message] = field(default_factory=list)
    # 楽観ロック用。保存のたびに 1 増える。0 は未保存 (新規の会話)
    version: int = 0
    # 最後に処理したユーザー発言の Slack ts と、そのときの結果 (再送時に同じ結果を返すため)
    last_message_ts: str | None = None
    last_result: dict[str, Any] | None = None


class ConversationStore:
    def __init__(self, table: Any):
        """table は boto3 の DynamoDB Table リソース"""
        self._table = table

    def load(self, thread_ts: str) -> Conversation:
        item = self._table.get_item(Key={"thread_ts": thread_ts}, ConsistentRead=True).get("Item")
        if not item:
            return Conversation(thread_ts=thread_ts)
        return Conversation(
            thread_ts=thread_ts,
            messages=[Message(**m) for m in json.loads(item["messages"])],
            version=int(item["version"]),
            last_message_ts=item.get("last_message_ts"),
            last_result=json.loads(item["last_result"]) if "last_result" in item else None,
        )

    def save(
        self,
        conversation: Conversation,
        *,
        repo: str,
        new_messages: list[Message],
        message_ts: str | None,
        result: dict[str, Any],
    ) -> None:
        """会話に発言を追記して保存する。読み込み後に別の呼び出しで更新されていたら ConflictError"""
        messages = conversation.messages + new_messages
        if len(messages) > MAX_STORED_MESSAGES:
            # user から始まる状態を保つため、偶数個ずつ古いものから捨てる
            drop = len(messages) - MAX_STORED_MESSAGES
            messages = messages[drop + drop % 2 :]

        item: dict[str, Any] = {
            "thread_ts": conversation.thread_ts,
            "repo": repo,
            "messages": json.dumps([m.__dict__ for m in messages], ensure_ascii=False),
            "version": conversation.version + 1,
            "last_result": json.dumps(result, ensure_ascii=False),
            "updated_at": int(time.time()),
            "expires_at": int(time.time()) + TTL_SECONDS,
        }
        if message_ts:
            item["last_message_ts"] = message_ts

        if conversation.version == 0:
            condition = {"ConditionExpression": "attribute_not_exists(thread_ts)"}
        else:
            condition = {
                "ConditionExpression": "version = :expected",
                "ExpressionAttributeValues": {":expected": conversation.version},
            }

        try:
            self._table.put_item(Item=item, **condition)
        except self._table.meta.client.exceptions.ConditionalCheckFailedException as e:
            raise ConflictError(conversation.thread_ts) from e
