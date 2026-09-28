"""Data-quality checks. They run as SQL against the loaded tables, not against the Python objects,
so they verify what was actually stored (and would catch a bug in loading, too)."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from app.engine.generators import to_date
from app.engine.index import SchemaIndex
from app.engine.schema import SchemaSpec

SAMPLE_SIZE = 5


def _result(kind, table, column, description, failed, samples=None, expected=None):
    return {
        "kind": kind,
        "table": table,
        "column": column,
        "description": description,
        "status": "pass" if failed == 0 else "fail",
        "failed": failed,
        "samples": samples or [],
    }


def _count(conn: Connection, from_clause, *conditions) -> int:
    return conn.execute(select(func.count()).select_from(from_clause).where(*conditions)).scalar_one()


def _samples(conn: Connection, pk_col, from_clause, *conditions) -> list:
    rows = conn.execute(select(pk_col).select_from(from_clause).where(*conditions).limit(SAMPLE_SIZE)).all()
    return [r[0] for r in rows]


def _violation(conn, kind, tname, cname, description, pk_col, from_clause, *conditions):
    failed = _count(conn, from_clause, *conditions)
    samples = _samples(conn, pk_col, from_clause, *conditions) if failed else []
    return _result(kind, tname, cname, description, failed, samples)


def run_checks(conn: Connection, schema: SchemaSpec, tables: dict, idx: SchemaIndex) -> dict:
    results = []
    for spec in schema.tables:
        t = tables[spec.name]
        pk = t.c[idx.pk(spec.name)]

        actual = conn.execute(select(func.count()).select_from(t)).scalar_one()
        results.append(_result("row_count", spec.name, None, f"{spec.name} has {spec.rows} rows", 0 if actual == spec.rows else abs(actual - spec.rows)))

        for col in spec.columns:
            g = idx.generator(spec.name, col.name)
            c = t.c[col.name]
            p = col.params

            # Not-null: only for columns that can never legitimately be empty.
            if col.type != "id" and not col.null_rate and not g.may_be_null():
                results.append(_violation(conn, "not_null", spec.name, col.name, f"{spec.name}.{col.name} has no empty values", pk, t, c.is_(None)))

            if col.unique:
                dup = select(c).where(c.is_not(None)).group_by(c).having(func.count() > 1)
                failed = conn.execute(select(func.count()).select_from(dup.subquery())).scalar_one()
                samples = [r[0] for r in conn.execute(dup.limit(SAMPLE_SIZE)).all()] if failed else []
                results.append(_result("unique", spec.name, col.name, f"{spec.name}.{col.name} values are unique", failed, samples))

            if col.type == "fk":
                parent_name, parent_col = p["ref"].split(".")
                parent = tables[parent_name]
                joined = t.outerjoin(parent, c == parent.c[parent_col])
                results.append(
                    _violation(conn, "fk_integrity", spec.name, col.name, f"every {spec.name}.{col.name} points to an existing {parent_name}.{parent_col}", pk, joined, c.is_not(None), parent.c[parent_col].is_(None))
                )

            if col.type in ("int", "float"):
                results.append(_violation(conn, "range", spec.name, col.name, f"{spec.name}.{col.name} is between {p['min']} and {p['max']}", pk, t, c.is_not(None), (c < p["min"]) | (c > p["max"])))

            if col.type == "date":
                lo, hi = to_date(p["start"], ""), to_date(p["end"], "")
                results.append(_violation(conn, "range", spec.name, col.name, f"{spec.name}.{col.name} is between {lo} and {hi}", pk, t, c.is_not(None), (c < lo) | (c > hi)))

            if col.type in ("choice",):
                results.append(_violation(conn, "allowed_values", spec.name, col.name, f"{spec.name}.{col.name} only has expected values", pk, t, c.is_not(None), c.not_in(p["values"])))

            if col.type == "date_after":
                base = t.c[p["after"]]
                results.append(_violation(conn, "date_order", spec.name, col.name, f"{spec.name}.{col.name} is not before {p['after']}", pk, t, c.is_not(None), base.is_not(None), c < base))

            if col.type == "date_from_parent":
                parent_name = idx.fk_target(spec.name, p["fk"])
                parent = tables[parent_name]
                joined = t.join(parent, t.c[p["fk"]] == parent.c[idx.pk(parent_name)])
                results.append(
                    _violation(conn, "date_order", spec.name, col.name, f"{spec.name}.{col.name} is not before {parent_name}.{p['parent_column']}", pk, joined, c.is_not(None), parent.c[p["parent_column"]].is_not(None), c < parent.c[p["parent_column"]])
                )
                if "until_column" in p:
                    results.append(
                        _violation(conn, "date_order", spec.name, col.name, f"{spec.name}.{col.name} is not after {parent_name}.{p['until_column']}", pk, joined, c.is_not(None), parent.c[p["until_column"]].is_not(None), c > parent.c[p["until_column"]])
                    )

    failed = [r for r in results if r["status"] == "fail"]
    return {
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "checks": results,
    }
