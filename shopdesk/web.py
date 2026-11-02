"""The offline web app."""
from datetime import date, timedelta

from . import core
from .core import money
from .fieldkit import App, Fail, bar_chart, card, form, h, link, redirect, stats, table

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, price INTEGER NOT NULL, cost INTEGER NOT NULL DEFAULT 0, stock REAL NOT NULL DEFAULT 0, reorder REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS bills (id INTEGER PRIMARY KEY, day TEXT NOT NULL, customer INTEGER REFERENCES customers(id), total INTEGER NOT NULL, discount INTEGER NOT NULL, profit INTEGER NOT NULL, credit INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS bill_lines (bill INTEGER NOT NULL REFERENCES bills(id), product INTEGER NOT NULL REFERENCES products(id), qty REAL NOT NULL, amount INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, phone TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY, customer INTEGER NOT NULL REFERENCES customers(id), day TEXT NOT NULL, amount INTEGER NOT NULL);
"""


def create_app(db="shop.db", today=date.today):
    a = App("ShopDesk", db, SCHEMA, [("Today", "/"), ("New bill", "/bill"), ("Products", "/products"), ("Customers", "/customers")])

    def product(r):
        return core.Product(r["id"], r["name"], r["price"], r["cost"], r["stock"], r["reorder"])

    def products():
        return [product(r) for r in a.rows("SELECT * FROM products ORDER BY name")]

    def owed(cid):
        rows = [(date.fromisoformat(r["day"]), "sale", r["total"]) for r in a.rows("SELECT day, total FROM bills WHERE customer = ? AND credit = 1", cid)]
        rows += [(date.fromisoformat(r["day"]), "payment", r["amount"]) for r in a.rows("SELECT day, amount FROM payments WHERE customer = ?", cid)]
        return rows

    @a.route("/")
    def home(req):
        now = today()
        d = now.isoformat()
        sales = a.row("SELECT COUNT(*) n, COALESCE(SUM(total), 0) t, COALESCE(SUM(profit), 0) p FROM bills WHERE day = ?", d)
        since = (now - timedelta(days=30)).isoformat()
        sold = {r["product"]: r["q"] / 30 for r in a.rows("SELECT l.product, SUM(l.qty) q FROM bill_lines l JOIN bills b ON b.id = l.bill WHERE b.day >= ? GROUP BY l.product", since)}
        last = {r["product"]: date.fromisoformat(r["d"]) for r in a.rows("SELECT l.product, MAX(b.day) d FROM bill_lines l JOIN bills b ON b.id = l.bill GROUP BY l.product")}
        ps = products()
        order = core.reorder_list(ps, sold)
        slow = core.slow_stock(ps, last, now)
        debt = sum(core.customer_balance([(k, x) for _, k, x in owed(c["id"])]) for c in a.rows("SELECT id FROM customers"))
        best = a.rows("SELECT p.name, SUM(l.amount) t FROM bill_lines l JOIN products p ON p.id = l.product JOIN bills b ON b.id = l.bill WHERE b.day >= ? GROUP BY p.id ORDER BY t DESC LIMIT 8", since)
        body = stats([("Sales today", money(sales["t"])), ("Bills", sales["n"]), ("Profit today", money(sales["p"])), ("Customers owe", money(debt)), ("Stock value", money(sum(round(p.cost * p.stock) for p in ps)))])
        body += card("Buy soon", table(order, [("Product", lambda r: r[0].name), ("Left", lambda r: f"{r[0].stock:g}"), ("Days of stock", lambda r: "?" if r[1] is None else f"{r[1]:.0f}"), ("Suggested order", lambda r: r[2])], "Stock looks fine."))
        body += card("Best sellers, last 30 days", bar_chart([(r["name"], r["t"] / 100) for r in best]))
        body += card("Slow stock", table(slow[:10], [("Product", lambda r: r[0].name), ("Days since a sale", lambda r: "never sold" if r[1] is None else r[1]), ("Money tied up", lambda r: money(r[2]))], "Nothing has been sitting."))
        return a.page("Today", body)

    @a.route("/products", ("GET", "POST"))
    def products_page(req):
        if req.method == "POST":
            try:
                if req.get("buy"):
                    r = a.row("SELECT * FROM products WHERE id = ?", req.text("buy"))
                    if r is None:
                        raise Fail("No such product", 404)
                    n = core.buy(product(r), req.number("qty", low=0.001), core.to_paisa(req.text("unit_cost")))
                    a.run("UPDATE products SET cost = ?, stock = ? WHERE id = ?", n.cost, n.stock, r["id"])
                    a.log("purchase", f"{r['name']} {req.get('qty')}")
                else:
                    a.run("INSERT INTO products (name, price, reorder) VALUES (?, ?, ?)", req.text("name"), core.to_paisa(req.text("price")), req.number("reorder", 0, 0))
            except core.ShopError as exc:
                raise Fail(str(exc)) from None
            return redirect("/products")
        rows = products()
        return a.page("Products", card("New product", form(a, "/products", [("name", "Name"), ("price", "Selling price"), ("reorder", "Reorder at", "number", 0)], "Add")) + card("Stock in", form(a, "/products", [("buy", "Product", "select", [(p.id, p.name) for p in rows]), ("qty", "Quantity", "number"), ("unit_cost", "Buying price per unit")], "Record purchase")) + card("Products", table(rows, [("Name", lambda p: p.name), ("Price", lambda p: money(p.price)), ("Cost", lambda p: money(p.cost)), ("Stock", lambda p: f"{p.stock:g}"), ("Margin", lambda p: f"{core.margin(p):.0%}"), ("Note", lambda p: "; ".join(core.price_warnings(p)))], "No products yet.")))

    @a.route("/bill", ("GET", "POST"))
    def new_bill(req):
        ps = products()
        by = {str(p.id): p for p in ps}
        if req.method == "POST":
            lines = []
            for p in ps:
                q = str(req.form.get(f"q{p.id}", "")).strip()
                if q:
                    n = req.number(f"q{p.id}", low=0)
                    if n > 0:
                        lines.append((p, n))
            cust = req.text("customer", False) or None
            credit = bool(req.get("credit"))
            if credit and not cust:
                raise Fail("A credit sale needs a customer")
            try:
                b = core.bill(lines, core.to_paisa(req.get("discount") or 0))
            except core.ShopError as exc:
                raise Fail(str(exc)) from None
            cur = a.run("INSERT INTO bills (day, customer, total, discount, profit, credit) VALUES (?, ?, ?, ?, ?, ?)", today().isoformat(), cust, b["total"], b["discount"], core.bill_profit(b["rows"], b["discount"]), int(credit))
            for p, q, amount in b["rows"]:
                a.run("INSERT INTO bill_lines (bill, product, qty, amount) VALUES (?, ?, ?, ?)", cur.lastrowid, p.id, q, amount)
                a.run("UPDATE products SET stock = stock - ? WHERE id = ?", q, p.id)
            return redirect(f"/receipt/{cur.lastrowid}")
        fields = [(f"q{p.id}", f"{p.name} ({money(p.price)}, {p.stock:g} left)", "number", "") for p in ps]
        cust = [("", "Walk-in")] + [(c["id"], c["name"]) for c in a.rows("SELECT * FROM customers ORDER BY name")]
        return a.page("New bill", card("Quantities", form(a, "/bill", fields + [("discount", "Discount"), ("customer", "Customer", "select", cust), ("credit", "On credit (baki)", "checkbox", "1")], "Make bill")))

    @a.route("/receipt/<id>")
    def receipt(req, id):
        b = a.row("SELECT * FROM bills WHERE id = ?", id)
        if b is None:
            raise Fail("No such bill", 404)
        rows = a.rows("SELECT p.name, l.qty, l.amount FROM bill_lines l JOIN products p ON p.id = l.product WHERE l.bill = ?", id)
        return a.page(f"Receipt {id}", card(b["day"], table(rows, [("Item", "name"), ("Qty", lambda r: f"{r['qty']:g}"), ("Amount", lambda r: money(r["amount"]))]) + f"<p>Discount {money(b['discount'])}</p><p><b>Total {money(b['total'])}</b></p>" + ("<p>On credit</p>" if b["credit"] else "")))

    @a.route("/customers", ("GET", "POST"))
    def customers(req):
        if req.method == "POST":
            try:
                if req.get("pay"):
                    amount = core.to_paisa(req.text("amount"))
                    bal = core.customer_balance([(k, x) for _, k, x in owed(req.text("pay"))])
                    if amount <= 0 or amount > bal:
                        raise Fail(f"That customer owes {money(bal)}")
                    a.run("INSERT INTO payments (customer, day, amount) VALUES (?, ?, ?)", req.text("pay"), today().isoformat(), amount)
                else:
                    a.run("INSERT INTO customers (name, phone) VALUES (?, ?)", req.text("name"), req.text("phone", False))
            except core.ShopError as exc:
                raise Fail(str(exc)) from None
            return redirect("/customers")
        rows = []
        for c in a.rows("SELECT * FROM customers ORDER BY name"):
            m = owed(c["id"])
            age = core.aged(m, today())
            rows.append({"c": c, "owed": core.customer_balance([(k, x) for _, k, x in m]), "oldest": max((d for d, _ in age), default=0)})
        return a.page("Customers", card("Add", form(a, "/customers", [("name", "Name"), ("phone", "Phone")], "Add")) + card("Record a payment", form(a, "/customers", [("pay", "Customer", "select", [(r["c"]["id"], r["c"]["name"]) for r in rows]), ("amount", "Amount")], "Save")) + card("Balances", table(sorted(rows, key=lambda r: -r["owed"]), [("Customer", lambda r: r["c"]["name"]), ("Owes", lambda r: money(r["owed"])), ("Oldest unpaid", lambda r: f"{r['oldest']} days" if r["owed"] else "")], "No customers yet.")))

    return a
