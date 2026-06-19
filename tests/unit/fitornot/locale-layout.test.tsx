import { cleanup, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const setRequestLocaleMock = vi.fn();
const getMessagesMock = vi.fn().mockResolvedValue({
  ai: { fitornot: { search: { title: '下单前，先把商品看透' } } },
});
const nextIntlProviderMock = vi.fn(
  ({
    children,
    locale,
  }: {
    children: React.ReactNode;
    locale?: string;
  }) => (
    <div data-locale={locale} data-testid="intl-provider">
      {children}
    </div>
  )
);

vi.mock('next-intl', () => ({
  hasLocale: () => true,
  NextIntlClientProvider: (props: {
    children: React.ReactNode;
    locale?: string;
  }) => nextIntlProviderMock(props),
}));

vi.mock('next-intl/server', () => ({
  getMessages: getMessagesMock,
  setRequestLocale: setRequestLocaleMock,
}));

vi.mock('@/core/theme/provider', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/shared/contexts/app', () => ({
  AppContextProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/shared/components/ui/sonner', () => ({
  Toaster: () => <div data-testid="fitornot-toaster" />,
}));

describe('LocaleLayout', () => {
  beforeEach(() => {
    cleanup();
    setRequestLocaleMock.mockReset();
    getMessagesMock.mockClear();
    nextIntlProviderMock.mockClear();
  });

  it('passes the active locale into the NextIntl client provider', async () => {
    const { default: LocaleLayout } = await import('@/app/[locale]/layout');

    render(
      await LocaleLayout({
        children: <div>FITorNOT locale shell</div>,
        params: Promise.resolve({ locale: 'zh' }),
      })
    );

    expect(setRequestLocaleMock).toHaveBeenCalledWith('zh');
    expect(getMessagesMock).toHaveBeenCalledWith({ locale: 'zh' });
    expect(nextIntlProviderMock).toHaveBeenCalledWith(
      expect.objectContaining({
        locale: 'zh',
        messages: {
          ai: { fitornot: { search: { title: '下单前，先把商品看透' } } },
        },
      })
    );
    expect(screen.getByTestId('intl-provider')).toHaveAttribute('data-locale', 'zh');
    expect(screen.getByText('FITorNOT locale shell')).toBeInTheDocument();
  });
});
