// Lays the voice onto the silent recording at the times record.mjs wrote down, adds a very quiet music bed,
// and writes one MP4.
//
//   node build.mjs               # out/silsila-demo-film.mp4
//   node build.mjs --no-music
//
// Needs ffmpeg on the PATH. The voice is synthetic (Azure AI Speech) and the film says so on screen. The music
// bed is generated here from sine tones (a slow, soft chord); nothing is taken from a recording.

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const music = !process.argv.includes("--no-music");
const tl = JSON.parse(fs.readFileSync(path.join(HERE, "out", "timeline.json"), "utf8"));
const raw = path.join(HERE, "out", "raw.webm");
const out = path.join(HERE, "out", "silsila-demo-film.mp4");
const T = Math.ceil(tl.seconds);

const args = ["-y", "-i", raw];
for (const l of tl.lines) args.push("-i", path.join(HERE, l.file));
const n = tl.lines.length;
const filters = tl.lines.map((l, i) => `[${i + 1}:a]aresample=48000,adelay=${Math.round(l.at * 1000)}:all=1[a${i}]`);
filters.push(`${tl.lines.map((_, i) => `[a${i}]`).join("")}amix=inputs=${n}:normalize=0:dropout_transition=0,loudnorm=I=-16:TP=-1.5:LRA=11[voice]`);
if (music) {
  // A minor ninth, low and slow: five sine tones, gently swelling, filtered soft, faded in and out.
  const tones = [110, 164.81, 220, 261.63, 329.63];
  tones.forEach((f, i) => {
    args.push("-f", "lavfi", "-t", String(T), "-i", `sine=frequency=${f}:sample_rate=48000`);
    filters.push(`[${n + 1 + i}:a]volume=${i < 2 ? 0.5 : 0.32},tremolo=f=${(0.1 + i * 0.03).toFixed(2)}:d=0.55[m${i}]`);
  });
  filters.push(`${tones.map((_, i) => `[m${i}]`).join("")}amix=inputs=${tones.length}:normalize=0,lowpass=f=900,aecho=0.8:0.7:420|660:0.35|0.25,` +
    `volume=0.05,afade=t=in:st=0:d=3,afade=t=out:st=${T - 4}:d=4[bed]`);
  filters.push(`[voice][bed]amix=inputs=2:normalize=0:dropout_transition=0[aout]`);
} else {
  filters.push(`[voice]anull[aout]`);
}
args.push(
  "-filter_complex", filters.join(";"),
  "-map", "0:v", "-map", "[aout]",
  "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart",
  "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-t", String(T),
  "-metadata", "title=Silsila - demo film (recorded from the live site; fictional families; synthetic voice)",
  out,
);
execFileSync("ffmpeg", args, { stdio: ["ignore", "ignore", "inherit"] });
const mb = (fs.statSync(out).size / 1e6).toFixed(1);
console.log(`${out}: ${Math.floor(tl.seconds / 60)} min ${Math.round(tl.seconds % 60)} s, ${mb} MB, ${n} narration lines, music ${music ? "on" : "off"}, ${tl.problems.length} recording problems`);
