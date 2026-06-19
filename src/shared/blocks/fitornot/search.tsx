'use client';

import { useMemo, useState } from 'react';
import { nanoid } from 'nanoid';
import { ArrowRight, History, Link2, Search } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { useRouter } from '@/core/i18n/navigation';
import { Button } from '@/shared/components/ui/button';
import { Input } from '@/shared/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select';
import { Textarea } from '@/shared/components/ui/textarea';

import { FitOrNotHistorySheet } from './history-sheet';
import { savePendingFitOrNotRequest } from './storage';

const JD_PATTERN = /jd\.com/i;
const TAOBAO_PATTERN = /taobao\.com/i;
const XHS_PATTERN = /xiaohongshu\.com/i;

export function FitOrNotSearch() {
  const t = useTranslations('ai.fitornot');
  const router = useRouter();
  const [prompt, setPrompt] = useState('');
  const [links, setLinks] = useState('');
  const [targetLanguage, setTargetLanguage] = useState('zh-CN');

  const detectedPlatforms = useMemo(() => {
    const combined = `${prompt}\n${links}`;
    return {
      jd: JD_PATTERN.test(combined),
      taobao: TAOBAO_PATTERN.test(combined),
      xiaohongshu: XHS_PATTERN.test(combined),
    };
  }, [links, prompt]);

  const handleSubmit = () => {
    const promptValue = prompt.trim();
    const linksValue = links.trim();
    if (!promptValue) {
      return;
    }

    const entryId = nanoid();
    const userRawInput = [promptValue, linksValue].filter(Boolean).join('\n');

    savePendingFitOrNotRequest({
      id: entryId,
      userRawInput,
      targetLanguage,
    });
    router.push(`/fitornot/loading/${entryId}`);
  };

  return (
    <section className="flex flex-1 items-center px-5 py-10 md:px-10 md:py-14">
      <div className="mx-auto flex w-full max-w-[920px] flex-col gap-8">
        <div className="flex items-center justify-between gap-4">
          <div className="text-lg font-semibold tracking-[0.18em] text-slate-800">
            FITorNOT
          </div>
          <FitOrNotHistorySheet
            trigger={
              <Button
                variant="outline"
                type="button"
                className="rounded-full border-slate-200 bg-white/80 px-4 text-slate-600 shadow-[0_8px_24px_rgba(211,223,232,0.35)] hover:bg-white"
              >
                <History data-icon="inline-start" />
                {t('history.title')}
              </Button>
            }
          />
        </div>

        <div className="space-y-4 text-center">
          <h1 className="mx-auto max-w-[760px] text-4xl font-semibold tracking-tight text-slate-900 md:text-6xl md:leading-[1.1]">
            {t('search.title')}
          </h1>
          <p className="mx-auto max-w-[760px] text-base leading-7 text-slate-500 md:text-lg">
            {t('search.card_title')}
          </p>
        </div>

        <div className="rounded-[28px] bg-white px-5 py-5 shadow-[0_20px_40px_rgba(211,223,232,0.35)] ring-1 ring-slate-200/70 transition-all duration-300 focus-within:-translate-y-0.5 focus-within:shadow-[0_24px_48px_rgba(211,223,232,0.4)] md:px-6 md:py-6">
          <div className="flex flex-col gap-5">
            <Textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder={t('search.prompt_placeholder')}
              className="min-h-40 resize-none border-0 bg-transparent px-0 text-lg leading-8 text-slate-800 shadow-none focus-visible:ring-0 md:min-h-44"
            />

            <div className="h-px bg-slate-200/80" />

            <div className="flex items-center gap-3 rounded-[18px] bg-slate-50 px-4 py-3">
              <Link2 className="size-4 text-slate-400" />
              <Input
                value={links}
                onChange={(event) => setLinks(event.target.value)}
                placeholder={t('search.link_placeholder')}
                className="h-auto border-0 bg-transparent px-0 py-0 text-sm text-slate-600 shadow-none focus-visible:ring-0"
              />
            </div>

            <div className="flex flex-col gap-4 border-t border-slate-200/80 pt-4 sm:flex-row sm:items-center sm:justify-between">
              <Select value={targetLanguage} onValueChange={setTargetLanguage}>
                <SelectTrigger className="w-full rounded-xl border-slate-200 bg-transparent text-slate-600 shadow-none sm:w-52">
                  <SelectValue placeholder={t('search.language_placeholder')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="zh-CN">中文</SelectItem>
                  <SelectItem value="English">English</SelectItem>
                </SelectContent>
              </Select>

              <Button
                type="button"
                className="h-12 w-full rounded-xl bg-[#8CA6BD] px-6 text-white shadow-[0_10px_24px_rgba(140,166,189,0.28)] hover:bg-[#486176] sm:w-auto"
                onClick={handleSubmit}
                disabled={!prompt.trim()}
              >
                <Search data-icon="inline-start" />
                {t('search.submit')}
                <ArrowRight className="size-4" />
              </Button>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap justify-center gap-3">
          {detectedPlatforms.jd && (
            <div className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm text-slate-500 shadow-[0_10px_20px_rgba(211,223,232,0.22)]">
              <span className="size-2 rounded-full bg-sky-300" />
              京东
            </div>
          )}
          {detectedPlatforms.taobao && (
            <div className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm text-slate-500 shadow-[0_10px_20px_rgba(211,223,232,0.22)]">
              <span className="size-2 rounded-full bg-orange-300" />
              淘宝
            </div>
          )}
          {detectedPlatforms.xiaohongshu && (
            <div className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm text-slate-500 shadow-[0_10px_20px_rgba(211,223,232,0.22)]">
              <span className="size-2 rounded-full bg-rose-300" />
              小红书
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
