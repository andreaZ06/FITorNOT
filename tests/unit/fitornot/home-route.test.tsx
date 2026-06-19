import { beforeEach, describe, expect, it, vi } from 'vitest';

const redirectMock = vi.fn();
const setRequestLocaleMock = vi.fn();
const getTranslationsMock = vi.fn();
const getThemePageMock = vi.fn();

vi.mock('@/core/i18n/navigation', () => ({
  redirect: redirectMock,
}));

vi.mock('next-intl/server', () => ({
  getTranslations: getTranslationsMock,
  setRequestLocale: setRequestLocaleMock,
}));

vi.mock('@/core/theme', () => ({
  getThemePage: getThemePageMock,
}));

describe('FITorNOT locale home route', () => {
  beforeEach(() => {
    vi.resetModules();
    redirectMock.mockReset();
    setRequestLocaleMock.mockReset();
    getTranslationsMock.mockReset();
    getThemePageMock.mockReset();

    getTranslationsMock.mockResolvedValue({
      raw: vi.fn().mockReturnValue({}),
    });
    getThemePageMock.mockResolvedValue(() => null);
  });

  it('redirects the locale root route to the standalone fitornot entry', async () => {
    const { default: LandingPage } = await import('@/app/[locale]/(landing)/page');

    await LandingPage({
      params: Promise.resolve({ locale: 'zh' }),
    });

    expect(setRequestLocaleMock).toHaveBeenCalledWith('zh');
    expect(redirectMock).toHaveBeenCalledWith({
      href: '/fitornot',
      locale: 'zh',
    });
  });
});
