// Renders the app icon SVG to the PNG sizes the PWA manifest needs.
// Run: node scripts/make-icons.mjs   (uses sharp, installed with Next.js)
import sharp from "sharp";
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const mark = (scale) => `
  <g transform="translate(256 256) scale(${scale}) translate(-120 -50)" fill="none" stroke="#f7f3ec" stroke-width="10">
    <rect x="10" y="20" width="60" height="60" rx="6"/>
    <circle cx="120" cy="50" r="32"/>
    <rect x="170" y="20" width="60" height="60" rx="6"/>
    <path d="M70 50h18M152 50h18"/>
    <circle cx="120" cy="50" r="10" fill="#d3b07a" stroke="none"/>
  </g>`;

const svg = (scale, rounded) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="${rounded ? 112 : 0}" fill="#0e5a57"/>
  ${mark(scale)}
</svg>`;

const out = new URL("../public/icons/", import.meta.url);
writeFileSync(new URL("icon.svg", out), svg(1.5, true));
const jobs = [
  ["icon-192.png", 192, svg(1.5, true)],
  ["icon-512.png", 512, svg(1.5, true)],
  ["icon-maskable-512.png", 512, svg(1.1, false)],
  ["apple-touch-icon.png", 180, svg(1.4, false)],
];
for (const [name, size, s] of jobs) {
  await sharp(Buffer.from(s)).resize(size, size).png().toFile(fileURLToPath(new URL(name, out)));
}
console.log("icons written");
