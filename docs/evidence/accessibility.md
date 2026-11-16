# Accessibility audit (axe-core)

**Date:** 16 Nov 2026 (the whole audit was repeated after the changes of 15 and 16 Nov). **Tool:** axe-core
4.10.2, rule sets `wcag2a`, `wcag2aa`, `wcag21aa`, `wcag22aa` and `best-practice`, run in the browser against
the local build with demo data.

**Coverage.** Every screen a judge or user can reach, with every tab opened and every collapsed section
expanded, in two configurations:

1. English, light theme, desktop width (1440 px, or the pane width where the pane was narrower).
2. Arabic (right to left), dark theme, phone width (375 × 812).

| Screen | States checked |
|---|---|
| Home | default; with the "Ask about Silsila" guide open showing an answer with a live lookup, a declined personal question and a "no answer" |
| Watch a cascade | all 13 steps run live, checked at every step |
| Family Twin (3D) | default; table view open, a person selected, a result recorded, line of descent shown; cascade race playing |
| Evidence | every section and table expanded, the newborn scenario preset chosen, the guide open |
| Relative's invitation link | read-aloud buttons present, every common question opened, comprehension check answered |
| Counsellor console | all 6 tabs; FHIR import with the sample record read, and with a refused record |
| Counsellor case view | all 6 tabs (family tree, report, working, invitations, audit, FHIR export) |
| Family case (Mariam in English, Reem in Arabic) | all 6 tabs |

**Result: 0 violations on every screen in both configurations**, after the fixes below.

**Issues found and fixed in the 16 Nov audit**

| Rule | Impact | Where | Fix |
|---|---|---|---|
| `color-contrast` | serious | the "Live lookup" label in the guide, light theme (brass text on a tinted panel) | uses the secondary ink colour |
| `color-contrast` | serious | the newborn's tag in the Family Twin scene (white on bright pink) | darker pink background |

**Issues found and fixed in the first audit (15 Nov)**

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
(see `docs/pilot-protocol.md`). In the Family Twin the 3D canvas and the labels drawn over it are hidden from
assistive technology; the same information is available as a sortable table and in the cards beside it.
Read-aloud clips are a synthetic voice and have not been checked by a native listener.
