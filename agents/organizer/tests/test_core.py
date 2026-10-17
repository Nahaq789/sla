import copy

import pytest

import core
from core import InvalidModelOutputError, Message
from tests.conftest import NEED_MORE_INFO, READY, FakeBedrock, tool_response

MODEL_ID = "jp.anthropic.claude-sonnet-4-6"


def organize(tool_input, messages=None):
    bedrock = FakeBedrock(tool_response(tool_input))
    messages = messages or [Message("user", core.first_user_text("Nahaq789/pob", "直して"))]
    return core.organize(messages, bedrock=bedrock, model_id=MODEL_ID), bedrock


def test_ready():
    result, _ = organize(READY)
    assert result == READY | {"issue": READY["issue"]}


def test_need_more_info_has_no_issue():
    result, _ = organize(NEED_MORE_INFO)
    assert result == {"status": "need_more_info", "issue": None, "questions": ["どのエラーメッセージですか？"]}


def test_request_forces_tool_and_enables_prompt_cache():
    _, bedrock = organize(READY)
    request = bedrock.requests[0]
    assert request["modelId"] == MODEL_ID
    assert request["toolConfig"]["toolChoice"] == {"tool": {"name": "submit_result"}}
    assert {"cachePoint": {"type": "default"}} in request["system"]
    assert {"cachePoint": {"type": "default"}} in request["toolConfig"]["tools"]


def test_history_is_sent_in_order():
    messages = [
        Message("user", "最初の依頼"),
        Message("assistant", core.assistant_text({"status": "need_more_info", "issue": None, "questions": ["?"]})),
        Message("user", "回答"),
    ]
    _, bedrock = organize(READY, messages)
    sent = bedrock.requests[0]["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    assert sent[2]["content"] == [{"text": "回答"}]


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [Message("assistant", "x")],
        [Message("user", "a"), Message("user", "b")],
        [Message("user", "a"), Message("assistant", "b")],
    ],
)
def test_rejects_invalid_conversation(messages):
    with pytest.raises(ValueError):
        core.organize(messages, bedrock=FakeBedrock(), model_id=MODEL_ID)


def test_unknown_labels_are_dropped():
    tool_input = copy.deepcopy(READY)
    tool_input["issue"]["labels"] = ["enhancement", "urgent"]
    result, _ = organize(tool_input)
    assert result["issue"]["labels"] == ["enhancement"]


@pytest.mark.parametrize(
    "tool_input",
    [
        {"status": "done", "questions": []},
        {"status": "ready", "questions": []},
        {"status": "need_more_info", "questions": []},
        READY | {"issue": READY["issue"] | {"tasks": []}},
        READY | {"issue": READY["issue"] | {"title": " "}},
    ],
)
def test_invalid_model_output(tool_input):
    with pytest.raises(InvalidModelOutputError):
        organize(tool_input)


def test_missing_tool_use():
    bedrock = FakeBedrock({"output": {"message": {"content": [{"text": "hi"}]}}, "stopReason": "end_turn"})
    with pytest.raises(InvalidModelOutputError):
        core.organize([Message("user", "a")], bedrock=bedrock, model_id=MODEL_ID)
