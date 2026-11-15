"""Pre-record read-aloud clips for approved content with Azure AI Speech.

    AZURE_SPEECH_KEY=... AZURE_SPEECH_REGION=uaenorth uv run python scripts/make_read_aloud.py

The clips are a SYNTHETIC voice reading text that is already approved: fixed templates, the MedlinePlus
paragraphs a relative can be shown (English original, and the Arabic machine translation where one exists)
and the comprehension questions. Nothing is written or rephrased: the text sent to the speech service is the
approved text, character for character, and each clip is stored under the SHA-256 of that text. If a text
changes, its old clip no longer matches and is not played (and `--prune` deletes it).

Only public, non-personal text is sent to the speech service. Existing clips are kept; only missing ones
are requested. The free tier allows 20 requests a minute, so the script pauses between requests.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from xml.sax.saxutils import escape

import httpx

from silsila.content import AUDIO, registry, sha256

VOICES = {"en": ("en-GB", "en-GB-SoniaNeural"), "ar": ("ar-AE", "ar-AE-FatimaNeural")}
FORMAT = "audio-16khz-32kbitrate-mono-mp3"
BITRATE = 32000
RATE = "-8%"  # slightly slower than the default, for listeners who are not fluent readers


def ssml(lang: str, text: str) -> str:
    locale, voice = VOICES[lang]
    body = '<break time="500ms"/>'.join(escape(line) for line in text.split("\n"))
    return (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{locale}">'
            f'<voice name="{voice}"><prosody rate="{RATE}">{body}</prosody></voice></speak>')


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prune", action="store_true", help="delete clips whose text is no longer approved content")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    reg = registry()
    wanted = reg.read_aloud_texts()
    mfile = AUDIO / "manifest.json"
    manifest = json.loads(mfile.read_text()) if mfile.exists() else {"meta": {}, "clips": {"en": {}, "ar": {}}}
    todo = [w for w in wanted if sha256(w["text"]) not in manifest["clips"][w["lang"]]
            or not (AUDIO / manifest["clips"][w["lang"]][sha256(w["text"])]["file"]).exists()]
    print(f"{len(wanted)} texts, {len(todo)} to record, {sum(len(w['text']) for w in todo):,} characters")
    if args.dry_run:
        return
    if todo:
        key, region = os.environ.get("AZURE_SPEECH_KEY"), os.environ.get("AZURE_SPEECH_REGION", "uaenorth")
        if not key:
            sys.exit("Set AZURE_SPEECH_KEY (and AZURE_SPEECH_REGION) to record the missing clips")
        url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        with httpx.Client(timeout=120) as client:
            for i, w in enumerate(todo):
                h = sha256(w["text"])
                for attempt in range(6):
                    r = client.post(url, content=ssml(w["lang"], w["text"]).encode("utf-8"), headers={
                        "Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": FORMAT, "User-Agent": "silsila-read-aloud"})
                    if r.status_code == 429:
                        time.sleep(20 * (attempt + 1))
                        continue
                    r.raise_for_status()
                    break
                else:
                    sys.exit("The speech service kept refusing requests (rate limit); run again later")
                rel = f"{w['lang']}/{h[:16]}.mp3"
                (AUDIO / w["lang"]).mkdir(parents=True, exist_ok=True)
                (AUDIO / rel).write_bytes(r.content)
                manifest["clips"][w["lang"]][h] = {
                    "file": rel, "voice": VOICES[w["lang"]][1], "kind": w["kind"], "id": w["id"],
                    "chars": len(w["text"]), "seconds": round(len(r.content) * 8 / BITRATE, 1)}
                print(f"  {i + 1}/{len(todo)} {w['lang']} {w['kind']} {w['id']} {len(r.content):,} bytes")
                mfile.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
                time.sleep(3.2)
    keep = {(w["lang"], sha256(w["text"])) for w in wanted}
    stale = [(lang, h) for lang in ("en", "ar") for h in manifest["clips"][lang] if (lang, h) not in keep]
    if stale and args.prune:
        for lang, h in stale:
            (AUDIO / manifest["clips"][lang].pop(h)["file"]).unlink(missing_ok=True)
        print(f"pruned {len(stale)} clips whose text is no longer approved content")
    elif stale:
        print(f"{len(stale)} clips no longer match approved text (never played; --prune deletes them)")
    clips = [c for lang in ("en", "ar") for c in manifest["clips"][lang].values()]
    manifest["meta"] = {
        "provider": "Azure AI Speech (neural text to speech)", "synthetic": True,
        "voices": {lang: v[1] for lang, v in VOICES.items()}, "format": FORMAT, "rate": RATE,
        "generated": dt.date.today().isoformat(),
        "clips": len(clips), "minutes": round(sum(c["seconds"] for c in clips) / 60, 1),
        "note": ("Synthetic voice reading approved text exactly; each clip is keyed by the SHA-256 of its text. "
                 "Arabic clips read the machine translation, which is pending native clinical review. No clip "
                 "has yet been checked by a native listener."),
    }
    AUDIO.mkdir(parents=True, exist_ok=True)
    mfile.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(f"manifest: {manifest['meta']['clips']} clips, {manifest['meta']['minutes']} minutes")


if __name__ == "__main__":
    main()
