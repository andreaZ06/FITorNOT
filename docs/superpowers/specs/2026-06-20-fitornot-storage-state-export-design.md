# FITorNOT Storage State Export Design

Date: 2026-06-20
Status: Draft approved in chat, written for implementation review

## Scope

这份设计只覆盖一件事：

1. 把本地已登录的 FITorNOT 浏览器会话导出为 Playwright `storageState`
2. 产出可直接粘贴到 Railway 环境变量 `FITORNOT_BROWSER_STORAGE_STATE` 的单行值
3. 为这条链路补齐测试和文档

它不覆盖以下内容：

- 不改动 FITorNOT 前端 UI
- 不新增线上登录流程
- 不改动 DeepSeek / LangGraph 业务逻辑
- 不接回 Bright Data

## Problem Summary

我们已经把 Railway 上的 Playwright 运行时打通，也已经让后端在被平台拦截时正确提示：

- Railway 上优先使用 `FITORNOT_BROWSER_STORAGE_STATE`
- 也支持 `FITORNOT_BROWSER_CDP_URL`

但现在仍缺一个真正可复用、适合上线交付的最后一环：

- 用户虽然可以在本地浏览器里登录京东 / 淘宝 / 小红书
- 但没有一个稳定、低出错率的方式，把这份登录态转换成 Railway 可直接使用的 `storageState`
- 如果每次都靠手动脚本或临时调试来导出，会让部署流程脆弱且难以复用

结果就是：后端能力已经准备好，但线上可操作性还不够顺手。

## Goal

提供一个本地工具链，让使用者在已经登录过 FITorNOT 浏览器资料目录后，可以稳定地导出：

- 一份结构化 `storageState.json`
- 一条 `base64:` 前缀的单行字符串

这样 Railway 部署时只需要把输出值粘贴到：

```bash
FITORNOT_BROWSER_STORAGE_STATE=base64:...
```

就能让线上后端直接带着可信登录态启动抓取。

## Recommended Approach

推荐方案是增加一个独立的本地导出脚本，而不是把这件事塞进现有 API 或手工步骤里。

### 方案说明

在 `review-pitfall-checker-v2/` 下增加一个导出工具，例如：

- `export_fitornot_storage_state.py`

它的职责是：

1. 复用现有浏览器资料目录路径约定
2. 使用 Playwright 读取该 profile 下的登录态
3. 调用 `context.storage_state()` 导出 JSON
4. 同时生成：
   - 本地 JSON 文件
   - Railway 可粘贴的 `base64:` 单行值
5. 在输出中明确告诉使用者下一步该把值放到哪里

### 为什么选这个方案

这个方案比“只写 README 手工导出”更稳，也比“做成线上接口”更安全：

1. 登录态处理留在本地，边界清晰
2. Railway 不需要额外知道用户如何登录，只消费最终结果
3. 脚本可以反复执行，便于后续 cookie 失效后的再导出
4. 测试可以覆盖核心格式与异常处理，减少上线踩坑

## Runtime Design

### Inputs

导出工具应支持以下输入来源：

- 默认从 `FITORNOT_BROWSER_PROFILE_DIR` 读取 profile 目录
- 若未设置，则回退到当前项目默认资料目录
- 可选指定输出文件路径

### Outputs

导出工具至少应产出三类结果：

1. `storage_state` JSON 对象
2. 保存到磁盘的 JSON 文件路径
3. 一个可直接复制的 Railway 环境变量值：

```text
base64:<encoded-json>
```

### Console UX

终端输出应该尽量直接，避免技术噪音。至少包含：

- 导出是否成功
- JSON 文件保存位置
- Railway 该填写的完整值
- 如果 profile 未登录，明确提示先用本地 FITorNOT 浏览器完成登录

## File Responsibilities

### New file

- `review-pitfall-checker-v2/export_fitornot_storage_state.py`
  - 导出入口
  - 参数解析
  - 调用 Playwright 打开本地 profile
  - 输出 JSON 文件与 base64 单行值

### Existing files to update

- `review-pitfall-checker-v2/README.md`
  - 增加“如何导出 Railway 可用 storage state”的步骤

- `review-pitfall-checker-v2/.env.example`
  - 保持 `FITORNOT_BROWSER_STORAGE_STATE` 文档清晰
  - 可补一行注释指向导出脚本

- `review-pitfall-checker-v2/tests/test_domestic_browser.py`
  - 如有需要，补与编码格式相关的工具级测试

- `review-pitfall-checker-v2/tests/`
  - 新增导出脚本测试文件，覆盖纯函数和 CLI 行为中可稳定测试的部分

## Error Handling

导出工具必须对以下情况给出清晰失败信息，而不是直接栈追踪砸脸：

1. profile 目录不存在
2. Playwright 未安装或浏览器不可用
3. profile 可打开，但未登录关键平台
4. 导出的 `storageState` 为空或结构异常
5. 输出文件写入失败

失败时的原则：

- 明确说出失败原因
- 明确指出下一步动作
- 不生成看似成功但实际不可用的空值

## Security Boundaries

这是一个本地敏感数据导出工具，因此边界要写清楚：

- 导出的 `storageState` 视为敏感凭据
- 默认只写入本地文件，不自动上传任何远程服务
- README 中明确提醒：
  - 不要提交导出的 JSON 到 Git
  - 只将单行值粘贴到 Railway 私密环境变量

## Testing Strategy

这部分要严格走 TDD。

### Unit coverage

优先把可纯函数测试的逻辑拆出来，例如：

- `storageState` JSON 转 base64 单行值
- base64 值格式校验
- 输出 payload 组装
- 路径解析与默认值逻辑

### Behavior coverage

对脚本层至少覆盖这些行为：

1. 给定合法 `storageState`，能生成正确 `base64:` 值
2. 缺少 profile 路径时，返回清晰错误
3. 导出为空对象时，拒绝生成成功结果
4. README / `.env.example` 文档中包含导出指引

测试应避免依赖真实登录态，也不要要求联网。

## Success Criteria

实现完成后，应满足：

1. 本地登录一次后，可以稳定导出 Railway 可用的 `FITORNOT_BROWSER_STORAGE_STATE`
2. Railway 用户只需复制脚本输出值即可完成配置
3. 文档里有清晰步骤，不需要额外口头解释
4. 测试能保护编码格式、空状态和文档回归
