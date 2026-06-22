# CLAUDE.md — Fathom

Personal fishing instrument ("my own Fishbrain"). A zero-build static web app that shows, per
local spot: today's tide, the best-time bite windows, and what's biting with ranked tackle.
Built to run free on GitHub Pages with no backend and no API keys at runtime.

## How it runs
- Pure static site. `index.html` loads `src/styles.css` and `src/app.js`.
- `src/app.js` **fetches `data/locations.json` + `data/species.json`** at startup, computes a
  bite score, and renders. Because it uses `fetch`, the app **must be served over http** —
  open it via `make serve` (or deploy to Pages), never `file://`.
- The scoring in `app.js` is a lightweight inline engine running on **sample tide data**
  (the `extrema` arrays in `locations.json`). `src/fishing-core.js` is the real engine that
  pulls **live** tides (NOAA CO-OPS) + weather (Open-Meteo) — wiring it in is the main TODO.

## Data is the source of truth
- `data/locations.json` → `{ "locations": [ {id, name, lat, lon, station, water, tags, extrema, cond, fish[]} ] }`
  - `station` = NOAA CO-OPS 7-char tide station ID (null for freshwater). **Verify IDs** at
    tidesandcurrents.noaa.gov/map — several SoCal spots are currently pointed at Newport's 9410580.
  - `water`: `"salt"` | `"fresh"`. Freshwater spots have `extrema: null` → the instrument drops
    to a "no tidal influence" state and scoring redistributes tide weight into solunar + light.
  - `fish`: array of `{ slug, tide, light, note }` — `slug` references a key in species.json.
- `data/species.json` → `{ "species": { "<slug>": {n, s, cast, depth, rigs:[{name,detail,line} ×3]} } }`
  - `rigs[0]` is the "Top pick" (emphasized in the UI); exactly 3, best first.

## Conventions
- **Slugs** are the join key everywhere: `species.json` keys, `images/fish/<slug>.png`, generators.
- **Image resolution** (in `app.js` renderFish): try `images/fish/<slug>.png` (photo) →
  `images/fish/vector/<slug>.png` (vector fallback) → placeholder. So photos override vectors
  per-species automatically once generated.
- **Bite score** = `0.45·tide + 0.33·solunar + 0.22·light`, then ×weather. Tide component is the
  normalized rate-of-change of the tide curve (max mid-tide, ~0 at slack = moving water).
  Weights live at the top of the engine; tune per how your spots actually fish.
- **Generators are idempotent**: they only draw species whose PNG is missing (dedup by file).

## Plates (fish images)
- `make plates` → `scripts/fishgen.py` draws original vector field-guide plates to
  `images/fish/vector/` (free, offline, committed). These already exist for all 14 species.
- `make photos` → `scripts/fishgen_photo.py` generates **photoreal** plates to `images/fish/`
  (run locally; needs an image API or local Stable Diffusion). One-time, ~$0.28 on Imagen 4 Fast,
  or $0 via a local endpoint. This is the step the owner has NOT run yet. Dedup means re-running
  is safe. `--transparent` cuts out the background (rembg).
- Prompts in `fishgen_photo.py` encode diagnostic features per species (e.g. sheephead male
  tricolor + white chin; halibut flatfish eyes-up; spotfin shoulder spot) to stay ID-accurate.

## Enrich (optional, free)
- `make enrich` → `scripts/enrich.mjs` finds slugs referenced by locations.json but missing from
  species.json and fills them via the Gemini free tier (text only; no web grounding). For spots
  needing current/verified info, prefer asking Claude to research and hand back a species.json block.

## Free-stack rules (keep these true)
- No runtime API keys: tides = NOAA CO-OPS (keyless), weather = Open-Meteo (keyless), sun/moon =
  SunCalc (client-side). Hosting = GitHub Pages. Keep the deployed app key-free and ad-free.
- Keys only appear in **local** scripts (image gen, enrich), read from env, never committed.

## Roadmap / TODO (good next tasks for Claude Code)
1. **Wire live data**: replace the inline sample engine in `app.js` with `src/fishing-core.js`
   (`fetchTideExtrema(station, date)` + `fetchMarine(lat, lon, date)` + `bestWindows(...)`).
   Add a small loading state and a 24h cache (localStorage) to be polite to the APIs.
2. **Run `make photos`** to replace vector plates with photoreal ones.
3. **Add-spot UI**: a form writing new locations to localStorage (or a committed JSON edit).
4. **Regulations/seasons** per species (size/bag limits, open seasons) — sourced, not invented.
5. Multi-day forecast (NOAA + Open-Meteo support date ranges).

## Gotchas
- Serve over http (`make serve`); `file://` breaks `fetch`.
- Irvine Lake is shore-only, typically Fri–Sun, and **bass are catch-and-release** — keep that note.
- Photoreal generations can muddle fin counts/markings; eyeball each plate vs a reference, delete
  and re-run any that look wrong (dedup handles the rest).
- Don't invent regs, seasons, or station IDs — verify or leave a TODO.
