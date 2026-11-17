// Lays the voice onto the silent recording at the times record.mjs wrote down, adds the music bed and the
// sound effects that make_sound.py generated, and writes one MP4.
//
//   node build.mjs               # out/silsila-demo-film.mp4
//   node build.mjs --no-music    # voice and effects only
//   node build.mjs --no-sfx      # voice and music only
//   node build.mjs --raw=FILE    # use a patched copy of the recording instead of out/raw.webm
//
// Needs ffmpeg on the PATH. The voice is synthetic (Azure AI Speech) and the film says so on screen. The music
// and the effects are computed from sine tones and noise by make_sound.py; nothing is taken from a recording.
// The music is kept well under the voice and is lowered further while a line is being spoken.

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const music = !process.argv.includes("--no-music") && fs.existsSync(path.join(HERE, "out", "music.wav"));
const sfx = !process.argv.includes("--no-sfx") && fs.existsSync(path.join(HERE, "out", "sfx.wav"));
const tl = JSON.parse(fs.readFileSync(path.join(HERE, "out", "timeline.json"), "utf8"));
const rawArg = process.argv.find((a) => a.startsWith("--raw="));
const raw = rawArg ? path.resolve(rawArg.slice(6)) : path.join(HERE, "out", "raw.webm");
const out = path.join(HERE, "out", "silsila-demo-film.mp4");
const T = Math.ceil(tl.seconds);

const args = ["-y", "-i", raw];
for (const l of tl.lines) args.push("-i", path.join(HERE, l.file));
const n = tl.lines.length;
const filters = tl.lines.map((l, i) => `[${i + 1}:a]aresample=48000,adelay=${Math.round(l.at * 1000)}:all=1[a${i}]`);
// the voice: every line at its time, brought to a standard loudness, in both ears
filters.push(`${tl.lines.map((_, i) => `[a${i}]`).join("")}amix=inputs=${n}:normalize=0:dropout_transition=0,aformat=channel_layouts=stereo,` +
  `loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,asplit=2[voice][key]`);
const mix = ["[voice]"];
let next = n + 1;
if (music) {
  // the bed sits about 13 dB under its file level, and the voice pushes it down by about 6 dB more while it speaks
  args.push("-i", path.join(HERE, "out", "music.wav"));
  filters.push(`[${next}:a]aresample=48000,volume=-13dB,aecho=0.8:0.6:380|610:0.22|0.16[m0]`);
  filters.push(`[m0][key]sidechaincompress=threshold=0.03:ratio=2:attack=180:release=1100[bed]`);
  mix.push("[bed]");
  next += 1;
} else {
  filters.push(`[key]anullsink`);
}
if (sfx) {
  args.push("-i", path.join(HERE, "out", "sfx.wav"));
  filters.push(`[${next}:a]aresample=48000,aecho=0.8:0.5:90|170:0.18|0.1[fx]`);
  mix.push("[fx]");
}
filters.push(`${mix.join("")}amix=inputs=${mix.length}:normalize=0:dropout_transition=0,alimiter=limit=0.89:level=0[aout]`);
args.push(
  "-filter_complex", filters.join(";"),
  "-map", "0:v", "-map", "[aout]",
  "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "25", "-movflags", "+faststart",
  "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", String(T),
  "-metadata", "title=Silsila - demo film (recorded from the live site; fictional families; synthetic voice)",
  out,
);
execFileSync("ffmpeg", args, { stdio: ["ignore", "ignore", "inherit"] });
const mb = (fs.statSync(out).size / 1e6).toFixed(1);
console.log(`${out}: ${Math.floor(tl.seconds / 60)} min ${Math.round(tl.seconds % 60)} s, ${mb} MB, ${n} narration lines, music ${music ? "on" : "off"}, ${sfx ? (tl.events || []).length : 0} sound cues, ${tl.problems.length} recording problems`);
