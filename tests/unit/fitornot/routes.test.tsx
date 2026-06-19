import { cleanup, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const setRequestLocaleMock = vi.fn();
const getMetadataMock = vi.fn();
const metadataResolver = vi.fn();

vi.mock('next-intl/server', () => ({
  setRequestLocale: setRequestLocaleMock,
}));

vi.mock('@/shared/lib/seo', () => ({
  getMetadata: getMetadataMock,
}));

vi.mock('@/shared/blocks/fitornot', () => ({
  FitOrNotShell: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="fitornot-shell">{children}</div>
  ),
  FitOrNotSearch: () => <div data-testid="fitornot-search" />,
  FitOrNotLoading: ({ entryId }: { entryId: string }) => (
    <div data-entry-id={entryId} data-testid="fitornot-loading" />
  ),
  FitOrNotResult: ({ entryId }: { entryId: string }) => (
    <div data-entry-id={entryId} data-testid="fitornot-result" />
  ),
}));

describe('FITorNOT standalone routes', () => {
  beforeEach(() => {
    cleanup();
    vi.resetModules();
    setRequestLocaleMock.mockReset();
    getMetadataMock.mockReset();
    metadataResolver.mockReset();
    getMetadataMock.mockReturnValue(metadataResolver);
  });

  it('renders standalone layout content without the landing shell branding', async () => {
    const { default: FitOrNotLayout } = await import('@/app/[locale]/fitornot/layout');

    render(
      await FitOrNotLayout({
        children: <div>Standalone FitOrNot</div>,
        params: Promise.resolve({ locale: 'en' }),
      })
    );

    expect(setRequestLocaleMock).toHaveBeenCalledWith('en');
    expect(screen.getByTestId('fitornot-shell')).toBeInTheDocument();
    expect(screen.getByText('Standalone FitOrNot')).toBeInTheDocument();
    expect(screen.queryByText('ShipAny Two')).not.toBeInTheDocument();
  });

  it('renders the new search entry with FitOrNotSearch', async () => {
    const pageModule = await import('@/app/[locale]/fitornot/page');

    render(
      await pageModule.default({
        params: Promise.resolve({ locale: 'zh' }),
      })
    );

    expect(getMetadataMock).toHaveBeenCalledWith({
      metadataKey: 'ai.fitornot.metadata',
      canonicalUrl: '/fitornot',
    });
    expect(pageModule.generateMetadata).toBe(metadataResolver);
    expect(setRequestLocaleMock).toHaveBeenCalledWith('zh');
    expect(screen.getByTestId('fitornot-search')).toBeInTheDocument();
  });

  it('renders the loading entry with the entryId passed into FitOrNotLoading', async () => {
    const pageModule = await import(
      '@/app/[locale]/fitornot/loading/[entryId]/page'
    );

    render(
      await pageModule.default({
        params: Promise.resolve({ locale: 'en', entryId: 'entry-123' }),
      })
    );

    expect(getMetadataMock).toHaveBeenCalledWith({
      metadataKey: 'ai.fitornot.metadata',
      canonicalUrl: '/fitornot',
      noIndex: true,
    });
    expect(pageModule.generateMetadata).toBe(metadataResolver);
    expect(setRequestLocaleMock).toHaveBeenCalledWith('en');
    expect(screen.getByTestId('fitornot-loading')).toHaveAttribute(
      'data-entry-id',
      'entry-123'
    );
  });

  it('renders the result entry with the entryId passed into FitOrNotResult', async () => {
    const pageModule = await import(
      '@/app/[locale]/fitornot/result/[entryId]/page'
    );

    render(
      await pageModule.default({
        params: Promise.resolve({ locale: 'en', entryId: 'entry-456' }),
      })
    );

    expect(getMetadataMock).toHaveBeenCalledWith({
      metadataKey: 'ai.fitornot.metadata',
      canonicalUrl: '/fitornot',
      noIndex: true,
    });
    expect(pageModule.generateMetadata).toBe(metadataResolver);
    expect(setRequestLocaleMock).toHaveBeenCalledWith('en');
    expect(screen.getByTestId('fitornot-result')).toHaveAttribute(
      'data-entry-id',
      'entry-456'
    );
  });
});
