/* Annotate templates.js with what each slot ACTUALLY is.
 *
 * build-templates.py can only see slot names, and names lie: `p1-label` is a
 * 38px bold card heading in deck A, while `t1-label` is a 14px uppercase
 * kicker in deck B. Guessing from the name is what put a paragraph at 57px
 * and a heading at 24px. So we render each design in Chromium, measure every
 * [data-slot], and write the answer into the file.
 *
 * Kinds
 *   kicker   small uppercase label — a stage name, never a sentence
 *   display  the slide's own headline
 *   lede     the supporting sentence under a headline
 *   figure   a big number or short marker
 *   heading  a card's heading inside a grid of three
 *   note     the supporting line under a card heading
 *
 * Usage:  node tools/annotate-kinds.mjs path/to/templates.js
 */
import { chromium } from 'playwright';
import fs from 'node:fs';

const FILE = process.argv[2] || 'templates.js';
const src = fs.readFileSync(FILE, 'utf8');
const m = src.match(/window\.DECK_TEMPLATES\s*=\s*(\[[\s\S]*\]);?\s*$/);
if (!m) { console.error('no window.DECK_TEMPLATES assignment in ' + FILE); process.exit(1); }
const templates = JSON.parse(m[1]);

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium' });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
await page.goto('about:blank');

const measured = await page.evaluate(async (tpls) => {
  const out = [];
  for (const t of tpls) {
    const frame = document.createElement('iframe');
    frame.style.cssText = 'position:fixed;left:-9999px;top:0;width:1600px;height:900px;border:0';
    document.body.appendChild(frame);
    frame.srcdoc = t.html;
    await new Promise(r => { frame.onload = r; });
    await new Promise(r => setTimeout(r, 120));
    const doc = frame.contentDocument, win = frame.contentWindow;
    const sections = [...doc.querySelectorAll('[data-role]')].map(sec => {
      const slots = {};
      sec.querySelectorAll('[data-slot]').forEach(el => {
        const cs = win.getComputedStyle(el);
        const box = el.getBoundingClientRect();
        slots[el.dataset.slot] = {
          size: Math.round(parseFloat(cs.fontSize) || 0),
          weight: parseInt(cs.fontWeight, 10) || 400,
          upper: cs.textTransform === 'uppercase',
          width: Math.round(box.width)
        };
      });
      return { role: sec.dataset.role, slots };
    });
    out.push({ id: t.id, sections });
    frame.remove();
  }
  return out;
}, templates);

await browser.close();

/* group key: strip the sub-role suffix so p1-label and p1 sit together */
const groupOf = n => n.replace(/-(label|title|caption)$/, '');

/* How many characters comfortably fill the slot's own box at its own size.
   Rough but measured: an average glyph is ~0.52em wide, and we allow the
   number of lines the design already gives that kind. */
const LINES = { kicker: 1, display: 2, lede: 3, figure: 1, heading: 2, note: 3 };
function capFor(kind, m) {
  if (kind === 'figure') return 12;
  const perLine = Math.max(6, Math.floor(m.width / (m.size * 0.52)));
  const cap = perLine * LINES[kind];
  const ceiling = { kicker: 30, display: 62, lede: 130, heading: 34, note: 88 }[kind] || 90;
  return Math.max(10, Math.min(cap, ceiling));
}

function classify(role, slots) {
  const names = Object.keys(slots);
  const groups = {};
  names.forEach(n => { (groups[groupOf(n)] = groups[groupOf(n)] || []).push(n); });

  const kinds = {};
  for (const [g, members] of Object.entries(groups)) {
    // A small uppercase member of any group is always a kicker.
    const rest = [];
    members.forEach(n => {
      const s = slots[n];
      if (s.upper && s.size <= 18) kinds[n] = 'kicker'; else rest.push(n);
    });
    if (!rest.length) continue;

    rest.sort((a, b) => slots[b].size - slots[a].size);
    const top = rest[0], t = slots[top];

    // The section's own headline/statement is the display line; a very large
    // slot inside a numbered group is a figure only when it reads as one.
    const isSectionHead = /^(headline|statement)$/.test(top);
    const isNumber = /hero-number$/.test(top) || /^stat-\d+$/.test(top);
    kinds[top] = isSectionHead ? 'display'
               : isNumber      ? 'figure'
               : (members.length === 1 && /^(subhead|lede|body|hero-caption)$/.test(top)) ? 'lede'
               : (members.length === 1 && t.size >= 30 && t.weight < 600) ? 'lede'
               : 'heading';
    rest.slice(1).forEach(n => {
      kinds[n] = (kinds[top] === 'display' || kinds[top] === 'figure') ? 'lede' : 'note';
    });
  }
  // A bare `body`/`subhead` sitting beside a display headline is the lede.
  names.forEach(n => {
    if (/^(subhead|body|lede)$/.test(n)) kinds[n] = 'lede';
    if (/^(footnote|attrib)$/.test(n)) kinds[n] = 'kicker';
  });
  return kinds;
}

let annotated = 0;
templates.forEach(t => {
  const found = measured.find(x => x.id === t.id);
  if (!found) return;
  t.sections.forEach((sec, i) => {
    const mm = found.sections[i];
    if (!mm) return;
    const kinds = classify(sec.role, mm.slots);
    sec.kinds = {};
    sec.caps = {};
    sec.slots.forEach(name => {
      const k = kinds[name] || 'note';
      sec.kinds[name] = k;
      sec.caps[name] = mm.slots[name] ? capFor(k, mm.slots[name])
                                      : ({ kicker: 30, display: 62, lede: 130, heading: 34, note: 88, figure: 12 }[k]);
      annotated++;
    });
  });
});

const header = src.slice(0, src.indexOf('window.DECK_TEMPLATES'));
fs.writeFileSync(FILE, header + 'window.DECK_TEMPLATES = ' + JSON.stringify(templates) + ';\n');
console.log(`annotated ${annotated} slots across ${templates.length} designs → ${FILE}`);
templates.forEach(t => {
  console.log('\n## ' + t.id);
  t.sections.forEach((s, i) => console.log('  ' + i + ' ' + s.role + ' | ' +
    s.slots.map(n => `${n}:${s.kinds[n]}/${s.caps[n]}`).join('  ')));
});
