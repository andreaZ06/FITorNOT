# FITorNOT Railway Backend Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `review-pitfall-checker-v2` 补齐为可部署到 Railway 的独立 FastAPI 服务，并补完前后端接线所需文档。

**Architecture:** 以后端目录为边界，新增 Docker 与 Railway 配置文件，保持运行入口仍为 `main:app`。通过轻量文件级测试保护部署产物，避免未来回退成“只能本地跑”的状态。

**Tech Stack:** FastAPI, Uvicorn, Docker, Railway, Python unittest

---

### Task 1: 为部署产物写失败测试

**Files:**
- Create: `review-pitfall-checker-v2/tests/test_deployment_artifacts.py`

- [ ] **Step 1: 写失败测试，锁定部署产物清单**

```python
import json
from pathlib import Path
import unittest


class DeploymentArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.project_root = Path(__file__).resolve().parents[1]

    def test_required_railway_artifacts_exist_and_include_expected_runtime_settings(self):
        dockerfile = self.project_root / "Dockerfile"
        dockerignore = self.project_root / ".dockerignore"
        env_example = self.project_root / ".env.example"
        railway_config = self.project_root / "railway.json"

        self.assertTrue(dockerfile.exists())
        self.assertTrue(dockerignore.exists())
        self.assertTrue(env_example.exists())
        self.assertTrue(railway_config.exists())
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m unittest discover -s review-pitfall-checker-v2/tests -p "test_deployment_artifacts.py"`
Expected: FAIL，因为部署文件尚不存在

### Task 2: 补 Docker 与 Railway 配置

**Files:**
- Create: `review-pitfall-checker-v2/Dockerfile`
- Create: `review-pitfall-checker-v2/.dockerignore`
- Create: `review-pitfall-checker-v2/railway.json`

- [ ] **Step 1: 写最小生产 Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

- [ ] **Step 2: 写 `.dockerignore`**

```gitignore
__pycache__/
.pytest_cache/
.browser-profile/
.env
.venv/
```

- [ ] **Step 3: 写 `railway.json` 并暴露健康检查**

```json
{
  "$schema": "https://railway.com/railway.schema.json",
  "deploy": {
    "healthcheckPath": "/health",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### Task 3: 补后端 env 模板与 README

**Files:**
- Create: `review-pitfall-checker-v2/.env.example`
- Modify: `review-pitfall-checker-v2/README.md`

- [ ] **Step 1: 写后端专用 `.env.example`**

```dotenv
DEEPSEEK_API_KEY=
BRIGHTDATA_API_KEY=
NEON_DATABASE_URL=
FITORNOT_ENABLE_BROWSER_AUTOMATION=0
FITORNOT_BROWSER_HEADLESS=true
FITORNOT_BROWSER_TIMEOUT_MS=45000
FITORNOT_BROWSER_SCROLL_ROUNDS=2
```

- [ ] **Step 2: 在 README 中加入 Railway 部署与 Vercel 接线说明**

```md
## Railway Deployment

1. Create a new Railway service from `review-pitfall-checker-v2`
2. Set `DEEPSEEK_API_KEY`
3. Keep `FITORNOT_ENABLE_BROWSER_AUTOMATION=0` unless you explicitly provision browser runtime support
4. Deploy and verify `GET /health`
5. Set Vercel `FITORNOT_API_BASE_URL` to the Railway public `https` URL
```

### Task 4: 回归验证与提交

**Files:**
- Test: `review-pitfall-checker-v2/tests/test_deployment_artifacts.py`
- Verify: `review-pitfall-checker-v2/README.md`

- [ ] **Step 1: 运行新增测试，确认转绿**

Run: `python -m unittest discover -s review-pitfall-checker-v2/tests -p "test_deployment_artifacts.py"`
Expected: PASS

- [ ] **Step 2: 运行前端既有验证，确保接线逻辑未受影响**

Run: `npm run typecheck`
Expected: PASS

- [ ] **Step 3: 跑仓库验证**

Run: `npm exec pnpm -- run verify`
Expected: PASS with existing warnings only

- [ ] **Step 4: 提交**

```bash
git add review-pitfall-checker-v2 docs/superpowers/specs/2026-06-19-fitornot-railway-backend-design.md docs/superpowers/plans/2026-06-19-fitornot-railway-backend-deployment.md
git commit -m "feat: add railway deployment for fitornot backend"
```
