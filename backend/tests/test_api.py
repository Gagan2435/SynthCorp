import csv
import io


def create(client, yaml_text, **extra):
    r = client.post("/api/runs", json={"config_yaml": yaml_text, **extra})
    assert r.status_code == 202, r.text
    return r.json()["id"]


def test_templates_and_validate(client, saas_yaml):
    assert {t["id"] for t in client.get("/api/templates").json()} == {"saas", "ecommerce"}
    ok = client.post("/api/schema/validate", json={"config_yaml": saas_yaml}).json()
    assert ok["valid"] and ok["plan"]["order"][0] == "plans"
    bad = client.post("/api/schema/validate", json={"config_yaml": "tables: []"}).json()
    assert not bad["valid"] and bad["errors"]


def test_invalid_schema_is_rejected_with_details(client):
    r = client.post("/api/runs", json={"config_yaml": "tables:\n  - name: t\n    rows: 1\n    columns:\n      - {name: a, type: nope}\n"})
    assert r.status_code == 422
    assert "unknown type" in r.json()["detail"]["errors"][0]


def test_full_run_passes_every_quality_check(client, saas_yaml):
    run_id = create(client, saas_yaml)
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["status"] == "done", run
    assert run["table_counts"]["invoices"] == 8000
    q = client.get(f"/api/runs/{run_id}/quality").json()
    assert q["failed"] == 0 and q["total"] > 20
    assert client.get("/api/runs").json()[0]["id"] == run_id


def test_injected_defects_are_caught(client, saas_yaml):
    run_id = create(client, saas_yaml, inject_defects=True)
    q = client.get(f"/api/runs/{run_id}/quality").json()
    failed = {(c["table"], c["column"], c["kind"]) for c in q["checks"] if c["status"] == "fail"}
    assert ("customers", "email", "unique") in failed
    assert any(k == "fk_integrity" for _, _, k in failed)
    assert q["injected_defects"]
    orphan = next(c for c in q["checks"] if c["kind"] == "fk_integrity" and c["status"] == "fail")
    assert orphan["failed"] == 3 and len(orphan["samples"]) == 3


def test_seed_override_is_reproducible(client, saas_yaml):
    a, b = create(client, saas_yaml, seed=5), create(client, saas_yaml, seed=5)
    rows = lambda rid: client.get(f"/api/runs/{rid}/tables/customers?limit=50").json()["rows"]
    assert rows(a) == rows(b)
    c = create(client, saas_yaml, seed=6)
    assert rows(a) != rows(c)


def test_preview_paging(client, saas_yaml):
    run_id = create(client, saas_yaml)
    page = client.get(f"/api/runs/{run_id}/tables/customers?limit=10&offset=20").json()
    assert page["total"] == 1000 and [r["id"] for r in page["rows"]] == list(range(21, 31))
    assert client.get(f"/api/runs/{run_id}/tables/ghosts").status_code == 404


def test_csv_export(client, saas_yaml):
    run_id = create(client, saas_yaml)
    r = client.get(f"/api/runs/{run_id}/tables/plans/csv")
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["id", "name", "monthly_price"] and len(rows) == 5


def test_sql_dump_contains_schema_and_data(client, saas_yaml):
    run_id = create(client, saas_yaml)
    text = client.get(f"/api/runs/{run_id}/dump.sql").text
    assert "CREATE TABLE customers" in text and "INSERT INTO `plans`" in text
    assert text.count("INSERT INTO `invoices`") >= 16  # 8000 rows in batches of 500


def test_mock_api(client, saas_yaml):
    run_id = create(client, saas_yaml)
    index = client.get(f"/api/mock/{run_id}").json()
    assert {t["name"] for t in index["tables"]} >= {"customers", "invoices"}
    page = client.get(f"/api/mock/{run_id}/invoices?customer_id=1&limit=100").json()
    assert page["total"] == len(page["items"]) or page["total"] > 100
    assert all(i["customer_id"] == 1 for i in page["items"])
    assert client.get(f"/api/mock/{run_id}/customers/1").json()["id"] == 1
    assert client.get(f"/api/mock/{run_id}/customers/999999").status_code == 404
    assert client.get(f"/api/mock/{run_id}/customers?nope=1").status_code == 400


def test_delete_run_drops_its_tables(client, saas_yaml):
    from sqlalchemy import inspect

    from app.db import engine

    run_id = create(client, saas_yaml)
    assert f"r{run_id}_customers" in inspect(engine).get_table_names()
    assert client.delete(f"/api/runs/{run_id}").status_code == 204
    assert f"r{run_id}_customers" not in inspect(engine).get_table_names()
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_run_isolation(client, saas_yaml):
    a, b = create(client, saas_yaml), create(client, saas_yaml, seed=3)
    assert client.get(f"/api/runs/{a}/tables/customers").json()["total"] == 1000
    assert client.get(f"/api/runs/{b}/tables/customers").json()["total"] == 1000
