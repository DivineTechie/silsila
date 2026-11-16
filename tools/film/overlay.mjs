// The overlay drawn on top of every page of the film (the graphics scenes and the live site alike): the caption
// of the line being spoken, the judging criterion, the "RECORDED" label (over the opening only), a progress line, a pointer that shows
// each click, zooms, and a dip to dark between pages. It runs inside the page, before the page's own scripts.
//
// State (caption, criterion, curtain, progress) travels between pages in window.name, which survives
// navigation, so a new page comes up already covered and already captioned.
export const overlay = ({ label }) => {
  const read = () => { try { return JSON.parse(window.name || "{}"); } catch { return {}; } };
  const save = (p) => { window.name = JSON.stringify({ ...read(), ...p }); };
  try {
    localStorage.setItem("silsila.theme", "light");
    if (!localStorage.getItem("silsila.lang")) localStorage.setItem("silsila.lang", "en");
  } catch {}
  const CSS = `
    html::before{content:"";position:fixed;inset:0;z-index:2147483000;pointer-events:none;opacity:0;transition:opacity .45s ease;
      background:radial-gradient(1400px 900px at 70% 20%,#123936 0%,#0d2423 45%,#071719 100%)}
    html[data-fx-curtain="1"]::before{opacity:1}
    html{overflow-x:hidden}
    #fx-cap{position:fixed;left:50%;bottom:54px;transform:translateX(-50%);z-index:2147483100;max-width:1700px;width:max-content;box-sizing:border-box;
      padding:16px 36px;border-radius:20px;background:rgba(7,23,25,.92);color:#fff;font:500 30px/1.32 "IBM Plex Sans",var(--font-sans,system-ui),system-ui,sans-serif;
      text-align:center;text-wrap:balance;box-shadow:0 14px 44px rgba(0,0,0,.28);transition:opacity .25s ease;pointer-events:none}
    #fx-cap:empty{opacity:0}
    #fx-crit{position:fixed;left:50%;top:10px;transform:translateX(-50%);z-index:2147483100;display:flex;align-items:center;gap:12px;padding:7px 22px 7px 8px;
      border-radius:999px;background:#0e5a57;color:#fff;font:600 21px/1.2 "IBM Plex Sans",var(--font-sans,system-ui),system-ui,sans-serif;white-space:nowrap;
      box-shadow:0 6px 22px rgba(0,0,0,.25);transition:opacity .4s ease, transform .4s ease;pointer-events:none}
    #fx-crit b{display:grid;place-items:center;width:34px;height:34px;border-radius:50%;background:#f2c14e;color:#1b1503;font-weight:700}
    #fx-crit small{font-size:14px;letter-spacing:.14em;text-transform:uppercase;opacity:.75;font-weight:600}
    #fx-crit[data-off="1"]{opacity:0;transform:translate(-50%,-14px)}
    html[data-fx-live="1"] #fx-crit{left:43%}
    #fx-label{position:fixed;left:26px;bottom:18px;z-index:2147483100;font:600 15px/1 "IBM Plex Sans",var(--font-sans,system-ui),system-ui,sans-serif;letter-spacing:.04em;
      color:#fff;background:rgba(7,23,25,.78);padding:7px 13px;border-radius:999px;pointer-events:none;transition:opacity 1.2s ease}
    #fx-label[data-off="1"]{opacity:0}
    #fx-bar{position:fixed;left:0;bottom:0;height:6px;z-index:2147483100;background:linear-gradient(90deg,#5fb3ab,#f2c14e);width:0;transition:width .6s linear;pointer-events:none}
    #fx-cur{position:fixed;left:0;top:0;z-index:2147483200;width:30px;height:30px;margin:-15px 0 0 -15px;border-radius:50%;background:rgba(242,193,78,.95);
      border:3px solid #fff;box-shadow:0 3px 14px rgba(0,0,0,.4);transition:transform .7s cubic-bezier(.3,.7,.2,1),opacity .3s;opacity:0;pointer-events:none}
    #fx-cur.tap{animation:fxtap .45s ease-out}
    @keyframes fxtap{0%{box-shadow:0 0 0 0 rgba(242,193,78,.8)}100%{box-shadow:0 0 0 34px rgba(242,193,78,0)}}
    main{transition:transform 1.15s cubic-bezier(.3,.7,.2,1);will-change:transform}
    nextjs-portal{display:none!important}
    html:not([data-fx-guide="1"]) [class*="bottom-4"][class*="end-4"]{display:none!important}
    html[data-fx-guide="1"] [class*="bottom-4"][class*="end-4"]{bottom:164px!important;transform:scale(1.22);transform-origin:bottom right}
    .fx-flash{outline:5px solid #f2c14e!important;outline-offset:4px;border-radius:10px}`;
  // A caption balanced over two lines is narrower than the box the browser gives it: shrink the box to the text.
  const fit = (cap) => {
    cap.style.width = "";
    if (!cap.textContent) return;
    const r = document.createRange();
    r.selectNodeContents(cap);
    let w = 0;
    for (const b of r.getClientRects()) w = Math.max(w, b.width);
    if (w) cap.style.width = `${Math.ceil(w) + 78}px`; // 36 px of padding each side, and a little slack so the lines do not re-break
  };
  const apply = () => {
    const s = read(), d = document.documentElement;
    if (!d) return;
    d.setAttribute("data-fx-curtain", s.curtain ? "1" : "0");
    d.setAttribute("data-fx-guide", s.guide ? "1" : "0");
    const cap = document.getElementById("fx-cap"), crit = document.getElementById("fx-crit"), bar = document.getElementById("fx-bar");
    if (cap && cap.textContent !== (s.caption || "")) { cap.textContent = s.caption || ""; fit(cap); }
    if (crit) {
      crit.dataset.off = s.crit ? "0" : "1";
      if (s.crit) crit.innerHTML = `<b>${s.crit}</b><span><small>Criterion ${s.crit}</small><br>${s.critName}</span>`;
    }
    const lab = document.getElementById("fx-label");
    if (lab) lab.dataset.off = s.nolabel ? "1" : "0"; // the label is shown over the opening, then again in words on the closing card
    if (bar) bar.style.width = `${Math.min(100, s.progress || 0)}%`;
  };
  const mount = () => {
    const d = document.documentElement;
    if (!d) return;
    if (!document.getElementById("fx-style")) {
      const st = document.createElement("style");
      st.id = "fx-style";
      st.textContent = CSS;
      (document.head || d).appendChild(st);
    }
    d.setAttribute("data-fx-curtain", read().curtain ? "1" : "0");
    d.setAttribute("data-fx-live", location.protocol === "file:" ? "0" : "1"); // on the site the criterion sits clear of the header's links
    if (document.body && !document.getElementById("fx-cap")) {
      for (const [id, text] of [["fx-cap", ""], ["fx-crit", ""], ["fx-label", label], ["fx-bar", ""], ["fx-cur", ""]]) {
        const el = document.createElement("div");
        el.id = id;
        el.setAttribute("aria-hidden", "true");
        if (id === "fx-cap") el.dir = "auto";
        el.textContent = text;
        document.body.appendChild(el);
      }
      apply();
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { const c = document.getElementById("fx-cap"); if (c) fit(c); });
    }
  };
  new MutationObserver(mount).observe(document, { childList: true, subtree: true }); // from the first node on, and again if the app re-renders <body>
  document.addEventListener("DOMContentLoaded", mount);
  window.fx = {
    set(p) { save(p); mount(); apply(); },
    cursor(x, y, show = true) {
      const c = document.getElementById("fx-cur");
      if (!c) return;
      c.style.opacity = show ? "1" : "0";
      c.style.transform = `translate(${x}px, ${y}px)`;
    },
    tap() {
      const c = document.getElementById("fx-cur");
      if (!c) return;
      c.classList.remove("tap");
      void c.offsetWidth;
      c.classList.add("tap");
    },
    zoom(cx, cy, scale, pull = 0.7) { // enlarge <main> around a point and pull that point towards the middle of the frame
      const m = document.querySelector("main");
      if (!m) return;
      const r = m.getBoundingClientRect();
      m.style.transformOrigin = `${cx - r.left}px ${cy - r.top}px`;
      m.style.transform = `translate(${(innerWidth / 2 - cx) * pull}px, ${(innerHeight * 0.46 - cy) * pull}px) scale(${scale})`;
    },
    unzoom() { const m = document.querySelector("main"); if (m) m.style.transform = "none"; },
  };
};
