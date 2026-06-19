import { setRequestLocale } from 'next-intl/server';

import { FitOrNotResult } from '@/shared/blocks/fitornot';
import { getMetadata } from '@/shared/lib/seo';

export const generateMetadata = getMetadata({
  metadataKey: 'ai.fitornot.metadata',
  canonicalUrl: '/fitornot',
  noIndex: true,
});

export default async function FitOrNotResultPage({
  params,
}: {
  params: Promise<{ locale: string; entryId: string }>;
}) {
  const { locale, entryId } = await params;
  setRequestLocale(locale);

  return <FitOrNotResult entryId={entryId} />;
}
