import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POST, maxDuration } from '@/app/api/fitornot/decision/route';

describe('POST /api/fitornot/decision', () => {
  beforeEach(() => {
    process.env.FITORNOT_API_BASE_URL = 'http://127.0.0.1:8000';
    vi.restoreAllMocks();
  });

  afterEach(() => {
    delete process.env.FITORNOT_API_BASE_URL;
  });

  it('exports a longer max duration for upstream decision generation', () => {
    expect(maxDuration).toBe(60);
  });

  it('forwards the decision request to the python backend', async () => {
    const upstreamPayload = {
      slots: {
        category: '充电宝',
        brand: 'Anker',
        model: '10000',
        urls: [],
      },
      retrieval_plan: {
        ecommerce_query: 'Anker 10000',
        xiaohongshu_queries: ['Anker 10000 发热', 'Anker 10000 虚标'],
      },
      raw_data: {
        retrieval_plan: {
          ecommerce_query: 'Anker 10000',
          xiaohongshu_queries: ['Anker 10000 发热', 'Anker 10000 虚标'],
        },
        verified_specs: {},
        ecommerce_evidence: [],
        xiaohongshu_evidence: [],
        blocked_sources: [],
      },
      cleaned_findings: {
        core_scandals: [],
        soft_drawbacks: [],
        noise_rate: {},
      },
      scenario_fit: {
        user_profile_extracted: '经常坐飞机',
        marketing_clash: null,
        suitability_analysis: '看 Wh 标识',
      },
      ecommerce_data: [],
      xiaohongshu_data: [],
      social_data: [],
      blocked_sources: [],
      report: '## report',
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(upstreamPayload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const response = await POST(
      new Request('http://localhost/api/fitornot/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userRawInput: '我想买 Anker 10000 毫安的充电宝',
          targetLanguage: 'zh-CN',
        }),
      })
    );
    const payload = await response.json();

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/v1/decision',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
        body: JSON.stringify({
          user_raw_input: '我想买 Anker 10000 毫安的充电宝',
          target_language: 'zh-CN',
        }),
      })
    );
    expect(payload.code).toBe(0);
    expect(payload.data.report).toBe('## report');
  });

  it('returns an error payload for invalid params', async () => {
    const response = await POST(
      new Request('http://localhost/api/fitornot/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userRawInput: '',
          targetLanguage: '',
        }),
      })
    );
    const payload = await response.json();

    expect(payload.code).toBe(-1);
  });

  it('returns an error payload when the backend request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'backend unavailable' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    );

    const response = await POST(
      new Request('http://localhost/api/fitornot/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userRawInput: 'query',
          targetLanguage: 'zh-CN',
        }),
      })
    );
    const payload = await response.json();

    expect(payload.code).toBe(-1);
    expect(payload.message).toContain('503');
  });

  it('returns a readable error payload when the backend responds with plain text', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('An error occurred with your deployment FUNCTION_INVOCATION_TIMEOUT', {
          status: 504,
          headers: { 'Content-Type': 'text/plain' },
        })
      )
    );

    const response = await POST(
      new Request('http://localhost/api/fitornot/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userRawInput: 'query',
          targetLanguage: 'zh-CN',
        }),
      })
    );
    const payload = await response.json();

    expect(payload.code).toBe(-1);
    expect(payload.message).toContain('504');
    expect(payload.message).toContain('FUNCTION_INVOCATION_TIMEOUT');
  });
});
