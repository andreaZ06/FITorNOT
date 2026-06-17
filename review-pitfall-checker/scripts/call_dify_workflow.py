"""FITorNOT 调用 Dify Workflow 的边界模块。

本模块只负责：
- 从环境变量或 .env 读取 Dify 配置。
- 组装 Workflow 请求。
- 处理超时、重试、HTTP 错误和响应解析。
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv


DEFAULT_DIFY_BASE_URL = "https://api.dify.ai/v1"


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


def parse_outputs(response_json: dict[str, Any]) -> dict[str, Any]:
    """只返回 Dify 响应里的 data.outputs。"""

    try:
        outputs = response_json["data"]["outputs"]
    except (KeyError, TypeError) as exc:
        raise DifyWorkflowError(
            "Dify 响应缺少 data.outputs", response_body=str(response_json)
        ) from exc

    if not isinstance(outputs, dict):
        raise DifyWorkflowError(
            "Dify data.outputs 不是对象", response_body=str(response_json)
        )

    return outputs


def run_dify_workflow(
    reviews_text: str,
    user_scenario: str = "",
    user_id: str = "test-user",
) -> dict[str, Any]:
    """运行 Dify Workflow 并返回 outputs。

    失败时最多重试 2 次，总共 3 次请求；每次失败后间隔 2 秒。
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
        "response_mode": "blocking",
        "user": user_id,
    }

    last_error: DifyWorkflowError | None = None
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=body, timeout=90)
        except requests.RequestException as exc:
            last_error = DifyWorkflowError(f"Dify 请求异常: {exc}")
        else:
            if not 200 <= response.status_code < 300:
                last_error = DifyWorkflowError(
                    "Dify Workflow 返回非成功状态",
                    status_code=response.status_code,
                    response_body=response.text,
                )
            else:
                try:
                    return parse_outputs(response.json())
                except ValueError as exc:
                    last_error = DifyWorkflowError(f"Dify 响应不是合法 JSON: {exc}")

        if attempt < 2:
            time.sleep(2)

    raise last_error or DifyWorkflowError("Dify Workflow 调用失败")
