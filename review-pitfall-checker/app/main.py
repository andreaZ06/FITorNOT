"""FITorNOT FastAPI 服务。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.config import APP_NAME
from scripts.call_dify_workflow import DifyWorkflowError, run_dify_workflow
from scripts.clean_reviews import clean_review_rows


app = FastAPI(title=APP_NAME, version="0.1.0")


class ReviewInput(BaseModel):
    review_id: str
    text: str
    rating: int | None = None
    useful_count: int | None = None


class AnalyzeRequest(BaseModel):
    product_id: str = Field(default="", description="商品 ID")
    reviews: list[ReviewInput]
    user_scenario: str = Field(..., description="用户使用场景，例如老人用、通勤用")


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    """串起清洗 + Dify Workflow 分析，返回避坑结论 JSON。"""

    cleaned_reviews = clean_review_rows([review.model_dump() for review in request.reviews])
    if not cleaned_reviews:
        return {
            "product_id": request.product_id,
            "user_scenario": request.user_scenario,
            "cleaned_count": 0,
            "results": [],
            "summary": "没有可用于分析的有效评论。",
        }

    try:
        results = run_dify_workflow(
            cleaned_reviews,
            user_scenario=request.user_scenario,
            product_id=request.product_id,
        )
    except DifyWorkflowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "product_id": request.product_id,
        "user_scenario": request.user_scenario,
        "cleaned_count": len(cleaned_reviews),
        "results": results,
        "summary": "已完成负评风险分级与用户场景适配分析。",
    }
