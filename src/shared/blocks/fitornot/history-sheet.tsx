'use client';

import type { ReactNode } from 'react';
import { useMemo, useState } from 'react';
import { Clock3, History } from 'lucide-react';
import { useTranslations } from 'next-intl';

import { useRouter } from '@/core/i18n/navigation';
import { Badge } from '@/shared/components/ui/badge';
import { Button } from '@/shared/components/ui/button';
import { ScrollArea } from '@/shared/components/ui/scroll-area';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/shared/components/ui/sheet';

import { getFitOrNotHistoryEntries, MAX_HISTORY_ENTRIES } from './storage';
import type { FitOrNotHistoryEntry, FitOrNotVerdictTone } from './types';

const BADGE_VARIANTS: Record<
  FitOrNotVerdictTone,
  'default' | 'secondary' | 'destructive' | 'outline'
> = {
  veto: 'destructive',
  caution: 'secondary',
  fit: 'default',
  unknown: 'outline',
};

type FitOrNotHistorySheetProps = {
  trigger?: ReactNode;
};

function formatTimestamp(value: string) {
  const parsedDate = new Date(value);
  if (Number.isNaN(parsedDate.getTime())) {
    return value;
  }

  return parsedDate.toLocaleString();
}

function HistoryEntryButton({
  entry,
  onSelect,
}: {
  entry: FitOrNotHistoryEntry;
  onSelect: (entryId: string) => void;
}) {
  const t = useTranslations('ai.fitornot');

  return (
    <button
      type="button"
      className="flex w-full flex-col gap-2 rounded-[20px] border border-slate-200 bg-slate-50/55 px-4 py-4 text-left transition-colors hover:bg-slate-50"
      onClick={() => onSelect(entry.id)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-slate-800">{entry.summaryTitle}</p>
          <div className="mt-1 flex items-center gap-2 text-xs text-slate-400">
            <Clock3 className="size-3.5" />
            <span>{formatTimestamp(entry.createdAt)}</span>
          </div>
        </div>
        <Badge variant={BADGE_VARIANTS[entry.verdictTone]}>
          {t(`history.verdict_${entry.verdictTone}`)}
        </Badge>
      </div>
    </button>
  );
}

export function FitOrNotHistorySheet({ trigger }: FitOrNotHistorySheetProps) {
  const t = useTranslations('ai.fitornot');
  const router = useRouter();
  const [open, setOpen] = useState(false);

  const historyEntries = useMemo(
    () => getFitOrNotHistoryEntries().slice(0, MAX_HISTORY_ENTRIES),
    [open]
  );

  const handleSelect = (entryId: string) => {
    setOpen(false);
    router.push(`/fitornot/result/${entryId}`);
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        {trigger ?? (
          <Button
            variant="outline"
            type="button"
            className="rounded-full border-slate-200 bg-white/80 px-4 text-slate-600 shadow-[0_8px_24px_rgba(211,223,232,0.35)] hover:bg-white"
          >
            <History data-icon="inline-start" />
            {t('history.title')}
          </Button>
        )}
      </SheetTrigger>
      <SheetContent side="right" className="gap-0 border-l border-slate-200 bg-white px-0">
        <SheetHeader className="border-b border-slate-200 px-6 pb-5 pt-8">
          <SheetTitle className="text-left text-xl font-semibold text-slate-900">
            {t('history.title')}
          </SheetTitle>
          <SheetDescription className="text-left text-sm leading-6 text-slate-500">
            {t('history.description')}
          </SheetDescription>
        </SheetHeader>

        <ScrollArea className="h-full">
          <div className="flex flex-col gap-3 p-5">
            {historyEntries.length === 0 ? (
              <div className="rounded-[20px] border border-dashed border-slate-200 px-4 py-10 text-center text-sm leading-6 text-slate-400">
                {t('history.empty')}
              </div>
            ) : (
              historyEntries.map((entry) => (
                <HistoryEntryButton key={entry.id} entry={entry} onSelect={handleSelect} />
              ))
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
