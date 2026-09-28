"""Validate a schema as a whole and decide the order tables must be generated in."""
from __future__ import annotations

from dataclasses import dataclass

from faker import Faker

from app.engine.generators import REGISTRY
from app.engine.index import SchemaIndex
from app.engine.schema import NAME_RE, SchemaError, SchemaSpec


@dataclass
class SchemaPlan:
    order: list
    edges: list  # {"from": child_table, "to": parent_table, "column": fk_column}
    index: SchemaIndex


def plan_schema(schema: SchemaSpec, max_rows_per_table: int = 200_000, max_total_rows: int = 500_000) -> SchemaPlan:
    errors: list[str] = []
    idx = SchemaIndex(schema)

    try:
        Faker(schema.locale)
    except Exception:
        errors.append(f"locale '{schema.locale}' is not supported by Faker (try en_US or en_IN)")

    seen_tables = set()
    for t in schema.tables:
        if not NAME_RE.match(t.name):
            errors.append(f"table '{t.name}': use lowercase letters, digits and underscores (max 40, start with a letter)")
        if t.name in seen_tables:
            errors.append(f"table '{t.name}' is defined twice")
        seen_tables.add(t.name)
        if t.rows > max_rows_per_table:
            errors.append(f"table '{t.name}': {t.rows} rows exceeds the limit of {max_rows_per_table}")
        names = set()
        for c in t.columns:
            if not NAME_RE.match(c.name):
                errors.append(f"{t.name}.{c.name}: use lowercase letters, digits and underscores")
            if c.name in names:
                errors.append(f"{t.name}.{c.name}: column defined twice")
            names.add(c.name)
            if c.type not in REGISTRY:
                errors.append(f"{t.name}.{c.name}: unknown type '{c.type}' (available: {', '.join(sorted(REGISTRY))})")
        ids = [c for c in t.columns if c.type == "id"]
        if len(ids) != 1:
            errors.append(f"table '{t.name}' needs exactly one column of type 'id' (found {len(ids)})")
        elif ids[0].params:
            errors.append(f"{t.name}.{ids[0].name}: type 'id' takes no options")
    if sum(t.rows for t in schema.tables) > max_total_rows:
        errors.append(f"total rows exceed the limit of {max_total_rows}")
    if errors:  # structural problems make deeper checks unreliable
        raise SchemaError(errors)

    for t in schema.tables:
        for c in t.columns:
            errors.extend(idx.generator(t.name, c.name).validate(idx))
    if errors:
        raise SchemaError(errors)

    edges = []
    for t in schema.tables:
        for c in t.columns:
            parent = idx.fk_target(t.name, c.name)
            if parent:
                edges.append({"from": t.name, "to": parent, "column": c.name})

    # Kahn's algorithm; ties broken by declaration order so the result is stable.
    declared = [t.name for t in schema.tables]
    deps = {n: {e["to"] for e in edges if e["from"] == n} for n in declared}
    order: list[str] = []
    remaining = list(declared)
    while remaining:
        ready = [n for n in remaining if deps[n] <= set(order)]
        if not ready:
            raise SchemaError([f"circular dependency between tables: {', '.join(remaining)}"])
        order.append(ready[0])
        remaining.remove(ready[0])
    return SchemaPlan(order=order, edges=edges, index=idx)
