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
      className="hover:bg-muted/70 flex w-full flex-col gap-2 rounded-lg border px-4 py-3 text-left transition-colors"
      onClick={() => onSelect(entry.id)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium">{entry.summaryTitle}</p>
          <div className="text-muted-foreground mt-1 flex items-center gap-2 text-xs">
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
          <Button variant="outline" type="button">
            <History data-icon="inline-start" />
            {t('history.title')}
          </Button>
        )}
      </SheetTrigger>
      <SheetContent side="right" className="gap-0">
        <SheetHeader className="border-b pb-4">
          <SheetTitle>{t('history.title')}</SheetTitle>
          <SheetDescription>{t('history.description')}</SheetDescription>
        </SheetHeader>

        <ScrollArea className="h-full">
          <div className="flex flex-col gap-3 p-4">
            {historyEntries.length === 0 ? (
              <div className="text-muted-foreground rounded-lg border border-dashed px-4 py-8 text-center text-sm">
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
