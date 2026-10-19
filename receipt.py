import os, re, textwrap
from datetime import date, datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from db import BASE, get_setting
from calc import rs

GREEN = colors.HexColor("#2E7D32")
DARK = colors.HexColor("#1B5E20")
LIGHT = colors.HexColor("#E8F5E9")
LINE = colors.HexColor("#DDDDDD")
GREY = colors.HexColor("#666666")


def _path(name):
    folder = os.path.join(BASE, "invoices")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, name)


# ---------------- THERMAL 80mm ----------------
def thermal_receipt(inv):
    cols = 40  # characters per line (80mm paper). 58mm printers: use 30.
    path = _path(f"INV-{inv['id']:04d}-thermal.pdf")
    sub = inv["total"] + inv["discount"]
    bal = inv["total"] - inv["paid"]
    rule = "-" * cols
    out = []

    def add(text="", font="Courier", size=8.5, center=False):
        out.append((text, font, size, center))

    def row(label, value, bold=False):
        add(label + value.rjust(cols - len(label)), "Courier-Bold" if bold else "Courier")

    add(get_setting("farm_name").upper(), "Courier-Bold", 14, True)
    add("Tel: " + get_setting("phone"), center=True)
    add(rule)
    add(f"Invoice : INV-{inv['id']:04d}")
    add(f"Date    : {inv['date']} {inv['time']}".rstrip())
    add(f"Customer: {inv['customer']}"[:cols])
    add(rule)
    for n, q, p in inv["items"]:
        add(n[:cols], "Courier-Bold")
        left = f"  {q:g} x {p:,.0f}"
        add(left + f"{q * p:,.0f}".rjust(cols - len(left)))
    add(rule)
    row("Subtotal", f"{sub:,.0f}")
    if inv["discount"]:
        row("Discount", f"-{inv['discount']:,.0f}")
    row("TOTAL (PKR)", f"{inv['total']:,.0f}", True)
    row("Paid", f"{inv['paid']:,.0f}")
    if bal > 0.5:
        row("BALANCE DUE", f"{bal:,.0f}", True)
    add(rule)
    for t in textwrap.wrap(get_setting("footer"), cols):
        add(t, center=True)
    add("")

    W = 80 * mm
    height = sum(s * 1.4 for _, _, s, _ in out) + 12 * mm
    c = canvas.Canvas(path, pagesize=(W, height))
    y = height - 6 * mm
    for text, font, size, center in out:
        y -= size * 1.4
        c.setFont(font, size)
        if center:
            c.drawCentredString(W / 2, y, text)
        else:
            c.drawString(4 * mm, y, text)
    c.save()
    return path


# ---------------- A4 helpers ----------------
def _header(c, w, h, title, ref):
    c.setFillColor(GREEN)
    c.rect(0, h - 45 * mm, w, 45 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(20 * mm, h - 22 * mm, get_setting("farm_name"))
    c.setFont("Helvetica", 11)
    c.drawString(20 * mm, h - 30 * mm, "Tel: " + get_setting("phone"))
    c.setFont("Helvetica-Bold", 22)
    c.drawRightString(w - 20 * mm, h - 22 * mm, title)
    c.setFont("Helvetica", 11)
    c.drawRightString(w - 20 * mm, h - 30 * mm, ref)
    c.setFillColor(colors.black)


def _bill_to(c, w, h, customer, right_label, right_value):
    L, R = 20 * mm, w - 20 * mm
    y = h - 60 * mm
    c.setFillColor(GREY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(L, y, "BILL TO")
    c.drawRightString(R, y, right_label)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(L, y - 6 * mm, customer)
    c.setFont("Helvetica", 12)
    c.drawRightString(R, y - 6 * mm, right_value)
    return y - 22 * mm


def _head(c, y, L, R, cols):
    c.setFillColor(LIGHT)
    c.rect(L, y - 3 * mm, R - L, 9 * mm, stroke=0, fill=1)
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 10)
    for label, x, a in cols:
        (c.drawRightString if a == "r" else c.drawString)(x, y, label)
    c.setFillColor(colors.black)
    return y - 10 * mm


def _row(c, y, L, R, cols, vals):
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.black)
    for (_, x, a), v in zip(cols, vals):
        (c.drawRightString if a == "r" else c.drawString)(x, y, str(v))
    c.setStrokeColor(LINE)
    c.line(L, y - 2.5 * mm, R, y - 2.5 * mm)


def _summary(c, y, R, rows):
    for label, value, style in rows:
        if style == "total":
            y -= 4 * mm  # gap so the bar doesn't cover the row above
            c.setFillColor(GREEN)
            c.rect(R - 76 * mm, y - 3 * mm, 76 * mm, 10 * mm, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 12)
            c.drawString(R - 73 * mm, y, label)
            c.drawRightString(R - 3 * mm, y, value)
            c.setFillColor(colors.black)
            y -= 14 * mm
        else:
            c.setFont("Helvetica-Bold" if style == "b" else "Helvetica", 11)
            c.drawString(R - 73 * mm, y, label)
            c.drawRightString(R - 3 * mm, y, value)
            y -= 7 * mm
    return y


def _footer(c, w):
    c.setFont("Helvetica-Oblique", 10)
    c.setFillColor(GREY)
    c.drawCentredString(w / 2, 15 * mm, get_setting("footer"))
    c.setFillColor(colors.black)


# ---------------- A4 INVOICE ----------------
def a4_invoice(inv):
    path = _path(f"INV-{inv['id']:04d}-A4.pdf")
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4
    L, R = 20 * mm, w - 20 * mm
    cols = [("ITEM", L + 2 * mm, "l"), ("QTY", 118 * mm, "r"), ("RATE", 148 * mm, "r"), ("AMOUNT", R - 2 * mm, "r")]
    _header(c, w, h, "INVOICE", f"INV-{inv['id']:04d}")
    y = _bill_to(c, w, h, inv["customer"], "DATE", f"{inv['date']} {inv['time']}".strip())
    y = _head(c, y, L, R, cols)
    for n, q, p in inv["items"]:
        if y < 30 * mm:
            c.showPage()
            y = _head(c, h - 30 * mm, L, R, cols)
        _row(c, y, L, R, cols, [n, f"{q:g}", f"{p:,.0f}", f"{q * p:,.0f}"])
        y -= 8 * mm
    if y < 85 * mm:
        c.showPage()
        y = h - 30 * mm
    sub = inv["total"] + inv["discount"]
    bal = inv["total"] - inv["paid"]
    rows = [("Subtotal", rs(sub), "n")]
    if inv["discount"]:
        rows.append(("Discount", "- " + rs(inv["discount"]), "n"))
    rows += [("TOTAL", rs(inv["total"]), "total"), ("Paid", rs(inv["paid"]), "n")]
    if bal > 0.5:
        rows.append(("Balance due", rs(bal), "b"))
    _summary(c, y - 6 * mm, R, rows)
    _footer(c, w)
    c.save()
    return path


# ---------------- A4 MONTHLY STATEMENT ----------------
def monthly_statement(customer, month, invs, lines, prev):
    safe = re.sub(r"[^\w\-]", "_", customer)
    path = _path(f"MONTHLY-{safe}-{month}.pdf")
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4
    L, R = 20 * mm, w - 20 * mm
    pretty = datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    cols = [("DATE", L + 2 * mm, "l"), ("INV", L + 28 * mm, "l"), ("ITEM", L + 46 * mm, "l"),
            ("QTY", 138 * mm, "r"), ("RATE", 160 * mm, "r"), ("AMOUNT", R - 2 * mm, "r")]
    _header(c, w, h, "MONTHLY INVOICE", pretty)
    y = _bill_to(c, w, h, customer, "PRINTED", str(date.today()))
    y = _head(c, y, L, R, cols)
    for d, inv_id, name, q, p, lt in lines:
        if y < 30 * mm:
            c.showPage()
            y = _head(c, h - 30 * mm, L, R, cols)
        _row(c, y, L, R, cols, [d, f"{inv_id:04d}", name[:26], f"{q:g}", f"{p:,.0f}", f"{lt:,.0f}"])
        y -= 8 * mm
    if y < 95 * mm:
        c.showPage()
        y = h - 30 * mm
    items_total = sum(l[5] for l in lines)
    discounts = sum(i[3] for i in invs)
    billed = sum(i[2] for i in invs)
    paid = sum(i[4] for i in invs)
    rows = [("Items total", rs(items_total), "n")]
    if discounts:
        rows.append(("Discounts", "- " + rs(discounts), "n"))
    rows += [("This month billed", rs(billed), "n"), ("Received", rs(paid), "n"),
             ("Previous balance", rs(prev), "n"), ("TOTAL DUE", rs(prev + billed - paid), "total")]
    _summary(c, y - 6 * mm, R, rows)
    _footer(c, w)
    c.save()
    return path