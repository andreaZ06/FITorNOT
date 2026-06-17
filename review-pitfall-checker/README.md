# FITorNOT

FITorNOT 是用于电商负评风险分析和用户场景适配的避坑评价分析工具。当前项目只处理用户手动导出或粘贴的评论 CSV，不实现真实电商平台爬虫，避免平台反爬和 ToS 风险。

## 目录结构

```text
review-pitfall-checker/
  data/
    sample_reviews.csv
    labeled_sample.csv
  scripts/
    clean_reviews.py
    call_dify_workflow.py
    evaluate.py
  app/
    main.py
  tests/
    test_clean_reviews.py
```

## 本地准备

```bash
cd review-pitfall-checker
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

复制 `.env.example` 为 `.env`，填入：

```env
DIFY_API_KEY=你的 Dify API Key
WORKFLOW_ID=你的 Workflow ID
DIFY_API_BASE_URL=https://api.dify.ai/v1
```

## 评论清洗

输入 CSV 字段：

- `review_id`
- `text`
- `rating`
- `useful_count`

运行：

```bash
python scripts/clean_reviews.py data/sample_reviews.csv -o data/cleaned_reviews.json
```

清洗规则：

- 文本少于 5 个字符的评论会被过滤。
- 包含“商家发的红包”“好评返现”等疑似广告/水军话术的评论会被过滤。
- 按 `review_id` 去重，保留第一次出现的有效评论。

## 调用 Dify Workflow

`scripts/call_dify_workflow.py` 使用 Dify Workflow by ID 接口：

```text
POST /workflows/{workflow_id}/run
```

请求会传入：

- `product_id`
- `reviews`
- `user_scenario`

解析时会优先读取 Dify 输出里的 `results`、`result` 或 `analysis_results`，并统一整理为：

- `review_id`
- `risk_level`
- `impact_on_user`
- `matched_scenario`
- `reason`

## 评估

人工标注文件：

```text
data/labeled_sample.csv
```

字段：

- `review_id`
- `human_risk_level`

运行：

```bash
python scripts/evaluate.py --scenario "老人日常使用，重视安全和售后"
```

脚本会输出 L1/L2/L3 准确率、混淆矩阵和不一致 case。

## FastAPI 服务

启动：

```bash
uvicorn app.main:app --reload
```

接口：

```http
POST /analyze
```

请求示例：

```json
{
  "product_id": "sku-001",
  "user_scenario": "老人日常使用，重视安全和售后",
  "reviews": [
    {
      "review_id": "r1",
      "text": "包装破损，客服处理很慢，老人用起来不方便",
      "rating": 2,
      "useful_count": 8
    }
  ]
}
```

## 测试

当前先使用 Python 标准库测试，避免骨架阶段增加额外测试依赖：

```bash
python -m unittest discover -s tests
```

后续如果测试规模扩大，可以引入 pytest，并把 Dify 调用边界用 mock 或本地假服务隔离。
