#!/usr/bin/env python3
"""
Enrich spots with species data using Claude API.

For each spot in locations.json that has few or no fish entries, asks Claude
to research what can be caught there, then:
  1. Updates locations.json fish[] arrays
  2. Adds new entries to species.json
  3. Generates images via Pollinations for any new species
  4. Runs rembg background removal on new images

Usage:
  python scripts/enrich_spots.py                    # enrich all spots missing species
  python scripts/enrich_spots.py newport corona     # enrich specific spot IDs
  python scripts/enrich_spots.py --all              # re-enrich all spots
  python scripts/enrich_spots.py --dry-run          # print what would change, no writes

Requires: pip install anthropic
API key:  set ANTHROPIC_API_KEY=sk-ant-... in your environment
"""

import json, os, sys, time, re, subprocess
import urllib.request, urllib.parse

ROOT         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCATIONS    = os.path.join(ROOT, "data", "locations.json")
SPECIES_FILE = os.path.join(ROOT, "data", "species.json")
FISH_IMG_DIR = os.path.join(ROOT, "images", "fish")

try:
    import anthropic
except ImportError:
    print("Missing dep. Run:  pip install anthropic")
    sys.exit(1)

SYSTEM_PROMPT = """You are an expert Southern California fishing guide with deep knowledge of
species identification, tackle, regulations, and local spots.

When given a fishing spot you return a JSON object (no markdown, raw JSON only) with this schema:

{
  "fish": [
    {
      "slug": "string — url-safe kebab-case, unique species identifier",
      "n": "string — common name (use the most widely-recognised local name)",
      "s": "string — scientific name",
      "tide": "incoming|outgoing|any",
      "light": "dawn|dusk|night|day|any",
      "note": "string — one-sentence spot-specific fishing note",
      "cast": "string — where/how to cast at this type of location (1-2 sentences)",
      "depth": "string — target depth range e.g. '5-30 ft'",
      "regs": {
        "size": "string — California CDFW minimum size or 'No minimum'",
        "bag": "string — daily bag limit",
        "season": "string — open season or 'Year-round'"
      },
      "rigs": [
        {"name": "string", "detail": "string — 2-3 sentences, be specific about sizes/weights", "line": "string — lb class e.g. '20 lb fluoro'"},
        {"name": "string", "detail": "string", "line": "string"},
        {"name": "string", "detail": "string", "line": "string"}
      ]
    }
  ]
}

Rules:
- Return 4-6 species most commonly caught at this type of spot in SoCal
- rigs array must have EXACTLY 3 entries, ordered best-first
- Do NOT invent regulations — use verified CDFW rules or write "Verify CDFW regs before fishing"
- slugs must be unique across all species (use genus if needed e.g. "white-seabass" not "seabass")
- For freshwater spots use freshwater species relevant to SoCal lakes/reservoirs
- Return raw JSON only, no markdown fences, no commentary"""

USER_PROMPT_TMPL = """Fishing spot details:
Name: {name}
Latitude: {lat}
Longitude: {lon}
Water type: {water}
Tags: {tags}
Notes: {notes}

What are the top 4-6 fish species a SoCal angler would target at this spot?
Return the JSON object described in your instructions."""


def ask_claude(client, spot):
    notes = []
    if spot.get("water") == "fresh":
        notes.append("freshwater lake/reservoir fishing")
    if "Surf" in spot.get("tags", []):
        notes.append("surf fishing spot")
    if "Pier" in spot.get("tags", []):
        notes.append("pier/dock fishing")
    if "Kelp" in spot.get("tags", []):
        notes.append("kelp beds present")

    prompt = USER_PROMPT_TMPL.format(
        name=spot["name"],
        lat=spot["lat"],
        lon=spot["lon"],
        water=spot.get("water", "salt"),
        tags=", ".join(spot.get("tags", [])),
        notes="; ".join(notes) if notes else "general inshore spot",
    )
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()
    # Strip any accidental markdown fences
    raw = re.sub(r'^```[a-z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    return json.loads(raw)


def generate_image(slug, species_info, overwrite=False):
    """Generate Pollinations image for a slug that has no PNG yet."""
    out = os.path.join(FISH_IMG_DIR, f"{slug}.png")
    if os.path.exists(out) and not overwrite:
        return True

    name = species_info.get("n", slug)
    sci  = species_info.get("s", "")
    PREFIX = (
        "exact flat lateral side view, 2D scientific field guide illustration, "
        "accurate fish anatomy, facing left, isolated on pure white background, "
        "no shadow, no angle, no perspective distortion, "
    )
    prompt = f"{PREFIX}{name} {sci}, precise scientific accuracy"
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(prompt)
        + "?width=700&height=420&nologo=true&model=flux&seed=42"
    )
    print(f"      image: generating {slug} ...", end=" ", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hooked-enrich/1.0"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
        os.makedirs(FISH_IMG_DIR, exist_ok=True)
        with open(out, "wb") as f:
            f.write(data)
        print(f"OK ({len(data)//1024} KB)")
        return True
    except Exception as e:
        print(f"FAIL {e}")
        return False


def remove_bg(slug):
    """Run rembg on an image to make background transparent."""
    out = os.path.join(FISH_IMG_DIR, f"{slug}.png")
    if not os.path.exists(out):
        return
    try:
        from rembg import remove as rembg_remove
        from PIL import Image
        import io
        print(f"      rembg:  {slug} ...", end=" ", flush=True)
        with open(out, "rb") as f:
            result = rembg_remove(f.read())
        img = Image.open(io.BytesIO(result)).convert("RGBA")
        img.save(out, "PNG")
        print("OK")
    except ImportError:
        print(f"      rembg:  skip {slug} (pip install rembg to enable)")
    except Exception as e:
        print(f"      rembg:  FAIL {e}")


def enrich_spot(spot, existing_species, dry_run=False):
    """Return (updated_fish_list, new_species_dict) for a spot."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  ERROR: set ANTHROPIC_API_KEY in environment")
        return None, {}

    client = anthropic.Anthropic(api_key=api_key)
    print(f"  researching '{spot['name']}' via Claude ...", flush=True)
    try:
        data = ask_claude(client, spot)
    except Exception as e:
        print(f"  FAIL: {e}")
        return None, {}

    fish_list = []
    new_species = {}
    for f in data.get("fish", []):
        slug = f["slug"]
        fish_list.append({
            "slug": slug,
            "tide":  f.get("tide", "any"),
            "light": f.get("light", "any"),
            "note":  f.get("note", ""),
        })
        if slug not in existing_species:
            new_species[slug] = {
                "n":     f["n"],
                "s":     f.get("s", ""),
                "cast":  f.get("cast", ""),
                "depth": f.get("depth", ""),
                "rigs":  f.get("rigs", []),
            }
            if "regs" in f:
                new_species[slug]["regs"] = f["regs"]
            if "note" in f:
                new_species[slug]["note"] = f.get("note", "")

    return fish_list, new_species


def main():
    overwrite_all = "--all" in sys.argv
    dry_run       = "--dry-run" in sys.argv
    targets       = [a for a in sys.argv[1:] if not a.startswith("--")]

    with open(LOCATIONS) as f:
        loc_data = json.load(f)
    with open(SPECIES_FILE) as f:
        sp_data = json.load(f)

    locations  = loc_data["locations"]
    species_db = sp_data["species"]

    to_enrich = []
    for loc in locations:
        if targets and loc["id"] not in targets:
            continue
        if overwrite_all or not loc.get("fish") or len(loc.get("fish", [])) < 2:
            to_enrich.append(loc)

    if not to_enrich:
        print("No spots need enrichment. Use --all to re-enrich everything.")
        return

    print(f"\nEnriching {len(to_enrich)} spot(s) ...\n")
    any_changed = False
    new_image_slugs = []

    for i, spot in enumerate(to_enrich):
        fish_list, new_species = enrich_spot(spot, species_db, dry_run)
        if fish_list is None:
            continue

        for slug, sp_info in new_species.items():
            print(f"    + new species: {slug} ({sp_info['n']})")

        if dry_run:
            print(f"  [dry-run] would set {spot['id']}.fish = {[f['slug'] for f in fish_list]}")
            print(f"  [dry-run] would add species: {list(new_species.keys())}")
            continue

        # Update locations.json
        for loc in loc_data["locations"]:
            if loc["id"] == spot["id"]:
                loc["fish"] = fish_list
                break

        # Update species.json
        species_db.update(new_species)
        new_image_slugs.extend(new_species.keys())
        any_changed = True

        if i < len(to_enrich) - 1:
            time.sleep(1)  # be polite to API

    if not any_changed:
        print("Nothing written.")
        return

    # Write updated JSON
    with open(LOCATIONS, "w") as f:
        json.dump(loc_data, f, indent=2, ensure_ascii=False)
    with open(SPECIES_FILE, "w") as f:
        json.dump(sp_data, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {LOCATIONS}")
    print(f"Wrote {SPECIES_FILE}")

    # Generate + de-background images for new species
    if new_image_slugs:
        print(f"\nGenerating images for {len(new_image_slugs)} new species ...\n")
        for j, slug in enumerate(new_image_slugs):
            generate_image(slug, species_db.get(slug, {}))
            remove_bg(slug)
            if j < len(new_image_slugs) - 1:
                time.sleep(2)

    print("\nDone. Review changes, then commit:\n")
    print("  git add data/ images/fish/")
    print("  git commit -m 'Enrich spots with researched species data'")
    print("  git push origin master\n")


if __name__ == "__main__":
    main()
