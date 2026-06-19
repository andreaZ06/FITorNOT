import type { ReactNode } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FitOrNotLoading } from '@/shared/blocks/fitornot/loading';
import type { FitOrNotDecisionResponse } from '@/shared/blocks/fitornot/types';

const pushMock = vi.fn();
const replaceMock = vi.fn();

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/core/i18n/navigation', () => ({
  Link: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
  }),
}));

function createMemoryStorage(): Storage {
  const storage = new Map<string, string>();

  return {
    get length() {
      return storage.size;
    },
    clear() {
      storage.clear();
    },
    getItem(key: string) {
      return storage.get(key) ?? null;
    },
    key(index: number) {
      return Array.from(storage.keys())[index] ?? null;
    },
    removeItem(key: string) {
      storage.delete(key);
    },
    setItem(key: string, value: string) {
      storage.set(key, value);
    },
  };
}

function buildResponse(overrides?: Partial<FitOrNotDecisionResponse>): FitOrNotDecisionResponse {
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
    ...overrides,
  };
}

describe('FitOrNotLoading', () => {
  beforeEach(() => {
    cleanup();
    pushMock.mockReset();
    replaceMock.mockReset();
    Object.defineProperty(window, 'localStorage', {
      value: createMemoryStorage(),
      configurable: true,
    });
    Object.defineProperty(window, 'sessionStorage', {
      value: createMemoryStorage(),
      configurable: true,
    });
    vi.restoreAllMocks();
  });

  it('submits the pending request, stores history, and routes to the result page on success', async () => {
    window.sessionStorage.setItem(
      'fitornot:pending:entry-1',
      JSON.stringify({
        id: 'entry-1',
        userRawInput: '我想买 Anker 10000 毫安的充电宝',
        targetLanguage: 'zh-CN',
      })
    );
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
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
      )
    );

    render(<FitOrNotLoading entryId="entry-1" />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith('/fitornot/result/entry-1');
    });

    expect(
      JSON.parse(window.localStorage.getItem('fitornot:history:v1') || '[]')
    ).toHaveLength(1);
    expect(window.sessionStorage.getItem('fitornot:pending:entry-1')).toBeNull();
  });

  it('shows an error state and keeps the pending request when the request fails', async () => {
    window.sessionStorage.setItem(
      'fitornot:pending:entry-2',
      JSON.stringify({
        id: 'entry-2',
        userRawInput: 'query',
        targetLanguage: 'zh-CN',
      })
    );
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: -1, message: 'backend failed' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    );

    render(<FitOrNotLoading entryId="entry-2" />);

    await waitFor(() => {
      expect(screen.getByText(/backend failed/i)).toBeInTheDocument();
    });

    expect(replaceMock).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem('fitornot:pending:entry-2')).not.toBeNull();
  });

  it('retries the request from the loading page after a failure', async () => {
    window.sessionStorage.setItem(
      'fitornot:pending:entry-3',
      JSON.stringify({
        id: 'entry-3',
        userRawInput: 'query',
        targetLanguage: 'zh-CN',
      })
    );

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ code: -1, message: 'backend failed' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        })
      )
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

    render(<FitOrNotLoading entryId="entry-3" />);

    await waitFor(() => {
      expect(screen.getByText(/backend failed/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /loading\.retry/i }));

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith('/fitornot/result/entry-3');
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(window.sessionStorage.getItem('fitornot:pending:entry-3')).toBeNull();
  });

  it('routes back to the search page when the pending request is missing', async () => {
    render(<FitOrNotLoading entryId="missing-entry" />);

    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/fitornot');
    });
  });

  it('renders the redesigned loading screen instead of the generic progress card', async () => {
    window.sessionStorage.setItem(
      'fitornot:pending:entry-visual',
      JSON.stringify({
        id: 'entry-visual',
        userRawInput: 'query',
        targetLanguage: 'zh-CN',
      })
    );
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: -1, message: 'backend failed' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    );

    render(<FitOrNotLoading entryId="entry-visual" />);

    expect(screen.getByText(/loading\.title/i)).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /loading\.retry/i })).toBeInTheDocument();
    });
  });
});
