# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two audiences served equally by the same interface:
- Beginners assembling their first PC, who need guidance, plain-language explanations, and reassurance that the parts they pick will actually work together.
- Hardware-literate enthusiasts who already know their specs, want to move fast, and should never feel talked down to.
Both are French-speaking (site is entirely in French).

## Product Purpose

A free, independently-run PC-building companion: users pick components (CPU, motherboard, RAM, case, PSU, GPU, storage, cooling), get automatic compatibility validation between parts, compare real Amazon prices across the catalog, ask an AI assistant for build advice, and get AI-estimated FPS for games on a given configuration. Users can create an account to save, edit, share, and delete their builds.

## Positioning

Unlike a plain price comparator (or PCPartPicker-style parts list), the differentiator is the integrated intelligence layer: automatic compatibility checking between every pair of selected parts, an AI assistant for build guidance, and AI-driven FPS estimation, all in one place — not three separate tools. This "smart all-in-one" angle is what future visual work should foreground, over generic price-comparison framing.

## Operating Context

- **Catalog ingestion (admin-only):** paste an Amazon ASIN → Bright Data fetches real product data → AI cleans the title and fills in missing specs from the description → background is auto-removed from the product image → component is saved to the database immediately, no manual review step.
- **Price freshness:** a scheduled job checks Amazon links daily/monthly; dead links are auto-repaired by re-fetching from Amazon when possible.
- **User accounts:** registration/login, saved builds (create, edit, rename, delete, share via link), and a broken-link reporting flow that queues a correction for admin review.
- **Admin panel:** collapsible sections, ASIN import, bulk price refresh, dead-link corrections queue, "delete all components" (double-confirmed), all gated behind an admin secret.
- Hosted on the user's own Oracle Cloud VM at pcradar.tech (self-hosted, HTTPS via Let's Encrypt) — not a commercial hosting budget, so the product has no paid infrastructure tier to design around.

## Capabilities and Constraints

- Component categories: CPU, Carte mère (motherboard), RAM, Boîtier (case), Alimentation (PSU), GPU, Stockage (storage), Refroidissement (cooling).
- Compatibility checks run pairwise across categories (e.g. CPU↔socket, RAM↔motherboard, GPU/PSU↔case) and are designed to skip silently rather than false-flag when a spec is missing — components can be saved with incomplete specs.
- Existing pages: accueil (home), configurateur (build a PC), comparateur (price comparison + component detail), assistant (AI chat advisor), estimer-fps (FPS estimator), compte (account/builds), build-view (shared read-only build), admin.
- Revenue mechanism: Amazon affiliate tag on outbound product links — must remain visible/functional through any redesign.
- No paid ad placements or third-party ads.

## Brand Commitments

- **Renaming in progress:** the product is moving from the displayed name "PC Configurator" to **"PC Radar"**, to match the pcradar.tech domain. Future design/copy work should use "PC Radar" as the product name (logo, title, header) going forward, replacing "PC Configurator" wherever it appears in the UI.
- No existing logo mark beyond a text wordmark ("PC CONFIGURATOR" in the header); a redesign is free to establish a real mark under the new name.

## Evidence on Hand

- Real, live component catalog in production (Turso DB) with real Amazon prices, images, and descriptions — not placeholder data.
- No testimonials, press, case studies, or usage metrics exist; none should be fabricated.

## Product Principles

1. Compatibility and price accuracy are trust-critical — never let visual redesign obscure a compatibility warning or a price/link.
2. Speak to both the nervous first-time builder and the fast-moving enthusiast without forcing either into the other's mode.
3. The AI-assistant and FPS-estimation features are the product's real edge over generic parts pickers — they should read as integrated, not bolted on.
4. Stay honest about being a free, independent, ad-free project — no design pattern that implies a commercial vendor, sponsorship, or urgency that isn't real (no fake scarcity/countdown patterns).

## Accessibility & Inclusion

No specific standard established yet; not addressed further at this stage.
