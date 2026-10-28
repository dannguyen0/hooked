#!/usr/bin/env python3
"""fishgen.py — Victorian woodcut/etching style fish plates.
Outputs SVG to images/fish/vector/ (app.js loads .svg directly; no cairosvg needed)."""
import os, json, random

OUT = os.environ.get("FISH_OUT", "images/fish/vector")
os.makedirs(OUT, exist_ok=True)
W, H, CY = 1200, 520, 262
X0, X1 = 175, 1010

INK   = "#12100A"
CREAM = "#F2EAD8"

# ── geometry helpers ──────────────────────────────────────────────────────────

def lerp(a, b, t): return a + (b - a) * t

def cr_closed(pts):
    n = len(pts)
    d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f} "
    for i in range(n):
        p0 = pts[(i-1)%n]; p1 = pts[i]; p2 = pts[(i+1)%n]; p3 = pts[(i+2)%n]
        c1 = (p1[0]+(p2[0]-p0[0])/6, p1[1]+(p2[1]-p0[1])/6)
        c2 = (p2[0]-(p3[0]-p1[0])/6, p2[1]-(p3[1]-p1[1])/6)
        d += f"C {c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f} "
    return d + "Z"

def body_loop(profile):
    top = [(lerp(X0, X1, f), CY - t) for f, t, b in profile]
    bot = [(lerp(X0, X1, f), CY + b) for f, t, b in profile]
    return top + bot[::-1]

def prof_top_at(prof, f):
    for i in range(len(prof)-1):
        if prof[i][0] <= f <= prof[i+1][0]:
            t = (f-prof[i][0]) / (prof[i+1][0]-prof[i][0])
            return lerp(prof[i][1], prof[i+1][1], t)
    return prof[-1][1]

def prof_bot_at(prof, f):
    for i in range(len(prof)-1):
        if prof[i][0] <= f <= prof[i+1][0]:
            t = (f-prof[i][0]) / (prof[i+1][0]-prof[i][0])
            return lerp(prof[i][2], prof[i+1][2], t)
    return prof[-1][2]

def caudal(kind, py, depth, length=150, off=0):
    x = X1 + off
    if kind == "fork":
        return (f'<path d="M {x-6} {py-depth*0.5} L {x+length} {py-depth} '
                f'L {x+length*0.62} {py} L {x+length} {py+depth} L {x-6} {py+depth*0.5} '
                f'Q {x+30} {py} {x-6} {py-depth*0.5} Z" />')
    if kind == "lunate":
        return (f'<path d="M {x-6} {py-depth*0.45} L {x+length} {py-depth*1.15} '
                f'Q {x+length*0.4} {py} {x+length} {py+depth*1.15} L {x-6} {py+depth*0.45} '
                f'Q {x+24} {py} {x-6} {py-depth*0.45} Z" />')
    return (f'<path d="M {x-6} {py-depth*0.55} Q {x+length} {py-depth} {x+length} {py} '
            f'Q {x+length} {py+depth} {x-6} {py+depth*0.55} Q {x+22} {py} {x-6} {py-depth*0.55} Z" />')

# ── woodcut texture helpers ───────────────────────────────────────────────────

def hatch_lines(bid, prof, n=50):
    """Graduated horizontal hatching: dense/dark at back (top), sparse at belly."""
    top_y = CY - max(t for _, t, b in prof) - 12
    bot_y = CY + max(b for _, t, b in prof) + 12
    out = f'<g clip-path="url(#c{bid})" stroke="{INK}" fill="none" stroke-linecap="round">'
    for i in range(n):
        t = i / (n - 1)
        y = lerp(top_y, bot_y, t)
        op = 0.72 * (1 - t) ** 0.45 + 0.03
        sw = 2.0 - 0.9 * t
        out += f'<line x1="{X0-50}" y1="{y:.1f}" x2="{X1+220}" y2="{y:.1f}" stroke-width="{sw:.2f}" opacity="{op:.2f}"/>'
    out += '</g>'
    return out

def scale_arcs(bid, prof, cols=18, rows=12):
    """Overlapping arc grid to suggest scales, clipped to body."""
    top_y = CY - prof_top_at(prof, 0.5) + 6
    bot_y = CY + prof_bot_at(prof, 0.5) - 6
    body_h = bot_y - top_y
    row_h  = body_h / rows
    col_w  = (X1 - X0) / cols
    r = col_w * 0.70
    out = f'<g clip-path="url(#c{bid})" fill="none" stroke="{INK}" stroke-width="1.1" opacity="0.32">'
    for row in range(rows + 2):
        offset = (row % 2) * col_w * 0.5
        y = top_y + row * row_h
        for col in range(-1, cols + 2):
            x = X0 + col * col_w + offset
            out += f'<path d="M {x-r:.1f} {y:.1f} A {r:.1f} {r:.1f} 0 0 1 {x+r:.1f} {y:.1f}"/>'
    out += '</g>'
    return out

def fin_rays(x1, y1, x2, y2, n=9, sw=0.85, op=0.32):
    """Parallel ray lines across a fin from base edge to tip."""
    out = ""
    for i in range(n):
        t = i / (n - 1)
        bx = lerp(x1, x2, t)
        tx = bx + lerp(-6, 6, t)
        out += f'<line x1="{bx:.0f}" y1="{y1:.0f}" x2="{tx:.0f}" y2="{y2:.0f}" stroke="{INK}" stroke-width="{sw}" opacity="{op}"/>'
    return out

def eye_at(x, y, r=13):
    return (f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r+3:.0f}" fill="{CREAM}" stroke="{INK}" stroke-width="2"/>'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" fill="{INK}" stroke="none"/>'
            f'<circle cx="{x-r*0.3:.0f}" cy="{y-r*0.3:.0f}" r="{r*0.32:.0f}" fill="{CREAM}" stroke="none"/>')

# ── mark helpers (all ink, clipped to body by caller) ────────────────────────

def spots(prof, n=26, rmin=5, rmax=12, seed=7, y0=.15, y1=.85):
    random.seed(seed); out = ""
    for _ in range(n):
        f = random.uniform(.18, .92)
        x = lerp(X0, X1, f)
        top = CY - prof_top_at(prof, f); bot = CY + prof_bot_at(prof, f)
        y = lerp(top, bot, random.uniform(y0, y1))
        r = random.uniform(rmin, rmax)
        op = random.uniform(0.17, 0.36)
        out += f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" fill="{INK}" opacity="{op:.2f}"/>'
    return out

def bars(prof, n=7, w=18, op=0.22):
    out = ""
    for i in range(n):
        f = lerp(.22, .8, i/(n-1)); x = lerp(X0, X1, f)
        top = CY - prof_top_at(prof, f) + 6; bot = CY + prof_bot_at(prof, f) - 6
        out += f'<rect x="{x-w/2:.0f}" y="{top:.0f}" width="{w}" height="{bot-top:.0f}" fill="{INK}" opacity="{op}"/>'
    return out

def wavy_bars(prof, n=9, op=0.28):
    out = ""
    for i in range(n):
        f = lerp(.2, .82, i/(n-1)); x = lerp(X0, X1, f)
        top = CY - prof_top_at(prof, f) + 4
        out += f'<path d="M {x:.0f} {top:.0f} q 22 12 10 30 q -14 16 6 30" fill="none" stroke="{INK}" stroke-width="5" opacity="{op}"/>'
    return out

def lateral(prof, f0=.18, f1=.95, yfrac=.42, op=0.38, w=2):
    pts = []
    for i in range(20):
        f = lerp(f0, f1, i/19); x = lerp(X0, X1, f)
        top = CY - prof_top_at(prof, f); bot = CY + prof_bot_at(prof, f)
        pts.append(f"{x:.0f} {lerp(top, bot, yfrac):.0f}")
    return f'<polyline points="{" ".join(pts)}" fill="none" stroke="{INK}" stroke-width="{w}" opacity="{op}"/>'

def blotches(prof, n=18, seed=3):
    random.seed(seed); out = ""
    for _ in range(n):
        f = random.uniform(.2, .9); x = lerp(X0, X1, f)
        top = CY - prof_top_at(prof, f); bot = CY + prof_bot_at(prof, f)
        y = lerp(top, bot, random.uniform(.1, .9))
        rx = random.uniform(10, 26); ry = random.uniform(8, 18)
        out += f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{rx:.0f}" ry="{ry:.0f}" fill="{INK}" opacity="{random.uniform(0.13, 0.26):.2f}"/>'
    return out

def finlets(prof):
    out = ""
    for i in range(5):
        f = lerp(.78, .96, i/4); x = lerp(X0, X1, f)
        out += f'<path d="M {x:.0f} {CY-prof_top_at(prof,f):.0f} l 14 -10 l 2 10 Z" fill="{INK}" opacity=".45"/>'
        out += f'<path d="M {x:.0f} {CY+prof_bot_at(prof,f):.0f} l 14 10 l 2 -10 Z" fill="{INK}" opacity=".45"/>'
    return out

def adipose(prof):
    f = .58; x = lerp(X0, X1, f); y = CY - prof_top_at(prof, f)
    return f'<path d="M {x:.0f} {y:.0f} q 40 -18 70 -2 l -4 12 q -34 -8 -66 4 Z" fill="{CREAM}" stroke="{INK}" stroke-width="1.5" opacity=".9"/>'

# ── SVG document wrapper ──────────────────────────────────────────────────────

def svg_doc(bid, body_d, texture, marks_clipped, front, eye, behind):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">
<defs><clipPath id="c{bid}"><path d="{body_d}"/></clipPath></defs>
<g stroke="{INK}" stroke-width="2.8" stroke-linejoin="round" fill="none">
{behind}
<path d="{body_d}" fill="{CREAM}" stroke="none"/>
{texture}
<g clip-path="url(#c{bid})" stroke="none" fill="{INK}">{marks_clipped}</g>
<path d="{body_d}" fill="none"/>
{front}
{eye}
</g></svg>'''

# ── standard fish builder ─────────────────────────────────────────────────────

FUSI   = [(.0,10,12),(.07,46,40),(.18,82,72),(.38,96,88),(.62,84,80),(.82,52,54),(.93,30,34),(1.0,16,18)]
DEEP   = [(.0,12,14),(.07,70,58),(.2,118,104),(.42,128,120),(.66,104,104),(.84,60,66),(.94,32,36),(1.0,16,18)]
ELON   = [(.0,8,12),(.08,44,40),(.22,62,58),(.45,64,62),(.68,56,56),(.85,38,40),(.94,24,26),(1.0,12,14)]
STREAM = [(.0,8,10),(.08,40,36),(.22,66,58),(.45,70,62),(.68,54,50),(.84,34,32),(.93,22,22),(1.0,12,12)]

def standard(p):
    prof   = p["profile"]
    bid    = p["id"]
    loop   = body_loop(prof)
    body_d = cr_closed(loop)
    behind = ""
    front  = ""

    topline = lambda f: CY - prof_top_at(prof, f)
    botline = lambda f: CY + prof_bot_at(prof, f)

    # caudal fin
    behind += f'<g fill="{CREAM}">{caudal(p.get("tail","fork"), CY, p.get("tailH",70), p.get("tailLen",150))}</g>'

    # dorsal fin
    dx1, dx2 = [lerp(X0, X1, f) for f in p.get("dorsal", (.30, .72))]
    dh = p.get("dorsalH", 60)
    if p.get("spinyDorsal", True):
        pts = f"M {dx1:.0f} {topline(p['dorsal'][0]):.0f} "
        ns = 9
        for i in range(ns + 1):
            f  = lerp(p["dorsal"][0], p["dorsal"][1], i/ns)
            bx = lerp(X0, X1, f); by = topline(f)
            pk = dh * (1 - 0.35 * i/ns)
            pts += f"L {bx:.0f} {by-pk:.0f} L {bx+(dx2-dx1)/ns*0.5:.0f} {by-pk*0.28:.0f} "
        pts += f"L {dx2:.0f} {topline(p['dorsal'][1]):.0f} Z"
        behind += f'<path d="{pts}" fill="{CREAM}"/>'
    else:
        midf  = (p["dorsal"][0] + p["dorsal"][1]) / 2
        tip_y = topline(midf) - dh
        behind += (f'<path d="M {dx1:.0f} {topline(p["dorsal"][0]):.0f} '
                   f'Q {lerp(X0,X1,midf):.0f} {tip_y:.0f} {dx2:.0f} {topline(p["dorsal"][1]):.0f} Z" fill="{CREAM}"/>')
        behind += fin_rays(dx1, topline(p["dorsal"][0]), dx2, tip_y, n=11)

    # anal fin
    af   = p.get("anal", (.62, .82))
    ax1, ax2 = lerp(X0,X1,af[0]), lerp(X0,X1,af[1])
    amid = (af[0]+af[1])/2
    ah   = p.get("analH", 42)
    atip_y = botline(amid) + ah
    behind += (f'<path d="M {ax1:.0f} {botline(af[0]):.0f} '
               f'Q {lerp(X0,X1,amid):.0f} {atip_y:.0f} {ax2:.0f} {botline(af[1]):.0f} Z" fill="{CREAM}"/>')
    behind += fin_rays(ax1, botline(af[0]), ax2, atip_y, n=6)

    # pectoral fin
    pcx = lerp(X0, X1, p.get("pecX", .30)); pcy = CY + p.get("pecY", 14)
    front += (f'<path d="M {pcx:.0f} {pcy-8:.0f} Q {pcx+70:.0f} {pcy+30:.0f} {pcx+8:.0f} {pcy+58:.0f} '
              f'Q {pcx-12:.0f} {pcy+24:.0f} {pcx:.0f} {pcy-8:.0f} Z" fill="{CREAM}"/>')
    for i in range(6):
        t = i/5
        sx = lerp(pcx, pcx+8, t); sy = lerp(pcy-8, pcy+58, t)
        ex = sx + 44*(1-t*0.5); ey = lerp(pcy+30, pcy+58, 0.15+t*0.5)
        front += f'<line x1="{sx:.0f}" y1="{sy:.0f}" x2="{ex:.0f}" y2="{ey:.0f}" stroke="{INK}" stroke-width="0.85" opacity="0.32"/>'

    # pelvic fin
    plx = lerp(X0, X1, p.get("pelX", .34)); ply = botline(p.get("pelX", .34))
    front += (f'<path d="M {plx:.0f} {ply-4:.0f} Q {plx+18:.0f} {ply+44:.0f} {plx-12:.0f} {ply+40:.0f} '
              f'Q {plx-16:.0f} {ply+12:.0f} {plx:.0f} {ply-4:.0f} Z" fill="{CREAM}"/>')

    # gill arc
    gx = lerp(X0, X1, .17)
    front += f'<path d="M {gx:.0f} {topline(.17)+10:.0f} Q {gx-20:.0f} {CY:.0f} {gx:.0f} {botline(.17)-10:.0f}" stroke-width="2.2" opacity=".55"/>'

    # barbels
    if p.get("barbels"):
        mx = X0 + 4; my = botline(.02) - 6
        for k in range(4):
            front += f'<path d="M {mx} {my} q {-30-k*8} {18+k*10} {-58-k*10} {30+k*16}" stroke-width="2.2" opacity=".7"/>'

    # adipose fin (catfish)
    if p.get("adipose"):
        behind += adipose(prof)

    texture      = hatch_lines(bid, prof) + scale_arcs(bid, prof)
    marks_clipped = p.get("marks_fn", lambda pr: "")(prof)
    ev = eye_at(lerp(X0, X1, p.get("eyeX", .12)), CY - p.get("eyeY", 6), p.get("eyeR", 13))
    return svg_doc(bid, body_d, texture, marks_clipped, front, ev, behind)

# ── flatfish (halibut) ────────────────────────────────────────────────────────

def flatfish(bid):
    prof   = [(.0,8,8),(.08,70,60),(.22,120,118),(.5,150,150),(.78,116,120),(.93,60,66),(1.0,16,18)]
    loop   = body_loop(prof); body_d = cr_closed(loop)
    topline = lambda f: CY - prof_top_at(prof, f)
    botline = lambda f: CY + prof_bot_at(prof, f)

    # dorsal + anal fringe
    fr = ""
    for i in range(38):
        f  = lerp(.07, .95, i/37)
        x  = lerp(X0, X1, f)
        ty = topline(f); by = botline(f)
        fr += f'<line x1="{x:.0f}" y1="{ty:.0f}" x2="{x:.0f}" y2="{ty-24:.0f}" stroke="{INK}" stroke-width="5" opacity=".55"/>'
        fr += f'<line x1="{x:.0f}" y1="{by:.0f}" x2="{x:.0f}" y2="{by+24:.0f}" stroke="{INK}" stroke-width="5" opacity=".55"/>'

    tail_g = f'<g fill="{CREAM}">{caudal("round", CY, 70, 120)}</g>'
    marks  = spots(prof, n=46, rmin=6, rmax=18, seed=11) + spots(prof, n=22, rmin=3, rmax=7, seed=5)
    mouth  = f'<path d="M {X0-2} {CY+6} q -26 4 -30 22 q 20 2 34 -6" fill="{CREAM}"/>'
    e1 = eye_at(lerp(X0, X1, .12), CY-34, 11)
    e2 = eye_at(lerp(X0, X1, .18), CY-12, 11)
    texture = hatch_lines(bid, prof) + scale_arcs(bid, prof)
    return svg_doc(bid, body_d, texture, marks, mouth+e1+e2, "", fr+tail_g)

# ── species registry ──────────────────────────────────────────────────────────

SPECIES = {
  "kelp-bass": lambda: standard(dict(id="kb", profile=FUSI,
      dorsal=(.26,.74), dorsalH=58, anal=(.62,.82), tail="fork", tailH=66,
      marks_fn=lambda pr: spots(pr,n=30,rmin=7,rmax=16,seed=4) + bars(pr,n=6,w=16,op=0.15))),

  "barred-sand-bass": lambda: standard(dict(id="sb", profile=FUSI,
      dorsal=(.26,.74), dorsalH=56, tail="fork", tailH=64,
      marks_fn=lambda pr: bars(pr,n=7,w=22,op=0.28) + spots(pr,n=10,rmin=4,rmax=8,seed=9))),

  "spotted-bay-bass": lambda: standard(dict(id="sp", profile=FUSI, eyeR=12,
      dorsal=(.26,.74), dorsalH=52, tail="fork", tailH=60,
      marks_fn=lambda pr: spots(pr,n=40,rmin=4,rmax=9,seed=2))),

  "largemouth-bass": lambda: standard(dict(id="lm", profile=FUSI, eyeX=.13,
      dorsal=(.28,.72), dorsalH=50, tail="fork", tailH=58, pecX=.28,
      marks_fn=lambda pr: blotches(pr,n=14,seed=6) + lateral(pr,yfrac=.5,op=.55,w=9))),

  "spotfin-croaker": lambda: standard(dict(id="sf", profile=ELON,
      dorsal=(.22,.5), dorsalH=46, anal=(.66,.82), tail="fork", tailH=58,
      marks_fn=lambda pr: (
          f'<ellipse cx="{lerp(X0,X1,.2):.0f}" cy="{CY+prof_bot_at(pr,.2)-26:.0f}" '
          f'rx="16" ry="22" fill="{INK}" opacity=".50"/>'
          + lateral(pr, yfrac=.42, op=.28, w=2)))),

  "california-corbina": lambda: standard(dict(id="co", profile=ELON, barbels=False,
      dorsal=(.2,.46), dorsalH=40, anal=(.66,.82), tail="fork", tailH=52, eyeX=.11,
      marks_fn=lambda pr: "".join(
          f'<path d="M {lerp(X0,X1,.2+i*.07):.0f} {CY-prof_top_at(pr,.2+i*.07)+8:.0f} l 38 56" '
          f'fill="none" stroke="{INK}" stroke-width="5" opacity=".20"/>' for i in range(8)))),

  "pacific-bonito": lambda: standard(dict(id="bo", profile=STREAM,
      dorsal=(.24,.4), dorsalH=44, spinyDorsal=False, anal=(.64,.76), tail="lunate", tailH=86, tailLen=160, eyeX=.1,
      marks_fn=lambda pr: "".join(
          f'<path d="M {lerp(X0,X1,.22+i*.07):.0f} {CY-prof_top_at(pr,.22+i*.07):.0f} l 68 32" '
          f'fill="none" stroke="{INK}" stroke-width="6" opacity=".42"/>' for i in range(8))
          + finlets(pr))),

  "pacific-mackerel": lambda: standard(dict(id="mk", profile=STREAM,
      dorsal=(.24,.36), dorsalH=38, spinyDorsal=False, anal=(.62,.72), tail="lunate", tailH=78, tailLen=150, eyeX=.1,
      marks_fn=lambda pr: wavy_bars(pr,n=11,op=0.40) + finlets(pr))),

  "barred-surfperch": lambda: standard(dict(id="su", profile=DEEP, eyeX=.12, eyeR=12,
      dorsal=(.24,.62), dorsalH=50, anal=(.6,.8), tail="fork", tailH=58,
      marks_fn=lambda pr: bars(pr,n=9,w=16,op=0.26) + lateral(pr,yfrac=.4,op=.22,w=2))),

  "opaleye": lambda: standard(dict(id="op", profile=DEEP, eyeX=.12, eyeR=12,
      dorsal=(.26,.66), dorsalH=46, anal=(.62,.8), tail="fork", tailH=56,
      marks_fn=lambda pr: (
          f'<circle cx="{lerp(X0,X1,.4):.0f}" cy="{CY-prof_top_at(pr,.4)+22:.0f}" r="12" fill="{CREAM}" opacity=".95"/>'
          f'<circle cx="{lerp(X0,X1,.52):.0f}" cy="{CY-prof_top_at(pr,.52)+20:.0f}" r="10" fill="{CREAM}" opacity=".90"/>'))),

  "california-sheephead": lambda: standard(dict(id="sh",
      profile=[(.0,14,16),(.06,78,52),(.14,118,86),(.3,120,116),(.55,104,108),(.8,60,66),(.93,32,36),(1.0,16,18)],
      eyeX=.1, eyeR=12, dorsal=(.24,.78), dorsalH=44, anal=(.62,.82), tail="round", tailH=70,
      marks_fn=lambda pr: (
          f'<path d="M {X0} {CY-120} L {lerp(X0,X1,.26):.0f} {CY-130} L {lerp(X0,X1,.26):.0f} {CY+130} L {X0} {CY+120} Z" fill="{INK}" opacity=".50"/>'
          f'<path d="M {lerp(X0,X1,.72):.0f} {CY-120} L {X1} {CY-60} L {X1} {CY+60} L {lerp(X0,X1,.72):.0f} {CY+120} Z" fill="{INK}" opacity=".50"/>'
          f'<path d="M {X0-4} {CY+40} q 60 40 130 36 l 0 30 q -80 6 -134 -22 Z" fill="{CREAM}" opacity=".85"/>'))),

  "black-crappie": lambda: standard(dict(id="cr",
      profile=[(.0,12,14),(.06,72,56),(.18,118,104),(.4,126,120),(.64,100,104),(.83,56,62),(.94,30,34),(1.0,16,18)],
      eyeX=.12, eyeR=14, dorsal=(.4,.74), dorsalH=58, anal=(.5,.78), analH=54, tail="fork", tailH=56,
      marks_fn=lambda pr: blotches(pr,n=22,seed=8))),

  "channel-catfish": lambda: standard(dict(id="cc",
      profile=[(.0,10,14),(.06,46,52),(.16,70,84),(.36,72,90),(.6,60,76),(.82,38,48),(.93,24,28),(1.0,12,14)],
      eyeX=.12, eyeR=10, barbels=True, adipose=True,
      dorsal=(.22,.34), dorsalH=44, anal=(.62,.84), analH=46, tail="fork", tailH=64, pecX=.22,
      marks_fn=lambda pr: spots(pr,n=22,rmin=4,rmax=8,seed=12))),

  "california-halibut": lambda: flatfish("hb"),
}

NAMES = {
  "kelp-bass":             ("Calico / Kelp Bass",        "Paralabrax clathratus"),
  "barred-sand-bass":      ("Barred Sand Bass",          "Paralabrax nebulifer"),
  "spotted-bay-bass":      ("Spotted Bay Bass",          "Paralabrax maculatofasciatus"),
  "largemouth-bass":       ("Largemouth Bass",           "Micropterus salmoides"),
  "spotfin-croaker":       ("Spotfin Croaker",           "Roncador stearnsii"),
  "california-corbina":    ("California Corbina",        "Menticirrhus undulatus"),
  "pacific-bonito":        ("Pacific Bonito",            "Sarda lineolata"),
  "pacific-mackerel":      ("Pacific Mackerel",          "Scomber japonicus"),
  "barred-surfperch":      ("Barred Surfperch",          "Amphistichus argenteus"),
  "opaleye":               ("Opaleye",                   "Girella nigricans"),
  "california-sheephead":  ("California Sheephead",      "Bodianus pulcher"),
  "black-crappie":         ("Black Crappie",             "Pomoxis nigromaculatus"),
  "channel-catfish":       ("Channel Catfish",           "Ictalurus punctatus"),
  "california-halibut":    ("California Halibut",        "Paralichthys californicus"),
}

def main():
    manifest_path = os.path.join(OUT, "manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        try: manifest = json.load(open(manifest_path))
        except: pass

    made, skipped = [], []
    for slug, build in SPECIES.items():
        svg_path = os.path.join(OUT, f"{slug}.svg")
        if os.path.exists(svg_path):
            skipped.append(slug); continue
        svg = build()
        open(svg_path, "w", encoding="utf-8").write(svg)
        nm, sci = NAMES.get(slug, (slug, ""))
        manifest[slug] = {"name": nm, "sci": sci, "file": f"{slug}.svg"}
        made.append(slug)

    json.dump(manifest, open(manifest_path, "w"), indent=2)
    print(f"generated ({len(made)}): {made}")
    print(f"skipped ({len(skipped)}): {skipped}")

if __name__ == "__main__":
    main()
