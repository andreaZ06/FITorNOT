'use client';

import { useMemo, useState } from 'react';
import { nanoid } from 'nanoid';
import { History, Search } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { useRouter } from '@/core/i18n/navigation';
import { Button } from '@/shared/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card';
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
    <section className="py-16 md:py-24">
      <div className="container">
        <div className="mx-auto flex max-w-4xl flex-col gap-8">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-2">
              <p className="text-muted-foreground text-sm tracking-[0.3em] uppercase">
                FITorNOT
              </p>
              <h1 className="text-3xl font-semibold tracking-tight md:text-5xl">
                {t('search.title')}
              </h1>
            </div>
            <FitOrNotHistorySheet
              trigger={
                <Button variant="outline" type="button">
                  <History data-icon="inline-start" />
                  {t('history.title')}
                </Button>
              }
            />
          </div>

          <Card className="border-border/60 shadow-sm">
            <CardHeader className="pb-4">
              <CardTitle className="text-lg font-medium">
                {t('search.card_title')}
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-6">
              <Textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder={t('search.prompt_placeholder')}
                className="min-h-40 resize-none"
              />

              <Input
                value={links}
                onChange={(event) => setLinks(event.target.value)}
                placeholder={t('search.link_placeholder')}
              />

              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <Select value={targetLanguage} onValueChange={setTargetLanguage}>
                  <SelectTrigger className="w-full sm:w-48">
                    <SelectValue placeholder={t('search.language_placeholder')} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="zh-CN">中文</SelectItem>
                    <SelectItem value="English">English</SelectItem>
                  </SelectContent>
                </Select>

                <Button
                  type="button"
                  className="w-full sm:w-auto"
                  onClick={handleSubmit}
                  disabled={!prompt.trim()}
                >
                  <Search data-icon="inline-start" />
                  {t('search.submit')}
                </Button>
              </div>
            </CardContent>
          </Card>

          <div className="flex flex-wrap gap-3">
            {detectedPlatforms.jd && (
              <div className="bg-muted text-muted-foreground rounded-full px-4 py-2 text-sm">
                京东
              </div>
            )}
            {detectedPlatforms.taobao && (
              <div className="bg-muted text-muted-foreground rounded-full px-4 py-2 text-sm">
                淘宝
              </div>
            )}
            {detectedPlatforms.xiaohongshu && (
              <div className="bg-muted text-muted-foreground rounded-full px-4 py-2 text-sm">
                小红书
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
