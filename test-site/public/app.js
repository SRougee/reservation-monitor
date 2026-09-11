const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

async function api(path, options={}) {
  const response = await fetch(path, { ...options, headers: { "content-type": "application/json", ...(options.headers||{}) } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}
function renderHeader(user) {
  const nav = $("#nav");
  if (!nav) return;
  nav.innerHTML = user ? `<a href="/landing.html">Home</a><a href="/dummy.html">Dummy Page</a><a href="/reservation.html">Reservations</a>${user.role==='admin'?'<a href="/admin.html">Admin Log</a>':''}<button id="logout">Logout</button>` : '';
  $("#logout")?.addEventListener("click", async()=>{await api('/api/logout',{method:'POST'});location.href='/';});
}
async function currentUser() { try { const data=await api('/api/state'); return data.user; } catch { return null; } }
async function guard() {
  const user=await currentUser();
  if(!user) { location.href='/'; return null; }
  renderHeader(user); return user;
}
async function initLogin() {
  $("#loginForm")?.addEventListener("submit",async(e)=>{
    e.preventDefault(); $("#loginError").textContent='';
    try { await api('/api/login',{method:'POST',body:JSON.stringify({username:$("#username").value,password:$("#password").value})}); location.href='/landing.html'; }
    catch(err){$("#loginError").textContent=err.message;}
  });
}
async function loadGrid() {
  const data=await api('/api/state');
  const grid=$("#grid"); if(!grid)return data;
  grid.innerHTML='';
  for(const cell of data.cells){
    const el=document.createElement('div'); el.className=`booking-block ${cell.status}`; el.dataset.cellId=cell.id; el.textContent=`${cell.id}`;
    el.title=cell.status==='red'?'Permanently unavailable':cell.status==='available'?'Available - click to select':'Unavailable';
    if(cell.status==='available') el.addEventListener('click',()=>el.classList.toggle('selected'));
    grid.appendChild(el);
  }
  if($("#cycleInfo")) $("#cycleInfo").textContent=`Availability changes every ${data.cycleMs/1000} seconds. White cells remain available until reserved.`;
  return data;
}
async function initReservation() {
  const user=await guard(); if(!user)return;
  let refreshing=false;
  const refresh=async()=>{if(refreshing)return;refreshing=true;try{await loadGrid();$("#message").textContent='Grid reloaded.';}catch(e){$("#message").textContent=e.message;}finally{refreshing=false;}};
  $("#reloadGrid").addEventListener('click',refresh);
  $("#reserveButton").addEventListener('click',async()=>{
    const ids=$$('.booking-block.selected').map(x=>Number(x.dataset.cellId));
    if(!ids.length){$("#message").textContent='Select one or more white cells first.';return;}
    try{
      const result=await api('/api/reserve',{method:'POST',body:JSON.stringify({cellIds:ids})});
      // Reservation is the exception to manual reload: immediately reflect the successful reservation.
      await loadGrid();
      $("#message").textContent=`Reserved cells: ${result.reserved.join(', ')} by ${result.username}. The reservation has been recorded in the log.`;
    }
    catch(e){$("#message").textContent=e.message;}
  });
  await loadGrid();
  // Intentionally no automatic polling here. Availability changes are only fetched when
  // the user presses Reload Availability, except that a successful reservation refreshes
  // the grid immediately so the reserved cells turn grey.
}
async function initAdmin(){
  const user=await guard(); if(!user||user.role!=='admin'){if(user) location.href='/landing.html';return;}
  async function action(action, cellId){try{await api('/api/admin',{method:'POST',body:JSON.stringify({action,cellId})});await loadAdmin();}catch(e){$("#adminMessage").textContent=e.message;}}
  $("#reset").onclick=()=>action('reset'); $("#openRandom").onclick=()=>action('open_random'); $("#clearLog").onclick=()=>action('clear_log');
  $("#openCell").onclick=()=>action('open_cell',Number($("#cellNumber").value)); $("#closeCell").onclick=()=>action('close_cell',Number($("#cellNumber").value));
  async function loadAdmin(){
    const data=await api('/api/log');
    $("#logBody").innerHTML=data.reservations.map(r=>`<tr><td>${r.cell_id}</td><td>${r.username}</td><td>${new Date(r.opened_at).toLocaleString()}</td><td>${new Date(r.reserved_at).toLocaleString()}</td><td>${Number(r.open_seconds).toFixed(2)} sec</td></tr>`).join('') || '<tr><td colspan="5">No reservations yet.</td></tr>';
    await loadGrid();
  }
  await loadAdmin(); setInterval(loadAdmin,3000);
}
async function initStandardPage(){ if($("#loginForm")||$("#reservationPage")||$("#adminPage"))return; await guard(); }

document.addEventListener('DOMContentLoaded',()=>{
  initLogin();
  if($("#reservationPage")) initReservation();
  else if($("#adminPage")) initAdmin();
  else initStandardPage();
});
