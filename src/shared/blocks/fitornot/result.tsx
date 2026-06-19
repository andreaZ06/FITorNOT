'use client';

import type { ComponentType, ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, History, Search, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Link } from '@/core/i18n/navigation';
import { MarkdownPreview } from '@/shared/blocks/common';
import { Badge } from '@/shared/components/ui/badge';
import { Button } from '@/shared/components/ui/button';

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
    badge: string;
    icon: ComponentType<{ className?: string }>;
    panel: string;
  }
> = {
  veto: {
    badge: 'bg-rose-100 text-rose-700',
    icon: ShieldAlert,
    panel: 'border-rose-200 bg-rose-50/70',
  },
  caution: {
    badge: 'bg-amber-100 text-amber-700',
    icon: ShieldQuestion,
    panel: 'border-amber-200 bg-amber-50/70',
  },
  fit: {
    badge: 'bg-emerald-100 text-emerald-700',
    icon: ShieldCheck,
    panel: 'border-emerald-200 bg-emerald-50/70',
  },
  unknown: {
    badge: 'bg-slate-100 text-slate-600',
    icon: ShieldQuestion,
    panel: 'border-slate-200 bg-slate-50/80',
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

function SurfacePanel({
  children,
  className = '',
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-[28px] border border-slate-200 bg-white p-5 shadow-[0_16px_36px_rgba(211,223,232,0.28)] md:p-6 ${className}`.trim()}
    >
      {children}
    </div>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="text-lg font-semibold text-slate-900">{children}</h2>;
}

function QueryMetaCard({
  title,
  value,
}: {
  title: string;
  value: string | number;
}) {
  return (
    <div className="rounded-[20px] bg-white px-4 py-4 shadow-[0_10px_20px_rgba(211,223,232,0.2)] ring-1 ring-slate-200/80">
      <p className="text-xs font-medium tracking-[0.18em] text-slate-400 uppercase">{title}</p>
      <p className="mt-3 text-sm font-semibold break-words text-slate-700">{value}</p>
    </div>
  );
}

function EmptyResultState({ title, description, backLabel }: { title: string; description: string; backLabel: string }) {
  return (
    <section className="px-5 py-16 md:px-10">
      <div className="mx-auto flex max-w-[720px] flex-col gap-6 text-center">
        <div className="space-y-3">
          <p className="text-sm font-semibold tracking-[0.28em] text-slate-400 uppercase">
            FITorNOT
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-900">{title}</h1>
          <p className="text-base leading-7 text-slate-500">{description}</p>
        </div>
        <div className="flex justify-center">
          <Button
            asChild
            className="h-11 rounded-xl bg-[#8CA6BD] px-6 text-white hover:bg-[#486176]"
          >
            <Link href="/fitornot">{backLabel}</Link>
          </Button>
        </div>
      </div>
    </section>
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
      <section className="px-5 py-10 md:px-10">
        <div className="mx-auto flex max-w-[1120px] flex-col gap-6">
          <SurfacePanel className="space-y-4">
            <div className="h-6 w-32 animate-pulse rounded-full bg-slate-200" />
            <div className="h-10 w-72 animate-pulse rounded-2xl bg-slate-200" />
            <div className="grid gap-4 md:grid-cols-2">
              <div className="h-44 animate-pulse rounded-[22px] bg-slate-100" />
              <div className="h-44 animate-pulse rounded-[22px] bg-slate-100" />
            </div>
          </SurfacePanel>
        </div>
      </section>
    );
  }

  if (!currentEntry) {
    return (
      <EmptyResultState
        title={t('result.empty_title')}
        description={t('result.empty_description')}
        backLabel={t('result.back_to_search')}
      />
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
    <section className="px-5 py-8 md:px-10 md:py-10">
      <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-6">
        <div className="flex flex-col gap-4 rounded-[24px] border border-slate-200 bg-white/88 px-5 py-4 shadow-[0_16px_36px_rgba(211,223,232,0.28)] backdrop-blur md:flex-row md:items-center md:justify-between">
          <div className="space-y-1">
            <p className="text-xs font-semibold tracking-[0.28em] text-slate-400 uppercase">
              FITorNOT
            </p>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900 md:text-3xl">
              {currentEntry.summaryTitle}
            </h1>
          </div>
          <div className="flex flex-wrap gap-3">
            <FitOrNotHistorySheet
              trigger={
                <Button
                  variant="outline"
                  type="button"
                  className="rounded-full border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                >
                  <History data-icon="inline-start" />
                  {t('history.title')}
                </Button>
              }
            />
            <Button
              asChild
              variant="outline"
              className="rounded-full border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
            >
              <Link href="/fitornot">
                <Search data-icon="inline-start" />
                {t('result.new_search')}
              </Link>
            </Button>
          </div>
        </div>

        <div className={`rounded-[28px] border px-5 py-5 md:px-6 md:py-6 ${bannerStyle.panel}`}>
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div className="flex items-start gap-3">
              <div className={`rounded-full p-2 ${bannerStyle.badge}`}>
                <BannerIcon className="size-5" />
              </div>
              <div className="space-y-2">
                <p className="text-sm font-semibold tracking-[0.18em] text-slate-500 uppercase">
                  {t(`result.verdict_${verdictTone}`)}
                </p>
                <p className="text-base leading-7 text-slate-700">
                  {currentEntry.response.scenario_fit.suitability_analysis}
                </p>
              </div>
            </div>
            <Badge variant={BADGE_VARIANTS[verdictTone]}>
              {t(`history.verdict_${verdictTone}`)}
            </Badge>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
          <QueryMetaCard title={t('result.blocked_sources')} value={blockedSourcesCount} />
        </div>

        <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
          <div className="flex flex-col gap-6">
            <SurfacePanel>
              <div className="space-y-4">
                <SectionTitle>{t('result.specs_title')}</SectionTitle>
                <div className="grid gap-3">
                  {verifiedSpecs.length === 0 ? (
                    <p className="text-sm leading-6 text-slate-500">{t('result.no_specs')}</p>
                  ) : (
                    verifiedSpecs.map(([key, value]) => (
                      <div
                        key={key}
                        className="flex items-start justify-between gap-4 rounded-[18px] bg-slate-50 px-4 py-3"
                      >
                        <span className="text-sm text-slate-400">{key}</span>
                        <span className="max-w-[60%] text-right text-sm font-semibold break-words text-slate-700">
                          {formatSpecValue(value)}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </SurfacePanel>

            <SurfacePanel>
              <div className="space-y-4">
                <SectionTitle>{t('result.query_meta_title')}</SectionTitle>
                <div className="grid gap-3">
                  <div className="rounded-[18px] bg-slate-50 px-4 py-3 text-sm">
                    <p className="text-slate-400">{t('result.user_input')}</p>
                    <p className="mt-2 leading-6 break-words text-slate-700">
                      {currentEntry.userRawInput}
                    </p>
                  </div>
                  <div className="rounded-[18px] bg-slate-50 px-4 py-3 text-sm">
                    <p className="text-slate-400">{t('result.user_language')}</p>
                    <p className="mt-2 text-slate-700">{currentEntry.targetLanguage}</p>
                  </div>
                  <div className="rounded-[18px] bg-slate-50 px-4 py-3 text-sm">
                    <p className="text-slate-400">{t('result.user_profile')}</p>
                    <p className="mt-2 leading-6 text-slate-700">
                      {currentEntry.response.scenario_fit.user_profile_extracted}
                    </p>
                  </div>
                </div>
              </div>
            </SurfacePanel>
          </div>

          <div className="flex flex-col gap-6">
            <SurfacePanel>
              <div className="space-y-5">
                <SectionTitle>{t('result.risks_title')}</SectionTitle>

                <div className="space-y-3">
                  <p className="text-sm font-semibold text-slate-800">
                    {t('result.core_scandals')}
                  </p>
                  {currentEntry.response.cleaned_findings.core_scandals.length === 0 ? (
                    <p className="text-sm leading-6 text-slate-500">
                      {t('result.no_core_scandals')}
                    </p>
                  ) : (
                    currentEntry.response.cleaned_findings.core_scandals.map((item) => (
                      <div
                        key={`${item.issue}-${item.source}`}
                        className="rounded-[18px] border border-rose-200 bg-rose-50/70 px-4 py-4"
                      >
                        <p className="font-semibold text-slate-800">{item.issue}</p>
                        <p className="mt-2 text-sm leading-6 text-slate-500">{item.evidence}</p>
                        <p className="mt-2 text-xs text-slate-400">{item.source}</p>
                      </div>
                    ))
                  )}
                </div>

                <div className="space-y-3">
                  <p className="text-sm font-semibold text-slate-800">
                    {t('result.soft_drawbacks')}
                  </p>
                  {currentEntry.response.cleaned_findings.soft_drawbacks.length === 0 ? (
                    <p className="text-sm leading-6 text-slate-500">
                      {t('result.no_soft_drawbacks')}
                    </p>
                  ) : (
                    currentEntry.response.cleaned_findings.soft_drawbacks.map((item) => (
                      <div
                        key={`${item.issue}-${item.source}`}
                        className="rounded-[18px] border border-amber-200 bg-amber-50/70 px-4 py-4"
                      >
                        <p className="font-semibold text-slate-800">{item.issue}</p>
                        <p className="mt-2 text-sm leading-6 text-slate-500">{item.evidence}</p>
                        <p className="mt-2 text-xs text-slate-400">{item.source}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </SurfacePanel>
          </div>
        </div>

        <SurfacePanel>
          <div className="space-y-4">
            <SectionTitle>{t('result.report_title')}</SectionTitle>
            <div className="rounded-[20px] border border-slate-200 bg-white px-4 py-4">
              <MarkdownPreview content={currentEntry.response.report} />
            </div>
          </div>
        </SurfacePanel>

        {historyEntries.length > 0 && (
          <div className="flex flex-col gap-3 text-sm md:flex-row md:items-center md:justify-between">
            <Button asChild variant="ghost" className="w-fit px-0 text-slate-600 hover:bg-transparent">
              <Link href="/fitornot">
                <ArrowLeft data-icon="inline-start" />
                {t('result.back_to_search')}
              </Link>
            </Button>
            <p className="text-slate-400">{t('result.history_hint')}</p>
          </div>
        )}
      </div>
    </section>
  );
}
