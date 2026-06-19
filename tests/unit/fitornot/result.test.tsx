import type { ReactNode } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { FitOrNotResult } from '@/shared/blocks/fitornot/result';
import type {
  FitOrNotDecisionResponse,
  FitOrNotHistoryEntry,
} from '@/shared/blocks/fitornot/types';

const pushMock = vi.fn();

vi.mock('next-intl', () => ({
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

function buildResponse(overrides?: Partial<FitOrNotDecisionResponse>): FitOrNotDecisionResponse {
  return {
    slots: {
      category: 'power_bank',
      brand: 'Anker',
      model: '10000',
      urls: [],
    },
    retrieval_plan: {
      ecommerce_query: 'Anker 10000',
      xiaohongshu_queries: ['Anker 10000 发热', 'Anker 10000 上飞机'],
    },
    raw_data: {
      retrieval_plan: {
        ecommerce_query: 'Anker 10000',
        xiaohongshu_queries: ['Anker 10000 发热', 'Anker 10000 上飞机'],
      },
      verified_specs: {
        wh: '37Wh',
        rated_energy: '10000mAh',
      },
      ecommerce_evidence: [],
      xiaohongshu_evidence: [],
      blocked_sources: [],
    },
    cleaned_findings: {
      core_scandals: [
        {
          issue: '机身发热明显',
          evidence: '追评：快充 15 分钟就有点烫手。',
          source: '电商追评',
        },
      ],
      soft_drawbacks: [
        {
          issue: '机身偏厚',
          evidence: '小红书评论：放小包里会鼓起来。',
          source: '小红书真实评论',
        },
      ],
      noise_rate: {
        jd: '0.33',
        xhs: '0.28',
      },
    },
    scenario_fit: {
      user_profile_extracted: '经常坐飞机，希望随身带上机',
      marketing_clash: null,
      suitability_analysis: '37Wh 在常见航司限制内，通常可随身携带。',
    },
    ecommerce_data: [{ title: 'Anker 10000 充电宝' }],
    xiaohongshu_data: [{ note: '真实体验' }],
    social_data: [],
    blocked_sources: [],
    report: '## 航旅结论\n- 可以随身带上飞机。',
    ...overrides,
  };
}

function buildHistoryEntry(
  id: string,
  createdAt: string,
  summaryTitle: string,
  response?: Partial<FitOrNotDecisionResponse>
): FitOrNotHistoryEntry {
  return {
    id,
    createdAt,
    summaryTitle,
    userRawInput: `${summaryTitle} query`,
    targetLanguage: 'zh-CN',
    verdictTone: 'veto',
    response: buildResponse(response),
  };
}

describe('FitOrNotResult', () => {
  beforeEach(() => {
    cleanup();
    pushMock.mockReset();
    Object.defineProperty(window, 'localStorage', {
      value: createMemoryStorage(),
      configurable: true,
    });
  });

  it('renders the current result, opens history, and limits the history list to three entries', async () => {
    window.localStorage.setItem(
      'fitornot:history:v1',
      JSON.stringify([
        buildHistoryEntry('entry-4', '2026-06-19T08:04:00.000Z', 'Fourth'),
        buildHistoryEntry('entry-3', '2026-06-19T08:03:00.000Z', 'Third'),
        buildHistoryEntry('entry-2', '2026-06-19T08:02:00.000Z', 'Second'),
        buildHistoryEntry('entry-1', '2026-06-19T08:01:00.000Z', 'Anker 10000'),
      ])
    );

    render(<FitOrNotResult entryId="entry-1" />);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: 'Anker 10000' })
      ).toBeInTheDocument();
    });

    expect(screen.getByText('37Wh')).toBeInTheDocument();
    expect(screen.getByText(/机身发热明显/i)).toBeInTheDocument();
    expect(screen.getByText(/航旅结论/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /history\.title/i }));

    await waitFor(() => {
      expect(screen.getByText('Fourth')).toBeInTheDocument();
    });

    expect(screen.getByText('Third')).toBeInTheDocument();
    expect(screen.getByText('Second')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Anker 10000/ })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Second/i }));
    expect(pushMock).toHaveBeenCalledWith('/fitornot/result/entry-2');
  });

  it('shows the expired state when the result entry cannot be found', async () => {
    render(<FitOrNotResult entryId="missing-entry" />);

    await waitFor(() => {
      expect(screen.getByText(/result\.empty_title/i)).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: /result\.back_to_search/i })).toHaveAttribute(
      'href',
      '/fitornot'
    );
  });
});
