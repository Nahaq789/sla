import os
from typing import Any

import boto3
import pytest
from moto import mock_aws

from history import ConversationStore

TABLE_NAME = "slack-issue-agent-conversations"


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    # 実際の AWS に接続しないよう、ダミーの認証情報を使う
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.delenv("AWS_PROFILE", raising=False)


@pytest.fixture
def table():
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "thread_ts", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "thread_ts", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield table


@pytest.fixture
def store(table):
    return ConversationStore(table)


def tool_response(tool_input: dict[str, Any]) -> dict[str, Any]:
    """Bedrock Converse の、submit_result ツールを呼んだときの応答"""
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {"toolUse": {"toolUseId": "t1", "name": "submit_result", "input": tool_input}}
                ],
            }
        },
        "stopReason": "tool_use",
        "usage": {"inputTokens": 100, "outputTokens": 50, "totalTokens": 150},
    }


READY = {
    "status": "ready",
    "issue": {
        "title": "ログイン画面のエラーメッセージを日本語化",
        "background": "パスワード誤り時のメッセージが英語のまま表示されている。",
        "tasks": ["エラーメッセージの文言を日本語に置き換える"],
        "acceptance_criteria": ["パスワード誤り時に日本語のメッセージが表示されること"],
        "labels": ["enhancement"],
    },
    "questions": [],
}

NEED_MORE_INFO = {
    "status": "need_more_info",
    "questions": ["どのエラーメッセージですか？"],
}


class FakeBedrock:
    """呼ばれた順に、用意した応答を返す Bedrock クライアントの代わり"""

    def __init__(self, *responses: dict[str, Any]):
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def converse(self, **request):
        self.requests.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response
