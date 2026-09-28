"""HTTP routes: schema tools, runs, previews, exports and the mock app API."""
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import CreateRunRequest, RunDetail, RunSummary, ValidateRequest
from app.db import engine, get_db
from app.engine.schema import SchemaError
from app.models import Run
from app.services import exports, runs

router = APIRouter(prefix="/api")

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
TEMPLATES = {
    "saas": ("SaaS company", "Customers, plans, subscriptions, invoices and support tickets, with churn."),
    "ecommerce": ("Online shop", "Shoppers, products and orders. A smaller schema to start with."),
}


@router.get("/health")
def health():
    return {"status": "ok"}


# ----------------------------------------------------------------- schema tools
@router.get("/templates")
def list_templates():
    return [
        {"id": tid, "name": name, "description": desc, "yaml": (TEMPLATE_DIR / f"{tid}.yaml").read_text()}
        for tid, (name, desc) in TEMPLATES.items()
    ]


@router.post("/schema/validate")
def validate_schema(body: ValidateRequest):
    """Always answers 200: `valid: false` plus a list of problems, so the editor can show them as you type."""
    try:
        schema, plan = runs.prepare(body.config_yaml)
    except SchemaError as exc:
        return {"valid": False, "errors": exc.errors, "plan": None}
    return {"valid": True, "errors": [], "plan": runs.describe_plan(schema, plan)}


# ----------------------------------------------------------------- runs
def _get_run(db: Session, run_id: int) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


def _get_done_run(db: Session, run_id: int) -> Run:
    run = _get_run(db, run_id)
    if run.status != "done":
        raise HTTPException(409, f"Run is {run.status}; data is only available once it is done")
    return run


@router.post("/runs", status_code=202)
def create_run(body: CreateRunRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        run = runs.create_run(db, body.config_yaml, body.seed, body.inject_defects)
    except SchemaError as exc:
        raise HTTPException(422, {"errors": exc.errors})
    background.add_task(runs.execute_run, run.id)
    return RunDetail.from_run(run)


@router.get("/runs")
def list_runs(db: Session = Depends(get_db)):
    rows = db.scalars(select(Run).order_by(Run.id.desc()).limit(50)).all()
    return [RunSummary.from_run(r) for r in rows]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    return RunDetail.from_run(_get_run(db, run_id))


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: int, db: Session = Depends(get_db)):
    runs.delete_run(db, _get_run(db, run_id))


@router.get("/runs/{run_id}/quality")
def get_quality(run_id: int, db: Session = Depends(get_db)):
    run = _get_done_run(db, run_id)
    return run.quality


def _table_or_404(tables: dict, name: str):
    if name not in tables:
        raise HTTPException(404, f"Unknown table '{name}'")
    return tables[name]


@router.get("/runs/{run_id}/tables/{table}")
def preview_table(run_id: int, table: str, limit: int = Query(25, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    run = _get_done_run(db, run_id)
    _, plan, tables = runs.run_tables(run)
    t = _table_or_404(tables, table)
    pk = t.c[plan.index.pk(table)]
    with engine.connect() as conn:
        rows = conn.execute(select(t).order_by(pk).limit(limit).offset(offset)).all()
    return {
        "table": table,
        "columns": [c.name for c in t.columns],
        "total": exports.count_rows(engine, t),
        "limit": limit,
        "offset": offset,
        "rows": jsonable_encoder([dict(r._mapping) for r in rows]),
    }


@router.get("/runs/{run_id}/tables/{table}/csv")
def export_csv(run_id: int, table: str, db: Session = Depends(get_db)):
    run = _get_done_run(db, run_id)
    _, plan, tables = runs.run_tables(run)
    t = _table_or_404(tables, table)
    return StreamingResponse(
        exports.csv_stream(engine, t, plan.index.pk(table)),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{table}.csv"'},
    )


@router.get("/runs/{run_id}/dump.sql")
def export_sql(run_id: int, db: Session = Depends(get_db)):
    run = _get_done_run(db, run_id)
    schema, plan, tables = runs.run_tables(run)
    return StreamingResponse(
        exports.sql_dump_data_stream(engine, schema, plan, tables),
        media_type="application/sql",
        headers={"Content-Disposition": f'attachment; filename="{schema.name}.sql"'},
    )


# ----------------------------------------------------------------- mock app API
# The generated dataset served like a real app's REST API: this is what an agent would be pointed at.
@router.get("/mock/{run_id}")
def mock_index(run_id: int, db: Session = Depends(get_db)):
    run = _get_done_run(db, run_id)
    return {"name": run.name, "tables": run.plan["tables"], "relationships": run.plan["edges"]}


@router.get("/mock/{run_id}/{table}")
def mock_list(run_id: int, table: str, request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    run = _get_done_run(db, run_id)
    _, plan, tables = runs.run_tables(run)
    t = _table_or_404(tables, table)
    reserved = {"limit", "offset"}
    conditions = []
    for key, raw in request.query_params.items():
        if key in reserved:
            continue
        if key not in t.c:
            raise HTTPException(400, f"Cannot filter on unknown column '{key}'")
        conditions.append(t.c[key] == raw)
    pk = t.c[plan.index.pk(table)]
    with engine.connect() as conn:
        rows = conn.execute(select(t).where(*conditions).order_by(pk).limit(limit).offset(offset)).all()
    return {
        "items": jsonable_encoder([dict(r._mapping) for r in rows]),
        "total": exports.count_rows(engine, t, conditions),
        "limit": limit,
        "offset": offset,
    }


@router.get("/mock/{run_id}/{table}/{item_id}")
def mock_get(run_id: int, table: str, item_id: int, db: Session = Depends(get_db)):
    run = _get_done_run(db, run_id)
    _, plan, tables = runs.run_tables(run)
    t = _table_or_404(tables, table)
    with engine.connect() as conn:
        row = conn.execute(select(t).where(t.c[plan.index.pk(table)] == item_id)).first()
    if row is None:
        raise HTTPException(404, f"{table} {item_id} not found")
    return jsonable_encoder(dict(row._mapping))
