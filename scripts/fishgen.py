#!/usr/bin/env python3
"""fishgen.py — original field-guide-style side-view fish plates -> transparent PNG.
Keyed by slug; only renders species missing from the images dir (dedup)."""
import os, math, json, cairosvg

OUT = os.environ.get("FISH_OUT", "images/fish/vector")
os.makedirs(OUT, exist_ok=True)
W, H, CY = 1200, 520, 262
X0, X1 = 175, 1010                      # body span (snout -> peduncle)

def lerp(a, b, t): return a + (b - a) * t

def cr_closed(pts):
    """Catmull-Rom through a closed loop of points -> smooth SVG path."""
    n = len(pts); d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f} "
    for i in range(n):
        p0 = pts[(i - 1) % n]; p1 = pts[i]; p2 = pts[(i + 1) % n]; p3 = pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f"C {c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f} "
    return d + "Z"

def body_loop(profile):
    """profile: list of (frac, top_off, bot_off). Returns closed point loop."""
    top = [(lerp(X0, X1, f), CY - t) for f, t, b in profile]
    bot = [(lerp(X0, X1, f), CY + b) for f, t, b in profile]
    return top + bot[::-1]

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
    # rounded
    return (f'<path d="M {x-6} {py-depth*0.55} Q {x+length} {py-depth} {x+length} {py} '
            f'Q {x+length} {py+depth} {x-6} {py+depth*0.55} Q {x+22} {py} {x-6} {py-depth*0.55} Z" />')

def fin(d): return d

def rays(x1, y1, x2, y2, n, col):
    out = ""
    for i in range(n + 1):
        t = i / n
        out += f'<line x1="{lerp(x1,x2,t):.0f}" y1="{y1:.0f}" x2="{lerp(x1,x2,t):.0f}" y2="{y2:.0f}" stroke="{col}" stroke-width="2" opacity=".35"/>'
    return out

def svg_doc(defs, body_d, parts, eye, palette):
    bid = palette["id"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">
<defs>
<linearGradient id="g{bid}" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="{palette['dark']}"/>
<stop offset=".5" stop-color="{palette['mid']}"/>
<stop offset="1" stop-color="{palette['belly']}"/>
</linearGradient>
<clipPath id="c{bid}"><path d="{body_d}"/></clipPath>
{defs}
</defs>
<g stroke="{palette['line']}" stroke-width="2.5" stroke-linejoin="round">
{parts.get('behind','')}
<path d="{body_d}" fill="url(#g{bid})"/>
<g clip-path="url(#c{bid})" stroke="none">{parts.get('marks','')}</g>
<path d="{body_d}" fill="none"/>
{parts.get('front','')}
{eye}
</g></svg>'''

def eye_at(x, y, r=13, ring=None):
    ring = ring or "#0c0f10"
    return (f'<circle cx="{x}" cy="{y}" r="{r+3}" fill="none" stroke="{ring}" stroke-width="2.5"/>'
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="#0c1112" stroke="none"/>'
            f'<circle cx="{x-r*0.3}" cy="{y-r*0.3}" r="{r*0.32}" fill="#cfe0e2" stroke="none"/>')

# ---- standard fish builder -------------------------------------------------
def standard(p):
    prof = p["profile"]
    loop = body_loop(prof)
    body_d = cr_closed(loop)
    pal = p["palette"]
    # fin geometry
    backY = CY - prof_top_at(prof, p.get("dorsalX", .5))
    front = ""; behind = ""
    # dorsal
    dx1, dx2 = [lerp(X0, X1, f) for f in p.get("dorsal", (.30, .72))]
    dh = p.get("dorsalH", 60)
    topline = lambda f: CY - prof_top_at(prof, f)
    if p.get("spinyDorsal", True):
        pts = f"M {dx1} {topline(p['dorsal'][0])} "
        nspine = 7
        for i in range(nspine + 1):
            f = lerp(p["dorsal"][0], p["dorsal"][1], i / nspine)
            bx = lerp(X0, X1, f); by = topline(f)
            peak = dh * (1 - 0.4 * i / nspine)
            pts += f"L {bx} {by-peak} L {bx+ (dx2-dx1)/nspine*0.5} {by-peak*0.3} "
        pts += f"L {dx2} {topline(p['dorsal'][1])} Z"
        behind += f'<path d="{pts}" fill="{pal["fin"]}" opacity=".92"/>'
    else:
        midf = (p["dorsal"][0] + p["dorsal"][1]) / 2
        behind += (f'<path d="M {dx1} {topline(p["dorsal"][0])} '
                   f'Q {lerp(X0,X1,midf)} {topline(midf)-dh} {dx2} {topline(p["dorsal"][1])} Z" '
                   f'fill="{pal["fin"]}" opacity=".92"/>')
    # anal fin
    ax1, ax2 = [lerp(X0, X1, f) for f in p.get("anal", (.62, .82))]
    botline = lambda f: CY + prof_bot_at(prof, f)
    amid = (p.get("anal", (.62, .82))[0] + p.get("anal", (.62, .82))[1]) / 2
    ah = p.get("analH", 42)
    behind += (f'<path d="M {ax1} {botline(p.get("anal",(.62,.82))[0])} '
               f'Q {lerp(X0,X1,amid)} {botline(amid)+ah} {ax2} {botline(p.get("anal",(.62,.82))[1])} Z" '
               f'fill="{pal["fin"]}" opacity=".9"/>')
    # caudal
    behind += f'<g fill="{pal["fin"]}" opacity=".95">{caudal(p.get("tail","fork"), CY, p.get("tailH",70), p.get("tailLen",150))}</g>'
    # pectoral (in front of body)
    pcx = lerp(X0, X1, p.get("pecX", .30)); pcy = CY + p.get("pecY", 14)
    front += (f'<path d="M {pcx} {pcy-8} Q {pcx+70} {pcy+30} {pcx+8} {pcy+58} '
              f'Q {pcx-12} {pcy+24} {pcx} {pcy-8} Z" fill="{pal["fin2"]}" opacity=".85"/>')
    # pelvic
    plx = lerp(X0, X1, p.get("pelX", .34)); ply = CY + prof_bot_at(prof, p.get("pelX", .34))
    front += (f'<path d="M {plx} {ply-4} Q {plx+18} {ply+44} {plx-12} {ply+40} '
              f'Q {plx-16} {ply+12} {plx} {ply-4} Z" fill="{pal["fin2"]}" opacity=".8"/>')
    # gill line
    gx = lerp(X0, X1, .17)
    front += f'<path d="M {gx} {CY-prof_top_at(prof,.17)+10} Q {gx-18} {CY} {gx} {CY+prof_bot_at(prof,.17)-10}" fill="none" stroke="{pal["line"]}" stroke-width="2" opacity=".5"/>'
    # barbels
    if p.get("barbels"):
        mx = X0 + 4; my = CY + prof_bot_at(prof, .02) - 6
        for k in range(4):
            front += f'<path d="M {mx} {my} q {-30-k*8} {18+k*10} {-58-k*10} {30+k*16}" fill="none" stroke="{pal["line"]}" stroke-width="2.4" opacity=".75"/>'
    marks = p.get("marks_fn", lambda prof: "")(prof)
    eye = eye_at(lerp(X0, X1, p.get("eyeX", .12)), CY - p.get("eyeY", 6), p.get("eyeR", 13), p.get("eyeRing"))
    return svg_doc(p.get("defs", ""), body_d, {"behind": behind, "front": front, "marks": marks}, eye, pal)

def prof_top_at(prof, f):
    for i in range(len(prof) - 1):
        if prof[i][0] <= f <= prof[i + 1][0]:
            t = (f - prof[i][0]) / (prof[i + 1][0] - prof[i][0])
            return lerp(prof[i][1], prof[i + 1][1], t)
    return prof[-1][1]

def prof_bot_at(prof, f):
    for i in range(len(prof) - 1):
        if prof[i][0] <= f <= prof[i + 1][0]:
            t = (f - prof[i][0]) / (prof[i + 1][0] - prof[i][0])
            return lerp(prof[i][2], prof[i + 1][2], t)
    return prof[-1][2]

# ---- marking helpers (run inside clip) ------------------------------------
def spots(prof, color, n=26, rmin=5, rmax=12, seed=7, y0=.15, y1=.85):
    import random; random.seed(seed); out = ""
    for _ in range(n):
        f = random.uniform(.18, .92)
        x = lerp(X0, X1, f)
        top = CY - prof_top_at(prof, f); bot = CY + prof_bot_at(prof, f)
        y = lerp(top, bot, random.uniform(y0, y1))
        r = random.uniform(rmin, rmax)
        out += f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.0f}" fill="{color}" opacity="{random.uniform(.5,.85):.2f}"/>'
    return out

def bars(prof, color, n=7, w=18, op=.3):
    out = ""
    for i in range(n):
        f = lerp(.22, .8, i / (n - 1)); x = lerp(X0, X1, f)
        top = CY - prof_top_at(prof, f) + 6; bot = CY + prof_bot_at(prof, f) - 6
        out += f'<rect x="{x-w/2:.0f}" y="{top:.0f}" width="{w}" height="{bot-top:.0f}" fill="{color}" opacity="{op}"/>'
    return out

def wavy_bars(prof, color, n=9, op=.4):
    out = ""
    for i in range(n):
        f = lerp(.2, .82, i / (n - 1)); x = lerp(X0, X1, f)
        top = CY - prof_top_at(prof, f) + 4
        out += f'<path d="M {x:.0f} {top:.0f} q 22 12 10 30 q -14 16 6 30" fill="none" stroke="{color}" stroke-width="6" opacity="{op}"/>'
    return out

def lateral(prof, color, f0=.18, f1=.95, yfrac=.42, op=.4, w=3):
    pts = []
    for i in range(20):
        f = lerp(f0, f1, i / 19); x = lerp(X0, X1, f)
        top = CY - prof_top_at(prof, f); bot = CY + prof_bot_at(prof, f)
        pts.append(f"{x:.0f} {lerp(top,bot,yfrac):.0f}")
    return f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="{w}" opacity="{op}"/>'

def blotches(prof, color, n=18, seed=3):
    import random; random.seed(seed); out = ""
    for _ in range(n):
        f = random.uniform(.2, .9); x = lerp(X0, X1, f)
        top = CY - prof_top_at(prof, f); bot = CY + prof_bot_at(prof, f)
        y = lerp(top, bot, random.uniform(.1, .9))
        rx = random.uniform(10, 26); ry = random.uniform(8, 18)
        out += f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{rx:.0f}" ry="{ry:.0f}" fill="{color}" opacity="{random.uniform(.4,.7):.2f}"/>'
    return out

# ---- special: flatfish (halibut) ------------------------------------------
def flatfish(p):
    pal = p["palette"]
    prof = [(.0,8,8),(.08,70,60),(.22,120,118),(.5,150,150),(.78,116,120),(.93,60,66),(1.0,16,18)]
    loop = body_loop(prof); body_d = cr_closed(loop)
    # long dorsal/anal fringe
    fr = ""
    for edge, sgn in (("top", -1), ("bot", 1)):
        prev = None
        for i in range(40):
            f = lerp(.07, .95, i / 39); x = lerp(X0, X1, f)
            yy = CY + sgn * (prof_top_at(prof, f) if edge == "top" else prof_bot_at(prof, f))
            fr += f'<line x1="{x:.0f}" y1="{yy:.0f}" x2="{x:.0f}" y2="{yy+sgn*26:.0f}" stroke="{pal["fin"]}" stroke-width="6" opacity=".8"/>'
    tail = f'<g fill="{pal["fin"]}" opacity=".95">{caudal("round", CY, 70, 120)}</g>'
    marks = spots(prof, pal["spot"], n=46, rmin=6, rmax=18, seed=11) + spots(prof, "#22150a", n=22, rmin=3, rmax=7, seed=5)
    # two eyes on top-left (eyed side up)
    e1 = eye_at(lerp(X0, X1, .12), CY - 34, 11)
    e2 = eye_at(lerp(X0, X1, .18), CY - 12, 11)
    mouth = f'<path d="M {X0-2} {CY+6} q -26 4 -30 22 q 20 2 34 -6" fill="{pal["mid"]}" stroke="{pal["line"]}" stroke-width="2"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}">
<defs><linearGradient id="g{pal['id']}" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="{pal['dark']}"/><stop offset="1" stop-color="{pal['mid']}"/></linearGradient>
<clipPath id="c{pal['id']}"><path d="{body_d}"/></clipPath></defs>
<g stroke="{pal['line']}" stroke-width="2.5" stroke-linejoin="round">
{fr}{tail}
<path d="{body_d}" fill="url(#g{pal['id']})"/>
<g clip-path="url(#c{pal['id']})" stroke="none">{marks}</g>
<path d="{body_d}" fill="none"/>
{mouth}{e1}{e2}</g></svg>'''

# ===========================================================================
# SPECIES
# ===========================================================================
def P(id, dark, mid, belly, fin, fin2, line, spot=None):
    return dict(id=id, dark=dark, mid=mid, belly=belly, fin=fin, fin2=fin2, line=line, spot=spot or mid)

FUSI = [(.0,10,12),(.07,46,40),(.18,82,72),(.38,96,88),(.62,84,80),(.82,52,54),(.93,30,34),(1.0,16,18)]
DEEP = [(.0,12,14),(.07,70,58),(.2,118,104),(.42,128,120),(.66,104,104),(.84,60,66),(.94,32,36),(1.0,16,18)]
ELON = [(.0,8,12),(.08,44,40),(.22,62,58),(.45,64,62),(.68,56,56),(.85,38,40),(.94,24,26),(1.0,12,14)]
STREAM=[(.0,8,10),(.08,40,36),(.22,66,58),(.45,70,62),(.68,54,50),(.84,34,32),(.93,22,22),(1.0,12,12)]

SPECIES = {
 "kelp-bass": lambda: standard(dict(profile=FUSI,
    palette=P("kb","#54562a","#7c7d44","#c8c79a","#494a28","#6f7040","#23230f"),
    dorsal=(.26,.74), dorsalH=58, anal=(.66,.82), tail="fork", tailH=66,
    marks_fn=lambda pr: spots(pr, "#d8d6a6", n=30, rmin=7, rmax=16, seed=4) + bars(pr,"#3c3d1c",6,16,.18))),
 "barred-sand-bass": lambda: standard(dict(profile=FUSI,
    palette=P("sb","#6c6750","#928c6d","#cfc9ad","#5e5942","#7d7860","#2a281c"),
    dorsal=(.26,.74), dorsalH=56, tail="fork", tailH=64,
    marks_fn=lambda pr: bars(pr,"#403c28",7,22,.32)+spots(pr,"#403c28",n=10,rmin=4,rmax=8,seed=9))),
 "spotted-bay-bass": lambda: standard(dict(profile=FUSI,
    palette=P("sp","#5f6038","#84855a","#c6c79c","#52522f","#70714a","#262712"), eyeR=12,
    dorsal=(.26,.74), dorsalH=52, tail="fork", tailH=60,
    marks_fn=lambda pr: spots(pr,"#2e2f15",n=40,rmin=4,rmax=9,seed=2))),
 "largemouth-bass": lambda: standard(dict(profile=FUSI,
    palette=P("lm","#42613a","#6f8a52","#cdd1a6","#3c5232","#5f7848","#1d2a16"), eyeX=.13,
    dorsal=(.28,.72), dorsalH=50, tail="fork", tailH=58, pecX=.28,
    marks_fn=lambda pr: blotches(pr,"#2c3a1f",n=14,seed=6)+lateral(pr,"#283a1c",.16,.95,.5,.55,9))),
 "spotfin-croaker": lambda: standard(dict(profile=ELON,
    palette=P("sf","#7e8890","#a7b0b5","#e2e6e6","#6b757c","#8b9499","#2b3236"),
    dorsal=(.22,.5), dorsalH=46, anal=(.66,.82), tail="fork", tailH=58, spinyDorsal=True,
    marks_fn=lambda pr: f'<ellipse cx="{lerp(X0,X1,.2):.0f}" cy="{CY+prof_bot_at(pr,.2)-26:.0f}" rx="16" ry="22" fill="#10151a" opacity=".85"/>'+lateral(pr,"#5a646a",.18,.95,.42,.3,2))),
 "california-corbina": lambda: standard(dict(profile=ELON,
    palette=P("co","#7c858c","#a3acb1","#e0e4e4","#6a737a","#889196","#2c3236"), barbels=False,
    dorsal=(.2,.46), dorsalH=40, anal=(.66,.82), tail="fork", tailH=52, eyeX=.11,
    marks_fn=lambda pr: "".join(f'<path d="M {lerp(X0,X1,.2+i*.07):.0f} {CY-prof_top_at(pr,.2+i*.07)+8:.0f} l 40 60" stroke="#5b656b" stroke-width="5" opacity=".22" fill="none"/>' for i in range(8)))),
 "pacific-bonito": lambda: standard(dict(profile=STREAM,
    palette=P("bo","#2f4f6e","#5f7f9a","#d2dadd","#27435e","#4a6a85","#16202b"),
    dorsal=(.24,.4), dorsalH=44, anal=(.64,.76), tail="lunate", tailH=86, tailLen=160, eyeX=.1,
    marks_fn=lambda pr: "".join(f'<path d="M {lerp(X0,X1,.22+i*.07):.0f} {CY-prof_top_at(pr,.22+i*.07):.0f} l 70 34" stroke="#16202b" stroke-width="6" opacity=".5" fill="none"/>' for i in range(8)) + finlets(pr))),
 "pacific-mackerel": lambda: standard(dict(profile=STREAM,
    palette=P("mk","#2f5650","#5c8079","#d6dedb","#27463f","#48685f","#15211d"),
    dorsal=(.24,.36), dorsalH=38, anal=(.62,.72), tail="lunate", tailH=78, tailLen=150, eyeX=.1,
    marks_fn=lambda pr: wavy_bars(pr,"#15211d",11,.5)+finlets(pr))),
 "barred-surfperch": lambda: standard(dict(profile=DEEP,
    palette=P("su","#8f989c","#b6bdbe","#e6e8e6","#9aa0a0","#c2a98f","#33383a"), eyeX=.12, eyeR=12,
    dorsal=(.24,.62), dorsalH=50, anal=(.6,.8), tail="fork", tailH=58, spinyDorsal=True,
    marks_fn=lambda pr: bars(pr,"#7a6b52",9,16,.3)+lateral(pr,"#6f777a",.18,.94,.4,.25,2))),
 "opaleye": lambda: standard(dict(profile=DEEP,
    palette=P("op","#33442f","#506446","#9aaa86","#2c3a28","#475a3d","#172013"),
    eyeRing="#3a73c0", eyeX=.12, eyeR=12, dorsal=(.26,.66), dorsalH=46, anal=(.62,.8), tail="fork", tailH=56,
    marks_fn=lambda pr: f'<circle cx="{lerp(X0,X1,.4):.0f}" cy="{CY-prof_top_at(pr,.4)+22:.0f}" r="11" fill="#e8efe2" opacity=".9"/><circle cx="{lerp(X0,X1,.52):.0f}" cy="{CY-prof_top_at(pr,.52)+20:.0f}" r="9" fill="#e8efe2" opacity=".85"/>')),
 "california-sheephead": lambda: standard(dict(profile=[(.0,14,16),(.06,78,52),(.14,118,86),(.3,120,116),(.55,104,108),(.8,60,66),(.93,32,36),(1.0,16,18)],
    palette=P("sh","#7a1f24","#a83b33","#d98a6a","#5a161a","#7a2520","#2a0a0c"), eyeX=.1, eyeR=12,
    dorsal=(.24,.78), dorsalH=44, anal=(.62,.82), tail="round", tailH=70,
    marks_fn=lambda pr: (
      f'<path d="M {X0} {CY-120} L {lerp(X0,X1,.26)} {CY-130} L {lerp(X0,X1,.26)} {CY+130} L {X0} {CY+120} Z" fill="#1a1012" opacity=".82"/>'
      f'<path d="M {lerp(X0,X1,.72)} {CY-120} L {X1} {CY-60} L {X1} {CY+60} L {lerp(X0,X1,.72)} {CY+120} Z" fill="#1a1012" opacity=".82"/>'
      f'<path d="M {X0-4} {CY+40} q 60 40 130 36 l 0 30 q -80 6 -134 -22 Z" fill="#eadfce" opacity=".9"/>'))),
 "black-crappie": lambda: standard(dict(profile=[(.0,12,14),(.06,72,56),(.18,118,104),(.4,126,120),(.64,100,104),(.83,56,62),(.94,30,34),(1.0,16,18)],
    palette=P("cr","#6e7560","#969c80","#d6dbc4","#5f6552","#7e856b","#23271c"), eyeX=.12, eyeR=14,
    dorsal=(.4,.74), dorsalH=58, anal=(.5,.78), analH=54, tail="fork", tailH=56, spinyDorsal=True,
    marks_fn=lambda pr: blotches(pr,"#1f2417",n=22,seed=8))),
 "channel-catfish": lambda: standard(dict(profile=[(.0,10,14),(.06,46,52),(.16,70,84),(.36,72,90),(.6,60,76),(.82,38,48),(.93,24,28),(1.0,12,14)],
    palette=P("cc","#5d6358","#838877","#cdd0bd","#565b50","#727767","#222419"), eyeX=.12, eyeR=10,
    barbels=True, dorsal=(.22,.34), dorsalH=44, anal=(.62,.84), analH=46, tail="fork", tailH=64, pecX=.22,
    marks_fn=lambda pr: spots(pr,"#262920",n=22,rmin=4,rmax=8,seed=12)+adipose(pr))),
}

def finlets(prof):
    out = ""
    for i in range(5):
        f = lerp(.78, .96, i / 4); x = lerp(X0, X1, f)
        out += f'<path d="M {x:.0f} {CY-prof_top_at(prof,f):.0f} l 14 -10 l 2 10 Z" fill="#16202b" opacity=".7"/>'
        out += f'<path d="M {x:.0f} {CY+prof_bot_at(prof,f):.0f} l 14 10 l 2 -10 Z" fill="#16202b" opacity=".7"/>'
    return out

def adipose(prof):
    f = .58; x = lerp(X0, X1, f); y = CY - prof_top_at(prof, f)
    return f'<path d="M {x} {y} q 40 -18 70 -2 l -4 12 q -34 -8 -66 4 Z" fill="#565b50" opacity=".9"/>'

FLATS = {
 "california-halibut": lambda: flatfish(dict(palette=P("hb","#5a4a32","#8a7553","#b59c74","#4a3c28","#6a5840","#241a0e", spot="#3a2c18"))),
}

NAMES = {
 "kelp-bass":("Calico / Kelp Bass","Paralabrax clathratus"),
 "barred-sand-bass":("Barred Sand Bass","Paralabrax nebulifer"),
 "spotted-bay-bass":("Spotted Bay Bass","Paralabrax maculatofasciatus"),
 "largemouth-bass":("Largemouth Bass","Micropterus salmoides"),
 "spotfin-croaker":("Spotfin Croaker","Roncador stearnsii"),
 "california-corbina":("California Corbina","Menticirrhus undulatus"),
 "pacific-bonito":("Pacific Bonito","Sarda lineolata"),
 "pacific-mackerel":("Pacific Mackerel","Scomber japonicus"),
 "barred-surfperch":("Barred Surfperch","Amphistichus argenteus"),
 "opaleye":("Opaleye","Girella nigricans"),
 "california-sheephead":("California Sheephead","Bodianus pulcher"),
 "black-crappie":("Black Crappie","Pomoxis nigromaculatus"),
 "channel-catfish":("Channel Catfish","Ictalurus punctatus"),
 "california-halibut":("California Halibut","Paralichthys californicus"),
}

def main():
    builders = {**SPECIES, **FLATS}
    manifest_path = os.path.join(OUT, "manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        manifest = json.load(open(manifest_path))
    made, skipped = [], []
    for slug, build in builders.items():
        png = os.path.join(OUT, f"{slug}.png")
        if os.path.exists(png):                 # dedup: only generate missing
            skipped.append(slug); continue
        svg = build()
        open(os.path.join(OUT, f"{slug}.svg"), "w").write(svg)
        cairosvg.svg2png(bytestring=svg.encode(), write_to=png, output_width=900, output_height=390)
        nm, sci = NAMES.get(slug, (slug, ""))
        manifest[slug] = {"name": nm, "sci": sci, "file": f"{slug}.png"}
        made.append(slug)
    json.dump(manifest, open(manifest_path, "w"), indent=2)
    print("generated:", made)
    print("skipped (already had):", skipped)

if __name__ == "__main__":
    main()
