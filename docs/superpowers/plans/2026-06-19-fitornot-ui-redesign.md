# FITorNOT UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the FITorNOT search, loading, and result flow as a standalone route with the `ui02.txt` visual system, while removing ShipAny landing chrome and pricing-style leakage.

**Architecture:** Move FITorNOT from the landing route group into a dedicated locale route tree, keep the existing client-side workflow and storage model, and restyle the existing `src/shared/blocks/fitornot` components with a shared FITorNOT-specific shell and visual tokens. Preserve the current `/api/fitornot/decision` integration and local history behavior while adding regression tests for the new standalone surface.

**Tech Stack:** Next.js App Router, React client components, next-intl, Vitest + Testing Library, existing shadcn/ui primitives, local browser storage.

---

## File Structure

### New files

- `src/app/[locale]/fitornot/layout.tsx`
  - Dedicated FITorNOT route layout that bypasses the landing shell.
- `src/app/[locale]/fitornot/page.tsx`
  - Search page entry under the standalone route tree.
- `src/app/[locale]/fitornot/loading/[entryId]/page.tsx`
  - Loading page entry under the standalone route tree.
- `src/app/[locale]/fitornot/result/[entryId]/page.tsx`
  - Result page entry under the standalone route tree.
- `src/shared/blocks/fitornot/shell.tsx`
  - Shared FITorNOT route shell and reusable surface classes for the redesigned experience.
- `tests/unit/fitornot/routes.test.tsx`
  - Route-level regression coverage for the new standalone FITorNOT pages.

### Deleted files

- `src/app/[locale]/(landing)/(ai)/fitornot/page.tsx`
- `src/app/[locale]/(landing)/(ai)/fitornot/loading/[entryId]/page.tsx`
- `src/app/[locale]/(landing)/(ai)/fitornot/result/[entryId]/page.tsx`

### Modified files

- `src/shared/blocks/fitornot/search.tsx`
  - Replace the current default card UI with the `ui02` search composition.
- `src/shared/blocks/fitornot/loading.tsx`
  - Replace the current generic card/progress UI with the full-screen loading composition and aligned error state.
- `src/shared/blocks/fitornot/result.tsx`
  - Rework the page chrome and content layout to the new FITorNOT result surface, removing the landing-like feel.
- `src/shared/blocks/fitornot/history-sheet.tsx`
  - Restyle the history drawer to match the FITorNOT surface.
- `src/shared/blocks/fitornot/index.ts`
  - Export the new shell if needed by route entries.
- `tests/unit/fitornot/search.test.tsx`
  - Add visual/wording regressions for the standalone search surface.
- `tests/unit/fitornot/loading.test.tsx`
  - Add regressions for the redesigned loading and error states.
- `tests/unit/fitornot/result.test.tsx`
  - Add regressions for the redesigned result surface and the absence of unwanted recommendation/pricing content.
- `src/config/locale/messages/zh/ai/fitornot.json`
  - Tighten the FITorNOT copy for the new standalone surface.
- `src/config/locale/messages/en/ai/fitornot.json`
  - Tighten the FITorNOT copy for the new standalone surface.

## Task 1: Standalone FITorNOT Route Tree

**Files:**
- Create: `src/app/[locale]/fitornot/layout.tsx`
- Create: `src/app/[locale]/fitornot/page.tsx`
- Create: `src/app/[locale]/fitornot/loading/[entryId]/page.tsx`
- Create: `src/app/[locale]/fitornot/result/[entryId]/page.tsx`
- Delete: `src/app/[locale]/(landing)/(ai)/fitornot/page.tsx`
- Delete: `src/app/[locale]/(landing)/(ai)/fitornot/loading/[entryId]/page.tsx`
- Delete: `src/app/[locale]/(landing)/(ai)/fitornot/result/[entryId]/page.tsx`
- Test: `tests/unit/fitornot/routes.test.tsx`

- [ ] **Step 1: Write the failing route-isolation test**

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next-intl/server', () => ({
  setRequestLocale: vi.fn(),
}));

vi.mock('@/shared/blocks/fitornot', () => ({
  FitOrNotSearch: () => <div>fit-search-stub</div>,
  FitOrNotLoading: ({ entryId }: { entryId: string }) => (
    <div>{`fit-loading-${entryId}`}</div>
  ),
  FitOrNotResult: ({ entryId }: { entryId: string }) => (
    <div>{`fit-result-${entryId}`}</div>
  ),
}));

import FitOrNotLayout from '@/app/[locale]/fitornot/layout';
import FitOrNotSearchPage from '@/app/[locale]/fitornot/page';
import FitOrNotLoadingPage from '@/app/[locale]/fitornot/loading/[entryId]/page';
import FitOrNotResultPage from '@/app/[locale]/fitornot/result/[entryId]/page';

describe('standalone FITorNOT route tree', () => {
  it('renders the dedicated shell without ShipAny landing chrome', async () => {
    render(
      await FitOrNotLayout({
        children: <div>route-body</div>,
        params: Promise.resolve({ locale: 'zh' }),
      })
    );

    expect(screen.getByText('route-body')).toBeInTheDocument();
    expect(screen.queryByText(/ShipAny Two/i)).not.toBeInTheDocument();
  });

  it('renders the search page through the standalone route entry', async () => {
    render(await FitOrNotSearchPage({ params: Promise.resolve({ locale: 'zh' }) }));
    expect(screen.getByText('fit-search-stub')).toBeInTheDocument();
  });

  it('renders loading and result entries under the standalone route tree', async () => {
    render(
      <div>
        {await FitOrNotLoadingPage({
          params: Promise.resolve({ locale: 'zh', entryId: 'abc' }),
        })}
        {await FitOrNotResultPage({
          params: Promise.resolve({ locale: 'zh', entryId: 'xyz' }),
        })}
      </div>
    );

    expect(screen.getByText('fit-loading-abc')).toBeInTheDocument();
    expect(screen.getByText('fit-result-xyz')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm exec vitest run tests/unit/fitornot/routes.test.tsx`
Expected: FAIL because the standalone route files do not exist yet.

- [ ] **Step 3: Write the minimal standalone route implementation**

```tsx
// src/app/[locale]/fitornot/layout.tsx
import type { ReactNode } from 'react';
import { setRequestLocale } from 'next-intl/server';

import { FitOrNotShell } from '@/shared/blocks/fitornot';

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

// src/app/[locale]/fitornot/page.tsx
import { FitOrNotSearch } from '@/shared/blocks/fitornot';
import { getMetadata } from '@/shared/lib/seo';

export const generateMetadata = getMetadata({
  metadataKey: 'ai.fitornot.metadata',
  canonicalUrl: '/fitornot',
});

export default async function FitOrNotSearchPage() {
  return <FitOrNotSearch />;
}

// src/app/[locale]/fitornot/loading/[entryId]/page.tsx
import { FitOrNotLoading } from '@/shared/blocks/fitornot';
import { getMetadata } from '@/shared/lib/seo';

export const generateMetadata = getMetadata({
  metadataKey: 'ai.fitornot.metadata',
  canonicalUrl: '/fitornot',
  noIndex: true,
});

export default async function FitOrNotLoadingPage({
  params,
}: {
  params: Promise<{ locale: string; entryId: string }>;
}) {
  const { entryId } = await params;
  return <FitOrNotLoading entryId={entryId} />;
}

// src/app/[locale]/fitornot/result/[entryId]/page.tsx
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
  const { entryId } = await params;
  return <FitOrNotResult entryId={entryId} />;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm exec vitest run tests/unit/fitornot/routes.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/fitornot/routes.test.tsx src/app/[locale]/fitornot src/app/[locale]/(landing)/(ai)/fitornot
git commit -m "refactor: move fitornot into standalone route tree"
```

## Task 2: Shared FITorNOT Shell and Search Surface

**Files:**
- Create: `src/shared/blocks/fitornot/shell.tsx`
- Modify: `src/shared/blocks/fitornot/index.ts`
- Modify: `src/shared/blocks/fitornot/search.tsx`
- Modify: `src/shared/blocks/fitornot/history-sheet.tsx`
- Modify: `src/config/locale/messages/zh/ai/fitornot.json`
- Modify: `src/config/locale/messages/en/ai/fitornot.json`
- Test: `tests/unit/fitornot/search.test.tsx`

- [ ] **Step 1: Write the failing search-surface regressions**

```tsx
it('renders FITorNOT-only chrome without ShipAny or pricing copy', () => {
  render(<FitOrNotSearch />);

  expect(screen.getAllByText('FITorNOT').length).toBeGreaterThan(0);
  expect(screen.queryByText(/ShipAny Two/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/pricing/i)).not.toBeInTheDocument();
});

it('renders the redesigned search surface controls', () => {
  render(<FitOrNotSearch />);

  expect(screen.getByRole('button', { name: /history\.title/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /search\.submit/i })).toBeInTheDocument();
  expect(screen.getByRole('combobox')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm exec vitest run tests/unit/fitornot/search.test.tsx`
Expected: FAIL because the current search surface still uses the old generic card layout and wording.

- [ ] **Step 3: Write the minimal redesigned shell and search implementation**

```tsx
// src/shared/blocks/fitornot/shell.tsx
import type { ReactNode } from 'react';

export function FitOrNotShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-[#F4F7F9] text-slate-700">
      <div className="mx-auto flex min-h-screen w-full max-w-[1440px] flex-col">
        {children}
      </div>
    </div>
  );
}

// src/shared/blocks/fitornot/index.ts
export * from './shell';
export * from './search';
export * from './loading';
export * from './result';

// src/shared/blocks/fitornot/search.tsx
<section className="flex flex-1 items-center px-5 py-10 md:px-10">
  <div className="mx-auto flex w-full max-w-[900px] flex-col gap-8">
    <div className="flex items-center justify-between gap-4">
      <div className="text-lg font-semibold tracking-[0.18em] text-slate-800">FITorNOT</div>
      <FitOrNotHistorySheet />
    </div>

    <div className="space-y-4 text-center">
      <h1 className="mx-auto max-w-[760px] text-4xl font-semibold tracking-tight text-slate-900 md:text-6xl">
        {t('search.title')}
      </h1>
      <p className="mx-auto max-w-[720px] text-base leading-7 text-slate-500 md:text-lg">
        {t('search.card_title')}
      </p>
    </div>

    <div className="rounded-[28px] bg-white p-5 shadow-[0_20px_40px_rgba(211,223,232,0.35)] md:p-6">
      {/* textarea, link row, language selector, action button */}
    </div>

    <div className="flex flex-wrap justify-center gap-3">
      {/* platform pills */}
    </div>
  </div>
</section>

// src/shared/blocks/fitornot/history-sheet.tsx
<SheetContent side="right" className="gap-0 border-l border-slate-200 bg-white">
  {/* keep behavior, restyle rows and header */}
</SheetContent>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm exec vitest run tests/unit/fitornot/search.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/shared/blocks/fitornot/shell.tsx src/shared/blocks/fitornot/index.ts src/shared/blocks/fitornot/search.tsx src/shared/blocks/fitornot/history-sheet.tsx src/config/locale/messages/zh/ai/fitornot.json src/config/locale/messages/en/ai/fitornot.json tests/unit/fitornot/search.test.tsx
git commit -m "feat: redesign fitornot search surface"
```

## Task 3: Loading Screen Redesign

**Files:**
- Modify: `src/shared/blocks/fitornot/loading.tsx`
- Test: `tests/unit/fitornot/loading.test.tsx`

- [ ] **Step 1: Write the failing loading-screen regressions**

```tsx
it('renders the redesigned loading surface instead of the generic card shell', async () => {
  window.sessionStorage.setItem(
    'fitornot:pending:entry-visual',
    JSON.stringify({
      id: 'entry-visual',
      userRawInput: 'query',
      targetLanguage: 'zh-CN',
    })
  );

  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: -1, message: 'backend failed' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      })
    )
  );

  render(<FitOrNotLoading entryId="entry-visual" />);

  expect(screen.getByText(/loading\.status_title/i)).toBeInTheDocument();
  expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();

  await waitFor(() => {
    expect(screen.getByRole('button', { name: /loading\.retry/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm exec vitest run tests/unit/fitornot/loading.test.tsx`
Expected: FAIL because the current loading page still renders a progress bar and generic card layout.

- [ ] **Step 3: Write the minimal redesigned loading implementation**

```tsx
// src/shared/blocks/fitornot/loading.tsx
<section className="relative flex min-h-screen items-center justify-center overflow-hidden px-5 py-10">
  <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(175,202,226,0.45),_transparent_48%)]" />
  <div className="relative mx-auto flex w-full max-w-[920px] flex-col items-center justify-center gap-10 text-center">
    <div className="relative flex h-[260px] w-[260px] items-center justify-center md:h-[320px] md:w-[320px]">
      <div className="absolute inset-0 rounded-full border border-[#8CA6BD]/20" />
      <div className="absolute inset-3 animate-spin rounded-full border-2 border-transparent border-t-[#8CA6BD] border-r-[#8CA6BD]/20" />
      <div className="h-[70%] w-[70%] rounded-[40%] bg-[linear-gradient(135deg,_rgba(175,202,226,0.78),_rgba(140,166,189,0.92))] blur-2xl" />
    </div>

    {!errorMessage ? (
      <div className="space-y-4">
        <p className="text-xs font-semibold tracking-[0.36em] text-slate-400 uppercase">FITorNOT</p>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900 md:text-5xl">
          {t('loading.title')}
        </h1>
        <p className="text-base leading-7 text-slate-500 md:text-lg">
          {loadingMessages[stepIndex]}
        </p>
      </div>
    ) : (
      <div className="w-full max-w-[560px] rounded-[28px] border border-rose-200 bg-white/90 p-6 shadow-[0_20px_40px_rgba(211,223,232,0.35)]">
        {/* same retry/back behavior with redesigned error block */}
      </div>
    )}
  </div>
</section>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm exec vitest run tests/unit/fitornot/loading.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/shared/blocks/fitornot/loading.tsx tests/unit/fitornot/loading.test.tsx
git commit -m "feat: redesign fitornot loading screen"
```

## Task 4: Result Screen Redesign

**Files:**
- Modify: `src/shared/blocks/fitornot/result.tsx`
- Test: `tests/unit/fitornot/result.test.tsx`

- [ ] **Step 1: Write the failing result-screen regressions**

```tsx
it('renders the FITorNOT result chrome without recommendation or pricing leakage', async () => {
  window.localStorage.setItem(
    'fitornot:history:v1',
    JSON.stringify([buildHistoryEntry('entry-1', '2026-06-19T08:01:00.000Z', 'Anker 10000')])
  );

  render(<FitOrNotResult entryId="entry-1" />);

  await waitFor(() => {
    expect(screen.getByRole('heading', { name: 'Anker 10000' })).toBeInTheDocument();
  });

  expect(screen.getAllByText('FITorNOT').length).toBeGreaterThan(0);
  expect(screen.queryByText(/alternative/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/pricing/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/ShipAny/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm exec vitest run tests/unit/fitornot/result.test.tsx`
Expected: FAIL because the current result layout still uses the generic card composition and lacks the new FITorNOT page chrome.

- [ ] **Step 3: Write the minimal redesigned result implementation**

```tsx
// src/shared/blocks/fitornot/result.tsx
<section className="px-5 py-6 md:px-10 md:py-8">
  <div className="mx-auto flex w-full max-w-[1120px] flex-col gap-6">
    <div className="flex items-center justify-between rounded-[22px] border border-slate-200 bg-white/85 px-5 py-4 shadow-[0_16px_36px_rgba(211,223,232,0.28)] backdrop-blur">
      <div className="space-y-1">
        <div className="text-sm font-semibold tracking-[0.24em] text-slate-500 uppercase">FITorNOT</div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 md:text-3xl">
          {currentEntry.summaryTitle}
        </h1>
      </div>
      <div className="flex flex-wrap gap-3">
        {/* history + new search buttons */}
      </div>
    </div>

    <div className="rounded-[28px] border px-5 py-5 md:px-6 md:py-6">
      {/* verdict banner */}
    </div>

    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {/* plan and evidence overview cards */}
    </div>

    <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
      {/* left specs/query meta, right risks */}
    </div>

    <div className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-[0_16px_36px_rgba(211,223,232,0.28)] md:p-6">
      {/* markdown report */}
    </div>
  </div>
</section>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm exec vitest run tests/unit/fitornot/result.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/shared/blocks/fitornot/result.tsx tests/unit/fitornot/result.test.tsx
git commit -m "feat: redesign fitornot result screen"
```

## Task 5: Full Verification and Browser QA

**Files:**
- Modify: none unless fixes are found
- Test: `tests/unit/fitornot/routes.test.tsx`
- Test: `tests/unit/fitornot/search.test.tsx`
- Test: `tests/unit/fitornot/loading.test.tsx`
- Test: `tests/unit/fitornot/result.test.tsx`
- Test: `tests/unit/fitornot/storage.test.ts`

- [ ] **Step 1: Run the focused FITorNOT suite**

Run: `npm exec vitest run tests/unit/fitornot`
Expected: PASS

- [ ] **Step 2: Run the broader repository checks**

Run: `npm test`
Expected: PASS

Run: `npm run typecheck`
Expected: PASS

Run: `npm run lint`
Expected: PASS with no new errors; existing warnings may remain if unchanged.

Run: `npx pnpm run verify`
Expected: PASS

- [ ] **Step 3: Run browser QA on the standalone FITorNOT flow**

Flow under test:

`/[locale]/fitornot` -> enter query -> navigate to loading page -> render result page from saved history.

Browser checks:

- page identity matches the standalone route
- no visible `ShipAny Two`
- no visible pricing section or pricing CTA
- search page visually matches the `ui02` search tone
- loading page visually matches the `ui02` loading tone
- result page keeps the new FITorNOT chrome and does not show alternative recommendation content

- [ ] **Step 4: Commit final polish if any QA fixes are needed**

```bash
git add src/app/[locale]/fitornot src/shared/blocks/fitornot tests/unit/fitornot src/config/locale/messages/zh/ai/fitornot.json src/config/locale/messages/en/ai/fitornot.json
git commit -m "fix: polish fitornot standalone ui flow"
```

- [ ] **Step 5: Push**

```bash
git push origin main
```

## Self-Review

### Spec coverage

- Standalone route tree: covered by Task 1
- Remove landing shell / ShipAny leakage: covered by Tasks 1, 2, 4, and browser QA
- Search surface redesign: covered by Task 2
- Loading surface redesign: covered by Task 3
- Result surface redesign: covered by Task 4
- Keep history behavior: preserved in Tasks 2 and 4, with existing storage/history tests retained
- No recommendation or pricing section in FITorNOT flow: covered by Task 4 and browser QA
- Visual verification against `ui02.txt`: covered by Task 5

### Placeholder scan

No `TODO`, `TBD`, or deferred implementation markers remain. Each task includes named files, failing tests, verification commands, and commit steps.

### Type consistency

The plan keeps the existing `FitOrNotSearch`, `FitOrNotLoading`, `FitOrNotResult`, and storage-driven route contract. New additions are limited to the standalone route files and `FitOrNotShell`, which use the same entry signatures already present in the route tree.
