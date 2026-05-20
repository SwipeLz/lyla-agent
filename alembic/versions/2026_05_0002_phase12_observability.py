"""phase12 observability

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("voice_command_logs") as batch_op:
        batch_op.add_column(sa.Column("metadata_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("request_received_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("response_sent_at", sa.DateTime(timezone=True), nullable=True)
        )

    with op.batch_alter_table("devices") as batch_op:
        batch_op.add_column(sa.Column("api_token", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("firmware_version", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("wifi_rssi_dbm", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("battery_pct", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("free_heap_bytes", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("devices") as batch_op:
        batch_op.drop_column("free_heap_bytes")
        batch_op.drop_column("battery_pct")
        batch_op.drop_column("wifi_rssi_dbm")
        batch_op.drop_column("firmware_version")
        batch_op.drop_column("api_token")

    with op.batch_alter_table("voice_command_logs") as batch_op:
        batch_op.drop_column("response_sent_at")
        batch_op.drop_column("request_received_at")
        batch_op.drop_column("metadata_json")
