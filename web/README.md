# Silsila web

Next.js (App Router) + TypeScript + Tailwind front end for the Silsila API.
Prototype with **fictional** families. No AI-written text: every person-facing
sentence comes from the API as approved template parts or verbatim MedlinePlus
quotations, and is rendered exactly as given.

## Run

```bash
# 1. API (from backend/)
uv run python -m silsila.api.seed
uv run uvicorn silsila.api.app:app --port 8000

# 2. Web (from web/)
npm install
npm run dev            # http://localhost:3000
# or: npm run build && npm start
```

If port 8000 is taken, run the API elsewhere and point the web app at it:
`NEXT_PUBLIC_API_URL=http://localhost:8010 npm run dev` (the value is inlined
at build time, so set it for `npm run build` too).

### Environment

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Silsila API base URL |

### Demo accounts

The sign-in form is empty on purpose. Demo usernames are `mariam` and `reem`
(family) and `counsellor`. Their passwords are the test values in
`backend/.env` (copied from `backend/.env.example`), keys
`SILSILA_DEMO_FAMILY_PASSWORD` and `SILSILA_DEMO_COUNSELLOR_PASSWORD`.

## Screens

| Route | Who | What |
|---|---|---|
| `/` | everyone | What Silsila is, sign-in, link to Evidence, "About this information" |
| `/family`, `/family/[caseId]` | family | Pedigree diagram, per-relative calculated chance, couples, permissions (compute / invite), inform-relatives flow (relative → channel → disclosure → preview), "Don't inform", invitation timelines, ask a question, simple tree editor |
| `/r/[code]` | relative (no account) | Invitation message, anonymity notice, sourced information, comprehension check, book / decline, ask a question |
| `/counsellor` | counsellor | Work queue (priority, reasons, age), cases, messages inbox (rule / n-gram / LLM labels, resolve), audit log with chain status, demo tools (blocked unapproved text, audit tampering) when `/api/health` reports `demo_mode` |
| `/counsellor/cases/[caseId]` | counsellor | Tree, report, "Show the working" (alleles, derivations with formula and inputs, citations, limitations, per-person and per-couple numbers), invitations (approve & send, record result), case audit, FHIR export (download / copy) |
| `/evidence` | everyone | Benchmark files from `docs/evidence` (cascade-yield chart, triage sensitivity/specificity by language variety, privacy run, other files rendered generically) and the parameter register |

## Design rules followed

- Provenance label on every value: Recorded, Calculated, Quoted source, Approved wording.
- Neutral information design: no red/green risk colouring, no directive wording.
- English and Arabic (RTL, Western digits). Arabic interface text is machine-translated and pending native clinical review; the footer says so.
- Keyboard focus visible, labelled inputs, AA contrast, `prefers-reduced-motion`, light and dark themes.
- Installable PWA (`/manifest.webmanifest`, icons in `public/icons`, regenerate with `node scripts/make-icons.mjs`).
- Session token kept in memory and `sessionStorage` only.
