import unittest
from datetime import date, timedelta

from shopdesk import core, create_app
from shopdesk.core import Product, ShopError, aged, bill, bill_profit, buy, customer_balance, margin, money, price_warnings, reorder_list, slow_stock, to_paisa

T = date(2026, 11, 2)
RICE = Product(1, "Rice", 7000, 6000, 100)


class TestMoney(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(to_paisa("1,250.50"), 125050)
        for bad in ("x", "-1", "NaN"):
            with self.assertRaises(ShopError):
                to_paisa(bad)

    def test_format(self):
        self.assertEqual(money(125050), "1,250.50")


class TestStock(unittest.TestCase):
    def test_weighted_average(self):
        p = buy(Product(1, "x", 0, 1000, 10), 10, 2000)
        self.assertEqual((p.cost, p.stock), (1500, 20))

    def test_first_purchase(self):
        self.assertEqual(buy(Product(1, "x", 0), 5, 300).cost, 300)

    def test_bad_quantity(self):
        with self.assertRaises(ShopError):
            buy(RICE, 0, 1)


class TestBill(unittest.TestCase):
    def test_totals(self):
        b = bill([(RICE, 2)], discount=1000)
        self.assertEqual((b["subtotal"], b["total"]), (14000, 13000))

    def test_loose_quantities(self):
        self.assertEqual(bill([(RICE, 1.5)])["total"], 10500)

    def test_tax_after_discount(self):
        self.assertEqual(bill([(RICE, 1)], 2000, 0.15)["total"], 5750)

    def test_refusals(self):
        for args in (([(RICE, 500)],), ([],), ([(RICE, 0)],), ([(RICE, 1)], 99999)):
            with self.assertRaises(ShopError):
                bill(*args)

    def test_profit(self):
        b = bill([(RICE, 2)], 500)
        self.assertEqual(bill_profit(b["rows"], 500), 1500)

    def test_margin_and_warnings(self):
        self.assertAlmostEqual(margin(RICE), 1 / 7)
        self.assertIn("below cost", price_warnings(Product(1, "x", 50, 100))[0])
        self.assertIn("only", price_warnings(Product(1, "x", 102, 100))[0])
        self.assertEqual(price_warnings(RICE), [])


class TestCredit(unittest.TestCase):
    def test_balance(self):
        self.assertEqual(customer_balance([("sale", 500), ("payment", 200), ("sale", 100)]), 400)

    def test_ageing_pays_the_oldest_first(self):
        m = [(T - timedelta(days=60), "sale", 500), (T - timedelta(days=10), "sale", 300), (T - timedelta(days=5), "payment", 600)]
        self.assertEqual(aged(m, T), [(10, 200)])


class TestPlanning(unittest.TestCase):
    def test_reorder_by_level_and_by_speed(self):
        a = Product(1, "low", 0, 0, 2, 5)
        b = Product(2, "fast", 0, 0, 20, 0)
        c = Product(3, "fine", 0, 0, 100, 5)
        rows = reorder_list([a, b, c], {2: 10.0, 3: 1.0})
        self.assertEqual([r[0].name for r in rows], ["fast", "low"])
        self.assertEqual(rows[0][2], 190)

    def test_slow_stock(self):
        a = Product(1, "old", 0, 100, 10)
        b = Product(2, "new", 0, 100, 10)
        rows = slow_stock([a, b], {1: T - timedelta(days=200), 2: T - timedelta(days=5)}, T)
        self.assertEqual([r[0].name for r in rows], ["old"])
        self.assertEqual(rows[0][2], 1000)


class TestApp(unittest.TestCase):
    def setUp(self):
        self.a = create_app(":memory:", lambda: T)
        self.a.post("/products", name="Rice", price="70", reorder=5)
        self.a.post("/products", buy=1, qty=20, unit_cost="60")
        self.a.post("/customers", name="Karim", phone="")

    def text(self, url="/"):
        return self.a.get(url).body.decode()

    def test_sale_updates_everything(self):
        r = self.a.post("/bill", q1=3, discount="10")
        self.assertEqual(r.status, 303)
        self.assertIn("200.00", self.text(r.headers["Location"]))
        self.assertEqual(self.a.one("SELECT stock FROM products"), 17)
        page = self.text()
        self.assertIn("200.00", page)
        self.assertIn("20.00", page)

    def test_over_selling_changes_nothing(self):
        self.assertEqual(self.a.post("/bill", q1=99).status, 400)
        self.assertEqual(self.a.one("SELECT stock FROM products"), 20)
        self.assertEqual(self.a.one("SELECT COUNT(*) FROM bills"), 0)

    def test_empty_bill(self):
        self.assertEqual(self.a.post("/bill").status, 400)

    def test_credit_flow(self):
        self.assertEqual(self.a.post("/bill", q1=1, credit=1).status, 400)
        self.a.post("/bill", q1=2, credit=1, customer=1)
        self.assertIn("140.00", self.text("/customers"))
        self.a.post("/customers", pay=1, amount="40")
        self.assertIn("100.00", self.text("/customers"))
        self.assertEqual(self.a.post("/customers", pay=1, amount="500").status, 400)

    def test_cash_sales_add_no_debt(self):
        self.a.post("/bill", q1=2, customer=1)
        self.assertIn("0.00", self.text("/customers"))

    def test_buy_soon_list(self):
        self.a.post("/bill", q1=16)
        self.assertIn("Rice", self.text().split("Buy soon")[1])

    def test_duplicate_product(self):
        self.assertEqual(self.a.post("/products", name="Rice", price="1").status, 409)


if __name__ == "__main__":
    unittest.main()
