---
name: PC Radar
description: Compatibility-checked PC building tool, sober dark-tech interface with a single emerald accent
colors:
  bg: "#0e0f11"
  surface: "#141517"
  surface-2: "#1a1b1e"
  surface-3: "#222327"
  line: "#26272b"
  line-strong: "#35363c"
  text: "#ececee"
  text-2: "#a3a3ab"
  text-3: "#81828a"
  accent: "#3ecf8e"
  accent-hover: "#5fdba3"
  accent-ink: "#05140d"
  danger: "#f07171"
  photo-bg: "#f4f4f5"
typography:
  display:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "clamp(2.3rem, 5vw, 3.6rem)"
    fontWeight: 650
    lineHeight: 1.04
    letterSpacing: "-0.045em"
  title:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "clamp(1.7rem, 3vw, 2.25rem)"
    fontWeight: 620
    lineHeight: 1.15
    letterSpacing: "-0.03em"
  body:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  data:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontWeight: 500
    fontVariantNumeric: "tabular-nums"
rounded:
  sm: "8px"
  md: "12px"
  lg: "16px"
  full: "999px"
spacing:
  sm: "12px"
  md: "24px"
  lg: "56px"
  xl: "72px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.sm}"
    padding: "11px 20px"
  button-secondary:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text}"
    border: "1px solid {colors.line-strong}"
    rounded: "{rounded.sm}"
    padding: "11px 20px"
  button-danger:
    backgroundColor: "transparent"
    textColor: "{colors.danger}"
    rounded: "{rounded.sm}"
    padding: "11px 20px"
---

# Design System: PC Radar

Source of truth for tokens: `:root` in `static/style.css`. This document describes what shipped in the 2026-09 redesign (made with the taste-skill `design-taste-frontend` / `redesign-existing-projects` guidance), replacing the former "Radar Room" system (DotGothic16, teal + copper, grid background, corner brackets).

## Overview

**Design read:** product tool for French-speaking PC builders (first-timers and enthusiasts), sober dark-tech language in the Linear / Vercel family, vanilla CSS on the existing static-HTML stack.

**Dials:** variance 6, motion 4, density 5.

- Dark only (`color-scheme: dark`), chosen explicitly by the owner over a light/auto option.
- Neutral charcoal ground, no green tint. Depth comes from stepped surfaces (`surface` → `surface-3`) and 1px lines, not from glow.
- One accent, emerald `#3ecf8e`, carrying meaning: primary action, selected component, compatible state, best price, winning score.
- Real product data wherever a visual is needed (the home hero shows a real build pulled from `/api/components` and checked live by `/api/check-compatibility`). No fake screenshots.

## Colors

### Named Rules
**The One-Accent Rule.** Emerald is the only hue with meaning. Red (`danger`) exists only for real error/incompatibility states. Prices, category headers and specs use text colors, never a second accent.

**Legacy aliases.** `--led`, `--copper`, `--panel`, `--border`, `--text-dim`… still exist in `:root` as aliases to the new tokens, because JS-generated inline styles reference them. New code uses the new names.

**Product photos.** Raw Amazon images sit on `photo-bg` (`#f4f4f5`) with `mix-blend-mode: multiply`; background-removed images (`.is-transparent`) sit on `surface-2`.

## Typography

**Geist** for all UI text, **Geist Mono** for data only (prices, totals, scores, the VS badge). Loaded from Google Fonts.

### Named Rules
**The Data-Only Mono Rule.** Monospace is for numbers and measurements, always with `tabular-nums`. Never used as a "tech" costume on labels or headings.

**Sentence case.** No all-caps headings, no uppercase tracked eyebrows above sections.

## Layout

- Container max-width 1200px, 24px gutters (16px under 640px).
- Home page uses distinct layout families per section: split hero (copy + live build panel), row list (profiles), asymmetric bento (5 cells: 4×2 / 2×2 / 2 / 2 / 2), horizontal flow line (3 steps), CTA band.
- All multi-column layouts collapse to one column under 640px; no horizontal page scroll.

## Shapes

One radius scale, applied everywhere:
- `sm` 8px: buttons, inputs, selects, chips, thumbnails
- `md` 12px: cards (`.chip-card`, component cards, modals' inner blocks)
- `lg` 16px: hero panel, bento cells, modal box, build summary
- `full`: toggle switch, score ring, step dots

## Elevation & Motion

- Flat surfaces; a single large tinted shadow (`--shadow-lg`) only on floating layers: hero build panel, modals, search dropdown, lightbox.
- Transitions 200-300ms on `cubic-bezier(0.16, 1, 0.3, 1)`, transform/opacity only.
- Hover: component and link cards lift 2px; buttons press down 1px on `:active`.
- Page content fades in on load; home sections reveal on scroll via IntersectionObserver.
- Everything collapses to instant under `prefers-reduced-motion: reduce`.

## Components

- **Buttons:** primary (emerald fill), secondary (surface-2 + strong line), danger (red outline), `.btn-link` (text + arrow, for the secondary hero action).
- **Component card** (`.component-btn`): photo tile, name, specs, mono price. Selected = emerald border + inset ring + soft emerald wash.
- **Compat result:** soft emerald or soft red panel, icon + text; the text stays in body color for readability.
- **Navigation:** sticky translucent header, 60px tall, wordmark with favicon mark, pill-highlighted active link, collapses to a menu under 960px.
- **Icons:** Phosphor (regular weight) via jsDelivr. No emoji in UI.

## Do's and Don'ts

### Do
- Reuse tokens from `:root`; add a new token before adding a raw hex.
- Keep class names stable: the page scripts build markup with them.
- Show real data or an honest empty/error state, never invented numbers.

### Don't
- Don't add a second accent, glow effects, or a background grid.
- Don't use em-dashes in visible UI copy (legal pages excepted until reviewed).
- Don't use three identical cards in a row as a feature layout.
