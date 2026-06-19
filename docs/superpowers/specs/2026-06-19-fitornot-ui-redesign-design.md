# FITorNOT UI Redesign Design

Date: 2026-06-19
Status: Draft approved in chat, written for implementation review

## Scope

This spec covers only the FITorNOT user flow at `/[locale]/fitornot`:

1. Search page
2. Loading page
3. Result page
4. Local history sheet

It does not change the rest of the ShipAny-based site in this pass.

## Problem Summary

The current FITorNOT flow works functionally, but it still inherits too much of the surrounding template product:

- `ShipAny Two` branding leaks into the experience through the landing shell
- template navigation and footer cues dilute FITorNOT as a standalone tool
- the visual language is still close to default shadcn and template styling
- the current UI does not faithfully follow the softer blue-gray, low-noise, inspection-tool tone shown in `review-pitfall-checker-v2/ui02.txt`
- pricing-oriented or landing-oriented affordances do not belong in this tool flow

The result is a mismatch between product intent and presentation: the tool behaves like a focused audit assistant, but looks like a page embedded inside a SaaS template.

## Goal

Turn FITorNOT into a standalone-feeling audit tool with a calm, trustworthy, slightly clinical interface that matches the reference flow in `ui02.txt`.

The user experience should feel like:

- a dedicated decision assistant, not a template demo page
- soft, quiet, evidence-first, not promotional
- immediate and guided: search -> loading -> result
- free of all visible `ShipAny Two` wording or pricing-related UI inside the FITorNOT flow

## Approved Direction

We will use the dedicated-route approach:

1. Move FITorNOT pages out of the landing route shell
2. Keep the public URL as `/[locale]/fitornot`
3. Give FITorNOT its own layout and page chrome
4. Re-skin all three states using the `ui02.txt` visual system
5. Preserve the existing local-history behavior and result rendering logic

This is preferred over trying to hide pieces of the landing shell because the tool needs clean separation from template branding and pricing behavior.

## Design Read

Reading this as: a consumer decision tool for everyday buyers, with a calm trust-first language, leaning toward a light blue-gray product surface with restrained motion and soft evidence-review cues.

## Visual System

### Palette

Primary palette should come from the `ui02.txt` references:

- page background: pale mist blue-gray
- card background: warm white / high-contrast white surfaces
- text: slate blue-gray, never pure black
- primary accent: dusty steel blue
- support accent: muted aqua/teal for positive or neutral signal
- warning accent: muted rose/red for risk states
- borders: thin, cool, low-contrast gray-blue

The page should remain light throughout. No dark sections, no hero gradients, no marketing glow effects.

### Typography

- Use a clean sans stack already available in the app
- Headings: compact, confident, not oversized hero-marketing type
- Body copy: quiet and readable
- Labels: small, uppercase only when needed for subtle metadata

Typography should feel editorially tidy, but still like a practical tool.

### Shape and surfaces

- Rounded corners should stay soft but controlled, roughly 16px to 24px on major panels
- Cards should look mist-shadowed and airy, not heavy
- Surfaces should be sparse and intentional
- Avoid nested card-on-card clutter where an open layout can do the job

### Motion

Motion should be low-intensity:

- subtle focus expansion on search surface
- soft loading pulses and rotating rings on loading page
- mild fade/slide entrance on result blocks

No cinematic transitions, no bouncing marketing motion, no distracting animation loops beyond loading feedback.

## Information Architecture

### Route structure

FITorNOT should become a dedicated route tree:

- `src/app/[locale]/fitornot/layout.tsx`
- `src/app/[locale]/fitornot/page.tsx`
- `src/app/[locale]/fitornot/loading/[entryId]/page.tsx`
- `src/app/[locale]/fitornot/result/[entryId]/page.tsx`

The old route files under `src/app/[locale]/(landing)/(ai)/fitornot/...` should be removed once the new tree is in place.

### Why this move matters

This removes inherited landing chrome, especially:

- `ShipAny Two` branding
- landing header/footer
- any pricing-oriented navigation or CTA bleed-through
- landing-specific top banners

The FITorNOT route should inherit only the locale-level layout, not the landing shell.

## Page-by-Page Design

### 1. Search page

The search page should directly reflect the first section in `ui02.txt`.

#### Required structure

- top utility row:
  - FITorNOT wordmark only
  - history button on the right
- centered main content area
- large but not theatrical title
- one primary elongated input surface
- optional link input row inside the same main surface
- language selector
- primary action button
- platform detection pills under the main input card

#### What to remove

- any `ShipAny Two` text
- any landing-style brand copy about boilerplates or SaaS templates
- any pricing links or pricing lists
- any generic template footer text

#### Behavior

- same existing submit behavior: save pending request -> route to loading page
- platform detection pills remain present and reactive
- history button still opens the local sheet

### 2. Loading page

The loading page should follow the second section in `ui02.txt`.

#### Required structure

- standalone full-screen composition
- soft central animated object:
  - layered loading ring
  - subtle mist blob
- status headline and rotating status message
- one compact explanatory line
- optional micro pulse dots beneath
- minimal FITorNOT engine label at the bottom

#### Error state

If the request fails:

- stay on the loading page
- replace the loading stack with a soft error panel
- keep `Retry` and `Back to search`
- do not destroy the page's visual identity by dropping back to a generic alert-only card

### 3. Result page

The result page should use the third section in `ui02.txt` as the structural and tonal reference, but it must stay bound to the real backend response.

#### Required structure

- compact top app bar with:
  - FITorNOT wordmark
  - history button
  - new search button
- verdict banner near the top
- overview strip for retrieval plan / evidence counts / blocked sources
- two-column desktop layout for:
  - verified specs and query context
  - risk cards and findings
- full report section rendered from markdown

#### Explicit removal

Do not implement the mock "alternative product recommendation" section from the reference.

Reason:

- it is not supported by the current backend shape
- it would introduce fake product data
- the user explicitly asked not to include pricing-list style content

#### Tone by verdict

- `veto`: muted rose/red
- `caution`: amber/stone caution
- `fit`: soft green/teal confidence
- `unknown`: neutral slate

The verdict styling should affect banner emphasis and badges, not repaint the whole page.

## History Sheet

The existing local-history behavior stays, but the visual treatment should match the new tool surface:

- soft white sheet
- compact entry cards
- subtle verdict badges
- no template-site styling cues

History remains capped at 3 completed entries in local storage.

## Copy and Branding Rules

Within the FITorNOT route:

- visible product name should be `FITorNOT`
- no visible `ShipAny`, `ShipAny Two`, or "boilerplate" wording
- no pricing links
- no pricing section
- no "built with ShipAny" footer cues

This rule applies to:

- page chrome
- headings
- helper copy
- empty states
- any local footer or utility text within the FITorNOT route

It does not require rewriting unrelated pages elsewhere in the site.

## Component Strategy

Keep the current client modules under `src/shared/blocks/fitornot`, but restyle and reorganize them:

- `search.tsx`
- `loading.tsx`
- `result.tsx`
- `history-sheet.tsx`

Add a small FITorNOT-specific visual layer rather than mixing more generic landing components into the surface.

Likely supporting additions:

- FITorNOT shell wrapper
- shared panel classes / utility tokens
- lightweight status badge styles

## Data Flow

Business behavior should remain unchanged:

1. Search page creates `entryId`
2. Pending request stored in `sessionStorage`
3. Loading page performs `/api/fitornot/decision`
4. Success writes the result into local history
5. Result page resolves from local history

The redesign is visual and structural, not a workflow rewrite.

## Accessibility

The redesign must preserve:

- visible focus states
- strong enough contrast on buttons and labels
- keyboard access to history sheet and main actions
- readable error state on loading page
- responsive text wrapping on narrow screens

The soft palette cannot come at the cost of weak contrast.

## Responsive Rules

### Mobile

- search card becomes full-width
- header row stays compact
- history button remains visible
- result page stacks into one column
- verdict banner becomes vertical

### Desktop

- centered narrow search composition
- loading page remains vertically centered
- result page uses measured two-column rhythm without wide empty gutters

## Testing Plan

### Existing tests to keep

- search navigation test
- loading success / retry behavior
- result rendering tests
- storage history tests

### Tests to add or update

1. Route-level layout isolation
   - FITorNOT route should no longer depend on landing shell content
2. Search UI assertions
   - no `ShipAny Two`
   - no pricing text
3. Result UI assertions
   - no alternative recommendation block
4. Loading error state assertions
   - retry and back actions stay present inside the redesigned screen

### Visual verification

Manual verification should check:

- `/zh/fitornot`
- `/zh/fitornot/loading/[entryId]`
- `/zh/fitornot/result/[entryId]`

And compare those surfaces directly against `ui02.txt` for:

- palette
- spacing
- loading-state tone
- page chrome cleanliness
- absence of ShipAny/pricing leakage

## Risks

### Route migration risk

Moving FITorNOT out of the landing group can accidentally break route discovery if old and new trees coexist. Implementation should remove or replace the old route files cleanly.

### Visual drift risk

If implementation leans too heavily on generic shadcn defaults, the result will still feel template-like. The redesign needs explicit tone, spacing, and color overrides.

### Copy leakage risk

Some text can still leak indirectly from shared layout or shared components. Verification must explicitly look for `ShipAny`, `ShipAny Two`, and `pricing`.

## Success Criteria

This redesign is successful when:

1. `/[locale]/fitornot` feels like a standalone FITorNOT tool
2. No visible `ShipAny Two` remains in the FITorNOT flow
3. No pricing list or pricing-oriented section remains in the FITorNOT flow
4. Search, loading, result, and history retain current functionality
5. The visual language clearly matches the calm blue-gray reference from `ui02.txt`
