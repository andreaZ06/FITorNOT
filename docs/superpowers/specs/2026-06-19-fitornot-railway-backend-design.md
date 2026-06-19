# FITorNOT Railway Backend Design

## Goal

将 `review-pitfall-checker-v2` 补齐为一个可独立部署到 Railway 的 FastAPI 后端，并让 Vercel 前端可以通过公网 `FITORNOT_API_BASE_URL` 稳定调用。

## Current State

- 业务入口已经存在于 `review-pitfall-checker-v2/main.py`
- 已暴露 `POST /api/v1/decision` 与 `GET /health`
- 依赖已集中在 `review-pitfall-checker-v2/requirements.txt`
- 当前缺少容器构建文件、Railway 配置、后端专用环境变量模板与部署说明

## Recommended Approach

采用 Docker 部署作为 Railway 的标准运行边界：

- 在 `review-pitfall-checker-v2/` 目录内增加 `Dockerfile` 与 `.dockerignore`
- 使用容器启动命令直接运行 `uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}`
- 通过 `railway.json` 提供健康检查路径和重启策略
- 用独立的 `.env.example` 明确后端生产环境变量，而不是复用前端模板

这样做的原因是：

1. Railway 对 Docker 工作流支持稳定，和 FastAPI 的运行模型天然契合
2. 可以把 Python 依赖、启动命令和健康检查都固定在后端目录中，边界清晰
3. 前端只需要知道一个公网后端地址，不需要感知 Python 运行细节

## Runtime Behavior

后端上线后提供两个正式公网入口：

- `GET /health`
- `POST /api/v1/decision`

Railway 容器默认不依赖本地桌面环境，因此国内站浏览器自动化能力应视为可选增强，而不是启动前置条件：

- `DEEPSEEK_API_KEY` 作为必填
- `BRIGHTDATA_API_KEY`、`NEON_DATABASE_URL` 作为按需增强
- `FITORNOT_ENABLE_BROWSER_AUTOMATION` 在 Railway 默认保持关闭

## Error Handling

- 后端缺少 `DEEPSEEK_API_KEY` 时，应在请求阶段返回清晰错误，而不是容器无法启动
- Railway 健康检查必须始终走 `GET /health`
- 文档中明确提醒：Vercel 的 `FITORNOT_API_BASE_URL` 必须填 Railway 公网 `https` 地址，不能指向 `127.0.0.1`

## Testing Strategy

新增一个轻量部署产物测试，校验：

- `Dockerfile` 存在且使用 `uvicorn` 暴露 `PORT`
- `.dockerignore` 屏蔽浏览器 profile、缓存与本地 env
- 后端 `.env.example` 包含关键生产变量
- `railway.json` 暴露 `/health`

这组测试不触发真实网络，也不依赖外部平台，适合做回归保护。
