"""Optional demo feature: deliberately corrupt a few rows so the quality report has something to catch.

It proves the checks really detect problems instead of always printing green."""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.engine import Engine

from app.engine.index import SchemaIndex
from app.engine.schema import SchemaSpec

HOW_MANY = 3


def inject_defects(engine: Engine, schema: SchemaSpec, tables: dict, idx: SchemaIndex) -> list:
    done = []
    with engine.begin() as conn:
        fk_done = num_done = uniq_done = False
        for spec in schema.tables:
            t = tables[spec.name]
            pk = t.c[idx.pk(spec.name)]
            for col in spec.columns:
                c = t.c[col.name]
                target = None
                if col.type == "fk" and not fk_done:
                    target, value, label = c, 999_999_999, "orphan foreign key"
                    fk_done = True
                elif col.type in ("int", "float") and col.params["min"] >= 0 and not num_done:
                    target, value, label = c, -1, "value below allowed range"
                    num_done = True
                elif col.type == "email" and col.unique and not uniq_done and spec.rows > 1:
                    first = conn.execute(select(c).order_by(pk).limit(1)).scalar_one()
                    ids = [r[0] for r in conn.execute(select(pk).order_by(pk.desc()).limit(2)).all()]
                    conn.execute(update(t).where(pk.in_(ids)).values({col.name: first}))
                    done.append({"table": spec.name, "column": col.name, "defect": "duplicate value", "rows": len(ids)})
                    uniq_done = True
                if target is not None:
                    ids = [r[0] for r in conn.execute(select(pk).order_by(pk).limit(HOW_MANY)).all()]
                    conn.execute(update(t).where(pk.in_(ids)).values({col.name: value}))
                    done.append({"table": spec.name, "column": col.name, "defect": label, "rows": len(ids)})
    return done
