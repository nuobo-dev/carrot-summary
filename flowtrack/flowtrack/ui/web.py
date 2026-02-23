"""Web-based dashboard for FlowTrack.

A lightweight Flask app serving a single-page dashboard with:
- Settings editor
- Todo list (auto-populated + manual)
- Pomodoro timer display
- Activity overview
"""

import json
import logging
import os
import threading
from datetime import date, datetime, timedelta
from typing import Any, Optional

from flask import Flask, jsonify, render_template_string, request

logger = logging.getLogger(__name__)

# Will be set by start_dashboard()
_app_ref = None  # type: Optional[Any]  # FlowTrackApp


def create_flask_app() -> Flask:
    app = Flask(__name__)
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    @app.route("/")
    def index():
        return render_template_string(DASHBOARD_HTML)

    @app.route("/api/status")
    def api_status():
        if _app_ref is None:
            return jsonify({"error": "not initialized"})
        pm = _app_ref._pomodoro_manager
        session = None
        if pm and pm.active_session:
            s = pm.active_session
            elapsed_sec = s.elapsed.total_seconds()
            work_sec = pm.WORK_DURATION.total_seconds()
            if s.status.value == "active":
                remaining = max(0, work_sec - elapsed_sec)
            elif s.status.value == "break":
                brk = pm.get_break_duration(s.completed_count).total_seconds()
                remaining = max(0, brk - elapsed_sec)
            else:
                remaining = 0
            session = {
                "id": s.id,
                "category": s.category,
                "sub_category": s.sub_category,
                "status": s.status.value,
                "elapsed": int(elapsed_sec),
                "remaining": int(remaining),
                "completed_count": s.completed_count,
            }
        paused = []
        if pm:
            for cat, s in pm.paused_sessions.items():
                paused.append({"category": cat, "elapsed": int(s.elapsed.total_seconds()),
                               "completed_count": s.completed_count})
        return jsonify({
            "tracking": _app_ref._tracking,
            "session": session,
            "paused_sessions": paused,
        })

    @app.route("/api/summary/daily")
    def api_daily():
        if not _app_ref or not _app_ref._summary_generator:
            return jsonify({"error": "not ready"})
        from flowtrack.reporting.formatter import TextFormatter
        s = _app_ref._summary_generator.daily_summary(date.today())
        cats = []
        for c in s.categories:
            subs = []
            for sub_name, sub_time in sorted(c.sub_categories.items(), key=lambda x: x[1], reverse=True):
                if sub_name and sub_name != c.category:
                    subs.append({
                        "name": sub_name,
                        "time_str": TextFormatter.format_duration(sub_time),
                    })
            cats.append({
                "category": c.category,
                "time": str(c.total_time),
                "time_str": TextFormatter.format_duration(c.total_time),
                "sessions": c.completed_sessions,
                "sub_tasks": subs,
            })
        return jsonify({
            "date": str(s.date),
            "categories": cats,
            "total_time": TextFormatter.format_duration(s.total_time),
            "total_sessions": s.total_sessions,
        })

    @app.route("/api/todos")
    def api_todos():
        if not _app_ref or not _app_ref._store:
            return jsonify([])
        return jsonify(_app_ref._store.get_todos(include_done=True))

    @app.route("/api/todos", methods=["POST"])
    def api_add_todo():
        if not _app_ref or not _app_ref._store:
            return jsonify({"error": "not ready"}), 500
        data = request.json or {}
        title = data.get("title", "").strip()
        if not title:
            return jsonify({"error": "title required"}), 400
        cat = data.get("category", "")
        tid = _app_ref._store.add_todo(title, cat)
        return jsonify({"id": tid})

    @app.route("/api/todos/<int:tid>/toggle", methods=["POST"])
    def api_toggle_todo(tid):
        if _app_ref and _app_ref._store:
            _app_ref._store.toggle_todo(tid)
        return jsonify({"ok": True})

    @app.route("/api/todos/<int:tid>", methods=["DELETE"])
    def api_delete_todo(tid):
        if _app_ref and _app_ref._store:
            _app_ref._store.delete_todo(tid)
        return jsonify({"ok": True})

    @app.route("/api/config")
    def api_get_config():
        if not _app_ref:
            return jsonify({})
        return jsonify(_app_ref.config)

    @app.route("/api/config", methods=["POST"])
    def api_save_config():
        if not _app_ref:
            return jsonify({"error": "not ready"}), 500
        data = request.json
        if not isinstance(data, dict):
            return jsonify({"error": "invalid"}), 400
        from flowtrack.core.config import save_config
        _app_ref.config = data
        save_config(data, _app_ref.config_path)
        _app_ref._apply_config_changes()
        return jsonify({"ok": True})

    @app.route("/api/task/start", methods=["POST"])
    def api_start_task():
        if not _app_ref or not _app_ref._pomodoro_manager:
            return jsonify({"error": "not ready"}), 500
        data = request.json or {}
        cat = data.get("category", "").strip()
        sub = data.get("sub_category", "").strip() or cat
        if not cat:
            return jsonify({"error": "category required"}), 400
        _app_ref._pomodoro_manager.on_activity(cat, sub, datetime.now())
        return jsonify({"ok": True})

    @app.route("/api/tracking/toggle", methods=["POST"])
    def api_toggle_tracking():
        if _app_ref:
            _app_ref._toggle_tracking()
        return jsonify({"tracking": _app_ref._tracking if _app_ref else False})

    return app


def start_dashboard(app_ref, port: int = 5555) -> threading.Thread:
    """Start the Flask dashboard in a daemon thread."""
    global _app_ref
    _app_ref = app_ref
    flask_app = create_flask_app()

    def _run():
        flask_app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

    t = threading.Thread(target=_run, daemon=True, name="flowtrack-web")
    t.start()
    logger.info("Dashboard started at http://127.0.0.1:%d", port)
    return t



DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FlowTrack Dashboard</title>
<style>
  :root { --bg: #f8f9fa; --card: #fff; --accent: #e8724a; --accent2: #5a9a6e;
          --text: #333; --muted: #888; --border: #e5e5e5; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.5; }
  .container { max-width: 900px; margin: 0 auto; padding: 20px; }
  h1 { font-size: 1.4em; font-weight: 600; margin-bottom: 20px; display: flex;
       align-items: center; gap: 10px; }
  h1 .carrot { font-size: 1.6em; }
  .tabs { display: flex; gap: 0; border-bottom: 2px solid var(--border); margin-bottom: 20px; }
  .tab { padding: 10px 20px; cursor: pointer; border-bottom: 2px solid transparent;
         margin-bottom: -2px; color: var(--muted); font-weight: 500; font-size: 0.9em; }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab:hover { color: var(--text); }
  .panel { display: none; }
  .panel.active { display: block; }
  .card { background: var(--card); border-radius: 10px; padding: 20px; margin-bottom: 16px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
  .card h2 { font-size: 1em; font-weight: 600; margin-bottom: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; font-size: 0.75em; }
  /* Pomodoro timer */
  .timer-ring { width: 200px; height: 200px; margin: 0 auto 16px; position: relative; }
  .timer-ring svg { transform: rotate(-90deg); }
  .timer-ring circle { fill: none; stroke-width: 8; }
  .timer-ring .bg { stroke: var(--border); }
  .timer-ring .fg { stroke: var(--accent); stroke-linecap: round; transition: stroke-dashoffset 1s linear; }
  .timer-ring .fg.break { stroke: var(--accent2); }
  .timer-text { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
                text-align: center; }
  .timer-text .time { font-size: 2.4em; font-weight: 300; font-variant-numeric: tabular-nums; }
  .timer-text .label { font-size: 0.8em; color: var(--muted); }
  .session-info { text-align: center; margin-bottom: 12px; }
  .session-info .cat { font-weight: 600; font-size: 1.1em; }
  .session-info .count { color: var(--muted); font-size: 0.85em; }
  .dots { display: flex; justify-content: center; gap: 6px; margin: 8px 0; }
  .dots .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--border); }
  .dots .dot.filled { background: var(--accent); }
  /* Todo */
  .todo-input { display: flex; gap: 8px; margin-bottom: 12px; }
  .todo-input input { flex: 1; padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px; font-size: 0.9em; }
  .todo-input button { padding: 8px 16px; background: var(--accent); color: #fff; border: none;
                       border-radius: 6px; cursor: pointer; font-size: 0.9em; }
  .todo-list { list-style: none; }
  .todo-item { display: flex; align-items: center; gap: 10px; padding: 8px 0;
               border-bottom: 1px solid var(--border); }
  .todo-item:last-child { border-bottom: none; }
  .todo-item.done .todo-title { text-decoration: line-through; color: var(--muted); }
  .todo-item input[type=checkbox] { width: 18px; height: 18px; accent-color: var(--accent); }
  .todo-title { flex: 1; font-size: 0.9em; }
  .todo-cat { font-size: 0.75em; color: var(--muted); background: var(--bg); padding: 2px 8px; border-radius: 10px; }
  .todo-auto { font-size: 0.65em; color: var(--accent2); }
  .todo-del { background: none; border: none; color: var(--muted); cursor: pointer; font-size: 1.1em; }
  .todo-del:hover { color: #e55; }
  /* Activity table */
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px 12px; font-size: 0.9em; }
  th { color: var(--muted); font-weight: 500; font-size: 0.8em; text-transform: uppercase;
       border-bottom: 2px solid var(--border); }
  td { border-bottom: 1px solid var(--border); }
  .bar { height: 6px; border-radius: 3px; background: var(--accent); }
  /* Hierarchical activity breakdown */
  .activity-cat { margin-bottom: 16px; }
  .activity-cat-header { display: flex; align-items: center; gap: 10px; padding: 8px 0; cursor: pointer; }
  .activity-cat-header:hover { opacity: 0.8; }
  .activity-cat-name { font-weight: 600; font-size: 0.95em; flex: 1; }
  .activity-cat-time { font-size: 0.9em; color: var(--muted); min-width: 60px; text-align: right; }
  .activity-cat-sessions { font-size: 0.75em; color: var(--muted); min-width: 70px; text-align: right; }
  .activity-cat-bar { flex: 0 0 120px; height: 6px; border-radius: 3px; background: var(--border); overflow: hidden; }
  .activity-cat-bar-fill { height: 100%; border-radius: 3px; background: var(--accent); }
  .activity-subs { padding-left: 20px; border-left: 2px solid var(--border); margin-left: 8px; }
  .activity-sub { display: flex; align-items: center; gap: 10px; padding: 4px 0; font-size: 0.85em; color: var(--text); }
  .activity-sub-name { flex: 1; }
  .activity-sub-time { color: var(--muted); min-width: 60px; text-align: right; }
  .activity-sub-bar { flex: 0 0 80px; height: 4px; border-radius: 2px; background: var(--border); overflow: hidden; }
  .activity-sub-bar-fill { height: 100%; border-radius: 2px; background: var(--accent); opacity: 0.6; }
  .chevron { font-size: 0.7em; color: var(--muted); transition: transform 0.2s; }
  .chevron.open { transform: rotate(90deg); }
  /* Settings */
  .setting-group { margin-bottom: 16px; }
  .setting-group label { display: block; font-size: 0.8em; color: var(--muted); margin-bottom: 4px; font-weight: 500; }
  .setting-group input, .setting-group select { width: 100%; padding: 8px 12px; border: 1px solid var(--border);
    border-radius: 6px; font-size: 0.9em; }
  .setting-group input[type=number] { width: 120px; }
  .setting-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .btn { padding: 8px 20px; border: none; border-radius: 6px; cursor: pointer; font-size: 0.9em; }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-secondary { background: var(--border); color: var(--text); }
  .btn:hover { opacity: 0.9; }
  .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
  .status-dot.on { background: var(--accent2); }
  .status-dot.off { background: var(--muted); }
  .tracking-toggle { cursor: pointer; padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border);
                     background: var(--card); font-size: 0.85em; }
  .flex-between { display: flex; justify-content: space-between; align-items: center; }
  .paused-list { margin-top: 12px; }
  .paused-item { font-size: 0.85em; color: var(--muted); padding: 4px 0; }
  .msg { padding: 8px 12px; background: #e8f5e9; border-radius: 6px; margin-bottom: 12px; font-size: 0.85em; color: #2e7d32; display: none; }
</style>
</head>
<body>
<div class="container">
  <h1><span class="carrot">🥕</span> FlowTrack</h1>
  <div class="tabs">
    <div class="tab active" data-tab="timer">Timer</div>
    <div class="tab" data-tab="todos">Tasks</div>
    <div class="tab" data-tab="activity">Activity</div>
    <div class="tab" data-tab="settings">Settings</div>
  </div>

  <!-- TIMER -->
  <div class="panel active" id="panel-timer">
    <div class="card">
      <div class="flex-between" style="margin-bottom:16px">
        <h2>Pomodoro Timer</h2>
        <button class="tracking-toggle" onclick="toggleTracking()">
          <span class="status-dot" id="status-dot"></span>
          <span id="tracking-label">Loading...</span>
        </button>
      </div>
      <div id="timer-content">
        <div class="timer-ring">
          <svg viewBox="0 0 200 200" width="200" height="200">
            <circle class="bg" cx="100" cy="100" r="90"/>
            <circle class="fg" id="timer-arc" cx="100" cy="100" r="90"
                    stroke-dasharray="565.5" stroke-dashoffset="0"/>
          </svg>
          <div class="timer-text">
            <div class="time" id="timer-time">--:--</div>
            <div class="label" id="timer-label">No session</div>
          </div>
        </div>
        <div class="session-info">
          <div class="cat" id="session-cat">-</div>
          <div class="count" id="session-count">0 sessions completed</div>
        </div>
        <div class="dots" id="session-dots"></div>
      </div>
      <div style="text-align:center;margin-top:12px">
        <input id="task-cat" placeholder="Category" style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;width:140px">
        <input id="task-sub" placeholder="Sub-category" style="padding:6px 10px;border:1px solid #ddd;border-radius:6px;width:140px">
        <button class="btn btn-primary" onclick="startTask()" style="margin-left:4px">Start Task</button>
      </div>
    </div>
    <div class="card" id="paused-card" style="display:none">
      <h2>Paused Sessions</h2>
      <div id="paused-list"></div>
    </div>
  </div>

  <!-- TODOS -->
  <div class="panel" id="panel-todos">
    <div class="card">
      <h2>Task List</h2>
      <div class="todo-input">
        <input id="todo-title" placeholder="Add a task..." onkeydown="if(event.key==='Enter')addTodo()">
        <button onclick="addTodo()">Add</button>
      </div>
      <ul class="todo-list" id="todo-list"></ul>
    </div>
  </div>

  <!-- ACTIVITY -->
  <div class="panel" id="panel-activity">
    <div class="card">
      <h2>Today's Activity</h2>
      <div id="activity-breakdown"></div>
      <div style="margin-top:12px;text-align:right;color:var(--muted);font-size:0.85em">
        Total: <strong id="activity-total">0m</strong> &middot; <span id="activity-sessions">0</span> sessions
      </div>
    </div>
  </div>

  <!-- SETTINGS -->
  <div class="panel" id="panel-settings">
    <div class="msg" id="settings-msg">Settings saved!</div>
    <div class="card">
      <h2>Pomodoro</h2>
      <div class="setting-row">
        <div class="setting-group"><label>Work (min)</label><input type="number" id="s-work" min="1" max="120"></div>
        <div class="setting-group"><label>Short Break (min)</label><input type="number" id="s-short" min="1" max="60"></div>
        <div class="setting-group"><label>Long Break (min)</label><input type="number" id="s-long" min="1" max="60"></div>
        <div class="setting-group"><label>Long Break After</label><input type="number" id="s-interval" min="1" max="20"></div>
      </div>
      <div class="setting-row" style="margin-top:8px">
        <div class="setting-group"><label>Debounce (sec)</label><input type="number" id="s-debounce" min="1" max="300"></div>
        <div class="setting-group"><label>Poll Interval (sec)</label><input type="number" id="s-poll" min="1" max="60"></div>
      </div>
    </div>
    <div class="card">
      <h2>Email / Report</h2>
      <p style="font-size:0.8em;color:var(--muted);margin-bottom:12px">
        Optional — send your weekly report to your email. For Gmail, use an
        <a href="https://myaccount.google.com/apppasswords" target="_blank" style="color:var(--accent)">App Password</a>.
        For Outlook: smtp-mail.outlook.com:587. See README for full setup guide.
      </p>
      <div class="setting-row">
        <div class="setting-group"><label>SMTP Server</label><input id="s-smtp" placeholder="e.g. smtp.gmail.com"></div>
        <div class="setting-group"><label>Port</label><input type="number" id="s-port" placeholder="587"></div>
      </div>
      <div class="setting-row">
        <div class="setting-group"><label>Username</label><input id="s-user" placeholder="your.email@gmail.com"></div>
        <div class="setting-group"><label>Password</label><input type="password" id="s-pass" placeholder="App password (not your regular password)"></div>
      </div>
      <div class="setting-group"><label>Recipient</label><input id="s-to" placeholder="where to send reports (can be same as username)"></div>
    </div>
    <div style="text-align:right;margin-top:8px">
      <button class="btn btn-primary" onclick="saveSettings()">Save Settings</button>
    </div>
  </div>
</div>

<script>
let config = {};
const C = 2 * Math.PI * 90; // circumference

document.querySelectorAll('.tab').forEach(t => {
  t.onclick = () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('panel-' + t.dataset.tab).classList.add('active');
  };
});

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  return r.json();
}

async function refreshStatus() {
  try {
    const d = await fetchJSON('/api/status');
    const dot = document.getElementById('status-dot');
    const lbl = document.getElementById('tracking-label');
    dot.className = 'status-dot ' + (d.tracking ? 'on' : 'off');
    lbl.textContent = d.tracking ? 'Tracking' : 'Stopped';

    const arc = document.getElementById('timer-arc');
    const timeEl = document.getElementById('timer-time');
    const labelEl = document.getElementById('timer-label');
    const catEl = document.getElementById('session-cat');
    const countEl = document.getElementById('session-count');

    if (d.session) {
      const s = d.session;
      const rem = s.remaining;
      const total = s.status === 'break' ? (s.completed_count > 0 && s.completed_count % 4 === 0 ? 900 : 300) : 1500;
      const pct = Math.max(0, rem / total);
      arc.style.strokeDashoffset = C * (1 - pct);
      arc.classList.toggle('break', s.status === 'break');
      const m = Math.floor(rem / 60), sec = rem % 60;
      timeEl.textContent = String(m).padStart(2,'0') + ':' + String(sec).padStart(2,'0');
      labelEl.textContent = s.status === 'break' ? 'Break' : s.status === 'active' ? 'Focus' : s.status;
      catEl.textContent = s.category + (s.sub_category && s.sub_category !== s.category ? ' / ' + s.sub_category : '');
      countEl.textContent = s.completed_count + ' session' + (s.completed_count !== 1 ? 's' : '') + ' completed';
      // dots
      const dots = document.getElementById('session-dots');
      dots.innerHTML = '';
      for (let i = 0; i < 4; i++) {
        const d2 = document.createElement('div');
        d2.className = 'dot' + (i < (s.completed_count % 4 || (s.completed_count > 0 && s.completed_count % 4 === 0 ? 4 : 0)) ? ' filled' : '');
        dots.appendChild(d2);
      }
    } else {
      arc.style.strokeDashoffset = C;
      timeEl.textContent = '--:--';
      labelEl.textContent = 'No session';
      catEl.textContent = '-';
      countEl.textContent = '0 sessions completed';
      document.getElementById('session-dots').innerHTML = '';
    }
    // paused
    const pc = document.getElementById('paused-card');
    const pl = document.getElementById('paused-list');
    if (d.paused_sessions && d.paused_sessions.length > 0) {
      pc.style.display = '';
      pl.innerHTML = d.paused_sessions.map(p =>
        `<div class="paused-item">⏸ ${p.category} — ${Math.floor(p.elapsed/60)}m elapsed, ${p.completed_count} sessions</div>`
      ).join('');
    } else { pc.style.display = 'none'; }
  } catch(e) { console.error(e); }
}

async function refreshTodos() {
  const todos = await fetchJSON('/api/todos');
  const ul = document.getElementById('todo-list');
  ul.innerHTML = todos.map(t => `
    <li class="todo-item ${t.done ? 'done' : ''}">
      <input type="checkbox" ${t.done ? 'checked' : ''} onchange="toggleTodo(${t.id})">
      <span class="todo-title">${esc(t.title)}</span>
      ${t.category ? '<span class="todo-cat">' + esc(t.category) + '</span>' : ''}
      ${t.auto_generated ? '<span class="todo-auto">auto</span>' : ''}
      <button class="todo-del" onclick="deleteTodo(${t.id})">×</button>
    </li>
  `).join('');
}

async function refreshActivity() {
  const d = await fetchJSON('/api/summary/daily');
  const container = document.getElementById('activity-breakdown');
  if (!d.categories || d.categories.length === 0) {
    container.innerHTML = '<p style="color:var(--muted);font-size:0.9em">No activity recorded yet today.</p>';
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
    html += `<div class="activity-cat">
      <div class="activity-cat-header" onclick="toggleSubs(${i})">
        <span class="chevron ${hasSubs ? 'open' : ''}" id="chev-${i}">${hasSubs ? '▶' : '•'}</span>
        <span class="activity-cat-name">${esc(c.category)}</span>
        <span class="activity-cat-bar"><span class="activity-cat-bar-fill" style="width:${pct}%"></span></span>
        <span class="activity-cat-time">${c.time_str}</span>
        <span class="activity-cat-sessions">${c.sessions} sess</span>
      </div>`;
    if (hasSubs) {
      html += `<div class="activity-subs" id="subs-${i}">`;
      c.sub_tasks.forEach(s => {
        const sp = (parseDur(s.time_str) / maxSub * 100).toFixed(0);
        html += `<div class="activity-sub">
          <span class="activity-sub-name">${esc(s.name)}</span>
          <span class="activity-sub-bar"><span class="activity-sub-bar-fill" style="width:${sp}%"></span></span>
          <span class="activity-sub-time">${s.time_str}</span>
        </div>`;
      });
      html += '</div>';
    }
    html += '</div>';
  });
  container.innerHTML = html;
  document.getElementById('activity-total').textContent = d.total_time;
  document.getElementById('activity-sessions').textContent = d.total_sessions;
}

function toggleSubs(i) {
  const el = document.getElementById('subs-' + i);
  const chev = document.getElementById('chev-' + i);
  if (!el) return;
  if (el.style.display === 'none') {
    el.style.display = '';
    if (chev) chev.classList.add('open');
  } else {
    el.style.display = 'none';
    if (chev) chev.classList.remove('open');
  }
}

function parseDur(s) {
  let m = 0;
  const hm = s.match(/(\d+)h/); if (hm) m += parseInt(hm[1]) * 60;
  const mm = s.match(/(\d+)m/); if (mm) m += parseInt(mm[1]);
  return m || 1;
}

async function loadConfig() {
  config = await fetchJSON('/api/config');
  const p = config.pomodoro || {};
  document.getElementById('s-work').value = p.work_minutes || 25;
  document.getElementById('s-short').value = p.short_break_minutes || 5;
  document.getElementById('s-long').value = p.long_break_minutes || 15;
  document.getElementById('s-interval').value = p.long_break_interval || 4;
  document.getElementById('s-debounce').value = config.debounce_threshold_seconds || 30;
  document.getElementById('s-poll').value = config.poll_interval_seconds || 5;
  const e = (config.report || {}).email || {};
  document.getElementById('s-smtp').value = e.smtp_server || '';
  document.getElementById('s-port').value = e.smtp_port || 587;
  document.getElementById('s-user').value = e.smtp_username || '';
  document.getElementById('s-pass').value = e.smtp_password || '';
  document.getElementById('s-to').value = e.to_address || '';
}

async function saveSettings() {
  config.pomodoro = {
    work_minutes: parseInt(document.getElementById('s-work').value),
    short_break_minutes: parseInt(document.getElementById('s-short').value),
    long_break_minutes: parseInt(document.getElementById('s-long').value),
    long_break_interval: parseInt(document.getElementById('s-interval').value),
  };
  config.debounce_threshold_seconds = parseInt(document.getElementById('s-debounce').value);
  config.poll_interval_seconds = parseInt(document.getElementById('s-poll').value);
  if (!config.report) config.report = {};
  config.report.email = {
    smtp_server: document.getElementById('s-smtp').value,
    smtp_port: parseInt(document.getElementById('s-port').value),
    smtp_username: document.getElementById('s-user').value,
    smtp_password: document.getElementById('s-pass').value,
    to_address: document.getElementById('s-to').value,
    use_tls: true,
  };
  await fetchJSON('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(config)});
  const msg = document.getElementById('settings-msg');
  msg.style.display = 'block';
  setTimeout(() => msg.style.display = 'none', 2000);
}

async function addTodo() {
  const inp = document.getElementById('todo-title');
  const title = inp.value.trim();
  if (!title) return;
  await fetchJSON('/api/todos', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title})});
  inp.value = '';
  refreshTodos();
}

async function toggleTodo(id) {
  await fetchJSON(`/api/todos/${id}/toggle`, {method:'POST'});
  refreshTodos();
}

async function deleteTodo(id) {
  await fetchJSON(`/api/todos/${id}`, {method:'DELETE'});
  refreshTodos();
}

async function toggleTracking() {
  await fetchJSON('/api/tracking/toggle', {method:'POST'});
  refreshStatus();
}

async function startTask() {
  const cat = document.getElementById('task-cat').value.trim();
  const sub = document.getElementById('task-sub').value.trim();
  if (!cat) { document.getElementById('task-cat').focus(); return; }
  await fetchJSON('/api/task/start', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({category:cat, sub_category:sub})});
  document.getElementById('task-cat').value = '';
  document.getElementById('task-sub').value = '';
  refreshStatus();
}

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// Auto-refresh
setInterval(refreshStatus, 2000);
setInterval(refreshActivity, 15000);
setInterval(refreshTodos, 10000);

// Initial load
refreshStatus(); refreshTodos(); refreshActivity(); loadConfig();
</script>
</body>
</html>"""
