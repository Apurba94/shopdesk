"""Shop rules. Money is whole paisa. Cost of goods uses the weighted average method, so profit stays
right when the buying price changes between purchases."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class ShopError(Exception):
    pass


def to_paisa(text):
    try:
        d = Decimal(str(text).replace(",", "").strip())
    except InvalidOperation:
        raise ShopError(f"not an amount: {text}") from None
    if not d.is_finite() or d < 0:
        raise ShopError(f"not an amount: {text}")
    return int((d * 100).to_integral_value())


def money(p):
    sign = "-" if p < 0 else ""
    p = abs(p)
    return f"{sign}{p // 100:,}.{p % 100:02d}"


@dataclass
class Product:
    id: int
    name: str
    price: int
    cost: int = 0          # weighted average cost per unit, in paisa
    stock: float = 0
    reorder: float = 0


def buy(p, qty, unit_cost):
    """New stock changes the average cost: (old value + new value) / new quantity."""
    if qty <= 0:
        raise ShopError("quantity must be above zero")
    value = p.cost * p.stock + unit_cost * qty
    total = p.stock + qty
    return Product(p.id, p.name, p.price, round(value / total), total, p.reorder)


def bill(lines, discount=0, tax_rate=0.0):
    """lines: [(product, quantity)]. Returns the totals. Tax is added after the discount."""
    if not lines:
        raise ShopError("the bill is empty")
    subtotal = 0
    rows = []
    for p, q in lines:
        if q <= 0:
            raise ShopError(f"{p.name}: quantity must be above zero")
        if q > p.stock + 1e-9:
            raise ShopError(f"{p.name}: only {p.stock:g} in stock")
        amount = round(p.price * q)
        subtotal += amount
        rows.append((p, q, amount))
    if discount < 0 or discount > subtotal:
        raise ShopError("the discount cannot be more than the bill")
    taxable = subtotal - discount
    tax = round(taxable * tax_rate)
    return {"rows": rows, "subtotal": subtotal, "discount": discount, "tax": tax, "total": taxable + tax}


def bill_profit(rows, discount):
    """Profit on a bill, after sharing out the discount."""
    return sum(a - round(p.cost * q) for p, q, a in rows) - discount


def margin(p):
    return (p.price - p.cost) / p.price if p.price else 0.0


def price_warnings(p):
    out = []
    if p.cost and p.price < p.cost:
        out.append(f"selling below cost by {money(p.cost - p.price)}")
    elif p.cost and margin(p) < 0.05:
        out.append(f"margin is only {margin(p):.1%}")
    return out


def customer_balance(moves):
    """Credit sales (baki): moves are (kind, amount), with kind sale or payment. Returns what is owed."""
    return sum(a if k == "sale" else -a for k, a in moves)


def aged(moves, today):
    """How old an unpaid balance is. Payments clear the oldest sales first.
    moves: (date, kind, amount). Returns [(days old, unpaid amount)]."""
    sales = [[d, a] for d, k, a in sorted(moves, key=lambda m: m[0]) if k == "sale"]
    paid = sum(a for _, k, a in moves if k == "payment")
    out = []
    for d, a in sales:
        use = min(paid, a)
        paid -= use
        if a - use:
            out.append(((today - d).days, a - use))
    return out


def reorder_list(products, sold_per_day, lead_days=7):
    """Products to buy, most urgent first. A product selling fast is flagged sooner."""
    rows = []
    for p in products:
        rate = sold_per_day.get(p.id, 0.0)
        cover = p.stock / rate if rate > 0 else None
        if p.stock <= p.reorder or (cover is not None and cover <= lead_days):
            rows.append((p, cover, max(0, round(rate * lead_days * 3 - p.stock))))
    return sorted(rows, key=lambda r: (r[1] is None, r[1] or 0))


def slow_stock(products, last_sold, today, days=90):
    """Money tied up in goods that are not selling. last_sold: {id: date}."""
    rows = []
    for p in products:
        d = last_sold.get(p.id)
        if p.stock > 0 and (d is None or (today - d).days > days):
            rows.append((p, None if d is None else (today - d).days, round(p.cost * p.stock)))
    return sorted(rows, key=lambda r: -r[2])
