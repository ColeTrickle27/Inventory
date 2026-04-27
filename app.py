import csv
import os
import sqlite3
from datetime import datetime, timedelta
from io import StringIO

from flask import Flask, Response, flash, redirect, render_template_string, request, url_for

DB_PATH = os.environ.get("INVENTORY_DB", "inventory.db")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "bugman-dev-key")

BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Holloman Inventory</title>
  <style>
    :root { --dark:#1f2933; --light:#f6f8fa; --border:#d0d7de; --accent:#116329; --danger:#b42318; --warn:#b54708; }
    * { box-sizing:border-box; }
    body { font-family: Arial, sans-serif; margin:0; background:var(--light); color:#111827; }
    .layout { display:flex; min-height:100vh; }
    .sidebar { width:235px; background:var(--dark); color:white; padding:20px 15px; flex-shrink:0; }
    .sidebar h2 { font-size:20px; margin:0 0 18px; }
    .sidebar a { color:white; display:block; padding:10px 12px; margin:5px 0; text-decoration:none; border-radius:8px; }
    .sidebar a:hover { background:#374151; }
    .content { padding:24px; width:100%; overflow-x:auto; }
    .card { background:white; padding:18px; border:1px solid var(--border); border-radius:10px; margin-bottom:18px; box-shadow:0 1px 2px rgba(0,0,0,.04); }
    .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:14px; }
    .metric { font-size:32px; font-weight:bold; margin-top:6px; }
    table { border-collapse:collapse; width:100%; background:white; }
    th, td { border-bottom:1px solid var(--border); padding:10px; text-align:left; vertical-align:top; }
    th { background:#f3f4f6; }
    form { display:grid; gap:12px; max-width:760px; }
    label { font-weight:bold; }
    input, select, textarea { width:100%; padding:10px; border:1px solid var(--border); border-radius:8px; font-size:16px; }
    textarea { min-height:90px; }
    button, .button { display:inline-block; background:var(--accent); color:white; padding:10px 14px; border:0; border-radius:8px; text-decoration:none; font-size:16px; cursor:pointer; }
    .button.secondary { background:#374151; }
    .actions { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:12px; }
    .status { display:inline-block; padding:4px 8px; border-radius:999px; font-weight:bold; font-size:13px; }
    .OK { background:#dcfce7; color:#166534; }
    .LowStock { background:#fef3c7; color:#92400e; }
    .ReorderNeeded { background:#fee2e2; color:#991b1b; }
    .Overstocked { background:#e0f2fe; color:#075985; }
    .flash { background:#fff7ed; border:1px solid #fed7aa; padding:10px; border-radius:8px; margin-bottom:12px; }
    @media (max-width:800px) {
      .layout { display:block; }
      .sidebar { width:100%; height:auto; }
      .content { padding:14px; }
      th,td { font-size:14px; }
    }
  </style>
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <h2>Holloman Inventory</h2>
    <a href="{{ url_for('dashboard') }}">Dashboard</a>
    <a href="{{ url_for('inventory') }}">Inventory</a>
    <a href="{{ url_for('receive') }}">Received Orders</a>
    <a href="{{ url_for('usage') }}">Employee Usage</a>
    <a href="{{ url_for('employees') }}">Employees</a>
    <a href="{{ url_for('recommend') }}">Order Recommendations</a>
    <a href="{{ url_for('report') }}">Usage Report</a>
  </aside>
  <main class="content">
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        {% for message in messages %}<div class="flash">{{ message }}</div>{% endfor %}
      {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
  </main>
</div>
</body>
</html>
"""


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            role TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL UNIQUE,
            container_size TEXT NOT NULL DEFAULT '',
            starting_count REAL NOT NULL DEFAULT 0,
            min_level REAL NOT NULL DEFAULT 0,
            max_level REAL NOT NULL DEFAULT 0,
            vendor_id INTEGER,
            notes TEXT DEFAULT '',
            FOREIGN KEY(vendor_id) REFERENCES vendors(id)
        );

        CREATE TABLE IF NOT EXISTS received_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_received TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            quantity_ordered REAL NOT NULL,
            quantity_received REAL NOT NULL,
            vendor_id INTEGER,
            packing_slip_verified TEXT NOT NULL DEFAULT 'No',
            accepted_by INTEGER NOT NULL,
            notes TEXT DEFAULT '',
            FOREIGN KEY(item_id) REFERENCES inventory_items(id),
            FOREIGN KEY(vendor_id) REFERENCES vendors(id),
            FOREIGN KEY(accepted_by) REFERENCES employees(id)
        );

        CREATE TABLE IF NOT EXISTS usage_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            employee_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            quantity_used REAL NOT NULL,
            job_account_work_order TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            FOREIGN KEY(employee_id) REFERENCES employees(id),
            FOREIGN KEY(item_id) REFERENCES inventory_items(id)
        );
        """
    )
    db.commit()


def seed_data():
    db = get_db()
    existing = db.execute("SELECT COUNT(*) AS count FROM inventory_items").fetchone()["count"]
    if existing:
        return

    vendors = [("Univar Solutions", "Chemical supplier"), ("Target Specialty Products", "Pest supplies"), ("Veseris", "Pest control distributor"), ("Grainger", "General supplies")]
    db.executemany("INSERT INTO vendors(name, notes) VALUES (?, ?)", vendors)
    vendor_lookup = {row["name"]: row["id"] for row in db.execute("SELECT id, name FROM vendors")}

    employees = [
        ("Cole Matthews", 1, "Manager", ""),
        ("Office Staff", 1, "Office", ""),
        ("Technician 1", 1, "Technician", ""),
        ("Technician 2", 1, "Technician", ""),
        ("Inactive Example", 0, "Former Employee", "Hidden from new entry dropdowns"),
    ]
    db.executemany("INSERT INTO employees(name, active, role, notes) VALUES (?, ?, ?, ?)", employees)

    items = [
        ("Termidor SC", "20 oz bottle", 8, 4, 16, vendor_lookup["Univar Solutions"], "Termiticide - follow label every time"),
        ("Taurus SC", "20 oz bottle", 6, 3, 12, vendor_lookup["Veseris"], "Termiticide - follow label every time"),
        ("Bait Stations", "case", 18, 8, 30, vendor_lookup["Target Specialty Products"], "Termite/rodent station inventory"),
        ("Glue Boards", "case", 42, 20, 80, vendor_lookup["Target Specialty Products"], ""),
        ("Rodent Bait", "bucket", 7, 3, 12, vendor_lookup["Veseris"], "Restricted handling as applicable"),
        ("Granular Insecticide", "25 lb bag", 10, 4, 18, vendor_lookup["Univar Solutions"], ""),
        ("Aerosol", "case", 12, 5, 24, vendor_lookup["Target Specialty Products"], ""),
        ("Nitrile Gloves", "box", 30, 12, 60, vendor_lookup["Grainger"], ""),
    ]
    db.executemany("""
        INSERT INTO inventory_items(item, container_size, starting_count, min_level, max_level, vendor_id, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, items)
    db.commit()


def positive_number(value, field_name):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a number.")
    if number < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return number


def required(value, field_name):
    if value is None or str(value).strip() == "":
        raise ValueError(f"{field_name} is required.")
    return str(value).strip()


def item_summary(item_id=None):
    db = get_db()
    params = []
    where = ""
    if item_id is not None:
        where = "WHERE i.id = ?"
        params.append(item_id)

    rows = db.execute(
        f"""
        SELECT
            i.id,
            i.item,
            i.container_size,
            i.starting_count,
            i.min_level,
            i.max_level,
            i.notes,
            COALESCE(v.name, '') AS vendor,
            COALESCE((SELECT SUM(quantity_received) FROM received_orders r WHERE r.item_id = i.id), 0) AS total_received,
            COALESCE((SELECT SUM(quantity_used) FROM usage_entries u WHERE u.item_id = i.id), 0) AS total_used,
            COALESCE((SELECT SUM(quantity_used) FROM usage_entries u WHERE u.item_id = i.id AND date(u.date) >= date('now','-7 days')), 0) AS weekly_total_out
        FROM inventory_items i
        LEFT JOIN vendors v ON v.id = i.vendor_id
        {where}
        ORDER BY i.item
        """,
        params,
    ).fetchall()

    summaries = []
    for row in rows:
        current_stock = row["starting_count"] + row["total_received"] - row["total_used"]
        suggested_order_quantity = row["max_level"] - current_stock if current_stock < row["min_level"] else 0
        if current_stock > row["max_level"]:
            status = "Overstocked"
            status_label = "Overstocked"
        elif current_stock <= 0 or current_stock < row["min_level"] * 0.5:
            status = "ReorderNeeded"
            status_label = "Reorder Needed"
        elif current_stock < row["min_level"]:
            status = "LowStock"
            status_label = "Low Stock"
        else:
            status = "OK"
            status_label = "OK"
        summaries.append(dict(row) | {
            "current_stock": current_stock,
            "suggested_order_quantity": max(suggested_order_quantity, 0),
            "status": status,
            "status_label": status_label,
        })
    return summaries[0] if item_id is not None and summaries else None if item_id is not None else summaries


def csv_response(filename, headers, rows):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def active_employees():
    return get_db().execute("SELECT id, name FROM employees WHERE active = 1 ORDER BY name").fetchall()


def inventory_options():
    return get_db().execute("SELECT id, item FROM inventory_items ORDER BY item").fetchall()


def vendor_options():
    return get_db().execute("SELECT id, name FROM vendors ORDER BY name").fetchall()


@app.route("/")
def dashboard():
    db = get_db()
    summaries = item_summary()
    total_items = len(summaries)
    reorder_count = sum(1 for item in summaries if item["status"] == "ReorderNeeded")
    low_count = sum(1 for item in summaries if item["status"] == "LowStock")
    recent_received = db.execute(
        """
        SELECT r.date_received, i.item, r.quantity_received, COALESCE(v.name, '') AS vendor
        FROM received_orders r
        JOIN inventory_items i ON i.id = r.item_id
        LEFT JOIN vendors v ON v.id = r.vendor_id
        ORDER BY r.date_received DESC, r.id DESC LIMIT 5
        """
    ).fetchall()
    recent_usage = db.execute(
        """
        SELECT u.date, e.name AS employee, i.item, u.quantity_used
        FROM usage_entries u
        JOIN employees e ON e.id = u.employee_id
        JOIN inventory_items i ON i.id = u.item_id
        ORDER BY u.date DESC, u.id DESC LIMIT 5
        """
    ).fetchall()
    top_week = db.execute(
        """
        SELECT i.item, SUM(u.quantity_used) AS total_used
        FROM usage_entries u
        JOIN inventory_items i ON i.id = u.item_id
        WHERE date(u.date) >= date('now','-7 days')
        GROUP BY i.item
        ORDER BY total_used DESC LIMIT 5
        """
    ).fetchall()
    return render_template_string(BASE_HTML + """
    {% block content %}
    <h1>Dashboard</h1>
    <div class="cards">
      <div class="card"><div>Total Inventory Items</div><div class="metric">{{ total_items }}</div></div>
      <div class="card"><div>Items Needing Reorder</div><div class="metric">{{ reorder_count }}</div></div>
      <div class="card"><div>Low Stock Items</div><div class="metric">{{ low_count }}</div></div>
    </div>
    <div class="card"><h2>Recently Received</h2><table><tr><th>Date</th><th>Item</th><th>Qty</th><th>Vendor</th></tr>{% for r in recent_received %}<tr><td>{{ r.date_received }}</td><td>{{ r.item }}</td><td>{{ r.quantity_received }}</td><td>{{ r.vendor }}</td></tr>{% else %}<tr><td colspan="4">No received orders yet.</td></tr>{% endfor %}</table></div>
    <div class="card"><h2>Recent Usage</h2><table><tr><th>Date</th><th>Employee</th><th>Item</th><th>Qty</th></tr>{% for u in recent_usage %}<tr><td>{{ u.date }}</td><td>{{ u.employee }}</td><td>{{ u.item }}</td><td>{{ u.quantity_used }}</td></tr>{% else %}<tr><td colspan="4">No usage entries yet.</td></tr>{% endfor %}</table></div>
    <div class="card"><h2>Top Used This Week</h2><table><tr><th>Item</th><th>Total Used</th></tr>{% for t in top_week %}<tr><td>{{ t.item }}</td><td>{{ t.total_used }}</td></tr>{% else %}<tr><td colspan="2">No usage this week.</td></tr>{% endfor %}</table></div>
    {% endblock %}
    """, total_items=total_items, reorder_count=reorder_count, low_count=low_count, recent_received=recent_received, recent_usage=recent_usage, top_week=top_week)


@app.route("/inventory", methods=["GET", "POST"])
def inventory():
    db = get_db()
    if request.method == "POST":
        try:
            item = required(request.form.get("item"), "Item")
            container_size = required(request.form.get("container_size"), "Container Size")
            starting_count = positive_number(request.form.get("starting_count"), "Starting Count")
            min_level = positive_number(request.form.get("min_level"), "Min Level")
            max_level = positive_number(request.form.get("max_level"), "Max Level")
            if max_level < min_level:
                raise ValueError("Max Level must be greater than or equal to Min Level.")
            vendor_id = request.form.get("vendor_id") or None
            notes = request.form.get("notes", "")
            db.execute(
                """
                INSERT INTO inventory_items(item, container_size, starting_count, min_level, max_level, vendor_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (item, container_size, starting_count, min_level, max_level, vendor_id, notes),
            )
            db.commit()
            flash("Inventory item added.")
            return redirect(url_for("inventory"))
        except (sqlite3.IntegrityError, ValueError) as exc:
            flash(f"Could not save item: {exc}")

    return render_template_string(BASE_HTML + """
    {% block content %}
    <h1>Inventory</h1>
    <div class="actions"><a class="button secondary" href="{{ url_for('export_inventory') }}">Export Inventory CSV</a></div>
    <div class="card">
      <h2>Add Inventory Item</h2>
      <form method="post">
        <label>Item<input name="item" required></label>
        <label>Container Size<input name="container_size" required placeholder="20 oz bottle, case, bucket"></label>
        <label>Starting Count<input type="number" step="0.01" min="0" name="starting_count" required></label>
        <label>Min Level<input type="number" step="0.01" min="0" name="min_level" required></label>
        <label>Max Level<input type="number" step="0.01" min="0" name="max_level" required></label>
        <label>Vendor<select name="vendor_id"><option value="">No vendor selected</option>{% for v in vendors %}<option value="{{ v.id }}">{{ v.name }}</option>{% endfor %}</select></label>
        <label>Notes<textarea name="notes"></textarea></label>
        <button type="submit">Add Item</button>
      </form>
    </div>
    <div class="card">
      <h2>Current Inventory</h2>
      <table>
        <tr><th>Item</th><th>Container Size</th><th>Starting Count</th><th>Total Received</th><th>Total Used</th><th>Current Stock</th><th>Weekly Total Out</th><th>Min</th><th>Max</th><th>Suggested Order</th><th>Vendor</th><th>Status</th></tr>
        {% for i in items %}
        <tr>
          <td>{{ i.item }}</td><td>{{ i.container_size }}</td><td>{{ i.starting_count }}</td><td>{{ i.total_received }}</td><td>{{ i.total_used }}</td><td>{{ i.current_stock }}</td><td>{{ i.weekly_total_out }}</td><td>{{ i.min_level }}</td><td>{{ i.max_level }}</td><td>{{ i.suggested_order_quantity }}</td><td>{{ i.vendor }}</td><td><span class="status {{ i.status }}">{{ i.status_label }}</span></td>
        </tr>
        {% endfor %}
      </table>
    </div>
    {% endblock %}
    """, items=item_summary(), vendors=vendor_options())


@app.route("/receive", methods=["GET", "POST"])
def receive():
    db = get_db()
    if request.method == "POST":
        try:
            date_received = required(request.form.get("date_received"), "Date Received")
            item_id = int(required(request.form.get("item_id"), "Item"))
            quantity_ordered = positive_number(request.form.get("quantity_ordered"), "Quantity Ordered")
            quantity_received = positive_number(request.form.get("quantity_received"), "Quantity Received")
            vendor_id = request.form.get("vendor_id") or None
            packing_slip_verified = request.form.get("packing_slip_verified", "No")
            accepted_by = int(required(request.form.get("accepted_by"), "Accepted By"))
            employee = db.execute("SELECT active FROM employees WHERE id = ?", (accepted_by,)).fetchone()
            if not employee or employee["active"] != 1:
                raise ValueError("Accepted By must be an active employee.")
            db.execute(
                """
                INSERT INTO received_orders(date_received, item_id, quantity_ordered, quantity_received, vendor_id, packing_slip_verified, accepted_by, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (date_received, item_id, quantity_ordered, quantity_received, vendor_id, packing_slip_verified, accepted_by, request.form.get("notes", "")),
            )
            db.commit()
            flash("Received order saved. Stock has been updated.")
            return redirect(url_for("inventory"))
        except ValueError as exc:
            flash(str(exc))
    return render_template_string(BASE_HTML + """
    {% block content %}
    <h1>Received Orders</h1>
    <div class="actions"><a class="button secondary" href="{{ url_for('export_received') }}">Export Received Orders CSV</a></div>
    <div class="card">
      <form method="post">
        <label>Date Received<input type="date" name="date_received" required></label>
        <label>Item<select name="item_id" required>{% for i in items %}<option value="{{ i.id }}">{{ i.item }}</option>{% endfor %}</select></label>
        <label>Quantity Ordered<input type="number" step="0.01" min="0" name="quantity_ordered" required></label>
        <label>Quantity Received<input type="number" step="0.01" min="0" name="quantity_received" required></label>
        <label>Vendor<select name="vendor_id"><option value="">No vendor selected</option>{% for v in vendors %}<option value="{{ v.id }}">{{ v.name }}</option>{% endfor %}</select></label>
        <label>Packing Slip Verified<select name="packing_slip_verified"><option>Yes</option><option>No</option></select></label>
        <label>Accepted By<select name="accepted_by" required>{% for e in employees %}<option value="{{ e.id }}">{{ e.name }}</option>{% endfor %}</select></label>
        <label>Notes<textarea name="notes"></textarea></label>
        <button type="submit">Save Received Order</button>
      </form>
    </div>
    {% endblock %}
    """, items=inventory_options(), vendors=vendor_options(), employees=active_employees())


@app.route("/usage", methods=["GET", "POST"])
def usage():
    db = get_db()
    if request.method == "POST":
        try:
            date = required(request.form.get("date"), "Date")
            employee_id = int(required(request.form.get("employee_id"), "Employee"))
            item_id = int(required(request.form.get("item_id"), "Item"))
            quantity_used = positive_number(request.form.get("quantity_used"), "Quantity Used")
            if quantity_used <= 0:
                raise ValueError("Quantity Used must be greater than zero.")
            employee = db.execute("SELECT active FROM employees WHERE id = ?", (employee_id,)).fetchone()
            if not employee or employee["active"] != 1:
                raise ValueError("Employee must be active for new usage entries.")
            summary = item_summary(item_id)
            if summary is None:
                raise ValueError("Item does not exist.")
            if summary["current_stock"] < quantity_used:
                raise ValueError(f"Not enough stock. Current stock is {summary['current_stock']}.")
            db.execute(
                """
                INSERT INTO usage_entries(date, employee_id, item_id, quantity_used, job_account_work_order, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (date, employee_id, item_id, quantity_used, request.form.get("job_account_work_order", ""), request.form.get("notes", "")),
            )
            db.commit()
            flash("Usage saved. Stock has been updated.")
            return redirect(url_for("inventory"))
        except ValueError as exc:
            flash(str(exc))
    return render_template_string(BASE_HTML + """
    {% block content %}
    <h1>Employee Usage</h1>
    <div class="actions"><a class="button secondary" href="{{ url_for('export_usage') }}">Export Employee Usage CSV</a></div>
    <div class="card">
      <form method="post">
        <label>Date<input type="date" name="date" required></label>
        <label>Employee<select name="employee_id" required>{% for e in employees %}<option value="{{ e.id }}">{{ e.name }}</option>{% endfor %}</select></label>
        <label>Item<select name="item_id" required>{% for i in items %}<option value="{{ i.id }}">{{ i.item }}</option>{% endfor %}</select></label>
        <label>Quantity Used<input type="number" step="0.01" min="0.01" name="quantity_used" required></label>
        <label>Job / Account / Work Order<input name="job_account_work_order"></label>
        <label>Notes<textarea name="notes"></textarea></label>
        <button type="submit">Save Usage</button>
      </form>
    </div>
    {% endblock %}
    """, employees=active_employees(), items=inventory_options())


@app.route("/employees", methods=["GET", "POST"])
def employees():
    db = get_db()
    if request.method == "POST":
        try:
            name = required(request.form.get("name"), "Employee Name")
            role = request.form.get("role", "")
            active = 1 if request.form.get("active") == "on" else 0
            notes = request.form.get("notes", "")
            db.execute("INSERT INTO employees(name, active, role, notes) VALUES (?, ?, ?, ?)", (name, active, role, notes))
            db.commit()
            flash("Employee added.")
            return redirect(url_for("employees"))
        except ValueError as exc:
            flash(str(exc))
    emps = db.execute("SELECT * FROM employees ORDER BY active DESC, name").fetchall()
    return render_template_string(BASE_HTML + """
    {% block content %}
    <h1>Employees</h1>
    <div class="card"><h2>Add Employee</h2><form method="post"><label>Employee Name<input name="name" required></label><label>Role<input name="role"></label><label><input type="checkbox" name="active" checked> Active</label><label>Notes<textarea name="notes"></textarea></label><button>Add Employee</button></form></div>
    <div class="card"><h2>Employee List</h2><table><tr><th>Name</th><th>Active/Inactive</th><th>Role</th><th>Notes</th></tr>{% for e in emps %}<tr><td>{{ e.name }}</td><td>{{ 'Active' if e.active else 'Inactive' }}</td><td>{{ e.role }}</td><td>{{ e.notes }}</td></tr>{% endfor %}</table></div>
    {% endblock %}
    """, emps=emps)


@app.route("/recommend")
def recommend():
    recommendations = [i for i in item_summary() if i["current_stock"] < i["min_level"]]
    return render_template_string(BASE_HTML + """
    {% block content %}
    <h1>Order Recommendations</h1>
    <div class="actions"><a class="button secondary" href="{{ url_for('export_recommendations') }}">Export Recommendations CSV</a></div>
    <div class="card"><table><tr><th>Item</th><th>Current Stock</th><th>Min Level</th><th>Max Level</th><th>Suggested Order Quantity</th><th>Vendor</th><th>Status</th></tr>{% for i in recommendations %}<tr><td>{{ i.item }}</td><td>{{ i.current_stock }}</td><td>{{ i.min_level }}</td><td>{{ i.max_level }}</td><td>{{ i.suggested_order_quantity }}</td><td>{{ i.vendor }}</td><td><span class="status {{ i.status }}">{{ i.status_label }}</span></td></tr>{% else %}<tr><td colspan="7">Nothing needs ordering right now.</td></tr>{% endfor %}</table></div>
    {% endblock %}
    """, recommendations=recommendations)


@app.route("/report")
def report():
    db = get_db()
    start = request.args.get("start")
    end = request.args.get("end")
    employee_id = request.args.get("employee_id")
    item_id = request.args.get("item_id")
    vendor_id = request.args.get("vendor_id")
    conditions = []
    params = []
    if start:
        conditions.append("date(u.date) >= date(?)")
        params.append(start)
    if end:
        conditions.append("date(u.date) <= date(?)")
        params.append(end)
    if employee_id:
        conditions.append("u.employee_id = ?")
        params.append(employee_id)
    if item_id:
        conditions.append("u.item_id = ?")
        params.append(item_id)
    if vendor_id:
        conditions.append("i.vendor_id = ?")
        params.append(vendor_id)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    by_item = db.execute(f"SELECT i.item, SUM(u.quantity_used) AS total FROM usage_entries u JOIN inventory_items i ON i.id=u.item_id {where} GROUP BY i.item ORDER BY total DESC", params).fetchall()
    by_employee = db.execute(f"SELECT e.name, SUM(u.quantity_used) AS total FROM usage_entries u JOIN employees e ON e.id=u.employee_id JOIN inventory_items i ON i.id=u.item_id {where} GROUP BY e.name ORDER BY total DESC", params).fetchall()
    weekly = db.execute(f"SELECT strftime('%Y-%W', u.date) AS week, SUM(u.quantity_used) AS total FROM usage_entries u JOIN inventory_items i ON i.id=u.item_id {where} GROUP BY week ORDER BY week DESC", params).fetchall()
    low_stock = [i for i in item_summary() if i["current_stock"] < i["min_level"]]
    return render_template_string(BASE_HTML + """
    {% block content %}
    <h1>Comprehensive Usage Report</h1>
    <div class="actions"><a class="button secondary" href="{{ url_for('export_report', start=start, end=end, employee_id=employee_id, item_id=item_id, vendor_id=vendor_id) }}">Export Report CSV</a></div>
    <div class="card"><form method="get"><label>Start Date<input type="date" name="start" value="{{ start or '' }}"></label><label>End Date<input type="date" name="end" value="{{ end or '' }}"></label><label>Employee<select name="employee_id"><option value="">All employees</option>{% for e in employees %}<option value="{{ e.id }}" {% if employee_id == e.id|string %}selected{% endif %}>{{ e.name }}</option>{% endfor %}</select></label><label>Item<select name="item_id"><option value="">All items</option>{% for i in items %}<option value="{{ i.id }}" {% if item_id == i.id|string %}selected{% endif %}>{{ i.item }}</option>{% endfor %}</select></label><label>Vendor<select name="vendor_id"><option value="">All vendors</option>{% for v in vendors %}<option value="{{ v.id }}" {% if vendor_id == v.id|string %}selected{% endif %}>{{ v.name }}</option>{% endfor %}</select></label><button>Run Report</button></form></div>
    <div class="card"><h2>Total Quantity Used by Item</h2><table><tr><th>Item</th><th>Total Used</th></tr>{% for r in by_item %}<tr><td>{{ r.item }}</td><td>{{ r.total }}</td></tr>{% else %}<tr><td colspan="2">No usage found.</td></tr>{% endfor %}</table></div>
    <div class="card"><h2>Total Quantity Used by Employee</h2><table><tr><th>Employee</th><th>Total Used</th></tr>{% for r in by_employee %}<tr><td>{{ r.name }}</td><td>{{ r.total }}</td></tr>{% else %}<tr><td colspan="2">No usage found.</td></tr>{% endfor %}</table></div>
    <div class="card"><h2>Weekly Usage Totals</h2><table><tr><th>Week</th><th>Total Used</th></tr>{% for r in weekly %}<tr><td>{{ r.week }}</td><td>{{ r.total }}</td></tr>{% else %}<tr><td colspan="2">No weekly usage found.</td></tr>{% endfor %}</table></div>
    <div class="card"><h2>Low-Stock Items</h2><table><tr><th>Item</th><th>Current Stock</th><th>Min Level</th><th>Status</th></tr>{% for i in low_stock %}<tr><td>{{ i.item }}</td><td>{{ i.current_stock }}</td><td>{{ i.min_level }}</td><td>{{ i.status_label }}</td></tr>{% else %}<tr><td colspan="4">No low-stock items.</td></tr>{% endfor %}</table></div>
    {% endblock %}
    """, by_item=by_item, by_employee=by_employee, weekly=weekly, low_stock=low_stock, employees=active_employees(), items=inventory_options(), vendors=vendor_options(), start=start, end=end, employee_id=employee_id, item_id=item_id, vendor_id=vendor_id)


@app.route("/export/inventory")
def export_inventory():
    rows = [[i["item"], i["container_size"], i["starting_count"], i["total_received"], i["total_used"], i["current_stock"], i["weekly_total_out"], i["min_level"], i["max_level"], i["suggested_order_quantity"], i["vendor"], i["status_label"]] for i in item_summary()]
    return csv_response("inventory.csv", ["Item", "Container Size", "Starting Count", "Total Received", "Total Used", "Current Stock", "Weekly Total Out", "Min Level", "Max Level", "Suggested Order Quantity", "Vendor", "Status"], rows)


@app.route("/export/recommendations")
def export_recommendations():
    rows = [[i["item"], i["current_stock"], i["min_level"], i["max_level"], i["suggested_order_quantity"], i["vendor"], i["status_label"]] for i in item_summary() if i["current_stock"] < i["min_level"]]
    return csv_response("order_recommendations.csv", ["Item", "Current Stock", "Min Level", "Max Level", "Suggested Order Quantity", "Vendor", "Status"], rows)


@app.route("/export/usage")
def export_usage():
    rows = get_db().execute("""
        SELECT u.date, e.name AS employee, i.item, u.quantity_used, u.job_account_work_order, u.notes
        FROM usage_entries u JOIN employees e ON e.id=u.employee_id JOIN inventory_items i ON i.id=u.item_id
        ORDER BY u.date DESC, u.id DESC
    """).fetchall()
    return csv_response("employee_usage.csv", ["Date", "Employee", "Item", "Quantity Used", "Job/Account/Work Order", "Notes"], rows)


@app.route("/export/received")
def export_received():
    rows = get_db().execute("""
        SELECT r.date_received, i.item, r.quantity_ordered, r.quantity_received, COALESCE(v.name,'') AS vendor, r.packing_slip_verified, e.name AS accepted_by, r.notes
        FROM received_orders r JOIN inventory_items i ON i.id=r.item_id LEFT JOIN vendors v ON v.id=r.vendor_id JOIN employees e ON e.id=r.accepted_by
        ORDER BY r.date_received DESC, r.id DESC
    """).fetchall()
    return csv_response("received_orders.csv", ["Date Received", "Item", "Quantity Ordered", "Quantity Received", "Vendor", "Packing Slip Verified", "Accepted By", "Notes"], rows)


@app.route("/export/report")
def export_report():
    summaries = item_summary()
    rows = [[i["item"], i["current_stock"], i["weekly_total_out"], i["min_level"], i["max_level"], i["suggested_order_quantity"], i["status_label"]] for i in summaries]
    return csv_response("comprehensive_usage_report.csv", ["Item", "Current Stock", "Weekly Total Out", "Min Level", "Max Level", "Suggested Order Quantity", "Status"], rows)


if __name__ == "__main__":
    init_db()
    seed_data()
    app.run(debug=True)
