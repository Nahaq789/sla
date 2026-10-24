import pytest

import app

VALID = {
    "callback_url": "https://example.com/webhook-waiting/1",
    "repo": "owner/repo",
    "issue_number": 12,
    "thread_ts": "1700000000.000100",
}


@pytest.fixture
def posted(monkeypatch):
    calls = []
    monkeypatch.setattr(app, "post_result", lambda url, body: calls.append((url, body)) or True)
    return calls


def test_parse_payload_accepts_valid_input():
    assert app.parse_payload(dict(VALID)) == VALID


@pytest.mark.parametrize(
    "override",
    [
        {"callback_url": "ftp://example.com/x"},
        {"callback_url": None},
        {"repo": "no-slash"},
        {"issue_number": 0},
        {"issue_number": "12"},
        {"issue_number": True},
        {"thread_ts": ""},
    ],
)
def test_parse_payload_rejects_invalid_input(override):
    with pytest.raises(app.InvalidRequestError):
        app.parse_payload({**VALID, **override})


def test_invoke_returns_error_without_callback_for_invalid_input(posted):
    response = app.invoke({**VALID, "repo": "bad"})

    assert response["status"] == "error"
    assert response["error"]["code"] == "invalid_request"
    assert posted == []


def test_run_job_posts_done_and_completes_task(monkeypatch, posted):
    monkeypatch.setattr(app, "do_work", lambda job: "ok")
    task_id = app.app.add_async_task("test")

    app.run_job(dict(VALID), task_id)

    assert posted == [
        (
            VALID["callback_url"],
            {"status": "done", "repo": "owner/repo", "issue_number": 12, "thread_ts": VALID["thread_ts"], "summary": "ok"},
        )
    ]
    assert app.app.get_async_task_info()["active_count"] == 0


def test_run_job_posts_error_when_work_fails(monkeypatch, posted):
    def boom(job):
        raise RuntimeError("clone failed")

    monkeypatch.setattr(app, "do_work", boom)
    task_id = app.app.add_async_task("test")

    app.run_job(dict(VALID), task_id)

    body = posted[0][1]
    assert body["status"] == "error"
    assert body["error"] == {"code": "internal_error", "message": "clone failed"}
    assert app.app.get_async_task_info()["active_count"] == 0
