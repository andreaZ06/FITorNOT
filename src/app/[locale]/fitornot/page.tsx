import { setRequestLocale } from 'next-intl/server';

import { FitOrNotSearch } from '@/shared/blocks/fitornot';
import { getMetadata } from '@/shared/lib/seo';

export const generateMetadata = getMetadata({
  metadataKey: 'ai.fitornot.metadata',
  canonicalUrl: '/fitornot',
});

export default async function FitOrNotSearchPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <FitOrNotSearch />;
}
