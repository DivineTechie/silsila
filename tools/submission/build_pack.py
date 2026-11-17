"""Builds the judges' submission pack: one zip with the deck, the judge's guide, the evidence summaries and the
governance documents, plus a START-HERE page with every link. It is published as a GitHub release asset.

    python tools/submission/build_pack.py            # writes submission/Silsila-submission-pack.zip

Needs submission/Silsila_solution_deck.pdf (tools/submission/build_deck.py). Only files tracked in this
repository are copied, apart from the deck and the thumbnail; the benchmark's item files and per-prompt logs
are never included (they are withheld so the benchmark stays usable).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "submission" / "Silsila-submission-pack.zip"

LINKS = [
    ("Live app (no password; one-click roles)", "https://silsila-web.lemonisland-568f9acd.uaenorth.azurecontainerapps.io"),
    ("API health", "https://silsila-api.lemonisland-568f9acd.uaenorth.azurecontainerapps.io/api/health"),
    ("Demo film (5 min 9 s)", "https://youtu.be/fCHWTlGyeSY"),
    ("Source code (Apache-2.0)", "https://github.com/DivineTechie/silsila"),
    ("This pack (latest release)", "https://github.com/DivineTechie/silsila/releases/latest"),
]

# (path in the repository, path in the zip)
FILES = [
    ("submission/Silsila_solution_deck.pdf", "01-deck/Silsila_solution_deck.pdf"),
    ("submission/silsila-youtube-thumbnail.png", "01-deck/film-thumbnail.png"),
    ("docs/JUDGES.md", "02-judges-guide/JUDGES.md"),
    ("README.md", "02-judges-guide/README.md"),
    ("docs/architecture.md", "03-how-it-works/architecture.md"),
    ("docs/production.md", "03-how-it-works/production.md"),
    ("docs/deployment.md", "03-how-it-works/deployment.md"),
    ("docs/identity-oidc.md", "03-how-it-works/identity-oidc.md"),
    ("docs/ai-disclosure.md", "04-responsible-ai/ai-disclosure.md"),
    ("docs/limitations.md", "04-responsible-ai/limitations.md"),
    ("docs/alternatives.md", "05-impact-and-pilot/alternatives.md"),
    ("docs/commercial-case.md", "05-impact-and-pilot/commercial-case.md"),
    ("docs/pilot-protocol.md", "05-impact-and-pilot/pilot-protocol.md"),
    ("bench_llm/PREREGISTRATION.md", "06-evidence/silsila-bench/PREREGISTRATION.md"),
    ("bench_llm/AMENDMENTS.md", "06-evidence/silsila-bench/AMENDMENTS.md"),
]


def tracked(prefix: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", prefix], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if p]


def start_here(commit: str) -> str:
    rows = "\n".join(f"| {name} | {url} |" for name, url in LINKS)
    return f"""# Silsila: submission pack

Future Health Digital Innovation Challenge 2026 · Fertility, Challenge 03: Understanding and Reducing Inherited
Disease Risk. Built from commit `{commit}` on {dt.date.today().isoformat()}.

| What | Link |
|---|---|
{rows}

## What is in this pack

| Folder | Contents |
|---|---|
| 01-deck | The solution deck (organisers' template) and the film's thumbnail |
| 02-judges-guide | `JUDGES.md`: for each of the six criteria, what to open and which number to check; the README |
| 03-how-it-works | Architecture, production readiness, deployment and identity (UAE PASS / Entra ID) |
| 04-responsible-ai | AI disclosure (AI makes no decision in Silsila), limitations |
| 05-impact-and-pilot | Comparison with what exists today, commercial case, pilot protocol |
| 06-evidence | Evidence summaries (JSON and Markdown), governance documents, the benchmark's pre-registration |

Said plainly: no patient has used Silsila. All families are fictional and all evidence comes from simulated
families. The Arabic is machine translation awaiting native clinical review. `SHA256SUMS.txt` lists every file.
"""


def main() -> None:
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                            check=True).stdout.strip()
    files = list(FILES)
    files += [(p, "06-evidence/" + p.removeprefix("docs/evidence/")) for p in tracked("docs/evidence")
              if "/logs/" not in p]
    files += [(p, "04-responsible-ai/governance/" + p.removeprefix("docs/governance/")) for p in tracked("docs/governance")]
    missing = [src for src, _ in files if not (ROOT / src).exists()]
    if missing:
        raise SystemExit("missing: " + ", ".join(missing))
    sums = []
    OUT.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        text = start_here(commit).encode()
        z.writestr("Silsila-submission-pack/00-START-HERE.md", text)
        sums.append((hashlib.sha256(text).hexdigest(), "00-START-HERE.md"))
        for src, dst in files:
            data = (ROOT / src).read_bytes()
            z.writestr("Silsila-submission-pack/" + dst, data)
            sums.append((hashlib.sha256(data).hexdigest(), dst))
        z.writestr("Silsila-submission-pack/SHA256SUMS.txt", "".join(f"{h}  {p}\n" for h, p in sums))
    print(f"{OUT.relative_to(ROOT)}: {len(sums)} files, {OUT.stat().st_size / 1e6:.1f} MB, commit {commit}")


if __name__ == "__main__":
    main()
