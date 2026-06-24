import { fetchTideExtrema, makeContext, computeBiteScore, bestWindows } from './fishing-core.js?v=3';

// ── Time constants ────────────────────────────────────────────────────────
const MIN = 60000;
const today = new Date(); today.setSeconds(0, 0);
const dayStart = new Date(today); dayStart.setHours(0, 0, 0, 0);
const TODAY_ISO = dayStart.toISOString().slice(0, 10);
const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const FRESH_W = { tide: 0, solunar: 0.6, light: 0.4 };

// ── Small helpers ─────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const isoDate = d => d.toISOString().slice(0, 10);
const band = s => s >= 75 ? 'prime' : s >= 55 ? 'good' : s >= 35 ? 'fair' : 'slow';
const labl = s => s >= 75 ? 'Prime' : s >= 55 ? 'Good' : s >= 35 ? 'Fair' : 'Slow';
const fmt = m => {
  m = ((m % 1440) + 1440) % 1440;
  const h = Math.floor(m / 60), mm = String(Math.round(m % 60)).padStart(2, '0'), ap = h < 12 ? 'AM' : 'PM';
  let hh = h % 12; if (!hh) hh = 12;
  return `${hh}:${mm} ${ap}`;
};
const degToCompass = d => ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'][Math.round(d / 22.5) % 16];
const moonLabel = p => p < .05 ? 'new' : p < .25 ? 'waxing cres.' : p < .30 ? 'first qtr' : p < .48 ? 'waxing gib.' : p < .52 ? 'full' : p < .70 ? 'waning gib.' : p < .75 ? 'last qtr' : p < .95 ? 'waning cres.' : 'new';

// ── LocalStorage cache (24-hour, keyed by spot+date) ─────────────────────
function cacheGet(id) {
  try {
    const raw = localStorage.getItem(`hooked_v1_${id}_${TODAY_ISO}`);
    if (!raw) return null;
    const d = JSON.parse(raw);
    if (d.extrema) d.extrema = d.extrema.map(e => ({ ...e, t: new Date(e.t) }));
    return d;
  } catch { return null; }
}
function cacheSet(id, data) {
  try {
    const serial = { ...data, extrema: data.extrema?.map(e => ({ ...e, t: e.t.toISOString() })) };
    localStorage.setItem(`hooked_v1_${id}_${TODAY_ISO}`, JSON.stringify(serial));
  } catch {}
}

// ── Convert locations.json sample extrema [h,m,v,type] → [{t,height,type}] ──
function convertSampleExtrema(sp) {
  if (!sp.extrema) return null;
  return sp.extrema.map(([h, m, v, type]) => ({
    t: new Date(+dayStart + (h * 60 + m) * MIN),
    height: v, type,
  }));
}

// ── Weather fetch (Open-Meteo, no API key) ────────────────────────────────
async function fetchWeatherRaw(lat, lon) {
  const d = isoDate(today);
  const w = await fetch(
    `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}` +
    `&hourly=wind_speed_10m,wind_direction_10m,surface_pressure` +
    `&wind_speed_unit=kn&timezone=auto&start_date=${d}&end_date=${d}`
  ).then(r => r.json());
  let waves = null;
  try {
    waves = await fetch(
      `https://marine-api.open-meteo.com/v1/marine?latitude=${lat}&longitude=${lon}` +
      `&hourly=wave_height&length_unit=imperial&timezone=auto&start_date=${d}&end_date=${d}`
    ).then(r => r.json());
  } catch { /* inland spots not covered by marine grid */ }
  return { w, waves };
}

function makeWeatherAt(raw) {
  if (!raw) return null;
  const { w, waves } = raw;
  const hrs = w.hourly.time.map(s => new Date(s));
  return time => {
    let i = 0;
    while (i < hrs.length - 1 && +hrs[i + 1] <= +time) i++;
    return {
      windKn: w.hourly.wind_speed_10m[i],
      windDir: degToCompass(w.hourly.wind_direction_10m[i]),
      pressureHpa: w.hourly.surface_pressure[i],
      pressureTrend3h: i >= 3 ? w.hourly.surface_pressure[i] - w.hourly.surface_pressure[i - 3] : 0,
      waveHeightFt: waves?.hourly?.wave_height?.[i] ?? null,
    };
  };
}

// ── Per-spot data state ───────────────────────────────────────────────────
const spotData = {}; // id → { ctx, weatherAt, staticWeather, loaded, loading }

function initSampleCtx(spot) {
  const extrema = convertSampleExtrema(spot);
  const ctx = makeContext({ extrema: extrema || [], lat: spot.lat, lon: spot.lon, date: today });
  const cond = spot.cond || {};
  const staticWeather = {
    windKn: parseFloat(cond.wind) || 0,
    pressureTrend3h: typeof cond.trend === 'number' ? cond.trend : 0,
    waveHeightFt: cond.swell ? parseFloat(cond.swell) : null,
  };
  spotData[spot.id] = { ctx, weatherAt: null, staticWeather, loaded: false, loading: false };
}

async function loadLiveData(spot) {
  if (spotData[spot.id]?.loaded) {
    if (spot.id === active?.id) renderAll();
    return;
  }
  spotData[spot.id] = { ...spotData[spot.id], loading: true };
  if (spot.id === active?.id) setLoading(true);
  try {
    const cached = cacheGet(spot.id);
    let extrema, weatherRaw;
    if (cached && 'extrema' in cached) {
      extrema = cached.extrema;
      weatherRaw = cached.wr || null;
    } else {
      [extrema, weatherRaw] = await Promise.all([
        spot.station ? fetchTideExtrema(spot.station, today).catch(() => null) : Promise.resolve(null),
        fetchWeatherRaw(spot.lat, spot.lon).catch(() => null),
      ]);
      if (!extrema && spot.water === 'salt') extrema = convertSampleExtrema(spot);
      cacheSet(spot.id, { extrema, wr: weatherRaw || null });
    }
    const ctx = makeContext({ extrema: extrema || [], lat: spot.lat, lon: spot.lon, date: today });
    const weatherAt = makeWeatherAt(weatherRaw);
    spotData[spot.id] = { ctx, weatherAt, staticWeather: spotData[spot.id]?.staticWeather, loaded: true, loading: false };
  } catch (e) {
    console.warn('Live data fetch failed:', e);
    spotData[spot.id] = { ...spotData[spot.id], loaded: true, loading: false };
  }
  if (spot.id === active?.id) { setLoading(false); renderAll(); }
}

function setLoading(on) {
  const el = $('loadingIndicator');
  if (el) el.hidden = !on;
}

// ── Scoring bridge (fishing-core API → app render format) ─────────────────
function scoreAt(spot, mins) {
  const sd = spotData[spot.id];
  if (!sd?.ctx) return { s: 0, dir: '—', tide: 0, sol: 0, light: 0 };
  const time = new Date(+dayStart + mins * MIN);
  const w = sd.weatherAt ? sd.weatherAt(time) : sd.staticWeather;
  const weights = spot.water === 'fresh' ? FRESH_W : undefined;
  const r = computeBiteScore(time, sd.ctx, { weather: w, weights });
  return { s: r.score, dir: r.direction, tide: r.breakdown.tide, sol: r.breakdown.solunar, light: r.breakdown.light };
}

function winAt(spot) {
  const sd = spotData[spot.id];
  if (!sd?.ctx) return [];
  const noon = new Date(+dayStart + 12 * 60 * MIN);
  const weather = sd.weatherAt ? sd.weatherAt(noon) : sd.staticWeather;
  const weights = spot.water === 'fresh' ? FRESH_W : undefined;
  return bestWindows({
    extrema: sd.ctx.extrema.length ? sd.ctx.extrema : null,
    lat: spot.lat, lon: spot.lon, date: today,
    weather, weights,
  }).map(w => ({
    s: (+w.start - +dayStart) / MIN,
    e: (+w.end - +dayStart) / MIN,
    pk: w.peakScore,
    pkm: (+w.peakTime - +dayStart) / MIN,
    dir: w.direction,
  }));
}

// ── Custom spots (localStorage) ───────────────────────────────────────────
const CUSTOM_KEY = 'hooked_custom_v1';
function loadCustomSpots() {
  try { return JSON.parse(localStorage.getItem(CUSTOM_KEY) || '[]'); } catch { return []; }
}
function saveCustomSpots(spots) {
  localStorage.setItem(CUSTOM_KEY, JSON.stringify(spots));
}
function deleteCustomSpot(id) {
  saveCustomSpots(loadCustomSpots().filter(s => s.id !== id));
  SPOTS = SPOTS.filter(s => s.id !== id);
  delete spotData[id];
  if (active.id === id) { active = SPOTS[0]; nowMin = realNow; isPreview = false; }
  renderAll();
}
function addCustomSpot(spot) {
  const customs = loadCustomSpots();
  customs.push(spot);
  saveCustomSpots(customs);
  SPOTS.push(spot);
  initSampleCtx(spot);
  active = spot; nowMin = realNow; isPreview = false;
  renderAll();
  loadLiveData(spot);
}

// ── Render functions ──────────────────────────────────────────────────────
let active, nowMin, realNow, isPreview = false;
let SPOTS, FISHDB;

$('dateLabel').textContent = today.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }).toUpperCase();

function renderRail() {
  $('spotList').innerHTML = SPOTS.map(sp => {
    const ws = winAt(sp);
    const best = ws[0];
    const bs = best ? best.pk : scoreAt(sp, nowMin).s;
    const b = band(bs);
    const isCustom = !!sp._custom;
    return `<li class="spot-li">
      <button class="spot" data-id="${sp.id}" aria-current="${sp.id === active.id}">
        <span class="chip" data-band="${b}">${bs}</span>
        <span class="nm">${sp.name}</span>
      </button>${isCustom ? `<button class="spot-edit" data-edit="${sp.id}" title="Edit spot">✎</button><button class="spot-del" data-del="${sp.id}" title="Delete spot">×</button>` : ''}
    </li>`;
  }).join('');
  $('spotList').querySelectorAll('.spot').forEach(btn => btn.onclick = () => {
    const sp = SPOTS.find(s => s.id === btn.dataset.id);
    if (!sp) return;
    active = sp; nowMin = realNow; isPreview = false;
    renderAll();
    loadLiveData(sp);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  $('spotList').querySelectorAll('.spot-edit').forEach(btn => btn.onclick = e => {
    e.stopPropagation();
    const sp = SPOTS.find(s => s.id === btn.dataset.edit);
    if (sp) openModalForEdit(sp);
  });
  $('spotList').querySelectorAll('.spot-del').forEach(btn => btn.onclick = e => {
    e.stopPropagation();
    const sp = SPOTS.find(s => s.id === btn.dataset.del);
    if (sp && confirm(`Delete "${sp.name}"?`)) deleteCustomSpot(sp.id);
  });
}

function renderHead() {
  const sp = active;
  $('spName').textContent = sp.name;
  $('spCoords').innerHTML = `<b>${sp.lat.toFixed(4)}°N ${Math.abs(sp.lon).toFixed(4)}°W</b><br>${sp.station ? 'NOAA ' + sp.station : 'NO TIDE STATION'} · ${sp.water === 'fresh' ? 'FRESHWATER' : 'MLLW'}`;
  $('spTags').innerHTML = sp.tags.map(t => `<span class="tag">${t}</span>`).join('');

  const sd = spotData[sp.id];
  const lw = sd?.loaded && sd.weatherAt ? sd.weatherAt(new Date()) : null;
  const c = sp.cond || {};
  const ctx = sd?.ctx;

  const windStr = lw ? `${Math.round(lw.windKn)} kn` : (c.wind || '—');
  const windDir = lw ? lw.windDir : (c.windDir || '—');
  const swellStr = lw && lw.waveHeightFt != null ? `${lw.waveHeightFt.toFixed(1)} ft` : (c.swell || 'calm');
  const swellSub = lw ? (lw.waveHeightFt != null ? '—' : 'no marine data') : (c.swellP ? `@${c.swellP}` : '—');
  const baroStr = lw ? Math.round(lw.pressureHpa) : (c.baro || '—');
  const trend = lw ? lw.pressureTrend3h : (typeof c.trend === 'number' ? c.trend : 0);
  const moonStr = ctx ? `${ctx.moonPct}%` : (c.moon || '—');
  const moonSub = ctx ? moonLabel(ctx.moonPhase) : '';
  const liveTag = (lw || ctx) ? ' <small class="live-tag">LIVE</small>' : '';

  const ICONS = {
    Wind: `<svg class="cond-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M1 5h9a2.5 2.5 0 1 0-2.5-2.5"/><path d="M1 9h12a2.5 2.5 0 1 1-2.5 2.5"/><path d="M1 13h7"/></svg>`,
    Surface: `<svg class="cond-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M1 10 Q3 7 5 10 Q7 13 9 10 Q11 7 13 10"/><path d="M1 6.5 Q3 3.5 5 6.5 Q7 9.5 9 6.5 Q11 3.5 13 6.5"/></svg>`,
    Swell:  `<svg class="cond-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M1 10 Q3 7 5 10 Q7 13 9 10 Q11 7 13 10"/><path d="M1 6.5 Q3 3.5 5 6.5 Q7 9.5 9 6.5 Q11 3.5 13 6.5"/></svg>`,
    Pressure:`<svg class="cond-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><circle cx="8" cy="9" r="5.5"/><path d="M8 9 L11 4.5"/><circle cx="8" cy="9" r="1" fill="currentColor" stroke="none"/></svg>`,
    Moon:   `<svg class="cond-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M11.5 10A5.5 5.5 0 1 1 6 4.5a4 4 0 0 0 5.5 5.5Z"/></svg>`,
  };
  const cells = [
    ['Wind', `${windStr} <small>${windDir}</small>${lw ? liveTag : ''}`],
    sp.water === 'fresh'
      ? ['Surface', 'calm <small>—</small>']
      : ['Swell', `${swellStr} <small>${swellSub}</small>`],
    ['Pressure', `${baroStr} <small class="${trend < 0 ? 'down' : 'up'}">${trend < 0 ? '▼' : '▲'}${Math.abs(trend).toFixed(1)}</small>`],
    ['Moon', `${moonStr} <small>${moonSub}</small>`],
  ];
  $('cond').innerHTML = cells.map(([k, v]) => `<div class="cell"><div class="k">${ICONS[k] || ''}${k}</div><div class="v">${v}</div></div>`).join('');
}

function renderInstrument() {
  const sp = active, svg = $('tideSvg');
  const Wd = 960, padL = 18, padR = 18;
  const padT = 28;
  const tideH = 248;
  const stripY = padT + tideH + 14;
  const stripH = 22;
  const footY  = stripY + stripH + 18;
  const Ht     = footY + 12;
  svg.setAttribute('viewBox', `0 0 ${Wd} ${Ht}`);
  svg.style.aspectRatio = `${Wd}/${Ht}`;

  let g = '';
  const stripW = Wd - padL - padR;
  const Xm = m => padL + stripW * m / 1440;

  const sd = spotData[sp.id];
  const ex = sd?.ctx?.extrema;

  // ── Legend row (top of chart, inside SVG) ───────────────────────────────
  const legItems = [
    ['#10B981','Prime ≥75'],['#F97316','Good 55–74'],['#0EA5E9','Fair 35–54'],
    ['rgba(139,92,246,.7)','Solunar peak'],
  ];
  let legX = padL;
  legItems.forEach(([c, lbl]) => {
    g += `<rect x="${legX}" y="8" width="7" height="7" rx="1.5" fill="${c}"/>`;
    g += `<text x="${legX + 10}" y="15" fill="#9CA3AF" font-family="Space Grotesk" font-size="9" font-weight="600">${lbl}</text>`;
    legX += lbl.length * 5.4 + 18;
  });

  // ── Subtle grid lines ────────────────────────────────────────────────────
  for (let i = 0; i <= 4; i++) {
    const y = padT + tideH * i / 4;
    g += `<line x1="${padL}" y1="${y}" x2="${Wd - padR}" y2="${y}" stroke="rgba(0,0,0,.05)" stroke-width="1"/>`;
  }

  // ── Activity strip ───────────────────────────────────────────────────────
  g += `<text x="${padL}" y="${stripY - 5}" fill="#9CA3AF" font-family="Space Grotesk" font-size="9.5" font-weight="700" letter-spacing="1.5">FISH ACTIVITY</text>`;
  g += `<clipPath id="stripClip"><rect x="${padL}" y="${stripY}" width="${stripW}" height="${stripH}" rx="5"/></clipPath>`;
  g += `<rect x="${padL}" y="${stripY}" width="${stripW}" height="${stripH}" rx="5" fill="rgba(0,0,0,.05)"/>`;

  for (let m = 0; m < 1440; m += 4) {
    const s = scoreAt(sp, m).s;
    const col = s >= 75 ? '#10B981' : s >= 55 ? '#F97316' : s >= 35 ? '#0EA5E9' : null;
    if (!col) continue;
    const op = s >= 75 ? 0.88 : s >= 55 ? 0.72 : 0.48;
    const x = padL + stripW * m / 1440, w = stripW * 4 / 1440 + 0.5;
    g += `<rect x="${x}" y="${stripY}" width="${w}" height="${stripH}" fill="${col}" opacity="${op}" clip-path="url(#stripClip)"/>`;
  }

  // ── Solunar markers ──────────────────────────────────────────────────────
  if (sd?.ctx?.events) {
    const { major, minor } = sd.ctx.events;
    major.forEach(t => {
      if (!t) return;
      const m = (+t - +dayStart) / MIN;
      if (m < 0 || m > 1440) return;
      const x = Xm(m);
      g += `<line x1="${x}" y1="${padT}" x2="${x}" y2="${stripY}" stroke="rgba(139,92,246,.22)" stroke-width="1.5" stroke-dasharray="4 3"/>`;
      g += `<rect x="${x - 14}" y="${stripY}" width="28" height="${stripH}" fill="rgba(139,92,246,.22)" clip-path="url(#stripClip)"/>`;
    });
    minor.forEach(t => {
      if (!t) return;
      const m = (+t - +dayStart) / MIN;
      if (m < 0 || m > 1440) return;
      const x = Xm(m);
      g += `<line x1="${x}" y1="${padT + 40}" x2="${x}" y2="${stripY}" stroke="rgba(139,92,246,.12)" stroke-width="1" stroke-dasharray="2 4"/>`;
    });
  }

  // ── Tide curve ───────────────────────────────────────────────────────────
  if (ex && ex.length) {
    // Extend extrema with synthetic boundary points so the curve is smooth
    // across the full 24h instead of going flat at the edges
    const loH = Math.min(...ex.map(e => e.height));
    const hiH = Math.max(...ex.map(e => e.height));
    const spanPre = ex.length > 1 ? +ex[1].t - +ex[0].t : 6 * 60 * MIN;
    const spanPost = ex.length > 1 ? +ex[ex.length-1].t - +ex[ex.length-2].t : 6 * 60 * MIN;
    const synPre = {
      t: new Date(+ex[0].t - spanPre),
      height: ex[0].type === 'H' ? loH : hiH,
      type: ex[0].type === 'H' ? 'L' : 'H', virtual: true
    };
    const synPost = {
      t: new Date(+ex[ex.length-1].t + spanPost),
      height: ex[ex.length-1].type === 'H' ? loH : hiH,
      type: ex[ex.length-1].type === 'H' ? 'L' : 'H', virtual: true
    };
    const allEx = [synPre, ...ex, synPost];

    const vs = ex.map(e => e.height), lo = Math.min(...vs) - .5, hi = Math.max(...vs) + .5;
    const X = m => Xm(m);
    const Y = v => padT + tideH * (1 - (v - lo) / (hi - lo));
    const interp = ms => {
      let i = 0;
      while (i < allEx.length - 1 && +allEx[i + 1].t <= ms) i++;
      const a = allEx[i], b = allEx[i + 1];
      if (!b) return a.height;
      if (ms <= +a.t) return a.height;
      const ph = (ms - +a.t) / (+b.t - +a.t);
      return a.height + (b.height - a.height) * (1 - Math.cos(Math.PI * ph)) / 2;
    };
    let d = '';
    for (let m = 0; m <= 1440; m += 4) { const v = interp(+dayStart + m * MIN); d += (m === 0 ? 'M' : 'L') + X(m).toFixed(1) + ',' + Y(v).toFixed(1) + ' '; }
    const baseY = padT + tideH;
    g += `<path d="${d}L${Wd - padR},${baseY} L${padL},${baseY}Z" fill="rgba(14,165,233,.09)"/>`;
    g += `<path d="${d}" fill="none" stroke="#0EA5E9" stroke-width="2.5" stroke-linejoin="round"/>`;

    // Labels with white background pill for readability
    ex.forEach(e => {
      const m = (+e.t - +dayStart) / MIN, cx = X(m), cy = Y(e.height);
      const up = e.type === 'H';
      const lblY = up ? cy - 30 : cy + 14;
      const timeY = lblY + 13;
      // pill background
      g += `<rect x="${cx - 30}" y="${lblY - 11}" width="60" height="27" rx="5" fill="rgba(255,255,255,.92)" stroke="rgba(0,0,0,.08)" stroke-width="1"/>`;
      g += `<text x="${cx}" y="${lblY}" fill="${up ? '#0EA5E9' : '#374151'}" font-family="Space Grotesk" font-size="10.5" font-weight="700" text-anchor="middle">${up ? '▲' : '▼'} ${e.height.toFixed(1)} ft</text>`;
      g += `<text x="${cx}" y="${timeY}" fill="#6B7280" font-family="Space Grotesk" font-size="9.5" font-weight="500" text-anchor="middle">${fmt((+e.t - +dayStart)/MIN)}</text>`;
      // connector line from pill to dot
      g += `<line x1="${cx}" y1="${up ? lblY + 20 : lblY - 2}" x2="${cx}" y2="${up ? cy - 4 : cy + 4}" stroke="#0EA5E9" stroke-width="1" stroke-dasharray="2 2" opacity=".4"/>`;
      g += `<circle cx="${cx}" cy="${cy}" r="4.5" fill="#fff" stroke="#0EA5E9" stroke-width="2.5"/>`;
    });

    const xn = X(nowMin), vn = interp(+dayStart + nowMin * MIN);
    g += `<line x1="${xn}" y1="${padT}" x2="${xn}" y2="${stripY + stripH}" stroke="${isPreview ? '#0EA5E9' : '#F97316'}" stroke-width="1.8" stroke-dasharray="${isPreview ? '5 3' : '0'}" opacity=".8"/>`;
    g += `<circle cx="${xn}" cy="${Y(vn)}" r="6" fill="${isPreview ? '#0EA5E9' : '#F97316'}" stroke="#fff" stroke-width="2.5"/>`;
  } else {
    const yMid = padT + tideH / 2;
    const isFresh = active.water === 'fresh';
    const msg = sd?.loading ? 'Fetching live tide data…'
      : isFresh ? 'Freshwater — solunar + light scoring'
      : 'Add a NOAA Station ID to enable tide data';
    g += `<line x1="${padL}" y1="${yMid}" x2="${Wd - padR}" y2="${yMid}" stroke="rgba(0,0,0,.07)" stroke-dasharray="6 5"/>`;
    g += `<text x="${Wd/2}" y="${yMid - 10}" fill="#9CA3AF" font-family="Space Grotesk" font-size="14" font-weight="600" text-anchor="middle">${msg}</text>`;
    if (!isFresh && !sd?.loading)
      g += `<text x="${Wd/2}" y="${yMid + 16}" fill="#F97316" font-family="Space Grotesk" font-size="12" font-weight="500" text-anchor="middle">tidesandcurrents.noaa.gov → find your station → edit spot</text>`;
    const xn = Xm(nowMin);
    g += `<line x1="${xn}" y1="${padT}" x2="${xn}" y2="${stripY + stripH}" stroke="${isPreview ? '#0EA5E9' : '#F97316'}" stroke-width="1.8" opacity=".8"/>`;
  }

  // ── Sun rise/set ─────────────────────────────────────────────────────────
  if (sd?.ctx?.times) {
    [[sd.ctx.times.sunrise,'☀ Rise'],[sd.ctx.times.sunset,'☀ Set']].forEach(([t,lbl]) => {
      if (!t) return;
      const m = (+t - +dayStart) / MIN;
      if (m < 0 || m > 1440) return;
      const x = Xm(m);
      g += `<line x1="${x}" y1="${padT}" x2="${x}" y2="${stripY}" stroke="rgba(251,191,36,.45)" stroke-width="1" stroke-dasharray="4 4"/>`;
      g += `<text x="${x}" y="${footY}" fill="#D97706" font-family="Space Grotesk" font-size="10" font-weight="600" text-anchor="middle">${lbl}</text>`;
    });
  }

  svg.innerHTML = g;
  $('xaxis').innerHTML = ['12a','4a','8a','12p','4p','8p','12a'].map(t=>`<span>${t}</span>`).join('');
  $('nowLabel').textContent = (isPreview ? 'Preview · ' : 'Now · ') + fmt(nowMin);
  $('nowLabel').className = 'now-t' + (isPreview ? ' preview' : '');
  $('resetNow').hidden = !isPreview;
}

function renderReadout() {
  const r = scoreAt(active, nowMin), b = band(r.s);
  const col = b === 'prime' ? 'var(--green)' : b === 'good' ? 'var(--amber)' : b === 'fair' ? 'var(--cyan)' : 'var(--ink-dim)';
  $('scoreNum').innerHTML = `${r.s}`; $('scoreNum').style.color = col;
  $('scoreLab').textContent = labl(r.s); $('scoreLab').style.color = col;
  const hasExtrema = active.extrema?.length || spotData[active.id]?.ctx?.extrema?.length;
  $('scoreDir').textContent = hasExtrema
    ? `Tide ${r.dir}`
    : active.water === 'fresh' ? 'Freshwater · solunar driven'
    : 'No station · solunar + light only';
  $('roTime').textContent = isPreview ? fmt(nowMin) : 'now';
  const set = (bar, val, vn) => { $(bar).style.width = Math.round(val * 100) + '%'; $(vn).textContent = Math.round(val * 100); };
  set('bTide', r.tide, 'vTide'); set('bSol', r.sol, 'vSol'); set('bLight', r.light, 'vLight');
  if (active.water === 'fresh') $('vTide').textContent = 'n/a';
}

function renderWindows() {
  const ws = winAt(active);
  if (!ws.length) {
    $('winList').innerHTML = `<div class="win-empty">No window clears the bite threshold today.<br>Slow grind — fish the best of what's there.</div>`;
    return;
  }
  const durStr = (s, e) => {
    const mins = ((e % 1440) - (s % 1440) + 1440) % 1440;
    return mins >= 60 ? `${Math.floor(mins/60)}h ${mins%60 ? (mins%60)+'m' : ''}`.trim() : `${mins}m`;
  };
  $('winList').innerHTML = ws.map(w => {
    const b = band(w.pk);
    const tide = active.water === 'fresh' ? 'solunar peak' : (w.dir === 'incoming' ? '↑ incoming' : w.dir === 'outgoing' ? '↓ outgoing' : 'slack');
    const dur = durStr(w.s, w.e);
    return `<li data-band="${b}">
      <span class="rng">${fmt(w.s)} – ${fmt(w.e)}<small>${dur} · ${tide}</small><span class="win-peak">Peak&nbsp;${fmt(w.pkm)}</span></span>
      <span></span>
      <span class="pk" data-band="${b}">${w.pk}</span>
    </li>`;
  }).join('');
}

function renderFish() {
  $('fishCount').textContent = active.fish.length + ' species';
  $('fishGrid').innerHTML = active.fish.map(ref => {
    const f = FISHDB[ref.slug];
    if (!f) return '';
    const photo = 'images/fish/' + ref.slug + '.png';
    const vector = 'images/fish/vector/' + ref.slug + '.png';
    const r1 = f.rigs[0], rest = f.rigs.slice(1);
    const regs = f.regs;
    const regsHtml = regs ? `<div class="reg-bar">
      ${regs.size ? `<span class="reg-item"><span>MIN</span> ${regs.size}</span>` : ''}
      ${regs.bag ? `<span class="reg-item"><span>BAG</span> ${regs.bag}</span>` : ''}
      ${regs.season ? `<span class="reg-item"><span>SEASON</span> ${regs.season}</span>` : ''}
      <span class="reg-verify">Verify CDFW regs before fishing</span>
    </div>` : '';
    return `<div class="card">
      <div class="plate"><img src="${photo}" alt="${f.n}" loading="lazy" data-fb="${vector}" onerror="if(this.dataset.fb){this.src=this.dataset.fb;this.dataset.fb='';}else{this.style.display='none';this.parentNode.innerHTML='<span class=ph>NO PLATE</span>';}"/></div>
      <div class="cbody">
        <div class="fh"><div><div class="fn">${f.n}</div><div class="sci">${f.s}</div></div>
          <div class="pref"><span>tide</span> ${ref.tide}<br><span>light</span> ${ref.light}</div></div>
        <div class="cd"><div><div class="k">Cast</div><div class="v">${f.cast}</div></div><div><div class="k">Depth</div><div class="v">${f.depth}</div></div></div>
        <div class="rigs">
          <div class="rig1"><div class="badge"><b>01</b> · Top pick</div><div class="rn">${r1.name}</div><div class="rd">${r1.detail}</div><div class="rl">${r1.line}</div></div>
          ${rest.map((r, i) => `<div class="rigN"><div class="ix">0${i + 2}</div><div><div class="rn">${r.name}</div><div class="rd">${r.detail}</div><div class="rl">${r.line}</div></div></div>`).join('')}
        </div>
        ${regsHtml}
        <div class="note">${ref.note}</div>
      </div></div>`;
  }).join('');
}

function renderAll() { renderRail(); renderHead(); renderInstrument(); renderReadout(); renderWindows(); renderFish(); }

// ── Tide SVG scrub interaction ─────────────────────────────────────────────
let dragging = false;
const svg = $('tideSvg');
function scrub(e) {
  const rect = svg.getBoundingClientRect();
  const cx = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
  nowMin = clamp(Math.round(cx / rect.width * 1440), 0, 1440);
  isPreview = Math.abs(nowMin - realNow) > 7;
  renderInstrument(); renderReadout();
}
svg.addEventListener('pointerdown', e => { dragging = true; svg.setPointerCapture(e.pointerId); scrub(e); });
svg.addEventListener('pointermove', e => { if (dragging) scrub(e); });
svg.addEventListener('pointerup', () => dragging = false);
$('resetNow').onclick = () => { nowMin = realNow; isPreview = false; renderInstrument(); renderReadout(); };

// ── Add-spot modal ────────────────────────────────────────────────────────
const modal = $('addSpotModal');
const addSpotBtn = $('addSpotBtn');
const closeModalBtn = $('closeModal');
const cancelModalBtn = $('cancelModal');
const addSpotForm = $('addSpotForm');
const speciesRowsEl = $('speciesRows');
const addSpeciesRowBtn = $('addSpeciesRowBtn');

// ── Leaflet map picker ────────────────────────────────────────────────────
let leafletMap = null;
let leafletPin = null;
const BAND_COLORS = { prime: '#74E0A0', good: '#FFB03A', fair: '#4FC4D6', slow: '#5C696C' };

function initLeafletMap() {
  leafletMap = L.map('spotPickerMap', { zoomControl: true }).setView([33.62, -117.80], 10);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18,
  }).addTo(leafletMap);

  // Existing spots as score-colored circle markers
  SPOTS.forEach(sp => {
    const sc = spotData[sp.id];
    const s = sc?.ctx ? scoreAt(sp, nowMin).s : 50;
    const b = band(s);
    const col = BAND_COLORS[b];
    L.circleMarker([sp.lat, sp.lon], {
      radius: 9, color: col, fillColor: col, fillOpacity: 0.85, weight: 2,
    }).addTo(leafletMap)
      .bindTooltip(`<b>${sp.name}</b><br>${s}/100 ${labl(s)}`, { permanent: false, direction: 'top' });
  });

  // Click anywhere to drop the pin
  leafletMap.on('click', e => placePin(e.latlng.lat, e.latlng.lng));
}

function placePin(lat, lng) {
  const rlat = Math.round(lat * 10000) / 10000;
  const rlng = Math.round(lng * 10000) / 10000;
  $('f-lat').value = rlat;
  $('f-lon').value = rlng;
  if (leafletPin) {
    leafletPin.setLatLng([lat, lng]);
  } else {
    leafletPin = L.marker([lat, lng]).addTo(leafletMap);
  }
}

// Sync typed lat/lon → map pin
function syncPinFromInputs() {
  if (!leafletMap) return;
  const lat = parseFloat($('f-lat').value);
  const lng = parseFloat($('f-lon').value);
  if (!isNaN(lat) && !isNaN(lng)) {
    if (leafletPin) { leafletPin.setLatLng([lat, lng]); }
    else { leafletPin = L.marker([lat, lng]).addTo(leafletMap); }
    leafletMap.panTo([lat, lng]);
  }
}

function openModal() {
  modal.hidden = false;
  document.body.style.overflow = 'hidden';
  // Init map on first open; invalidate size on subsequent opens
  setTimeout(() => {
    if (!leafletMap) initLeafletMap();
    else leafletMap.invalidateSize();
  }, 60);
}

function closeModal() {
  modal.hidden = true;
  document.body.style.overflow = '';
  addSpotForm.reset();
  speciesRowsEl.innerHTML = '';
  editingSpotId = null;
  $('modalTitle').textContent = 'Add Spot';
  if (leafletPin && leafletMap) { leafletMap.removeLayer(leafletPin); leafletPin = null; }
}

let editingSpotId = null;

function openModalForEdit(sp) {
  editingSpotId = sp.id;
  $('modalTitle').textContent = 'Edit Spot';
  $('f-name').value = sp.name;
  $('f-station').value = sp.station || '';
  $('f-lat').value = sp.lat;
  $('f-lon').value = sp.lon;
  $('f-tags').value = (sp.tags || []).join(', ');
  addSpotForm.querySelector(`input[name="water"][value="${sp.water}"]`).checked = true;
  speciesRowsEl.innerHTML = '';
  (sp.fish || []).forEach((f, idx) => {
    addSpeciesRowBtn.click();
    const row = speciesRowsEl.children[idx];
    row.querySelector(`[name="slug_${idx}"]`).value = f.slug;
    row.querySelector(`[name="tide_${idx}"]`).value = f.tide || 'any';
    row.querySelector(`[name="light_${idx}"]`).value = f.light || 'dawn';
    row.querySelector(`[name="note_${idx}"]`).value = f.note || '';
  });
  openModal();
  // place existing pin on map after map init
  setTimeout(() => { if (sp.lat && sp.lon) placePin(sp.lat, sp.lon); updateNearestStationHint(); }, 120);
}

addSpotBtn.onclick = e => {
  e.preventDefault();
  editingSpotId = null;
  $('modalTitle').textContent = 'Add Spot';
  openModal();
};
closeModalBtn.onclick = closeModal;
cancelModalBtn.onclick = closeModal;
modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });

function buildSpeciesOptions() {
  return Object.entries(FISHDB).map(([slug, f]) => `<option value="${slug}">${f.n}</option>`).join('');
}

addSpeciesRowBtn.onclick = () => {
  const idx = speciesRowsEl.children.length;
  const row = document.createElement('div');
  row.className = 'sp-row';
  row.innerHTML = `
    <select class="form-select" name="slug_${idx}"><option value="">Species…</option>${buildSpeciesOptions()}</select>
    <select class="form-select" name="tide_${idx}">
      <option value="any">any tide</option><option value="incoming">incoming</option>
      <option value="outgoing">outgoing</option><option value="—">—</option>
    </select>
    <select class="form-select" name="light_${idx}">
      <option value="dawn">dawn</option><option value="dusk">dusk</option>
      <option value="midday">midday</option><option value="night">night</option><option value="any">any light</option>
    </select>
    <input class="form-input" name="note_${idx}" type="text" placeholder="Short note…">
    <button type="button" class="btn-rm-sp" title="Remove">×</button>`;
  row.querySelector('.btn-rm-sp').onclick = () => row.remove();
  speciesRowsEl.appendChild(row);
};

addSpotForm.onsubmit = e => {
  e.preventDefault();
  const fd = new FormData(addSpotForm);
  const name = fd.get('name')?.trim();
  const lat = parseFloat(fd.get('lat'));
  const lon = parseFloat(fd.get('lon'));
  if (!name || isNaN(lat) || isNaN(lon)) { alert('Name, latitude, and longitude are required.'); return; }
  const water = fd.get('water') || 'salt';
  const station = fd.get('station')?.trim() || null;
  const tagsRaw = fd.get('tags')?.trim() || '';
  const tags = tagsRaw ? tagsRaw.split(',').map(t => t.trim()).filter(Boolean) : [];
  const fish = [];
  speciesRowsEl.querySelectorAll('.sp-row').forEach((row, idx) => {
    const slug = row.querySelector(`[name="slug_${idx}"]`)?.value;
    if (!slug) return;
    fish.push({
      slug,
      tide: row.querySelector(`[name="tide_${idx}"]`)?.value || 'any',
      light: row.querySelector(`[name="light_${idx}"]`)?.value || 'dawn',
      note: row.querySelector(`[name="note_${idx}"]`)?.value?.trim() || '',
    });
  });
  if (editingSpotId) {
    // Update existing custom spot in-place
    const idx = SPOTS.findIndex(s => s.id === editingSpotId);
    if (idx !== -1) {
      const existing = SPOTS[idx];
      SPOTS[idx] = { ...existing, name, lat, lon, station: station || null, water, tags, fish };
      // Clear cached live data so it refetches with the new station
      delete spotData[editingSpotId];
      localStorage.removeItem(`hooked_v1_${editingSpotId}_${TODAY_ISO}`);
      // Persist updated custom spots
      const customs = SPOTS.filter(s => s._custom);
      localStorage.setItem(CUSTOM_KEY, JSON.stringify(customs));
      if (active?.id === editingSpotId) active = SPOTS[idx];
      closeModal();
      initSampleCtx(SPOTS[idx]);
      renderAll();
      loadLiveData(SPOTS[idx]);
    }
  } else {
    const id = 'custom_' + name.toLowerCase().replace(/[^a-z0-9]+/g, '_') + '_' + Date.now().toString(36);
    const spot = { id, _custom: true, name, lat, lon, station: station || null, water, tags, extrema: null, cond: {}, fish };
    closeModal();
    addCustomSpot(spot);
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

// ── NOAA station lookup — fetch all tide stations once, cache in localStorage ─
const NOAA_CACHE_KEY = 'hooked_noaa_stations_v1';
let _noaaStations = null;

async function getNoaaStations() {
  if (_noaaStations) return _noaaStations;
  try {
    const cached = localStorage.getItem(NOAA_CACHE_KEY);
    if (cached) { _noaaStations = JSON.parse(cached); return _noaaStations; }
  } catch {}
  try {
    const res = await fetch('https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json?type=tidepredictions&units=english');
    const data = await res.json();
    // Slim down to just what we need: id, name, lat, lng
    _noaaStations = (data.stations || []).map(s => ({ id: s.id, name: s.name, lat: s.lat, lng: s.lng }));
    try { localStorage.setItem(NOAA_CACHE_KEY, JSON.stringify(_noaaStations)); } catch {}
    return _noaaStations;
  } catch { return []; }
}

function haversineKm(lat1, lon1, lat2, lon2) {
  const R = 6371, dLat = (lat2 - lat1) * Math.PI / 180, dLon = (lon2 - lon1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180) * Math.cos(lat2*Math.PI/180) * Math.sin(dLon/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

// ── Lat/lon inputs → move map pin + nearest station hint ─────────────────
async function updateNearestStationHint() {
  const lat = parseFloat($('f-lat').value);
  const lon = parseFloat($('f-lon').value);
  const hint = $('nearestStationHint');
  const stationInput = $('f-station');
  if (!hint || isNaN(lat) || isNaN(lon)) return;

  // Only for salt water spots
  const waterVal = document.querySelector('input[name="water"]:checked')?.value;
  if (waterVal !== 'salt') { hint.textContent = ''; return; }

  hint.innerHTML = ' <i style="color:#9CA3AF">Looking up nearest station…</i>';
  const stations = await getNoaaStations();
  if (!stations.length) { hint.textContent = ''; return; }

  let best = null, bestDist = Infinity;
  for (const s of stations) {
    const d = haversineKm(lat, lon, s.lat, s.lng);
    if (d < bestDist) { bestDist = d; best = s; }
  }
  if (!best) { hint.textContent = ''; return; }

  const km = bestDist.toFixed(1), mi = (bestDist * 0.621).toFixed(1);
  hint.innerHTML = ` Nearest: <b>${best.name}</b> · ID <b>${best.id}</b> · ${mi} mi away.
    <a href="#" style="color:var(--amber);font-weight:700;margin-left:6px" id="useStationBtn">Use this</a>`;
  $('useStationBtn')?.addEventListener('click', e => {
    e.preventDefault();
    stationInput.value = best.id;
    hint.innerHTML = ` ✓ Auto-filled station <b>${best.id}</b> (${best.name}, ${mi} mi).`;
  });
}
$('f-lat').addEventListener('input', () => { syncPinFromInputs(); updateNearestStationHint(); });
$('f-lon').addEventListener('input', () => { syncPinFromInputs(); updateNearestStationHint(); });

// ── Water type toggle in modal ────────────────────────────────────────────
document.querySelectorAll('input[name="water"]').forEach(r => r.onchange = () => {
  const isSalt = document.querySelector('input[name="water"]:checked')?.value === 'salt';
  $('stationRow').hidden = !isSalt;
});

// ── Init ──────────────────────────────────────────────────────────────────
(async function init() {
  try {
    const [locs, fish] = await Promise.all([
      fetch('data/locations.json').then(r => r.json()),
      fetch('data/species.json').then(r => r.json()),
    ]);
    FISHDB = fish.species;
    SPOTS = locs.locations;
    // Merge custom spots from localStorage
    loadCustomSpots().forEach(sp => SPOTS.push(sp));
    // Build sample contexts for all spots immediately (enables instant render)
    SPOTS.forEach(sp => initSampleCtx(sp));
    active = SPOTS[0];
    realNow = nowMin = clamp(today.getHours() * 60 + today.getMinutes(), 0, 1440);
    renderAll();
    // Kick off live data fetch for the first spot
    loadLiveData(active);
  } catch (e) {
    console.error(e);
    document.querySelector('.main').innerHTML =
      '<p style="font-family:monospace;color:#9AA7A8;padding:48px;max-width:560px;line-height:1.7">Could not load <b>data/*.json</b>. This app must be served over http — run <b>make serve</b> and open the localhost URL.</p>';
  }
})();
