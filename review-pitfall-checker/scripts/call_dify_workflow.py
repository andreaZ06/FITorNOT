"""FITorNOT 调用 Dify Workflow 的边界模块。

本模块负责读取 Dify 配置、发送 Workflow 请求、解析 streaming SSE 事件，
并把最终 workflow_finished 事件里的 data.outputs 返回给业务层。
"""

from __future__ import annotations

import json
import os
import time
from collections import deque
from typing import Any

import requests
from dotenv import load_dotenv


DEFAULT_DIFY_BASE_URL = "https://api.dify.ai/v1"
RECENT_EVENT_LIMIT = 5


class DifyWorkflowError(RuntimeError):
    """Dify Workflow 调用失败时抛出的异常。"""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.response_body = response_body
        detail_parts = [message]
        if status_code is not None:
            detail_parts.append(f"status_code={status_code}")
        if response_body:
            detail_parts.append(f"response_body={response_body}")
        super().__init__("; ".join(detail_parts))


def get_dify_config() -> tuple[str, str]:
    """读取 Dify API Key 和 Base URL。"""

    load_dotenv()
    api_key = os.getenv("DIFY_API_KEY", "").strip()
    base_url = os.getenv("DIFY_BASE_URL", DEFAULT_DIFY_BASE_URL).strip().rstrip("/")

    if not api_key:
        raise DifyWorkflowError("缺少环境变量 DIFY_API_KEY")

    return api_key, base_url or DEFAULT_DIFY_BASE_URL


def format_recent_events(events: deque[dict[str, Any]]) -> str:
    """把最近收到的 SSE 事件格式化到错误信息里，便于排查。"""

    return json.dumps(list(events), ensure_ascii=False)


def parse_sse_json_line(line: str | bytes) -> dict[str, Any] | None:
    """解析一行 Dify SSE 数据。

    Dify SSE 行格式通常是：data: {...json...}
    空行、非 data 行和 [DONE] 行会被忽略。
    """

    if isinstance(line, bytes):
        line = line.decode("utf-8")

    line = line.strip()
    if not line or not line.startswith("data:"):
        return None

    payload = line.removeprefix("data:").strip()
    if not payload or payload == "[DONE]":
        return None

    try:
        event = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DifyWorkflowError(
            "Dify SSE 行不是合法 JSON", response_body=payload
        ) from exc

    if not isinstance(event, dict):
        return None

    return event


def extract_workflow_outputs_from_stream(response: requests.Response) -> dict[str, Any]:
    """逐行消费 SSE 流，并返回 workflow_finished 事件里的 outputs。"""

    recent_events: deque[dict[str, Any]] = deque(maxlen=RECENT_EVENT_LIMIT)

    try:
        lines = response.iter_lines(decode_unicode=True)
        for line in lines:
            event = parse_sse_json_line(line)
            if event is None:
                continue

            recent_events.append(event)
            event_name = event.get("event")

            if event_name == "workflow_finished":
                outputs = (event.get("data") or {}).get("outputs")
                if isinstance(outputs, dict):
                    return outputs
                raise DifyWorkflowError(
                    "workflow_finished 事件缺少 data.outputs",
                    response_body=format_recent_events(recent_events),
                )

            if event_name == "error":
                message = event.get("message") or (event.get("data") or {}).get(
                    "message"
                )
                raise DifyWorkflowError(
                    f"Dify Workflow streaming error: {message or 'unknown error'}",
                    response_body=format_recent_events(recent_events),
                )
    except requests.RequestException as exc:
        raise DifyWorkflowError(
            f"Dify SSE 流读取异常: {exc}",
            response_body=format_recent_events(recent_events),
        ) from exc

    raise DifyWorkflowError(
        "Dify SSE 流结束但没有收到 workflow_finished 事件",
        response_body=format_recent_events(recent_events),
    )


def run_dify_workflow(
    reviews_text: str,
    user_scenario: str = "",
    user_id: str = "test-user",
) -> dict[str, Any]:
    """运行 Dify Workflow streaming 模式并返回最终 outputs。

    只对连接层面的 requests.post 失败做重试，避免业务超时或已启动的
    Workflow 被重复提交。
    """

    api_key, base_url = get_dify_config()
    url = f"{base_url}/workflows/run"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "inputs": {
            "reviews": reviews_text,
            "user_scenario": user_scenario or "",
        },
        "response_mode": "streaming",
        "user": user_id,
    }

    last_error: DifyWorkflowError | None = None
    for attempt in range(3):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=body,
                timeout=180,
                stream=True,
            )
            break
        except requests.RequestException as exc:
            last_error = DifyWorkflowError(f"Dify 连接异常: {exc}")
            if attempt < 2:
                time.sleep(2)
    else:
        raise last_error or DifyWorkflowError("Dify Workflow 连接失败")

    if not 200 <= response.status_code < 300:
        raise DifyWorkflowError(
            "Dify Workflow 返回非成功状态",
            status_code=response.status_code,
            response_body=response.text,
        )

    return extract_workflow_outputs_from_stream(response)
