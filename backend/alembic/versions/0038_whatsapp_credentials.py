"""phone_number_id and per-tenant credentials for WhatsApp.

``channel_registrations.external_identifier`` holds the *business phone number*, which is what a
tenant claims and what a human reads. The WhatsApp adapter needs two more things the number cannot
give it:

``phone_number_id``
    Meta's own id for the business number. Two reasons it cannot be derived from the number:
    the send endpoint takes ``{PHONE_NUMBER_ID}`` in the path, and the webhook's ``metadata`` block
    supplies it - so routing on the number alone means parsing a number Meta never actually sends.
    It is the stable identifier: a number can in principle be released and reissued, and the
    numeric id will not follow it.

``encrypted_access_token``
    A tenant's own system-user token, from Embedded Signup. Stored through the existing
    :mod:`app.core.secrets` ``SecretStore`` rather than plaintext - the same treatment
    ``accounts.encrypted_access_token`` already gets, and deliberately *not* a new
    ``channel_credentials`` table, which would be a second and weaker answer to a solved problem.

Both are nullable. A registration made before this migration is still valid on its number, and
delivery falls back to the platform token; making them required would strand those rows.

``phone_number_id`` is unique *within WhatsApp* and partial on ``IS NOT NULL``. Not globally: the
value is only meaningful paired with its channel, and a partial unique index lets every non-WhatsApp
registration carry a NULL without colliding, which a plain unique index would forbid after the
first two rows.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0038_whatsapp_credentials"
down_revision = "0037_conversation_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("channel_registrations", sa.Column("phone_number_id", sa.String(255), nullable=True))
    op.add_column(
        "channel_registrations", sa.Column("encrypted_access_token", sa.Text(), nullable=True)
    )
    op.create_index(
        "uq_channel_registration_phone_number_id",
        "channel_registrations",
        ["channel", "phone_number_id"],
        unique=True,
        sqlite_where=sa.text("phone_number_id IS NOT NULL"),
        postgresql_where=sa.text("phone_number_id IS NOT NULL"),
    )
    # Listing every registration that has onboarded its own token, for the Studio's channel view
    # and for deciding which rows need the platform-token fallback.
    op.create_index(
        "ix_channel_registration_has_token",
        "channel_registrations",
        ["organization_id"],
        sqlite_where=sa.text("encrypted_access_token IS NOT NULL"),
        postgresql_where=sa.text("encrypted_access_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_channel_registration_has_token", table_name="channel_registrations")
    op.drop_index("uq_channel_registration_phone_number_id", table_name="channel_registrations")
    op.drop_column("channel_registrations", "encrypted_access_token")
    op.drop_column("channel_registrations", "phone_number_id")