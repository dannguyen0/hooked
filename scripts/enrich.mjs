// scripts/enrich.mjs — fill MISSING fish entries in data/species.json using a FREE LLM.
//
// Reads the fish slugs referenced by data/locations.json, finds any not yet defined in
// data/species.json, and asks Gemini (free tier) to produce tackle data for them.
// Run locally:  GEMINI_API_KEY=xxxx node scripts/enrich.mjs
//
// Free-tier note (2026): Flash / Flash-Lite are the free text models (~15 RPM, ~1500/day,
// no card). Uses the model's own knowledge — for spots needing live web research, leave the
// slug out and have Claude fill it with search instead. Model names drift; check ai.google.dev.

import { readFile, writeFile } from 'node:fs/promises';

const MODEL = 'gemini-2.5-flash';
const KEY = process.env.GEMINI_API_KEY;
if (!KEY) { console.error('Set GEMINI_API_KEY'); process.exit(1); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const human = (slug) => slug.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

function prompt(slug) {
  return `You are a local Southern California fishing expert. Give shore/inshore tackle for "${human(slug)}".
Return ONLY a JSON object (no markdown) with this exact shape:
{"n":"common name","s":"scientific name",
 "cast":"where/how far to cast, one phrase","depth":"typical depth range, one phrase",
 "rigs":[{"name":"rig/lure name","detail":"how to fish it, 1-2 sentences","line":"line/leader spec"},
         {"name":"...","detail":"...","line":"..."},
         {"name":"...","detail":"...","line":"..."}]}
Exactly 3 rigs, best first. Be specific and accurate for SoCal.`;
}

async function callGemini(text, tries = 0) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent?key=${KEY}`;
  const res = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ contents: [{ parts: [{ text }] }],
      generationConfig: { responseMimeType: 'application/json', temperature: 0.4 } }),
  });
  if (res.status === 429 && tries < 5) { const w = 2 ** tries * 4000; console.log(`  429, waiting ${w/1000}s`); await sleep(w); return callGemini(text, tries + 1); }
  if (!res.ok) throw new Error(`Gemini ${res.status}: ${await res.text()}`);
  const j = await res.json();
  return JSON.parse((j.candidates?.[0]?.content?.parts?.[0]?.text ?? '{}').replace(/```json|```/g, '').trim());
}

const locs = JSON.parse(await readFile('data/locations.json', 'utf8')).locations;
const db = JSON.parse(await readFile('data/species.json', 'utf8'));
const needed = [...new Set(locs.flatMap((l) => l.fish.map((f) => f.slug)))];
const missing = needed.filter((slug) => !db.species[slug]);

if (!missing.length) { console.log('Nothing to enrich — every referenced species is already defined.'); process.exit(0); }
console.log('Missing species:', missing.join(', '));
for (const slug of missing) {
  try {
    const entry = await callGemini(prompt(slug));
    db.species[slug] = entry;
    console.log('  ✓', slug, '→', entry.n);
    await sleep(4500);
  } catch (e) { console.error('  ✗', slug, e.message); }
}
await writeFile('data/species.json', JSON.stringify(db, null, 2));
console.log('Wrote data/species.json. Now run `make plates` (and `make photos`) to draw any new fish.');
