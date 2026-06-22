#!/usr/bin/env python3
"""fishgen_photo.py — photorealistic fish plates -> images/fish/<slug>.png

Run on YOUR machine (image APIs are reachable there). Only generates species
that are MISSING from the images dir, so it's a one-time sub-dollar job.

  pip install google-genai pillow            # + rembg  (optional transparency)
  GEMINI_API_KEY=xxxx python3 fishgen_photo.py
  GEMINI_API_KEY=xxxx python3 fishgen_photo.py --transparent   # cut out background

Provider is swappable: default Google (Imagen 4 Fast, ~$0.02/img). OpenAI and a
local ComfyUI/Stable-Diffusion endpoint are stubbed below — pick one.
"""
import os, sys, json, io, time

OUT = os.environ.get("FISH_OUT", "images/fish")
os.makedirs(OUT, exist_ok=True)
PROVIDER = os.environ.get("FISH_PROVIDER", "google")     # google | openai | local
MODEL    = os.environ.get("FISH_MODEL", "imagen-4.0-fast-generate-001")  # or gemini-2.5-flash-image
TRANSPARENT = "--transparent" in sys.argv

# Diagnostic features per species — keeps the photoreal output ID-accurate.
FEATURES = {
 "kelp-bass":"olive-brown California calico (kelp) bass with cream-white blotches in a checkerboard pattern, spiny dorsal fin, large mouth",
 "barred-sand-bass":"barred sand bass, grayish tan-brown with darker vertical bars along the flank, one elongated dorsal spine",
 "spotted-bay-bass":"spotted bay bass, olive-tan fusiform body densely covered in small dark spots",
 "largemouth-bass":"largemouth bass, green back fading to pale belly, bold dark horizontal lateral stripe of blotches, oversized jaw extending past the eye",
 "spotfin-croaker":"spotfin croaker, silvery steel body with a brassy sheen and a distinct round black spot at the base of the pectoral fin, sub-terminal mouth",
 "california-corbina":"California corbina, slender elongated silvery-gray croaker with faint diagonal wavy bars and a single short barbel under the lower jaw",
 "pacific-bonito":"Pacific bonito, streamlined tuna-like body, steel-blue back with dark slanted oblique stripes, silver belly, deeply forked tail and small finlets",
 "pacific-mackerel":"Pacific mackerel, streamlined body, greenish-blue back with wavy dark vertical bars, bright silver belly, finlets and a forked tail",
 "barred-surfperch":"barred surfperch, deep compressed silvery oval body with coppery-olive vertical bars and a small mouth",
 "opaleye":"opaleye, oval dark olive-green body with one or two small white spots high on the back and a striking opal blue-green eye",
 "california-sheephead":"adult male California sheephead, deep body with a steep bulging forehead, jet-black head and front third, red-orange midsection, black rear, white lower jaw, prominent canine teeth",
 "black-crappie":"black crappie, deep compressed silvery body with irregular black mottling and blotches, tall spiny dorsal fin set far back, large eye",
 "channel-catfish":"channel catfish, slate-olive smooth scaleless body with scattered small dark spots, long whisker barbels around the mouth, deeply forked tail and an adipose fin",
 "california-halibut":"California halibut, a flatfish lying flat and viewed from its eyed side with both eyes on the upper-left, mottled sandy-brown camouflage, very large mouth, long continuous dorsal and anal fins fringing an asymmetric oval body",
}
NAMES = {  # for manifest
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

def prompt_for(slug):
    feat = FEATURES[slug]
    view = ("viewed from directly above its eyed side, head pointing left"
            if slug == "california-halibut" else
            "exact left-side profile, whole fish from head to tail visible, horizontal")
    return (f"Professional photorealistic studio photograph of a single fresh {feat}. "
            f"{view}, centered. Isolated on a pure seamless flat white background, soft even "
            f"softbox lighting, ultra-sharp focus, fine scale and skin texture, natural wet sheen, "
            f"true-to-life coloration. No text, no watermark, no logo, no human hands, no hook or "
            f"line, no props, no scenery, no shadow clutter.")

# ---------------- providers : return PNG bytes ----------------
def gen_google(prompt):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    if MODEL.startswith("imagen"):
        r = client.models.generate_images(model=MODEL, prompt=prompt,
            config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="4:3"))
        return r.generated_images[0].image.image_bytes
    # gemini-2.5-flash-image style (multimodal)
    r = client.models.generate_content(model=MODEL, contents=prompt)
    for part in r.candidates[0].content.parts:
        if getattr(part, "inline_data", None):
            return part.inline_data.data
    raise RuntimeError("no image returned")

def gen_openai(prompt):
    from openai import OpenAI
    client = OpenAI()  # uses OPENAI_API_KEY
    r = client.images.generate(model="gpt-image-2", prompt=prompt, size="1024x768")
    import base64
    return base64.b64decode(r.data[0].b64_json)

def gen_local(prompt):
    # Point at a local ComfyUI / Automatic1111 endpoint (free, unlimited).
    import requests
    url = os.environ.get("LOCAL_SD_URL", "http://127.0.0.1:7860/sdapi/v1/txt2img")
    r = requests.post(url, json={"prompt": prompt, "steps": 30, "width": 1024, "height": 768})
    import base64
    return base64.b64decode(r.json()["images"][0])

GEN = {"google": gen_google, "openai": gen_openai, "local": gen_local}[PROVIDER]

def to_transparent(png_bytes):
    from rembg import remove
    return remove(png_bytes)

def main():
    manifest_path = os.path.join(OUT, "manifest.json")
    manifest = json.load(open(manifest_path)) if os.path.exists(manifest_path) else {}
    made, skipped, failed = [], [], []
    for slug in FEATURES:
        png = os.path.join(OUT, f"{slug}.png")
        if os.path.exists(png):                       # dedup
            skipped.append(slug); continue
        try:
            data = GEN(prompt_for(slug))
            if TRANSPARENT:
                data = to_transparent(data)
            open(png, "wb").write(data)
            nm, sci = NAMES.get(slug, (slug, ""))
            manifest[slug] = {"name": nm, "sci": sci, "file": f"{slug}.png", "style": "photo"}
            made.append(slug); print("  ✓", slug)
            time.sleep(1.5)                           # be polite to rate limits
        except Exception as e:
            failed.append((slug, str(e))); print("  ✗", slug, "->", e)
    json.dump(manifest, open(manifest_path, "w"), indent=2)
    print(f"\nprovider={PROVIDER} model={MODEL}")
    print("generated:", made)
    print("skipped (already had):", skipped)
    if failed: print("failed:", failed)

if __name__ == "__main__":
    main()
