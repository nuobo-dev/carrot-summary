/* CarrotSummary Dashboard JS */
let config = {}, currentSession = null, activeTaskId = null, activeTaskDisplay = null;
const C = 2 * Math.PI * 90;
let lastRemaining = 0, lastRemainingAt = 0, lastTotal = 1500, lastStatus = null;
let selectedDate = new Date().toISOString().split('T')[0];
let calYear = new Date().getFullYear(), calMonth = new Date().getMonth() + 1;

// Tab switching
document.querySelectorAll('.tab').forEach(t => {
  t.onclick = () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('panel-' + t.dataset.tab).classList.add('active');
    if (t.dataset.tab === 'activity') { refreshActivity(); loadActivityByTask(); }
  };
});

async function fetchJSON(url, opts) { return (await fetch(url, opts)).json(); }
function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function parseDur(s) {
  let m = 0;
  const hm = s.match(/(\d+)h/); if (hm) m += parseInt(hm[1]) * 60;
  const mm = s.match(/(\d+)m/); if (mm) m += parseInt(mm[1]);
  return m || 1;
}

// --- Timer display ---
function updateTimerDisplay(remaining, total, status) {
  const arc = document.getElementById('timer-arc');
  const timeEl = document.getElementById('timer-time');
  const labelEl = document.getElementById('timer-label');
  if (!status) {
    arc.style.strokeDashoffset = C; arc.style.transition = 'none';
    timeEl.textContent = '--:--'; labelEl.textContent = 'No session'; return;
  }
  arc.style.transition = 'stroke-dashoffset 1s linear';
  arc.style.strokeDashoffset = C * (1 - Math.max(0, remaining / total));
  arc.style.stroke = status === 'break' ? 'var(--green)' : 'var(--accent)';
  const rem = Math.max(0, Math.round(remaining));
  const m = Math.floor(rem / 60), sec = rem % 60;
  timeEl.textContent = String(m).padStart(2,'0') + ':' + String(sec).padStart(2,'0');
  labelEl.textContent = status === 'break' ? 'Break' : status === 'active' ? 'Focus' : status;
}

// --- Status refresh ---
async function refreshStatus() {
  try {
    const d = await fetchJSON('/api/status');
    document.getElementById('status-dot').className = 'status-dot' + (d.tracking ? ' on' : '');
    document.getElementById('tracking-label').textContent = d.tracking ? 'Tracking' : 'Stopped';
    currentSession = d.session;
    activeTaskId = d.active_task_id;
    activeTaskDisplay = d.active_task_display;

    // Active task display
    const atEl = document.getElementById('active-task-display');
    if (atEl) atEl.textContent = activeTaskDisplay || 'No active task';

    if (d.session) {
      const s = d.session;
      const total = s.status === 'break' ? (s.completed_count > 0 && s.completed_count % 4 === 0 ? 900 : 300) : 1500;
      lastRemaining = s.remaining; lastRemainingAt = Date.now(); lastTotal = total; lastStatus = s.status;
      document.getElementById('session-cat').textContent = s.category + (s.sub_category && s.sub_category !== s.category ? ' / ' + s.sub_category : '');
      document.getElementById('session-count').textContent = s.completed_count + ' session' + (s.completed_count !== 1 ? 's' : '') + ' completed';
      const dots = document.getElementById('session-dots');
      dots.innerHTML = '';
      for (let i = 0; i < 4; i++) {
        const dot = document.createElement('div');
        dot.className = 'dot' + (i < (s.completed_count % 4 || (s.completed_count > 0 && s.completed_count % 4 === 0 ? 4 : 0)) ? ' filled' : '');
        dots.appendChild(dot);
      }
    } else {
      lastStatus = null; lastRemaining = 0;
      updateTimerDisplay(0, 1500, null);
      document.getElementById('session-cat').textContent = '—';
      document.getElementById('session-count').textContent = '0 sessions completed';
      document.getElementById('session-dots').innerHTML = '';
    }
    document.getElementById('paused-list').innerHTML = (d.paused_sessions || []).map(p =>
      `<div>⏸ ${esc(p.category)} — ${Math.floor(p.elapsed/60)}m, ${p.completed_count} sess</div>`
    ).join('');
    // Update active-task highlights in-place without rebuilding the DOM.
    // This avoids destroying input focus and scroll position.
    updateActiveHighlights();
  } catch(e) { console.error(e); }
}

function updateActiveHighlights() {
  document.querySelectorAll('.child-item').forEach(el => {
    const id = parseInt(el.dataset.taskId, 10);
    if (!id) return;
    const shouldBeActive = id === activeTaskId;
    const isActive = el.classList.contains('active');
    if (shouldBeActive && !isActive) {
      el.classList.add('active');
      // Add tracking badge if missing
      if (!el.querySelector('.t-badge.tracking')) {
        const badge = document.createElement('span');
        badge.className = 't-badge tracking';
        badge.textContent = '● tracking';
        el.querySelector('.t-title').after(badge);
      }
    } else if (!shouldBeActive && isActive) {
      el.classList.remove('active');
      const badge = el.querySelector('.t-badge.tracking');
      if (badge) badge.remove();
    }
  });
}

// --- Active Task ---
async function setActiveTask(taskId) {
  await fetchJSON('/api/active-task', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({task_id:taskId})});
  activeTaskId = taskId;
  updateActiveHighlights();
  // Refresh status for timer display (but won't rebuild todos)
  refreshStatus();
}
async function clearActiveTask() {
  await fetchJSON('/api/active-task', {method:'DELETE'});
  activeTaskId = null;
  updateActiveHighlights();
  refreshStatus();
}

// --- Drag and Drop ---
let draggedTodoId = null, draggedBucketId = null;
function dragTodo(e, id) { draggedTodoId = id; draggedBucketId = null; e.dataTransfer.setData('type','task'); e.stopPropagation(); }
function dragBucket(e, id) { draggedBucketId = id; draggedTodoId = null; e.dataTransfer.setData('type','bucket'); }
async function dropOnBucket(e, targetId) {
  e.preventDefault(); e.stopPropagation(); e.currentTarget.classList.remove('drag-over');
  const type = e.dataTransfer.getData('type');
  if (type === 'task' && draggedTodoId && draggedTodoId !== targetId) {
    await fetchJSON(`/api/todos/${draggedTodoId}/move`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({parent_id:targetId})});
    refreshTodos();
  } else if (type === 'bucket' && draggedBucketId && draggedBucketId !== targetId) {
    if (confirm('Merge these two buckets?')) {
      await fetchJSON('/api/todos/merge', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({source_id:draggedBucketId, target_id:targetId})});
      refreshTodos();
    }
  }
  draggedTodoId = null; draggedBucketId = null;
}
async function addTaskToBucket(bucketId) {
  const inp = document.getElementById('add-task-' + bucketId);
  if (!inp) return;
  const title = inp.value.trim();
  if (!title) { inp.focus(); return; }
  await fetchJSON('/api/todos', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title, parent_id: bucketId})});
  inp.value = '';
  refreshTodos();
}

// --- Todo rendering (Focus tab) ---
async function refreshTodos() {
  const todos = await fetchJSON('/api/todos');
  const el = document.getElementById('todo-list');
  const parents = todos.filter(t => !t.parent_id);
  const childMap = {};
  todos.filter(t => t.parent_id).forEach(t => {
    if (!childMap[t.parent_id]) childMap[t.parent_id] = [];
    childMap[t.parent_id].push(t);
  });
  let html = '';
  parents.forEach(p => {
    const children = childMap[p.id] || [];
    html += `<div class="bucket" data-id="${p.id}" draggable="true"
      ondragstart="dragBucket(event,${p.id})"
      ondragover="event.preventDefault();this.classList.add('drag-over')"
      ondragleave="this.classList.remove('drag-over')"
      ondrop="dropOnBucket(event,${p.id})">
      <div class="todo-item bucket-header ${p.done?'done':''}">
        <span class="drag-handle">⠿</span>
        <input type="checkbox" ${p.done?'checked':''} onchange="toggleTodo(${p.id})">
        <span class="t-title" style="font-weight:600">${esc(p.title)}</span>
        <span class="t-badge manual">bucket</span>
        <span style="color:var(--text-tertiary);font-size:11px">${children.length}</span>
        <button class="t-del" onclick="deleteTodo(${p.id})">×</button>
      </div><div class="bucket-children">`;
    children.forEach(c => {
      const isActive = activeTaskId === c.id;
      html += `<div class="todo-item child-item ${c.done?'done':''} ${isActive?'active':''}"
        data-task-id="${c.id}"
        draggable="true" ondragstart="dragTodo(event,${c.id})"
        onclick="event.target.tagName!=='INPUT'&&event.target.tagName!=='BUTTON'&&setActiveTask(${c.id})">
        <span class="drag-handle">⠿</span>
        <input type="checkbox" ${c.done?'checked':''} onchange="toggleTodo(${c.id})">
        <span class="t-title">${esc(c.title)}</span>
        ${isActive?'<span class="t-badge tracking">● tracking</span>':''}
        ${c.auto_generated?'<span class="t-badge auto">auto</span>':'<span class="t-badge manual">manual</span>'}
        <button class="t-del" onclick="event.stopPropagation();deleteTodo(${c.id})">×</button>
      </div>`;
    });
    // Inline add-task
    html += `<div style="display:flex;gap:6px;padding:6px 0;margin-top:2px">
      <input id="add-task-${p.id}" class="input" placeholder="+ Add task..." style="flex:1;padding:5px 10px;font-size:12px"
        onkeydown="if(event.key==='Enter')addTaskToBucket(${p.id})">
      <button onclick="addTaskToBucket(${p.id})" style="padding:4px 10px;background:var(--accent);color:#fff;border:none;border-radius:5px;cursor:pointer;font-size:11px">Add</button>
    </div>`;
    html += '</div></div>';
  });
  // Orphan tasks
  const orphans = todos.filter(t => t.parent_id && !parents.find(pp => pp.id === t.parent_id));
  if (orphans.length) {
    html += '<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">';
    html += '<div style="font-size:11px;color:var(--text-tertiary);margin-bottom:4px">Unassigned</div>';
    orphans.forEach(c => {
      const isActive = activeTaskId === c.id;
      html += `<div class="todo-item child-item ${c.done?'done':''} ${isActive?'active':''}"
        data-task-id="${c.id}"
        draggable="true" ondragstart="dragTodo(event,${c.id})"
        onclick="event.target.tagName!=='INPUT'&&event.target.tagName!=='BUTTON'&&setActiveTask(${c.id})">
        <span class="drag-handle">⠿</span>
        <input type="checkbox" ${c.done?'checked':''} onchange="toggleTodo(${c.id})">
        <span class="t-title">${esc(c.title)}</span>
        ${isActive?'<span class="t-badge tracking">● tracking</span>':''}
        <span class="t-badge auto">auto</span>
        <button class="t-del" onclick="event.stopPropagation();deleteTodo(${c.id})">×</button>
      </div>`;
    });
    html += '</div>';
  }
  el.innerHTML = html;
}

// --- Activity by Task (Activity tab) ---
async function loadActivityByTask(dateStr) {
  const d = dateStr || selectedDate;
  const container = document.getElementById('activity-by-task');
  if (!container) return;
  try {
    const data = await fetchJSON('/api/activity/by-task?date=' + d);
    if (!data.tasks || (!data.tasks.length && !data.unassigned.entries.length)) {
      container.innerHTML = '<p style="color:var(--text-tertiary);font-size:13px">No task-linked activity recorded.</p>';
      return;
    }
    let html = '';
    data.tasks.forEach(hl => {
      if (hl.total_seconds === 0 && !hl.children.length) return;
      html += `<div class="activity-task-group">
        <div class="activity-task-header" onclick="this.parentElement.classList.toggle('collapsed')">
          <span class="chevron open">▶</span>
          <span style="font-weight:600">${esc(hl.title)}</span>
          <span style="margin-left:auto;font-size:12px;color:var(--text-secondary)">${hl.total_time}</span>
        </div>
        <div class="activity-task-children">`;
      hl.children.forEach(ll => {
        html += `<div class="activity-subtask">
          <div class="activity-subtask-header" onclick="this.parentElement.classList.toggle('collapsed')">
            <span class="chevron open" style="font-size:10px">▶</span>
            <span>${esc(ll.title)}</span>
            <span class="${ll.done?'done-badge':''}">${ll.done?'✓':''}</span>
            <span style="margin-left:auto;font-size:11px;color:var(--text-secondary)">${ll.total_time}</span>
          </div>
          <div class="activity-entries">`;
        if (ll.entries.length) {
          ll.entries.forEach(e => {
            html += `<div class="activity-entry">
              <span class="entry-app">${esc(e.app_name)}</span>
              <span class="entry-summary">${esc(e.summary)}</span>
              <span class="entry-time">${e.time_str}</span>
            </div>`;
          });
        } else {
          html += '<div style="font-size:11px;color:var(--text-tertiary);padding:4px 0">No activity recorded</div>';
        }
        html += '</div></div>';
      });
      html += '</div></div>';
    });
    // Unassigned
    if (data.unassigned && data.unassigned.entries.length) {
      html += `<div class="activity-task-group">
        <div class="activity-task-header" onclick="this.parentElement.classList.toggle('collapsed')">
          <span class="chevron open">▶</span>
          <span style="font-weight:600;color:var(--text-tertiary)">Unassigned</span>
          <span style="margin-left:auto;font-size:12px;color:var(--text-secondary)">${data.unassigned.total_time}</span>
        </div>
        <div class="activity-task-children"><div class="activity-entries">`;
      data.unassigned.entries.forEach(e => {
        html += `<div class="activity-entry">
          <span class="entry-app">${esc(e.app_name)}</span>
          <span class="entry-summary">${esc(e.summary)}</span>
          <span class="entry-time">${e.time_str}</span>
        </div>`;
      });
      html += '</div></div></div>';
    }
    container.innerHTML = html;
  } catch(e) { console.error(e); container.innerHTML = '<p style="color:var(--text-tertiary)">Error loading activity</p>'; }
}

// --- Activity (Category Breakdown) ---
async function loadActivity(dateStr) {
  selectedDate = dateStr || new Date().toISOString().split('T')[0];
  const d = await fetchJSON('/api/summary/daily?date=' + selectedDate);
  const container = document.getElementById('activity-breakdown');
  const label = document.getElementById('activity-date-label');
  const dt = new Date(selectedDate + 'T12:00:00');
  label.textContent = dt.toLocaleDateString('en-US', {weekday:'long', month:'long', day:'numeric', year:'numeric'});
  if (!d.categories || !d.categories.length) {
    container.innerHTML = '<p style="color:var(--text-tertiary);font-size:13px">No activity recorded.</p>';
    document.getElementById('activity-total').textContent = '0m';
    document.getElementById('activity-sessions').textContent = '0';
    return;
  }
  const maxTime = Math.max(...d.categories.map(c => parseDur(c.time_str)), 1);
  let html = '';
  d.categories.forEach((c, i) => {
    const pct = (parseDur(c.time_str) / maxTime * 100).toFixed(0);
    const hasSubs = c.sub_tasks && c.sub_tasks.length > 0;
    const maxSub = hasSubs ? Math.max(...c.sub_tasks.map(s => parseDur(s.time_str)), 1) : 1;
    html += `<div class="activity-cat"><div class="activity-cat-header" onclick="toggleSubs(${i})">
      <span class="chevron ${hasSubs?'open':''}" id="chev-${i}">${hasSubs?'▶':'•'}</span>
      <span class="activity-cat-name">${esc(c.category)}</span>
      <span class="activity-cat-bar"><span class="activity-cat-bar-fill" style="width:${pct}%"></span></span>
      <span class="activity-cat-time">${c.time_str}</span>
      <span class="activity-cat-sessions">${c.sessions} sess</span></div>`;
    if (hasSubs) {
      html += `<div class="activity-subs" id="subs-${i}">`;
      c.sub_tasks.forEach((s, si) => {
        const sp = (parseDur(s.time_str) / maxSub * 100).toFixed(0);
        if (s.collapsed && s.collapsed.length) {
          html += `<div class="activity-sub other-row" onclick="toggleCollapsed('col-${i}-${si}',this)">
            <span class="activity-sub-name" style="color:var(--accent)">▶ ${esc(s.name)}</span>
            <span class="activity-sub-bar"><span class="activity-sub-bar-fill" style="width:${sp}%;opacity:0.4"></span></span>
            <span class="activity-sub-time">${s.time_str}</span></div>
            <div id="col-${i}-${si}" class="collapsed-detail" style="display:none">`;
          s.collapsed.forEach(cc => { html += `<div class="collapsed-item"><span>${esc(cc.name)}</span><span>${cc.time_str}</span></div>`; });
          html += '</div>';
        } else {
          html += `<div class="activity-sub"><span class="activity-sub-name">${esc(s.name)}</span>
            <span class="activity-sub-bar"><span class="activity-sub-bar-fill" style="width:${sp}%"></span></span>
            <span class="activity-sub-time">${s.time_str}</span></div>`;
        }
      });
      html += '</div>';
    }
    html += '</div>';
  });
  container.innerHTML = html;
  document.getElementById('activity-total').textContent = d.total_time;
  document.getElementById('activity-sessions').textContent = d.total_sessions;
}
async function refreshActivity() { loadActivity(selectedDate); }

function toggleSubs(i) {
  const el = document.getElementById('subs-'+i), ch = document.getElementById('chev-'+i);
  if (!el) return; el.style.display = el.style.display==='none'?'':'none';
  if (ch) ch.classList.toggle('open');
}
function toggleCollapsed(id, row) {
  const el = document.getElementById(id); if (!el) return;
  const show = el.style.display === 'none'; el.style.display = show ? '' : 'none';
  const n = row.querySelector('.activity-sub-name');
  if (n) n.innerHTML = n.innerHTML.replace(/^[▶▼]/, show ? '▼' : '▶');
}

// --- Calendar ---
const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
async function renderCalendar() {
  const grid = document.getElementById('cal-grid');
  const title = document.getElementById('cal-title');
  const MN = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  title.textContent = MN[calMonth-1] + ' ' + calYear;
  const data = await fetchJSON(`/api/summary/month?year=${calYear}&month=${calMonth}`);
  let html = DAYS.map(d => `<div class="cal-header">${d}</div>`).join('');
  const firstDay = new Date(calYear, calMonth-1, 1).getDay();
  const dim = new Date(calYear, calMonth, 0).getDate();
  const today = new Date().toISOString().split('T')[0];
  for (let i = 0; i < firstDay; i++) html += '<div class="cal-day empty"></div>';
  for (let d = 1; d <= dim; d++) {
    const ds = `${calYear}-${String(calMonth).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const has = data.days && data.days[ds];
    html += `<div class="cal-day ${ds===today?'today':''} ${ds===selectedDate?'selected':''} ${has?'has-data':''}" onclick="selectDay('${ds}')" title="${has?data.days[ds].minutes+'m':''}">${d}</div>`;
  }
  grid.innerHTML = html;
}
function calPrev() { calMonth--; if(calMonth<1){calMonth=12;calYear--;} renderCalendar(); }
function calNext() { calMonth++; if(calMonth>12){calMonth=1;calYear++;} renderCalendar(); }
function selectDay(ds) { selectedDate = ds; loadActivity(ds); loadActivityByTask(ds); renderCalendar(); }

// --- Report ---
async function generateReport() {
  const s = document.getElementById('report-start').value, e = document.getElementById('report-end').value;
  if (!s||!e) { alert('Select both dates'); return; }
  const out = document.getElementById('report-output');
  out.className = 'report-output visible';
  out.innerHTML = '<p style="color:var(--text-tertiary)">Generating...</p>';
  const d = await fetchJSON(`/api/summary/range?start=${s}&end=${e}`);
  let html = `<div style="font-weight:600;margin-bottom:8px">${s} to ${e} — ${d.total_time}, ${d.total_sessions} sessions</div>`;
  d.days.forEach(day => {
    if (day.total_time==='0m') return;
    html += `<div style="margin-bottom:6px"><div style="font-weight:500;font-size:12px">${day.date} — ${day.total_time}</div>`;
    day.categories.forEach(c => { html += `<div style="font-size:11px;color:var(--text-secondary);padding-left:12px">${c.category}: ${c.time_str}</div>`; });
    html += '</div>';
  });
  out.innerHTML = html;
}

// --- Settings ---
async function loadConfig() {
  config = await fetchJSON('/api/config');
  const p = config.pomodoro || {};
  document.getElementById('s-work').value = p.work_minutes || 25;
  document.getElementById('s-short').value = p.short_break_minutes || 5;
  document.getElementById('s-long').value = p.long_break_minutes || 15;
  document.getElementById('s-interval').value = p.long_break_interval || 4;
  document.getElementById('s-debounce').value = config.debounce_threshold_seconds || 30;
  document.getElementById('s-poll').value = config.poll_interval_seconds || 5;
  const e = (config.report||{}).email||{};
  document.getElementById('s-smtp').value = e.smtp_server||'';
  document.getElementById('s-port').value = e.smtp_port||587;
  document.getElementById('s-user').value = e.smtp_username||'';
  document.getElementById('s-pass').value = e.smtp_password||'';
  document.getElementById('s-to').value = e.to_address||'';
}
async function saveSettings() {
  config.pomodoro = { work_minutes:+document.getElementById('s-work').value, short_break_minutes:+document.getElementById('s-short').value,
    long_break_minutes:+document.getElementById('s-long').value, long_break_interval:+document.getElementById('s-interval').value };
  config.debounce_threshold_seconds = +document.getElementById('s-debounce').value;
  config.poll_interval_seconds = +document.getElementById('s-poll').value;
  if(!config.report) config.report={};
  config.report.email = { smtp_server:document.getElementById('s-smtp').value, smtp_port:+document.getElementById('s-port').value,
    smtp_username:document.getElementById('s-user').value, smtp_password:document.getElementById('s-pass').value,
    to_address:document.getElementById('s-to').value, use_tls:true };
  await fetchJSON('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(config)});
  const msg = document.getElementById('settings-msg');
  msg.classList.add('visible'); setTimeout(()=>msg.classList.remove('visible'),2000);
}

// --- Todo CRUD actions ---
async function addTodo() {
  const inp = document.getElementById('todo-title'), title = inp.value.trim();
  if(!title) return;
  await fetchJSON('/api/todos',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title})});
  inp.value=''; refreshTodos();
}
async function toggleTodo(id) { await fetchJSON(`/api/todos/${id}/toggle`,{method:'POST'}); refreshTodos(); }
async function deleteTodo(id) { await fetchJSON(`/api/todos/${id}`,{method:'DELETE'}); refreshTodos(); }
async function clearAllTodos() { if(!confirm('Delete ALL tasks?')) return; await fetchJSON('/api/todos/clear-all',{method:'POST'}); refreshTodos(); }
async function clearAutoTodos() { if(!confirm('Delete auto-tracked tasks?')) return; await fetchJSON('/api/todos/clear-auto',{method:'POST'}); refreshTodos(); }

// --- Pomodoro controls ---
async function pomodoroStart() { await fetchJSON('/api/pomodoro/start',{method:'POST'}); refreshStatus(); }
async function pomodoroStop() { await fetchJSON('/api/pomodoro/stop',{method:'POST'}); refreshStatus(); }
async function pomodoroSkip() { await fetchJSON('/api/pomodoro/skip',{method:'POST'}); refreshStatus(); }

// --- Timers ---
setInterval(refreshStatus, 2000);
setInterval(refreshActivity, 15000);
setInterval(()=>{ if(!lastStatus||lastStatus==='completed'||lastStatus==='paused') return;
  updateTimerDisplay(Math.max(0,lastRemaining-(Date.now()-lastRemainingAt)/1000),lastTotal,lastStatus); }, 1000);

// --- Init ---
refreshStatus(); refreshTodos(); refreshActivity(); loadConfig(); renderCalendar();
document.getElementById('report-start').value = new Date(Date.now()-7*86400000).toISOString().split('T')[0];
document.getElementById('report-end').value = new Date().toISOString().split('T')[0];
