// Records the Silsila film: a scripted walk through the live site in a real browser, with the narration's
// captions and an honesty label on screen. Run make_voice.py first (it gives each line's length), then:
//
//   node record.mjs --lang en            # or --lang ar
//   node record.mjs --lang en --web http://localhost:3000 --api http://localhost:8000
//
// Output: out/raw-<lang>.webm (silent video) and out/timeline-<lang>.json (when each line starts).
// build.sh then lays the voice clips onto the video at those times.
//
// Everything on screen is the real application with its fictional demo families. Nothing is staged except
// the order of clicks. The label "RECORDED · fictional families · synthetic voice (Azure)" stays on screen.

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const LANG = arg("lang", "en");
const WEB = arg("web", "https://silsila-web.lemonisland-568f9acd.uaenorth.azurecontainerapps.io").replace(/\/$/, "");
const API = arg("api", "https://silsila-api.lemonisland-568f9acd.uaenorth.azurecontainerapps.io").replace(/\/$/, "");
const W = 1920, H = 1080;

const narration = JSON.parse(fs.readFileSync(path.join(HERE, "narration.json"), "utf8"));
const voice = JSON.parse(fs.readFileSync(path.join(HERE, "out", "voice", `${LANG}.json`), "utf8"));
const lineOf = (scene, n) => voice.find((v) => v.scene === scene && v.n === n);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const GAP = 280; // silence between lines, ms

// Playwright's own headless Chromium: it captures exactly the page (installed Chrome clips the bottom of the
// frame by the height of its toolbar). WebGL for the Family Twin runs on the software renderer.
const browser = await chromium.launch({ headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const context = await browser.newContext({
  viewport: { width: W, height: H },
  recordVideo: { dir: path.join(HERE, "out", "raw"), size: { width: W, height: H } },
  locale: LANG === "ar" ? "ar-AE" : "en-GB",
  colorScheme: "light",
});

// Language, theme, the caption bar and the honesty label, on every page.
await context.addInitScript(
  ({ lang, label }) => {
    try {
      localStorage.setItem("silsila.lang", lang);
      localStorage.setItem("silsila.theme", "light");
    } catch {}
    const mount = () => {
      if (document.getElementById("film-bar")) return;
      const style = document.createElement("style");
      style.textContent = `
        #film-bar{position:fixed;inset-inline:0;bottom:0;z-index:99999;min-height:104px;display:flex;align-items:center;justify-content:center;
          padding:14px 64px;background:rgba(13,36,35,.95);color:#fff;font:500 30px/1.35 var(--font-sans),system-ui,sans-serif;text-align:center}
        #film-bar span{max-width:1500px;text-wrap:balance}
        #film-label{position:fixed;top:78px;inset-inline-end:20px;z-index:99999;padding:6px 14px;border-radius:999px;background:#12302f;color:#fff;
          font:600 15px/1.3 var(--font-sans),system-ui,sans-serif;letter-spacing:.02em;box-shadow:0 2px 10px rgba(0,0,0,.18)}
        body{padding-bottom:104px}
        [class*="bottom-4"][class*="end-4"]{bottom:124px!important}
        nextjs-portal{display:none!important}
        .film-flash{outline:4px solid #e3b56a!important;outline-offset:3px;border-radius:8px;transition:outline-color .2s}`;
      document.head.appendChild(style);
      const bar = document.createElement("div");
      bar.id = "film-bar";
      bar.setAttribute("aria-hidden", "true");
      bar.dir = "auto";
      bar.appendChild(document.createElement("span")).textContent = sessionStorage.getItem("film-caption") || "";
      const tag = document.createElement("div");
      tag.id = "film-label";
      tag.setAttribute("aria-hidden", "true");
      tag.textContent = label;
      document.body.append(bar, tag);
    };
    window.__caption = (text) => {
      try { sessionStorage.setItem("film-caption", text); } catch {}
      const el = document.querySelector("#film-bar span");
      if (el) el.textContent = text;
    };
    if (document.body) mount();
    else document.addEventListener("DOMContentLoaded", mount);
    // the app replaces <body> content while it loads; put the bar back if it goes
    document.addEventListener("DOMContentLoaded", () => new MutationObserver(mount).observe(document.body, { childList: true }));
  },
  { lang: LANG, label: narration.label[LANG] },
);

const page = await context.newPage();
const t0 = Date.now();
const timeline = [];
const problems = [];
page.on("pageerror", (e) => problems.push(`page error: ${e.message}`));
page.on("console", (m) => m.type() === "error" && !/422|Failed to load resource/.test(m.text()) && problems.push(`console: ${m.text().slice(0, 200)}`));

const caption = (text) => page.evaluate((t) => window.__caption && window.__caption(t), text).catch(() => {});

/** Start speaking a line now; resolves when the line (plus a short gap) is over. */
function say(scene, n) {
  const line = lineOf(scene, n);
  if (!line) throw new Error(`no voice for ${scene} ${n}`);
  timeline.push({ scene, n, file: line.file, at: (Date.now() - t0) / 1000, seconds: line.seconds });
  void caption(line.caption);
  return sleep(line.seconds * 1000 + GAP);
}
const quiet = () => caption("");

const go = async (p) => {
  await page.goto(WEB + p, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle").catch(() => {});
};
const scrollTo = (y) => page.evaluate((top) => window.scrollTo({ top, behavior: "smooth" }), y);
/** Smoothly bring an element near the top of the window (below the sticky header). */
const reveal = async (locator, offset = 96) => {
  await locator.first().evaluate((el, off) => {
    const top = el.getBoundingClientRect().top + window.scrollY - off;
    window.scrollTo({ top, behavior: "smooth" });
  }, offset).catch((e) => problems.push(`reveal: ${e.message.slice(0, 120)}`));
};
const flash = async (locator, ms = 1400) => {
  const el = locator.first();
  await el.evaluate((n) => n.classList.add("film-flash")).catch(() => {});
  setTimeout(() => el.evaluate((n) => n.classList.remove("film-flash")).catch(() => {}), ms);
};
const press = async (locator) => {
  await flash(locator, 700);
  await sleep(250);
  await locator.first().click({ timeout: 15000 }).catch((e) => problems.push(`click: ${e.message.slice(0, 160)}`));
};

// ---- Watch a cascade ---------------------------------------------------------------------------------
const controls = () => page.locator("main section").first();
const nextButton = () => controls().locator("button").nth(2);
let step = 1;
async function nextStep() {
  step += 1;
  await press(nextButton());
  await page.waitForFunction((n) => {
    const done = document.querySelectorAll("main ol[aria-label] button:not([disabled])").length;
    return done >= n;
  }, step, { timeout: 30000 }).catch(() => problems.push(`cascade step ${step} did not arrive in 30 s`));
  await sleep(350);
}

// ---- scenes -------------------------------------------------------------------------------------------
await go("/");
await page.locator("h1").waitFor();
await sleep(1200);

// 1. The claim
await say("hook", 0);
await say("hook", 1);
let p = say("hook", 2);
await sleep(1500);
await reveal(page.locator("#only-h"), 110);
await p;
p = say("hook", 3);
await sleep(2500);
await scrollTo(0);
await p;
await quiet();

// 2. A newborn's result; every relative's chance
await go("/cascade");
await page.locator("main svg").first().waitFor({ timeout: 45000 });
await reveal(controls(), 84);
await sleep(900);
await say("risk", 0);
await say("risk", 1);
p = say("risk", 2);
await nextStep();
await p;
await say("risk", 3);

// 3. The family decides; the counsellor approves
p = say("consent", 0);
await nextStep();
await p;
p = say("consent", 1);
await nextStep();
await p;
p = say("consent", 2);
await nextStep();
await p;

// 4. The relative's private link
p = say("relative", 0);
await nextStep();
await p;
await say("relative", 1);
p = say("relative", 2);
await nextStep(); // comprehension check
await sleep(1800);
await nextStep(); // the options, in the source's words
await sleep(2200);
await nextStep(); // books counselling
await p;

// 5. Safety, closure, measures
p = say("safety", 0);
await nextStep();
await p;
p = say("safety", 1);
await nextStep();
await p;
p = say("safety", 2);
await nextStep();
await p;
p = say("safety", 3);
await nextStep();
await sleep(1200);
await reveal(page.locator("main .grid.content-start").first(), 150);
await p;
await sleep(600);
await quiet();

// 6. Family Twin
await go("/twin");
await page.locator("canvas").waitFor({ timeout: 45000 });
await sleep(2500);
p = say("twin", 0);
await sleep(600);
await p;
p = say("twin", 1);
try {
  const clan = await (await fetch(`${API}/api/twin`)).json();
  const base = await (await fetch(`${API}/api/twin/what-if`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ results: {} }) })).json();
  const onFile = new Set([clan.index, ...clan.parents]);
  const pick = clan.people
    .filter((x) => !x.deceased && !onFile.has(x.id) && base.p_carrier[x.id] > 0.3 && base.p_carrier[x.id] < 0.7)
    .sort((a, b) => b.generation - a.generation)[0];
  const name = LANG === "ar" && pick.name_ar ? pick.name_ar : pick.name;
  await press(page.locator("main button").filter({ hasText: /Show as a table|اعرض كجدول|جدول/ }));
  await sleep(500);
  await page.locator("main table button").filter({ hasText: new RegExp(`^${name}`) }).first().click({ timeout: 8000 });
  await sleep(400);
  await press(page.locator("main button").filter({ hasText: /Hide the table|أخفِ الجدول/ }));
  await scrollTo(0);
  await sleep(700);
  await press(page.locator("main button").filter({ hasText: /Record: carrier|سجّل: حامل/ }));
} catch (e) {
  problems.push(`twin record: ${String(e.message || e).slice(0, 160)}`);
}
await p;
await sleep(800);
p = say("twin", 2);
await press(page.locator("main button").filter({ hasText: /Play: Silsila|شغّل: ترتيب سلسلة/ }));
await sleep(1500);
await reveal(page.locator("main button").filter({ hasText: /Play: Silsila|شغّل: ترتيب سلسلة/ }), 640);
await p;
await sleep(3500);
await quiet();

// 7. Voice intake (counsellor console; demo sign-in for a fictional persona, no password)
const session = await (await fetch(`${API}/api/demo/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ persona: "counsellor" }) })).json();
await page.evaluate((s) => sessionStorage.setItem("silsila.session", JSON.stringify(s)), session);
await go("/counsellor");
const tabs = () => page.locator("main [role=tab]");
await tabs().nth(2).waitFor({ timeout: 30000 });
await press(tabs().nth(2));
await sleep(2000);
p = say("voice", 0);
await sleep(1500);
await scrollTo(260);
await sleep(3600);
await scrollTo(760);
await p;
p = say("voice", 1);
await sleep(500);
await scrollTo(1250);
await sleep(1700);
await scrollTo(1750);
await p;
await quiet();

// 8. Why not ask a chatbot
await go("/evidence");
const jaisRow = page.locator("main tr").filter({ hasText: "Jais 3 7B" }).first();
await jaisRow.waitFor({ timeout: 45000 });
await reveal(jaisRow, 420);
await sleep(900);
await say("contrast", 0);
p = say("contrast", 1);
await flash(jaisRow, 5000);
await p;
// "no model writes to a family": the guide answers about the tool with fixed text and a live check of the gate
p = say("contrast", 2);
const launcher = page.locator('button[aria-controls="guide-panel"]');
await press(launcher);
await sleep(1100);
await press(page.locator("#guide-panel ul button").nth(1)); // "Does AI write what families read?"
await p;
await sleep(2600);
await press(launcher);
await quiet();

// 9. FHIR import and the outcome measures
await go("/counsellor");
await tabs().nth(1).waitFor({ timeout: 30000 });
await press(tabs().nth(1));
const card = page.locator("#fi-json").locator("xpath=ancestor::section[1]");
await card.waitFor({ timeout: 30000 });
await reveal(card, 96);
await sleep(600);
p = say("import", 0);
await press(card.locator("button").nth(0)); // load the fictional sample
await sleep(1300);
await press(card.locator("button").nth(1)); // check the record
await sleep(1200);
await reveal(card.locator("[aria-live]"), 300);
await sleep(1900);
await scrollTo(0);
await sleep(400);
await press(tabs().nth(3)); // Outcomes
await p;
await sleep(1400);
await quiet();

// 10. Evidence and close
await go("/evidence");
await page.locator("#ev-b1_engine").waitFor({ timeout: 45000 });
await reveal(page.locator("#ev-b1_engine"), 96);
await sleep(700);
await say("close", 0);
p = say("close", 1);
await reveal(page.locator("main h2").filter({ hasText: /Privacy|الخصوصية/ }), 96);
await p;
p = say("close", 2);
await sleep(300);
await go("/");
await p;
await say("close", 3);
await sleep(1500);

const total = (Date.now() - t0) / 1000;
const video = page.video();
await context.close();
await browser.close();
const raw = path.join(HERE, "out", `raw-${LANG}.webm`);
fs.renameSync(await video.path(), raw);
fs.writeFileSync(path.join(HERE, "out", `timeline-${LANG}.json`), JSON.stringify({ lang: LANG, web: WEB, recorded: new Date().toISOString(), seconds: total, lines: timeline, problems }, null, 1) + "\n");
console.log(`recorded ${total.toFixed(1)} s to ${raw}`);
if (problems.length) console.log(`problems (${problems.length}):\n  ` + problems.join("\n  "));
