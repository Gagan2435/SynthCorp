from alembic import context

from app.db import Base, engine
from app import models  # noqa: F401  (registers the tables on Base.metadata)

target_metadata = Base.metadata


def run_migrations_online():
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
