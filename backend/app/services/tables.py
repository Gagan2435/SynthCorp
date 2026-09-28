"""Turn a schema into real SQL tables, and load generated rows into them."""
from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, Table
from sqlalchemy.engine import Engine

from app.engine.index import SchemaIndex
from app.engine.schema import SchemaSpec


def build_tables(schema: SchemaSpec, idx: SchemaIndex, prefix: str = "") -> dict:
    """Build SQLAlchemy Table objects. `prefix` keeps every run's tables separate (r12_customers, ...).

    No FOREIGN KEY / UNIQUE constraints are created on purpose: the quality engine is what
    verifies integrity, so the dataset can be exported to systems that don't enforce them.
    """
    md = MetaData()
    tables = {}
    for t in schema.tables:
        cols = []
        for c in t.columns:
            if c.type == "id":
                cols.append(Column(c.name, Integer, primary_key=True, autoincrement=False))
            else:
                cols.append(Column(c.name, idx.generator(t.name, c.name).sql_type(idx), nullable=True, index=(c.type == "fk")))
        tables[t.name] = Table(prefix + t.name, md, *cols)
    return tables


def create_tables(engine: Engine, tables: dict) -> None:
    next(iter(tables.values())).metadata.create_all(engine)


def drop_tables(engine: Engine, tables: dict) -> None:
    next(iter(tables.values())).metadata.drop_all(engine)


def load_rows(engine: Engine, table: Table, rows: list, batch_size: int) -> None:
    """Batched executemany: far faster than one INSERT per row (PyMySQL rewrites it into multi-row INSERTs)."""
    for start in range(0, len(rows), batch_size):
        with engine.begin() as conn:
            conn.execute(table.insert(), rows[start : start + batch_size])
