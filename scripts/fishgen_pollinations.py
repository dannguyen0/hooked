#!/usr/bin/env python3
"""
Generate accurate flat-lateral fish portraits via Pollinations.ai (free, no key).
Saves to images/fish/<slug>.png — skips any that already exist.

Usage:
  python scripts/fishgen_pollinations.py
  python scripts/fishgen_pollinations.py --overwrite   # re-generate all
  python scripts/fishgen_pollinations.py kelp-bass     # single species
"""

import json, os, sys, time, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPECIES_FILE = os.path.join(ROOT, "data", "species.json")
OUT_DIR      = os.path.join(ROOT, "images", "fish")

# Prompts engineered for flat 2D lateral accuracy.
# Common prefix enforces the side-view, illustration style, and clean background.
PREFIX = (
    "exact flat lateral side view, 2D scientific field guide illustration, "
    "accurate fish anatomy, facing left, isolated on pure white background, "
    "no shadow, no angle, no perspective distortion, "
)

PROMPTS = {
    "kelp-bass":
        PREFIX +
        "Calico kelp bass Paralabrax clathratus, mottled brown-olive-green body with "
        "irregular cream-white blotches and spots, spiny first dorsal fin, large mouth, "
        "slightly forked tail, precise scientific accuracy",

    "barred-sand-bass":
        PREFIX +
        "Barred sand bass Paralabrax nebulifer, pale grey-tan body with 8 irregular "
        "dark olive-brown vertical bars, mildly forked tail, third dorsal spine elongated, "
        "precise scientific accuracy",

    "spotted-bay-bass":
        PREFIX +
        "Spotted bay bass Paralabrax maculatofasciatus, olive-bronze body covered in "
        "distinct dark brown round spots, bluish-grey tinge on fins, precise scientific accuracy",

    "largemouth-bass":
        PREFIX +
        "Largemouth bass Micropterus salmoides, olive-green back fading to white belly, "
        "bold continuous dark black horizontal midline stripe, upper jaw extends past eye, "
        "notched dorsal fin, precise scientific accuracy",

    "spotfin-croaker":
        PREFIX +
        "Spotfin croaker Roncador stearnsii, silvery-grey metallic body, one large "
        "conspicuous black spot at pectoral fin base, underslung inferior mouth, "
        "high arched back, precise scientific accuracy",

    "california-corbina":
        PREFIX +
        "California corbina Menticirrhus undulatus, elongated silver-grey body with faint "
        "diagonal wavy lines, single short chin barbel below mouth, underslung mouth, "
        "low first dorsal fin, precise scientific accuracy",

    "pacific-bonito":
        PREFIX +
        "Pacific bonito Sarda lineolata, streamlined fusiform body, dark metallic blue-black "
        "back with 4-5 oblique diagonal dark stripes, silver sides, row of small finlets "
        "behind dorsal and anal fins, precise scientific accuracy",

    "pacific-mackerel":
        PREFIX +
        "Pacific mackerel Scomber japonicus, iridescent blue-green back with 25-30 "
        "wavy irregular dark zigzag lines, silver-white belly, streamlined body, "
        "row of small finlets, precise scientific accuracy",

    "barred-surfperch":
        PREFIX +
        "Barred surfperch Amphistichus argenteus, deep oval laterally compressed silver body, "
        "8-9 distinct brassy-yellow vertical bars on sides, reddish-orange fin tinge, "
        "precise scientific accuracy",

    "opaleye":
        PREFIX +
        "Opaleye Girella nigricans, deep oval dark olive-green body, one or two white "
        "spots at dorsal fin base, distinctive bright pale blue iridescent eyes, "
        "precise scientific accuracy",

    "california-sheephead":
        PREFIX +
        "Male California sheephead Bodianus pulcher, jet black head and posterior body, "
        "broad vivid rose-red mid-body band, white chin patch, prominent knobby forehead "
        "bump, large protruding canine teeth, precise scientific accuracy",

    "black-crappie":
        PREFIX +
        "Black crappie Pomoxis nigromaculatus, deep laterally compressed body, "
        "silver-green with irregular dark black speckles and mottling, large round "
        "fan-like dorsal fin with 7-8 spines, precise scientific accuracy",

    "channel-catfish":
        PREFIX +
        "Channel catfish Ictalurus punctatus, elongated cylindrical body, blue-grey "
        "with small scattered dark spots on sides, 8 long sensory barbels around mouth, "
        "deeply forked tail fin, adipose fin present, precise scientific accuracy",

    "california-halibut":
        PREFIX +
        "California halibut Paralichthys californicus eyed-side view, flat oval body, "
        "mottled brown-grey upper surface with pale blotches, large mouth with sharp teeth, "
        "both eyes visible on left topside, precise scientific accuracy",
}

BASE_URL = (
    "https://image.pollinations.ai/prompt/{prompt}"
    "?width=700&height=420&nologo=true&model=flux&transparent=true&seed={seed}"
)

def download(slug, prompt, overwrite=False, seed=42):
    out = os.path.join(OUT_DIR, f"{slug}.png")
    if os.path.exists(out) and not overwrite:
        print(f"  skip  {slug} (exists — use --overwrite to replace)")
        return True
    url = BASE_URL.format(prompt=urllib.parse.quote(prompt), seed=seed)
    print(f"  fetch {slug} ...", end=" ", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hooked-fishgen/1.0"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
        with open(out, "wb") as f:
            f.write(data)
        print(f"OK  ({len(data)//1024} KB)")
        return True
    except Exception as e:
        print(f"FAIL  {e}")
        return False

def main():
    overwrite = "--overwrite" in sys.argv
    targets = [a for a in sys.argv[1:] if not a.startswith("--")]
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(SPECIES_FILE) as f:
        species = json.load(f)["species"]

    slugs = targets if targets else [s for s in species if s in PROMPTS]
    missing = [s for s in species if s not in PROMPTS and s not in (targets or [])]
    if missing:
        print(f"Warning: no prompt for: {missing}")

    print(f"Generating {len(slugs)} fish image(s) via Pollinations.ai ...\n")
    ok = fail = 0
    for i, slug in enumerate(slugs):
        if slug not in PROMPTS:
            print(f"  skip  {slug} (no prompt defined)")
            continue
        if download(slug, PROMPTS[slug], overwrite, seed=42 + i):
            ok += 1
        else:
            fail += 1
        if i < len(slugs) - 1:
            time.sleep(2)

    print(f"\nDone: {ok} saved, {fail} failed.")
    if fail:
        print("Re-run with --overwrite to retry, or pass slug names to regenerate specific fish.")

if __name__ == "__main__":
    main()
