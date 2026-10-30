#!/usr/bin/env python3
"""fishgen_photo.py — Victorian engraving fish plates -> images/fish/<slug>.png

Generates plates for any species slug found in data/species.json that is
missing from images/fish/. Safe to re-run; existing files are skipped.

  python scripts/fishgen_photo.py
  python scripts/fishgen_photo.py --force   # overwrite existing

Requires the Higgsfield CLI (`higgsfield`) authenticated:
  higgsfield auth login

Provider can be overridden via env:
  FISH_PROVIDER=openai OPENAI_API_KEY=xxx python scripts/fishgen_photo.py
"""
import os, sys, json, subprocess, urllib.request

OUT = os.environ.get("FISH_OUT", "images/fish")
os.makedirs(OUT, exist_ok=True)
PROVIDER = os.environ.get("FISH_PROVIDER", "higgsfield")
FORCE = "--force" in sys.argv

# ── Prompt builder ────────────────────────────────────────────────────────────

def prompt_for(slug, name):
    view = ("viewed from above its eyed side with both eyes on the upper-left, head pointing left"
            if "halibut" in slug else
            "exact left-side profile, whole fish from head to tail, horizontal")
    base = (f"Victorian natural history engraving of a single {name}. "
            f"{view}, centered on a plain cream background. "
            f"Black ink illustration in the style of a 19th-century field guide plate: "
            f"dense parallel hatching lines on the dorsal back area graduating to lighter on the belly, "
            f"fine overlapping arc lines suggesting scales, detailed fins with visible ray lines, "
            f"clean confident ink outline, small precise eye with white highlight. "
            f"No color, no watercolor, no gray tones, pure black ink lines on cream paper. "
            f"No text, no border, no watermark, no background scenery.")
    return base

# ── Providers ─────────────────────────────────────────────────────────────────

def gen_higgsfield(prompt, slug):
    """Use Higgsfield CLI (gpt_image_2_5). Returns PNG bytes."""
    result = subprocess.run(
        ["higgsfield", "generate", "create", "gpt_image_2_5",
         "--prompt", prompt, "--aspect_ratio", "4:3", "--resolution", "2k", "--wait"],
        capture_output=True, text=True
    )
    url = result.stdout.strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"Higgsfield error: {result.stdout} {result.stderr}")
    with urllib.request.urlopen(url) as r:
        return r.read()

def gen_openai(prompt, slug):
    from openai import OpenAI
    import base64
    client = OpenAI()
    r = client.images.generate(model="gpt-image-2", prompt=prompt, size="1024x768",
                                response_format="b64_json")
    return base64.b64decode(r.data[0].b64_json)

def gen_local(prompt, slug):
    import requests, base64
    url = os.environ.get("LOCAL_SD_URL", "http://127.0.0.1:7860/sdapi/v1/txt2img")
    r = requests.post(url, json={"prompt": prompt, "steps": 30, "width": 1024, "height": 768})
    return base64.b64decode(r.json()["images"][0])

GEN = {"higgsfield": gen_higgsfield, "openai": gen_openai, "local": gen_local}[PROVIDER]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    species_path = os.path.join("data", "species.json")
    if not os.path.exists(species_path):
        print("Run from the project root (data/species.json not found).")
        sys.exit(1)

    with open(species_path) as f:
        db = json.load(f)["species"]

    made, skipped, failed = [], [], []
    for slug, info in db.items():
        png = os.path.join(OUT, f"{slug}.png")
        if os.path.exists(png) and not FORCE:
            skipped.append(slug)
            continue
        name = info.get("n", slug)
        print(f"  gen {slug} ({name}) ...")
        try:
            data = GEN(prompt_for(slug, name), slug)
            with open(png, "wb") as f:
                f.write(data)
            made.append(slug)
            print(f"  done {slug}")
        except Exception as e:
            failed.append((slug, str(e)))
            print(f"  FAIL {slug} -> {e}")

    print(f"\nprovider={PROVIDER}")
    print(f"generated: {made}")
    print(f"skipped (already had): {len(skipped)}")
    if failed:
        print(f"failed: {failed}")

if __name__ == "__main__":
    main()
