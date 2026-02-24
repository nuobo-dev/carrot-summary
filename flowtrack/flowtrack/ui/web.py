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
        date_str = request.args.get("date")
        target = date.fromisoformat(date_str) if date_str else date.today()
        s = _app_ref._summary_generator.daily_summary(target)
        cats = _build_category_response(s.categories, TextFormatter)
        return jsonify({
            "date": str(s.date),
            "categories": cats,
            "total_time": TextFormatter.format_duration(s.total_time),
            "total_sessions": s.total_sessions,
        })

    @app.route("/api/summary/range")
    def api_range_summary():
        """Summary for a date range (for report generation)."""
        if not _app_ref or not _app_ref._summary_generator:
            return jsonify({"error": "not ready"})
        from flowtrack.reporting.formatter import TextFormatter
        start_str = request.args.get("start")
        end_str = request.args.get("end")
        if not start_str or not end_str:
            return jsonify({"error": "start and end required"}), 400
        start_d = date.fromisoformat(start_str)
        end_d = date.fromisoformat(end_str)
        days = []
        d = start_d
        while d <= end_d:
            ds = _app_ref._summary_generator.daily_summary(d)
            cats = _build_category_response(ds.categories, TextFormatter)
            days.append({
                "date": str(ds.date),
                "categories": cats,
                "total_time": TextFormatter.format_duration(ds.total_time),
                "total_sessions": ds.total_sessions,
            })
            d += timedelta(days=1)
        # Aggregate totals
        total_sec = sum(ds.total_time.total_seconds() for ds in [_app_ref._summary_generator.daily_summary(start_d + timedelta(days=i)) for i in range((end_d - start_d).days + 1)])
        total_sess = sum(d2["total_sessions"] for d2 in days)
        return jsonify({
            "start": str(start_d), "end": str(end_d),
            "days": days,
            "total_time": TextFormatter.format_duration(timedelta(seconds=total_sec)),
            "total_sessions": total_sess,
        })

    @app.route("/api/summary/month")
    def api_month_summary():
        """Quick overview of which days have activity for calendar rendering."""
        if not _app_ref or not _app_ref._store:
            return jsonify({"error": "not ready"})
        year = int(request.args.get("year", date.today().year))
        month = int(request.args.get("month", date.today().month))
        from calendar import monthrange
        _, num_days = monthrange(year, month)
        day_totals = {}
        for day_num in range(1, num_days + 1):
            d = date(year, month, day_num)
            if d > date.today():
                break
            start_dt = datetime(year, month, day_num)
            end_dt = start_dt + timedelta(days=1)
            count = len(_app_ref._store.get_activities(start_dt, end_dt))
            if count > 0:
                from flowtrack.reporting.formatter import TextFormatter
                poll = _app_ref.config.get("poll_interval_seconds", 5)
                minutes = (count * poll) // 60
                day_totals[str(d)] = {"count": count, "minutes": minutes}
        return jsonify({"year": year, "month": month, "days": day_totals})

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

    @app.route("/api/todos/<int:tid>/move", methods=["POST"])
    def api_move_todo(tid):
        if not _app_ref or not _app_ref._store:
            return jsonify({"error": "not ready"}), 500
        data = request.json or {}
        parent_id = data.get("parent_id")  # None = unparent
        _app_ref._store.move_todo(tid, parent_id)
        return jsonify({"ok": True})

    @app.route("/api/todos/clear-all", methods=["POST"])
    def api_clear_all_todos():
        if _app_ref and _app_ref._store:
            _app_ref._store.clear_all_todos()
        return jsonify({"ok": True})

    @app.route("/api/todos/clear-auto", methods=["POST"])
    def api_clear_auto_todos():
        if _app_ref and _app_ref._store:
            _app_ref._store.clear_auto_todos()
        return jsonify({"ok": True})

    @app.route("/api/todos/merge", methods=["POST"])
    def api_merge_buckets():
        if not _app_ref or not _app_ref._store:
            return jsonify({"error": "not ready"}), 500
        data = request.json or {}
        source_id = data.get("source_id")
        target_id = data.get("target_id")
        if not source_id or not target_id:
            return jsonify({"error": "source_id and target_id required"}), 400
        _app_ref._store.merge_buckets(source_id, target_id)
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



def _build_category_response(categories, TextFormatter):
    """Build API response for categories, collapsing <5min sub-tasks into 'Other'."""
    cats = []
    for c in categories:
        main_subs = []
        other_subs = []
        for sub_name, sub_time in sorted(c.sub_categories.items(), key=lambda x: x[1], reverse=True):
            display_name = f"General {c.category.lower()}" if (sub_name == c.category or not sub_name) else sub_name
            minutes = sub_time.total_seconds() / 60
            entry = {"name": display_name, "time_str": TextFormatter.format_duration(sub_time)}
            if minutes >= 1:
                main_subs.append(entry)
            else:
                other_subs.append(entry)
        # Collapse small tasks into a single "Other" entry with expandable detail
        if other_subs:
            from datetime import timedelta as td
            other_total = sum((s.total_seconds() for n, s in c.sub_categories.items()
                              if s.total_seconds() < 60 and n != c.category), 0)
            main_subs.append({
                "name": f"Other ({len(other_subs)} items)",
                "time_str": TextFormatter.format_duration(td(seconds=other_total)),
                "collapsed": other_subs,
            })
        cats.append({
            "category": c.category,
            "time": str(c.total_time),
            "time_str": TextFormatter.format_duration(c.total_time),
            "sessions": c.completed_sessions,
            "sub_tasks": main_subs,
        })
    return cats


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FlowTrack Dashboard</title>
<style>
  :root { --bg: #f8f9fa; --card: #fff; --accent: #e8724a; --accent2: #5a9a6e;
          --text: #333; --muted: #888; --border: #e5e5e5; --active-bg: #fff7f4; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.5; }
  .container { max-width: 900px; margin: 0 auto; padding: 20px; }
  h1 { font-size: 1.4em; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; }
  .tabs { display: flex; gap: 0; border-bottom: 2px solid var(--border); margin-bottom: 20px; }
  .tab { padding: 10px 20px; cursor: pointer; border-bottom: 2px solid transparent;
         margin-bottom: -2px; color: var(--muted); font-weight: 500; font-size: 0.9em; }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab:hover { color: var(--text); }
  .panel { display: none; } .panel.active { display: block; }
  .card { background: var(--card); border-radius: 10px; padding: 20px; margin-bottom: 16px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
  .card h2 { font-weight: 600; margin-bottom: 12px; color: var(--muted); text-transform: uppercase;
             letter-spacing: 0.5px; font-size: 0.75em; }
</style>
</head>
<body>
<div class="container">
  <h1><span style="font-size:1.6em">🥕</span> FlowTrack</h1>
  <div class="tabs">
    <div class="tab active" data-tab="focus">Focus</div>
    <div class="tab" data-tab="activity">Activity</div>
    <div class="tab" data-tab="settings">Settings</div>
  </div>

  <!-- FOCUS (Timer + Tasks combined) -->
  <div class="panel active" id="panel-focus">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <h2>Pomodoro Timer</h2>
        <button id="track-btn" onclick="toggleTracking()" style="cursor:pointer;padding:6px 14px;border-radius:6px;border:1px solid var(--border);background:var(--card);font-size:0.85em">
          <span id="status-dot" style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px"></span>
          <span id="tracking-label">Loading...</span>
        </button>
      </div>
      <div style="display:flex;gap:24px;align-items:center;flex-wrap:wrap">
        <div style="position:relative;width:160px;height:160px;flex-shrink:0">
          <svg viewBox="0 0 200 200" width="160" height="160" style="transform:rotate(-90deg)">
            <circle fill="none" stroke="var(--border)" stroke-width="10" cx="100" cy="100" r="90"/>
            <circle id="timer-arc" fill="none" stroke="var(--accent)" stroke-width="10" stroke-linecap="round"
                    cx="100" cy="100" r="90" stroke-dasharray="565.5" stroke-dashoffset="0" style="transition:stroke-dashoffset 1s linear"/>
          </svg>
          <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center">
            <div id="timer-time" style="font-size:2em;font-weight:300;font-variant-numeric:tabular-nums">--:--</div>
            <div id="timer-label" style="font-size:0.8em;color:var(--muted)">No session</div>
          </div>
        </div>
        <div style="flex:1;min-width:200px">
          <div id="session-cat" style="font-weight:600;font-size:1.1em;margin-bottom:4px">-</div>
          <div id="session-count" style="color:var(--muted);font-size:0.85em;margin-bottom:8px">0 sessions completed</div>
          <div id="session-dots" style="display:flex;gap:6px;margin-bottom:12px"></div>
          <div id="paused-list" style="font-size:0.85em;color:var(--muted)"></div>
        </div>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input id="task-cat" placeholder="Task name" style="flex:1;min-width:150px;padding:8px 12px;border:1px solid var(--border);border-radius:6px;font-size:0.9em">
        <input id="task-sub" placeholder="Details (optional)" style="flex:1;min-width:120px;padding:8px 12px;border:1px solid var(--border);border-radius:6px;font-size:0.9em">
        <button onclick="startTask()" style="padding:8px 20px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.9em;white-space:nowrap">Start Task</button>
      </div>
    </div>

    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h2 style="margin-bottom:0">Task List</h2>
        <div style="display:flex;gap:6px">
          <button onclick="clearAutoTodos()" style="padding:4px 10px;background:var(--bg);color:var(--muted);border:1px solid var(--border);border-radius:6px;cursor:pointer;font-size:0.75em">Clear Auto</button>
          <button onclick="clearAllTodos()" style="padding:4px 10px;background:var(--bg);color:#e55;border:1px solid var(--border);border-radius:6px;cursor:pointer;font-size:0.75em">Clear All</button>
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-bottom:12px">
        <input id="todo-title" placeholder="Add a work bucket..." onkeydown="if(event.key==='Enter')addTodo()"
               style="flex:1;padding:8px 12px;border:1px solid var(--border);border-radius:6px;font-size:0.9em">
        <button onclick="addTodo()" style="padding:8px 16px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.9em">Add</button>
      </div>
      <div id="todo-list" style="list-style:none"></div>
    </div>
  </div>

  <!-- ACTIVITY -->
  <div class="panel" id="panel-activity">
    <!-- Calendar -->
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <button onclick="calPrev()" style="background:none;border:1px solid var(--border);border-radius:6px;padding:4px 10px;cursor:pointer">◀</button>
        <span id="cal-title" style="font-weight:600"></span>
        <button onclick="calNext()" style="background:none;border:1px solid var(--border);border-radius:6px;padding:4px 10px;cursor:pointer">▶</button>
      </div>
      <div id="cal-grid" style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;text-align:center;font-size:0.8em"></div>
    </div>
    <!-- Day detail -->
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <h2 id="activity-date-label" style="margin-bottom:0">Today's Activity</h2>
        <div style="color:var(--muted);font-size:0.85em">
          Total: <strong id="activity-total">0m</strong> &middot; <span id="activity-sessions">0</span> sessions
        </div>
      </div>
      <div id="activity-breakdown"></div>
    </div>
    <!-- Report generator -->
    <div class="card">
      <h2>Generate Report</h2>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <label style="font-size:0.8em;color:var(--muted)">From</label>
        <input type="date" id="report-start" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:0.85em">
        <label style="font-size:0.8em;color:var(--muted)">To</label>
        <input type="date" id="report-end" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:0.85em">
        <button onclick="generateReport()" style="padding:6px 16px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.85em">Generate</button>
      </div>
      <div id="report-output" style="margin-top:12px;display:none"></div>
    </div>
  </div>

  <!-- SETTINGS -->
  <div class="panel" id="panel-settings">
    <div id="settings-msg" style="padding:8px 12px;background:#e8f5e9;border-radius:6px;margin-bottom:12px;font-size:0.85em;color:#2e7d32;display:none">Settings saved!</div>
    <div class="card">
      <h2>Pomodoro</h2>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div><label style="display:block;font-size:0.8em;color:var(--muted);margin-bottom:4px">Work (min)</label><input type="number" id="s-work" min="1" max="120" style="width:120px;padding:8px 12px;border:1px solid var(--border);border-radius:6px"></div>
        <div><label style="display:block;font-size:0.8em;color:var(--muted);margin-bottom:4px">Short Break (min)</label><input type="number" id="s-short" min="1" max="60" style="width:120px;padding:8px 12px;border:1px solid var(--border);border-radius:6px"></div>
        <div><label style="display:block;font-size:0.8em;color:var(--muted);margin-bottom:4px">Long Break (min)</label><input type="number" id="s-long" min="1" max="60" style="width:120px;padding:8px 12px;border:1px solid var(--border);border-radius:6px"></div>
        <div><label style="display:block;font-size:0.8em;color:var(--muted);margin-bottom:4px">Long Break After</label><input type="number" id="s-interval" min="1" max="20" style="width:120px;padding:8px 12px;border:1px solid var(--border);border-radius:6px"></div>
        <div><label style="display:block;font-size:0.8em;color:var(--muted);margin-bottom:4px">Debounce (sec)</label><input type="number" id="s-debounce" min="1" max="300" style="width:120px;padding:8px 12px;border:1px solid var(--border);border-radius:6px"></div>
        <div><label style="display:block;font-size:0.8em;color:var(--muted);margin-bottom:4px">Poll Interval (sec)</label><input type="number" id="s-poll" min="1" max="60" style="width:120px;padding:8px 12px;border:1px solid var(--border);border-radius:6px"></div>
      </div>
    </div>
    <div class="card">
      <h2>Email / Report</h2>
      <p style="font-size:0.8em;color:var(--muted);margin-bottom:12px">Optional — send your weekly report to your email. For Gmail, use an <a href="https://myaccount.google.com/apppasswords" target="_blank" style="color:var(--accent)">App Password</a>. See README for full setup guide.</p>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <div><label style="display:block;font-size:0.8em;color:var(--muted);margin-bottom:4px">SMTP Server</label><input id="s-smtp" placeholder="smtp.gmail.com" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:6px"></div>
        <div><label style="display:block;font-size:0.8em;color:var(--muted);margin-bottom:4px">Port</label><input type="number" id="s-port" placeholder="587" style="width:120px;padding:8px 12px;border:1px solid var(--border);border-radius:6px"></div>
        <div><label style="display:block;font-size:0.8em;color:var(--muted);margin-bottom:4px">Username</label><input id="s-user" placeholder="your.email@gmail.com" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:6px"></div>
        <div><label style="display:block;font-size:0.8em;color:var(--muted);margin-bottom:4px">Password</label><input type="password" id="s-pass" placeholder="App password" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:6px"></div>
      </div>
      <div style="margin-top:12px"><label style="display:block;font-size:0.8em;color:var(--muted);margin-bottom:4px">Recipient</label><input id="s-to" placeholder="where to send reports" style="width:100%;padding:8px 12px;border:1px solid var(--border);border-radius:6px"></div>
    </div>
    <div style="text-align:right;margin-top:8px"><button onclick="saveSettings()" style="padding:8px 20px;background:var(--accent);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.9em">Save Settings</button></div>
  </div>
</div>

<style>
  .todo-item { display:flex; align-items:center; gap:10px; padding:8px 0; border-bottom:1px solid var(--border); }
  .todo-item:last-child { border-bottom:none; }
  .todo-item.done .t-title { text-decoration:line-through; color:var(--muted); }
  .todo-item.active { background:var(--active-bg); border-radius:6px; padding:8px; margin:-0px -8px; border-bottom:1px solid var(--border); }
  .todo-item input[type=checkbox] { width:18px; height:18px; accent-color:var(--accent); flex-shrink:0; }
  .t-title { flex:1; font-size:0.9em; }
  .t-badge { font-size:0.65em; padding:2px 8px; border-radius:10px; white-space:nowrap; }
  .t-badge.auto { background:#e8f5e9; color:var(--accent2); }
  .t-badge.manual { background:#e3f2fd; color:#1976d2; }
  .t-badge.tracking { background:var(--active-bg); color:var(--accent); font-weight:600; animation:pulse 2s infinite; }
  .t-cat { font-size:0.75em; color:var(--muted); background:var(--bg); padding:2px 8px; border-radius:10px; }
  .t-del { background:none; border:none; color:var(--muted); cursor:pointer; font-size:1.1em; }
  .t-del:hover { color:#e55; }
  .bucket { margin-bottom:12px; border:1px solid var(--border); border-radius:8px; overflow:hidden; }
  .bucket.drag-over { border-color:var(--accent); background:var(--active-bg); }
  .bucket-header { background:var(--bg); padding:10px 12px; }
  .bucket-children { padding:0 8px 4px 28px; }
  .child-item { font-size:0.88em; padding:6px 0; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.6} }
  .activity-cat { margin-bottom:16px; }
  .activity-cat-header { display:flex; align-items:center; gap:10px; padding:8px 0; cursor:pointer; }
  .activity-cat-header:hover { opacity:0.8; }
  .activity-cat-name { font-weight:600; font-size:0.95em; flex:1; }
  .activity-cat-time { font-size:0.9em; color:var(--muted); min-width:60px; text-align:right; }
  .activity-cat-sessions { font-size:0.75em; color:var(--muted); min-width:70px; text-align:right; }
  .activity-cat-bar { flex:0 0 120px; height:6px; border-radius:3px; background:var(--border); overflow:hidden; }
  .activity-cat-bar-fill { height:100%; border-radius:3px; background:var(--accent); }
  .activity-subs { padding-left:20px; border-left:2px solid var(--border); margin-left:8px; }
  .activity-sub { display:flex; align-items:center; gap:10px; padding:4px 0; font-size:0.85em; }
  .activity-sub-name { flex:1; }
  .activity-sub-time { color:var(--muted); min-width:60px; text-align:right; }
  .activity-sub-bar { flex:0 0 80px; height:4px; border-radius:2px; background:var(--border); overflow:hidden; }
  .activity-sub-bar-fill { height:100%; border-radius:2px; background:var(--accent); opacity:0.6; }
  .chevron { font-size:0.7em; color:var(--muted); transition:transform 0.2s; }
  .chevron.open { transform:rotate(90deg); }
  .cal-day { padding:6px 2px; border-radius:6px; cursor:pointer; position:relative; }
  .cal-day:hover { background:var(--border); }
  .cal-day.today { font-weight:700; color:var(--accent); }
  .cal-day.selected { background:var(--accent); color:#fff; border-radius:6px; }
  .cal-day.has-data::after { content:''; position:absolute; bottom:2px; left:50%; transform:translateX(-50%);
    width:4px; height:4px; border-radius:50%; background:var(--accent2); }
  .cal-day.empty { color:var(--border); cursor:default; }
  .cal-header { font-weight:600; color:var(--muted); font-size:0.7em; padding:4px 0; }
  .collapsed-toggle { cursor:pointer; color:var(--accent); font-size:0.8em; margin-left:8px; }
</style>

<script>
let config = {}, currentSession = null;
const C = 2 * Math.PI * 90;
let lastRemaining = 0, lastRemainingAt = 0, lastTotal = 1500, lastStatus = null;

document.querySelectorAll('.tab').forEach(t => {
  t.onclick = () => {
    document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('panel-' + t.dataset.tab).classList.add('active');
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

function updateTimerDisplay(remaining, total, status) {
  const arc = document.getElementById('timer-arc');
  const timeEl = document.getElementById('timer-time');
  const labelEl = document.getElementById('timer-label');
  if (!status) {
    arc.style.strokeDashoffset = C;
    arc.style.transition = 'none';
    timeEl.textContent = '--:--';
    labelEl.textContent = 'No session';
    return;
  }
  const pct = Math.max(0, remaining / total);
  arc.style.transition = 'stroke-dashoffset 0.9s linear';
  arc.style.strokeDashoffset = C * (1 - pct);
  arc.style.stroke = status === 'break' ? 'var(--accent2)' : 'var(--accent)';
  const rem = Math.max(0, Math.round(remaining));
  const m = Math.floor(rem / 60), sec = rem % 60;
  timeEl.textContent = String(m).padStart(2,'0') + ':' + String(sec).padStart(2,'0');
  labelEl.textContent = status === 'break' ? 'Break' : status === 'active' ? 'Focus' : status;
}

async function refreshStatus() {
  try {
    const d = await fetchJSON('/api/status');
    document.getElementById('status-dot').style.background = d.tracking ? 'var(--accent2)' : 'var(--muted)';
    document.getElementById('tracking-label').textContent = d.tracking ? 'Tracking' : 'Stopped';
    const arc = document.getElementById('timer-arc');
    currentSession = d.session;
    if (d.session) {
      const s = d.session, rem = s.remaining;
      const total = s.status === 'break' ? (s.completed_count > 0 && s.completed_count % 4 === 0 ? 900 : 300) : 1500;
      // Store for local interpolation
      lastRemaining = rem;
      lastRemainingAt = Date.now();
      lastTotal = total;
      lastStatus = s.status;
      updateTimerDisplay(rem, total, s.status);
      document.getElementById('session-cat').textContent = s.category + (s.sub_category && s.sub_category !== s.category ? ' / ' + s.sub_category : '');
      document.getElementById('session-count').textContent = s.completed_count + ' session' + (s.completed_count !== 1 ? 's' : '') + ' completed';
      const dots = document.getElementById('session-dots');
      dots.innerHTML = '';
      for (let i = 0; i < 4; i++) {
        const dot = document.createElement('div');
        dot.style.cssText = 'width:10px;height:10px;border-radius:50%;background:' +
          (i < (s.completed_count % 4 || (s.completed_count > 0 && s.completed_count % 4 === 0 ? 4 : 0)) ? 'var(--accent)' : 'var(--border)');
        dots.appendChild(dot);
      }
    } else {
      lastStatus = null;
      lastRemaining = 0;
      updateTimerDisplay(0, 1500, null);
      document.getElementById('session-cat').textContent = '-';
      document.getElementById('session-count').textContent = '0 sessions completed';
      document.getElementById('session-dots').innerHTML = '';
    }
    const pl = document.getElementById('paused-list');
    if (d.paused_sessions && d.paused_sessions.length > 0) {
      pl.innerHTML = d.paused_sessions.map(p => `<div style="padding:2px 0">⏸ ${esc(p.category)} — ${Math.floor(p.elapsed/60)}m, ${p.completed_count} sess</div>`).join('');
    } else { pl.innerHTML = ''; }
    // Re-render todos to update tracking highlight
    refreshTodos();
  } catch(e) { console.error(e); }
}
</script>

<script>
async function refreshTodos() {
  const todos = await fetchJSON('/api/todos');
  const el = document.getElementById('todo-list');
  const trackingCat = currentSession ? (currentSession.sub_category || currentSession.category) : null;

  // Separate into parents (top-level manual buckets) and children
  const parents = todos.filter(t => !t.parent_id);
  const childMap = {};
  todos.filter(t => t.parent_id).forEach(t => {
    if (!childMap[t.parent_id]) childMap[t.parent_id] = [];
    childMap[t.parent_id].push(t);
  });

  let html = '';
  parents.forEach(p => {
    const children = childMap[p.id] || [];
    const isTracking = !p.done && trackingCat && p.title.toLowerCase() === trackingCat.toLowerCase();
    html += `<div class="bucket" data-id="${p.id}" draggable="true"
                  ondragstart="dragBucket(event,${p.id})"
                  ondragover="event.preventDefault();this.classList.add('drag-over')"
                  ondragleave="this.classList.remove('drag-over')"
                  ondrop="dropOnBucket(event,${p.id})">
      <div class="todo-item bucket-header ${p.done ? 'done' : ''} ${isTracking ? 'active' : ''}">
        <span style="color:var(--muted);cursor:grab;margin-right:2px">⠿</span>
        <input type="checkbox" ${p.done ? 'checked' : ''} onchange="toggleTodo(${p.id})">
        <span class="t-title" style="font-weight:600">${esc(p.title)}</span>
        ${isTracking ? '<span class="t-badge tracking">● tracking</span>' : ''}
        <span class="t-badge manual">bucket</span>
        ${p.category ? '<span class="t-cat">' + esc(p.category) + '</span>' : ''}
        <span style="color:var(--muted);font-size:0.75em">${children.length} items</span>
        <button class="t-del" onclick="deleteTodo(${p.id})">×</button>
      </div>
      <div class="bucket-children">`;
    children.forEach(c => {
      const cTracking = !c.done && trackingCat && c.title.toLowerCase() === trackingCat.toLowerCase();
      html += `<div class="todo-item child-item ${c.done ? 'done' : ''} ${cTracking ? 'active' : ''}"
                    draggable="true" ondragstart="dragTodo(event,${c.id})">
        <span style="color:var(--muted);cursor:grab;margin-right:4px">⠿</span>
        <input type="checkbox" ${c.done ? 'checked' : ''} onchange="toggleTodo(${c.id})">
        <span class="t-title">${esc(c.title)}</span>
        ${cTracking ? '<span class="t-badge tracking">● tracking</span>' : ''}
        <span class="t-badge auto">auto</span>
        <button class="t-del" onclick="deleteTodo(${c.id})">×</button>
      </div>`;
    });
    html += '</div></div>';
  });

  // Show orphan auto-tasks (no parent) at the bottom
  const orphans = todos.filter(t => t.parent_id && !parents.find(p => p.id === t.parent_id));
  if (orphans.length > 0) {
    html += '<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border)">';
    html += '<div style="font-size:0.75em;color:var(--muted);margin-bottom:4px">Unassigned tasks (drag into a bucket above)</div>';
    orphans.forEach(c => {
      const cTracking = !c.done && trackingCat && c.title.toLowerCase() === trackingCat.toLowerCase();
      html += `<div class="todo-item child-item ${c.done ? 'done' : ''} ${cTracking ? 'active' : ''}"
                    draggable="true" ondragstart="dragTodo(event,${c.id})">
        <span style="color:var(--muted);cursor:grab;margin-right:4px">⠿</span>
        <input type="checkbox" ${c.done ? 'checked' : ''} onchange="toggleTodo(${c.id})">
        <span class="t-title">${esc(c.title)}</span>
        ${cTracking ? '<span class="t-badge tracking">● tracking</span>' : ''}
        <span class="t-badge auto">auto</span>
        <button class="t-del" onclick="deleteTodo(${c.id})">×</button>
      </div>`;
    });
    html += '</div>';
  }

  el.innerHTML = html;
}

let draggedTodoId = null, draggedBucketId = null;
function dragTodo(e, id) { draggedTodoId = id; draggedBucketId = null; e.dataTransfer.effectAllowed = 'move'; }
function dragBucket(e, id) { draggedBucketId = id; draggedTodoId = null; e.dataTransfer.effectAllowed = 'move'; }

async function dropOnBucket(e, targetId) {
  e.preventDefault();
  e.currentTarget.classList.remove('drag-over');
  if (draggedTodoId && draggedTodoId !== targetId) {
    // Move a child task into this bucket
    await fetchJSON(`/api/todos/${draggedTodoId}/move`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({parent_id:targetId})});
    refreshTodos();
  } else if (draggedBucketId && draggedBucketId !== targetId) {
    // Merge source bucket into target bucket
    if (confirm('Merge these two buckets? All tasks from the dragged bucket will move into this one.')) {
      await fetchJSON('/api/todos/merge', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({source_id:draggedBucketId, target_id:targetId})});
      refreshTodos();
    }
  }
  draggedTodoId = null;
  draggedBucketId = null;
}

// Keep old dropTodo for orphan area compatibility
async function dropTodo(e, parentId) { return dropOnBucket(e, parentId); }

async function clearAllTodos() {
  if (!confirm('Delete ALL tasks? This cannot be undone.')) return;
  await fetchJSON('/api/todos/clear-all', {method:'POST'});
  refreshTodos();
}

async function clearAutoTodos() {
  if (!confirm('Delete all auto-tracked tasks? Manual buckets will be kept.')) return;
  await fetchJSON('/api/todos/clear-auto', {method:'POST'});
  refreshTodos();
}

let selectedDate = new Date().toISOString().split('T')[0];
let calYear = new Date().getFullYear(), calMonth = new Date().getMonth() + 1;

async function loadActivity(dateStr) {
  selectedDate = dateStr || new Date().toISOString().split('T')[0];
  const d = await fetchJSON('/api/summary/daily?date=' + selectedDate);
  const container = document.getElementById('activity-breakdown');
  const label = document.getElementById('activity-date-label');
  const dt = new Date(selectedDate + 'T12:00:00');
  label.textContent = dt.toLocaleDateString('en-US', {weekday:'long', month:'long', day:'numeric', year:'numeric'});
  if (!d.categories || d.categories.length === 0) {
    container.innerHTML = '<p style="color:var(--muted);font-size:0.9em">No activity recorded.</p>';
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
        const hasCollapsed = s.collapsed && s.collapsed.length > 0;
        if (hasCollapsed) {
          // Render "Other" as a clickable expandable row
          html += `<div class="activity-sub other-row" style="cursor:pointer" onclick="toggleCollapsed('col-${i}-${si}',this)">
            <span class="activity-sub-name" style="color:var(--accent)">▶ ${esc(s.name)}</span>
            <span class="activity-sub-bar"><span class="activity-sub-bar-fill" style="width:${sp}%;opacity:0.4"></span></span>
            <span class="activity-sub-time">${s.time_str}</span>
          </div>
          <div id="col-${i}-${si}" class="collapsed-detail" style="display:none;padding-left:24px;padding-bottom:6px;border-left:2px solid var(--border);margin-left:4px">`;
          s.collapsed.forEach(cc => {
            html += `<div style="display:flex;justify-content:space-between;font-size:0.8em;color:var(--muted);padding:3px 0;border-bottom:1px solid #f0f0f0">
              <span>${esc(cc.name)}</span><span style="min-width:50px;text-align:right">${cc.time_str}</span></div>`;
          });
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
  const el = document.getElementById('subs-' + i), chev = document.getElementById('chev-' + i);
  if (!el) return;
  el.style.display = el.style.display === 'none' ? '' : 'none';
  if (chev) chev.classList.toggle('open');
}

function toggleCollapsed(id, row) {
  const el = document.getElementById(id);
  if (!el) return;
  const showing = el.style.display === 'none';
  el.style.display = showing ? '' : 'none';
  const nameSpan = row.querySelector('.activity-sub-name');
  if (nameSpan) {
    nameSpan.innerHTML = nameSpan.innerHTML.replace(/^[▶▼]/, showing ? '▼' : '▶');
  }
}

// Calendar
const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
async function renderCalendar() {
  const grid = document.getElementById('cal-grid');
  const title = document.getElementById('cal-title');
  const monthNames = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  title.textContent = monthNames[calMonth-1] + ' ' + calYear;
  const data = await fetchJSON(`/api/summary/month?year=${calYear}&month=${calMonth}`);
  let html = DAYS.map(d => `<div class="cal-header">${d}</div>`).join('');
  const firstDay = new Date(calYear, calMonth-1, 1).getDay();
  const daysInMonth = new Date(calYear, calMonth, 0).getDate();
  const today = new Date().toISOString().split('T')[0];
  for (let i = 0; i < firstDay; i++) html += '<div class="cal-day empty"></div>';
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = `${calYear}-${String(calMonth).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const hasData = data.days && data.days[ds];
    const isToday = ds === today;
    const isSel = ds === selectedDate;
    const mins = hasData ? data.days[ds].minutes : 0;
    const tip = hasData ? `${mins}m tracked` : '';
    html += `<div class="cal-day ${isToday?'today':''} ${isSel?'selected':''} ${hasData?'has-data':''}" onclick="selectDay('${ds}')" title="${tip}">${d}</div>`;
  }
  grid.innerHTML = html;
}
function calPrev() { calMonth--; if(calMonth<1){calMonth=12;calYear--;} renderCalendar(); }
function calNext() { calMonth++; if(calMonth>12){calMonth=1;calYear++;} renderCalendar(); }
function selectDay(ds) { selectedDate = ds; loadActivity(ds); renderCalendar(); }

// Report
async function generateReport() {
  const start = document.getElementById('report-start').value;
  const end = document.getElementById('report-end').value;
  if (!start || !end) { alert('Select both start and end dates'); return; }
  const out = document.getElementById('report-output');
  out.style.display = 'block';
  out.innerHTML = '<p style="color:var(--muted)">Generating...</p>';
  const d = await fetchJSON(`/api/summary/range?start=${start}&end=${end}`);
  let html = `<div style="font-weight:600;margin-bottom:8px">${start} to ${end} — ${d.total_time}, ${d.total_sessions} sessions</div>`;
  d.days.forEach(day => {
    if (day.total_time === '0m') return;
    html += `<div style="margin-bottom:8px"><div style="font-weight:500;font-size:0.85em;color:var(--text)">${day.date} — ${day.total_time}</div>`;
    day.categories.forEach(c => {
      html += `<div style="font-size:0.8em;color:var(--muted);padding-left:12px">${c.category}: ${c.time_str}</div>`;
    });
    html += '</div>';
  });
  out.innerHTML = html;
}
</script>

<script>
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

async function toggleTodo(id) { await fetchJSON(`/api/todos/${id}/toggle`, {method:'POST'}); refreshTodos(); }
async function deleteTodo(id) { await fetchJSON(`/api/todos/${id}`, {method:'DELETE'}); refreshTodos(); }
async function toggleTracking() { await fetchJSON('/api/tracking/toggle', {method:'POST'}); refreshStatus(); }

async function startTask() {
  const cat = document.getElementById('task-cat').value.trim();
  const sub = document.getElementById('task-sub').value.trim();
  if (!cat) { document.getElementById('task-cat').focus(); return; }
  // Start the pomodoro task
  await fetchJSON('/api/task/start', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({category:cat, sub_category:sub || cat})});
  // Also add to task list as manual task
  const taskTitle = sub ? cat + ': ' + sub : cat;
  await fetchJSON('/api/todos', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({title: taskTitle, category: cat})});
  document.getElementById('task-cat').value = '';
  document.getElementById('task-sub').value = '';
  refreshStatus();
}

setInterval(refreshStatus, 2000);
setInterval(refreshActivity, 15000);

// Local 1-second tick for smooth timer countdown
setInterval(function() {
  if (!lastStatus || lastStatus === 'completed' || lastStatus === 'paused') return;
  const elapsed = (Date.now() - lastRemainingAt) / 1000;
  const interpolated = Math.max(0, lastRemaining - elapsed);
  updateTimerDisplay(interpolated, lastTotal, lastStatus);
}, 1000);

refreshStatus(); refreshActivity(); loadConfig(); renderCalendar();
// Set default report dates
document.getElementById('report-start').value = new Date(Date.now()-7*86400000).toISOString().split('T')[0];
document.getElementById('report-end').value = new Date().toISOString().split('T')[0];
</script>
</body>
</html>"""
