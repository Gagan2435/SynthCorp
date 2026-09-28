"""create runs table

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0001"
down_revision = None


def upgrade():
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("inject_defects", sa.Boolean(), nullable=False),
        sa.Column("config_yaml", sa.Text().with_variant(mysql.MEDIUMTEXT(), "mysql"), nullable=False),
        sa.Column("table_prefix", sa.String(20), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("progress", sa.JSON(), nullable=True),
        sa.Column("table_counts", sa.JSON(), nullable=True),
        sa.Column("quality", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_runs_status", "runs", ["status"])


def downgrade():
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_table("runs")
