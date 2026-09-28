"""Streaming exports (CSV per table, one SQL dump) and paged reads shared with the mock API."""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Iterator

from sqlalchemy import func, select
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from app.services.tables import build_tables

CHUNK = 5000


def keyset_chunks(engine: Engine, table, pk_name: str) -> Iterator[list]:
    """Read a table in id order, CHUNK rows at a time (keyset pagination stays fast on huge tables)."""
    pk = table.c[pk_name]
    last = 0
    while True:
        with engine.connect() as conn:
            rows = conn.execute(select(table).where(pk > last).order_by(pk).limit(CHUNK)).all()
        if not rows:
            return
        yield rows
        last = rows[-1]._mapping[pk_name]


def csv_stream(engine: Engine, table, pk_name: str) -> Iterator[str]:
    header = [c.name for c in table.columns]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    yield buf.getvalue()
    for rows in keyset_chunks(engine, table, pk_name):
        buf = io.StringIO()
        writer = csv.writer(buf)
        for r in rows:
            writer.writerow(["" if v is None else v for v in r])
        yield buf.getvalue()


def sql_literal(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, Decimal)):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    s = str(v).replace("\\", "\\\\").replace("'", "''")
    return f"'{s}'"


def sql_dump_stream(engine: Engine, schema, plan) -> Iterator[str]:
    """A MySQL-flavoured dump using the original (un-prefixed) table names."""
    tables = build_tables(schema, plan.index, prefix="")
    yield f"-- SynthCorp dump: {schema.name} (seed {schema.seed})\nSET FOREIGN_KEY_CHECKS=0;\n\n"
    for name in plan.order:
        t = tables[name]
        yield str(CreateTable(t).compile(dialect=mysql.dialect())).strip() + ";\n"
        for ix in t.indexes:
            yield str(CreateIndex(ix).compile(dialect=mysql.dialect())).strip() + ";\n"
        yield "\n"
    yield "SET FOREIGN_KEY_CHECKS=1;\n"


def sql_dump_data_stream(engine: Engine, schema, plan, live_tables: dict) -> Iterator[str]:
    yield from sql_dump_stream(engine, schema, plan)
    for name in plan.order:
        t = live_tables[name]
        cols = ", ".join(f"`{c.name}`" for c in t.columns)
        pk_name = plan.index.pk(name)
        for rows in keyset_chunks(engine, t, pk_name):
            for start in range(0, len(rows), 500):
                values = ",\n".join("(" + ", ".join(sql_literal(v) for v in r) + ")" for r in rows[start : start + 500])
                yield f"INSERT INTO `{name}` ({cols}) VALUES\n{values};\n"
        yield "\n"


def count_rows(engine: Engine, table, where=()) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table).where(*where)).scalar_one()
