"""Settings window for FlowTrack.

Tabbed settings UI built with tkinter + ttk for cross-platform support.
Tabs: Email, Categories, Context Rules, Pomodoro.
"""

import logging
import smtplib
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _apply_theme(style: ttk.Style) -> None:
    """Apply a minimalistic flat theme with muted colors and system fonts."""
    style.theme_use("clam")

    bg = "#f5f5f5"
    fg = "#333333"
    accent = "#5a7d9a"
    field_bg = "#ffffff"
    border = "#cccccc"
    button_bg = "#e8e8e8"

    style.configure(".", background=bg, foreground=fg, borderwidth=0,
                    focusthickness=0, font=("TkDefaultFont", 10))
    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=button_bg, foreground=fg,
                    padding=(14, 6), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", bg)],
              foreground=[("selected", accent)])
    style.configure("TFrame", background=bg)
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("TEntry", fieldbackground=field_bg, foreground=fg,
                    bordercolor=border, lightcolor=border, darkcolor=border)
    style.configure("TButton", background=button_bg, foreground=fg,
                    borderwidth=1, relief="flat", padding=(10, 4))
    style.map("TButton",
              background=[("active", accent)],
              foreground=[("active", "#ffffff")])
    style.configure("Accent.TButton", background=accent, foreground="#ffffff")
    style.map("Accent.TButton",
              background=[("active", "#4a6d8a")])
    style.configure("TCheckbutton", background=bg, foreground=fg)
    style.configure("TSpinbox", fieldbackground=field_bg, foreground=fg,
                    bordercolor=border)
    style.configure("Treeview", background=field_bg, foreground=fg,
                    fieldbackground=field_bg, borderwidth=0, rowheight=26)
    style.configure("Treeview.Heading", background=button_bg, foreground=fg,
                    borderwidth=0, font=("TkDefaultFont", 9, "bold"))
    style.map("Treeview", background=[("selected", accent)],
              foreground=[("selected", "#ffffff")])


class SettingsWindow:
    """Tabbed settings window built with tkinter for cross-platform GUI support."""

    def __init__(self, config: dict[str, Any], on_save: Callable[[dict[str, Any]], None]):
        self.config = _deep_copy_dict(config)
        self.on_save = on_save
        self._window: tk.Toplevel | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Display the settings window with tabs."""
        self._window = tk.Toplevel()
        win = self._window
        win.title("FlowTrack Settings")
        win.geometry("620x520")
        win.resizable(False, False)
        win.configure(bg="#f5f5f5")

        style = ttk.Style(win)
        _apply_theme(style)

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=12, pady=(12, 4))

        email_frame = ttk.Frame(notebook)
        categories_frame = ttk.Frame(notebook)
        context_frame = ttk.Frame(notebook)
        pomodoro_frame = ttk.Frame(notebook)

        notebook.add(email_frame, text="  Email  ")
        notebook.add(categories_frame, text="  Categories  ")
        notebook.add(context_frame, text="  Context Rules  ")
        notebook.add(pomodoro_frame, text="  Pomodoro  ")

        self._build_email_tab(email_frame)
        self._build_categories_tab(categories_frame)
        self._build_context_rules_tab(context_frame)
        self._build_pomodoro_tab(pomodoro_frame)

        # Bottom button bar
        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", padx=12, pady=(4, 12))
        ttk.Button(btn_frame, text="Cancel", command=win.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btn_frame, text="Save", style="Accent.TButton",
                   command=self._save).pack(side="right")

    # ------------------------------------------------------------------
    # Email tab
    # ------------------------------------------------------------------

    def _build_email_tab(self, parent: ttk.Frame) -> None:
        """Email configuration: SMTP server, port, TLS, credentials, recipient."""
        email_cfg = self.config.get("report", {}).get("email", {})

        pad = {"padx": 10, "pady": 4}
        row = 0

        ttk.Label(parent, text="SMTP Server:").grid(row=row, column=0, sticky="w", **pad)
        self._smtp_server = ttk.Entry(parent, width=40)
        self._smtp_server.insert(0, email_cfg.get("smtp_server", ""))
        self._smtp_server.grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        ttk.Label(parent, text="Port:").grid(row=row, column=0, sticky="w", **pad)
        self._smtp_port = ttk.Entry(parent, width=10)
        self._smtp_port.insert(0, str(email_cfg.get("smtp_port", 587)))
        self._smtp_port.grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(parent, text="Username:").grid(row=row, column=0, sticky="w", **pad)
        self._smtp_username = ttk.Entry(parent, width=40)
        self._smtp_username.insert(0, email_cfg.get("smtp_username", ""))
        self._smtp_username.grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        ttk.Label(parent, text="Password:").grid(row=row, column=0, sticky="w", **pad)
        self._smtp_password = ttk.Entry(parent, width=40, show="*")
        self._smtp_password.insert(0, email_cfg.get("smtp_password", ""))
        self._smtp_password.grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        self._use_tls = tk.BooleanVar(value=email_cfg.get("use_tls", True))
        ttk.Checkbutton(parent, text="Use TLS", variable=self._use_tls).grid(
            row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(parent, text="Recipient:").grid(row=row, column=0, sticky="w", **pad)
        self._to_address = ttk.Entry(parent, width=40)
        self._to_address.insert(0, email_cfg.get("to_address", ""))
        self._to_address.grid(row=row, column=1, sticky="ew", **pad)
        row += 1

        ttk.Button(parent, text="Test Connection", command=self._test_smtp).grid(
            row=row, column=1, sticky="w", **pad)

        parent.columnconfigure(1, weight=1)

    def _test_smtp(self) -> None:
        """Attempt an SMTP connection with the current field values."""
        server = self._smtp_server.get().strip()
        port_str = self._smtp_port.get().strip()
        username = self._smtp_username.get().strip()
        password = self._smtp_password.get()
        use_tls = self._use_tls.get()

        if not server or not port_str:
            messagebox.showwarning("Missing Info", "Server and port are required.",
                                   parent=self._window)
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("Invalid Port", "Port must be a number.",
                                 parent=self._window)
            return

        try:
            if use_tls:
                conn = smtplib.SMTP(server, port, timeout=10)
                conn.starttls()
            else:
                conn = smtplib.SMTP(server, port, timeout=10)
            if username:
                conn.login(username, password)
            conn.quit()
            messagebox.showinfo("Success", "SMTP connection successful.",
                                parent=self._window)
        except Exception as exc:
            messagebox.showerror("Connection Failed", f"Could not connect:\n{exc}",
                                 parent=self._window)

    # ------------------------------------------------------------------
    # Categories tab
    # ------------------------------------------------------------------

    def _build_categories_tab(self, parent: ttk.Frame) -> None:
        """Work category management: add/edit/remove categories and keyword rules."""
        self._cat_rules: list[dict[str, Any]] = [
            dict(r) for r in self.config.get("classification_rules", [])
        ]

        # Treeview listing categories
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        cols = ("category", "app_patterns", "title_patterns")
        self._cat_tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                      selectmode="browse", height=8)
        self._cat_tree.heading("category", text="Category")
        self._cat_tree.heading("app_patterns", text="App Patterns")
        self._cat_tree.heading("title_patterns", text="Title Patterns")
        self._cat_tree.column("category", width=140)
        self._cat_tree.column("app_patterns", width=200)
        self._cat_tree.column("title_patterns", width=200)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self._cat_tree.yview)
        self._cat_tree.configure(yscrollcommand=scrollbar.set)
        self._cat_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._refresh_cat_tree()

        # Buttons
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x", padx=10, pady=4)
        ttk.Button(btn_frame, text="Add", command=self._add_category).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="Edit", command=self._edit_category).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Remove", command=self._remove_category).pack(side="left", padx=4)

    def _refresh_cat_tree(self) -> None:
        for item in self._cat_tree.get_children():
            self._cat_tree.delete(item)
        for rule in self._cat_rules:
            self._cat_tree.insert("", "end", values=(
                rule.get("category", ""),
                ", ".join(rule.get("app_patterns", [])),
                ", ".join(rule.get("title_patterns", [])),
            ))

    def _add_category(self) -> None:
        self._category_dialog("Add Category", {})

    def _edit_category(self) -> None:
        sel = self._cat_tree.selection()
        if not sel:
            return
        idx = self._cat_tree.index(sel[0])
        self._category_dialog("Edit Category", self._cat_rules[idx], idx)

    def _remove_category(self) -> None:
        sel = self._cat_tree.selection()
        if not sel:
            return
        idx = self._cat_tree.index(sel[0])
        self._cat_rules.pop(idx)
        self._refresh_cat_tree()

    def _category_dialog(self, title: str, rule: dict[str, Any],
                         edit_index: int | None = None) -> None:
        dlg = tk.Toplevel(self._window)
        dlg.title(title)
        dlg.geometry("400x220")
        dlg.resizable(False, False)
        dlg.transient(self._window)
        dlg.grab_set()

        pad = {"padx": 10, "pady": 4}

        ttk.Label(dlg, text="Category:").grid(row=0, column=0, sticky="w", **pad)
        cat_entry = ttk.Entry(dlg, width=35)
        cat_entry.insert(0, rule.get("category", ""))
        cat_entry.grid(row=0, column=1, sticky="ew", **pad)

        ttk.Label(dlg, text="App Patterns:").grid(row=1, column=0, sticky="w", **pad)
        app_entry = ttk.Entry(dlg, width=35)
        app_entry.insert(0, ", ".join(rule.get("app_patterns", [])))
        app_entry.grid(row=1, column=1, sticky="ew", **pad)

        ttk.Label(dlg, text="Title Patterns:").grid(row=2, column=0, sticky="w", **pad)
        title_entry = ttk.Entry(dlg, width=35)
        title_entry.insert(0, ", ".join(rule.get("title_patterns", [])))
        title_entry.grid(row=2, column=1, sticky="ew", **pad)

        ttk.Label(dlg, text="Comma-separated regex patterns",
                  foreground="#888888").grid(row=3, column=1, sticky="w", padx=10)

        def _ok() -> None:
            cat = cat_entry.get().strip()
            if not cat:
                messagebox.showwarning("Missing", "Category name is required.", parent=dlg)
                return
            new_rule = {
                "category": cat,
                "app_patterns": [p.strip() for p in app_entry.get().split(",") if p.strip()],
                "title_patterns": [p.strip() for p in title_entry.get().split(",") if p.strip()],
            }
            if edit_index is not None:
                self._cat_rules[edit_index] = new_rule
            else:
                self._cat_rules.append(new_rule)
            self._refresh_cat_tree()
            dlg.destroy()

        btn_row = ttk.Frame(dlg)
        btn_row.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(btn_row, text="OK", style="Accent.TButton", command=_ok).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="left", padx=4)
        dlg.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------
    # Context Rules tab
    # ------------------------------------------------------------------

    def _build_context_rules_tab(self, parent: ttk.Frame) -> None:
        """Context rule management: add/edit/remove sub-category patterns."""
        self._ctx_rules: list[dict[str, Any]] = [
            dict(r) for r in self.config.get("context_rules", [])
        ]

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        cols = ("category", "title_patterns", "sub_category")
        self._ctx_tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                      selectmode="browse", height=8)
        self._ctx_tree.heading("category", text="Category")
        self._ctx_tree.heading("title_patterns", text="Title Patterns")
        self._ctx_tree.heading("sub_category", text="Sub-Category")
        self._ctx_tree.column("category", width=140)
        self._ctx_tree.column("title_patterns", width=220)
        self._ctx_tree.column("sub_category", width=140)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self._ctx_tree.yview)
        self._ctx_tree.configure(yscrollcommand=scrollbar.set)
        self._ctx_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._refresh_ctx_tree()

        btn_frame = ttk.Frame(parent)
        btn_frame.pack(fill="x", padx=10, pady=4)
        ttk.Button(btn_frame, text="Add", command=self._add_context_rule).pack(side="left", padx=(0, 4))
        ttk.Button(btn_frame, text="Edit", command=self._edit_context_rule).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Remove", command=self._remove_context_rule).pack(side="left", padx=4)

    def _refresh_ctx_tree(self) -> None:
        for item in self._ctx_tree.get_children():
            self._ctx_tree.delete(item)
        for rule in self._ctx_rules:
            self._ctx_tree.insert("", "end", values=(
                rule.get("category", ""),
                ", ".join(rule.get("title_patterns", [])),
                rule.get("sub_category", ""),
            ))

    def _add_context_rule(self) -> None:
        self._context_rule_dialog("Add Context Rule", {})

    def _edit_context_rule(self) -> None:
        sel = self._ctx_tree.selection()
        if not sel:
            return
        idx = self._ctx_tree.index(sel[0])
        self._context_rule_dialog("Edit Context Rule", self._ctx_rules[idx], idx)

    def _remove_context_rule(self) -> None:
        sel = self._ctx_tree.selection()
        if not sel:
            return
        idx = self._ctx_tree.index(sel[0])
        self._ctx_rules.pop(idx)
        self._refresh_ctx_tree()

    def _context_rule_dialog(self, title: str, rule: dict[str, Any],
                             edit_index: int | None = None) -> None:
        dlg = tk.Toplevel(self._window)
        dlg.title(title)
        dlg.geometry("400x220")
        dlg.resizable(False, False)
        dlg.transient(self._window)
        dlg.grab_set()

        pad = {"padx": 10, "pady": 4}

        ttk.Label(dlg, text="Category:").grid(row=0, column=0, sticky="w", **pad)
        cat_entry = ttk.Entry(dlg, width=35)
        cat_entry.insert(0, rule.get("category", ""))
        cat_entry.grid(row=0, column=1, sticky="ew", **pad)

        ttk.Label(dlg, text="Title Patterns:").grid(row=1, column=0, sticky="w", **pad)
        pat_entry = ttk.Entry(dlg, width=35)
        pat_entry.insert(0, ", ".join(rule.get("title_patterns", [])))
        pat_entry.grid(row=1, column=1, sticky="ew", **pad)

        ttk.Label(dlg, text="Sub-Category:").grid(row=2, column=0, sticky="w", **pad)
        sub_entry = ttk.Entry(dlg, width=35)
        sub_entry.insert(0, rule.get("sub_category", ""))
        sub_entry.grid(row=2, column=1, sticky="ew", **pad)

        ttk.Label(dlg, text="Comma-separated regex patterns",
                  foreground="#888888").grid(row=3, column=1, sticky="w", padx=10)

        def _ok() -> None:
            cat = cat_entry.get().strip()
            sub = sub_entry.get().strip()
            if not cat or not sub:
                messagebox.showwarning("Missing", "Category and sub-category are required.",
                                       parent=dlg)
                return
            new_rule = {
                "category": cat,
                "title_patterns": [p.strip() for p in pat_entry.get().split(",") if p.strip()],
                "sub_category": sub,
            }
            if edit_index is not None:
                self._ctx_rules[edit_index] = new_rule
            else:
                self._ctx_rules.append(new_rule)
            self._refresh_ctx_tree()
            dlg.destroy()

        btn_row = ttk.Frame(dlg)
        btn_row.grid(row=4, column=0, columnspan=2, pady=10)
        ttk.Button(btn_row, text="OK", style="Accent.TButton", command=_ok).pack(side="left", padx=4)
        ttk.Button(btn_row, text="Cancel", command=dlg.destroy).pack(side="left", padx=4)
        dlg.columnconfigure(1, weight=1)

    # ------------------------------------------------------------------
    # Pomodoro tab
    # ------------------------------------------------------------------

    def _build_pomodoro_tab(self, parent: ttk.Frame) -> None:
        """Pomodoro settings: durations, debounce, manual task creation."""
        pom_cfg = self.config.get("pomodoro", {})

        pad = {"padx": 10, "pady": 4}
        row = 0

        # --- Duration settings ---
        ttk.Label(parent, text="Durations",
                  font=("TkDefaultFont", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 2))
        row += 1

        ttk.Label(parent, text="Work (min):").grid(row=row, column=0, sticky="w", **pad)
        self._work_min = ttk.Spinbox(parent, from_=1, to=120, width=8)
        self._work_min.set(pom_cfg.get("work_minutes", 25))
        self._work_min.grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(parent, text="Short Break (min):").grid(row=row, column=0, sticky="w", **pad)
        self._short_break = ttk.Spinbox(parent, from_=1, to=60, width=8)
        self._short_break.set(pom_cfg.get("short_break_minutes", 5))
        self._short_break.grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(parent, text="Long Break (min):").grid(row=row, column=0, sticky="w", **pad)
        self._long_break = ttk.Spinbox(parent, from_=1, to=60, width=8)
        self._long_break.set(pom_cfg.get("long_break_minutes", 15))
        self._long_break.grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(parent, text="Long Break After:").grid(row=row, column=0, sticky="w", **pad)
        self._long_interval = ttk.Spinbox(parent, from_=1, to=20, width=8)
        self._long_interval.set(pom_cfg.get("long_break_interval", 4))
        self._long_interval.grid(row=row, column=1, sticky="w", **pad)
        row += 1

        # --- Debounce ---
        ttk.Label(parent, text="Context Switch",
                  font=("TkDefaultFont", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(12, 2))
        row += 1

        ttk.Label(parent, text="Debounce (sec):").grid(row=row, column=0, sticky="w", **pad)
        self._debounce = ttk.Spinbox(parent, from_=1, to=300, width=8)
        self._debounce.set(self.config.get("debounce_threshold_seconds", 30))
        self._debounce.grid(row=row, column=1, sticky="w", **pad)
        row += 1

        # --- Manual task creation ---
        ttk.Label(parent, text="Manual Task",
                  font=("TkDefaultFont", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(12, 2))
        row += 1

        ttk.Label(parent, text="Category:").grid(row=row, column=0, sticky="w", **pad)
        self._manual_category = ttk.Entry(parent, width=30)
        self._manual_category.grid(row=row, column=1, sticky="w", **pad)
        row += 1

        ttk.Label(parent, text="Sub-Category:").grid(row=row, column=0, sticky="w", **pad)
        self._manual_subcategory = ttk.Entry(parent, width=30)
        self._manual_subcategory.grid(row=row, column=1, sticky="w", **pad)
        row += 1

        self._manual_task_callback: Callable[..., Any] | None = None
        ttk.Button(parent, text="Create Pomodoro Task",
                   command=self._create_manual_task).grid(
            row=row, column=1, sticky="w", **pad)

    def _create_manual_task(self) -> None:
        """Signal that the user wants to create a manual Pomodoro task."""
        cat = self._manual_category.get().strip()
        sub = self._manual_subcategory.get().strip()
        if not cat:
            messagebox.showwarning("Missing", "Category is required for a manual task.",
                                   parent=self._window)
            return
        # Store the manual task request in config so the caller can act on it
        self.config.setdefault("_pending_manual_task", {})
        self.config["_pending_manual_task"] = {
            "category": cat,
            "sub_category": sub or cat,
        }
        messagebox.showinfo("Task Queued",
                            f"Pomodoro task '{cat}' will start on save.",
                            parent=self._window)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Validate inputs, build updated config, and call on_save callback."""
        # --- Validate port ---
        try:
            port = int(self._smtp_port.get().strip())
        except ValueError:
            messagebox.showerror("Invalid", "SMTP port must be a number.",
                                 parent=self._window)
            return

        # --- Validate Pomodoro spinbox values ---
        try:
            work_min = int(self._work_min.get())
            short_brk = int(self._short_break.get())
            long_brk = int(self._long_break.get())
            long_int = int(self._long_interval.get())
            debounce = int(self._debounce.get())
        except ValueError:
            messagebox.showerror("Invalid", "Pomodoro values must be integers.",
                                 parent=self._window)
            return

        # --- Build updated config ---
        updated = dict(self.config)

        # Email settings
        report = dict(updated.get("report", {}))
        email = {
            "smtp_server": self._smtp_server.get().strip(),
            "smtp_port": port,
            "smtp_username": self._smtp_username.get().strip(),
            "smtp_password": self._smtp_password.get(),
            "use_tls": self._use_tls.get(),
            "to_address": self._to_address.get().strip(),
        }
        report["email"] = email
        updated["report"] = report

        # Classification rules
        updated["classification_rules"] = list(self._cat_rules)

        # Context rules
        updated["context_rules"] = list(self._ctx_rules)

        # Pomodoro
        updated["pomodoro"] = {
            "work_minutes": work_min,
            "short_break_minutes": short_brk,
            "long_break_minutes": long_brk,
            "long_break_interval": long_int,
        }
        updated["debounce_threshold_seconds"] = debounce

        self.on_save(updated)
        if self._window is not None:
            self._window.destroy()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _deep_copy_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Simple deep copy for JSON-compatible dicts (avoids import copy)."""
    import json
    return json.loads(json.dumps(d))
