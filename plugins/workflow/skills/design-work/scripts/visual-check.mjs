#!/usr/bin/env node
// visual-check.mjs — the end of every design round: screenshot a page at a desktop and a phone width, and lint the
// layout the way a reviewer's eye would, so a broken page never reaches the user as "done".
//
//   node visual-check.mjs <url> [<url> …] [options]
//
//   --widths 1280,390        viewport widths (default 1280,390); the height follows the width (800 / 844)
//   --out <dir>              where the PNGs and report.json go (default ./visual-check)
//   --label <name>           a prefix for the files, e.g. before / after (default: none)
//   --selector <css>         the surface you changed: scrolled into view before the shot, and shot alone as well
//
// The lint covers what is drawn on the screen being shot (each box cut to the ancestors that clip it), the same thing
// the screenshot shows. To check something further down an app that scrolls inside a panel, name it with --selector.
//   --full                   full-page screenshots instead of the first screen
//   --wait <ms>              extra settle time after load (default 600)
//   --wait-for <css>         wait for this selector before shooting
//   --storage-state <file>   a Playwright storage state (cookies, localStorage) for an authenticated page
//   --header "K: V"          an extra request header; repeatable
//   --color-scheme dark      emulate prefers-color-scheme (light | dark)
//   --no-lint                screenshots only
//
// Exit 0 = shot, no layout issue found · 1 = shot, issues found (listed) · 2 = could not run (no Playwright, bad
// arguments, the page did not load). Issues are CANDIDATES for the eye, not verdicts: read the screenshots anyway.
//
// Playwright comes from the repo being worked on (`playwright` or `@playwright/test`, resolved from the current
// directory), or from PLAYWRIGHT_MODULE (a path to either package). Nothing is installed by this script.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

export const DEFAULT_WIDTHS = [1280, 390];
export const PHONE_MAX = 600;
export const MIN_TARGET = 24; // WCAG 2.2 SC 2.5.8 (AA); 44 is the comfortable size

export function parseArgs(argv) {
  const o = { urls: [], widths: DEFAULT_WIDTHS, out: 'visual-check', label: '', selector: null, full: false, wait: 600,
    waitFor: null, storageState: null, headers: {}, colorScheme: null, lint: true };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i], next = () => { if (i + 1 >= argv.length) throw new Error(`${a} needs a value`); return argv[++i]; };
    if (a === '--widths') o.widths = next().split(',').map(Number).filter(n => n > 0);
    else if (a === '--out') o.out = next();
    else if (a === '--label') o.label = next();
    else if (a === '--selector') o.selector = next();
    else if (a === '--full') o.full = true;
    else if (a === '--wait') o.wait = Number(next());
    else if (a === '--wait-for') o.waitFor = next();
    else if (a === '--storage-state') o.storageState = next();
    else if (a === '--header') { const [k, ...v] = next().split(':'); o.headers[k.trim()] = v.join(':').trim(); }
    else if (a === '--color-scheme') o.colorScheme = next();
    else if (a === '--no-lint') o.lint = false;
    else if (a.startsWith('--')) throw new Error(`unknown option ${a}`);
    else o.urls.push(a);
  }
  if (!o.urls.length) throw new Error('give at least one URL');
  if (!o.widths.length) throw new Error('--widths holds no width');
  return o;
}

// The file-name stem of a URL's screenshots: readable (a local page by its folder and file, a served one by host and
// path, then the query with long values such as tokens left out) and unique (a short hash of the whole URL), so two
// pages differing only in a query value never overwrite each other's shots.
export function shotStem(url) {
  let u = null;
  try { u = new URL(url); } catch { /* not a URL: use it as given */ }
  const clean = s => s.replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '');
  let place = url;
  if (u && u.protocol === 'file:') place = u.pathname.split('/').filter(Boolean).slice(-2).join('-');
  else if (u) place = u.host + u.pathname;
  const query = u ? [...u.searchParams].map(([k, v]) => (v && v.length <= 12 ? `${k}-${v}` : k)).join('-') : '';
  let h = 0x811c9dc5; // FNV-1a, then an avalanche, so URLs one character apart get unrelated hashes
  for (let i = 0; i < url.length; i++) h = Math.imul(h ^ url.charCodeAt(i), 0x01000193);
  h = Math.imul(h ^ (h >>> 16), 0x85ebca6b); h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35); h = (h ^ (h >>> 16)) >>> 0;
  return `${clean(place).slice(-40)}${query ? '-' + clean(query).slice(0, 30) : ''}-${h.toString(36).padStart(7, '0').slice(-6)}`.replace(/^-/, '');
}

// ---- the lint: pure functions over what the page reported, so they run under `node --test` ----

const parseColor = c => {
  const m = /rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:[ ,/]+([\d.]+%?))?\s*\)/.exec(c || '');
  if (!m) return null;
  const a = m[4] === undefined ? 1 : m[4].endsWith('%') ? parseFloat(m[4]) / 100 : parseFloat(m[4]);
  return { r: +m[1], g: +m[2], b: +m[3], a };
};
const lum = ({ r, g, b }) => {
  const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
export function contrast(fg, bg) {
  const F = parseColor(fg), B = parseColor(bg);
  if (!F || !B) return null;
  const mix = { r: F.r * F.a + B.r * (1 - F.a), g: F.g * F.a + B.g * (1 - F.a), b: F.b * F.a + B.b * (1 - F.a) };
  const [hi, lo] = [lum(mix), lum(B)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
const overlap = (a, b) => Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
const inside = (a, b) => a.x >= b.x - 1 && a.y >= b.y - 1 && a.x + a.w <= b.x + b.w + 1 && a.y + a.h <= b.y + b.h + 1;
const floats = it => it.position === 'fixed' || it.position === 'sticky';

// snap: { vw, sw, items: [{ id, sel, x, y, w, h, interactive, inlineLink, ownText, text, clipsX, clipsY, ellipsis,
//          color, bg, fontSize, fontWeight, position, name, img, inScroller }] }
export function lint(snap, width) {
  const issues = [], add = (kind, sel, detail) => issues.push({ kind, sel, detail });
  const items = snap.items || [];
  if (snap.sw > snap.vw + 1) {
    const culprits = items.filter(it => !it.inScroller && !floats(it) && it.x + it.w > snap.vw + 1).sort((a, b) => (b.x + b.w) - (a.x + a.w));
    add('horizontal-overflow', culprits[0] ? culprits[0].sel : 'document', `the page scrolls sideways: ${snap.sw}px of content in a ${snap.vw}px viewport` + (culprits.length ? `; widest: ${culprits.slice(0, 3).map(c => `${c.sel} ends at ${Math.round(c.x + c.w)}px`).join(', ')}` : ''));
  }
  for (const it of items) {
    if ((it.clipsX || it.clipsY) && it.ownText && !it.ellipsis) add('clipped-text', it.sel, `text is cut off${it.text ? `: "${it.text}"` : ''}`);
  }
  const texts = items.filter(it => it.ownText && !floats(it));
  for (let i = 0; i < texts.length; i++) for (let j = i + 1; j < texts.length; j++) {
    const a = texts[i], b = texts[j];
    if (inside(a, b) || inside(b, a)) continue;
    const o = overlap(a, b);
    if (o > 4 && o > 0.15 * Math.min(a.w * a.h, b.w * b.h)) add('overlapping-text', a.sel, `"${a.text}" overlaps ${b.sel} "${b.text}"`);
  }
  const controls = items.filter(it => it.interactive && !floats(it));
  for (let i = 0; i < controls.length; i++) for (let j = i + 1; j < controls.length; j++) {
    const a = controls[i], b = controls[j];
    if (inside(a, b) || inside(b, a)) continue;
    if (overlap(a, b) > 16) add('overlapping-controls', a.sel, `overlaps ${b.sel}: a tap may hit the wrong one`);
  }
  if (width <= PHONE_MAX) for (const it of items) {
    if (it.interactive && !it.inlineLink && (it.w < MIN_TARGET || it.h < MIN_TARGET)) add('small-target', it.sel, `${Math.round(it.w)}×${Math.round(it.h)}px on a phone (at least ${MIN_TARGET}, 44 is comfortable)${it.name ? `: "${it.name}"` : ''}`);
  }
  // One finding per colour pair: a muted grey used on fifty labels is one decision, and fifty lines bury the rest.
  const faint = new Map();
  for (const it of items) {
    if (!it.ownText || !it.color || !it.bg) continue;
    const r = contrast(it.color, it.bg);
    const large = it.fontSize >= 24 || (it.fontSize >= 18.66 && it.fontWeight >= 700), need = large ? 3 : 4.5;
    if (r === null || r >= need) continue;
    const k = `${it.color}|${it.bg}|${need}`, g = faint.get(k) || { r, need, sel: it.sel, texts: [] };
    g.texts.push(it.text); faint.set(k, g);
  }
  for (const [k, g] of faint) {
    const n = g.texts.length, eg = [...new Set(g.texts)].slice(0, 3).map(t => `"${t}"`).join(', ');
    add('low-contrast', g.sel, `${g.r.toFixed(2)}:1 (needs ${g.need}:1), ${k.split('|')[0]} on ${k.split('|')[1]}, ${n} text${n > 1 ? 's' : ''}: ${eg}`);
  }
  for (const it of items) {
    if (it.interactive && !it.name) add('unnamed-control', it.sel, 'a control with no text, label or title: a screen reader says nothing');
    if (it.img && it.img.alt === null) add('image-without-alt', it.sel, 'an image with no alt attribute');
  }
  const seen = new Set();
  return issues.filter(x => { const k = `${x.kind}|${x.sel}|${x.detail}`; if (seen.has(k)) return false; seen.add(k); return true; });
}

// ---- in the page: what the lint reads (runs in the browser, so it uses nothing from this module) ----
function collect() {
  const de = document.documentElement, out = { vw: de.clientWidth, sw: de.scrollWidth, items: [] };
  const CONTROL = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=checkbox],[role=switch],[role=menuitem],[tabindex]:not([tabindex="-1"])';
  const sel = el => {
    let s = el.tagName.toLowerCase();
    if (el.id) return s + '#' + el.id;
    const t = el.getAttribute('data-testid'); if (t) return `${s}[data-testid="${t}"]`;
    const c = (typeof el.className === 'string' ? el.className : '').trim().split(/\s+/).filter(Boolean)[0];
    if (c) s += '.' + c;
    const p = el.parentElement; if (p) { const same = [...p.children].filter(x => x.tagName === el.tagName); if (same.length > 1) s += `:nth-of-type(${same.indexOf(el) + 1})`; }
    return s;
  };
  const transparent = b => !b || b === 'transparent' || /rgba\([^)]*,\s*0\)$/.test(b);
  let n = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (n >= 5000) break;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || Number(cs.opacity) === 0) continue;
    const b = el.getBoundingClientRect();
    if (b.width < 1 || b.height < 1) continue;
    const ownText = [...el.childNodes].some(c => c.nodeType === 3 && c.textContent.trim());
    const interactive = el.matches(CONTROL) && !el.disabled;
    // What is actually drawn: the box cut to every ancestor that clips. A label truncated by its parent's ellipsis
    // extends under its neighbour in layout, and is not drawn over it.
    let inScroller = false, l = b.left, t = b.top, rr = b.right, bb = b.bottom;
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const ps = getComputedStyle(p);
      const cx = /(auto|scroll|hidden|clip)/.test(ps.overflowX), cy = /(auto|scroll|hidden|clip)/.test(ps.overflowY);
      if (cx && p.scrollWidth > p.clientWidth + 1) inScroller = true;
      if (cx || cy) { const q = p.getBoundingClientRect(); if (cx) { l = Math.max(l, q.left); rr = Math.min(rr, q.right); } if (cy) { t = Math.max(t, q.top); bb = Math.min(bb, q.bottom); } }
    }
    if (rr - l < 1 || bb - t < 1) continue;
    const r = { left: l, top: t, width: rr - l, height: bb - t };
    let bg = null;
    if (ownText) for (let p = el; p; p = p.parentElement) { const b = getComputedStyle(p).backgroundColor; if (!transparent(b)) { bg = b; break; } }
    if (ownText && !bg) bg = 'rgb(255, 255, 255)';
    const label = el.getAttribute('aria-label') || el.getAttribute('title') || (el.labels && el.labels[0] && el.labels[0].textContent) || el.textContent || el.getAttribute('placeholder') || el.getAttribute('value') || (el.querySelector && el.querySelector('img[alt]') && el.querySelector('img[alt]').getAttribute('alt')) || '';
    out.items.push({
      id: n++, sel: sel(el), x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height,
      interactive, inlineLink: el.tagName === 'A' && !!el.parentElement && [...el.parentElement.childNodes].some(c => c.nodeType === 3 && c.textContent.trim()),
      ownText, text: ownText ? el.textContent.trim().replace(/\s+/g, ' ').slice(0, 60) : '',
      clipsX: /(hidden|clip)/.test(cs.overflowX) && el.scrollWidth > el.clientWidth + 1,
      clipsY: /(hidden|clip)/.test(cs.overflowY) && el.scrollHeight > el.clientHeight + 1 && !/-webkit-box/.test(cs.display),
      ellipsis: cs.textOverflow === 'ellipsis' || Number(cs.webkitLineClamp) > 0,
      color: ownText ? cs.color : null, bg, fontSize: parseFloat(cs.fontSize), fontWeight: Number(cs.fontWeight) || 400,
      position: cs.position, name: interactive ? label.trim().replace(/\s+/g, ' ').slice(0, 40) : null,
      img: el.tagName === 'IMG' ? { alt: el.getAttribute('alt') } : null, inScroller,
    });
  }
  return out;
}

async function loadPlaywright() {
  const tries = [];
  if (process.env.PLAYWRIGHT_MODULE) tries.push(process.env.PLAYWRIGHT_MODULE);
  const req = createRequire(path.join(process.cwd(), 'noop.js'));
  for (const name of ['playwright', '@playwright/test']) { try { tries.push(req.resolve(name)); } catch { /* not in this repo */ } }
  for (const p of tries) {
    try { const m = await import(p.startsWith('/') ? pathToFileURL(p).href : p); const pw = m.chromium ? m : m.default; if (pw && pw.chromium) return pw; } catch { /* next */ }
  }
  return null;
}

async function main() {
  let o;
  try { o = parseArgs(process.argv.slice(2)); } catch (e) { console.error(`visual-check: ${e.message}`); process.exit(2); }
  const pw = await loadPlaywright();
  if (!pw) {
    console.error('visual-check: no Playwright here. Run from a repo that has `playwright` or `@playwright/test`, or point PLAYWRIGHT_MODULE at one (e.g. a scratch `npm i playwright` + `npx playwright install chromium`).');
    process.exit(2);
  }
  fs.mkdirSync(o.out, { recursive: true });
  const linuxRoot = process.platform === 'linux' && process.getuid && process.getuid() === 0;
  const browser = await pw.chromium.launch(linuxRoot ? { args: ['--no-sandbox'] } : {});
  const report = { when: new Date().toISOString(), runs: [] };
  let issues = 0, failed = false;
  try {
    for (const url of o.urls) for (const width of o.widths) {
      const phone = width <= PHONE_MAX;
      const ctx = await browser.newContext({ viewport: { width, height: phone ? 844 : 800 }, deviceScaleFactor: phone ? 2 : 1, isMobile: phone, hasTouch: phone,
        storageState: o.storageState || undefined, extraHTTPHeaders: o.headers, colorScheme: o.colorScheme || undefined });
      const page = await ctx.newPage(), consoleErrors = [], pageErrors = [], failedRequests = [];
      page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 300)); });
      page.on('pageerror', e => pageErrors.push(String(e).slice(0, 300)));
      page.on('response', r => { if (r.status() >= 400) failedRequests.push(`${r.status()} ${r.url().slice(0, 200)}`); });
      const base = `${o.label ? o.label + '-' : ''}${shotStem(url)}-${width}`;
      const run = { url, width, shots: [] };
      try {
        await page.goto(url, { waitUntil: 'load', timeout: 45000 });
        if (o.waitFor) await page.waitForSelector(o.waitFor, { timeout: 20000 });
        await page.waitForTimeout(o.wait);
        // The surface you changed is what gets judged: bring it on screen first (an app that scrolls inside a panel
        // never shows it in a full-page shot), so the screenshot and the lint both cover it.
        if (o.selector) { const el = page.locator(o.selector).first(); if (await el.count()) { await el.scrollIntoViewIfNeeded().catch(() => {}); await page.waitForTimeout(200); } }
        const shot = path.join(o.out, `${base}.png`);
        await page.screenshot({ path: shot, fullPage: o.full });
        run.shots.push(shot);
        if (o.selector) {
          const el = page.locator(o.selector).first();
          if (await el.count()) { const s = path.join(o.out, `${base}-element.png`); await el.screenshot({ path: s }); run.shots.push(s); }
          else run.selectorMissing = o.selector;
        }
        run.consoleErrors = consoleErrors; run.pageErrors = pageErrors; run.failedRequests = failedRequests;
        run.issues = o.lint ? lint(await page.evaluate(collect), width) : [];
      } catch (e) { run.error = String(e.message || e).split('\n')[0]; failed = true; }
      await ctx.close();
      report.runs.push(run);
      const n = (run.issues || []).length + (run.consoleErrors || []).length + (run.pageErrors || []).length + (run.failedRequests || []).length + (run.selectorMissing ? 1 : 0);
      issues += n;
      console.log(`\n${url} @ ${width}px — ${run.error ? 'FAILED: ' + run.error : n ? `${n} to look at` : 'nothing flagged'}`);
      for (const s of run.shots) console.log(`  shot   ${s}`);
      if (run.selectorMissing) console.log(`  !      the selector ${run.selectorMissing} matched nothing`);
      for (const e of run.pageErrors || []) console.log(`  error  ${e}`);
      for (const e of run.consoleErrors || []) console.log(`  console ${e}`);
      for (const e of run.failedRequests || []) console.log(`  http   ${e}`);
      const byKind = new Map();
      for (const x of run.issues || []) byKind.set(x.kind, [...(byKind.get(x.kind) || []), x]);
      for (const [kind, xs] of byKind) {
        for (const x of xs.slice(0, 6)) console.log(`  ${kind.padEnd(20)} ${x.sel} — ${x.detail}`);
        if (xs.length > 6) console.log(`  ${kind.padEnd(20)} … ${xs.length - 6} more in the report`);
      }
    }
  } finally { await browser.close(); }
  fs.writeFileSync(path.join(o.out, `${o.label ? o.label + '-' : ''}report.json`), JSON.stringify(report, null, 1));
  console.log(`\nreport: ${path.join(o.out, `${o.label ? o.label + '-' : ''}report.json`)} — read every screenshot above before calling the round done.`);
  process.exit(failed ? 2 : issues ? 1 : 0);
}

if (import.meta.url === pathToFileURL(process.argv[1] || '').href) main();
