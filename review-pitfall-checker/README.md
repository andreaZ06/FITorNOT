# FITorNOT

FITorNOT 是用于电商负评风险分析和用户场景适配的避坑评价分析工具。当前项目只处理用户手动导出或粘贴的评论文本/CSV，不实现真实电商平台爬虫，避免平台反爬和 ToS 风险。

## 目录结构

```text
review-pitfall-checker/
  data/
    sample_reviews.csv
    sample_reviews.txt
    labeled_sample.csv
    test_cases.json
  scripts/
    clean_reviews.py
    call_dify_workflow.py
    evaluate.py
    batch_test.py
  app/
    main.py
  tests/
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
DIFY_BASE_URL=https://api.dify.ai/v1
```

## Dify Workflow 调用

`scripts/call_dify_workflow.py` 使用 Dify Workflow blocking 接口：

```text
POST {DIFY_BASE_URL}/workflows/run
```

请求体：

```json
{
  "inputs": {
    "reviews": "整理好的评论文本",
    "user_scenario": "用户使用场景"
  },
  "response_mode": "blocking",
  "user": "test-user"
}
```

成功时只返回 `response.json()["data"]["outputs"]`。失败时最多重试 2 次，间隔 2 秒，仍失败会抛出 `DifyWorkflowError`，错误里包含状态码和响应体，方便排查。

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
  "reviews": "包装破损，客服处理很慢，老人用起来不方便。\n尺寸偏小，脚背高的人穿久了会压脚。"
}
```

`main.py` 只做轻量程序化预处理：去空白行、去纯表情/符号行。语义级清洗和风险判断交给 Dify Workflow 内部节点。

## 批量测试

编辑：

```text
data/test_cases.json
```

格式：

```json
[
  {
    "product_id": "sample-sku-001",
    "reviews_file": "data/sample_reviews.txt",
    "scenario": "老人日常使用，重视安全和售后"
  }
]
```

确保本地 FastAPI 服务已启动后运行：

```bash
python scripts/batch_test.py
```

每个结果会保存到：

```text
data/results/{product_id}.json
```

脚本结束后会打印简单汇总表：

```text
product_id    recommendation    fatal_risks
```

## CSV 清洗

`scripts/clean_reviews.py` 仍保留 CSV 清洗能力，适合把手动导出的原始评论先整理成结构化数据：

```bash
python scripts/clean_reviews.py data/sample_reviews.csv -o data/cleaned_reviews.json
```

CSV 字段：

- `review_id`
- `text`
- `rating`
- `useful_count`

CSV 清洗规则：

- 文本少于 5 个字符的评论会被过滤。
- 包含“商家发的红包”“好评返现”等疑似广告/水军话术的评论会被过滤。
- 按 `review_id` 去重，保留第一次出现的有效评论。

## 测试

当前使用 Python 标准库测试：

```bash
python -m unittest discover -s tests
```
