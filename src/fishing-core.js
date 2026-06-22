// fishing-core.js
// Pure-ish fishing logic for a personal, zero-cost fishing app.
// One runtime dependency: suncalc (MIT). No API keys anywhere.
//
// Two layers:
//   1) computeBiteScore() / bestWindows()  -> pure functions, fully testable offline.
//   2) fetchTideExtrema() / fetchMarine()  -> free public data (NOAA + Open-Meteo), browser-safe (CORS ok).
//
// Times are JS Date objects. NOAA strings are local-station time; we parse them as local.

import SunCalc from './suncalc.js';

// ---------------------------------------------------------------------------
// Weights — tune these to your spots. tide/solunar/light sum to 1; weather is a
// separate multiplier so bad conditions scale the whole score down.
// ---------------------------------------------------------------------------
export const DEFAULT_WEIGHTS = { tide: 0.45, solunar: 0.33, light: 0.22 };

const MIN = 60 * 1000;
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
const gauss = (dtMin, sigma) => Math.exp(-0.5 * (dtMin / sigma) ** 2); // 1 at dt=0

// ===========================================================================
// TIDE
// ===========================================================================
// extrema: sorted [{ t: Date, height: Number, type: 'H'|'L' }]
// Cosine interpolation between consecutive highs/lows: height is smooth, and the
// rate (current) is zero at slack and maximal mid-tide — matches real behavior.

function tideAt(time, extrema) {
  const t = +time;
  let i = 0;
  while (i < extrema.length - 1 && +extrema[i + 1].t <= t) i++;
  const a = extrema[i], b = extrema[i + 1];
  if (!b) return { height: a.height, rate: 0, direction: 'slack' };
  if (t <= +a.t) return { height: a.height, rate: 0, direction: 'slack' };

  const span = +b.t - +a.t;            // ms between extrema
  const phase = (t - +a.t) / span;     // 0..1
  const dH = b.height - a.height;
  const height = a.height + dH * (1 - Math.cos(Math.PI * phase)) / 2;
  // d(height)/dt, converted to feet per hour
  const ratePerMs = dH * (Math.PI / (2 * span)) * Math.sin(Math.PI * phase);
  const rate = ratePerMs * 3.6e6;
  const direction = dH > 0 ? 'incoming' : 'outgoing';
  return { height, rate, direction };
}

// Max possible |rate| in the day = steepest cosine segment, used to normalize 0..1.
function dayMaxRate(extrema) {
  let max = 0;
  for (let i = 0; i < extrema.length - 1; i++) {
    const span = +extrema[i + 1].t - +extrema[i].t;
    const dH = Math.abs(extrema[i + 1].height - extrema[i].height);
    const peak = dH * (Math.PI / (2 * span)) * 3.6e6; // ft/hr at midpoint
    if (peak > max) max = peak;
  }
  return max || 1;
}

function tideComponent(time, extrema, maxRate) {
  if (!extrema || extrema.length === 0) return { score: 0, direction: 'slack', height: 0, rate: 0 };
  const { rate, direction, height } = tideAt(time, extrema);
  const movement = clamp(Math.abs(rate) / maxRate, 0, 1); // moving water = feeding water
  return { score: movement, direction, height, rate };
}

// ===========================================================================
// SOLUNAR (moon)
// ===========================================================================
// Major periods: lunar transit (overhead) + anti-transit (underfoot).
// Minor periods: moonrise + moonset.  Strengthened near new/full moon.

function solunarEvents(date, lat, lon) {
  // scan the day for moon altitude max (transit) and min (underfoot)
  const day = new Date(date); day.setHours(0, 0, 0, 0);
  let transit = null, under = null, hi = -Infinity, lo = Infinity;
  for (let m = 0; m <= 24 * 60; m += 10) {
    const t = new Date(+day + m * MIN);
    const alt = SunCalc.getMoonPosition(t, lat, lon).altitude;
    if (alt > hi) { hi = alt; transit = t; }
    if (alt < lo) { lo = alt; under = t; }
  }
  const mt = SunCalc.getMoonTimes(day, lat, lon);
  return {
    major: [transit, under].filter(Boolean),
    minor: [mt.rise, mt.set].filter(Boolean),
  };
}

function moonStrength(date) {
  const phase = SunCalc.getMoonIllumination(date).phase; // 0 new, .5 full
  return 0.6 + 0.4 * Math.abs(Math.cos(2 * Math.PI * phase)); // 1 at new/full, .6 at quarters
}

function solunarComponent(time, events, strength) {
  let best = 0;
  for (const e of events.major) best = Math.max(best, 1.0 * gauss((time - e) / MIN, 55));
  for (const e of events.minor) best = Math.max(best, 0.7 * gauss((time - e) / MIN, 40));
  return clamp(best * strength, 0, 1);
}

// ===========================================================================
// LIGHT (dawn / dusk)
// ===========================================================================
function lightComponent(time, times) {
  const peaks = [times.sunrise, times.sunset].filter(Boolean);
  let best = 0;
  for (const p of peaks) best = Math.max(best, gauss((time - p) / MIN, 55));
  return clamp(best, 0, 1);
}

// ===========================================================================
// WEATHER (optional multiplier)
// ===========================================================================
// weather = { windKn, pressureHpa, pressureTrend3h, waveHeightFt? } — any field optional.
export function weatherFactor(weather) {
  if (!weather) return 1;
  let f = 1;
  if (typeof weather.windKn === 'number')
    f *= clamp(1 - Math.max(0, weather.windKn - 10) / 30, 0.55, 1);   // calm <10kn, hurts above
  if (typeof weather.pressureTrend3h === 'number')
    f *= clamp(1 - weather.pressureTrend3h * 0.03, 0.9, 1.1);          // falling baro = slight bite bump
  if (typeof weather.waveHeightFt === 'number')
    f *= clamp(1 - Math.max(0, weather.waveHeightFt - 4) / 12, 0.6, 1);
  return clamp(f, 0.5, 1.1);
}

// ===========================================================================
// SPECIES FIT (optional) — nudge score toward a target species' preferences
// ===========================================================================
// target = { bestTide:['incoming'|'outgoing'], bestLight:['dawn'|'dusk'|'midday'|'night'] }
function speciesFit(target, direction, lightScore) {
  if (!target) return 1;
  let f = 1;
  if (target.bestTide?.length)
    f *= target.bestTide.includes(direction) ? 1.12 : 0.9;
  if (target.bestLight?.includes('dawn') || target.bestLight?.includes('dusk'))
    f *= 0.95 + 0.2 * lightScore; // rewards low-light if species likes it
  return clamp(f, 0.8, 1.2);
}

const labelFor = (s) =>
  s >= 75 ? 'Prime' : s >= 55 ? 'Good' : s >= 35 ? 'Fair' : 'Slow';

// ===========================================================================
// MAIN: score a single moment
// ===========================================================================
// ctx is precomputed once per (location, day) for speed — see makeContext().
export function computeBiteScore(time, ctx, opts = {}) {
  const w = { ...DEFAULT_WEIGHTS, ...(opts.weights || {}) };
  const tide = tideComponent(time, ctx.extrema, ctx.maxRate);
  const sol = solunarComponent(time, ctx.events, ctx.strength);
  const light = lightComponent(time, ctx.times);

  let core = w.tide * tide.score + w.solunar * sol + w.light * light;
  core *= speciesFit(opts.target, tide.direction, light);
  const wf = weatherFactor(opts.weather);
  const score = Math.round(clamp(core * wf, 0, 1) * 100);

  return {
    score,
    label: labelFor(score),
    direction: tide.direction,
    breakdown: {
      tide: +tide.score.toFixed(2),
      solunar: +sol.toFixed(2),
      light: +light.toFixed(2),
      weather: +wf.toFixed(2),
      tideHeightFt: +tide.height.toFixed(2),
    },
  };
}

// Precompute the per-day astro + tide context so scanning is cheap.
export function makeContext({ extrema, lat, lon, date }) {
  const d = new Date(date);
  const ex = extrema || [];
  const moonIll = SunCalc.getMoonIllumination(d);
  return {
    extrema: ex,
    maxRate: ex.length ? dayMaxRate(ex) : 1,
    events: solunarEvents(d, lat, lon),
    strength: moonStrength(d),
    times: SunCalc.getTimes(d, lat, lon),
    moonPct: Math.round(moonIll.fraction * 100),
    moonPhase: moonIll.phase,
  };
}

// ===========================================================================
// BEST WINDOWS — the "when should I go today" output
// ===========================================================================
export function bestWindows({ extrema, lat, lon, date, weather, target, weights,
  stepMin = 15, minScore = 55, maxGapMin = 20 } = {}) {
  const ctx = makeContext({ extrema, lat, lon, date });
  const day = new Date(date); day.setHours(0, 0, 0, 0);

  const samples = [];
  for (let m = 0; m <= 24 * 60; m += stepMin) {
    const t = new Date(+day + m * MIN);
    samples.push({ t, ...computeBiteScore(t, ctx, { weather, target, weights }) });
  }

  // group contiguous above-threshold samples into windows
  const windows = [];
  let cur = null;
  for (const s of samples) {
    if (s.score >= minScore) {
      if (!cur) cur = { start: s.t, end: s.t, peak: s };
      else { cur.end = s.t; if (s.score > cur.peak.score) cur.peak = s; }
    } else if (cur) { windows.push(cur); cur = null; }
  }
  if (cur) windows.push(cur);

  return windows
    .sort((a, b) => b.peak.score - a.peak.score)
    .map((w) => ({
      start: w.start, end: w.end,
      peakTime: w.peak.t, peakScore: w.peak.score, label: w.peak.label,
      direction: w.peak.direction,
    }));
}

// ===========================================================================
// FREE DATA FETCHERS  (no keys, CORS-friendly, browser or node)
// ===========================================================================
const ymd = (d) => {
  const z = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${z(d.getMonth() + 1)}${z(d.getDate())}`;
};
const iso = (d) => {
  const z = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
};

// NOAA CO-OPS tide predictions (high/low). station = 7-char ID, e.g. '9410230' (La Jolla).
export async function fetchTideExtrema(station, date) {
  const d = ymd(new Date(date));
  const url = `https://api.tidesandcurrents.noaa.gov/api/prod/datagetter` +
    `?product=predictions&application=personal-fishing-app` +
    `&begin_date=${d}&end_date=${d}&datum=MLLW&station=${station}` +
    `&time_zone=lst_ldt&units=english&interval=hilo&format=json`;
  const r = await fetch(url);
  const j = await r.json();
  if (!j.predictions) throw new Error('NOAA: no predictions (check station id)');
  return j.predictions.map((p) => ({
    t: new Date(p.t.replace(' ', 'T')),
    height: parseFloat(p.v),
    type: p.type, // 'H' | 'L'
  }));
}

// Open-Meteo wind + pressure (+ marine wave height). No key.
export async function fetchMarine(lat, lon, date) {
  const d = iso(new Date(date));
  const w = await fetch(`https://api.open-meteo.com/v1/forecast` +
    `?latitude=${lat}&longitude=${lon}&hourly=wind_speed_10m,surface_pressure` +
    `&wind_speed_unit=kn&timezone=auto&start_date=${d}&end_date=${d}`).then((r) => r.json());
  let waves = null;
  try {
    waves = await fetch(`https://marine-api.open-meteo.com/v1/marine` +
      `?latitude=${lat}&longitude=${lon}&hourly=wave_height&length_unit=imperial` +
      `&timezone=auto&start_date=${d}&end_date=${d}`).then((r) => r.json());
  } catch { /* marine grid may not cover inland spots */ }

  // helper: snapshot conditions at a given Date
  return (time) => {
    const hrs = w.hourly.time.map((s) => new Date(s));
    let i = 0; while (i < hrs.length - 1 && +hrs[i + 1] <= +time) i++;
    return {
      windKn: w.hourly.wind_speed_10m[i],
      pressureHpa: w.hourly.surface_pressure[i],
      pressureTrend3h: i >= 3
        ? w.hourly.surface_pressure[i] - w.hourly.surface_pressure[i - 3] : 0,
      waveHeightFt: waves?.hourly?.wave_height?.[i] ?? null,
    };
  };
}
