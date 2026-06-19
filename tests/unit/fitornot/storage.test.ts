import { beforeEach, describe, expect, it } from 'vitest';

import {
  appendFitOrNotHistoryEntry,
  getFitOrNotHistoryEntries,
  savePendingFitOrNotRequest,
  getPendingFitOrNotRequest,
  clearPendingFitOrNotRequest,
} from '@/shared/blocks/fitornot/storage';
import type {
  FitOrNotDecisionResponse,
  FitOrNotHistoryEntry,
  FitOrNotPendingRequest,
} from '@/shared/blocks/fitornot/types';

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

function buildResponse(report: string): FitOrNotDecisionResponse {
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
    report,
  };
}

function buildHistoryEntry(
  id: string,
  createdAt: string
): FitOrNotHistoryEntry {
  return {
    id,
    createdAt,
    userRawInput: `query-${id}`,
    targetLanguage: 'zh-CN',
    summaryTitle: `summary-${id}`,
    verdictTone: 'fit',
    response: buildResponse(`report-${id}`),
  };
}

describe('fitornot storage', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'localStorage', {
      value: createMemoryStorage(),
      configurable: true,
    });
    Object.defineProperty(window, 'sessionStorage', {
      value: createMemoryStorage(),
      configurable: true,
    });
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  it('keeps only the latest three history entries in descending order', () => {
    appendFitOrNotHistoryEntry(buildHistoryEntry('1', '2026-06-19T09:00:00.000Z'));
    appendFitOrNotHistoryEntry(buildHistoryEntry('2', '2026-06-19T10:00:00.000Z'));
    appendFitOrNotHistoryEntry(buildHistoryEntry('3', '2026-06-19T11:00:00.000Z'));
    appendFitOrNotHistoryEntry(buildHistoryEntry('4', '2026-06-19T12:00:00.000Z'));

    const entries = getFitOrNotHistoryEntries();

    expect(entries).toHaveLength(3);
    expect(entries.map((entry) => entry.id)).toEqual(['4', '3', '2']);
  });

  it('returns an empty array for invalid history payloads', () => {
    window.localStorage.setItem('fitornot:history:v1', '{not-json');

    expect(getFitOrNotHistoryEntries()).toEqual([]);
  });

  it('stores and clears pending requests by entry id', () => {
    const pending: FitOrNotPendingRequest = {
      id: 'entry-1',
      userRawInput: 'Anker 10000',
      targetLanguage: 'zh-CN',
    };

    savePendingFitOrNotRequest(pending);

    expect(getPendingFitOrNotRequest('entry-1')).toEqual(pending);

    clearPendingFitOrNotRequest('entry-1');

    expect(getPendingFitOrNotRequest('entry-1')).toBeNull();
  });
});
