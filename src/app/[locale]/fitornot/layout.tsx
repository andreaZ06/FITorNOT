import type { ReactNode } from 'react';
import { setRequestLocale } from 'next-intl/server';

function FitOrNotShell({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export default async function FitOrNotLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  return <FitOrNotShell>{children}</FitOrNotShell>;
}
