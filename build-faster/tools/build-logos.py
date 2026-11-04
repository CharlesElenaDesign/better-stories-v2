#!/usr/bin/env python3
"""Regenerate deck-studio/logos.js from deck-studio/logos/.

Run after adding, replacing or removing a logo:

    python3 tools/build-logos.py

Why a generated script instead of fetching the files:
fetch() is blocked on file:// (the page's origin is "null"), so a builder
opened by double-clicking index.html could never load a logo. A plain
<script src> has no such restriction, so the pack is injected on demand.

SVGs are stripped of editor metadata and given a viewBox where the source
file declared only width/height — without one the mark collapses or blows
out inside a height-constrained box.
"""
import os, re, base64, json, sys, io
try:
    from PIL import Image
except ImportError:
    Image = None

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(HERE, 'logos')
OUT  = os.path.join(HERE, 'logos.js')

def clean_svg(t):
    t = re.sub(r'<\?xml[^>]*\?>', '', t)
    # A DOCTYPE may carry an internal subset — Illustrator writes
    #   <!DOCTYPE svg PUBLIC "…" "…dtd" [ <!ENTITY ns_flows "…"> ]>
    # and [^>]* stops at the entity's own '>', leaving a dangling "]>" that
    # makes the file unparseable. Vestas's mark failed to load for exactly
    # this reason. Match the optional [ … ] before the closing '>'.
    t = re.sub(r'<!DOCTYPE[^>\[]*(?:\[[^\]]*\]\s*)?>', '', t, flags=re.S)
    t = re.sub(r'<!--.*?-->', '', t, flags=re.S)
    t = re.sub(r'<metadata\b.*?</metadata>', '', t, flags=re.S)
    t = re.sub(r'<sodipodi:namedview\b[^>]*/>', '', t, flags=re.S)
    t = re.sub(r'<sodipodi:namedview\b.*?</sodipodi:namedview>', '', t, flags=re.S)
    t = re.sub(r'\s+(inkscape|sodipodi):[a-zA-Z-]+="[^"]*"', '', t)
    t = re.sub(r'>\s+<', '><', t)
    t = re.sub(r'\s{2,}', ' ', t).strip()
    if 'viewBox' not in t:
        w = re.search(r'\swidth="(\d+(?:\.\d+)?)', t)
        h = re.search(r'\sheight="(\d+(?:\.\d+)?)', t)
        if w and h:
            t = re.sub(r'<svg\b', f'<svg viewBox="0 0 {w.group(1)} {h.group(1)}"', t, count=1)
    return t

MIME = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}

def white_variant(path):
    """Build a genuinely white version of a raster mark.

    A CSS filter can only recolour what is already on transparency.
    lloyds.png is artwork on a solid green plate, so filtering it produced a
    white block. Here the plate is knocked out by colour distance from the
    corner pixel, and everything that survives is painted white — which is
    what a co-branded deck on a dark ground actually needs.
    """
    if Image is None:
        return None
    try:
        im = Image.open(path).convert('RGBA')
        px = im.load()
        w, h = im.size
        corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
        opaque_bg = [c for c in corners if c[3] > 40]
        out = Image.new('RGBA', (w, h), (255, 255, 255, 0))
        op = out.load()
        if opaque_bg:
            bg = opaque_bg[0]
            tol, soft = 42.0, 88.0          # inside tol = plate, beyond soft = solid mark
            for y in range(h):
                for x in range(w):
                    r, g, b, a = px[x, y]
                    if a < 24:
                        continue
                    d = ((r-bg[0])**2 + (g-bg[1])**2 + (b-bg[2])**2) ** 0.5
                    if d <= tol:
                        continue
                    k = 255 if d >= soft else int(255 * (d - tol) / (soft - tol))
                    op[x, y] = (255, 255, 255, k)
        else:
            for y in range(h):
                for x in range(w):
                    a = px[x, y][3]
                    if a >= 12:
                        op[x, y] = (255, 255, 255, a)
        buf = io.BytesIO()
        out.save(buf, 'PNG', optimize=True)
        return buf.getvalue()
    except Exception:
        return None


def whiten_safe(path):
    """Can this mark be recoloured white with brightness(0) invert(1)?

    Only if it sits on transparency. lloyds.png is a flat RGB rectangle with
    no alpha at all, so whitening turned the entire logo into a white block
    on the deck. A mark with an opaque background gets a white plate instead.
    """
    if Image is None:
        return True
    try:
        im = Image.open(path).convert('RGBA')
        im.thumbnail((96, 96))
        px = list(im.getdata())
        n = len(px)
        w = im.size[0]
        corners = [px[0], px[w - 1], px[-w], px[-1]]
        if any(c[3] > 40 for c in corners):
            return False                      # background is opaque
        clear = sum(1 for q in px if q[3] < 24) / max(1, n)
        return clear >= 0.10
    except Exception:
        return True

# An official reversed asset always beats a synthesised one. Drop
# "<slug>-white.svg" or "<slug>-white.png" into logos/ and it is used
# verbatim — nothing is derived, nothing is recreated.
overrides, darkvars = {}, {}
for f in os.listdir(SRC):
    m = re.match(r'(.+)-white\.(svg|png|jpg|jpeg|webp)$', f, re.I)
    if m:
        overrides[m.group(1).lower()] = f
    # A few marks — Infosys's among them — are supplied already reversed:
    # white artwork that vanishes on a light deck. "<slug>-dark.svg" is the
    # version for a light ground, and belongs to its parent, not to a logo
    # of its own.
    d = re.match(r'(.+)-dark\.(svg|png|jpg|jpeg|webp)$', f, re.I)
    if d:
        darkvars[d.group(1).lower()] = f

pack, fixed, whited, official = {}, [], [], []
for f in sorted(os.listdir(SRC)):
    if f == 'SOURCES.json' or f.startswith('.'):
        continue
    if re.search(r'-(white|dark)\.(svg|png|jpg|jpeg|webp)$', f, re.I):
        continue                      # folded into the parent entry below
    slug, _, ext = f.rpartition('.')
    data = open(os.path.join(SRC, f), 'rb').read()
    if ext.lower() == 'svg':
        t = data.decode('utf-8', 'replace')
        had = 'viewBox' in t
        t = clean_svg(t)
        if not had and 'viewBox' in t:
            fixed.append(slug)
        # Vector marks in this library are flat artwork on transparency.
        pack[slug] = {'u': 'data:image/svg+xml;base64,' + base64.b64encode(t.encode()).decode(), 'w': True}
    elif ext.lower() in MIME:
        full = os.path.join(SRC, f)
        entry = {'u': f'data:{MIME[ext.lower()]};base64,' + base64.b64encode(data).decode(),
                 'w': whiten_safe(full)}
        wv = None if slug.lower() in overrides else white_variant(full)
        if wv:
            entry['uw'] = 'data:image/png;base64,' + base64.b64encode(wv).decode()
            entry['w'] = True          # a real white version exists, so no plate needed
            whited.append(slug)
        pack[slug] = entry
    else:
        print('  skipped (unknown type):', f, file=sys.stderr)

# Apply the overrides last so they win outright.
for slug, fname in overrides.items():
    if slug not in pack:
        continue
    data = open(os.path.join(SRC, fname), 'rb').read()
    ext = fname.rsplit('.', 1)[1].lower()
    if ext == 'svg':
        uri = 'data:image/svg+xml;base64,' + base64.b64encode(clean_svg(data.decode('utf-8', 'replace')).encode()).decode()
    else:
        uri = f'data:{MIME.get(ext, "image/png")};base64,' + base64.b64encode(data).decode()
    pack[slug]['uw'] = uri
    pack[slug]['w'] = True
    if slug in whited:
        whited.remove(slug)
    official.append(slug)

# The light-deck version, keyed on the same slug.
for slug, fname in darkvars.items():
    if slug not in pack:
        continue
    data = open(os.path.join(SRC, fname), 'rb').read()
    ext = fname.rsplit('.', 1)[1].lower()
    if ext == 'svg':
        pack[slug]['ud'] = 'data:image/svg+xml;base64,' + base64.b64encode(
            clean_svg(data.decode('utf-8', 'replace')).encode()).decode()
    else:
        pack[slug]['ud'] = f'data:{MIME.get(ext, "image/png")};base64,' + base64.b64encode(data).decode()

if 'infosys' not in pack:
    sys.exit('logos/infosys.svg is missing — the co-branded lockup needs it.')

js = ('/* GENERATED by tools/build-logos.py — do not edit by hand.\n'
      '   Logo data URIs, loaded on demand by index.html. See the tool for why. */\n'
      'window.DECK_LOGOS = ' + json.dumps(pack, separators=(',', ':')) + ';\n')
open(OUT, 'w', encoding='utf-8').write(js)

plated = [k for k, v in pack.items() if not v['w']]
# Distinguish a real reversed asset from one this toolchain derived: both
# win over a CSS filter, but only one of them came from a brand kit.
derived = [k for k in official
           if 'build-white-svgs.py' in open(os.path.join(SRC, overrides[k]), encoding='utf-8',
                                            errors='replace').read()[:4000]]
brandkit = [k for k in official if k not in derived]
if brandkit:
    print('official reversed asset used for:', ', '.join(sorted(brandkit)))
if derived:
    print(f'white SVG derived from the vector source for {len(derived)} marks')
if whited:
    print('white version synthesised for (no vector available):', ', '.join(whited))
    print('  → to avoid synthesis, add logos/<slug>-white.svg and re-run.')
if darkvars:
    print('light-deck version carried for:', ', '.join(sorted(k for k in darkvars if k in pack)))
print(f'{len(pack)} logos → logos.js ({len(js)/1024:.0f} KB)')
if plated:
    print('opaque background, rendered on a white plate:', ', '.join(plated))
if Image is None:
    print('NOTE: Pillow not installed — every raster assumed whiten-safe.')
if fixed:
    print('viewBox injected for:', ', '.join(fixed))
print('\nNote: index.html loads ./logos.js?v=N — bump that N so CloudFront serves the new pack.')
