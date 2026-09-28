"""Generate all rows in memory, parents first, deterministically from the seed."""
from __future__ import annotations

import hashlib
import random
from typing import Callable

from faker import Faker

from app.engine.generators import Runtime
from app.engine.planner import SchemaPlan
from app.engine.schema import SchemaError, SchemaSpec


def derive_seed(seed: int, table: str) -> int:
    """Each table gets its own random stream. Adding a table never changes the data of the others."""
    return int(hashlib.sha256(f"{seed}:{table}".encode()).hexdigest()[:12], 16)


def _make_unique(value, i: int, where: str):
    if isinstance(value, str):
        if "@" in value:
            local, domain = value.split("@", 1)
            return f"{local}{i}@{domain}"
        return f"{value}-{i}"
    raise SchemaError([f"{where}: cannot enforce 'unique' for this column type"])


def generate(schema: SchemaSpec, plan: SchemaPlan, on_table_done: Callable | None = None) -> dict:
    idx = plan.index
    tables: dict[str, list] = {}
    for name in plan.order:
        spec = idx.tables[name]
        derived = derive_seed(schema.seed, name)
        fake = Faker(schema.locale)
        fake.seed_instance(derived)
        rt = Runtime(rng=random.Random(derived), fake=fake, tables=tables, idx=idx)

        gens = [idx.generator(name, c.name) for c in spec.columns]
        for g in gens:
            g.prepare(rt, spec)
        seen = {g.col.name: set() for g in gens if g.col.unique}

        rows = []
        for i in range(spec.rows):
            row: dict = {}
            for g in gens:
                col = g.col
                if col.null_rate and col.type != "id" and rt.rng.random() < col.null_rate:
                    value = None
                else:
                    value = g.generate(rt, row, i)
                    if col.unique and value is not None:
                        for _ in range(25):
                            if value not in seen[col.name]:
                                break
                            value = g.generate(rt, row, i)
                        if value in seen[col.name]:
                            value = _make_unique(value, i, g.where)
                        seen[col.name].add(value)
                row[col.name] = value
            rows.append(row)
        tables[name] = rows
        if on_table_done:
            on_table_done(name, len(rows))
    return tables
