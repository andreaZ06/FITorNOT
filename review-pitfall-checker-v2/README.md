# FITorNOT Bright Data Agent

This is the new cross-platform FITorNOT iteration. It is intentionally kept
separate from `review-pitfall-checker`, which remains the manual review text
analysis tool.

## Scope

The agent accepts product URLs and an output language, then asks a runtime
Bright Data adapter to scrape each URL. It cleans noisy promotional signals,
extracts concrete risk signals, and renders a purchase decision report.

Supported source categories:

- Xiaohongshu: note text, high-signal comments, likes, collects.
- E-commerce such as JD, Taobao, and Tmall: product title, parameters,
  follow-up reviews, negative reviews, and quality complaints.

## Runtime Boundary

Production callers must pass a `brightdata_client` adapter with this method:

```python
class BrightDataClient:
    def scrape(self, url: str) -> dict:
        ...
```

That adapter is the only place that should call Bright Data MCP tools, such as
`brightdata__scrape` or a platform-specific Bright Data parser. The agent
itself does not scrape pages directly and does not invent data when a scrape
fails.

## Domestic Browser Recall

For JD, Taobao, and Xiaohongshu, the current runtime now supports a Playwright
browser adapter as the primary domestic recall path. It is designed for
lightweight list-page recall on e-commerce sites and reverse-search note/comment
recall on Xiaohongshu.

First-time setup:

```bash
pip install -r requirements.txt
playwright install chromium
```

Optional environment variables:

```bash
FITORNOT_BROWSER_PROFILE_DIR=./.browser-profile
FITORNOT_BROWSER_HEADLESS=false
FITORNOT_BROWSER_TIMEOUT_MS=45000
FITORNOT_BROWSER_SCROLL_ROUNDS=2
FITORNOT_ENABLE_BROWSER_AUTOMATION=1
```

Notes:

- Use `FITORNOT_BROWSER_HEADLESS=false` on the first run so you can complete
  manual login for Taobao or Xiaohongshu if needed.
- Login state is stored in the persistent profile directory and will be reused
  across runs.
- If browser automation is unavailable or blocked, the workflow degrades to the
  existing Bright Data fallback without inventing comments.

## Python Usage

```python
from fitornot_brightdata_agent import analyze_product_links

result = analyze_product_links(
    {
        "links": [
            "https://www.xiaohongshu.com/explore/example",
            "https://item.jd.com/100000.html",
        ],
        "output_language": "中文",
    },
    brightdata_client=brightdata_client,
)

print(result["report"])
```

If a URL fails with a timeout, 404, 429, or another Bright Data error, the
returned `blocked_links` list records the URL and reason. The report is then
marked as partial and only uses successfully scraped sources.

## Tests

Run the local test suite:

```bash
python -m unittest discover -s tests
```

## Railway Deployment

Use Railway to deploy this backend as a separate web service from the Next.js
frontend.

### 1. Configure the service root

This repository is a monorepo. In Railway, set the service root directory to:

```bash
review-pitfall-checker-v2
```

That ensures Railway picks up the local `Dockerfile`, `railway.json`, and
backend-only environment variables.

### 2. Set environment variables

Required:

```bash
DEEPSEEK_API_KEY=your-deepseek-key
```

Recommended:

```bash
NEON_DATABASE_URL=postgresql://...
```

Recommended Railway defaults:

```bash
FITORNOT_ENABLE_BROWSER_AUTOMATION=1
FITORNOT_BROWSER_HEADLESS=true
FITORNOT_BROWSER_TIMEOUT_MS=45000
FITORNOT_BROWSER_SCROLL_ROUNDS=2
FITORNOT_BROWSER_CHANNEL=
```

Notes:

- The Railway Docker image now provisions Playwright plus bundled Chromium
  during build, so browser recall should work without a separate system Chrome
  install.
- Leave `FITORNOT_BROWSER_CHANNEL` unset on Railway so Playwright launches its
  bundled Chromium instead of looking for a branded Chrome binary that is not
  present in the container.
- Set `FITORNOT_ENABLE_BROWSER_AUTOMATION=0` only when you want to force the
  API into its degraded, non-browser fallback path.

### 3. Deploy and verify health

After the service is live, verify the health endpoint:

```bash
curl https://your-railway-domain.up.railway.app/health
```

Expected response:

```json
{"status":"ok","service":"FITorNOT"}
```

### 4. Connect the Vercel frontend

In your Vercel project, set:

```bash
FITORNOT_API_BASE_URL=https://your-railway-domain.up.railway.app
```

Do not point Vercel to `http://127.0.0.1:8000`. That address only works for
local development and will fail in production.
