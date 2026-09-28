"""Request/response models for the HTTP API."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ValidateRequest(BaseModel):
    config_yaml: str = Field(max_length=100_000)


class CreateRunRequest(BaseModel):
    config_yaml: str = Field(max_length=100_000)
    seed: Optional[int] = Field(default=None, ge=0, le=2**31 - 1)
    inject_defects: bool = False


class RunSummary(BaseModel):
    id: int
    name: str
    status: str
    seed: int
    inject_defects: bool
    created_at: datetime
    finished_at: Optional[datetime]
    table_counts: Optional[dict]
    quality_passed: Optional[int] = None
    quality_failed: Optional[int] = None

    @classmethod
    def from_run(cls, run) -> "RunSummary":
        q = run.quality or {}
        return cls(
            id=run.id,
            name=run.name,
            status=run.status,
            seed=run.seed,
            inject_defects=run.inject_defects,
            created_at=run.created_at,
            finished_at=run.finished_at,
            table_counts=run.table_counts,
            quality_passed=q.get("passed"),
            quality_failed=q.get("failed"),
        )


class RunDetail(RunSummary):
    plan: Optional[dict]
    progress: Optional[dict]
    error: Optional[str]

    @classmethod
    def from_run(cls, run) -> "RunDetail":
        base = RunSummary.from_run(run).model_dump()
        return cls(**base, plan=run.plan, progress=run.progress, error=run.error)
