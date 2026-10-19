import os, re, sqlite3
from datetime import date, datetime
import customtkinter as ctk
from tkinter import messagebox
from db import (conn, BASE, VERSION, get_setting, set_setting, save_invoice,
                get_invoice, apply_payment, month_data)
from calc import egg_stats, rs
from receipt import thermal_receipt, a4_invoice, monthly_statement

GREEN, DARK, BG, CARD = "#2E7D32", "#1B5E20", "#E6ECE3", "#FFFFFF"
BORDER = "#B7C2B3"          # soft green-grey outline. For a black outline use "#222222"
BOX = dict(fg_color=CARD, border_width=1, border_color=BORDER, corner_radius=10)


def card(parent):
    return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12, border_width=1, border_color=BORDER)


def num(entry):
    """Number from an entry. Blank = 0. Invalid = None."""
    try:
        return float(entry.get().replace(",", "").strip() or 0)
    except ValueError:
        return None


def status(total, paid):
    if paid >= total - 0.5:
        return "Paid"
    return "Unpaid" if paid <= 0 else "Partial"


def open_pdf(path, direct=False):
    try:
        os.startfile(path, "print" if direct else "open")
    except Exception:
        os.startfile(path)


class Page(ctk.CTkFrame):
    title = ""

    def __init__(self, master):
        super().__init__(master, fg_color=BG, corner_radius=0)
        ctk.CTkLabel(self, text=self.title, font=("Segoe UI", 26, "bold"),
                     text_color=DARK).pack(anchor="w", padx=30, pady=(24, 12))

    def refresh(self):
        pass


# ---------------------------------------------------------------- DASHBOARD
class Dashboard(Page):
    title = "Dashboard"

    def __init__(self, master):
        super().__init__(master)
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=22)
        self.vals = {}
        names = ["Good eggs today", "Production today", "Sales today", "Sales this month", "Pending balance"]
        for c in range(3):
            grid.grid_columnconfigure(c, weight=1)
        for i, n in enumerate(names):
            box = card(grid)
            box.grid(row=i // 3, column=i % 3, padx=8, pady=8, sticky="nsew")
            ctk.CTkLabel(box, text=n, text_color="#555", font=("Segoe UI", 13)).pack(anchor="w", padx=18, pady=(14, 0))
            v = ctk.CTkLabel(box, text="-", text_color=DARK, font=("Segoe UI", 28, "bold"))
            v.pack(anchor="w", padx=18, pady=(0, 14))
            self.vals[n] = v
        ctk.CTkLabel(self, text="Recent invoices", font=("Segoe UI", 16, "bold"),
                     text_color=DARK).pack(anchor="w", padx=30, pady=(14, 4))
        self.recent = ctk.CTkTextbox(self, height=230, font=("Consolas", 13), **BOX)
        self.recent.pack(fill="x", padx=30)

    def refresh(self):
        today = str(date.today())
        good, coll = conn.execute(
            "SELECT COALESCE(SUM(collected - broken),0), COALESCE(SUM(collected),0) "
            "FROM egg_records WHERE date = ?", (today,)).fetchone()
        birds = conn.execute(
            "SELECT COALESCE(SUM(birds),0) FROM egg_records WHERE id IN "
            "(SELECT MAX(id) FROM egg_records WHERE date = ? GROUP BY flock)", (today,)).fetchone()[0]
        sales_today = conn.execute("SELECT COALESCE(SUM(total),0) FROM invoices WHERE date = ?", (today,)).fetchone()[0]
        sales_month = conn.execute("SELECT COALESCE(SUM(total),0) FROM invoices WHERE date LIKE ?",
                                   (today[:7] + "%",)).fetchone()[0]
        pending = conn.execute("SELECT COALESCE(SUM(total - COALESCE(paid,0)),0) FROM invoices "
                               "WHERE total - COALESCE(paid,0) > 0.5").fetchone()[0]
        v = self.vals
        v["Good eggs today"].configure(text=f"{good:,}")
        v["Production today"].configure(text=f"{coll / birds * 100:.1f}%" if birds else "-")
        v["Sales today"].configure(text=rs(sales_today))
        v["Sales this month"].configure(text=rs(sales_month))
        v["Pending balance"].configure(text=rs(pending))
        self.recent.delete("1.0", "end")
        for i, d, c, t, p in conn.execute("SELECT id, date, customer, total, COALESCE(paid,0) FROM invoices "
                                          "ORDER BY id DESC LIMIT 10"):
            self.recent.insert("end", f"INV-{i:04d}  {d}  {c:<18.18} {rs(t):>12}  {status(t, p)}\n")


# ---------------------------------------------------------------- DAILY EGGS
class EggsPage(Page):
    title = "Daily Egg Entry"

    def __init__(self, master):
        super().__init__(master)
        form = card(self)
        form.pack(fill="x", padx=30, pady=(0, 12))
        self.f = {}
        for i, (label, default) in enumerate([("Date", str(date.today())), ("Flock", "Shed 1"), ("Live birds", ""),
                                              ("Eggs collected", ""), ("Broken", "0")]):
            ctk.CTkLabel(form, text=label).grid(row=0, column=i, padx=12, pady=(14, 0), sticky="w")
            e = ctk.CTkEntry(form, width=150)
            e.insert(0, default)
            e.grid(row=1, column=i, padx=12, pady=(0, 14))
            self.f[label] = e
        ctk.CTkButton(form, text="Calculate & Save", fg_color=GREEN, command=self.save).grid(row=1, column=5, padx=12)
        self.result = ctk.CTkLabel(self, text="", justify="left", font=("Segoe UI", 18), text_color=DARK)
        self.result.pack(anchor="w", padx=30, pady=8)
        self.log = ctk.CTkTextbox(self, height=260, font=("Consolas", 13), **BOX)
        self.log.pack(fill="x", padx=30)

    def save(self):
        try:
            b, c, br = (int(self.f[k].get()) for k in ("Live birds", "Eggs collected", "Broken"))
        except ValueError:
            messagebox.showerror("Invalid", "Enter whole numbers for birds, eggs and broken.")
            return
        if b <= 0 or c < 0 or br < 0 or br > c:
            messagebox.showerror("Invalid", "Check the numbers (broken cannot be more than collected).")
            return
        s = egg_stats(b, c, br)
        conn.execute("INSERT INTO egg_records(date, flock, birds, collected, broken) VALUES (?,?,?,?,?)",
                     (self.f["Date"].get(), self.f["Flock"].get(), b, c, br))
        conn.commit()
        self.result.configure(text=f"Good eggs: {s['good']}    Trays: {s['trays']} + {s['loose']} loose    "
                                   f"Dozens: {s['dozens']:.1f}    Production: {s['production_pct']}%")
        self.f["Eggs collected"].delete(0, "end")
        self.f["Broken"].delete(0, "end")
        self.f["Broken"].insert(0, "0")
        self.refresh()

    def refresh(self):
        self.f["Date"].delete(0, "end")
        self.f["Date"].insert(0, str(date.today()))
        if not self.f["Live birds"].get():
            r = conn.execute("SELECT birds FROM egg_records ORDER BY id DESC LIMIT 1").fetchone()
            if r:
                self.f["Live birds"].insert(0, str(r[0]))
        self.log.delete("1.0", "end")
        self.log.insert("end", f"{'Date':<12}{'Flock':<12}{'Birds':>7}{'Eggs':>7}{'Broken':>8}{'Good':>7}{'Prod%':>8}\n")
        for d, f, b, c, br in conn.execute("SELECT date, flock, birds, collected, broken FROM egg_records "
                                           "ORDER BY id DESC LIMIT 15"):
            pct = c / b * 100 if b else 0
            self.log.insert("end", f"{d:<12}{f:<12.11}{b:>7}{c:>7}{br:>8}{c - br:>7}{pct:>7.1f}%\n")


# ---------------------------------------------------------------- NEW SALE
class SalePage(Page):
    title = "New Sale"

    def __init__(self, master):
        super().__init__(master)
        self.cart, self.items = [], {}
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=30, pady=(0, 16))
        body.grid_columnconfigure((0, 1), weight=1)
        body.grid_rowconfigure(0, weight=1)
        left, right = card(body), card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        def label(parent, text):
            ctk.CTkLabel(parent, text=text, text_color="#555").pack(anchor="w", padx=20, pady=(12, 2))

        label(left, "Customer")
        self.customer = ctk.CTkComboBox(left, values=["Walk-in"], width=320, command=self.on_customer)
        self.customer.set("Walk-in")
        self.customer.pack(anchor="w", padx=20)
        label(left, "Phone (optional)")
        self.phone = ctk.CTkEntry(left, width=320)
        self.phone.pack(anchor="w", padx=20)
        label(left, "Item")
        self.item = ctk.CTkOptionMenu(left, values=["-"], width=320, command=self.on_item,
                                      fg_color=GREEN, button_color=DARK)
        self.item.pack(anchor="w", padx=20)
        label(left, "Quantity")
        self.qty = ctk.CTkEntry(left, width=320)
        self.qty.pack(anchor="w", padx=20)
        label(left, "Price per unit (Rs.)")
        self.price = ctk.CTkEntry(left, width=320)
        self.price.pack(anchor="w", padx=20)
        ctk.CTkButton(left, text="+ Add to bill", fg_color=GREEN, width=320, height=40,
                      command=self.add).pack(anchor="w", padx=20, pady=18)

        ctk.CTkLabel(right, text="Bill", font=("Segoe UI", 16, "bold"),
                     text_color=DARK).pack(anchor="w", padx=20, pady=(14, 4))
        self.view = ctk.CTkTextbox(right, height=200, font=("Consolas", 13), border_width=1, border_color=BORDER)
        self.view.pack(fill="x", padx=20)
        bar = ctk.CTkFrame(right, fg_color="transparent")
        bar.pack(fill="x", padx=20, pady=6)
        ctk.CTkButton(bar, text="Remove last", width=110, fg_color="#9E9E9E", command=self.remove_last).pack(side="left")
        ctk.CTkButton(bar, text="Clear", width=80, fg_color="#9E9E9E", command=self.reset).pack(side="left", padx=8)
        row = ctk.CTkFrame(right, fg_color="transparent")
        row.pack(fill="x", padx=20)
        ctk.CTkLabel(row, text="Discount (Rs.)").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(row, text="Paid now (blank = full)").grid(row=0, column=1, sticky="w", padx=12)
        self.discount = ctk.CTkEntry(row, width=150)
        self.discount.grid(row=1, column=0)
        self.discount.bind("<KeyRelease>", lambda e: self.render())
        self.paid = ctk.CTkEntry(row, width=170)
        self.paid.grid(row=1, column=1, padx=12)
        self.total_lbl = ctk.CTkLabel(right, text="TOTAL  Rs. 0", font=("Segoe UI", 24, "bold"), text_color=DARK)
        self.total_lbl.pack(anchor="w", padx=20, pady=10)
        self.direct = ctk.CTkCheckBox(right, text="Print directly to default printer")
        self.direct.pack(anchor="w", padx=20)
        ctk.CTkButton(right, text="Save & Print Receipt (Thermal 80mm)", height=42, fg_color=GREEN,
                      command=lambda: self.save("thermal")).pack(fill="x", padx=20, pady=(12, 4))
        ctk.CTkButton(right, text="Save & A4 Invoice", height=42, fg_color=DARK,
                      command=lambda: self.save("a4")).pack(fill="x", padx=20, pady=4)

    def on_customer(self, choice):
        r = conn.execute("SELECT phone FROM customers WHERE name = ?", (choice,)).fetchone()
        self.phone.delete(0, "end")
        if r and r[0]:
            self.phone.insert(0, r[0])

    def on_item(self, choice):
        self.price.delete(0, "end")
        self.price.insert(0, f"{self.items.get(choice, 0):g}")

    def add(self):
        q, p = num(self.qty), num(self.price)
        if not q or q <= 0 or p is None or p < 0:
            messagebox.showerror("Invalid", "Enter a valid quantity and price.")
            return
        self.cart.append([self.item.get(), q, p])
        self.qty.delete(0, "end")
        self.render()

    def remove_last(self):
        if self.cart:
            self.cart.pop()
            self.render()

    def render(self):
        self.view.delete("1.0", "end")
        for i, (n, q, p) in enumerate(self.cart, 1):
            self.view.insert("end", f"{i}. {n[:16]:<16}{q:>6g} x {p:>6,.0f} = {q * p:>9,.0f}\n")
        sub = sum(q * p for _, q, p in self.cart)
        disc = num(self.discount) or 0
        self.total_lbl.configure(text=f"TOTAL  {rs(max(sub - disc, 0))}")

    def reset(self):
        self.cart.clear()
        for e in (self.qty, self.discount, self.paid, self.phone):
            e.delete(0, "end")
        self.customer.set("Walk-in")
        self.refresh()

    def save(self, kind):
        if not self.cart:
            messagebox.showwarning("Empty bill", "Add at least one item.")
            return
        sub = sum(q * p for _, q, p in self.cart)
        disc = num(self.discount)
        if disc is None or disc < 0 or disc > sub:
            messagebox.showerror("Invalid", "Discount is not valid.")
            return
        total = sub - disc
        paid = total if not self.paid.get().strip() else num(self.paid)
        if paid is None or paid < 0:
            messagebox.showerror("Invalid", "Paid amount is not valid.")
            return
        paid = min(paid, total)
        name = self.customer.get().strip() or "Walk-in"
        if name.lower() == "walk-in":
            name = "Walk-in"
        if total - paid > 0.5 and name == "Walk-in":
            messagebox.showwarning("Customer needed", "Enter a customer name when there is an unpaid balance.")
            return
        inv_id = save_invoice(name, self.phone.get().strip(), self.cart, disc, paid)
        inv = get_invoice(inv_id)
        path = thermal_receipt(inv) if kind == "thermal" else a4_invoice(inv)
        open_pdf(path, direct=bool(self.direct.get()))
        self.reset()

    def refresh(self):
        self.items = dict(conn.execute("SELECT name, price FROM items ORDER BY id").fetchall())
        names = list(self.items) or ["-"]
        self.item.configure(values=names)
        cur = self.item.get()
        if cur not in self.items:
            cur = "Egg (dozen)" if "Egg (dozen)" in self.items else names[0]
        self.item.set(cur)
        self.on_item(cur)
        self.customer.configure(values=["Walk-in"] + [r[0] for r in conn.execute(
            "SELECT name FROM customers ORDER BY name")])
        self.render()


# ---------------------------------------------------------------- INVOICE HISTORY
class InvoicesPage(Page):
    title = "Invoice History"

    def __init__(self, master):
        super().__init__(master)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=30)
        self.search = ctk.CTkEntry(top, width=340, placeholder_text="Search customer or invoice number")
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda e: self.refresh())
        self.list = ctk.CTkScrollableFrame(self, **BOX)
        self.list.pack(fill="both", expand=True, padx=30, pady=12)

    def refresh(self):
        for w in self.list.winfo_children():
            w.destroy()
        q = self.search.get().strip()
        id_q = q.upper().replace("INV-", "").lstrip("0")
        rows = conn.execute("SELECT id, date, customer, total, COALESCE(paid,0) FROM invoices "
                            "WHERE customer LIKE ? OR CAST(id AS TEXT) LIKE ? ORDER BY id DESC LIMIT 60",
                            (f"%{q}%", f"%{id_q}%")).fetchall()
        for r, (i, d, c, t, p) in enumerate(rows):
            for col, v in enumerate([f"INV-{i:04d}", d, c, rs(t), status(t, p)]):
                ctk.CTkLabel(self.list, text=v, anchor="w", width=[90, 90, 170, 100, 70][col]).grid(
                    row=r, column=col, padx=6, pady=4, sticky="w")
            ctk.CTkButton(self.list, text="Thermal", width=70, fg_color=GREEN,
                          command=lambda i=i: self.reprint(i, "thermal")).grid(row=r, column=5, padx=4)
            ctk.CTkButton(self.list, text="A4", width=60, fg_color=DARK,
                          command=lambda i=i: self.reprint(i, "a4")).grid(row=r, column=6, padx=4)

    def reprint(self, inv_id, kind):
        inv = get_invoice(inv_id)
        open_pdf(thermal_receipt(inv) if kind == "thermal" else a4_invoice(inv))


# ---------------------------------------------------------------- CUSTOMERS
class CustomersPage(Page):
    title = "Customers & Balances"

    def __init__(self, master):
        super().__init__(master)
        self.list = ctk.CTkScrollableFrame(self, fg_color=CARD)
        self.list.pack(fill="both", expand=True, padx=30, pady=(0, 20))

    def refresh(self):
        for w in self.list.winfo_children():
            w.destroy()
        for c, h in enumerate(["Customer", "Phone", "Total billed", "Balance due"]):
            ctk.CTkLabel(self.list, text=h, font=("Segoe UI", 13, "bold"), text_color=DARK, width=150,
                         anchor="w").grid(row=0, column=c, padx=8, pady=6, sticky="w")
        rows = conn.execute("SELECT c.name, COALESCE(c.phone,''), COALESCE(SUM(i.total),0), "
                            "COALESCE(SUM(i.total - COALESCE(i.paid,0)),0) FROM customers c "
                            "LEFT JOIN invoices i ON i.customer = c.name GROUP BY c.id ORDER BY 4 DESC").fetchall()
        for r, (n, ph, billed, bal) in enumerate(rows, 1):
            for c, v in enumerate([n, ph, rs(billed), rs(max(bal, 0))]):
                ctk.CTkLabel(self.list, text=v, anchor="w", width=150).grid(row=r, column=c, padx=8, pady=4, sticky="w")
            if bal > 0.5:
                ctk.CTkButton(self.list, text="Receive Payment", width=130, fg_color=GREEN,
                              command=lambda n=n, b=bal: self.pay(n, b)).grid(row=r, column=4, padx=8)

    def pay(self, name, balance):
        v = ctk.CTkInputDialog(text=f"{name} owes {rs(balance)}.\nAmount received (Rs.):",
                               title="Receive Payment").get_input()
        if not v:
            return
        try:
            amt = float(v.replace(",", ""))
        except ValueError:
            messagebox.showerror("Invalid", "Enter a valid amount.")
            return
        if amt <= 0:
            return
        left = apply_payment(name, amt)
        if left > 0.5:
            messagebox.showinfo("Note", f"{rs(left)} was more than the balance and was not applied.")
        self.refresh()


# ---------------------------------------------------------------- PRICES
class PricesPage(Page):
    title = "Prices"

    def __init__(self, master):
        super().__init__(master)
        top = card(self)
        top.pack(fill="x", padx=30, pady=(0, 12))
        ctk.CTkLabel(top, text="Egg prices (PKR)", font=("Segoe UI", 16, "bold"),
                     text_color=DARK).grid(row=0, column=0, columnspan=3, padx=16, pady=(14, 4), sticky="w")
        ctk.CTkLabel(top, text="Price per egg").grid(row=1, column=0, padx=16, sticky="w")
        ctk.CTkLabel(top, text="Price per dozen").grid(row=1, column=1, padx=16, sticky="w")
        self.egg = ctk.CTkEntry(top, width=160)
        self.egg.grid(row=2, column=0, padx=16, pady=(0, 14))
        self.dozen = ctk.CTkEntry(top, width=160)
        self.dozen.grid(row=2, column=1, padx=16, pady=(0, 14))
        ctk.CTkButton(top, text="Update Prices", fg_color=GREEN, command=self.save_eggs).grid(row=2, column=2, padx=16)
        self.note = ctk.CTkLabel(top, text="New sales use these prices. Old invoices are not changed.", text_color="#555")
        self.note.grid(row=3, column=0, columnspan=3, padx=16, pady=(0, 12), sticky="w")

        add = card(self)
        add.pack(fill="x", padx=30, pady=(0, 12))
        ctk.CTkLabel(add, text="Other items", font=("Segoe UI", 16, "bold"),
                     text_color=DARK).grid(row=0, column=0, padx=16, pady=(14, 4), sticky="w")
        self.new_name = ctk.CTkEntry(add, width=220, placeholder_text="Item name")
        self.new_name.grid(row=1, column=0, padx=16, pady=(0, 14))
        self.new_price = ctk.CTkEntry(add, width=120, placeholder_text="Price")
        self.new_price.grid(row=1, column=1, padx=8, pady=(0, 14))
        ctk.CTkButton(add, text="Add Item", fg_color=GREEN, command=self.add_item).grid(row=1, column=2, padx=8, pady=(0, 14))
        self.list = ctk.CTkScrollableFrame(self, fg_color=CARD)
        self.list.pack(fill="both", expand=True, padx=30, pady=(0, 16))

    def save_eggs(self):
        e, d = num(self.egg), num(self.dozen)
        if not e or not d or e <= 0 or d <= 0:
            messagebox.showerror("Invalid", "Enter valid prices.")
            return
        for name, price in (("Egg (single)", e), ("Egg (dozen)", d)):
            conn.execute("INSERT INTO items(name, price) VALUES (?, ?) "
                         "ON CONFLICT(name) DO UPDATE SET price = excluded.price", (name, price))
        conn.commit()
        self.note.configure(text=f"Updated: Rs. {e:g} per egg, Rs. {d:g} per dozen.", text_color=GREEN)

    def add_item(self):
        n, p = self.new_name.get().strip(), num(self.new_price)
        if not n or p is None or p < 0:
            messagebox.showerror("Invalid", "Enter an item name and price.")
            return
        try:
            conn.execute("INSERT INTO items(name, price) VALUES (?, ?)", (n, p))
            conn.commit()
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate", "An item with this name already exists.")
            return
        self.new_name.delete(0, "end")
        self.new_price.delete(0, "end")
        self.refresh()

    def save_item(self, item_id, entry):
        p = num(entry)
        if p is None or p < 0:
            messagebox.showerror("Invalid", "Enter a valid price.")
            return
        conn.execute("UPDATE items SET price = ? WHERE id = ?", (p, item_id))
        conn.commit()

    def delete_item(self, item_id):
        if messagebox.askyesno("Delete item", "Delete this item? Old invoices are not affected."):
            conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
            conn.commit()
            self.refresh()

    def refresh(self):
        eggs = dict(conn.execute("SELECT name, price FROM items WHERE name IN ('Egg (single)', 'Egg (dozen)')").fetchall())
        for entry, key in ((self.egg, "Egg (single)"), (self.dozen, "Egg (dozen)")):
            entry.delete(0, "end")
            entry.insert(0, f"{eggs.get(key, 0):g}")
        for w in self.list.winfo_children():
            w.destroy()
        others = conn.execute("SELECT id, name, price FROM items WHERE name NOT IN ('Egg (single)', 'Egg (dozen)') "
                              "ORDER BY name").fetchall()
        for r, (i, n, p) in enumerate(others):
            ctk.CTkLabel(self.list, text=n, width=220, anchor="w").grid(row=r, column=0, padx=8, pady=4)
            e = ctk.CTkEntry(self.list, width=110)
            e.insert(0, f"{p:g}")
            e.grid(row=r, column=1, padx=8)
            ctk.CTkButton(self.list, text="Save", width=60, fg_color=GREEN,
                          command=lambda i=i, e=e: self.save_item(i, e)).grid(row=r, column=2, padx=4)
            ctk.CTkButton(self.list, text="Delete", width=60, fg_color="#C62828",
                          command=lambda i=i: self.delete_item(i)).grid(row=r, column=3, padx=4)


# ---------------------------------------------------------------- MONTHLY STATEMENT
class StatementPage(Page):
    title = "Monthly Statement (A4)"

    def __init__(self, master):
        super().__init__(master)
        box = card(self)
        box.pack(fill="x", padx=30)
        ctk.CTkLabel(box, text="Customer").grid(row=0, column=0, padx=16, pady=(14, 0), sticky="w")
        ctk.CTkLabel(box, text="Month (YYYY-MM)").grid(row=0, column=1, padx=16, pady=(14, 0), sticky="w")
        self.customer = ctk.CTkComboBox(box, values=[""], width=280)
        self.customer.grid(row=1, column=0, padx=16, pady=(0, 16))
        self.month = ctk.CTkEntry(box, width=150)
        self.month.grid(row=1, column=1, padx=16, pady=(0, 16))
        ctk.CTkButton(box, text="Create A4 Monthly Invoice", fg_color=DARK, command=self.make).grid(row=1, column=2, padx=16)
        ctk.CTkLabel(self, text="Lists every sale for the customer in that month, plus any older unpaid balance.",
                     text_color="#555").pack(anchor="w", padx=30, pady=10)

    def make(self):
        name, month = self.customer.get().strip(), self.month.get().strip()
        if not name or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            messagebox.showerror("Invalid", "Choose a customer and enter the month like 2026-10.")
            return
        invs, lines, prev = month_data(name, month)
        if not invs:
            messagebox.showinfo("No sales", f"No invoices for {name} in {month}.")
            return
        open_pdf(monthly_statement(name, month, invs, lines, prev))

    def refresh(self):
        names = [r[0] for r in conn.execute("SELECT DISTINCT customer FROM invoices WHERE customer != 'Walk-in' "
                                            "ORDER BY customer")]
        self.customer.configure(values=names or [""])
        self.month.delete(0, "end")
        self.month.insert(0, date.today().strftime("%Y-%m"))


# ---------------------------------------------------------------- SETTINGS
class SettingsPage(Page):
    title = "Settings"

    def __init__(self, master):
        super().__init__(master)
        box = card(self)
        box.pack(fill="x", padx=30)
        self.e = {}
        for label, key, width in (("Farm name", "farm_name", 360), ("Phone", "phone", 360),
                                  ("Receipt footer message", "footer", 520)):
            ctk.CTkLabel(box, text=label).pack(anchor="w", padx=20, pady=(14, 2))
            en = ctk.CTkEntry(box, width=width)
            en.pack(anchor="w", padx=20)
            self.e[key] = en
        ctk.CTkButton(box, text="Save Settings", fg_color=GREEN, command=self.save).pack(anchor="w", padx=20, pady=16)
        b2 = card(self)
        b2.pack(fill="x", padx=30, pady=14)
        ctk.CTkLabel(b2, text="Backup", font=("Segoe UI", 16, "bold"), text_color=DARK).pack(anchor="w", padx=20, pady=(14, 2))
        ctk.CTkLabel(b2, text=f"Data folder: {BASE}\nVersion {VERSION}", justify="left", text_color="#555").pack(anchor="w", padx=20)
        ctk.CTkButton(b2, text="Backup Now", fg_color=DARK, command=self.backup).pack(anchor="w", padx=20, pady=14)

    def save(self):
        for k, en in self.e.items():
            set_setting(k, en.get().strip())
        messagebox.showinfo("Saved", "Settings saved. Restart the app to update the sidebar title.")

    def backup(self):
        folder = os.path.join(BASE, "backups")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"farm-{datetime.now():%Y-%m-%d_%H%M}.db")
        dst = sqlite3.connect(path)
        conn.backup(dst)
        dst.close()
        messagebox.showinfo("Backup done", path)

    def refresh(self):
        for k, en in self.e.items():
            en.delete(0, "end")
            en.insert(0, get_setting(k))