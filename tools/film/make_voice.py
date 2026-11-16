"""Record the film's voiceover with Azure AI Speech: one clip per narration line.

    AZURE_SPEECH_KEY=... AZURE_SPEECH_REGION=uaenorth uv run --with httpx python make_voice.py

The voice is SYNTHETIC and the film says so on screen. Only the narration in narration.json is sent to the
speech service (no personal data). Clips are cached by a hash of their text, voice and rate, so only changed
lines are recorded again. Writes out/voice/<id>-<hash>.mp3 and out/voice/index.json (durations in seconds).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from xml.sax.saxutils import escape

import httpx

HERE = Path(__file__).resolve().parent
OUT = HERE / "out" / "voice"
FORMAT = "audio-48khz-192kbitrate-mono-mp3"


def duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main() -> None:
    doc = json.loads((HERE / "narration.json").read_text())
    locale, voice = doc["voice"]
    rate = doc.get("rate", "0%")
    key, region = os.environ.get("AZURE_SPEECH_KEY"), os.environ.get("AZURE_SPEECH_REGION", "uaenorth")
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    with httpx.Client(timeout=120) as client:
        for line in doc["lines"]:
            say = line.get("say") or line["text"]
            digest = hashlib.sha256(f"{voice}\n{rate}\n{say}".encode()).hexdigest()[:12]
            path = OUT / f"{line['id']}-{digest}.mp3"
            if not path.exists():
                if not key:
                    sys.exit("Set AZURE_SPEECH_KEY to record the missing lines")
                ssml = (f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{locale}">'
                        f'<voice name="{voice}"><prosody rate="{rate}">{escape(say)}</prosody></voice></speak>')
                for attempt in range(6):
                    r = client.post(url, content=ssml.encode("utf-8"), headers={
                        "Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": FORMAT, "User-Agent": "silsila-film"})
                    if r.status_code == 429:
                        time.sleep(20 * (attempt + 1))
                        continue
                    r.raise_for_status()
                    break
                else:
                    sys.exit("The speech service kept refusing requests (rate limit); run again later")
                path.write_bytes(r.content)
                time.sleep(3.2)
            index.append({"id": line["id"], "file": str(path.relative_to(HERE)), "caption": line["text"], "seconds": round(duration(path), 2)})
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(index)} lines, {sum(x['seconds'] for x in index):.1f} s of speech ({voice}, rate {rate})")


if __name__ == "__main__":
    main()
