"""General settings kept in the records (app_settings), edited in Setup › General settings. Machine settings (the
records folder, the backup folder, the port) stay in settings.json (config.py), as they are needed before records.db
opens.

The values are cached in this module, loaded when the app starts (db.init) and refreshed on every save, so code with
no connection at hand (db.current_cycle) can read them."""
import json

# key -> (default, label, type, hint); the order is the form's
SPEC = {
    "organisation_name": ("", "Organisation name", "text",
                          "Shown at the top of the sidebar, e.g. your group name and department."),
    "cycle_rollover_day": (10, "Payroll month runs until", "day",
                           "Until this day of a month you are still closing the month before (the 10th: October's payroll "
                           "is worked on until 10 November). Change it rarely: joiner and leaver reminders and SQL documents "
                           "dated near the change are placed by the new day, also in months already filed."),
    "payee_default_category": ("utility", "New recurring payment: type", "select", None),
    "payee_default_month_offset": (1, "New recurring payment: paid in", "select", None),
    "payee_default_due_day": (6, "New recurring payment: day of month", "day", None),
    "soon_days": (3, "Due soon means within", "number", "Days. Next up marks a row 'soon' when it falls due within this many days."),
    "ahead_days": (7, "Show payments and checklist items from", "number", "Days before they are due, in Next up."),
    "backup_reminder_days": (7, "Remind me to back up after", "number", "Days without a backup."),
}
DEFAULTS = {k: v[0] for k, v in SPEC.items()}
_values = dict(DEFAULTS)


def get(key):
    return _values[key]


def values():
    return dict(_values)


def present(con):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'app_settings'").fetchone() is not None


def load(con):
    """Reads the settings saved in this records.db (defaults for any not saved)."""
    _values.clear()
    _values.update(DEFAULTS)
    if present(con):
        for k, v in con.execute("SELECT key, value FROM app_settings"):
            if k in SPEC:
                _values[k] = json.loads(v)
    return values()


def fields(categories):
    """The settings form, as FieldSpecs for the page."""
    out = []
    for k, (_, label, kind, hint) in SPEC.items():
        f = {"key": k, "label": label, "type": kind}
        if hint:
            f["hint"] = hint
        if k == "payee_default_category":
            f["options"] = [[c, n] for c, n in categories.items() if c != "receipt"]  # money in is chosen with Money in
        if k == "payee_default_month_offset":
            f["options"] = [[0, "The same month"], [1, "The next month"]]
        if k == "organisation_name":
            f["wide"] = True
        out.append(f)
    return out


def check(changes, categories):
    """The values given, checked: {key: value}. Raises ValueError with a plain sentence."""
    out = {}
    for k, v in changes.items():
        if k not in SPEC:
            raise ValueError(f"There is no setting called {k}.")
        label, kind = SPEC[k][1], SPEC[k][2]
        if kind == "text":
            if not isinstance(v, str) or len(v.strip()) > 120:
                raise ValueError(f"{label}: give some text, at most 120 characters.")
            v = v.strip()
        elif kind == "day":
            if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 28:
                raise ValueError(f"{label}: give a day from 1 to 28, so every month has it.")
        elif kind == "number":
            if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 60:
                raise ValueError(f"{label}: give a number of days from 0 to 60.")
        elif k == "payee_default_category" and (v not in categories or v == "receipt"):
            raise ValueError(f"{label}: choose one of the payment types.")
        elif k == "payee_default_month_offset" and v not in (0, 1):
            raise ValueError(f"{label}: choose the same month or the next month.")
        out[k] = v
    return out


def save(con, changes):
    """Writes the changed settings (the caller checked them and commits) and refreshes the cache."""
    for k, v in changes.items():
        con.execute("INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                    (k, json.dumps(v)))
    _values.update(changes)


def install(con, has_records):
    """Update 19's part: the table, and today's values written out (for a records.db already in use the organisation
    name the sidebar showed until now, so nothing on screen changes)."""
    con.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL CHECK (json_valid(value)))")
    seed = dict(DEFAULTS)
    if has_records:
        seed["organisation_name"] = "Agrinexus · HR & Finance"
    for k, v in seed.items():
        con.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)", (k, json.dumps(v)))
