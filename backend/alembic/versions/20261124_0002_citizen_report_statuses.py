"""Align citizen-report statuses with the review workflow.

Legacy ``assigned`` state is normalized to ``under_review``. The existing
``assigned_to`` value is not modified and remains the source of assignment data.
"""

import sqlalchemy as sa

from alembic import op

revision = "20261124_0002"
down_revision = "20261122_0001"
branch_labels = None
depends_on = None


_STATUS_CONSTRAINT = "ck_citizen_reports_status_valid"
_NEW_STATUS_CHECK = "status IN ('submitted','under_review','verified','rejected','resolved')"
_OLD_STATUS_CHECK = "status IN ('submitted','under_review','assigned','resolved','rejected')"


def upgrade() -> None:
    # The old constraint permits under_review, so this normalization is valid
    # before replacing the constraint. assigned_to is intentionally untouched.
    op.execute("UPDATE citizen_reports SET status = 'under_review' WHERE status = 'assigned'")
    op.drop_constraint(op.f(_STATUS_CONSTRAINT), "citizen_reports", type_="check")
    op.create_check_constraint(op.f(_STATUS_CONSTRAINT), "citizen_reports", _NEW_STATUS_CHECK)


def downgrade() -> None:
    # A downgrade cannot faithfully represent verified in the old state set.
    # Refuse before DDL rather than silently rewriting verified history.
    verified_count = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM citizen_reports WHERE status = 'verified'"))
        .scalar_one()
    )
    if verified_count:
        raise RuntimeError(
            "Cannot downgrade citizen-report statuses while verified reports exist; "
            "preserve their workflow state before downgrading."
        )

    op.drop_constraint(op.f(_STATUS_CONSTRAINT), "citizen_reports", type_="check")
    op.create_check_constraint(op.f(_STATUS_CONSTRAINT), "citizen_reports", _OLD_STATUS_CHECK)
