"""FITorNOT FastAPI 服务。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.config import APP_NAME
from scripts.call_dify_workflow import DifyWorkflowError, run_dify_workflow
from scripts.clean_reviews import lightweight_clean_reviews_text


app = FastAPI(title=APP_NAME, version="0.1.0")


class AnalyzeRequest(BaseModel):
    product_id: str
    reviews: str
    user_scenario: Optional[str] = None


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    """分析一段已整理好的评论文本，并把 Dify outputs 原样返回。"""

    reviews_text = lightweight_clean_reviews_text(request.reviews)
    if not reviews_text:
        raise HTTPException(status_code=400, detail="reviews 不能为空")

    try:
        return run_dify_workflow(
            reviews_text=reviews_text,
            user_scenario=request.user_scenario or "",
            user_id=request.product_id or "test-user",
        )
    except DifyWorkflowError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": str(exc),
                "dify_status_code": exc.status_code,
                "dify_response_body": exc.response_body,
            },
        ) from exc
