import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const fromMock = vi.fn();
const selectMock = vi.fn(() => ({ from: fromMock }));

vi.mock('next/cache', () => ({
  revalidateTag: vi.fn(),
  unstable_cache: (fn: (...args: unknown[]) => unknown) => fn,
}));

vi.mock('@/core/db', () => ({
  db: () => ({
    select: selectMock,
  }),
}));

vi.mock('@/shared/services/settings', () => ({
  getAllSettingNames: vi.fn().mockResolvedValue([]),
  publicSettingNames: [],
}));

describe('shared config model', () => {
  beforeEach(() => {
    vi.resetModules();
    fromMock.mockReset();
    selectMock.mockClear();
    process.env.DATABASE_URL = 'postgresql://example.com/db';
    process.env.DATABASE_PROVIDER = 'postgresql';
  });

  afterEach(() => {
    delete process.env.DATABASE_URL;
    delete process.env.DATABASE_PROVIDER;
  });

  it('returns an empty config object when the config table has not been created yet', async () => {
    fromMock.mockRejectedValueOnce(
      new Error('Failed query: select "name", "value" from "config" [cause]: relation "config" does not exist')
    );

    const { getConfigs } = await import('@/shared/models/config');

    await expect(getConfigs()).resolves.toEqual({});
  });
});
