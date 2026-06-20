import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { requestFitOrNotDecision } from '@/shared/blocks/fitornot/request';
import type { FitOrNotDecisionResponse } from '@/shared/blocks/fitornot/types';

function buildResponse(): FitOrNotDecisionResponse {
  return {
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
      verified_specs: {
        wh: '37Wh',
      },
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
}

describe('requestFitOrNotDecision', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('falls back to the same-origin proxy when the direct backend request fails before a response arrives', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            code: 0,
            data: buildResponse(),
          }),
          {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }
        )
      );

    vi.stubGlobal('fetch', fetchMock);

    const result = await requestFitOrNotDecision({
      userRawInput: '我想买 Anker 10000 毫安的充电宝',
      targetLanguage: 'zh-CN',
      apiBaseUrl: 'https://fitornot-backend-production.up.railway.app',
    });

    expect(result.report).toBe('## report');
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'https://fitornot-backend-production.up.railway.app/api/v1/decision',
      expect.objectContaining({
        method: 'POST',
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/fitornot/decision',
      expect.objectContaining({
        method: 'POST',
      })
    );
  });
});
