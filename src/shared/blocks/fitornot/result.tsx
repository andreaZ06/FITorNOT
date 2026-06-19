'use client';

import type { ComponentType } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, History, Search, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Link } from '@/core/i18n/navigation';
import { MarkdownPreview } from '@/shared/blocks/common';
import { Badge } from '@/shared/components/ui/badge';
import { Button } from '@/shared/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card';

import { FitOrNotHistorySheet } from './history-sheet';
import { getFitOrNotHistoryEntries, MAX_HISTORY_ENTRIES } from './storage';
import type { FitOrNotHistoryEntry, FitOrNotVerdictTone } from './types';
import { getFitOrNotVerdictTone } from './view-model';

const BADGE_VARIANTS: Record<
  FitOrNotVerdictTone,
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  veto: 'destructive',
  caution: 'secondary',
  fit: 'default',
  unknown: 'outline',
};

const BANNER_STYLES: Record<
  FitOrNotVerdictTone,
  {
    container: string;
    icon: ComponentType<{ className?: string }>;
  }
> = {
  veto: {
    container: 'border-destructive/30 bg-destructive/10',
    icon: ShieldAlert,
  },
  caution: {
    container: 'border-amber-500/30 bg-amber-500/10',
    icon: ShieldQuestion,
  },
  fit: {
    container: 'border-emerald-500/30 bg-emerald-500/10',
    icon: ShieldCheck,
  },
  unknown: {
    container: 'border-border bg-muted/50',
    icon: ShieldQuestion,
  },
};

type FitOrNotResultProps = {
  entryId: string;
};

function formatSpecValue(value: unknown) {
  if (value === null || value === undefined) {
    return '-';
  }

  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  return JSON.stringify(value);
}

function QueryMetaCard({
  title,
  value,
}: {
  title: string;
  value: string | number;
}) {
  return (
    <div className="bg-muted/70 rounded-lg px-4 py-3">
      <p className="text-muted-foreground text-xs uppercase">{title}</p>
      <p className="mt-2 text-sm font-medium break-words">{value}</p>
    </div>
  );
}

export function FitOrNotResult({ entryId }: FitOrNotResultProps) {
  const t = useTranslations('ai.fitornot');
  const [currentEntry, setCurrentEntry] = useState<FitOrNotHistoryEntry | null | undefined>(
    undefined
  );

  useEffect(() => {
    const historyEntries = getFitOrNotHistoryEntries();
    setCurrentEntry(historyEntries.find((entry) => entry.id === entryId) ?? null);
  }, [entryId]);

  const historyEntries = useMemo(
    () => getFitOrNotHistoryEntries().slice(0, MAX_HISTORY_ENTRIES),
    [currentEntry]
  );

  if (currentEntry === undefined) {
    return (
      <section className="py-16">
        <div className="container">
          <div className="mx-auto max-w-5xl">
            <Card>
              <CardContent className="flex flex-col gap-4 py-8">
                <div className="bg-muted h-8 w-48 animate-pulse rounded-md" />
                <div className="bg-muted h-24 animate-pulse rounded-lg" />
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="bg-muted h-48 animate-pulse rounded-lg" />
                  <div className="bg-muted h-48 animate-pulse rounded-lg" />
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>
    );
  }

  if (!currentEntry) {
    return (
      <section className="py-16">
        <div className="container">
          <div className="mx-auto flex max-w-3xl flex-col gap-6 text-center">
            <div className="space-y-2">
              <p className="text-muted-foreground text-sm tracking-[0.3em] uppercase">
                FITorNOT
              </p>
              <h1 className="text-3xl font-semibold tracking-tight">
                {t('result.empty_title')}
              </h1>
              <p className="text-muted-foreground">{t('result.empty_description')}</p>
            </div>
            <div className="flex justify-center">
              <Button asChild>
                <Link href="/fitornot">{t('result.back_to_search')}</Link>
              </Button>
            </div>
          </div>
        </div>
      </section>
    );
  }

  const verdictTone = getFitOrNotVerdictTone(currentEntry.response);
  const bannerStyle = BANNER_STYLES[verdictTone];
  const BannerIcon = bannerStyle.icon;
  const verifiedSpecs = Object.entries(currentEntry.response.raw_data.verified_specs || {});
  const blockedSourcesCount =
    currentEntry.response.blocked_sources.length +
    currentEntry.response.raw_data.blocked_sources.length;

  return (
    <section className="py-10 md:py-14">
      <div className="container">
        <div className="mx-auto flex max-w-6xl flex-col gap-6">
          <div className="flex flex-col gap-4 rounded-2xl border px-5 py-4 md:flex-row md:items-center md:justify-between">
            <div className="space-y-1">
              <p className="text-muted-foreground text-xs tracking-[0.28em] uppercase">
                FITorNOT
              </p>
              <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
                {currentEntry.summaryTitle}
              </h1>
            </div>
            <div className="flex flex-wrap gap-3">
              <FitOrNotHistorySheet
                trigger={
                  <Button variant="outline" type="button">
                    <History data-icon="inline-start" />
                    {t('history.title')}
                  </Button>
                }
              />
              <Button asChild variant="outline">
                <Link href="/fitornot">
                  <Search data-icon="inline-start" />
                  {t('result.new_search')}
                </Link>
              </Button>
            </div>
          </div>

          <div className={`rounded-2xl border px-5 py-5 ${bannerStyle.container}`}>
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="flex items-start gap-3">
                <BannerIcon className="mt-0.5 size-5" />
                <div className="space-y-1">
                  <p className="text-sm font-medium">{t(`result.verdict_${verdictTone}`)}</p>
                  <p className="text-muted-foreground text-sm">
                    {currentEntry.response.scenario_fit.suitability_analysis}
                  </p>
                </div>
              </div>
              <Badge variant={BADGE_VARIANTS[verdictTone]}>
                {t(`history.verdict_${verdictTone}`)}
              </Badge>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-4">
            <QueryMetaCard
              title={t('result.plan_query')}
              value={currentEntry.response.retrieval_plan.ecommerce_query || '-'}
            />
            <QueryMetaCard
              title={t('result.plan_xhs')}
              value={currentEntry.response.retrieval_plan.xiaohongshu_queries.join(' / ') || '-'}
            />
            <QueryMetaCard
              title={t('result.hit_count')}
              value={
                currentEntry.response.ecommerce_data.length +
                currentEntry.response.xiaohongshu_data.length
              }
            />
            <QueryMetaCard
              title={t('result.blocked_sources')}
              value={blockedSourcesCount}
            />
          </div>

          <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="flex flex-col gap-6">
              <Card className="border-border/60 shadow-sm">
                <CardHeader>
                  <CardTitle>{t('result.specs_title')}</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3">
                  {verifiedSpecs.length === 0 ? (
                    <p className="text-muted-foreground text-sm">{t('result.no_specs')}</p>
                  ) : (
                    verifiedSpecs.map(([key, value]) => (
                      <div
                        key={key}
                        className="bg-muted/60 flex items-start justify-between gap-4 rounded-lg px-4 py-3"
                      >
                        <span className="text-muted-foreground text-sm">{key}</span>
                        <span className="max-w-[60%] text-right text-sm font-medium break-words">
                          {formatSpecValue(value)}
                        </span>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card className="border-border/60 shadow-sm">
                <CardHeader>
                  <CardTitle>{t('result.query_meta_title')}</CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3">
                  <div className="bg-muted/60 rounded-lg px-4 py-3 text-sm">
                    <p className="text-muted-foreground">{t('result.user_input')}</p>
                    <p className="mt-2 break-words">{currentEntry.userRawInput}</p>
                  </div>
                  <div className="bg-muted/60 rounded-lg px-4 py-3 text-sm">
                    <p className="text-muted-foreground">{t('result.user_language')}</p>
                    <p className="mt-2">{currentEntry.targetLanguage}</p>
                  </div>
                  <div className="bg-muted/60 rounded-lg px-4 py-3 text-sm">
                    <p className="text-muted-foreground">{t('result.user_profile')}</p>
                    <p className="mt-2">
                      {currentEntry.response.scenario_fit.user_profile_extracted}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="flex flex-col gap-6">
              <Card className="border-border/60 shadow-sm">
                <CardHeader>
                  <CardTitle>{t('result.risks_title')}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-3">
                    <p className="text-sm font-medium">{t('result.core_scandals')}</p>
                    {currentEntry.response.cleaned_findings.core_scandals.length === 0 ? (
                      <p className="text-muted-foreground text-sm">{t('result.no_core_scandals')}</p>
                    ) : (
                      currentEntry.response.cleaned_findings.core_scandals.map((item) => (
                        <div
                          key={`${item.issue}-${item.source}`}
                          className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3"
                        >
                          <p className="font-medium">{item.issue}</p>
                          <p className="text-muted-foreground mt-2 text-sm">{item.evidence}</p>
                          <p className="mt-2 text-xs">{item.source}</p>
                        </div>
                      ))
                    )}
                  </div>

                  <div className="space-y-3">
                    <p className="text-sm font-medium">{t('result.soft_drawbacks')}</p>
                    {currentEntry.response.cleaned_findings.soft_drawbacks.length === 0 ? (
                      <p className="text-muted-foreground text-sm">{t('result.no_soft_drawbacks')}</p>
                    ) : (
                      currentEntry.response.cleaned_findings.soft_drawbacks.map((item) => (
                        <div
                          key={`${item.issue}-${item.source}`}
                          className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3"
                        >
                          <p className="font-medium">{item.issue}</p>
                          <p className="text-muted-foreground mt-2 text-sm">{item.evidence}</p>
                          <p className="mt-2 text-xs">{item.source}</p>
                        </div>
                      ))
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>

          <Card className="border-border/60 shadow-sm">
            <CardHeader>
              <CardTitle>{t('result.report_title')}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="rounded-xl border p-4">
                <MarkdownPreview content={currentEntry.response.report} />
              </div>
            </CardContent>
          </Card>

          {historyEntries.length > 0 && (
            <div className="flex items-center justify-between text-sm">
              <Button asChild variant="ghost" className="px-0">
                <Link href="/fitornot">
                  <ArrowLeft data-icon="inline-start" />
                  {t('result.back_to_search')}
                </Link>
              </Button>
              <p className="text-muted-foreground">{t('result.history_hint')}</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
