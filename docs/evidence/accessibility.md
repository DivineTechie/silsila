# Accessibility audit (axe-core)

**Date:** 15 Nov 2026. **Tool:** axe-core 4.10.2, rule sets `wcag2a`, `wcag2aa`, `wcag21aa` and `best-practice`
(the home page and the cascade replay were also checked with `wcag22aa`),
run in the browser against the local build with demo data.

**Coverage.** Every screen a judge or user can reach, with every tab opened and every collapsed section
expanded, in two configurations:

1. English, light theme, desktop width (1440 px or the pane width).
2. Arabic (right to left), dark theme, phone width (375 × 812).

| Screen | States checked |
|---|---|
| Home with judge mode | default |
| Watch a cascade | all 12 steps run live, English desktop and Arabic dark phone |
| Family Twin (3D) | table view open, a person selected, line of descent shown, cascade race playing |
| Evidence | scenario calculator, all benchmark files, all tables and raw data expanded |
| Family case (Mariam, CAH; Reem, beta-thalassaemia; Reem's case list) | all 8 tabs |
| Relative's invitation link | information expanded |
| Counsellor console | all 5 tabs, voice intake after the engine calculation |
| Counsellor case view | all 8 tabs, FHIR export shown |

**Result: 0 violations on every screen in both configurations**, after the fixes below.

**Issues found and fixed in this audit**

| Rule | Impact | Where | Fix |
|---|---|---|---|
| `scrollable-region-focusable` | serious | evidence charts and tables, audit log, family-tree diagram, tables in the counsellor views, Family Twin table and race list | every scrolling area is keyboard-focusable and named (`tabIndex=0`, `role=region`, unique `aria-label`) |
| `color-contrast` | serious | source title inside citation chips (3.78:1) | removed the 75% opacity; full-contrast text with normal weight |
| `definition-list` | serious | triage evidence summary | moved a stray file-path label out of the `<dl>` |
| `heading-order` | moderate | family case tabs (headings jumped from level 1 to 3) | each tab panel now has a level-2 heading for screen readers, named after the tab |
| `landmark-unique` | moderate | regions added during the audit | region names include the section they belong to |
| `listitem`, `aria-allowed-role` | serious, minor | race list (introduced during the audit) | the region wraps the list instead of replacing its role |

**Not covered by automated checks.** Screen-reader walkthroughs (VoiceOver, NVDA, TalkBack), keyboard-only task
completion timing, and testing with disabled users. These belong in the pilot's usability sessions
(see `docs/pilot-protocol.md`). The 3D scene is decorative for assistive technology; the same information is
available as a sortable table and in the side panels.
