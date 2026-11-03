"""作業結果を n8n の Wait ノードの再開用 URL に POST する。"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
# n8n (自宅 PC) が一時的に応答しない場合に備えて数回だけ再送する
RETRY_WAIT_SECONDS = (0, 5, 30)


def post_result(url: str, body: dict[str, Any]) -> bool:
    """結果を POST する。どの試行でも 2xx が返らなければ False を返す (例外は投げない)。"""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    for attempt, wait in enumerate(RETRY_WAIT_SECONDS, start=1):
        time.sleep(wait)
        request = urllib.request.Request(
            url, data=data, method="POST", headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                if 200 <= response.status < 300:
                    return True
                logger.warning("callback returned %s (attempt %d)", response.status, attempt)
        except Exception as e:  # noqa: BLE001 - 失敗しても作業結果のログは残したい
            logger.warning("callback failed (attempt %d): %s", attempt, e)
    logger.error("callback gave up after %d attempts", len(RETRY_WAIT_SECONDS))
    return False
