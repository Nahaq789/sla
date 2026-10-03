import json


def lambda_handler(event, context):
    """
    フェーズ1 固定レスポンス実装。
    入力: {message, thread_ts, repo}
    出力: Issue 案の JSON（フェーズ2 で Bedrock 呼び出しに差し替える）
    """
    return {
        "status": "ready",
        "repo": event.get("repo"),
        "issue": {
            "title": "仮タイトル（フェーズ1 固定レスポンス）",
            "background": "背景情報をここに記載します",
            "tasks": ["タスク1", "タスク2"],
            "acceptance_criteria": ["完了条件1", "完了条件2"],
            "labels": ["enhancement"],
        },
        "questions": [],
    }
