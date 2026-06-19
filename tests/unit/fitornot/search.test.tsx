import type { ReactNode } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FitOrNotSearch } from '@/shared/blocks/fitornot/search';

const pushMock = vi.fn();

vi.mock('nanoid', () => ({
  nanoid: () => 'entry-123',
}));

vi.mock('next-intl', () => ({
  useLocale: () => 'zh',
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/core/i18n/navigation', () => ({
  Link: ({ children, href }: { children: ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
  useRouter: () => ({
    push: pushMock,
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

describe('FitOrNotSearch', () => {
  beforeEach(() => {
    cleanup();
    pushMock.mockReset();
    Object.defineProperty(window, 'localStorage', {
      value: createMemoryStorage(),
      configurable: true,
    });
    Object.defineProperty(window, 'sessionStorage', {
      value: createMemoryStorage(),
      configurable: true,
    });
  });

  it('saves the pending request and routes to the loading page on submit', () => {
    render(<FitOrNotSearch />);

    fireEvent.change(screen.getByPlaceholderText(/search\.prompt_placeholder/i), {
      target: {
        value: '我想买 Anker 10000 毫安充电宝',
      },
    });
    fireEvent.change(screen.getByPlaceholderText(/search\.link_placeholder/i), {
      target: {
        value: 'https://item.jd.com/100241293249.html',
      },
    });
    fireEvent.click(screen.getByRole('button', { name: /search\.submit/i }));

    expect(pushMock).toHaveBeenCalledWith('/fitornot/loading/entry-123');
    expect(
      JSON.parse(
        window.sessionStorage.getItem('fitornot:pending:entry-123') || 'null'
      )
    ).toEqual({
      id: 'entry-123',
      userRawInput: '我想买 Anker 10000 毫安充电宝\nhttps://item.jd.com/100241293249.html',
      targetLanguage: 'zh-CN',
    });
  });

  it('shows platform detection pills based on the current input', () => {
    render(<FitOrNotSearch />);

    fireEvent.change(screen.getByPlaceholderText(/search\.prompt_placeholder/i), {
      target: {
        value:
          '我在看 https://item.jd.com/100241293249.html 和 https://www.xiaohongshu.com/explore/demo',
      },
    });

    expect(screen.getByText(/京东/i)).toBeInTheDocument();
    expect(screen.getByText(/小红书/i)).toBeInTheDocument();
  });

  it('opens the history sheet from the search page', () => {
    window.localStorage.setItem(
      'fitornot:history:v1',
      JSON.stringify([
        {
          id: 'entry-1',
          createdAt: '2026-06-19T08:01:00.000Z',
          userRawInput: 'Anker 10000 query',
          targetLanguage: 'zh-CN',
          summaryTitle: 'Anker 10000',
          verdictTone: 'fit',
          response: {
            slots: {
              category: 'power_bank',
              brand: 'Anker',
              model: '10000',
              urls: [],
            },
            retrieval_plan: {
              ecommerce_query: 'Anker 10000',
              xiaohongshu_queries: [],
            },
            raw_data: {
              retrieval_plan: {
                ecommerce_query: 'Anker 10000',
                xiaohongshu_queries: [],
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
              user_profile_extracted: 'travel',
              marketing_clash: null,
              suitability_analysis: 'fit',
            },
            ecommerce_data: [],
            xiaohongshu_data: [],
            social_data: [],
            blocked_sources: [],
            report: 'report',
          },
        },
      ])
    );

    render(<FitOrNotSearch />);

    fireEvent.click(screen.getByRole('button', { name: /history\.title/i }));

    expect(screen.getByText('Anker 10000')).toBeInTheDocument();
  });
});
