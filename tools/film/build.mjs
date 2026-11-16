// Lays the voice clips onto the silent recording at the times record.mjs wrote down, and writes an MP4.
//
//   node build.mjs --lang en      # out/silsila-film-en.mp4
//
// Needs ffmpeg on the PATH. The voice is synthetic (Azure AI Speech) and the video says so on screen.

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const i = process.argv.indexOf("--lang");
const LANG = i > 0 ? process.argv[i + 1] : "en";
const tl = JSON.parse(fs.readFileSync(path.join(HERE, "out", `timeline-${LANG}.json`), "utf8"));
const raw = path.join(HERE, "out", `raw-${LANG}.webm`);
const out = path.join(HERE, "out", `silsila-film-${LANG}.mp4`);

const args = ["-y", "-i", raw];
for (const l of tl.lines) args.push("-i", path.join(HERE, l.file));
const delays = tl.lines.map((l, n) => `[${n + 1}:a]adelay=${Math.round(l.at * 1000)}:all=1[a${n}]`);
const mix = `${tl.lines.map((_, n) => `[a${n}]`).join("")}amix=inputs=${tl.lines.length}:normalize=0:dropout_transition=0,loudnorm=I=-16:TP=-1.5:LRA=11[aout]`;
args.push(
  "-filter_complex", [...delays, mix].join(";"),
  "-map", "0:v", "-map", "[aout]",
  "-c:v", "libx264", "-preset", "medium", "-crf", "24", "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart",
  "-c:a", "aac", "-b:a", "128k", "-t", String(Math.ceil(tl.seconds)),
  "-metadata", `title=Silsila (${LANG}) - recorded demo, fictional families, synthetic voice`,
  out,
);
execFileSync("ffmpeg", args, { stdio: ["ignore", "ignore", "inherit"] });
const mb = (fs.statSync(out).size / 1e6).toFixed(1);
console.log(`${out}: ${tl.seconds.toFixed(0)} s, ${mb} MB, ${tl.lines.length} narration lines, ${tl.problems.length} recording problems`);
