/**
 * The pat counter.
 *
 * GitHub Pages is static, so the one thing the creature in the label cannot do by
 * itself is remember that it was patted. This is that memory, and it is the whole of
 * the new infrastructure: one Worker, one KV namespace, free tier, nothing to run.
 *
 * Three endpoints:
 *
 *   POST /show   {gen, agent, line_id, session}   a line was put in front of somebody
 *   POST /pat    {gen, agent, line_id, session}   somebody clicked while it was showing
 *   GET  /counts?gen=N                            the tallies, for the weekly roll (#29)
 *
 * The denominator is not optional. Agents are not shown equally often, so a pat count
 * on its own says nothing; selection in #29 ranks on pats/shows, and it cannot
 * reconstruct the shows afterwards.
 *
 * Two rules that came out of the simulation rather than out of taste:
 *
 *   1. The first pat of a session is discarded. A fixed fraction of visitors pat
 *      because the creature is new, not because of what it said. Mechanically it is
 *      also the click that has heard nothing yet: the creature is silent until it is
 *      spoken to, so click 1 produces a line and click 2 is the first click that is a
 *      response to one.
 *   2. Ten counted pats a session, then accept and discard in silence. Somebody
 *      sitting on the button must not be able to elect a line.
 *
 * And a third that follows from the second: shows are capped too, at eleven. Without
 * it the same person sitting on the button drives an agent's ratio to zero from the
 * denominator instead of the numerator, which is the same attack upside down. Eleven
 * rather than ten because a session's first show is the one whose pat is discarded.
 *
 * What is stored, in full, and nothing else:
 *
 *   c:<gen>:<agent>   {shows, pats, lines:{<line_id>:{shows,pats}}, hours:{<YYYY-MM-DDTHH>:{shows,pats}}}
 *   s:<session>       {n, pats, shows}          random tab-scoped id, 24h TTL
 *
 * where n is 0 or 1 — whether a pat has been seen at all, which is the whole of what
 * rule 1 needs — and pats and shows are what this session has contributed so far.
 *
 * No IP, no cookie, no fingerprint, no persistent id, no user agent, no referrer, no
 * minute-resolution time. The hour bucket is taken from the Worker's own clock, so the
 * client sends no timestamp and no timezone either. Nothing here identifies a person
 * and there is nothing to correlate across a browser restart.
 */

const PAT_CAP = 10;                 // counted pats per session
const SHOW_CAP = PAT_CAP + 1;       // see the note above
const SESSION_TTL = 86400;          // seconds; the id dies with the tab anyway
const MAX_BODY = 1024;              // bytes; nothing legitimate is close

// gen is a small integer, agent and line_id are short opaque tokens chosen by #29,
// session is whatever the client generated. Anything else is a 400 and is not stored.
const TOKEN = /^[A-Za-z0-9_.:-]{1,64}$/;
const SESSION = /^[A-Za-z0-9_-]{8,64}$/;


function cors(env, request) {
  const allow = (env.ALLOW_ORIGIN || '*').split(',').map((s) => s.trim());
  const origin = request.headers.get('Origin');
  const ok = allow.indexOf('*') >= 0 ? (origin || '*')
           : (origin && allow.indexOf(origin) >= 0 ? origin : null);
  return {
    'Access-Control-Allow-Origin': ok || 'null',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Max-Age': '86400',
    'Vary': 'Origin',
  };
}


// A browser can be told to stay off. It is a speed bump and not a wall — curl sends no
// Origin and is let through, because the weekly job and a shell test both need to be —
// but it does stop the page next door from spending this KV namespace's write budget.
function originAllowed(env, request) {
  const allow = (env.ALLOW_ORIGIN || '*').split(',').map((s) => s.trim());
  if (allow.indexOf('*') >= 0) return true;
  const origin = request.headers.get('Origin');
  return !origin || allow.indexOf(origin) >= 0;
}


function json(body, status, headers) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: Object.assign(
      { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
      headers || {}),
  });
}


function hourBucket(now) {
  return new Date(now).toISOString().slice(0, 13);   // 2026-09-06T11
}


async function readEvent(request) {
  const len = parseInt(request.headers.get('Content-Length') || '0', 10);
  if (len > MAX_BODY) return null;
  const text = await request.text();
  if (text.length > MAX_BODY) return null;
  let d;
  try { d = JSON.parse(text); } catch (e) { return null; }
  if (!d || typeof d !== 'object') return null;

  const gen = typeof d.gen === 'number' ? d.gen : parseInt(d.gen, 10);
  if (!isFinite(gen) || gen < 0 || gen > 1e6 || gen !== Math.floor(gen)) return null;
  const session = String(d.session == null ? '' : d.session);
  if (!SESSION.test(session)) return null;

  // agent and line_id are both allowed to be missing on a pat. The creature is silent
  // until it is spoken to, so the first click of a visit has heard nothing yet and
  // there is genuinely nothing to name; that click is the one that gets discarded.
  // A show has to name both, and is refused below if it does not.
  const agent = d.agent == null || d.agent === '' ? '' : String(d.agent);
  const line = d.line_id == null || d.line_id === '' ? '' : String(d.line_id);
  if (agent && !TOKEN.test(agent)) return null;
  if (line && !TOKEN.test(line)) return null;

  return { gen: gen, agent: agent, line: line, session: session };
}


// One key per (gen, agent). Totals, the per-line breakdown and the hour histogram all
// live in the same document, so an event is one read and one write rather than three.
async function bump(env, ev, field, now) {
  const key = 'c:' + ev.gen + ':' + ev.agent;
  const c = (await env.PATS.get(key, 'json')) || { shows: 0, pats: 0, lines: {}, hours: {} };
  c.shows = c.shows || 0;
  c.pats = c.pats || 0;
  c.lines = c.lines || {};
  c.hours = c.hours || {};

  c[field] += 1;
  if (ev.line) {
    const l = c.lines[ev.line] || (c.lines[ev.line] = { shows: 0, pats: 0 });
    l[field] += 1;
  }
  const h = hourBucket(now);
  const b = c.hours[h] || (c.hours[h] = { shows: 0, pats: 0 });
  b[field] += 1;

  await env.PATS.put(key, JSON.stringify(c));
}


async function loadSession(env, sid) {
  const s = (await env.PATS.get('s:' + sid, 'json')) || {};
  return { n: s.n || 0, pats: s.pats || 0, shows: s.shows || 0 };
}


function saveSession(env, sid, s) {
  return env.PATS.put('s:' + sid, JSON.stringify(s), { expirationTtl: SESSION_TTL });
}


// Past the caps nothing is written, only read. Somebody sitting on the button is meant
// to be free to sit on it, and the free tier allows a thousand KV writes a day; a
// session that could go on writing for ever would spend that on one person.
async function onPat(env, ev, now) {
  const s = await loadSession(env, ev.session);
  const first = s.n === 0;
  // A click on a creature that has not spoken yet has nothing to attribute. It still
  // counts as this session's first pat — that is exactly the click the rule is here to
  // throw away — but it does not spend one of the ten.
  const counted = !!ev.agent && !first && s.pats < PAT_CAP;
  if (first) s.n = 1;
  if (counted) s.pats += 1;
  if (first || counted) await saveSession(env, ev.session, s);
  if (counted) await bump(env, ev, 'pats', now);
  return counted;
}


async function onShow(env, ev, now) {
  const s = await loadSession(env, ev.session);
  if (s.shows >= SHOW_CAP) return false;
  s.shows += 1;
  await saveSession(env, ev.session, s);
  await bump(env, ev, 'shows', now);
  return true;
}


// The tallies for one generation, in the shape #29 selects on: rank by pats/shows,
// skip the roll when any agent is under ten shows.
async function countsFor(env, gen) {
  const out = { gen: gen, totals: { shows: 0, pats: 0 }, agents: {} };
  const prefix = 'c:' + gen + ':';
  let cursor;
  do {
    const page = await env.PATS.list({ prefix: prefix, cursor: cursor });
    for (const k of page.keys) {
      const c = await env.PATS.get(k.name, 'json');
      if (!c) continue;
      const agent = k.name.slice(prefix.length);
      out.agents[agent] = {
        shows: c.shows || 0,
        pats: c.pats || 0,
        lines: c.lines || {},
        hours: c.hours || {},
      };
      out.totals.shows += c.shows || 0;
      out.totals.pats += c.pats || 0;
    }
    cursor = page.list_complete ? null : page.cursor;
  } while (cursor);
  return out;
}


async function allGens(env) {
  const gens = {};
  let cursor;
  do {
    const page = await env.PATS.list({ prefix: 'c:', cursor: cursor });
    for (const k of page.keys) gens[k.name.split(':')[1]] = true;
    cursor = page.list_complete ? null : page.cursor;
  } while (cursor);
  return Object.keys(gens).map(Number).sort((a, b) => a - b);
}


export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, '') || '/';
    const head = cors(env, request);
    const now = Date.now();

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: head });

    if (path === '/pat' || path === '/show') {
      if (request.method !== 'POST') return json({ ok: false }, 405, head);
      if (!originAllowed(env, request)) return json({ ok: false }, 403, head);
      if (!env.PATS) return json({ ok: false }, 500, head);
      const ev = await readEvent(request);
      if (!ev) return json({ ok: false }, 400, head);
      if (path === '/show' && (!ev.agent || !ev.line)) return json({ ok: false }, 400, head);

      // Whether it counted is deliberately not in the response. "Silently accept and
      // discard" is the rule, and a client that can see the cap is a client that can
      // work around it. The evidence lives in GET /counts.
      if (path === '/pat') await onPat(env, ev, now);
      else await onShow(env, ev, now);
      return json({ ok: true }, 200, head);
    }

    if (path === '/counts') {
      if (request.method !== 'GET') return json({ ok: false }, 405, head);
      if (!env.PATS) return json({ ok: false }, 500, head);
      // Open unless a token is set. The counts are not personal, but the weekly job
      // already carries one secret, so this costs nothing to lock if he wants it.
      if (env.COUNTS_TOKEN) {
        const auth = request.headers.get('Authorization') || '';
        if (auth !== 'Bearer ' + env.COUNTS_TOKEN) return json({ ok: false }, 401, head);
      }
      const asOf = new Date(now).toISOString();
      const q = url.searchParams.get('gen');
      if (q !== null && q !== '') {
        const gen = parseInt(q, 10);
        if (!isFinite(gen) || gen < 0) return json({ ok: false }, 400, head);
        const one = await countsFor(env, gen);
        one.as_of = asOf;
        return json(one, 200, head);
      }
      const list = await allGens(env);
      const gens = {};
      for (const g of list) gens[g] = await countsFor(env, g);
      return json({
        as_of: asOf,
        latest: list.length ? list[list.length - 1] : null,
        gens: gens,
      }, 200, head);
    }

    return json({ ok: false }, 404, head);
  },
};
