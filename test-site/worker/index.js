const COOKIE = "rm_session";
const OPEN_INTERVAL_MS = 30_000;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}
function nowIso() { return new Date().toISOString(); }
function cycleNumber() { return Math.floor(Date.now() / OPEN_INTERVAL_MS); }
function getCookie(request, name) {
  const value = request.headers.get("Cookie") || "";
  const match = value.split(";").map(v => v.trim()).find(v => v.startsWith(name + "="));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}
async function userFromRequest(request, env) {
  const token = getCookie(request, COOKIE);
  if (!token) return null;
  return await env.DB.prepare("SELECT username, role FROM sessions WHERE token = ?").bind(token).first();
}
async function ensureCells(env) {
  const row = await env.DB.prepare("SELECT COUNT(*) AS count FROM cells").first();
  if (Number(row?.count || 0) === 40) return;
  const statements = [];
  for (let i = 1; i <= 40; i++) {
    const permanent = i <= 8 ? 1 : 0;
    statements.push(env.DB.prepare("INSERT OR IGNORE INTO cells (id,status,permanently_unavailable) VALUES (?,?,?)").bind(i, permanent ? "red" : "grey", permanent));
  }
  await env.DB.batch(statements);
}
async function advanceAvailability(env, force = false) {
  await ensureCells(env);
  const currentCycle = cycleNumber();
  const marker = await env.DB.prepare("SELECT value FROM meta WHERE key='last_cycle'").first();
  const lastCycle = Number(marker?.value ?? -1);
  if (!force && lastCycle >= currentCycle) return;
  const grey = await env.DB.prepare("SELECT id FROM cells WHERE status='grey' AND permanently_unavailable=0").all();
  const candidates = (grey.results || []).map(r => r.id).sort(() => Math.random() - 0.5);
  const count = Math.min(4, candidates.length);
  const openedAt = nowIso();
  const statements = candidates.slice(0, count).map(id => env.DB.prepare("UPDATE cells SET status='available',opened_at=? WHERE id=? AND status='grey'").bind(openedAt, id));
  statements.push(env.DB.prepare("INSERT INTO meta(key,value) VALUES('last_cycle,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value").bind(String(currentCycle)));
  await env.DB.batch(statements);
}
async function apiState(request, env) {
  const user = await userFromRequest(request, env);
  if (!user) return json({ error: "Not authenticated" }, 401);
  await advanceAvailability(env);
  const cells = await env.DB.prepare("SELECT id,status,opened_at,permanently_unavailable FROM cells ORDER BY id").all();
  return json({ user, cells: cells.results || [], cycleMs: OPEN_INTERVAL_MS });
}
async function login(request, env) {
  const body = await request.json();
  const username = String(body.username || "").trim();
  const password = String(body.password || "");
  const user = await env.DB.prepare("SELECT username,role FROM users WHERE username=? AND password=?").bind(username, password).first();
  if (!user) return json({ error: "Invalid username or password" }, 401);
  const token = crypto.randomUUID();
  await env.DB.prepare("INSERT INTO sessions(token,username,role) VALUES(?,?,?)").bind(token, user.username, user.role).run();
  return new Response(JSON.stringify({ ok: true, user }), { headers: { "content-type": "application/json", "cache-control": "no-store", "set-cookie": `${COOKIE}=${encodeURIComponent(token)}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=86400` } });
}
async function logout(request, env) {
  const token = getCookie(request, COOKIE);
  if (token) await env.DB.prepare("DELETE FROM sessions WHERE token=?").bind(token).run();
  return new Response(null, { status: 204, headers: { "set-cookie": `${COOKIE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0` } });
}
async function reserve(request, env) {
  const user = await userFromRequest(request, env);
  if (!user) return json({ error: "Not authenticated" }, 401);
  const body = await request.json();
  const ids = [...new Set((body.cellIds || []).map(Number).filter(n => Number.isInteger(n) && n >= 1 && n <= 40))];
  if (!ids.length) return json({ error: "Select at least one cell" }, 400);
  const cells = await env.DB.prepare(`SELECT id,status,opened_at FROM cells WHERE id IN (${ids.map(() => "?").join(",")})`).bind(...ids).all();
  const available = (cells.results || []).filter(c => c.status === "available");
  if (available.length !== ids.length) return json({ error: "One or more selected cells are no longer available. Reload and try again." }, 409);
  const reservedAt = nowIso();
  const statements = [];
  for (const cell of available) {
    const openMs = Math.max(0, new Date(reservedAt).getTime() - new Date(cell.opened_at).getTime());
    statements.push(env.DB.prepare("INSERT INTO reservations(cell_id,username,opened_at,reserved_at,open_seconds) VALUES(?,?,?,?,?)").bind(cell.id, user.username, cell.opened_at, reservedAt, openMs / 1000));
    statements.push(env.DB.prepare("UPDATE cells SET status='grey',opened_at=NULL WHERE id=?").bind(cell.id));
  }
  await env.DB.batch(statements);
  return json({ ok: true, reserved: available.map(c => c.id), username: user.username, reservedAt });
}
async function logData(request, env) {
  const user = await userFromRequest(request, env);
  if (!user || user.role !== "admin") return json({ error: "Admin access required" }, 403);
  const rows = await env.DB.prepare("SELECT id,cell_id,username,opened_at,reserved_at,open_seconds FROM reservations ORDER BY id DESC LIMIT 500").all();
  return json({ reservations: rows.results || [] });
}
async function adminAction(request, env) {
  const user = await userFromRequest(request, env);
  if (!user || user.role !== "admin") return json({ error: "Admin access required" }, 403);
  const body = await request.json();
  await ensureCells(env);
  if (body.action === "reset") {
    await env.DB.prepare("UPDATE cells SET status=CASE WHEN permanently_unavailable=1 THEN 'red' ELSE 'grey' END,opened_at=NULL").run();
    await env.DB.prepare("UPDATE meta SET value='-1' WHERE key='last_cycle'").run();
  } else if (body.action === "open_random") {
    await advanceAvailability(env, true);
  } else if (body.action === "open_cell") {
    const id = Number(body.cellId);
    await env.DB.prepare("UPDATE cells SET status='available',opened_at=? WHERE id=? AND permanently_unavailable=0").bind(nowIso(), id).run();
  } else if (body.action === "close_cell") {
    const id = Number(body.cellId);
    await env.DB.prepare("UPDATE cells SET status='grey',opened_at=NULL WHERE id=? AND permanently_unavailable=0").bind(id).run();
  } else if (body.action === "clear_log") {
    await env.DB.prepare("DELETE FROM reservations").run();
  } else return json({ error: "Unknown action" }, 400);
  return json({ ok: true });
}
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/login" && request.method === "POST") return login(request, env);
    if (url.pathname === "/api/logout" && request.method === "POST") return logout(request, env);
    if (url.pathname === "/api/state" && request.method === "GET") return apiState(request, env);
    if (url.pathname === "/api/reserve" && request.method === "POST") return reserve(request, env);
    if (url.pathname === "/api/log" && request.method === "GET") return logData(request, env);
    if (url.pathname === "/api/admin" && request.method === "POST") return adminAction(request, env);
    return env.ASSETS.fetch(request);
  }
};
