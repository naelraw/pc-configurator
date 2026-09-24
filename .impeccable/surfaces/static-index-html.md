---
version: 1
slug: "static-index-html"
primary_target: "static/index.html"
related_targets: ["static/style.css"]
---

## Scope

Primary target: static/index.html (home, Persuade mode) plus the shared design system in static/style.css, which every other page (configurateur, comparateur, assistant, estimer-fps, compte, build-view, admin) inherits. This surface establishes the visual world; other pages extend it without a new concept round.

Audience: French-speaking beginners and hardware-literate enthusiasts, equally. Job/task/constraints/proof: see PRODUCT.md (Users, Positioning, Operating Context, Evidence on Hand). Nothing to add beyond product truth here.

## Direction contract

**THESIS:** A PC-building tool's home page defaults to either an RGB-glass-case hero glamour shot or a clean minimal SaaS hero — this surface refuses both. Instead, the site reads as an air-traffic-control radar room: every component the visitor adds is a contact detected and tracked on a scope, and "compatible" or "incompatible" is not a badge, it is a signal that either locks onto the sweep or drops off it.

**OWN-WORLD:** Near-black CRT ground (`#0a0f0d`, matching the existing `--led`-style dark base already in style.css) with a phosphor-green primary signal color, a dim amber secondary for warnings, and a cold red for incompatibility — never used decoratively, only as real state. Concentric range rings and a rotating sweep line anchor the hero as a literal radar scope; component cards read as radar contacts (a blip, a bearing/range readout in monospace, a data tag). Typography: a monospace/technical face (system mono or a grotesk-mono web font) for all numeric/status readouts and labels, paired with a plain, highly legible grotesk for body copy so the beginner audience is never forced to parse callsign-speak for ordinary sentences. Hairline rules and a coordinate-grid texture (faint, low-contrast) replace the current plain card borders.

**STORY:** A first-time visitor understands within the hero that this tool "scans" their build for compatibility the way radar scans for contacts — reassuring for a beginner (it's watching out for you), satisfying for an enthusiast (it reads like real instrumentation, not a toy). The primary action (start a build / go to configurateur) is the one console button on the scope.

**FIRST VIEWPORT:** Full-bleed dark radar scope fills the hero at the top of the page: concentric range rings centered right-of-viewport on desktop (left-aligned headline and CTA occupy the left third), a slow CSS-driven sweep line rotating continuously (respects `prefers-reduced-motion`: freezes to a static bearing line), 3–4 example component "blips" (CPU, GPU, RAM, carte mère) placed at fixed bearings with small monospace data tags (name + one key spec), one blip shown mid-sweep highlight to demonstrate the "detection" motion. Headline in the grotesk face states the product's real mechanism in one line (compatibility + IA), not a generic tagline. Primary CTA button styled as a console/instrument button (rectangular, hairline border, phosphor-green glow on hover/focus) linking to /configurateur.

**FORM:** Assigned-direction pick — this was IMPECCABLE'S PICK card (my top-ranked grounded candidate, not the script's dice-assigned index 4/"electronics workbench"), chosen by the user directly from the presented options; familiar-but-effective is accepted as a legitimate destination. Seed key: 75d0c952 (concept-seed --scope direction --mode persuade). Raises folds skipped since the user picked the pick card, not the assigned/challenger path — no borrowed disciplines apply here.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

## Notes

- Rebrand: display name changes from "PC Configurator" to "PC Radar" everywhere in the UI (see PRODUCT.md Brand Commitments) — logo, `<title>` tags, header wordmark across all pages.
- No image generation available this session: code-led build, no comp round. Ambition is carried entirely by this contract's FIRST VIEWPORT block, audited at finish against this text rather than against a generated comp.
- No browser tooling available this session for automated screenshot verification — finish inspection will be described in text and the user is asked to visually confirm in their own browser; this substitution is disclosed, not silent.
- Must preserve: Amazon affiliate links/tags, all existing functionality (compatibility logic, admin flows, auth), French copy and terminology already in use, and the site's actual data (no fabricated testimonials/metrics per PRODUCT.md Evidence on Hand).
