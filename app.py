import sqlite3
from flask import Flask, render_template_string, request, redirect, url_for, flash, jsonify, send_file
import csv
import os
from datetime import datetime

DB_PATH = 'inventory.db'

app = Flask(__name__)
app.secret_key = 'bugman'

BASE_HTML = '''
<!DOCTYPE html>
<html>
<head>
<title>Holloman Inventory</title>
<style>
body { font-family: Arial; margin:0; }
.sidebar { width:200px; float:left; background:#222; height:100vh; color:white; padding:15px; }
.sidebar a { color:white; display:block; margin:10px 0; text-decoration:none; }
.content { margin-left:220px; padding:20px; }
table { border-collapse: collapse; width:100%; }
th, td { border:1px solid #ccc; padding:8px; }
button { padding:8px 12px; }
</style>
</head>
<body>
<div class="sidebar">
<h3>Inventory</h3>
<a href="/">Dashboard</a>
<a href="/inventory">Inventory</a>
<a href="/receive">Receive</a>
<a href="/usage">Usage</a>
<a href="/employees">Employees</a>
<a href="/recommend">Reorder</a>
</div>
<div class="content">
{% block content %}{% endblock %}
</div>
</body>
</html>
'''


def get_db():
    return sqlite3.connect(DB_PATH)


def init_db():
    db = get_db()
    c = db.cursor()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS inventory_items (
        id INTEGER PRIMARY KEY,
        name TEXT,
        container_size TEXT,
        starting_count INTEGER,
        min_level INTEGER,
        max_level INTEGER
    );

    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY,
        name TEXT,
        active INTEGER
    );

    CREATE TABLE IF NOT EXISTS received_orders (
        id INTEGER PRIMARY KEY,
        date TEXT,
        item_id INTEGER,
        qty_received INTEGER,
        vendor TEXT
    );

    CREATE TABLE IF NOT EXISTS usage_entries (
        id INTEGER PRIMARY KEY,
        date TEXT,
        employee_id INTEGER,
        item_id INTEGER,
        qty INTEGER
    );
    ''')
    db.commit()


def seed():
    db = get_db()
    c = db.cursor()

    items = [
        ('Termidor SC','20oz',10,5,20),
        ('Taurus SC','20oz',8,4,16),
        ('Glue Boards','pack',50,20,100),
        ('Rodent Bait','bucket',5,2,10)
    ]

    c.executemany('INSERT INTO inventory_items(name,container_size,starting_count,min_level,max_level) VALUES (?,?,?,?,?)', items)

    employees = [('Cole',1),('Tech 1',1),('Tech 2',1)]
    c.executemany('INSERT INTO employees(name,active) VALUES (?,?)', employees)

    db.commit()


def get_stock(item_id):
    db = get_db()
    c = db.cursor()

    c.execute('SELECT starting_count FROM inventory_items WHERE id=?',(item_id,))
    start = c.fetchone()[0]

    c.execute('SELECT SUM(qty_received) FROM received_orders WHERE item_id=?',(item_id,))
    received = c.fetchone()[0] or 0

    c.execute('SELECT SUM(qty) FROM usage_entries WHERE item_id=?',(item_id,))
    used = c.fetchone()[0] or 0

    return start + received - used


@app.route('/')
def dashboard():
    db = get_db()
    items = db.execute('SELECT * FROM inventory_items').fetchall()

    total = len(items)
    low = 0

    for i in items:
        stock = get_stock(i[0])
        if stock < i[4]:
            low += 1

    return render_template_string(BASE_HTML + '''{% block content %}
    <h2>Dashboard</h2>
    <p>Total Items: {{total}}</p>
    <p>Low Stock: {{low}}</p>
    {% endblock %}''', total=total, low=low)


@app.route('/inventory')
def inventory():
    db = get_db()
    rows = db.execute('SELECT * FROM inventory_items').fetchall()

    data = []
    for r in rows:
        stock = get_stock(r[0])
        status = 'OK'
        if stock < r[4]: status = 'Low'
        if stock <= r[3]: status = 'Reorder'
        data.append((r, stock, status))

    return render_template_string(BASE_HTML + '''{% block content %}
    <h2>Inventory</h2>
    <table>
    <tr><th>Item</th><th>Stock</th><th>Status</th></tr>
    {% for r,stock,status in data %}
    <tr><td>{{r[1]}}</td><td>{{stock}}</td><td>{{status}}</td></tr>
    {% endfor %}
    </table>
    {% endblock %}''', data=data)


@app.route('/receive', methods=['GET','POST'])
def receive():
    db = get_db()
    if request.method == 'POST':
        db.execute('INSERT INTO received_orders(date,item_id,qty_received,vendor) VALUES (?,?,?,?)',
                   (request.form['date'], request.form['item'], request.form['qty'], request.form['vendor']))
        db.commit()
        return redirect('/inventory')

    items = db.execute('SELECT id,name FROM inventory_items').fetchall()
    return render_template_string(BASE_HTML + '''{% block content %}
    <h2>Receive</h2>
    <form method="post">
    Date <input name="date"><br>
    Item <select name="item">{% for i in items %}<option value="{{i[0]}}">{{i[1]}}</option>{% endfor %}</select><br>
    Qty <input name="qty"><br>
    Vendor <input name="vendor"><br>
    <button>Save</button>
    </form>
    {% endblock %}''', items=items)


@app.route('/usage', methods=['GET','POST'])
def usage():
    db = get_db()
    if request.method == 'POST':
        item = int(request.form['item'])
        qty = int(request.form['qty'])

        if get_stock(item) < qty:
            flash('Not enough stock')
            return redirect('/usage')

        db.execute('INSERT INTO usage_entries(date,employee_id,item_id,qty) VALUES (?,?,?,?)',
                   (request.form['date'], request.form['emp'], item, qty))
        db.commit()
        return redirect('/inventory')

    items = db.execute('SELECT id,name FROM inventory_items').fetchall()
    emps = db.execute('SELECT id,name FROM employees WHERE active=1').fetchall()

    return render_template_string(BASE_HTML + '''{% block content %}
    <h2>Usage</h2>
    <form method="post">
    Date <input name="date"><br>
    Employee <select name="emp">{% for e in emps %}<option value="{{e[0]}}">{{e[1]}}</option>{% endfor %}</select><br>
    Item <select name="item">{% for i in items %}<option value="{{i[0]}}">{{i[1]}}</option>{% endfor %}</select><br>
    Qty <input name="qty"><br>
    <button>Save</button>
    </form>
    {% endblock %}''', items=items, emps=emps)


@app.route('/employees', methods=['GET','POST'])
def employees():
    db = get_db()
    if request.method == 'POST':
        db.execute('INSERT INTO employees(name,active) VALUES (?,1)',(request.form['name'],))
        db.commit()
        return redirect('/employees')

    emps = db.execute('SELECT * FROM employees').fetchall()
    return render_template_string(BASE_HTML + '''{% block content %}
    <h2>Employees</h2>
    <form method="post">Name <input name="name"><button>Add</button></form>
    <ul>{% for e in emps %}<li>{{e[1]}}</li>{% endfor %}</ul>
    {% endblock %}''', emps=emps)


@app.route('/recommend')
def recommend():
    db = get_db()
    rows = db.execute('SELECT * FROM inventory_items').fetchall()
    rec = []

    for r in rows:
        stock = get_stock(r[0])
        if stock < r[3]:
            rec.append((r[1], stock, r[3], r[4], r[4]-stock))

    return render_template_string(BASE_HTML + '''{% block content %}
    <h2>Reorder</h2>
    <table>
    <tr><th>Item</th><th>Stock</th><th>Min</th><th>Max</th><th>Order</th></tr>
    {% for r in rec %}
    <tr><td>{{r[0]}}</td><td>{{r[1]}}</td><td>{{r[2]}}</td><td>{{r[3]}}</td><td>{{r[4]}}</td></tr>
    {% endfor %}
    </table>
    {% endblock %}''', rec=rec)


if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        init_db()
        seed()
    app.run(debug=True)
