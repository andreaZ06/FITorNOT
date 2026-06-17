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
