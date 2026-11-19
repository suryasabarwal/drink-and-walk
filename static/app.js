'use strict';

/* ---------- tiny helpers ---------- */
const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'class') el.className = v;
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const api = async (path, opts) => {
  let r;
  try { r = await fetch(path, opts); } catch (e) { throw new Error('No connection. Check your internet and try again.'); }
  let j = {};
  try { j = await r.json(); } catch (e) { /* not json */ }
  if (!r.ok) throw new Error(j.error || 'Something broke on our end. Try again in a minute.');
  return j;
};
const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const pad = n => String(n).padStart(2, '0');
const iso = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const fromIso = s => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
const fmtDay = d => d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const nights = () => S.start && S.end ? Math.round((fromIso(S.end) - fromIso(S.start)) / 864e5) + 1 : 0;
const put = (el, ...kids) => el.append(...kids.flat().filter(k => k != null && k !== false));
const say = t => { $('#live').textContent = ''; setTimeout(() => { $('#live').textContent = t; }, 30); };

/* ---------- state ---------- */
const FLOW = ['city', 'dates', 'group', 'start', 'vibe'];
const S = {
  step: 'home', flow: 'plan', city: null, start: '', end: '', people: 4, budget: 50,
  stay: null, vibe: 'dive', live: false, late: false, free: false, radius: 1500,
  plan: null, night: 0, anchors: null, anchorErr: '', locResults: null, picks: {},
  near: { mode: 'drink', results: null, at: null, note: '', err: '' },
};

/* ---------- navigation ---------- */
function go(step, push = true) {
  S.step = step;
  if (push) history.pushState({ step }, '');
  render();
  window.scrollTo(0, 0);
}
window.addEventListener('popstate', e => { S.step = (e.state && e.state.step) || 'home'; render(); });
function backStep() {
  const i = FLOW.indexOf(S.step);
  if (S.step === 'loading' || S.step === 'plan' || S.step === 'error') return 'vibe';
  if (S.step === 'nearby' || S.step === 'nearcity') return 'home';
  return i <= 0 ? 'home' : FLOW[i - 1];
}

function render() {
  const app = $('#app');
  app.replaceChildren();
  const bar = $('#barinner');
  bar.replaceChildren();
  $('#bar').hidden = true;
  const i = FLOW.indexOf(S.step);
  $('#back').hidden = S.step === 'home';
  $('#progress').hidden = i < 0;
  $('#progress i').style.width = i >= 0 ? `${((i + 1) / FLOW.length) * 100}%` : '0';
  $('#stepnote').textContent = i >= 0 ? `Step ${i + 1} of ${FLOW.length}` : '';
  (VIEWS[S.step] || VIEWS.home)(app, bar);
  const focus = $('h1, h2', app);
  if (focus) { focus.setAttribute('tabindex', '-1'); focus.focus({ preventScroll: true }); }
}

function setBar(bar, { label, onclick, ok, why, extra }) {
  $('#bar').hidden = false;
  bar.append(h('p', { class: 'why', 'aria-live': 'polite' }, ok ? '' : why || ''));
  if (extra) bar.append(extra);
  bar.append(h('button', { class: 'btn primary', onclick, disabled: !ok }, label));
}

/* ---------- toast and sheet ---------- */
let toastTimer;
function toast(msg, undo) {
  $('#toast')?.remove();
  const t = h('div', { class: 'toast', id: 'toast', role: 'status' }, h('span', {}, msg),
    undo ? h('button', { onclick: () => { undo(); t.remove(); } }, 'Undo') : null);
  document.body.append(t);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.remove(), 5000);
}
function sheet(title, content) {
  const close = () => scrim.remove();
  const scrim = h('div', { class: 'scrim', onclick: e => { if (e.target === scrim) close(); } },
    h('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
      h('h2', {}, title), content(close)));
  document.body.append(scrim);
  const first = $('input, button', scrim); if (first) first.focus();
  scrim.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  return close;
}

/* ---------- views ---------- */
const VIEWS = {};

VIEWS.home = app => {
  put(app, 
    h('h1', {}, 'Plan a cheap night out.'),
    h('p', { class: 'lead' }, 'A cheap night out for friends splitting the bill. Pick a city and where you are starting. We build a walking route of cheap food, happy hours and live music.'),
    h('button', { class: 'choice big', onclick: () => { S.flow = 'plan'; go('city'); } },
      h('div', {}, h('b', {}, 'Plan a trip'), h('span', { class: 'd' }, 'Pick a city, dates and a starting point. Five quick questions.'))),
    h('button', { class: 'choice big', onclick: startNearby },
      h('div', {}, h('b', {}, "I'm out right now"), h('span', { class: 'd' }, "Skip the planning. See what's cheap and open within walking distance."))),
    h('div', { class: 'how' },
      h('h3', {}, 'How it works'),
      ...[['1', 'Tell us the city, dates, how many of you and your budget.'],
          ['2', 'Tell us where you are staying or landing, so every walk starts from there.'],
          ['3', 'Get a route with cheap stops in order, walking times, and a running total. Swap anything you do not like.']]
        .map(([n, t]) => h('div', {}, h('span', { class: 'n' }, n), h('span', {}, t)))),
    credits(),
  );
};

function credits() {
  return h('p', { class: 'credits' },
    'Map data from ',
    h('a', { href: 'https://www.openstreetmap.org/copyright', target: '_blank', rel: 'noopener' }, 'OpenStreetMap contributors'),
    '. Weather from ',
    h('a', { href: 'https://open-meteo.com/', target: '_blank', rel: 'noopener' }, 'Open-Meteo'),
    '. Prices are estimates from the type of place, so call or check the menu before you go. We do not store your location.');
}

/* --- step 1: city --- */
VIEWS.city = (app, bar) => cityView(app, bar, 'Where are you headed?', 'Start typing a city. Pick it from the list.', () => go('dates'), 'Next');
VIEWS.nearcity = (app, bar) => cityView(app, bar, 'Which city are you in?', 'We could not get your location, so pick your city and we will search from the center.', () => loadNearby({ lat: S.city.lat, lon: S.city.lon }, 'Searching from the center of ' + S.city.name + '.'), 'Show cheap spots');

function cityView(app, bar, title, lead, next, label) {
  let timer, results = [], active = -1;
  const status = h('p', { class: 'help', 'aria-live': 'polite' }, '');
  const list = h('ul', { class: 'list', role: 'listbox', id: 'citylist', hidden: true });
  const picked = h('div', {});
  const input = h('input', { type: 'search', id: 'city', autocomplete: 'off', 'aria-autocomplete': 'list', 'aria-controls': 'citylist', placeholder: 'Austin, Lisbon, Osaka...', value: S.city ? S.city.label : '' });
  const paint = () => {
    list.replaceChildren(...results.map((c, i) => h('li', { role: 'presentation' },
      h('button', { role: 'option', 'aria-selected': String(i === active), onclick: () => choose(c) }, c.label))));
    list.hidden = !results.length;
  };
  const choose = c => {
    S.city = c; S.stay = null; S.anchors = null; S.locResults = null; S.picks = {};
    input.value = c.label; results = []; paint(); status.textContent = ''; showPicked(); refreshBar();
  };
  const showPicked = () => picked.replaceChildren(S.city ? h('p', { class: 'good-line' }, '✓ ', S.city.label) : '');
  input.addEventListener('input', () => {
    S.city = null; showPicked(); refreshBar();
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { results = []; paint(); status.textContent = ''; return; }
    timer = setTimeout(async () => {
      try {
        status.textContent = 'Searching...';
        const j = await api('/api/cities?q=' + encodeURIComponent(q));
        if (input.value.trim() !== q) return;
        results = j.results; active = -1; paint();
        status.textContent = results.length ? '' : 'No match. Try the main city name.';
      } catch (e) { status.textContent = e.message; }
    }, 250);
  });
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' && results.length) { active = (active + 1) % results.length; paint(); e.preventDefault(); }
    else if (e.key === 'ArrowUp' && results.length) { active = (active - 1 + results.length) % results.length; paint(); e.preventDefault(); }
    else if (e.key === 'Enter' && active >= 0) { choose(results[active]); e.preventDefault(); }
  });
  put(app, h('h2', {}, title), h('p', { class: 'lead' }, lead),
    h('label', { class: 'field' }, h('span', { class: 'sr' }, 'City'), input), status, list, picked);
  showPicked();
  function refreshBar() {
    bar.replaceChildren();
    setBar(bar, { label, onclick: next, ok: !!S.city, why: 'Pick a city from the list to continue.' });
  }
  refreshBar();
}

/* --- step 2: dates --- */
VIEWS.dates = (app, bar) => {
  const today = new Date();
  const nextDow = (from, dow) => addDays(from, (dow - from.getDay() + 7) % 7);
  const weekend = off => {
    const base = addDays(today, off);
    const fri = base.getDay() === 0 || base.getDay() === 6 || base.getDay() === 5 ? base : nextDow(base, 5);
    const sun = nextDow(fri, 0);
    return [fri, sun < fri ? addDays(sun, 7) : sun];
  };
  const s = h('input', { type: 'date', id: 'ds', min: iso(today), value: S.start });
  const e = h('input', { type: 'date', id: 'de', min: iso(today), value: S.end });
  const sum = h('p', { class: 'good-line', 'aria-live': 'polite' });
  const set = (a, b) => { S.start = iso(a); S.end = iso(b); s.value = S.start; e.value = S.end; update(); };
  const update = () => {
    S.start = s.value; S.end = e.value || s.value;
    if (S.start && !e.value) { e.value = S.start; S.end = S.start; }
    if (S.start) { e.min = S.start; e.max = iso(addDays(fromIso(S.start), 3)); }
    const n = nights();
    sum.textContent = n > 0 && n <= 4 ? `✓ ${n} ${n === 1 ? 'night' : 'nights'}: ${fmtDay(fromIso(S.start))} to ${fmtDay(fromIso(S.end))}` : '';
    refreshBar();
  };
  s.addEventListener('change', update); e.addEventListener('change', update);
  const sat = nextDow(today, 6);
  put(app, h('h2', {}, 'When are you going?'),
    h('p', { class: 'lead' }, 'Up to four nights. Dates matter because hours, happy hours and crowds change by day.'),
    h('div', { class: 'chips' },
      h('button', { class: 'chip', onclick: () => set(...weekend(0)) }, 'This weekend'),
      h('button', { class: 'chip', onclick: () => set(...weekend(7)) }, 'Next weekend'),
      h('button', { class: 'chip', onclick: () => set(sat, sat) }, 'Just this Saturday')),
    h('div', { class: 'row', style: 'margin-top:16px' },
      h('label', { class: 'field' }, h('span', {}, 'First night'), s),
      h('label', { class: 'field' }, h('span', {}, 'Last night'), e)),
    sum);
  function refreshBar() {
    bar.replaceChildren();
    const n = nights();
    const ok = n >= 1 && n <= 4;
    setBar(bar, { label: 'Next', onclick: () => go('group'), ok, why: !S.start ? 'Pick your dates to continue.' : 'Pick 1 to 4 nights, with the last night on or after the first.' });
  }
  update();
};

/* --- step 3: group and budget --- */
VIEWS.group = (app, bar) => {
  const count = h('output', { 'aria-live': 'polite' }, String(S.people));
  const money = h('div', { class: 'money', 'aria-live': 'polite' }, '$' + S.budget);
  const dec = h('button', { 'aria-label': 'One fewer person', onclick: () => bump(-1) }, '−');
  const inc = h('button', { 'aria-label': 'One more person', onclick: () => bump(1) }, '+');
  const bump = d => { S.people = Math.max(1, Math.min(20, S.people + d)); count.textContent = S.people; };
  const slider = h('input', { type: 'range', min: 20, max: 150, step: 5, value: S.budget, 'aria-label': 'Budget per person per night' });
  slider.addEventListener('input', () => { S.budget = +slider.value; money.textContent = '$' + S.budget; });
  put(app, h('h2', {}, 'How many of you?'),
    h('div', { class: 'stepper' }, dec, count, inc),
    h('p', { class: 'help', style: 'text-align:center' }, 'Including you.'),
    h('h3', {}, 'Your limit per person, per night'),
    money, slider,
    h('div', { class: 'chips', style: 'justify-content:center' }, ...[30, 50, 75, 100].map(v =>
      h('button', { class: 'chip', onclick: () => { S.budget = v; slider.value = v; money.textContent = '$' + v; } }, '$' + v))),
    h('p', { class: 'help' }, 'This covers food and drinks, not the ride home. If a plan runs over, we drop the last round first and tell you.'));
  setBar(bar, { label: 'Next', onclick: () => go('start'), ok: true });
};

/* --- step 4: where are you starting --- */
VIEWS.start = (app, bar) => {
  const chosen = h('div', {});
  const refresh = () => {
    chosen.replaceChildren(S.stay ? h('p', { class: 'good-line' }, '✓ Starting from: ', S.stay.name) : '');
    bar.replaceChildren();
    setBar(bar, { label: 'Next', onclick: () => go('vibe'), ok: !!S.stay, why: 'Pick a starting point to continue.' });
  };
  const pick = (name, lat, lon) => { S.stay = { name, lat, lon }; S.picks = {}; refresh(); };
  const q = h('input', { type: 'search', placeholder: 'Hotel name or street address', 'aria-label': 'Hotel name or street address', autocomplete: 'off' });
  const found = h('ul', { class: 'list', hidden: true });
  const foundNote = h('p', { class: 'help', 'aria-live': 'polite' });
  const search = async () => {
    const text = q.value.trim();
    if (text.length < 3) { foundNote.textContent = 'Type at least 3 letters.'; return; }
    foundNote.textContent = 'Searching...';
    try {
      const j = await api(`/api/locate?q=${encodeURIComponent(text)}&lat=${S.city.lat}&lon=${S.city.lon}`);
      found.replaceChildren(...j.results.map(r => h('li', { role: 'presentation' }, h('button', { onclick: () => { pick(r.label.split(',').slice(0, 2).join(',').trim(), r.lat, r.lon); found.hidden = true; } }, r.label))));
      found.hidden = !j.results.length;
      foundNote.textContent = j.results.length ? '' : 'Nothing found near ' + S.city.name + '. Try a neighborhood below.';
    } catch (e) { foundNote.textContent = e.message; }
  };
  q.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); search(); } });
  const anchorBox = h('div', {});
  const paintAnchors = () => {
    anchorBox.replaceChildren();
    if (S.anchorErr) { put(anchorBox, h('p', { class: 'help' }, S.anchorErr)); return; }
    if (!S.anchors) { put(anchorBox, h('div', { class: 'skeleton' })); return; }
    for (const kind of ['Neighborhood', 'Train station', 'Bus station']) {
      const items = S.anchors.filter(a => a.kind === kind);
      if (!items.length) continue;
      put(anchorBox, h('h3', {}, kind === 'Neighborhood' ? 'Neighborhoods' : kind + 's'),
        h('div', { class: 'chips' }, ...items.map(a => h('button', { class: 'chip', 'aria-pressed': String(!!S.stay && S.stay.name === a.name), onclick: () => { pick(a.name, a.lat, a.lon); paintAnchors(); } }, a.name))));
    }
  };
  if (!S.anchors && !S.anchorErr) {
    api(`/api/anchors?lat=${S.city.lat}&lon=${S.city.lon}`).then(j => { S.anchors = j.results; paintAnchors(); })
      .catch(e => { S.anchorErr = 'Could not load neighborhoods. Use the search box or the city center.'; paintAnchors(); });
  }
  put(app, h('h2', {}, 'Where are you staying or landing?'),
    h('p', { class: 'lead' }, 'We build the route outward from here, so the first walk is short. Hotel, rental, train station, anywhere.'),
    chosen,
    h('h3', {}, 'Search a hotel or address'),
    h('div', { class: 'row' }, q, h('button', { class: 'btn ghost', style: 'flex:none', onclick: search }, 'Search')),
    foundNote, found,
    anchorBox,
    h('h3', {}, 'Other ways'),
    h('div', { class: 'chips' },
      h('button', { class: 'chip', onclick: () => pick('the center of ' + S.city.name, S.city.lat, S.city.lon) }, 'Not sure yet, use the city center'),
      h('button', { class: 'chip', onclick: () => {
        if (!navigator.geolocation) { toast('Your browser can not share a location.'); return; }
        navigator.geolocation.getCurrentPosition(p => pick('My location', p.coords.latitude, p.coords.longitude), () => toast('Location was blocked. Pick a place from the list.'), { timeout: 10000 });
      } }, 'Use my current location')));
  paintAnchors(); refresh();
};

/* --- step 5: vibe --- */
VIEWS.vibe = (app, bar) => {
  const vibes = [['dive', 'Dive', 'Cheap pitchers, sticky floors, no pretending.'], ['chill', 'Chill', 'Sit down, talk, keep the volume low.'], ['lively', 'Lively', 'Louder rooms, patios, a little more energy.']];
  const box = h('div', {});
  const paint = () => box.replaceChildren(...vibes.map(([k, t, d]) => h('button', { class: 'choice', 'aria-pressed': String(S.vibe === k), onclick: () => { S.vibe = k; paint(); } },
    h('div', { style: 'flex:1' }, h('b', {}, t), h('span', { class: 'd' }, d)), S.vibe === k ? h('b', {}, '✓') : null)));
  paint();
  const sw = (key, title, desc) => {
    const i = h('input', { type: 'checkbox', role: 'switch' }); i.checked = S[key]; i.addEventListener('change', () => { S[key] = i.checked; });
    return h('label', { class: 'switch' }, h('div', {}, h('b', {}, title), h('small', {}, desc)), i);
  };
  put(app, h('h2', {}, "What's the mood?"), h('p', { class: 'lead' }, 'This shapes which kind of place we pick. You can swap any stop later.'),
    box, h('h3', {}, 'Extras'),
    sw('live', 'Live music', 'Make one stop a place with a band, if the map lists one.'),
    sw('late', 'Late-night food', 'End with food that is confirmed open after the bars wind down.'),
    sw('free', 'Free stuff only', 'Skip ticketed venues. Cover charges are not always listed, so ask at the door.'));
  setBar(bar, { label: 'Build my night', onclick: buildPlan, ok: true });
};

/* --- loading --- */
const WAIT = ['Asking the map where the cheap beer is.', 'Crossing out anything with "craft cocktail" in the name.', 'Checking who is open.', 'Counting walking minutes.'];
VIEWS.loading = app => {
  const line = h('p', { class: 'lead', 'aria-live': 'polite' }, WAIT[0]);
  let i = 0; const t = setInterval(() => { if (!document.body.contains(line)) return clearInterval(t); line.textContent = WAIT[++i % WAIT.length]; }, 2200);
  put(app, h('h2', {}, 'Building your night'), line, h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }));
};

VIEWS.error = (app, bar) => {
  put(app, h('h2', {}, 'That did not work'), h('p', { class: 'err', role: 'alert' }, S.error || 'Try again.'));
  setBar(bar, { label: 'Try again', onclick: buildPlan, ok: true, extra: h('button', { class: 'btn ghost', onclick: () => go('vibe') }, 'Change answers') });
};

/* ---------- plan building ---------- */
function planBody() {
  return { city: { name: S.city.name, country: S.city.country }, start: S.start, end: S.end, people: S.people, budget_pp: S.budget,
    stay: S.stay, vibe: S.vibe, live_music: S.live, late_night: S.late, free_only: S.free, radius: S.radius };
}
async function buildPlan() {
  S.step = 'loading'; render();
  try {
    S.plan = await post('/api/plan', planBody());
    S.night = 0;
    applyPicks();
    S.step = 'plan'; history.pushState({ step: 'plan' }, ''); render(); window.scrollTo(0, 0);
    say('Your plan is ready.');
  } catch (e) { S.error = e.message; S.step = 'error'; render(); }
}
function pickKey(n, slot) { return n.date + ':' + slot; }
function applyPicks() {
  let changed = false;
  for (const n of S.plan.nights) n.stops.forEach((st, i) => {
    const want = S.picks[pickKey(n, st.slot)];
    if (!want || st.place.id === want) return;
    if (n.stops.some(o => o.place.id === want)) return; // never the same place twice in one night
    const j = (st.alternatives || []).findIndex(a => a.place.id === want);
    if (j < 0) return;
    swapTo(n, i, j); changed = true;
  });
  if (changed) recompute(false);
}
function swapTo(n, i, j) {
  const st = n.stops[i];
  const alt = st.alternatives[j];
  const rest = st.alternatives.filter((_, k) => k !== j);
  const old = { ...st }; delete old.alternatives;
  alt.alternatives = [...rest, old];
  n.stops[i] = alt;
}
async function recompute(rerender = true) {
  const slim = { ...S.plan, nights: S.plan.nights.map(n => ({ ...n, stops: n.stops.map(s => { const c = { ...s }; delete c.alternatives; return c; }) })) };
  try {
    const j = await post('/api/recompute', { plan: slim });
    S.plan.text = j.text;
    j.nights.forEach((r, i) => Object.assign(S.plan.nights[i], r));
    S.plan.nights.forEach(n => n.stops.forEach(s => { s.cost = costOf(n, s); }));
  } catch (e) { toast(e.message); }
  if (rerender && S.step === 'plan') render();
}
function costOf(n, s) { return s.slot === 'last' ? Math.round(s.place.price.mid * 0.5) : s.place.price.mid; }

/* ---------- plan view ---------- */
const mapsUrl = (p, city) => 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(p.name + ' ' + (p.address || '') + ' ' + city);
const redditUrl = (p, city) => 'https://www.reddit.com/search/?q=' + encodeURIComponent(`${p.name} ${city} happy hour`);
const money0 = n => '$' + Math.round(n);

function placeTags(p, state, openLabel = 'Open then') {
  const t = [];
  if (state === true) t.push(h('span', { class: 'tag good' }, openLabel));
  else if (state === null || state === undefined) t.push(h('span', { class: 'tag' }, 'Hours unconfirmed'));
  if (p.happy_hint) t.push(h('span', { class: 'tag accent' }, 'Happy hour listed'));
  if (p.live_music) t.push(h('span', { class: 'tag' }, 'Live music'));
  if (p.outdoor_seating) t.push(h('span', { class: 'tag' }, 'Patio'));
  if (p.no_cover) t.push(h('span', { class: 'tag good' }, 'No cover listed'));
  else if (p.ticketed) t.push(h('span', { class: 'tag warn' }, 'May have a cover'));
  return t;
}

function dealRows(p, deals) {
  return (deals || []).map(d => h('div', { class: 'deal' },
    h('span', {}, h('b', {}, d.text), d.when ? ' (' + d.when + ')' : '', ' · added by a visitor, ' + (d.days_old < 1 ? 'today' : d.days_old + ' days ago') + '. Confirm before you go.'),
    h('button', { onclick: async () => { try { await post(`/api/deals/${d.id}/gone`, {}); toast('Thanks. Two reports hide a deal.'); } catch (e) { toast(e.message); } } }, 'Gone?')));
}

function addDealSheet(p, onAdded) {
  sheet('Add a deal at ' + p.name, close => {
    const t = h('input', { type: 'text', maxlength: 140, placeholder: '$3 pints, $5 tacos, free pool...' });
    const w = h('input', { type: 'text', maxlength: 40, placeholder: 'When? Tue all night, Mon to Fri 4 to 7' });
    const err = h('p', { class: 'help', role: 'alert' });
    return h('div', {},
      h('p', { class: 'lead' }, 'Know a real deal? Add it for the next group. No links, please. Deals stay for six months.'),
      h('label', { class: 'field' }, h('span', {}, 'The deal'), t),
      h('label', { class: 'field' }, h('span', {}, 'When (optional)'), w), err,
      h('div', { class: 'row' }, h('button', { class: 'btn ghost', onclick: close }, 'Cancel'),
        h('button', { class: 'btn primary', onclick: async () => {
          try { const j = await post('/api/deals', { place_id: p.id, place_name: p.name, text: t.value, when: w.value }); onAdded(j.deal); close(); toast('Added. Thanks for helping the next group.'); }
          catch (e) { err.textContent = e.message; }
        } }, 'Add deal')));
  });
}

VIEWS.plan = (app, bar) => {
  const P = S.plan; const city = P.city || S.city.name;
  const n = P.nights[S.night];
  const t = n.totals;
  const dateObj = fromIso(n.date);
  const metric = h('div', { class: 'card summary' },
    h('div', {}, h('div', { class: 'big-n' }, '~' + money0(t.per_person), h('span', { class: 'stepnote' }, ' each, estimated')),
      h('div', { class: 'help' }, `${money0(t.group)} for ${P.people} ${P.people === 1 ? 'person' : 'people'} · limit ${money0(P.budget_pp)} each`)),
    h('div', { class: `meter ${t.state}`, role: 'img', 'aria-label': `${Math.round(Math.min(t.pct, 1.6) * 100)} percent of your limit` }, h('i', { style: `width:${Math.min(100, t.pct * 100)}%` })),
    h('p', { class: 'msg' }, t.message));
  const wx = n.weather;
  const useF = (P.country || '') === 'US';
  const temp = c => useF ? Math.round(c * 9 / 5 + 32) + '°F' : Math.round(c) + '°C';

  const tabs = P.nights.length > 1 ? h('div', { class: 'tabs', role: 'tablist' }, ...P.nights.map((x, i) => h('button', { class: 'chip', role: 'tab', 'aria-pressed': String(i === S.night), onclick: () => { S.night = i; render(); } }, fmtDay(fromIso(x.date))))) : null;

  const heads = [...n.tips.map(text => ({ level: 'info', text })), ...P.banners];
  const tl = h('div', { class: 'timeline' });
  n.stops.forEach((s, i) => {
    const leg = n.legs[i];
    put(tl, h('div', { class: 'walk' }, h('span', {}), h('div', {},
      leg.min <= 1 && leg.m < 120 ? h('span', {}, 'Right there') : h('span', {}, 'Walk ', h('b', {}, leg.min + ' min'), ' · ' + leg.label, i === 0 ? ' from ' + (P.stay.name || 'your start') : ''))));
    const p = s.place;
    put(tl, h('div', { class: 'stop' }, h('div', { class: 't' }, s.time),
      h('div', { class: 'body' }, h('span', { class: 'num', 'aria-hidden': 'true' }, i + 1),
        h('div', { class: 'card' },
          h('span', { class: 'tag' }, s.label),
          h('h4', {}, p.name),
          h('div', { class: 'meta' }, h('span', { class: 'tag' }, '~' + money0(s.cost) + ' each (est.)'), placeTags(p, s.open)),
          p.address ? h('div', { class: 'help' }, p.address) : null,
          p.happy_hint ? h('div', { class: 'help' }, 'Map says: ' + p.happy_hint) : null,
          h('p', { class: 'line-voice' }, s.line),
          dealRows(p, s.deals),
          s.long_walk ? h('p', { class: 'help' }, 'Longer walk than usual. The map has few cheap options closer.') : null,
          h('div', { class: 'acts' },
            h('button', { class: 'btn small ghost', onclick: () => doSwap(i) }, 'Swap this stop'),
            h('a', { class: 'btn small line', href: mapsUrl(p, city), target: '_blank', rel: 'noopener' }, 'Map'),
            h('a', { class: 'btn small line', href: redditUrl(p, city), target: '_blank', rel: 'noopener' }, 'Check Reddit'),
            h('button', { class: 'btn small line', onclick: () => addDealSheet(p, d => { s.deals = [...(s.deals || []), d]; render(); }) }, 'Add a deal'))))));
  });
  if (!n.stops.length) put(tl, h('div', { class: 'notice' }, h('h5', {}, 'No stops found'), 'The map has nothing cheap here for these filters. Try searching wider or turning off an extra.'));
  if (n.home) put(tl, h('div', { class: 'walk' }, h('span', {}), h('div', {}, 'Back to ', h('b', {}, P.stay.name || 'your start'), `: ${n.home.min} min on foot. ${n.home.min > 25 ? 'That is far. Book a ride.' : 'Or book a ride before the last round.'}`)));

  put(app, 
    h('h2', {}, `${city}, ${fmtDay(dateObj)}`),
    h('p', { class: 'help' }, `${P.people} ${P.people === 1 ? 'person' : 'people'} · ${S.vibe} · from ${P.stay.name}`,
      wx && wx.lo_c != null && wx.hi_c != null ? ` · ${temp(wx.lo_c)} to ${temp(wx.hi_c)}${wx.rain_pct != null ? ', ' + wx.rain_pct + '% rain' : ''}` : ''),
    tabs, metric,
    heads.length ? h('div', { class: 'notice heads' + (heads.some(x => x.level === 'warn') ? ' warn' : '') }, h('h5', {}, 'Heads up'), h('ul', {}, ...heads.map(x => h('li', {}, x.text)))) : null,
    P.thin ? h('div', { class: 'banner warn' }, h('span', {}, 'The map only knows a few places here. '), h('button', { class: 'btn small line', style: 'margin-left:auto', onclick: widen }, 'Search wider')) : null,
    tl,
    n.events && n.events.length ? h('div', { class: 'notice' }, h('h5', {}, 'Also on tonight'), h('ul', {}, ...n.events.map(e => h('li', {}, h('a', { href: e.url, target: '_blank', rel: 'noopener' }, e.name), ` at ${e.venue}${e.time ? ', ' + e.time : ''}${e.price_from != null ? ', from $' + Math.round(e.price_from) : ''}`)))) :
      h('p', { class: 'help' }, 'Looking for festivals and shows? ', h('a', { href: 'https://www.google.com/search?q=' + encodeURIComponent(`events in ${city} ${fmtDay(dateObj)}`), target: '_blank', rel: 'noopener' }, 'Search events that night'), '. ', h('a', { href: 'https://www.reddit.com/search/?q=' + encodeURIComponent(`${city} happy hour deals`), target: '_blank', rel: 'noopener' }, 'Reddit happy hour threads'), '.'),
    h('div', { class: 'notice' }, h('h5', {}, 'Before you head out'), h('ul', {}, ...P.safety.map(x => h('li', {}, x)))),
    h('div', { style: 'margin-top:14px' }, h('button', { class: 'btn small line', onclick: () => go('city') }, 'Change city, dates or start')),
    credits());

  setBar(bar, { label: 'Copy plan', ok: true, onclick: copyPlan, extra: h('div', { class: 'row', style: 'flex:none' },
    h('button', { class: 'btn ghost', onclick: downloadIcs }, 'Calendar'),
    h('button', { class: 'btn ghost', onclick: shareLink }, 'Share link')) });
};

async function doSwap(i) {
  const n = S.plan.nights[S.night]; const st = n.stops[i];
  const used = new Set(n.stops.filter((_, k) => k !== i).map(x => x.place.id));
  const j = (st.alternatives || []).findIndex(a => !used.has(a.place.id));
  if (j < 0) { toast('No other cheap options nearby for this stop.'); return; }
  const before = JSON.stringify(n.stops);
  swapTo(n, i, j);
  S.picks[pickKey(n, n.stops[i].slot)] = n.stops[i].place.id;
  await recompute();
  toast('Swapped to ' + n.stops[i].place.name, async () => { n.stops = JSON.parse(before); delete S.picks[pickKey(n, n.stops[i].slot)]; await recompute(); });
}
async function widen() { S.radius = Math.min(4000, S.radius + 1000); await buildPlan(); }

async function copyPlan() {
  const text = S.plan.text;
  try { await navigator.clipboard.writeText(text); toast('Copied. Paste it in the group chat.'); }
  catch (e) {
    const ta = h('textarea', { style: 'position:fixed;opacity:0' }, text); document.body.append(ta); ta.select();
    try { document.execCommand('copy'); toast('Copied. Paste it in the group chat.'); } catch (x) { toast('Could not copy. Long-press the text instead.'); }
    ta.remove();
  }
}
async function downloadIcs() {
  const slim = { ...S.plan, nights: S.plan.nights.map(n => ({ ...n, stops: n.stops.map(s => { const c = { ...s }; delete c.alternatives; return c; }) })) };
  try {
    const r = await fetch('/api/ics', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plan: slim }) });
    if (!r.ok) throw new Error((await r.json()).error || 'Could not make the calendar file.');
    const url = URL.createObjectURL(await r.blob());
    const a = h('a', { href: url, download: 'drink-and-walk.ics' }); document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    toast('Calendar file saved. Open it to add every stop.');
  } catch (e) { toast(e.message); }
}
function shareLink() {
  const data = { c: S.city, s: S.start, e: S.end, p: S.people, b: S.budget, st: S.stay, v: S.vibe, l: S.live, la: S.late, f: S.free, r: S.radius, k: S.picks };
  const url = location.origin + location.pathname + '#p=' + btoa(unescape(encodeURIComponent(JSON.stringify(data))));
  if (navigator.share) navigator.share({ title: 'Drink and Walk', text: 'Our cheap night out', url }).catch(() => {});
  else navigator.clipboard.writeText(url).then(() => toast('Link copied. It rebuilds this plan for anyone who opens it.'), () => toast(url));
}
function restoreFromHash() {
  const m = location.hash.match(/^#p=(.+)$/); if (!m) return false;
  try {
    const d = JSON.parse(decodeURIComponent(escape(atob(m[1]))));
    Object.assign(S, { city: d.c, start: d.s, end: d.e, people: d.p, budget: d.b, stay: d.st, vibe: d.v, live: d.l, late: d.la, free: d.f, radius: d.r || 1500, picks: d.k || {} });
    if (!S.city || !S.stay) return false;
    history.replaceState({ step: 'vibe' }, '', location.pathname);
    buildPlan(); return true;
  } catch (e) { return false; }
}

/* ---------- "I'm out right now" ---------- */
function startNearby() {
  S.flow = 'nearby'; S.step = 'nearby'; history.pushState({ step: 'nearby' }, ''); S.near.results = null; S.near.err = ''; S.near.note = 'Finding you...'; render();
  if (!navigator.geolocation) { go('nearcity'); return; }
  navigator.geolocation.getCurrentPosition(
    p => loadNearby({ lat: p.coords.latitude, lon: p.coords.longitude }, 'Searching around you.'),
    () => go('nearcity'), { timeout: 10000, maximumAge: 60000 });
}
async function loadNearby(at, note) {
  if (at) S.near.at = at;
  if (note) S.near.note = note;
  S.step = 'nearby'; S.near.results = null; S.near.err = ''; render();
  const now = new Date();
  try {
    const q = new URLSearchParams({ lat: S.near.at.lat, lon: S.near.at.lon, day: (now.getDay() + 6) % 7, minute: now.getHours() * 60 + now.getMinutes(), mode: S.near.mode });
    const j = await api('/api/nearby?' + q);
    S.near.results = j.results; S.near.known = j.total_known;
  } catch (e) { S.near.err = e.message; }
  if (S.step === 'nearby') render();
}
VIEWS.nearby = app => {
  const modes = [['drink', 'Cheap drinks'], ['eat', 'Cheap food'], ['music', 'Live music'], ['free', 'Free-ish'], ['late', 'Late food']];
  const city = S.city ? S.city.name : '';
  put(app, h('h2', {}, 'Cheap and open near you'), h('p', { class: 'lead' }, S.near.note || ''),
    h('div', { class: 'chips', role: 'group', 'aria-label': 'What are you after' }, ...modes.map(([k, t]) => h('button', { class: 'chip', 'aria-pressed': String(S.near.mode === k), onclick: () => { S.near.mode = k; loadNearby(); } }, t))));
  if (S.near.err) { put(app, h('p', { class: 'err', role: 'alert' }, S.near.err), h('button', { class: 'btn ghost', onclick: () => loadNearby() }, 'Try again')); }
  else if (!S.near.results) { put(app, h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' }), h('div', { class: 'skeleton' })); }
  else if (!S.near.results.length) {
    put(app, h('div', { class: 'notice' }, h('h5', {}, 'Nothing cheap and open within walking distance'), `The map knows ${S.near.known} places here. Try another filter, or walk toward a busier street.`));
  } else {
    put(app, h('div', { style: 'margin-top:14px' }, ...S.near.results.map(r => {
      const p = r.place;
      return h('div', { class: 'card', style: 'margin-bottom:12px' },
        h('div', { class: 'meta' }, h('span', { class: 'tag accent' }, r.walk.min <= 1 ? 'Right here' : r.walk.min + ' min walk'), h('span', { class: 'tag' }, '~' + money0(r.cost) + ' each (est.)'), placeTags(p, r.open, 'Open now')),
        h('h4', { style: 'margin:4px 0;font-size:19px' }, p.name),
        p.address ? h('div', { class: 'help' }, p.address) : null,
        p.happy_hint ? h('div', { class: 'help' }, 'Map says: ' + p.happy_hint) : null,
        dealRows(p, r.deals),
        h('div', { class: 'acts' },
          h('a', { class: 'btn small ghost', href: mapsUrl(p, city), target: '_blank', rel: 'noopener' }, 'Map'),
          h('a', { class: 'btn small line', href: redditUrl(p, city), target: '_blank', rel: 'noopener' }, 'Check Reddit'),
          h('button', { class: 'btn small line', onclick: () => addDealSheet(p, d => { r.deals = [...(r.deals || []), d]; render(); }) }, 'Add a deal')));
    })));
  }
  put(app, credits());
};

/* ---------- boot ---------- */
$('#back').addEventListener('click', () => go(backStep()));
$('#home').addEventListener('click', () => go('home'));
history.replaceState({ step: 'home' }, '');
if (!restoreFromHash()) render();
