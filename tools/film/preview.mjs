// Stills of every graphics scene at its last step, under the longest caption spoken over it, to check that
// nothing collides with the caption or the criterion:   node preview.mjs   (writes out/preview/<scene>.png and
// prints any element that reaches under the caption).
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { overlay } from "./overlay.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const narration = JSON.parse(fs.readFileSync(path.join(HERE, "narration.json"), "utf8"));
const text = (id) => narration.lines.find((l) => l.id === id).text;
// scene, last step, the lines spoken over it, its criterion
const SCENES = [["hook", 3, ["hook3"], 0], ["problem", 3, ["prob3"], 1], ["flow", 0, ["flow1"], 1], ["audit", 2, ["rai2"], 4],
  ["engine", 2, ["tech3"], 2], ["models", 2, ["llm1"], 2], ["scale", 2, ["scale2"], 5], ["pilot", 2, ["pilot1", "pilot2"], 6],
  ["score", 2, ["score2"], 0], ["close", 2, ["close1"], 0]];
const out = path.join(HERE, "out", "preview");
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
await context.addInitScript(overlay, { label: narration.label });
const page = await context.newPage();
for (const [scene, last, ids, crit] of SCENES) {
  await page.goto(`${pathToFileURL(path.join(HERE, "film.html")).href}?scene=${scene}`);
  await page.waitForFunction(() => document.body.dataset.ready === "1");
  const caption = ids.map(text).sort((a, b) => b.length - a.length)[0];
  await page.evaluate(([n, c, k, name, sc]) => {
    window.film.step(n);
    if (sc === "flow") window.film.flow(6);
    window.fx.set({ caption: c, crit: k ? String(k) : "", critName: name, progress: 50, curtain: 0 });
  }, [last, caption, crit, narration.criteria[String(crit)] || "", scene]);
  await page.waitForTimeout(3200);
  const clash = await page.evaluate(() => {
    const cap = document.getElementById("fx-cap").getBoundingClientRect();
    const low = [];
    for (const el of document.querySelectorAll(".scene.on *")) {
      const r = el.getBoundingClientRect();
      if (r.height && r.bottom > cap.top - 14 && r.right > cap.left && r.left < cap.right && !el.children.length) low.push(`${el.tagName.toLowerCase()}.${el.className} bottom ${Math.round(r.bottom)}`);
    }
    return { capTop: Math.round(cap.top), lines: Math.round((cap.height - 32) / 39.6), low: low.slice(0, 6) };
  });
  console.log(scene.padEnd(8), `caption top ${clash.capTop}, ${clash.lines} line(s)`, clash.low.length ? `\n   reaches under it: ${clash.low.join("; ")}` : "");
  await page.screenshot({ path: path.join(out, `${scene}.png`) });
}
await browser.close();
