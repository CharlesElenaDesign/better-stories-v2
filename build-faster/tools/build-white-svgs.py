#!/usr/bin/env python3
"""Write a genuine white .svg for every vector logo in deck-studio/logos/.

    python3 tools/build-white-svgs.py [--force]

Until now a vector mark was reversed at render time with
`filter:brightness(0) invert(1)`. That works, but it is a CSS trick: it
depends on the filter being applied, it can't be inspected, and it silently
does the wrong thing to a mark that carries its own background. This writes
the reversed artwork out as a real file instead — logos/<slug>-white.svg —
which build-logos.py already treats as an override that wins outright.

What "white" means here: every paint in the file is forced to #fff —
fill, stroke, stop-color, presentation attributes, inline styles and any
embedded CSS — while `none` is left alone so counters and knock-outs stay
knocked out. A gradient is flattened to flat white, because a two-colour
gradient on a one-colour mark is noise.

An existing <slug>-white.svg is never overwritten without --force: a real
reversed asset from a brand kit always beats a derived one.

Marks this cannot do honestly are reported, not faked:
  · a .png with no vector source
  · an .svg that is only a wrapper around an embedded raster
"""
import os, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(HERE, 'logos')
FORCE = '--force' in sys.argv
MARK = '<!-- white variant derived from the vector source by tools/build-white-svgs.py -->'

NONE = re.compile(r'^\s*none\s*$', re.I)

def paint(m):
    """fill="X" / stroke="X" / stop-color="X"  →  #fff, unless X is none."""
    prop, q, val = m.group(1), m.group(2), m.group(3)
    return m.group(0) if NONE.match(val) else f'{prop}={q}#fff{q}'

def css_paint(m):
    prop, val = m.group(1), m.group(2)
    return m.group(0) if NONE.match(val) else f'{prop}:#fff'

def whiten(t):
    # presentation attributes
    t = re.sub(r'\b(fill|stroke|stop-color|flood-color|lighting-color)=(["\'])(.*?)\2', paint, t, flags=re.S)
    # inline style="" and any embedded <style> block — same property syntax
    t = re.sub(r'\b(fill|stroke|stop-color|flood-color|lighting-color)\s*:\s*([^;"\'}]+)', css_paint, t)
    # a shape painted from a gradient or pattern is flattened to flat white
    t = re.sub(r'(["\':;\s])url\(#[^)]*\)', r'\1#fff', t)
    # anything with no paint at all defaults to black, so the root carries white
    if not re.search(r'<svg\b[^>]*\sfill=', t):
        t = re.sub(r'<svg\b', '<svg fill="#fff"', t, count=1)
    return t

def is_raster_wrapper(t):
    """An <svg> whose only content is an embedded bitmap can't be recoloured."""
    if '<image' not in t:
        return False
    shapes = len(re.findall(r'<(path|rect|circle|ellipse|polygon|polyline|line|text)\b', t))
    return shapes == 0

DARK_INK = '#0B0E12'
NEAR_WHITE = re.compile(r'^\s*(#fff(?:fff)?|white|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))\s*$', re.I)

def ink(m):
    """The mirror of paint(): white becomes ink, every other hue is left alone."""
    prop, q, val = m.group(1), m.group(2), m.group(3)
    return f'{prop}={q}{DARK_INK}{q}' if NEAR_WHITE.match(val) else m.group(0)

def css_ink(m):
    prop, val = m.group(1), m.group(2)
    return f'{prop}:{DARK_INK}' if NEAR_WHITE.match(val) else m.group(0)

PAINTS = r'\b(fill|stroke|stop-color|flood-color|lighting-color)'

def darken(t):
    t = re.sub(PAINTS + r'=(["\'])(.*?)\2', ink, t, flags=re.S)
    t = re.sub(PAINTS + r'\s*:\s*([^;"\'}]+)', css_ink, t)
    if not re.search(r'<svg\b[^>]*\sfill=', t):
        t = re.sub(r'<svg\b', f'<svg fill="{DARK_INK}"', t, count=1)
    return t

def is_reversed_asset(t):
    """Is this file already drawn for a dark background?

    Some marks in the library — Infosys's among them — are supplied as the
    reversed version: white artwork with one brand accent. On a light deck
    those vanish, so they need the opposite derivation, not this one. A mark
    drawn in its own colours does not.
    """
    paints = re.findall(PAINTS + r'\s*[:=]\s*["\']?([^;"\'>}\s]+)', t)
    vals = [v for _, v in paints if not NONE.match(v) and not v.startswith('url(')]
    if len(vals) < 2:
        return False
    whites = sum(1 for v in vals if NEAR_WHITE.match(v))
    # A file is drawn for a dark ground when a good share of it is white and
    # nothing in it is dark — a mark with its own dark ink already works on
    # a light deck and must be left alone.
    def luminance(v):
        h = v.strip().lstrip('#')
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        if len(h) != 6:
            return None
        try:
            r, g, b = (int(h[i:i+2], 16) for i in (0, 2, 4))
        except ValueError:
            return None
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    lums = [l for l in (luminance(v) for v in vals) if l is not None]
    has_dark = any(l < 0.35 for l in lums)
    return whites / len(vals) >= 0.4 and not has_dark

written, skipped_existing, wrappers, rasters, darks = [], [], [], [], []

for f in sorted(os.listdir(SRC)):
    if f == 'SOURCES.json' or f.startswith('.'):
        continue
    slug, _, ext = f.rpartition('.')
    if re.search(r'-(white|dark)$', slug, re.I):
        continue
    ext = ext.lower()

    if ext != 'svg':
        if os.path.exists(os.path.join(SRC, f'{slug}-white.svg')):
            continue
        rasters.append(f'{slug}.{ext}')
        continue

    out = os.path.join(SRC, f'{slug}-white.svg')
    if os.path.exists(out) and not FORCE:
        skipped_existing.append(slug)
        continue

    t = open(os.path.join(SRC, f), encoding='utf-8', errors='replace').read()
    if is_raster_wrapper(t):
        wrappers.append(slug)
        continue

    body = whiten(t)
    if MARK not in body:
        body = re.sub(r'(<svg\b[^>]*>)', r'\1' + MARK, body, count=1)
    open(out, 'w', encoding='utf-8').write(body)
    written.append(slug)

    # A mark that ships reversed has no version for a light deck, so derive
    # one: white becomes ink, the brand accent is left exactly as it is.
    if is_reversed_asset(t):
        dout = os.path.join(SRC, f'{slug}-dark.svg')
        if not os.path.exists(dout) or FORCE:
            dbody = darken(t)
            if MARK not in dbody:
                dbody = re.sub(r'(<svg\b[^>]*>)', r'\1' + MARK, dbody, count=1)
            open(dout, 'w', encoding='utf-8').write(dbody)
            darks.append(slug)

print(f'{len(written)} white SVGs written to logos/')
if darks:
    print(f'{len(darks)} marks ship reversed, so a light-deck version was derived too: ' + ', '.join(darks))
if skipped_existing:
    print(f'{len(skipped_existing)} already had one (kept): ' + ', '.join(skipped_existing))
if wrappers:
    print('vector wrapper around a bitmap — cannot be recoloured: ' + ', '.join(wrappers))
if rasters:
    print('no vector source, so no white SVG is possible: ' + ', '.join(rasters))
    print('  → these keep their synthesised white PNG. For a true SVG, add the')
    print('    reversed asset from the brand kit as logos/<slug>-white.svg.')
print('\nNow re-run:  python3 tools/build-logos.py')
