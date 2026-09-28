"""Runtime settings, read once from environment variables."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # SQLite by default so the backend runs with zero setup; docker-compose points this at MySQL.
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./synthcorp.db")
    max_rows_per_table: int = int(os.getenv("MAX_ROWS_PER_TABLE", "200000"))
    max_total_rows: int = int(os.getenv("MAX_TOTAL_ROWS", "500000"))
    insert_batch_size: int = int(os.getenv("INSERT_BATCH_SIZE", "5000"))
    cors_origins: tuple = tuple(
        o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
    )


settings = Settings()
