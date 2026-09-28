"""The run pipeline: validate -> generate -> load into MySQL -> (inject defects) -> quality checks."""
from __future__ import annotations

import traceback

from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, engine
from app.engine.generator import generate
from app.engine.planner import SchemaPlan, plan_schema
from app.engine.schema import SchemaSpec, parse_schema
from app.models import Run, utcnow
from app.quality.checks import run_checks
from app.services.defects import inject_defects
from app.services.tables import build_tables, create_tables, drop_tables, load_rows


def describe_plan(schema: SchemaSpec, plan: SchemaPlan) -> dict:
    """A JSON-friendly description of the schema, used by the UI diagram and the mock API."""
    return {
        "order": plan.order,
        "edges": plan.edges,
        "tables": [
            {
                "name": t.name,
                "rows": t.rows,
                "columns": [
                    {"name": c.name, "type": c.type, **({"ref": c.params["ref"]} if c.type == "fk" else {})}
                    for c in t.columns
                ],
            }
            for t in schema.tables
        ],
    }


def prepare(config_yaml: str, seed: int | None = None):
    schema = parse_schema(config_yaml)
    if seed is not None:
        schema.seed = seed
    plan = plan_schema(schema, settings.max_rows_per_table, settings.max_total_rows)
    return schema, plan


def create_run(db: Session, config_yaml: str, seed: int | None, defects: bool) -> Run:
    """Validate synchronously so bad configs fail fast with a clear error, before any work is queued."""
    schema, plan = prepare(config_yaml, seed)
    run = Run(
        name=schema.name[:120],
        status="pending",
        seed=schema.seed,
        inject_defects=defects,
        config_yaml=config_yaml,
        plan=describe_plan(schema, plan),
        progress={"done_tables": [], "total_tables": len(plan.order)},
    )
    db.add(run)
    db.commit()
    run.table_prefix = f"r{run.id}_"
    db.commit()
    return run


def run_tables(run: Run):
    """Rebuild the SQLAlchemy tables for a finished run from its stored config."""
    schema, plan = prepare(run.config_yaml, run.seed)
    return schema, plan, build_tables(schema, plan.index, run.table_prefix)


def execute_run(run_id: int) -> None:
    """Runs in a background task with its own DB session."""
    db = SessionLocal()
    tables = None
    try:
        run = db.get(Run, run_id)
        run.status = "running"
        db.commit()

        schema, plan = prepare(run.config_yaml, run.seed)
        tables = build_tables(schema, plan.index, run.table_prefix)

        def on_table_done(name: str, count: int):
            run.progress = {
                "done_tables": [*run.progress["done_tables"], name],
                "total_tables": len(plan.order),
                "stage": "generating",
            }
            db.commit()

        data = generate(schema, plan, on_table_done)

        run.progress = {**run.progress, "stage": "loading"}
        db.commit()
        drop_tables(engine, tables)  # clear leftovers from any earlier attempt with the same id
        create_tables(engine, tables)
        for name in plan.order:
            load_rows(engine, tables[name], data[name], settings.insert_batch_size)
        run.table_counts = {name: len(rows) for name, rows in data.items()}
        del data  # free memory before the checks

        defects = inject_defects(engine, schema, tables, plan.index) if run.inject_defects else []

        run.progress = {**run.progress, "stage": "checking"}
        db.commit()
        with engine.connect() as conn:
            report = run_checks(conn, schema, tables, plan.index)
        report["injected_defects"] = defects
        run.quality = report

        run.status = "done"
        run.progress = {**run.progress, "stage": "done"}
        run.finished_at = utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001 - any failure must end up on the run, not vanish in a worker
        db.rollback()
        run = db.get(Run, run_id)
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
        run.finished_at = utcnow()
        db.commit()
        traceback.print_exc()
        if tables:
            try:
                drop_tables(engine, tables)
            except Exception:  # noqa: BLE001
                pass
    finally:
        db.close()


def delete_run(db: Session, run: Run) -> None:
    try:
        _, _, tables = run_tables(run)
        drop_tables(engine, tables)
    except Exception:  # noqa: BLE001 - config may be unreadable; still remove the record
        pass
    db.delete(run)
    db.commit()
