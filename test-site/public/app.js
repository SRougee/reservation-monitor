const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const TOKEN_KEY = "rm_session_token";
const GRID_POLL_MS = 500;

function authHeaders() {
  const token = sessionStorage.getItem(TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}
async function api(path, options={}) {
  const response = await fetch(path, {
    ...options,
    headers: { "content-type": "application/json", ...authHeaders(), ...(options.headers||{}) }
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function renderHeader(user) {
  const nav = $("#nav");
  if (!nav) return;
  nav.innerHTML = user ? `<a href="/landing.html">Home</a><a href="/dummy.html">Dummy Page</a><a href="/reservation.html">Reservations</a>${user.role==='admin'?'<a href="/admin.html">Admin Log</a>':''}<button id="logout">Logout</button>` : '';
  $("#logout")?.addEventListener("click", async()=>{await api('/api/logout',{method:'POST'});sessionStorage.removeItem(TOKEN_KEY);location.href='/';});
}
async function currentUser() { try { const data=await api('/api/state'); return data.user; } catch { return null; } }
async function guard() {
  const user=await currentUser();
  if(!user) { sessionStorage.removeItem(TOKEN_KEY); location.href='/'; return null; }
  renderHeader(user); return user;
}
async function initLogin() {
  $("#loginForm")?.addEventListener("submit",async(e)=>{
    e.preventDefault(); $("#loginError").textContent='';
    try {
      const result = await api('/api/login',{method:'POST',body:JSON.stringify({username:$("#username").value,password:$("#password").value})});
      sessionStorage.setItem(TOKEN_KEY, result.token);
      location.href='/landing.html';
    }
    catch(err){$("#loginError").textContent=err.message;}
  });
}
function renderGrid(data) {
  const grid=$("#grid"); if(!grid)return data;
  const old = new Map($$(".booking-block").map(el => [Number(el.dataset.cellId), el]));
  for(const cell of data.cells){
    let el = old.get(cell.id);
    const desiredClass = `booking-block ${cell.status}`;
    if(!el){
      el=document.createElement('div');
      el.dataset.cellId=cell.id;
      grid.appendChild(el);
      el.addEventListener('click',()=>{
        if(el.classList.contains('available')) el.classList.toggle('selected');
      });
    }
    if(el.className !== desiredClass) el.className=desiredClass;
    el.textContent=`${cell.id}`;
    el.title=cell.status==='red'?'Permanently unavailable':cell.status==='available'?'Available - click to select':'Unavailable';
    if(cell.status !== 'available') el.classList.remove('selected');
    old.delete(cell.id);
  }
  for(const el of old.values()) el.remove();
  if($("#cycleInfo")) $("#cycleInfo").textContent=`Availability changes every ${data.cycleMs/1000} seconds. White cells remain available until reserved. The grid updates automatically.`;
  return data;
}
async function loadGrid() {
  const data=await api('/api/state');
  return renderGrid(data);
}
async function initReservation() {
  const user=await guard(); if(!user)return;
  let refreshing=false;
  let autoRefreshRunning=true;

  const refresh=async(clearMessage=true)=>{
    if(refreshing)return;
    refreshing=true;
    try{
      await loadGrid();
      if(clearMessage) $("#message").textContent='Grid reloaded.';
    }catch(e){$("#message").textContent=e.message;}
    finally{refreshing=false;}
  };

  $("#reloadGrid").addEventListener('click',()=>refresh(true));
  $("#reserveButton").addEventListener('click',async()=>{
    const ids=$$('.booking-block.selected').map(x=>Number(x.dataset.cellId));
    if(!ids.length){$("#message").textContent='Select one or more white cells first.';return;}
    try{
      const result=await api('/api/reserve',{method:'POST',body:JSON.stringify({cellIds:ids})});
      await loadGrid();
      $("#message").textContent=`Reserved cells: ${result.reserved.join(', ')} by ${result.username}. The reservation has been recorded in the log.`;
    }
    catch(e){$("#message").textContent=e.message;}
  });

  await loadGrid();

  // The real-world simulation is browser-driven: the page's own JavaScript
  // checks for updated availability and changes the existing DOM in place.
  // The Python monitor observes those DOM changes rather than clicking
  // Reload Availability repeatedly.
  const autoRefresh=async()=>{
    while(autoRefreshRunning){
      try { await loadGrid(); } catch {}
      await new Promise(resolve=>setTimeout(resolve, GRID_POLL_MS));
    }
  };
  autoRefresh();
}
async function initAdmin(){
  const user=await guard(); if(!user||user.role!=='admin'){if(user) location.href='/landing.html';return;}
  async function action(action, cellId){try{await api('/api/admin',{method:'POST',body:JSON.stringify({action,cellId})});await loadAdmin();}catch(e){$("#adminMessage").textContent=e.message;}}
  $("#reset").onclick=()=>action('reset'); $("#openRandom").onclick=()=>action('open_random'); $("#clearLog").onclick=()=>action('clear_log');
  $("#openCell").onclick=()=>action('open_cell',Number($("#cellNumber").value)); $("#closeCell").onclick=()=>action('close_cell',Number($("#cellNumber").value));
  async function loadLog(){
    const data=await api('/api/log');
    $("#logBody").innerHTML=data.reservations.map(r=>`<tr><td>${r.cell_id}</td><td>${r.username}</td><td>${new Date(r.opened_at).toLocaleString()}</td><td>${new Date(r.reserved_at).toLocaleString()}</td><td>${Number(r.open_seconds).toFixed(2)} sec</td></tr>`).join('') || '<tr><td colspan="5">No reservations yet.</td></tr>';
  }
  async function loadAdmin(){
    await loadLog();
    await loadGrid();
  }
  await loadAdmin();
  setInterval(async()=>{try{await loadLog();}catch{}},3000);
}
async function initStandardPage(){ if($("#loginForm")||$("#reservationPage")||$("#adminPage"))return; await guard(); }

document.addEventListener('DOMContentLoaded',()=>{
  initLogin();
  if($("#reservationPage")) initReservation();
  else if($("#adminPage")) initAdmin();
  else initStandardPage();
});
