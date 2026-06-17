"""FITorNOT 单页分析界面。"""

from __future__ import annotations


def render_index_page() -> str:
    """返回 FITorNOT 分析工作台 HTML。"""

    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FITorNOT</title>
  <style>
    :root {
      color-scheme: light;
      --background: #f8faf3;
      --surface: #ffffff;
      --surface-low: #f2f4ed;
      --surface-mid: #ecefe8;
      --surface-high: #e7e9e2;
      --primary: #55624d;
      --primary-dark: #2f3c29;
      --primary-soft: #d9e7cd;
      --secondary: #755754;
      --secondary-soft: #fed7d2;
      --text: #191c18;
      --muted: #444841;
      --outline: #757870;
      --line: #c5c8be;
      --danger: #ba1a1a;
      --danger-soft: #ffdad6;
      --fit: #236342;
      --not: #8c2d25;
      --shadow: 0 36px 90px rgb(47 60 41 / 0.14);
      --radius-xl: 24px;
      --radius-lg: 16px;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100dvh;
      font-family: Arial, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 92% 12%, rgb(254 215 210 / 0.82), transparent 28rem),
        radial-gradient(circle at 8% 8%, rgb(217 231 205 / 0.92), transparent 32rem),
        linear-gradient(135deg, #f8faf3 0%, #f2f4ed 48%, #fff6f3 100%);
    }

    button, input, textarea { font: inherit; }

    .topbar {
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      padding: 20px min(6vw, 48px);
      border-bottom: 1px solid rgb(85 98 77 / 0.08);
      background: rgb(248 250 243 / 0.78);
      backdrop-filter: blur(20px);
    }

    .brand, .nav, .user {
      display: flex;
      align-items: center;
      gap: 14px;
    }

    .mark {
      display: grid;
      place-items: center;
      width: 38px;
      height: 38px;
      border-radius: 12px;
      color: white;
      background: var(--primary);
      font-weight: 800;
    }

    .brand strong {
      font-size: 24px;
      letter-spacing: 0;
      color: var(--primary);
    }

    .nav {
      gap: 26px;
      margin-left: 24px;
    }

    .nav a {
      color: var(--outline);
      text-decoration: none;
      font-size: 14px;
      font-weight: 700;
      transition: color 160ms ease;
    }

    .nav a.active, .nav a:hover { color: var(--primary); }

    .icon-button {
      display: grid;
      place-items: center;
      width: 40px;
      height: 40px;
      border: 0;
      border-radius: 999px;
      color: var(--outline);
      background: transparent;
      cursor: pointer;
    }

    .icon-button:hover { background: var(--surface-mid); color: var(--primary); }

    .avatar {
      display: grid;
      place-items: center;
      width: 40px;
      height: 40px;
      border: 1px solid rgb(85 98 77 / 0.12);
      border-radius: 999px;
      color: var(--primary);
      background: var(--surface-high);
      font-weight: 800;
    }

    .shell {
      width: min(1280px, calc(100% - 40px));
      margin: 0 auto;
      padding: 60px 0 48px;
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1.9fr) minmax(320px, 0.9fr);
      gap: 34px;
      align-items: start;
    }

    .hero h1 {
      margin: 0;
      color: var(--primary);
      font-size: clamp(46px, 6.4vw, 78px);
      font-weight: 300;
      line-height: 0.98;
      letter-spacing: 0;
    }

    .hero p {
      max-width: 650px;
      margin: 22px 0 38px;
      color: var(--muted);
      font-size: 18px;
      line-height: 1.85;
    }

    .analysis-card {
      border: 1px solid rgb(85 98 77 / 0.06);
      border-radius: 36px;
      background: var(--surface);
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .card-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      padding: 28px 32px 18px;
    }

    .title-lockup {
      display: flex;
      align-items: center;
      gap: 15px;
    }

    .title-icon {
      display: grid;
      place-items: center;
      width: 52px;
      height: 52px;
      border-radius: 20px;
      color: var(--primary-dark);
      background: #b2f2d8;
      font-size: 24px;
    }

    .card-head h2, .side-card h3 {
      margin: 0;
      color: var(--primary);
      font-size: 23px;
      line-height: 1.2;
    }

    .card-head p {
      margin: 5px 0 0;
      color: var(--outline);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }

    .form-grid {
      display: grid;
      gap: 18px;
      padding: 12px 32px 32px;
    }

    label {
      display: grid;
      gap: 9px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 800;
    }

    .field-note {
      color: var(--outline);
      font-size: 12px;
      font-weight: 600;
    }

    input, textarea {
      width: 100%;
      border: 2px solid transparent;
      border-radius: 18px;
      outline: none;
      color: var(--text);
      background: var(--surface-low);
      padding: 17px 18px;
      line-height: 1.65;
      transition: border-color 160ms ease, background 160ms ease, box-shadow 160ms ease;
    }

    textarea {
      min-height: 240px;
      resize: vertical;
    }

    input:focus, textarea:focus {
      border-color: rgb(85 98 77 / 0.24);
      background: var(--surface);
      box-shadow: 0 0 0 5px rgb(85 98 77 / 0.08);
    }

    .form-actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      padding-top: 4px;
    }

    .primary-button, .secondary-button {
      min-height: 54px;
      border: 0;
      border-radius: 18px;
      padding: 0 22px;
      cursor: pointer;
      font-weight: 850;
      transition: transform 160ms ease, filter 160ms ease, background 160ms ease;
    }

    .primary-button {
      flex: 1;
      min-width: 220px;
      color: white;
      background: var(--primary);
      box-shadow: 0 18px 36px rgb(85 98 77 / 0.18);
    }

    .secondary-button {
      color: var(--primary);
      background: var(--primary-soft);
    }

    .primary-button:hover { filter: brightness(1.08); }
    .secondary-button:hover { background: #cddcbe; }
    button:active { transform: translateY(1px) scale(0.99); }
    button:disabled { cursor: wait; opacity: 0.68; }

    .side-column { display: grid; gap: 22px; }

    .side-card {
      position: relative;
      overflow: hidden;
      border-radius: 32px;
      padding: 28px;
      border: 1px solid rgb(85 98 77 / 0.06);
      background: var(--secondary-soft);
      box-shadow: 0 22px 60px rgb(117 87 84 / 0.08);
    }

    .side-card.history {
      background: var(--surface-high);
    }

    .side-card p {
      color: rgb(43 22 20 / 0.72);
      line-height: 1.65;
      margin: 14px 0 22px;
    }

    .progress {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 6px;
    }

    .progress span {
      height: 7px;
      border-radius: 999px;
      background: rgb(43 22 20 / 0.2);
    }

    .progress span:nth-child(-n+4) { background: rgb(43 22 20 / 0.88); }

    .history-list { display: grid; gap: 12px; margin-top: 18px; }

    .history-item {
      display: grid;
      grid-template-columns: 44px minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
      padding: 12px;
      border-radius: 16px;
      background: rgb(255 255 255 / 0.42);
      cursor: pointer;
    }

    .history-thumb {
      display: grid;
      place-items: center;
      width: 44px;
      height: 44px;
      border-radius: 12px;
      color: var(--outline);
      background: var(--surface-mid);
    }

    .history-item strong {
      display: block;
      overflow: hidden;
      color: var(--text);
      font-size: 14px;
      white-space: nowrap;
      text-overflow: ellipsis;
    }

    .history-item small { color: var(--outline); }

    .result-card {
      margin-top: 24px;
      border: 1px solid rgb(85 98 77 / 0.08);
      border-radius: 28px;
      background: rgb(255 255 255 / 0.7);
      overflow: hidden;
    }

    .result-head {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      padding: 20px 24px;
      border-bottom: 1px solid rgb(85 98 77 / 0.08);
    }

    .result-head h2 { margin: 0; color: var(--primary); font-size: 20px; }
    .result-head span { color: var(--outline); font-size: 13px; font-weight: 700; }

    .result-body {
      display: grid;
      grid-template-columns: minmax(200px, 0.7fr) minmax(0, 1.3fr);
      gap: 18px;
      padding: 24px;
    }

    .decision-card {
      border-radius: 22px;
      padding: 18px;
      color: var(--primary-dark);
      background: var(--primary-soft);
    }

    .decision-card small {
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-weight: 850;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }

    .decision-card strong {
      display: block;
      font-size: 42px;
      line-height: 1;
    }

    .risk-list { display: grid; gap: 10px; }

    .risk-item, .empty-state {
      border-radius: 16px;
      padding: 14px 15px;
      font-size: 14px;
      line-height: 1.6;
    }

    .risk-item {
      color: var(--not);
      background: #fff5f2;
      border: 1px solid #ecc8c0;
    }

    .empty-state {
      color: var(--muted);
      background: var(--surface-low);
      border: 1px dashed var(--line);
    }

    pre {
      max-height: 260px;
      margin: 18px 0 0;
      overflow: auto;
      border-radius: 18px;
      padding: 16px;
      color: #eaf3e6;
      background: #101810;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre-wrap;
    }

    pre.error { color: var(--danger-soft); }

    .fab {
      position: fixed;
      right: 32px;
      bottom: 32px;
      display: grid;
      place-items: center;
      width: 60px;
      height: 60px;
      border: 0;
      border-radius: 20px;
      color: white;
      background: var(--primary);
      box-shadow: 0 20px 50px rgb(47 60 41 / 0.28);
      cursor: pointer;
      font-size: 26px;
      font-weight: 300;
    }

    @media (max-width: 980px) {
      .layout, .result-body { grid-template-columns: 1fr; }
      .nav, .user-meta { display: none; }
    }

    @media (max-width: 620px) {
      .topbar { padding: 16px 20px; }
      .shell { width: min(100% - 24px, 1280px); padding-top: 34px; }
      .card-head, .form-grid { padding-left: 20px; padding-right: 20px; }
      .hero h1 { font-size: 42px; }
      .analysis-card { border-radius: 26px; }
      .fab { right: 18px; bottom: 18px; }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="brand">
      <div class="mark">F</div>
      <strong>FITorNOT</strong>
      <nav class="nav" aria-label="主导航">
        <a class="active" href="#analysis">分析</a>
        <a href="#history">历史</a>
        <a href="#saved">已保存</a>
      </nav>
    </div>
    <div class="user">
      <button class="icon-button" type="button" title="设置">⚙</button>
      <div class="user-meta" style="text-align:right">
        <strong style="display:block;font-size:14px;">Alex Rivera</strong>
        <span style="color:var(--outline);font-size:12px;">高级会员</span>
      </div>
      <div class="avatar">A</div>
    </div>
  </header>

  <main class="shell">
    <div class="layout">
      <section class="hero" id="analysis">
        <h1>HELLO</h1>
        <p>粘贴商品负评、使用场景或商品链接备注，FITorNOT 会把杂乱评论整理成清晰的购买风险、致命问题和适配结论。</p>

        <section class="analysis-card">
          <div class="card-head">
            <div class="title-lockup">
              <div class="title-icon">⌕</div>
              <div>
                <h2>还在担心值不值得买？</h2>
                <p>让我来帮你判断</p>
              </div>
            </div>
          </div>

          <form class="form-grid" id="analyze-form">
            <label>
              <span>商品 ID / 链接备注</span>
              <span class="field-note">支持你手动填 SKU、商品链接或自己的备注名</span>
              <input id="product-id" name="product_id" value="sample-sku-001" autocomplete="off" />
            </label>

            <label>
              <span>使用场景</span>
              <span class="field-note">例如：老人使用、敏感肌、飞机出差、儿童家庭</span>
              <input id="user-scenario" name="user_scenario" value="老人日常使用，重视安全和售后" autocomplete="off" />
            </label>

            <label>
              <span>评论文本</span>
              <span class="field-note">把手动整理好的评论整段粘贴到这里，语义判断交给 Dify 工作流</span>
              <textarea id="reviews" name="reviews">包装破损，客服处理很慢，老人用起来不方便。
尺寸偏小，脚背高的人穿久了会压脚。</textarea>
            </label>

            <div class="form-actions">
              <button class="primary-button" id="submit-button" type="submit">立即分析</button>
              <button class="secondary-button" id="clear-button" type="button">清空结果</button>
            </div>
          </form>
        </section>

        <section class="result-card" aria-labelledby="result-title">
          <div class="result-head">
            <h2 id="result-title">结论</h2>
            <span id="result-status">等待输入</span>
          </div>
          <div class="result-body">
            <div class="decision-card">
              <small>Recommendation</small>
              <strong id="recommendation">--</strong>
            </div>
            <div>
              <div class="risk-list" id="fatal-risks">
                <div class="empty-state">分析完成后，这里会列出最需要避开的 fatal_risks。</div>
              </div>
              <pre id="raw-json">{}</pre>
            </div>
          </div>
        </section>
      </section>

      <aside class="side-column">
        <section class="side-card">
          <h3>每周推荐</h3>
          <p>根据你最近的使用场景，推荐适合你的商品~</p>
          <div class="progress" aria-hidden="true">
            <span></span><span></span><span></span><span></span><span></span><span></span><span></span>
          </div>
        </section>

        <section class="side-card history" id="history">
          <h3>最近查询</h3>
          <div class="history-list">
            <div class="history-item">
              <div class="history-thumb">□</div>
              <div><strong>人体工学办公椅</strong><small>2 小时前</small></div>
              <span>›</span>
            </div>
            <div class="history-item">
              <div class="history-thumb">□</div>
              <div><strong>降噪耳机</strong><small>昨天</small></div>
              <span>›</span>
            </div>
          </div>
        </section>
      </aside>
    </div>
  </main>

  <button class="fab" type="button" title="新建分析" id="new-analysis">+</button>

  <script>
    const form = document.getElementById("analyze-form");
    const submitButton = document.getElementById("submit-button");
    const clearButton = document.getElementById("clear-button");
    const newButton = document.getElementById("new-analysis");
    const statusNode = document.getElementById("result-status");
    const recommendationNode = document.getElementById("recommendation");
    const fatalRisksNode = document.getElementById("fatal-risks");
    const rawJsonNode = document.getElementById("raw-json");

    function renderRisks(risks) {
      fatalRisksNode.innerHTML = "";
      if (!Array.isArray(risks) || risks.length === 0) {
        fatalRisksNode.innerHTML = '<div class="empty-state">未发现明确 fatal_risks，建议结合原始 JSON 复核。</div>';
        return;
      }

      for (const risk of risks) {
        const item = document.createElement("div");
        item.className = "risk-item";
        item.textContent = typeof risk === "string"
          ? risk
          : (risk.title || risk.name || risk.reason || JSON.stringify(risk));
        fatalRisksNode.appendChild(item);
      }
    }

    function resetResult(clearInput = false) {
      statusNode.textContent = "等待输入";
      recommendationNode.textContent = "--";
      fatalRisksNode.innerHTML = '<div class="empty-state">分析完成后，这里会列出最需要避开的 fatal_risks。</div>';
      rawJsonNode.textContent = "{}";
      rawJsonNode.classList.remove("error");
      if (clearInput) {
        document.getElementById("product-id").value = "";
        document.getElementById("user-scenario").value = "";
        document.getElementById("reviews").value = "";
      }
    }

    clearButton.addEventListener("click", () => resetResult(false));
    newButton.addEventListener("click", () => {
      resetResult(true);
      document.getElementById("product-id").focus();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      submitButton.disabled = true;
      statusNode.textContent = "分析中";
      rawJsonNode.classList.remove("error");

      const payload = {
        product_id: document.getElementById("product-id").value.trim(),
        user_scenario: document.getElementById("user-scenario").value.trim(),
        reviews: document.getElementById("reviews").value.trim()
      };

      try {
        const response = await fetch("/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok) {
          throw data;
        }

        statusNode.textContent = "分析完成";
        recommendationNode.textContent = data.recommendation || data.fit_or_not || "已返回";
        renderRisks(data.fatal_risks);
        rawJsonNode.textContent = JSON.stringify(data, null, 2);
      } catch (error) {
        statusNode.textContent = "分析失败";
        recommendationNode.textContent = "ERROR";
        fatalRisksNode.innerHTML = '<div class="empty-state">Dify 或本地接口返回错误，请查看原始信息。</div>';
        rawJsonNode.classList.add("error");
        rawJsonNode.textContent = JSON.stringify(error, null, 2);
      } finally {
        submitButton.disabled = false;
      }
    });
  </script>
</body>
</html>"""
