// Records the Silsila demo film: animated graphics scenes (film.html) cut together with the LIVE site, driven
// in a real browser, in time with the narration. Run make_voice.py first (it gives each line's length), then:
//
//   node record.mjs                                   # records the hosted site
//   node record.mjs --web http://localhost:3000 --api http://localhost:8000
//
// Output: out/raw.webm (silent video) and out/timeline.json (when each line starts). build.mjs lays the voice
// (and a quiet music bed) onto the video at those times.
//
// What is on screen in the product scenes is the real application with its fictional demo families; nothing is
// staged except the order of clicks. On top of every page this script draws: the caption of the line being
// spoken, the judging criterion the scene speaks to, the label "RECORDED · fictional families · synthetic
// voice (Azure)" over the opening (the closing card says the same in words), a pointer that shows where it
// clicks, zooms, and a dip to dark between pages.

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { overlay } from "./overlay.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const WEB = arg("web", "https://silsila-web.lemonisland-568f9acd.uaenorth.azurecontainerapps.io").replace(/\/$/, "");
const API = arg("api", "https://silsila-api.lemonisland-568f9acd.uaenorth.azurecontainerapps.io").replace(/\/$/, "");
const GFX = pathToFileURL(path.join(HERE, "film.html")).href;
const W = 1920, H = 1080;
const GAP = 320; // silence after each line, ms

const narration = JSON.parse(fs.readFileSync(path.join(HERE, "narration.json"), "utf8"));
const voice = JSON.parse(fs.readFileSync(path.join(HERE, "out", "voice", "index.json"), "utf8"));
const TOTAL = voice.reduce((a, v) => a + v.seconds, 0) + 55; // rough length, for the progress line
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Playwright's own headless Chromium captures exactly the page (installed Chrome clips the bottom of the frame
// by the height of its toolbar). WebGL for the Family Twin runs on the software renderer.
const browser = await chromium.launch({ headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const context = await browser.newContext({
  viewport: { width: W, height: H },
  recordVideo: { dir: path.join(HERE, "out", "rawdir"), size: { width: W, height: H } },
  locale: "en-GB",
  colorScheme: "light",
});

// ---- the overlay, on every page --------------------------------------------------------------------------
await context.addInitScript(overlay, { label: narration.label });

const page = await context.newPage();
const t0 = Date.now();
const timeline = [];
const events = []; // moments that get a sound in the mix: taps, scene changes, a new criterion
const mark = (type) => events.push({ type, at: +((Date.now() - t0) / 1000).toFixed(2) });
const problems = [];
page.on("pageerror", (e) => problems.push(`page error: ${e.message.slice(0, 200)}`));
page.on("console", (m) => m.type() === "error" && !/422|Failed to load resource/.test(m.text()) && problems.push(`console: ${m.text().slice(0, 200)}`));
const note = (what) => (e) => problems.push(`${what}: ${String(e.message || e).split("\n")[0].slice(0, 160)}`);

const fx = (p) => page.evaluate((x) => window.fx && window.fx.set(x), p).catch(() => {});
const progress = () => fx({ progress: (100 * (Date.now() - t0)) / 1000 / TOTAL });

/** Start speaking a line now; resolves when the line (plus a short gap) is over. */
function say(id) {
  const line = voice.find((v) => v.id === id);
  if (!line) throw new Error(`no voice for ${id}`);
  timeline.push({ id, file: line.file, at: (Date.now() - t0) / 1000, seconds: line.seconds });
  void fx({ caption: line.caption, progress: (100 * (Date.now() - t0)) / 1000 / TOTAL });
  return sleep(line.seconds * 1000 + GAP);
}
const quiet = () => fx({ caption: "" });
let critNow = 0;
const criterion = (n) => {
  if (n && n !== critNow) mark("chime");
  critNow = n;
  return fx(n ? { crit: String(n), critName: narration.criteria[String(n)] } : { crit: "" });
};

/** Dip to dark, load a page, and come back up once it has settled. */
async function cut(url, ready) {
  mark("whoosh");
  await fx({ curtain: 1, caption: "" });
  await sleep(480);
  await page.evaluate(() => window.fx && window.fx.cursor(-60, -60, false)).catch(() => {});
  await page.goto(url, { waitUntil: "domcontentloaded" });
  if (ready) await ready().catch(note(`ready ${url.slice(-30)}`));
  else await page.waitForLoadState("networkidle").catch(() => {});
  await sleep(350);
  await fx({ curtain: 0 });
  await sleep(420);
  await progress();
}
let onGfx = false;
async function gfx(scene) {
  if (!onGfx) {
    await cut(`${GFX}?scene=${scene}`, () => page.waitForFunction(() => document.body.dataset.ready === "1", null, { timeout: 20000 }));
    onGfx = true;
  } else {
    mark("swish");
    await page.evaluate((s) => window.film.show(s), scene);
    await sleep(500);
  }
}
const live = async (p, ready) => { onGfx = false; await cut(WEB + p, ready); };
const step = (n) => { mark("pop"); return page.evaluate((k) => window.film.step(k), n); };

const scrollTo = (y) => page.evaluate((top) => window.scrollTo({ top, behavior: "smooth" }), y);
const reveal = (locator, offset = 96) => locator.first().evaluate((el, off) => {
  window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - off, behavior: "smooth" });
}, offset).catch(note("reveal"));
/** Move the pointer to something, show the tap, then really click it. */
async function press(locator) {
  const el = locator.first();
  await el.scrollIntoViewIfNeeded({ timeout: 8000 }).catch(() => {});
  const box = await el.boundingBox().catch(() => null);
  if (box) {
    await page.evaluate(([x, y]) => window.fx.cursor(x, y), [box.x + box.width / 2, box.y + box.height / 2]).catch(() => {});
    await sleep(720);
    await page.evaluate(() => window.fx.tap()).catch(() => {});
    mark("tap");
    await sleep(140);
  }
  await el.click({ timeout: 15000 }).catch(note("click"));
}
async function zoom(locator, scale = 1.28, pull = 0.7) {
  const box = await locator.first().boundingBox().catch(() => null);
  if (!box) return;
  await page.evaluate(([x, y, s, p]) => window.fx.zoom(x, y, s, p), [box.x + box.width / 2, box.y + Math.min(box.height, 620) / 2, scale, pull]).catch(() => {});
}
const unzoom = () => page.evaluate(() => window.fx.unzoom()).catch(() => {});
const flash = async (locator, ms = 2200) => {
  const el = locator.first();
  await el.evaluate((n) => n.classList.add("fx-flash")).catch(() => {});
  setTimeout(() => el.evaluate((n) => n.classList.remove("fx-flash")).catch(() => {}), ms);
};

// ---- Watch a cascade helpers ----------------------------------------------------------------------------
const controls = () => page.locator("main section").first();
const nextButton = () => controls().locator("button").nth(2);
const sees = () => page.locator("main .grid.content-start > section").nth(0);     // "What ... sees"
const recorded = () => page.locator("main .grid.content-start > section").nth(1); // "What Silsila recorded"
let stepNo = 1;
async function nextStep() {
  stepNo += 1;
  await press(nextButton());
  await page.waitForFunction((n) => document.querySelectorAll("main ol[aria-label] button:not([disabled])").length >= n, stepNo, { timeout: 30000 })
    .catch(() => problems.push(`cascade step ${stepNo} did not arrive in 30 s`));
  await sleep(380);
}
async function language(to) {
  await press(page.locator("header nav button[lang]"));
  await page.waitForFunction((l) => document.documentElement.lang === l, to, { timeout: 15000 }).catch(note(`language ${to}`));
  // the cascade re-reads every step in the new language; wait until Next is usable again
  await page.waitForFunction(() => { const b = document.querySelector("main section")?.querySelectorAll("button")[2]; return b && !b.disabled; }, null, { timeout: 30000 }).catch(() => {});
  await sleep(500);
}

// =================================================== the film ===========================================
// 1. The claim
await gfx("hook");
await sleep(700);
let p = say("hook1");
await step(1);
await p;
p = say("hook2");
await step(2);
await p;
p = say("hook3");
await sleep(900);
await fx({ nolabel: 1 }); // the "RECORDED" label has been up for the opening; the closing card says it again
await step(3);
await p;
await quiet();

// 2. The gap, in numbers (criterion 1)
await gfx("problem");
await criterion(1);
p = say("prob1");
await step(1);
await p;
p = say("prob2");
await step(2);
await p;
p = say("prob3");
await step(3);
await p;

// 3. What Silsila is
await gfx("flow");
p = say("flow1");
for (const [k, wait] of [[1, 2500], [2, 2900], [3, 2400], [4, 2600], [5, 1500], [6, 0]]) {
  await page.evaluate((n) => window.film.flow(n), k);
  await sleep(wait);
}
await p;
await quiet();

// 4. The live product: one result travelling through a family (criterion 3)
await live("/cascade", () => page.locator("main svg").first().waitFor({ timeout: 45000 }));
await criterion(3);
await reveal(controls(), 78);
await sleep(900);
p = say("live1");
await sleep(3800);
await zoom(page.locator("main svg").first(), 1.22, 0.55);
await p;
p = say("live2");
await unzoom();
await sleep(700);
await nextStep(); // every relative's chance, and whom to tell first
await zoom(sees(), 1.3);
await p;
p = say("live3");
await unzoom();
await sleep(500);
await nextStep(); // Mariam gives permission
await sleep(1500);
await nextStep(); // anonymous invitation
await sleep(1800);
await nextStep(); // the counsellor approves
await zoom(recorded(), 1.25);
await p;
p = say("live4");
await unzoom();
await sleep(400);
await nextStep(); // Noura opens her link
await zoom(sees(), 1.26);
await sleep(2600);
await unzoom();
await sleep(500);
await language("ar"); // the same link in Arabic
await zoom(sees(), 1.26);
await p;
p = say("live5");
await unzoom();
await sleep(400);
await nextStep(); // comprehension check
await sleep(1500);
await nextStep(); // the options, in the source's words
await sleep(1900);
await nextStep(); // books counselling
await p;
p = say("live6");
await language("en");
await nextStep(); // a hard question goes to a person
await zoom(sees(), 1.26);
await sleep(3200);
await unzoom();
await sleep(400);
await nextStep(); // the result closes the case
await p;

// 5. Responsible AI (criterion 4)
await criterion(4);
p = say("rai1");
await nextStep(); // the output gate blocks AI-written advice
await zoom(recorded(), 1.32);
await p;
p = say("rai3");
await unzoom();
await sleep(400);
await nextStep(); // what the programme sees
await zoom(sees(), 1.2);
await p;
await unzoom();
await gfx("audit");
p = say("rai2");
await step(1);
await sleep(5200);
await step(2);
await p;
await quiet();

// 6. Technical depth: the Family Twin, then the checks (criterion 2)
await live("/twin", () => page.locator("canvas").waitFor({ timeout: 45000 }));
await criterion(2);
await reveal(page.locator(".tw-scene"), 84);
await sleep(2400);
p = say("tech1");
await sleep(4200);
try {
  const clan = await (await fetch(`${API}/api/twin`)).json();
  const base = await (await fetch(`${API}/api/twin/what-if`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ results: {} }) })).json();
  const onFile = new Set([clan.index, ...clan.parents]);
  const pick = clan.people.filter((x) => !x.deceased && !onFile.has(x.id) && base.p_carrier[x.id] > 0.3 && base.p_carrier[x.id] < 0.7).sort((a, b) => b.generation - a.generation)[0];
  // pick the person in the picture itself: their label sits just under them
  const box = await page.evaluate((name) => {
    const l = [...document.querySelectorAll(".tw-label")].find((x) => x.querySelector(".tw-name").textContent.trim().startsWith(name));
    const r = l.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top - 16 };
  }, pick.name);
  await page.evaluate(([x, y]) => window.fx.cursor(x, y), [box.x, box.y]);
  await sleep(760);
  await page.evaluate(() => window.fx.tap());
  mark("tap");
  await page.mouse.click(box.x, box.y);
  await sleep(900);
  await press(page.locator("main button").filter({ hasText: /^Record: carrier$/ }));
} catch (e) {
  note("twin record")(e);
}
await p;
await sleep(1200);
await quiet();
// The fictional counsellor's session for a later scene is set now, while the tab is on the site: it stays with
// the tab, so that scene can open the console directly.
const session = await (await fetch(`${API}/api/demo/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ persona: "counsellor" }) })).json();
await page.evaluate((s) => sessionStorage.setItem("silsila.session", JSON.stringify(s)), session).catch(note("counsellor session"));
await gfx("engine");
p = say("tech2");
await step(1);
await p;
p = say("tech3");
await step(2);
await p;

// 7. Why not a language model, and what models are for (criteria 2 and 4)
await gfx("models");
p = say("llm1");
await sleep(1500);
await step(1);
await p;
await quiet(); // the scene's conclusion comes up where the caption was
await step(2);
await sleep(3400);
const tabs = () => page.locator("main [role=tab]");
await live("/counsellor", () => tabs().nth(2).waitFor({ timeout: 30000 }));
await criterion(4);
await press(tabs().nth(2)); // Voice intake
await sleep(1800);
p = say("llm2");
await sleep(1200);
await scrollTo(250);
await sleep(3400);
await scrollTo(780);
await sleep(3200);
await scrollTo(1500);
await p;
p = say("llm3");
await scrollTo(0);
await fx({ guide: 1 });
await sleep(500);
const launcher = page.locator('button[aria-controls="guide-panel"]');
await press(launcher);
await sleep(900);
await press(page.locator("#guide-panel ul button").nth(3)); // "What is the chance for a sibling, an aunt or a cousin?"
await p;
await sleep(2600);
await press(launcher);
await fx({ guide: 0 });
await quiet();

// 8. Deployment and scale (criterion 5)
await criterion(5);
await press(tabs().nth(1)); // Cases
const card = page.locator("#fi-json").locator("xpath=ancestor::section[1]");
await card.waitFor({ timeout: 30000 }).catch(note("import card"));
await reveal(card, 90);
await sleep(600);
await zoom(card, 1.16, 0.5);
p = say("scale1");
await press(card.locator("button").nth(0)); // load the fictional sample
await sleep(1100);
await press(card.locator("button").nth(1)); // check the record: read
await sleep(1500);
await reveal(card.locator("[aria-live]"), 260);
await sleep(1500);
try { // the same record marked preliminary: refused, with the reason
  const ta = page.locator("#fi-json");
  await ta.fill((await ta.inputValue()).replace('"final"', '"preliminary"'));
  await reveal(card, 90);
  await press(card.locator("button").nth(1));
  await sleep(900);
  await reveal(card.locator("[role=alert]"), 420);
  await flash(card.locator("[role=alert]"), 2600);
} catch (e) {
  note("import refusal")(e);
}
await p;
await sleep(2200);
await quiet();
await gfx("scale");
p = say("scale2");
await step(1);
await sleep(6200);
await step(2);
await p;

// 9. Path to pilot (criterion 6)
await gfx("pilot");
await criterion(6);
p = say("pilot1");
await sleep(4200);
await step(1);
await p;
p = say("pilot2");
await step(2);
await p;

// 10. Six criteria, the limits, and the close
await gfx("score");
await criterion(0);
p = say("score1");
await step(1);
await p;
p = say("score2");
await step(2);
await p;
await gfx("close");
await quiet();
mark("close");
await step(1);
await sleep(700);
p = say("close1");
await sleep(1700);
await step(2);
await p;
await fx({ progress: 100 });
await sleep(3200);

const total = (Date.now() - t0) / 1000;
const video = page.video();
await context.close();
await browser.close();
const raw = path.join(HERE, "out", "raw.webm");
fs.renameSync(await video.path(), raw);
fs.writeFileSync(path.join(HERE, "out", "timeline.json"), JSON.stringify({ web: WEB, recorded: new Date().toISOString(), seconds: total, lines: timeline, events, problems }, null, 1) + "\n");
console.log(`recorded ${total.toFixed(1)} s to ${raw}`);
if (problems.length) console.log(`problems (${problems.length}):\n  ` + problems.join("\n  "));
