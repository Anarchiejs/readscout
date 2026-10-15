"""Edit benchmark: local_edit on a small project written for readscout, judged by hidden checks the model never sees."""
import ast
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PRICING = '''from decimal import Decimal, ROUND_HALF_UP

VAT_RATES = {"standard": Decimal("0.20"), "reduced": Decimal("0.055"), "zero": Decimal("0")}


def round_money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calc_total(lines, vat="standard"):
    subtotal = sum(Decimal(str(l["price"])) * l["qty"] for l in lines)
    return round_money(subtotal * (1 + VAT_RATES[vat]))


def apply_discount(total, percent):
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    return round_money(Decimal(total) * (Decimal(100) - Decimal(percent)) / Decimal(100))


def format_price(amount):
    return f"{round_money(amount):.2f} EUR"
'''

CATALOG = '''import re
import unicodedata


def slugify(name):
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "item"


def paginate(items, page, per_page=10):
    if page < 1:
        raise ValueError("page starts at 1")
    start = page * per_page
    return items[start:start + per_page]


def search(items, query):
    q = query.lower().strip()
    return [i for i in items if q in i["name"].lower() or q in i.get("tags", "").lower()]
'''

CART = '''from shop.pricing import calc_total, apply_discount, format_price


class Cart:
    def __init__(self):
        self.lines = []

    def add(self, sku, price, qty=1):
        for line in self.lines:
            if line["sku"] == sku:
                line["qty"] += qty
                return
        self.lines.append({"sku": sku, "price": price, "qty": qty})

    def total(self, vat="standard", discount=0):
        total = calc_total(self.lines, vat)
        return apply_discount(total, discount) if discount else total

    def receipt(self):
        return "\\n".join(f"{l['sku']} x{l['qty']}" for l in self.lines) + f"\\nTOTAL {format_price(self.total())}"
'''

TESTS = '''import unittest
from decimal import Decimal

from shop.cart import Cart
from shop.catalog import search, slugify
from shop.pricing import apply_discount, round_money


class ShopTest(unittest.TestCase):
    def test_cart_total_with_vat(self):
        c = Cart()
        c.add("a", 10.0, 2)
        c.add("b", 5.5)
        self.assertEqual(c.total(), Decimal("30.60"))
        self.assertEqual(c.total(vat="zero"), Decimal("25.50"))

    def test_cart_merges_lines_and_discount(self):
        c = Cart()
        c.add("a", 10.0)
        c.add("a", 10.0)
        self.assertEqual(len(c.lines), 1)
        self.assertEqual(c.total(discount=10), Decimal("21.60"))

    def test_round_and_discount_bounds(self):
        self.assertEqual(round_money("2.345"), Decimal("2.35"))
        with self.assertRaises(ValueError):
            apply_discount(10, 101)

    def test_slugify_and_search(self):
        self.assertEqual(slugify("Creme Brulee!"), "creme-brulee")
        self.assertTrue(search([{"name": "Red Shoe", "tags": "summer"}], "SUMMER"))


if __name__ == "__main__":
    unittest.main()
'''

FILES = {'shop/__init__.py': '', 'shop/pricing.py': PRICING, 'shop/catalog.py': CATALOG, 'shop/cart.py': CART,
         'tests/__init__.py': '', 'tests/test_shop.py': TESTS}
GATE = [[sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.']]


def _make(root: Path):
    for rel, text in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')


def _py(root, code) -> bool:
    return subprocess.run([sys.executable, '-c', code], cwd=root, capture_output=True, timeout=60, stdin=subprocess.DEVNULL).returncode == 0


def _tests_pass(root) -> bool:
    return subprocess.run(GATE[0], cwd=root, capture_output=True, timeout=120, stdin=subprocess.DEVNULL).returncode == 0


def _strip_docstrings(src):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)) and node.body and isinstance(node.body[0], ast.Expr) \
                and isinstance(getattr(node.body[0], 'value', None), ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.dump(tree)


def _docstrings(root):
    src = (root / 'shop/pricing.py').read_text()
    fns = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)]
    return all(ast.get_docstring(f) for f in fns) and _strip_docstrings(src) == _strip_docstrings(PRICING)


def _hints(root):
    tree = ast.parse((root / 'shop/catalog.py').read_text())
    fns = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    return _tests_pass(root) and all(f.returns is not None and all(a.annotation is not None for a in f.args.args) for f in fns)


def _written_tests(root) -> float:
    """Share of mutants killed; 0 if the new tests fail on the original code or the source was touched."""
    t = root / 'tests/test_catalog.py'
    src_path = root / 'shop/catalog.py'
    if not t.exists() or src_path.read_text() != CATALOG or not _tests_pass(root):
        return 0.0
    mutants = [('or "item"', 'or ""'), ('.strip("-").lower()', '.strip("-")'), ('q in i["name"].lower() or ', ''),
               ('"ignore"', '"replace"'), ('.lower().strip()', '.strip()')]
    killed = 0
    for a, b in mutants:
        src_path.write_text(CATALOG.replace(a, b, 1))
        killed += not _tests_pass(root)
    src_path.write_text(CATALOG)
    return killed / len(mutants)


TASKS = [
    ('fix_paginate', ['shop/catalog.py'],
     'paginate() returns the wrong page: page 1 must return the first per_page items (pages start at 1). Fix it.',
     lambda r: _py(r, 'from shop.catalog import paginate as p; L=list(range(25)); assert p(L,1)==L[:10] and p(L,3)==L[20:] and p(L,2,5)==L[5:10]')),
    ('docstrings', ['shop/pricing.py'], 'Add a concise one-line docstring to every function in this file. Change nothing else.', _docstrings),
    ('rename', ['shop/pricing.py', 'shop/cart.py'],
     'Rename the function calc_total to compute_total everywhere: its definition and every import and call.',
     lambda r: _tests_pass(r) and all('calc_total' not in (r / f).read_text() for f in ['shop/pricing.py', 'shop/cart.py'])),
    ('add_param', ['shop/pricing.py'],
     "Add an optional parameter currency='EUR' to format_price. The output ends with that currency code instead of the "
     "hard-coded EUR, e.g. format_price(3, 'USD') == '3.00 USD'.",
     lambda r: _tests_pass(r) and _py(r, "from shop.pricing import format_price as f; assert f(3,'USD')=='3.00 USD' and f(2.5)=='2.50 EUR'")),
    ('type_hints', ['shop/catalog.py'], 'Add type hints to every parameter and return value of every function in this file. Do not change behaviour.', _hints),
    ('cart_remove', ['shop/cart.py'],
     'Add a method Cart.remove(self, sku, qty=1): it decreases the quantity of that line, deletes the line when the quantity '
     'reaches 0 or less, and raises KeyError if the sku is not in the cart.',
     lambda r: _tests_pass(r) and _py(r, "from shop.cart import Cart\nc=Cart(); c.add('a',1,3); c.remove('a'); assert c.lines[0]['qty']==2\n"
                                         "c.remove('a',5); assert c.lines==[]\ntry:\n c.remove('zz'); raise SystemExit(1)\nexcept KeyError: pass")),
    ('write_tests', ['tests/test_catalog.py', 'shop/catalog.py'],
     'Create the new file tests/test_catalog.py with unittest tests for slugify and search from shop/catalog.py: accents, '
     'punctuation and spaces, the "item" fallback for empty names, case-insensitive name search, tag search, no match. '
     'Do NOT modify shop/catalog.py.', _written_tests),
]


def run(model, edit_fn) -> list[dict]:
    """edit_fn(paths, instruction, gate, model, roots) -> receipt string (readscout.editing.edit)."""
    rows = []
    for name, paths, instruction, check in TASKS:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'shop-project'
            _make(root)
            t = time.time()
            try:
                receipt = edit_fn(paths, instruction, GATE, model=model, roots=[root], timeout=600)
            except Exception as e:  # noqa: BLE001 - a crash is a failed task
                receipt = f'CRASH {e}'
            status = receipt.split(' ', 1)[0]
            score = float(check(root)) if status == 'APPLIED' else 0.0
            rows.append({'task': name, 'status': status, 'score': score, 'seconds': round(time.time() - t, 1)})
    return rows
