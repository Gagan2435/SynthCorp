import pytest

from app.engine.planner import plan_schema
from app.engine.schema import SchemaError, parse_schema


def plan(text):
    return plan_schema(parse_schema(text))


BASE = """
tables:
  - name: parents
    rows: 5
    columns:
      - {name: id, type: id}
  - name: kids
    rows: 10
    columns:
      - {name: id, type: id}
      - {name: parent_id, type: fk, ref: parents.id}
"""


def test_parents_are_generated_before_children():
    text = BASE.replace("  - name: parents", "  - name: zz_placeholder").replace("zz_placeholder", "parents")
    # declare the child first: order must still put the parent first
    swapped = """
tables:
  - name: kids
    rows: 10
    columns:
      - {name: id, type: id}
      - {name: parent_id, type: fk, ref: parents.id}
  - name: parents
    rows: 5
    columns:
      - {name: id, type: id}
"""
    assert plan(swapped).order == ["parents", "kids"]
    assert plan(text).order == ["parents", "kids"]


def test_cycle_is_reported():
    with pytest.raises(SchemaError) as e:
        plan("""
tables:
  - name: a
    rows: 2
    columns:
      - {name: id, type: id}
      - {name: b_id, type: fk, ref: b.id}
  - name: b
    rows: 2
    columns:
      - {name: id, type: id}
      - {name: a_id, type: fk, ref: a.id}
""")
    assert "circular" in str(e.value)


@pytest.mark.parametrize(
    "bad, expected",
    [
        ("{name: x, type: nope}", "unknown type 'nope'"),
        ("{name: x, type: int, min: 1}", "needs option(s) ['max']"),
        ("{name: x, type: int, min: 1, max: 2, colour: red}", "unknown option"),
        ("{name: x, type: fk, ref: ghosts.id}", "unknown table 'ghosts'"),
        ("{name: x, type: fk, ref: parents.name}", "not the id column"),
        ("{name: x, type: date_after, after: later, max_days: 3}", "declared earlier"),
        ("{name: x, type: lookup, path: [parent_id]}", "'path' must be a list"),
        ("{name: Bad-Name, type: int, min: 1, max: 2}", "lowercase"),
    ],
)
def test_bad_columns_give_clear_errors(bad, expected):
    text = BASE + f"      - {bad}\n"
    with pytest.raises(SchemaError) as e:
        plan(text)
    assert expected in str(e.value)


def test_one_to_one_needs_enough_parents():
    text = BASE.replace("{name: parent_id, type: fk, ref: parents.id}", "{name: parent_id, type: fk, ref: parents.id, distribution: one_to_one}")
    with pytest.raises(SchemaError) as e:
        plan(text)
    assert "one_to_one" in str(e.value)


def test_row_limit_is_enforced():
    with pytest.raises(SchemaError):
        plan_schema(parse_schema(BASE), max_rows_per_table=8)


def test_needs_exactly_one_id():
    with pytest.raises(SchemaError):
        plan("tables:\n  - name: t\n    rows: 1\n    columns:\n      - {name: a, type: int, min: 1, max: 2}\n")
