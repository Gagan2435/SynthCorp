from collections import Counter
from pathlib import Path

from app.engine.generator import generate
from app.engine.planner import plan_schema
from app.engine.schema import parse_schema

TEMPLATES = Path(__file__).parent.parent / "app" / "templates"


def build(name, seed=None):
    schema = parse_schema((TEMPLATES / f"{name}.yaml").read_text())
    if seed is not None:
        schema.seed = seed
    return schema, generate(schema, plan_schema(schema))


def test_same_seed_gives_identical_data():
    _, a = build("saas", 11)
    _, b = build("saas", 11)
    assert a == b


def test_different_seed_changes_data():
    _, a = build("saas", 11)
    _, b = build("saas", 12)
    assert a["customers"] != b["customers"]


def test_adding_a_table_does_not_change_existing_tables():
    text = (TEMPLATES / "ecommerce.yaml").read_text()
    extra = text + "\n  - name: extra\n    rows: 3\n    columns:\n      - {name: id, type: id}\n"
    s1, s2 = parse_schema(text), parse_schema(extra)
    d1, d2 = generate(s1, plan_schema(s1)), generate(s2, plan_schema(s2))
    assert d1["orders"] == d2["orders"]


def test_row_counts_match_schema():
    schema, data = build("saas")
    for t in schema.tables:
        assert len(data[t.name]) == t.rows


def test_every_foreign_key_points_to_a_real_parent():
    _, data = build("saas")
    ids = {name: {r["id"] for r in rows} for name, rows in data.items()}
    assert all(r["customer_id"] in ids["customers"] for r in data["invoices"])
    assert all(r["customer_id"] in ids["customers"] for r in data["tickets"])
    assert all(r["plan_id"] in ids["plans"] for r in data["customers"])


def test_emails_are_unique():
    _, data = build("saas")
    emails = [r["email"] for r in data["customers"]]
    assert len(emails) == len(set(emails))


def test_one_to_one_uses_each_parent_once():
    _, data = build("saas")
    assert sorted(r["customer_id"] for r in data["subscriptions"]) == list(range(1, 1001))


def test_invoices_never_fall_after_churn():
    _, data = build("saas")
    customers = {c["id"]: c for c in data["customers"]}
    for inv in data["invoices"]:
        c = customers[inv["customer_id"]]
        assert inv["issued_on"] >= c["signup_date"]
        if c["churn_date"]:
            assert inv["issued_on"] <= c["churn_date"]


def test_invoice_amount_follows_customers_plan_price():
    _, data = build("saas")
    plans = {p["id"]: p["monthly_price"] for p in data["plans"]}
    customers = {c["id"]: c for c in data["customers"]}
    for inv in data["invoices"]:
        assert inv["amount"] == plans[customers[inv["customer_id"]]["plan_id"]]


def test_subscription_status_matches_churn():
    _, data = build("saas")
    customers = {c["id"]: c for c in data["customers"]}
    for s in data["subscriptions"]:
        churned = customers[s["customer_id"]]["churn_date"] is not None
        assert s["status"] == ("cancelled" if churned else "active")


def test_zipf_makes_some_customers_much_heavier_than_others():
    _, data = build("saas")
    counts = sorted(Counter(i["customer_id"] for i in data["invoices"]).values(), reverse=True)
    assert counts[0] > 20 * (sum(counts) / 1000)  # top customer >> average customer


def test_churned_customers_file_more_tickets():
    _, data = build("saas")
    churned = {c["id"] for c in data["customers"] if c["churn_date"]}
    per = Counter(t["customer_id"] for t in data["tickets"])
    avg_churned = sum(per[c] for c in churned) / len(churned)
    stayed = [c["id"] for c in data["customers"] if not c["churn_date"]]
    avg_stayed = sum(per[c] for c in stayed) / len(stayed)
    assert avg_churned > avg_stayed


def test_tickets_cluster_before_churn():
    _, data = build("saas")
    customers = {c["id"]: c for c in data["customers"]}
    near = total = 0
    for t in data["tickets"]:
        churn = customers[t["customer_id"]]["churn_date"]
        if churn:
            total += 1
            near += (churn - t["created_on"]).days <= 45
    assert near / total > 0.5


def test_seasonality_puts_more_signups_in_peak_months():
    _, data = build("saas")
    months = Counter(c["signup_date"].month for c in data["customers"])
    peak_avg = sum(months[m] for m in (1, 2, 9)) / 3
    other_avg = sum(v for m, v in months.items() if m not in (1, 2, 9)) / 9
    assert peak_avg > other_avg


def test_ecommerce_unit_price_matches_product():
    _, data = build("ecommerce")
    prices = {p["id"]: p["price"] for p in data["products"]}
    assert all(o["unit_price"] == prices[o["product_id"]] for o in data["orders"])
