"""Web-based dashboard for CarrotSummary.

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

from flask import Flask, jsonify, render_template, request, send_from_directory

from flowtrack.core.models import SessionStatus

logger = logging.getLogger(__name__)

# Will be set by start_dashboard()
_app_ref = None  # type: Optional[Any]  # CarrotSummaryApp


def create_flask_app() -> Flask:
    import os
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    @app.route("/")
    def index():
        return render_template("dashboard.html")

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
        # Active task info
        active_task_id = None
        active_task_display = None
        if _app_ref.tracker:
            active_task_id = _app_ref.tracker.current_active_task_id
        if active_task_id and _app_ref._store:
            todos = _app_ref._store.get_todos(include_done=True)
            task = next((t for t in todos if t["id"] == active_task_id), None)
            if task:
                parent = next((t for t in todos if t["id"] == task.get("parent_id")), None)
                active_task_display = f"{parent['title']}: {task['title']}" if parent else task["title"]
        return jsonify({
            "tracking": _app_ref._tracking,
            "session": session,
            "paused_sessions": paused,
            "active_task_id": active_task_id,
            "active_task_display": active_task_display,
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
        todos = _app_ref._store.get_todos(include_done=True)
        # Build two-tier hierarchy: High_Level_Tasks with nested Low_Level_Tasks
        parents = []
        child_map: dict[int, list[dict]] = {}
        for t in todos:
            pid = t.get("parent_id")
            if pid:
                child_map.setdefault(pid, []).append(t)
            else:
                parents.append(t)
        result = []
        for p in parents:
            p["children"] = child_map.get(p["id"], [])
            result.append(p)
        return jsonify(result)

    @app.route("/api/todos", methods=["POST"])
    def api_add_todo():
        if not _app_ref or not _app_ref._store:
            return jsonify({"error": "not ready"}), 500
        data = request.json or {}
        title = data.get("title", "").strip()
        if not title:
            return jsonify({"error": "title required"}), 400
        cat = data.get("category", "")
        parent_id = data.get("parent_id")
        tid = _app_ref._store.add_todo(title, cat, parent_id=parent_id)
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

    @app.route("/api/pomodoro/stop", methods=["POST"])
    def api_pomodoro_stop():
        """Stop the current pomodoro session and pause tracking."""
        if not _app_ref or not _app_ref._pomodoro_manager:
            return jsonify({"error": "not ready"}), 500
        pm = _app_ref._pomodoro_manager
        if pm.active_session:
            pm.active_session.status = SessionStatus.PAUSED
            pm.paused_sessions[pm.active_session.category] = pm.active_session
            pm.active_session = None
            pm._last_tick = None
        if _app_ref._tracking:
            _app_ref._stop_tracking()
        return jsonify({"ok": True})

    @app.route("/api/pomodoro/start", methods=["POST"])
    def api_pomodoro_start():
        """Resume tracking (pomodoro resumes on next activity detection)."""
        if not _app_ref:
            return jsonify({"error": "not ready"}), 500
        if not _app_ref._tracking:
            _app_ref._start_tracking()
        return jsonify({"ok": True})

    @app.route("/api/pomodoro/skip", methods=["POST"])
    def api_pomodoro_skip():
        """Skip current interval, increment completed count, start fresh work interval."""
        if not _app_ref or not _app_ref._pomodoro_manager:
            return jsonify({"error": "not ready"}), 500
        pm = _app_ref._pomodoro_manager
        if pm.active_session:
            if pm.active_session.status in (SessionStatus.ACTIVE, SessionStatus.BREAK):
                pm.active_session.completed_count += 1
                pm.active_session.status = SessionStatus.ACTIVE
                pm.active_session.elapsed = timedelta(0)
                pm._last_tick = datetime.now()
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # Active Task API (Task 18.2)
    # ------------------------------------------------------------------

    @app.route("/api/active-task", methods=["GET"])
    def api_get_active_task():
        if not _app_ref:
            return jsonify({"active_task_id": None})
        tid = None
        if _app_ref.tracker:
            tid = _app_ref.tracker.current_active_task_id
        # Look up task info
        task_info = None
        if tid and _app_ref._store:
            todos = _app_ref._store.get_todos(include_done=True)
            task = next((t for t in todos if t["id"] == tid), None)
            if task:
                parent = next((t for t in todos if t["id"] == task.get("parent_id")), None)
                task_info = {
                    "id": tid,
                    "title": task["title"],
                    "parent_title": parent["title"] if parent else None,
                    "display": f"{parent['title']}: {task['title']}" if parent else task["title"],
                }
        return jsonify({"active_task_id": tid, "task": task_info})

    @app.route("/api/active-task", methods=["POST"])
    def api_set_active_task():
        if not _app_ref:
            return jsonify({"error": "not ready"}), 500
        data = request.json or {}
        task_id = data.get("task_id")
        if task_id is not None:
            task_id = int(task_id)
        _app_ref.set_active_task(task_id)
        return jsonify({"ok": True, "active_task_id": task_id})

    @app.route("/api/active-task", methods=["DELETE"])
    def api_clear_active_task():
        if not _app_ref:
            return jsonify({"error": "not ready"}), 500
        _app_ref.clear_active_task()
        return jsonify({"ok": True})

    # ------------------------------------------------------------------
    # Activity-by-task API (Task 19.1)
    # ------------------------------------------------------------------

    @app.route("/api/activity/by-task")
    def api_activity_by_task():
        """Return auto-tracked activities organized by task hierarchy for a given date."""
        if not _app_ref or not _app_ref._store:
            return jsonify({"error": "not ready"})
        from flowtrack.reporting.formatter import TextFormatter
        date_str = request.args.get("date")
        target = date.fromisoformat(date_str) if date_str else date.today()
        start_dt = datetime(target.year, target.month, target.day)
        end_dt = start_dt + timedelta(days=1)
        poll = _app_ref.config.get("poll_interval_seconds", 5)

        # Get all todos and all activities for the day
        todos = _app_ref._store.get_todos(include_done=True)
        all_activities = _app_ref._store.get_activities(start_dt, end_dt)

        # Build parent (high-level) and child (low-level) maps
        parents = [t for t in todos if not t.get("parent_id")]
        child_map = {}
        for t in todos:
            pid = t.get("parent_id")
            if pid:
                child_map.setdefault(pid, []).append(t)

        # Group activities by active_task_id
        task_activities = {}
        unassigned = []
        for act in all_activities:
            tid = act.active_task_id
            if tid:
                task_activities.setdefault(tid, []).append(act)
            else:
                unassigned.append(act)

        # Build response: high-level tasks with nested low-level tasks and their activities
        result = []
        for parent in parents:
            children = child_map.get(parent["id"], [])
            child_results = []
            parent_total_sec = 0
            for child in children:
                acts = task_activities.get(child["id"], [])
                child_total_sec = len(acts) * poll
                parent_total_sec += child_total_sec
                # Aggregate activities by app+summary
                agg = _aggregate_activities(acts, poll)
                child_results.append({
                    "id": child["id"],
                    "title": child["title"],
                    "done": bool(child.get("done")),
                    "total_time": TextFormatter.format_duration(timedelta(seconds=child_total_sec)),
                    "total_seconds": child_total_sec,
                    "entries": agg,
                })
            result.append({
                "id": parent["id"],
                "title": parent["title"],
                "total_time": TextFormatter.format_duration(timedelta(seconds=parent_total_sec)),
                "total_seconds": parent_total_sec,
                "children": child_results,
            })

        # Unassigned activities
        unassigned_total = len(unassigned) * poll
        unassigned_agg = _aggregate_activities(unassigned, poll)

        return jsonify({
            "date": str(target),
            "tasks": result,
            "unassigned": {
                "total_time": TextFormatter.format_duration(timedelta(seconds=unassigned_total)),
                "total_seconds": unassigned_total,
                "entries": unassigned_agg,
            },
        })

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



def _aggregate_activities(activities, poll_interval):
    """Aggregate a list of ActivityRecord objects by app_name + activity_summary.

    Uses normalized keys so that entries differing only in case or
    trailing whitespace are combined into a single row.
    """
    import re as _re
    from flowtrack.reporting.formatter import TextFormatter

    def _normalize(text: str) -> str:
        """Lowercase, collapse whitespace, strip trailing punctuation."""
        t = text.lower().strip()
        t = _re.sub(r"\s+", " ", t)
        t = t.rstrip(" .,;:-–—")
        return t

    agg = {}
    for act in activities:
        raw_summary = act.activity_summary or act.sub_category
        norm_key = (_normalize(act.app_name), _normalize(raw_summary))
        if norm_key not in agg:
            agg[norm_key] = {"app_name": act.app_name, "summary": raw_summary,
                             "category": act.category, "count": 0,
                             "first_ts": act.timestamp, "last_ts": act.timestamp}
        agg[norm_key]["count"] += 1
        if act.timestamp < agg[norm_key]["first_ts"]:
            agg[norm_key]["first_ts"] = act.timestamp
        if act.timestamp > agg[norm_key]["last_ts"]:
            agg[norm_key]["last_ts"] = act.timestamp
    result = []
    for _key, data in sorted(agg.items(), key=lambda x: x[1]["count"], reverse=True):
        sec = data["count"] * poll_interval
        result.append({
            "app_name": data["app_name"],
            "summary": data["summary"],
            "category": data["category"],
            "time_str": TextFormatter.format_duration(timedelta(seconds=sec)),
            "time_seconds": sec,
            "timestamp_start": data["first_ts"].isoformat() if isinstance(data["first_ts"], datetime) else str(data["first_ts"]),
            "timestamp_end": data["last_ts"].isoformat() if isinstance(data["last_ts"], datetime) else str(data["last_ts"]),
        })
    return result


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


