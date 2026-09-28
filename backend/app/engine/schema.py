"""Schema config: the YAML/JSON a user writes to describe a synthetic company."""
from __future__ import annotations

import re

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


class SchemaError(ValueError):
    """Raised with *all* problems found, so the UI can show them together."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


class ColumnSpec(BaseModel):
    # Type-specific options (min, max, ref, ...) are kept as extras and validated per type.
    model_config = ConfigDict(extra="allow")

    name: str
    type: str
    null_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    unique: bool = False

    @property
    def params(self) -> dict:
        return dict(self.model_extra or {})


class TableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    rows: int = Field(ge=1)
    columns: list[ColumnSpec] = Field(min_length=1)


class SchemaSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "synthetic_company"
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    locale: str = "en_US"
    tables: list[TableSpec] = Field(min_length=1)


def parse_schema(text: str) -> SchemaSpec:
    if not text or not text.strip():
        raise SchemaError(["Schema is empty."])
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SchemaError([f"Invalid YAML: {exc}"])
    if not isinstance(raw, dict):
        raise SchemaError(["Schema must be a mapping with a 'tables' list."])
    try:
        return SchemaSpec.model_validate(raw)
    except ValidationError as exc:
        errors = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        raise SchemaError(errors)
