import json

import pytest
from botocore.exceptions import ClientError

import history
from history import ConversationStore
from lambda_app import handle
from tests.conftest import NEED_MORE_INFO, READY, FakeBedrock, tool_response

MODEL_ID = "jp.anthropic.claude-sonnet-4-6"
REPO = "Nahaq789/pob"
THREAD = "1727770000.123456"


def call(store, bedrock, text, message_ts=None, **overrides):
    event = {"message": text, "thread_ts": THREAD, "repo": REPO}
    if message_ts:
        event["message_ts"] = message_ts
    return handle(event | overrides, store=store, bedrock=bedrock, model_id=MODEL_ID)


def test_ask_then_ready(store):
    bedrock = FakeBedrock(tool_response(NEED_MORE_INFO), tool_response(READY))

    first = call(store, bedrock, "エラーメッセージ直して", "1.0")
    assert first["status"] == "need_more_info"
    assert first["repo"] == REPO
    assert first["thread_ts"] == THREAD

    second = call(store, bedrock, "パスワード誤りのとき。日本語にしたい", "2.0")
    assert second["status"] == "ready"
    assert second["issue"]["title"] == READY["issue"]["title"]

    # 2 回目は 1 回目の発言と結果を含めて Bedrock に送る
    sent = bedrock.requests[1]["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    assert "リポジトリ: Nahaq789/pob" in sent[0]["content"][0]["text"]
    assert json.loads(sent[1]["content"][0]["text"])["status"] == "need_more_info"
    assert sent[2]["content"][0]["text"] == "パスワード誤りのとき。日本語にしたい"

    saved = store.load(THREAD)
    assert len(saved.messages) == 4
    assert saved.version == 2


def test_resent_message_returns_previous_result_without_calling_bedrock(store):
    bedrock = FakeBedrock(tool_response(READY))
    first = call(store, bedrock, "直して", "1.0")
    again = call(store, bedrock, "直して", "1.0")
    assert again == first
    assert len(bedrock.requests) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"message": ""},
        {"message": "x" * 4001},
        {"thread_ts": ""},
        {"repo": "pob"},
        {"message_ts": 123},
    ],
)
def test_invalid_request(store, overrides):
    bedrock = FakeBedrock()
    result = call(store, bedrock, "直して", **overrides)
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_request"
    assert bedrock.requests == []


def test_invalid_model_output_is_not_saved(store):
    bedrock = FakeBedrock(tool_response({"status": "ready", "questions": []}))
    result = call(store, bedrock, "直して")
    assert result["error"]["code"] == "invalid_model_output"
    assert store.load(THREAD).version == 0


def test_bedrock_access_denied(store):
    denied = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "denied"}}, "Converse")
    result = call(store, FakeBedrock(denied), "直して")
    assert result["error"]["code"] == "bedrock_access_denied"


def test_other_bedrock_errors_are_raised(store):
    throttled = ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse")
    with pytest.raises(ClientError):
        call(store, FakeBedrock(throttled), "直して")


def test_concurrent_update_is_conflict(table):
    store = ConversationStore(table)
    call(store, FakeBedrock(tool_response(NEED_MORE_INFO)), "直して", "1.0")

    # 読み込みの直後に、別の呼び出しが同じスレッドを更新した状況を作る
    stale = store.load(THREAD)
    call(store, FakeBedrock(tool_response(READY)), "回答A", "2.0")

    with pytest.raises(history.ConflictError):
        store.save(stale, repo=REPO, new_messages=[], message_ts="3.0", result=READY)


def test_old_messages_are_trimmed_from_user(store, monkeypatch):
    monkeypatch.setattr(history, "MAX_STORED_MESSAGES", 4)
    bedrock = FakeBedrock(*[tool_response(NEED_MORE_INFO) for _ in range(3)])
    for i in range(3):
        call(store, bedrock, f"発言{i}", str(i))

    saved = store.load(THREAD)
    assert [m.role for m in saved.messages] == ["user", "assistant", "user", "assistant"]
    assert saved.messages[0].text == "発言1"


def test_tracing_with_real_langfuse_client(store):
    """Langfuse の API の呼び方が実際の SDK と合っていることを確認する (送信はしない)"""
    from langfuse import Langfuse

    tracer = Langfuse(
        public_key="pk-lf-test",
        secret_key="sk-lf-test",
        base_url="http://localhost:1",
        tracing_enabled=False,
    )
    bedrock = FakeBedrock(tool_response(READY), tool_response({"status": "x", "questions": []}))
    ok = handle({"message": "直して", "thread_ts": THREAD, "repo": REPO}, store=store, bedrock=bedrock, model_id=MODEL_ID, tracer=tracer)
    ng = handle({"message": "続き", "thread_ts": THREAD, "repo": REPO}, store=store, bedrock=bedrock, model_id=MODEL_ID, tracer=tracer)
    tracer.flush()
    assert ok["status"] == "ready"
    assert ng["error"]["code"] == "invalid_model_output"
