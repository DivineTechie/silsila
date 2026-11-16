# The Silsila film

A film in English (3 min 23 s) and in Arabic (3 min 53 s; Arabic takes longer to say), made automatically: a scripted walk through the
**live site** in a real browser, with a synthetic voiceover. Nothing is staged except the order of the
clicks; what is on screen is the application itself with its fictional demo families.

On screen throughout: **"RECORDED · fictional families · synthetic voice (Azure)"**, and in the Arabic
version a note that the Arabic narration is a machine translation pending native review.

| File | What it is |
|---|---|
| `narration.json` | The narration, line by line, in English and Arabic, and the on-screen label. Every number spoken is in `README.md` or `docs/evidence/`. |
| `make_voice.py` | Records each line with Azure AI Speech (`en-GB-RyanNeural`, `ar-AE-HamdanNeural`). Only the narration is sent; lines are cached by a hash of their text. |
| `record.mjs` | Drives the site with Playwright and records the screen at 1920x1080: Watch a cascade (13 steps), the Family Twin, voice intake, the chatbot contrast, FHIR import, Outcomes and Evidence. Each line's caption is shown while it is spoken. Writes when each line started. |
| `build.mjs` | Lays the voice clips onto the recording at those times with ffmpeg and writes the MP4. |

## Make it again

```bash
cd tools/film
npm install
npx playwright install chromium-headless-shell ffmpeg
AZURE_SPEECH_KEY=... AZURE_SPEECH_REGION=uaenorth uv run --with httpx python make_voice.py
node record.mjs --lang en && node build.mjs --lang en
node record.mjs --lang ar && node build.mjs --lang ar
```

`record.mjs` uses Playwright's headless Chromium and records the hosted site by default; pass
`--web http://localhost:3000 --api http://localhost:8000` to record a local run. It prints any step that did
not behave as scripted ("problems"); re-record if there are any.

The videos are written to `tools/film/out/` (`silsila-film-en.mp4`, `silsila-film-ar.mp4`). That folder is
not in the repository: the files are large and can be rebuilt.

## Honesty notes
- The films recorded on 16 Nov 2026 were checked frame by frame at sample points and for audio level; nobody has
  yet watched them through with the sound on. Do that before sending the link.
- The voice is synthetic. No clip has been checked by a native Arabic listener.
- The Arabic narration is a machine translation, like the rest of the Arabic in the prototype.
- The voice-intake scene shows the hosted site's recorded run (labelled RECORDED in the app), not live speech
  recognition.
- The film shows one fictional family and one simulated clan. The claims about yield rest on the benchmarks
  in `docs/evidence/`, and the narration says "across many simulated clans" where it quotes them.
