#!/usr/bin/env python3
"""
Generate photoreal fish images via Pollinations.ai (free, no API key).
Saves to images/fish/<slug>.png — skips any that already exist.

Usage:
  python scripts/fishgen_pollinations.py
  python scripts/fishgen_pollinations.py --overwrite   # re-generate all
"""

import json, os, sys, time, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPECIES_FILE = os.path.join(ROOT, "data", "species.json")
OUT_DIR      = os.path.join(ROOT, "images", "fish")

# Species-specific prompts — each one encodes diagnostic visual features
# so the model produces an accurate, ID-correct fish portrait.
PROMPTS = {
    "kelp-bass":
        "Calico kelp bass Paralabrax clathratus, mottled brown-green irregular pale patches, "
        "spiny dorsal fin, slightly compressed body, mouth large, lateral view, "
        "photorealistic fish portrait, pure white background, studio lighting, high detail",

    "barred-sand-bass":
        "Barred sand bass Paralabrax nebulifer, pale olive-grey with 8-9 irregular dark vertical "
        "bars, slightly forked tail, lateral view, photorealistic fish portrait, "
        "pure white background, studio lighting, high detail",

    "spotted-bay-bass":
        "Spotted bay bass Paralabrax maculatofasciatus, olive-brown with irregular dark brown spots "
        "covering body, blue-grey fins, lateral view, photorealistic fish portrait, "
        "pure white background, studio lighting, high detail",

    "largemouth-bass":
        "Largemouth bass Micropterus salmoides, olive-green back fading to white belly, "
        "bold black horizontal lateral stripe, large upturned mouth extending past eye, "
        "lateral view, photorealistic fish portrait, pure white background, studio lighting",

    "spotfin-croaker":
        "Spotfin croaker Roncador stearnsii, silver-grey metallic body, large black spot at base "
        "of pectoral fin, underslung mouth, lateral view, photorealistic fish portrait, "
        "pure white background, studio lighting, high detail",

    "california-corbina":
        "California corbina Menticirrhus undulatus, elongated silver-grey body with faint diagonal "
        "wavy markings, single short chin barbel, small underslung mouth, low first dorsal spine, "
        "lateral view, photorealistic fish portrait, pure white background, studio lighting",

    "pacific-bonito":
        "Pacific bonito Sarda lineolata, streamlined torpedo body, blue-black back with 4-5 "
        "oblique dark stripes, silver metallic sides, small finlets behind dorsal, "
        "lateral view, photorealistic fish portrait, pure white background, studio lighting",

    "pacific-mackerel":
        "Pacific mackerel Scomber japonicus, iridescent blue-green back with 25-30 wavy dark "
        "zigzag lines, silver belly, streamlined body, small finlets, lateral view, "
        "photorealistic fish portrait, pure white background, studio lighting, high detail",

    "barred-surfperch":
        "Barred surfperch Amphistichus argenteus, deep oval compressed body, silver with 8-9 "
        "brassy-yellow vertical bars, reddish-orange tinge on fins, lateral view, "
        "photorealistic fish portrait, pure white background, studio lighting",

    "opaleye":
        "Opaleye Girella nigricans, deep oval dark olive-green body, one or two white spots "
        "near dorsal fin base, striking pale blue iridescent eyes, lateral view, "
        "photorealistic fish portrait, pure white background, studio lighting, high detail",

    "california-sheephead":
        "California sheephead male Bodianus pulcher, jet black head and rear body, vivid "
        "rose-red midsection band, white chin patch, bulging knobby forehead, large teeth, "
        "lateral view, photorealistic fish portrait, pure white background, studio lighting",

    "black-crappie":
        "Black crappie Pomoxis nigromaculatus, deep laterally compressed body, silver-green with "
        "irregular black speckles and mottling, large fan-like dorsal fin, lateral view, "
        "photorealistic fish portrait, pure white background, studio lighting, high detail",

    "channel-catfish":
        "Channel catfish Ictalurus punctatus, elongated cylindrical body, blue-grey back with "
        "small scattered dark spots on sides, 8 long sensory barbels around mouth, deeply "
        "forked tail, lateral view, photorealistic fish portrait, pure white background, studio lighting",

    "california-halibut":
        "California halibut Paralichthys californicus, flat oval body with both eyes on left "
        "topside, mottled brown-grey upper surface, white underside visible, large mouth with teeth, "
        "angled dorsal view showing eyed side, photorealistic fish portrait, "
        "pure white background, studio lighting, high detail",
}

BASE_URL = "https://image.pollinations.ai/prompt/{prompt}?width=600&height=400&nologo=true&model=flux"

def download(slug, prompt, overwrite=False):
    out = os.path.join(OUT_DIR, f"{slug}.png")
    if os.path.exists(out) and not overwrite:
        print(f"  skip  {slug} (already exists)")
        return True
    url = BASE_URL.format(prompt=urllib.parse.quote(prompt))
    print(f"  fetch {slug} …", end=" ", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hooked-fishgen/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        with open(out, "wb") as f:
            f.write(data)
        print(f"✓  ({len(data)//1024} KB)")
        return True
    except Exception as e:
        print(f"✗  {e}")
        return False

def main():
    overwrite = "--overwrite" in sys.argv
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(SPECIES_FILE) as f:
        species = json.load(f)["species"]

    slugs = [s for s in species if s in PROMPTS]
    missing = [s for s in species if s not in PROMPTS]
    if missing:
        print(f"Warning: no prompt for {missing}")

    print(f"Generating {len(slugs)} fish images via Pollinations.ai …\n")
    ok = fail = 0
    for slug in slugs:
        if download(slug, PROMPTS[slug], overwrite):
            ok += 1
        else:
            fail += 1
        time.sleep(1.5)   # be polite — free service

    print(f"\nDone: {ok} saved, {fail} failed.")
    if fail:
        print("Re-run with --overwrite to retry failed images.")

if __name__ == "__main__":
    main()
