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
FITORNOT_BROWSER_STORAGE_STATE=
FITORNOT_BROWSER_CDP_URL=
```

Notes:

- Use `FITORNOT_BROWSER_HEADLESS=false` on the first run so you can complete
  manual login for Taobao or Xiaohongshu if needed.
- Login state is stored in the persistent profile directory and will be reused
  across runs.
- On headless hosts such as Railway, inject a trusted Playwright
  `storageState` payload through `FITORNOT_BROWSER_STORAGE_STATE`. The value
  can be raw JSON or a `base64:`-prefixed JSON payload.
- The storage-state exporter automatically trims the payload down to the
  supported FITorNOT domains (`jd.com`, `taobao.com`, `tmall.com`,
  `xiaohongshu.com`) so the secret stays within common hosting limits.
- If you already operate a trusted remote Chrome session, point
  `FITORNOT_BROWSER_CDP_URL` at it instead.
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
FITORNOT_BROWSER_STORAGE_STATE=
```

Notes:

- The Railway Docker image now provisions Playwright plus bundled Chromium
  during build, so browser recall should work without a separate system Chrome
  install.
- Leave `FITORNOT_BROWSER_CHANNEL` unset on Railway so Playwright launches its
  bundled Chromium instead of looking for a branded Chrome binary that is not
  present in the container.
- For trusted logged-in sessions on Railway, prefer
  `FITORNOT_BROWSER_STORAGE_STATE`. You can paste a raw Playwright
  `storageState` JSON object or a `base64:`-prefixed encoded payload. The
  exporter trims it to the FITorNOT-supported domains automatically.
- If you manage an external trusted browser yourself, set
  `FITORNOT_BROWSER_CDP_URL` instead of storage state.
- Set `FITORNOT_ENABLE_BROWSER_AUTOMATION=0` only when you want to force the
  API into its degraded, non-browser fallback path.

### 3. Export a trusted storage state locally

If you want Railway to reuse your local logged-in browser session, export a
Playwright `storageState` from the FITorNOT browser profile.

1. Launch the local FITorNOT browser profile and log in:

```bash
powershell -ExecutionPolicy Bypass -File .\start_fitornot_browser.ps1
```

2. Keep that browser window open after login. The exporter will try to connect
   to the live local browser first, which is more reliable than copying the
   profile on Windows.

3. Export the storage state:

```bash
python export_fitornot_storage_state.py --output outputs/fitornot-storage-state.json
```

4. Copy the printed single-line value into Railway exactly as:

```bash
FITORNOT_BROWSER_STORAGE_STATE=base64:...
```

The exporter writes a readable JSON file for inspection and also prints the
full `FITORNOT_BROWSER_STORAGE_STATE=` assignment so you can paste it directly
into Railway secrets.

### 4. Deploy and verify health

After the service is live, verify the health endpoint:

```bash
curl https://your-railway-domain.up.railway.app/health
```

Expected response:

```json
{"status":"ok","service":"FITorNOT"}
```

### 5. Connect the Vercel frontend

In your Vercel project, set:

```bash
FITORNOT_API_BASE_URL=https://your-railway-domain.up.railway.app
```

Do not point Vercel to `http://127.0.0.1:8000`. That address only works for
local development and will fail in production.
