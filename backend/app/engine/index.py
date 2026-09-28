"""Lookup helpers over a parsed schema."""
from __future__ import annotations

from app.engine.generators import REGISTRY, Generator
from app.engine.schema import ColumnSpec, SchemaSpec, TableSpec


class SchemaIndex:
    def __init__(self, schema: SchemaSpec):
        self.schema = schema
        self.tables: dict[str, TableSpec] = {t.name: t for t in schema.tables}
        self._generators: dict[tuple, Generator] = {}

    def column(self, table: str, name: str) -> ColumnSpec | None:
        t = self.tables.get(table)
        return next((c for c in t.columns if c.name == name), None) if t else None

    def pk(self, table: str) -> str | None:
        return next((c.name for c in self.tables[table].columns if c.type == "id"), None)

    def fk_target(self, table: str, column: str) -> str | None:
        c = self.column(table, column)
        if c is None or c.type != "fk" or not isinstance(c.params.get("ref"), str):
            return None
        return c.params["ref"].split(".")[0]

    def generator(self, table: str, column: str) -> Generator:
        key = (table, column)
        if key not in self._generators:
            spec = self.tables[table]
            col = self.column(table, column)
            self._generators[key] = REGISTRY[col.type](col, spec)
        return self._generators[key]
