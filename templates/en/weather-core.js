(() => {
  'use strict';
  const HOUR = 3600000, DAY = 24 * HOUR, CACHE_PREFIX = 'meiyu-decision-en-v1-';
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const utcISO = ms => new Date(ms).toISOString().replace('.000Z', 'Z');

  function windowSpecs(at = Date.now()) {
    const d = new Date(at + 8 * HOUR);
    const first = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1);
    return Array.from({length: 7}, (_, i) => ({
      start_utc: utcISO(first + i * DAY),
      end_utc: utcISO(first + (i + 1) * DAY),
    }));
  }

  function requestURL(input, key, windows) {
    const location = input.locations?.[key];
    if (!location || !input.model || windows.length !== 7) throw Error('Weather source identity is incomplete.');
    const query = new URLSearchParams({
      latitude: String(location.latitude),
      longitude: String(location.longitude),
      models: input.model,
      hourly: 'precipitation',
      start_hour: new Date(Date.parse(windows[0].start_utc) + HOUR).toISOString().slice(0, 16),
      end_hour: windows[6].end_utc.slice(0, 16),
      timezone: 'UTC',
      timeformat: 'iso8601',
      precipitation_unit: 'mm',
      cell_selection: 'nearest',
    });
    return 'https://ensemble-api.open-meteo.com/v1/ensemble?' + query;
  }

  function apiHour(value) {
    if (typeof value !== 'string' || !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:00(?::00)?(?:Z|\+00:00)?$/.test(value)) {
      throw Error('Response timestamps must be whole UTC hours.');
    }
    const ms = Date.parse(/Z$|\+00:00$/.test(value) ? value : value + 'Z');
    if (!Number.isFinite(ms)) throw Error('Response timestamp is invalid.');
    return ms;
  }

  async function sha256(raw) {
    if (typeof raw !== 'string' || !globalThis.crypto?.subtle) throw Error('SHA-256 validation is unavailable.');
    return [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw)))]
      .map(value => value.toString(16).padStart(2, '0')).join('');
  }

  function stable(value) {
    if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']';
    if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + stable(value[key])).join(',') + '}';
    return JSON.stringify(value);
  }

  async function parseRaw(raw, {input, key, fetched, windows, url, allowPartial = false}) {
    let body;
    try { body = JSON.parse(raw); } catch { throw Error('Weather response is not valid JSON.'); }
    const grid = input.grids?.[key], members = Number(input.expected_members);
    if (!body || Array.isArray(body) || body.error) throw Error('The weather API returned an error.');
    if (!grid || body.latitude !== grid.latitude || body.longitude !== grid.longitude) throw Error('Response grid does not match; cache was not replaced.');
    if (body.utc_offset_seconds !== 0 || !['GMT', 'UTC'].includes(body.timezone)) throw Error('Response is not in UTC.');
    if (!Array.isArray(windows) || windows.length !== 7 || windows.some((window, index) => {
      const start = Date.parse(window.start_utc), end = Date.parse(window.end_utc);
      return !Number.isFinite(start) || !Number.isFinite(end) || end - start !== DAY || (index > 0 && window.start_utc !== windows[index - 1].end_utc);
    })) throw Error('The 24-hour windows are invalid.');
    if (url !== requestURL(input, key, windows)) throw Error('Request source or window does not match.');
    if (!Number.isInteger(members) || members < 1) throw Error('The expected ensemble member count is invalid.');
    const hourly = body.hourly, units = body.hourly_units;
    if (!hourly || !units || !Array.isArray(hourly.time) || (units.time !== undefined && units.time !== 'iso8601')) throw Error('Hourly fields or units are missing.');
    if (units.precipitation !== undefined && units.precipitation !== 'mm') throw Error('Precipitation unit is not millimetres.');
    const expected = new Set(windows.flatMap(window => Array.from({length: 24}, (_, index) => Date.parse(window.start_utc) + (index + 1) * HOUR)));
    const times = hourly.time.map(apiHour);
    if (new Set(times).size !== times.length || times.some(time => !expected.has(time))) throw Error('Hourly data is duplicated or outside the requested windows.');
    const perturbed = Object.keys(hourly).filter(name => /^precipitation_member[0-9]+$/.test(name));
    const allowed = ['precipitation', ...Array.from({length: members - 1}, (_, index) => 'precipitation_member' + String(index + 1).padStart(2, '0'))];
    if (perturbed.some(name => !allowed.includes(name))) throw Error('Ensemble member identity does not match.');
    if (!allowPartial && allowed.some(name => !Object.hasOwn(hourly, name))) throw Error('Expected ensemble members are missing.');
    const fields = [...(Object.hasOwn(hourly, 'precipitation') ? ['precipitation'] : []), ...perturbed], values = {};
    for (const name of fields) {
      if (units[name] !== 'mm' || !Array.isArray(hourly[name]) || hourly[name].length > times.length) throw Error('Member units or length are invalid.');
      if (hourly[name].some(value => value !== null && (!finite(value) || value < 0))) throw Error('Precipitation contains an invalid value.');
      values[name] = new Map(hourly[name].map((value, index) => [times[index], value]));
    }
    const rows = windows.map(window => {
      const required = Array.from({length: 24}, (_, index) => Date.parse(window.start_utc) + (index + 1) * HOUR), totals = [], counts = [];
      for (const name of allowed) {
        const valuesForMember = required.map(time => values[name]?.get(time)).filter(finite);
        counts.push(valuesForMember.length);
        if (valuesForMember.length === 24) totals.push(valuesForMember.reduce((sum, value) => sum + value, 0));
      }
      totals.sort((a, b) => a - b);
      const complete = totals.length === members && Math.min(...counts) === 24;
      const events = totals.length ? totals.filter(total => total >= 25).length : null;
      const median = totals.length ? (totals[Math.floor((totals.length - 1) / 2)] + totals[Math.ceil((totals.length - 1) / 2)]) / 2 : null;
      const rounded = value => value === null ? null : Math.round((value + Number.EPSILON) * 1000) / 1000;
      return {...window, probability: complete ? events / members : null, complete, members_valid: totals.length, members_expected: members, hours_min: Math.min(...counts), hours_expected: 24, event_members: events, rain_median_mm: rounded(median), rain_min_mm: rounded(totals.length ? totals[0] : null), rain_max_mm: rounded(totals.length ? totals.at(-1) : null)};
    });
    if (!allowPartial && rows.some(window => !window.complete)) throw Error('Expected ensemble members or hours are incomplete.');
    return {schema_version: 1, location_key: key, location: input.locations[key], source: input.source, request_url: url, fetched_at_utc: fetched, raw_sha256: await sha256(raw), probability_kind: 'ensemble_member_fraction_uncalibrated', event_threshold_mm: 25, expected_members: members, windows: rows};
  }

  function resultStatus(snapshot, error = null, now = Date.now()) {
    if (!snapshot) return {status: error ? 'error' : 'missing', snapshot: null, error};
    const age = now - Date.parse(snapshot.fetched_at_utc), validTime = Number.isFinite(age) && age >= -300000 && age <= 3 * HOUR;
    return {status: !validTime ? 'stale' : snapshot.windows.every(window => window.complete) ? 'fresh' : 'partial', snapshot, error};
  }

  async function readCache(input, key, cacheKey = CACHE_PREFIX, allowPartial = false) {
    const packed = JSON.parse(localStorage.getItem(cacheKey + key) || 'null');
    if (!packed) return null;
    const summary = packed.snapshot;
    if (!summary || typeof packed.raw !== 'string' || !Array.isArray(summary.windows)) throw Error('Cached weather raw data is missing.');
    const parsed = await parseRaw(packed.raw, {input, key, fetched: summary.fetched_at_utc, windows: summary.windows.map(window => ({start_utc: window.start_utc, end_utc: window.end_utc})), url: summary.request_url, allowPartial});
    if (stable(parsed) !== stable(summary)) throw Error('Cached summary or raw weather content does not match.');
    return parsed;
  }

  globalThis.MeiYuWeatherCore = {HOUR, DAY, CACHE_PREFIX, windowSpecs, requestURL, sha256, parseRaw, resultStatus, readCache};
})();
