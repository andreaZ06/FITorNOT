'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, ArrowLeft, LoaderCircle, RotateCcw } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { Link, useRouter } from '@/core/i18n/navigation';
import { Button } from '@/shared/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card';
import { Progress } from '@/shared/components/ui/progress';
import { Skeleton } from '@/shared/components/ui/skeleton';

import {
  appendFitOrNotHistoryEntry,
  clearPendingFitOrNotRequest,
  getPendingFitOrNotRequest,
} from './storage';
import type { FitOrNotDecisionResponse } from './types';
import { buildFitOrNotHistoryEntry } from './view-model';

const LOADING_STEPS = [22, 51, 76, 92];

type FitOrNotDecisionRouteResponse = {
  code?: number;
  message?: string;
  data?: FitOrNotDecisionResponse;
};

type FitOrNotLoadingProps = {
  entryId: string;
};

export function FitOrNotLoading({ entryId }: FitOrNotLoadingProps) {
  const t = useTranslations('ai.fitornot');
  const router = useRouter();
  const requestStartedRef = useRef(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(true);
  const [retryCount, setRetryCount] = useState(0);

  const loadingProgress = useMemo(
    () => LOADING_STEPS[Math.min(stepIndex, LOADING_STEPS.length - 1)] ?? 22,
    [stepIndex]
  );

  useEffect(() => {
    if (errorMessage || !isSubmitting) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setStepIndex((currentValue) =>
        currentValue >= LOADING_STEPS.length - 1 ? 0 : currentValue + 1
      );
    }, 1200);

    return () => window.clearInterval(intervalId);
  }, [errorMessage, isSubmitting]);

  useEffect(() => {
    if (requestStartedRef.current) {
      return;
    }

    requestStartedRef.current = true;

    const pendingRequest = getPendingFitOrNotRequest(entryId);
    if (!pendingRequest) {
      setIsSubmitting(false);
      router.push('/fitornot');
      return;
    }

    let isActive = true;

    const runDecisionRequest = async () => {
      try {
        setIsSubmitting(true);
        setErrorMessage(null);

        const response = await fetch('/api/fitornot/decision', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            userRawInput: pendingRequest.userRawInput,
            targetLanguage: pendingRequest.targetLanguage,
          }),
        });

        const payload = (await response.json()) as FitOrNotDecisionRouteResponse;
        if (!response.ok || payload.code !== 0 || !payload.data) {
          throw new Error(payload.message || 'FITorNOT request failed');
        }

        if (!isActive) {
          return;
        }

        appendFitOrNotHistoryEntry(
          buildFitOrNotHistoryEntry({
            id: entryId,
            userRawInput: pendingRequest.userRawInput,
            targetLanguage: pendingRequest.targetLanguage,
            response: payload.data,
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
  }, [entryId, retryCount, router]);

  const handleRetry = () => {
    requestStartedRef.current = false;
    setStepIndex(0);
    setIsSubmitting(true);
    setErrorMessage(null);
    setRetryCount((currentValue) => currentValue + 1);
  };

  return (
    <section className="flex min-h-[calc(100vh-4rem)] items-center justify-center py-16">
      <div className="container">
        <div className="mx-auto flex max-w-3xl flex-col gap-6">
          <div className="space-y-2 text-center">
            <p className="text-muted-foreground text-sm tracking-[0.3em] uppercase">
              FITorNOT
            </p>
            <h1 className="text-3xl font-semibold tracking-tight md:text-5xl">
              {t('loading.title')}
            </h1>
            <p className="text-muted-foreground mx-auto max-w-2xl text-sm md:text-base">
              {errorMessage ? t('loading.error_description') : t('loading.description')}
            </p>
          </div>

          <Card className="border-border/60 shadow-sm">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-3 text-lg font-medium">
                {errorMessage ? (
                  <AlertCircle className="text-destructive size-5" />
                ) : (
                  <LoaderCircle className="text-primary size-5 animate-spin" />
                )}
                {errorMessage ? t('loading.error_title') : t('loading.status_title')}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-5">
              {errorMessage ? (
                <>
                  <div className="bg-destructive/8 text-destructive rounded-lg border px-4 py-3 text-sm">
                    {errorMessage}
                  </div>
                  <div className="flex flex-col gap-3 sm:flex-row">
                    <Button type="button" className="sm:flex-1" onClick={handleRetry}>
                      <RotateCcw data-icon="inline-start" />
                      {t('loading.retry')}
                    </Button>
                    <Button variant="outline" asChild className="sm:flex-1">
                      <Link href="/fitornot">
                        <ArrowLeft data-icon="inline-start" />
                        {t('loading.back')}
                      </Link>
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <div className="space-y-3">
                    <Progress value={loadingProgress} />
                    <div className="grid gap-3 md:grid-cols-3">
                      <Skeleton className="h-20" />
                      <Skeleton className="h-20" />
                      <Skeleton className="h-20" />
                    </div>
                  </div>
                  <div className="grid gap-3 text-sm sm:grid-cols-2">
                    <div className="bg-muted rounded-lg px-4 py-3">
                      {t('loading.step_collect')}
                    </div>
                    <div className="bg-muted rounded-lg px-4 py-3">
                      {t('loading.step_filter')}
                    </div>
                    <div className="bg-muted rounded-lg px-4 py-3">
                      {t('loading.step_compare')}
                    </div>
                    <div className="bg-muted rounded-lg px-4 py-3">
                      {t('loading.step_finalize')}
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}
