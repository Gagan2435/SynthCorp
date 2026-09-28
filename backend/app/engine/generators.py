"""Column generators.

Each column `type` in the schema maps to one Generator class. A generator can:
  * validate its own options against the rest of the schema   (validate/check)
  * say which SQL type its values need                        (sql_type)
  * generate one value for one row, seeing the row so far     (generate)

Because tables are generated parents-first, a generator can look up values in
already-generated parent tables (that is how lookups and churn-aware dates work).
"""
from __future__ import annotations

import itertools
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, Date, Integer, Numeric, String, Text

if TYPE_CHECKING:  # pragma: no cover
    from faker import Faker

    from app.engine.index import SchemaIndex
    from app.engine.schema import ColumnSpec, TableSpec

REGISTRY: dict[str, type["Generator"]] = {}


def register(cls):
    REGISTRY[cls.type_name] = cls
    return cls


@dataclass
class Runtime:
    rng: random.Random
    fake: "Faker"
    tables: dict  # table name -> list of row dicts (parents are complete before children run)
    idx: "SchemaIndex"


def to_date(value: Any, label: str) -> date:
    if isinstance(value, datetime):  # datetime is a subclass of date, check it first
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError(f"{label} must be a date like 2024-01-31")


def is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def infer_values_type(values: list):
    if all(isinstance(v, bool) for v in values):
        return Boolean()
    if all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        return Integer()
    if all(is_number(v) for v in values):
        return Numeric(14, 2)
    return String(max(16, min(255, max(len(str(v)) for v in values))))


class Generator:
    type_name = ""
    required: set = set()
    optional: set = set()
    produces = ""  # "date" for generators that output dates

    def __init__(self, col: "ColumnSpec", table: "TableSpec"):
        self.col = col
        self.table = table
        self.p = col.params

    @property
    def where(self) -> str:
        return f"{self.table.name}.{self.col.name}"

    # ---- validation -------------------------------------------------
    def validate(self, idx: "SchemaIndex") -> list:
        missing = self.required - self.p.keys()
        unknown = self.p.keys() - self.required - self.optional
        errors = []
        if missing:
            errors.append(f"{self.where}: type '{self.type_name}' needs option(s) {sorted(missing)}")
        if unknown:
            errors.append(
                f"{self.where}: unknown option(s) {sorted(unknown)} for type '{self.type_name}' "
                f"(allowed: {sorted(self.required | self.optional)})"
            )
        return errors or self.check(idx)

    def check(self, idx: "SchemaIndex") -> list:
        return []

    def prior_column_error(self, idx: "SchemaIndex", name: Any, want: str | None = None, want_date=False):
        """The option must name a column declared *earlier in this table* (so it already has a value)."""
        names = [c.name for c in self.table.columns]
        pos = names.index(self.col.name)
        if not isinstance(name, str) or name not in names[:pos]:
            return f"{self.where}: '{name}' must be a column declared earlier in table '{self.table.name}'"
        if want and idx.column(self.table.name, name).type != want:
            return f"{self.where}: '{name}' must be a '{want}' column"
        if want_date and not idx.generator(self.table.name, name).produces == "date":
            return f"{self.where}: '{name}' must be a date column"
        return None

    def parent_column_error(self, idx: "SchemaIndex", fk_col: str, parent_col: Any, want_date=False):
        parent = idx.fk_target(self.table.name, fk_col)
        if parent is None or not isinstance(parent_col, str) or idx.column(parent, parent_col) is None:
            return f"{self.where}: column '{parent_col}' does not exist in the table referenced by '{fk_col}'"
        if want_date and idx.generator(parent, parent_col).produces != "date":
            return f"{self.where}: '{parent}.{parent_col}' must be a date column"
        return None

    def date_option_errors(self, *names):
        errors = []
        for n in names:
            if n in self.p:
                try:
                    to_date(self.p[n], f"{self.where}: '{n}'")
                except ValueError as exc:
                    errors.append(str(exc))
        return errors

    # ---- structure --------------------------------------------------
    def sql_type(self, idx: "SchemaIndex"):
        return String(255)

    def may_be_null(self) -> bool:
        """True if this generator can legitimately output NULL by itself (used by quality checks)."""
        return False

    # ---- generation -------------------------------------------------
    def prepare(self, rt: Runtime, spec: "TableSpec") -> None:
        pass

    def generate(self, rt: Runtime, row: dict, i: int) -> Any:
        raise NotImplementedError


# --------------------------------------------------------------------- simple values
@register
class IdGen(Generator):
    type_name = "id"

    def sql_type(self, idx):
        return Integer()

    def generate(self, rt, row, i):
        return i + 1  # ids are 1..N, which lets children find a parent row by index in O(1)


@register
class UuidGen(Generator):
    type_name = "uuid"

    def sql_type(self, idx):
        return String(36)

    def generate(self, rt, row, i):
        return str(uuid.UUID(int=rt.rng.getrandbits(128), version=4))


class _FakerGen(Generator):
    method = ""

    def generate(self, rt, row, i):
        return getattr(rt.fake, self.method)()


def _faker_type(name, method):
    return register(type(f"{name.title()}Gen", (_FakerGen,), {"type_name": name, "method": method}))


for _n, _m in [
    ("person_name", "name"),
    ("email", "email"),
    ("company", "company"),
    ("phone", "phone_number"),
    ("city", "city"),
]:
    _faker_type(_n, _m)


@register
class TextGen(Generator):
    type_name = "text"
    optional = {"words"}

    def check(self, idx):
        w = self.p.get("words", 8)
        return [] if isinstance(w, int) and 1 <= w <= 200 else [f"{self.where}: 'words' must be 1-200"]

    def sql_type(self, idx):
        return Text()

    def generate(self, rt, row, i):
        return rt.fake.sentence(nb_words=self.p.get("words", 8))


@register
class ChoiceGen(Generator):
    type_name = "choice"
    required = {"values"}
    optional = {"weights"}

    def check(self, idx):
        v, w = self.p["values"], self.p.get("weights")
        if not isinstance(v, list) or not v:
            return [f"{self.where}: 'values' must be a non-empty list"]
        if w is not None and (not isinstance(w, list) or len(w) != len(v) or not all(is_number(x) and x >= 0 for x in w) or sum(w) <= 0):
            return [f"{self.where}: 'weights' must be non-negative numbers, one per value"]
        return []

    def sql_type(self, idx):
        return infer_values_type(self.p["values"])

    def prepare(self, rt, spec):
        self.values = [Decimal(str(v)) if isinstance(v, float) else v for v in self.p["values"]]
        w = self.p.get("weights")
        self.cum = list(itertools.accumulate(w)) if w else None

    def generate(self, rt, row, i):
        return rt.rng.choices(self.values, cum_weights=self.cum)[0]


@register
class CycleGen(Generator):
    type_name = "cycle"
    required = {"values"}

    def check(self, idx):
        v = self.p["values"]
        return [] if isinstance(v, list) and v else [f"{self.where}: 'values' must be a non-empty list"]

    def sql_type(self, idx):
        return infer_values_type(self.p["values"])

    def prepare(self, rt, spec):
        self.values = [Decimal(str(v)) if isinstance(v, float) else v for v in self.p["values"]]

    def generate(self, rt, row, i):
        return self.values[i % len(self.values)]


@register
class IntGen(Generator):
    type_name = "int"
    required = {"min", "max"}

    def check(self, idx):
        lo, hi = self.p["min"], self.p["max"]
        if not (isinstance(lo, int) and isinstance(hi, int) and not isinstance(lo, bool) and lo <= hi):
            return [f"{self.where}: 'min' and 'max' must be integers with min <= max"]
        return []

    def sql_type(self, idx):
        big = max(abs(self.p["min"]), abs(self.p["max"])) > 2**31 - 1
        return BigInteger() if big else Integer()

    def generate(self, rt, row, i):
        return rt.rng.randint(self.p["min"], self.p["max"])


@register
class FloatGen(Generator):
    type_name = "float"
    required = {"min", "max"}
    optional = {"decimals"}

    def check(self, idx):
        lo, hi, d = self.p["min"], self.p["max"], self.p.get("decimals", 2)
        if not (is_number(lo) and is_number(hi) and lo <= hi):
            return [f"{self.where}: 'min' and 'max' must be numbers with min <= max"]
        if not (isinstance(d, int) and 0 <= d <= 6) or max(abs(lo), abs(hi)) >= 10 ** (14 - d):
            return [f"{self.where}: 'decimals' must be 0-6 and the range must fit in 14 digits"]
        return []

    def sql_type(self, idx):
        return Numeric(14, self.p.get("decimals", 2))

    def generate(self, rt, row, i):
        d = self.p.get("decimals", 2)
        return Decimal(f"{rt.rng.uniform(self.p['min'], self.p['max']):.{d}f}")


@register
class BoolGen(Generator):
    type_name = "bool"
    optional = {"p"}

    def check(self, idx):
        p = self.p.get("p", 0.5)
        return [] if is_number(p) and 0 <= p <= 1 else [f"{self.where}: 'p' must be between 0 and 1"]

    def sql_type(self, idx):
        return Boolean()

    def generate(self, rt, row, i):
        return rt.rng.random() < self.p.get("p", 0.5)


# --------------------------------------------------------------------- dates
@register
class DateGen(Generator):
    type_name = "date"
    required = {"start", "end"}
    optional = {"seasonality"}
    produces = "date"

    def check(self, idx):
        errors = self.date_option_errors("start", "end")
        if errors:
            return errors
        if to_date(self.p["start"], "") > to_date(self.p["end"], ""):
            return [f"{self.where}: 'start' must not be after 'end'"]
        s = self.p.get("seasonality")
        if s is not None:
            months = s.get("peak_months") if isinstance(s, dict) else None
            strength = s.get("strength", 0.5) if isinstance(s, dict) else None
            if not (isinstance(months, list) and months and all(isinstance(m, int) and 1 <= m <= 12 for m in months) and is_number(strength) and strength >= 0):
                return [f"{self.where}: 'seasonality' needs peak_months (1-12) and strength >= 0"]
        return []

    def sql_type(self, idx):
        return Date()

    def prepare(self, rt, spec):
        start, end = to_date(self.p["start"], ""), to_date(self.p["end"], "")
        self.days = [start + timedelta(days=d) for d in range((end - start).days + 1)]
        s = self.p.get("seasonality")
        if s:
            months, strength = set(s["peak_months"]), s.get("strength", 0.5)
            weights = [1 + strength if d.month in months else 1 for d in self.days]
            self.cum = list(itertools.accumulate(weights))
        else:
            self.cum = None

    def generate(self, rt, row, i):
        return rt.rng.choices(self.days, cum_weights=self.cum)[0]


@register
class DateAfterGen(Generator):
    type_name = "date_after"
    required = {"after", "max_days"}
    optional = {"min_days", "max_date"}
    produces = "date"

    def check(self, idx):
        err = self.prior_column_error(idx, self.p["after"], want_date=True)
        lo, hi = self.p.get("min_days", 0), self.p["max_days"]
        if err:
            return [err]
        if not (isinstance(lo, int) and isinstance(hi, int) and 0 <= lo <= hi):
            return [f"{self.where}: 'min_days' <= 'max_days' must be non-negative integers"]
        return self.date_option_errors("max_date")

    def sql_type(self, idx):
        return Date()

    def may_be_null(self):
        return True  # NULL when the base is NULL or the result would pass max_date (e.g. "not churned yet")

    def generate(self, rt, row, i):
        base = row[self.p["after"]]
        if base is None:
            return None
        d = base + timedelta(days=rt.rng.randint(self.p.get("min_days", 0), self.p["max_days"]))
        cap = self.p.get("max_date")
        if cap is not None and d > to_date(cap, ""):
            return None
        return d


@register
class DateFromParentGen(Generator):
    type_name = "date_from_parent"
    required = {"fk", "parent_column", "max_days"}
    optional = {"min_days", "until_column", "max_date"}
    produces = "date"

    def check(self, idx):
        err = self.prior_column_error(idx, self.p["fk"], want="fk")
        if err:
            return [err]
        err = self.parent_column_error(idx, self.p["fk"], self.p["parent_column"], want_date=True)
        if err:
            return [err]
        if "until_column" in self.p:
            err = self.parent_column_error(idx, self.p["fk"], self.p["until_column"], want_date=True)
            if err:
                return [err]
        lo, hi = self.p.get("min_days", 0), self.p["max_days"]
        if not (isinstance(lo, int) and isinstance(hi, int) and 0 <= lo <= hi):
            return [f"{self.where}: 'min_days' <= 'max_days' must be non-negative integers"]
        return self.date_option_errors("max_date")

    def sql_type(self, idx):
        return Date()

    def may_be_null(self):
        return True

    def prepare(self, rt, spec):
        self.parent = rt.idx.fk_target(spec.name, self.p["fk"])
        self.cap = to_date(self.p["max_date"], "") if "max_date" in self.p else None

    def generate(self, rt, row, i):
        fk = row[self.p["fk"]]
        if fk is None:
            return None
        parent = rt.tables[self.parent][fk - 1]
        base = parent[self.p["parent_column"]]
        if base is None:
            return None
        upper = self.cap
        until = parent.get(self.p["until_column"]) if "until_column" in self.p else None
        if until is not None and (upper is None or until < upper):
            upper = until
        d = base + timedelta(days=rt.rng.randint(self.p.get("min_days", 0), self.p["max_days"]))
        if upper is not None and d > upper:
            # Stay inside the parent's life: e.g. an invoice can't come after the customer churned.
            d = base + timedelta(days=rt.rng.randint(0, max((upper - base).days, 0)))
        return d


@register
class DateAroundEventGen(Generator):
    """A date that clusters just before a parent's event (e.g. support tickets spike before churn)."""

    type_name = "date_around_event"
    required = {"fk", "start_column", "event_column", "window_days", "probability", "max_date"}
    produces = "date"

    def check(self, idx):
        err = self.prior_column_error(idx, self.p["fk"], want="fk")
        if err:
            return [err]
        for key in ("start_column", "event_column"):
            err = self.parent_column_error(idx, self.p["fk"], self.p[key], want_date=True)
            if err:
                return [err]
        w, pr = self.p["window_days"], self.p["probability"]
        if not (isinstance(w, int) and w >= 0 and is_number(pr) and 0 <= pr <= 1):
            return [f"{self.where}: 'window_days' must be >= 0 and 'probability' between 0 and 1"]
        return self.date_option_errors("max_date")

    def sql_type(self, idx):
        return Date()

    def may_be_null(self):
        return True

    def prepare(self, rt, spec):
        self.parent = rt.idx.fk_target(spec.name, self.p["fk"])
        self.cap = to_date(self.p["max_date"], "")

    def generate(self, rt, row, i):
        fk = row[self.p["fk"]]
        if fk is None:
            return None
        parent = rt.tables[self.parent][fk - 1]
        start = parent[self.p["start_column"]]
        if start is None:
            return None
        event = parent[self.p["event_column"]]
        end = min(event, self.cap) if event is not None else self.cap
        if event is not None and rt.rng.random() < self.p["probability"]:
            d = event - timedelta(days=rt.rng.randint(0, self.p["window_days"]))
        else:
            d = start + timedelta(days=rt.rng.randint(0, max((end - start).days, 0)))
        return max(start, min(d, end)) if end >= start else start


# --------------------------------------------------------------------- relationships
@register
class FkGen(Generator):
    type_name = "fk"
    required = {"ref"}
    optional = {"distribution", "zipf_s", "boost"}

    def check(self, idx):
        ref = self.p["ref"]
        if not isinstance(ref, str) or ref.count(".") != 1:
            return [f"{self.where}: 'ref' must look like 'table.column'"]
        table, column = ref.split(".")
        if table not in idx.tables:
            return [f"{self.where}: references unknown table '{table}'"]
        if table == self.table.name:
            return [f"{self.where}: self-references are not supported"]
        if idx.pk(table) != column:
            return [f"{self.where}: '{ref}' is not the id column of '{table}' (it is '{idx.pk(table)}')"]
        dist = self.p.get("distribution", "uniform")
        if dist not in ("uniform", "zipf", "one_to_one"):
            return [f"{self.where}: 'distribution' must be uniform, zipf or one_to_one"]
        if not (is_number(self.p.get("zipf_s", 1.1)) and self.p.get("zipf_s", 1.1) > 0):
            return [f"{self.where}: 'zipf_s' must be > 0"]
        if dist == "one_to_one" and self.table.rows > idx.tables[table].rows:
            return [f"{self.where}: one_to_one needs rows <= {table} rows ({self.table.rows} > {idx.tables[table].rows})"]
        boost = self.p.get("boost")
        if boost is not None:
            if not (isinstance(boost, dict) and set(boost) == {"column", "factor"} and is_number(boost["factor"]) and boost["factor"] > 0):
                return [f"{self.where}: 'boost' needs 'column' and a positive 'factor'"]
            if idx.column(table, boost["column"]) is None:
                return [f"{self.where}: boost column '{boost['column']}' not found in '{table}'"]
            if dist == "one_to_one":
                return [f"{self.where}: 'boost' cannot be combined with one_to_one"]
        return []

    def sql_type(self, idx):
        return Integer()

    def prepare(self, rt, spec):
        parent = self.p["ref"].split(".")[0]
        parent_rows = rt.tables[parent]
        n = len(parent_rows)
        dist = self.p.get("distribution", "uniform")
        self.mode = dist
        if dist == "one_to_one":
            self.ids = list(range(1, n + 1))
            rt.rng.shuffle(self.ids)
            return
        boost = self.p.get("boost")
        if dist == "uniform" and not boost:
            self.n = n
            self.mode = "uniform"
            return
        # Weighted choice. Zipf: a few parents get most of the children (heavy users).
        ids = list(range(1, n + 1))
        rt.rng.shuffle(ids)  # which parents are "heavy" is random, not just the first ids
        s = self.p.get("zipf_s", 1.1)
        weights = [1.0 / ((rank + 1) ** s) if dist == "zipf" else 1.0 for rank in range(n)]
        if boost:
            for k, pid in enumerate(ids):
                if parent_rows[pid - 1][boost["column"]] is not None:
                    weights[k] *= boost["factor"]
        self.ids = ids
        self.cum = list(itertools.accumulate(weights))
        self.mode = "weighted"

    def generate(self, rt, row, i):
        if self.mode == "uniform":
            return rt.rng.randint(1, self.n)
        if self.mode == "one_to_one":
            return self.ids[i]
        return rt.rng.choices(self.ids, cum_weights=self.cum)[0]


@register
class LookupGen(Generator):
    """Copy a value by following foreign keys: path [customer_id, plan_id, monthly_price]."""

    type_name = "lookup"
    required = {"path"}
    produces = ""

    def _steps(self, idx):
        """Return (tables_visited, error)."""
        path = self.p["path"]
        if not (isinstance(path, list) and len(path) >= 2 and all(isinstance(s, str) for s in path)):
            return None, f"{self.where}: 'path' must be a list like [fk_column, column, ...]"
        err = self.prior_column_error(idx, path[0], want="fk")
        if err:
            return None, err
        table = idx.fk_target(self.table.name, path[0])
        visited = [table]
        for step in path[1:-1]:
            nxt = idx.fk_target(table, step)
            if nxt is None:
                return None, f"{self.where}: '{table}.{step}' is not a foreign key, so the path cannot continue"
            table = nxt
            visited.append(table)
        if idx.column(table, path[-1]) is None:
            return None, f"{self.where}: column '{path[-1]}' not found in '{table}'"
        return visited, None

    def check(self, idx):
        _, err = self._steps(idx)
        return [err] if err else []

    def sql_type(self, idx):
        visited, _ = self._steps(idx)
        return idx.generator(visited[-1], self.p["path"][-1]).sql_type(idx)

    def may_be_null(self):
        return True

    def prepare(self, rt, spec):
        self.visited, _ = self._steps(rt.idx)

    def generate(self, rt, row, i):
        path = self.p["path"]
        value = row[path[0]]
        for table, step in zip(self.visited, path[1:]):
            if value is None:
                return None
            value = rt.tables[table][value - 1][step]
        return value


@register
class ParentFlagGen(Generator):
    """A label that depends on whether a parent column is set (e.g. status 'cancelled' if the customer churned)."""

    type_name = "parent_flag"
    required = {"fk", "parent_column", "if_null", "if_not_null"}

    def check(self, idx):
        err = self.prior_column_error(idx, self.p["fk"], want="fk") or self.parent_column_error(idx, self.p["fk"], self.p["parent_column"])
        return [err] if err else []

    def sql_type(self, idx):
        return String(64)

    def prepare(self, rt, spec):
        self.parent = rt.idx.fk_target(spec.name, self.p["fk"])

    def generate(self, rt, row, i):
        fk = row[self.p["fk"]]
        parent = rt.tables[self.parent][fk - 1]
        return self.p["if_null"] if parent[self.p["parent_column"]] is None else self.p["if_not_null"]
