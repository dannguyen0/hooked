#!/usr/bin/env python3
"""
Remove backgrounds from fish images using rembg (runs locally, free).

Install once:  pip install rembg pillow onnxruntime
First run downloads the u2net model (~170 MB, cached in ~/.u2net).

Usage:
  python scripts/remove_bg.py          # process all images/fish/*.png
  python scripts/remove_bg.py kelp-bass barred-sand-bass   # specific slugs
  python scripts/remove_bg.py --overwrite    # re-process even if output exists
"""

import os, sys

try:
    from rembg import remove
    from PIL import Image
    import io
except ImportError:
    print("Missing deps. Run:  pip install rembg pillow onnxruntime")
    sys.exit(1)

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FISH_DIR = os.path.join(ROOT, "images", "fish")

def process(slug, overwrite=False):
    src = os.path.join(FISH_DIR, f"{slug}.png")
    if not os.path.exists(src):
        print(f"  skip  {slug} (source not found)")
        return False
    out = src  # overwrite in-place with transparent version

    if not overwrite:
        img = Image.open(src)
        if img.mode == "RGBA":
            # check if already has transparency
            if img.getextrema()[3][0] < 255:
                print(f"  skip  {slug} (already transparent)")
                return True

    print(f"  removing bg from {slug} ...", end=" ", flush=True)
    try:
        with open(src, "rb") as f:
            data = f.read()
        result = remove(data)
        img = Image.open(io.BytesIO(result)).convert("RGBA")
        img.save(out, "PNG")
        print(f"OK  ({os.path.getsize(out)//1024} KB)")
        return True
    except Exception as e:
        print(f"FAIL  {e}")
        return False

def main():
    overwrite = "--overwrite" in sys.argv
    targets = [a for a in sys.argv[1:] if not a.startswith("--")]

    if targets:
        slugs = targets
    else:
        slugs = [
            os.path.splitext(f)[0]
            for f in os.listdir(FISH_DIR)
            if f.endswith(".png") and not f.startswith(".")
            and os.path.isfile(os.path.join(FISH_DIR, f))
        ]
        slugs.sort()

    print(f"Processing {len(slugs)} image(s) with rembg ...\n")
    ok = fail = 0
    for slug in slugs:
        if process(slug, overwrite):
            ok += 1
        else:
            fail += 1

    print(f"\nDone: {ok} processed, {fail} failed.")
    print("Commit with: git add images/fish/*.png && git commit -m 'Transparent fish PNGs'")

if __name__ == "__main__":
    main()
