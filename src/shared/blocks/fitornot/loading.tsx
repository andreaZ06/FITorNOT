'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, RotateCcw } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Link, useRouter } from '@/core/i18n/navigation';
import { Button } from '@/shared/components/ui/button';

import {
  appendFitOrNotHistoryEntry,
  clearPendingFitOrNotRequest,
  getPendingFitOrNotRequest,
} from './storage';
import { requestFitOrNotDecision } from './request';
import { buildFitOrNotHistoryEntry } from './view-model';

type FitOrNotLoadingProps = {
  entryId: string;
  apiBaseUrl?: string | null;
};

export function FitOrNotLoading({ entryId, apiBaseUrl }: FitOrNotLoadingProps) {
  const t = useTranslations('ai.fitornot');
  const router = useRouter();
  const requestStartedRef = useRef(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(true);
  const [retryCount, setRetryCount] = useState(0);

  const loadingMessages = useMemo(
    () => [
      t('loading.step_collect'),
      t('loading.step_filter'),
      t('loading.step_compare'),
      t('loading.step_finalize'),
    ],
    [t]
  );

  const activeMessage =
    loadingMessages[Math.min(stepIndex, loadingMessages.length - 1)] ??
    t('loading.step_collect');

  useEffect(() => {
    if (errorMessage || !isSubmitting) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setStepIndex((currentValue) =>
        currentValue >= loadingMessages.length - 1 ? 0 : currentValue + 1
      );
    }, 1800);

    return () => window.clearInterval(intervalId);
  }, [errorMessage, isSubmitting, loadingMessages.length]);

  useEffect(() => {
    if (requestStartedRef.current) {
      return;
    }

    requestStartedRef.current = true;

    const pendingRequest = getPendingFitOrNotRequest(entryId);
    if (!pendingRequest) {
      router.push('/fitornot');
      return;
    }

    let isActive = true;

    const runDecisionRequest = async () => {
      try {
        setIsSubmitting(true);
        setErrorMessage(null);

        const decision = await requestFitOrNotDecision({
          userRawInput: pendingRequest.userRawInput,
          targetLanguage: pendingRequest.targetLanguage,
          apiBaseUrl,
        });

        if (!isActive) {
          return;
        }

        appendFitOrNotHistoryEntry(
          buildFitOrNotHistoryEntry({
            id: entryId,
            userRawInput: pendingRequest.userRawInput,
            targetLanguage: pendingRequest.targetLanguage,
            response: decision,
          })
        );
        clearPendingFitOrNotRequest(entryId);
        setIsSubmitting(false);
        router.replace(`/fitornot/result/${entryId}`);
      } catch (error) {
        if (!isActive) {
          return;
        }

        const nextMessage =
          error instanceof Error ? error.message : 'FITorNOT request failed';
        setIsSubmitting(false);
        setErrorMessage(nextMessage);
      }
    };

    void runDecisionRequest();

    return () => {
      isActive = false;
    };
  }, [apiBaseUrl, entryId, retryCount, router]);

  const handleRetry = () => {
    requestStartedRef.current = false;
    setStepIndex(0);
    setIsSubmitting(true);
    setErrorMessage(null);
    setRetryCount((currentValue) => currentValue + 1);
  };

  return (
    <section className="relative flex min-h-screen items-center justify-center overflow-hidden px-5 py-10">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(175,202,226,0.48),_transparent_42%)]" />
      <div className="absolute inset-x-0 top-0 h-40 bg-[linear-gradient(180deg,_rgba(255,255,255,0.7),_transparent)]" />

      <div className="relative mx-auto flex w-full max-w-[920px] flex-col items-center justify-center gap-10 text-center">
        {!errorMessage ? (
          <>
            <div className="relative flex h-[270px] w-[270px] items-center justify-center md:h-[330px] md:w-[330px]">
              <div className="absolute inset-0 rounded-full border border-[#8CA6BD]/20" />
              <div className="absolute inset-[-6%] rounded-full border border-[#8CA6BD]/12" />
              <div className="absolute inset-3 animate-spin rounded-full border-2 border-transparent border-t-[#8CA6BD] border-r-[#8CA6BD]/20" />
              <div className="absolute inset-[18%] rounded-[42%] bg-[linear-gradient(135deg,_rgba(175,202,226,0.82),_rgba(140,166,189,0.94))] blur-2xl" />
            </div>

            <div className="max-w-[620px] space-y-4">
              <p className="text-xs font-semibold tracking-[0.34em] text-slate-400 uppercase">
                FITorNOT
              </p>
              <h1 className="text-3xl font-semibold tracking-tight text-slate-900 md:text-5xl">
                {t('loading.title')}
              </h1>
              <p className="text-lg leading-8 text-slate-500">{activeMessage}</p>
              <p className="text-sm leading-6 text-slate-400">{t('loading.description')}</p>
            </div>

            <div className="flex items-center justify-center gap-2 pt-2">
              <span className="size-2 animate-bounce rounded-full bg-[#8CA6BD] [animation-delay:-0.3s]" />
              <span className="size-2 animate-bounce rounded-full bg-[#8CA6BD] [animation-delay:-0.15s]" />
              <span className="size-2 animate-bounce rounded-full bg-[#8CA6BD]" />
            </div>

            <p className="pt-8 text-[11px] font-medium tracking-[0.4em] text-slate-300 uppercase">
              FITorNOT VERDICT ENGINE ACTIVE
            </p>
          </>
        ) : (
          <div className="w-full max-w-[580px] rounded-[30px] border border-rose-200 bg-white/92 p-6 shadow-[0_24px_48px_rgba(211,223,232,0.35)] backdrop-blur md:p-8">
            <div className="space-y-4 text-left">
              <div className="space-y-2 text-center">
                <p className="text-xs font-semibold tracking-[0.34em] text-slate-400 uppercase">
                  FITorNOT
                </p>
                <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
                  {t('loading.error_title')}
                </h1>
                <p className="text-sm leading-6 text-slate-500">
                  {t('loading.error_description')}
                </p>
              </div>

              <div className="rounded-[20px] border border-rose-200 bg-rose-50/70 px-4 py-4 text-sm leading-6 text-rose-700">
                {errorMessage}
              </div>

              <div className="flex flex-col gap-3 pt-2 sm:flex-row">
                <Button
                  type="button"
                  className="h-11 flex-1 rounded-xl bg-[#8CA6BD] text-white hover:bg-[#486176]"
                  onClick={handleRetry}
                >
                  <RotateCcw data-icon="inline-start" />
                  {t('loading.retry')}
                </Button>
                <Button
                  variant="outline"
                  asChild
                  className="h-11 flex-1 rounded-xl border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                >
                  <Link href="/fitornot">
                    <ArrowLeft data-icon="inline-start" />
                    {t('loading.back')}
                  </Link>
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
