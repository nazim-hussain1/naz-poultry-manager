import sqlite3, os, sys
from datetime import datetime

VERSION = "2.0"
BASE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
conn = sqlite3.connect(os.path.join(BASE, "farm.db"))

conn.executescript("""
CREATE TABLE IF NOT EXISTS egg_records(id INTEGER PRIMARY KEY, date TEXT, flock TEXT, birds INTEGER, collected INTEGER, broken INTEGER);
CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, name TEXT UNIQUE, price REAL);
CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY, name TEXT UNIQUE, phone TEXT);
CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY, customer TEXT, date TEXT, total REAL);
CREATE TABLE IF NOT EXISTS invoice_items(id INTEGER PRIMARY KEY, invoice_id INTEGER, name TEXT, qty REAL, price REAL, line_total REAL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
INSERT OR IGNORE INTO items(name, price) VALUES ('Egg (single)', 22), ('Egg (dozen)', 263);
INSERT OR IGNORE INTO settings(key, value) VALUES ('farm_name', 'Naz Poultry'), ('phone', '0333-7006557'), ('footer', 'Thank you for your business!');
""")


def add_column(table, col, decl):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


# ---- upgrade older databases (migrations) ----
add_column("invoices", "discount", "REAL DEFAULT 0")
add_column("invoices", "paid", "REAL DEFAULT 0")
add_column("invoices", "created", "TEXT")

if conn.execute("PRAGMA user_version").fetchone()[0] < 1:
    conn.execute("UPDATE items SET price = 263 WHERE name = 'Egg (dozen)'")
    conn.execute("UPDATE invoices SET paid = total")  # old test invoices count as paid
    conn.execute("INSERT OR IGNORE INTO customers(name) SELECT DISTINCT customer FROM invoices "
                 "WHERE customer IS NOT NULL AND customer NOT IN ('', 'Walk-in')")
    conn.execute("PRAGMA user_version = 1")
conn.commit()


# ---- helpers ----
def get_setting(key):
    r = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return r[0] if r else ""


def set_setting(key, value):
    conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.commit()


def save_invoice(customer, phone, cart, discount, paid):
    subtotal = sum(q * p for _, q, p in cart)
    total = max(subtotal - discount, 0)
    now = datetime.now()
    inv_id = conn.execute(
        "INSERT INTO invoices(customer, date, total, discount, paid, created) VALUES (?,?,?,?,?,?)",
        (customer, now.strftime("%Y-%m-%d"), total, discount, paid, now.strftime("%H:%M"))).lastrowid
    conn.executemany(
        "INSERT INTO invoice_items(invoice_id, name, qty, price, line_total) VALUES (?,?,?,?,?)",
        [(inv_id, n, q, p, q * p) for n, q, p in cart])
    if customer != "Walk-in":
        conn.execute("INSERT OR IGNORE INTO customers(name, phone) VALUES (?, ?)", (customer, phone))
        if phone:
            conn.execute("UPDATE customers SET phone = ? WHERE name = ?", (phone, customer))
    conn.commit()
    return inv_id


def get_invoice(inv_id):
    h = conn.execute("SELECT id, customer, date, total, COALESCE(discount,0), COALESCE(paid,0), COALESCE(created,'') "
                     "FROM invoices WHERE id = ?", (inv_id,)).fetchone()
    items = conn.execute("SELECT name, qty, price FROM invoice_items WHERE invoice_id = ? ORDER BY id",
                         (inv_id,)).fetchall()
    return {"id": h[0], "customer": h[1], "date": h[2], "total": h[3],
            "discount": h[4], "paid": h[5], "time": h[6], "items": items}


def apply_payment(customer, amount):
    """Apply a payment to the oldest unpaid invoices first. Returns leftover amount."""
    rows = conn.execute("SELECT id, total, COALESCE(paid,0) FROM invoices "
                        "WHERE customer = ? AND total - COALESCE(paid,0) > 0.5 ORDER BY date, id",
                        (customer,)).fetchall()
    for inv_id, total, paid in rows:
        if amount <= 0:
            break
        pay = min(amount, total - paid)
        conn.execute("UPDATE invoices SET paid = ? WHERE id = ?", (paid + pay, inv_id))
        amount -= pay
    conn.commit()
    return amount


def month_data(customer, month):
    like = month + "%"
    invs = conn.execute("SELECT id, date, total, COALESCE(discount,0), COALESCE(paid,0) FROM invoices "
                        "WHERE customer = ? AND date LIKE ? ORDER BY date, id", (customer, like)).fetchall()
    lines = conn.execute("SELECT i.date, i.id, ii.name, ii.qty, ii.price, ii.line_total "
                         "FROM invoices i JOIN invoice_items ii ON ii.invoice_id = i.id "
                         "WHERE i.customer = ? AND i.date LIKE ? ORDER BY i.date, i.id, ii.id",
                         (customer, like)).fetchall()
    prev = conn.execute("SELECT COALESCE(SUM(total - COALESCE(paid,0)), 0) FROM invoices "
                        "WHERE customer = ? AND date < ?", (customer, month + "-01")).fetchone()[0]
    return invs, lines, prev