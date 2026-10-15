"""Postgres enum labels are a contract, and SQLite cannot test them (a real outage).

**The bug this exists to prevent.** ``Message.direction``, ``Message.role`` and ``Message.status``
were mapped as ``SQLEnum(SomeEnum, name=...)`` with no ``values_callable``. Without it SQLAlchemy
sends ``member.name`` - ``"INBOUND"`` - while the database's enum *type* holds the labels the
migration wrote. Postgres rejected every write:

    invalid input value for enum message_direction: "INBOUND"

That survived **1072 passing tests** because SQLite does not enforce enum labels. A test that
round-trips an enum through the test database proves nothing about production; the only honest way
to test this is to assert what will be handed to Postgres, which is the type's label list.

**The invariant is not "everything is lowercase".** The labels are mixed-case on purpose, and
flattening them would be a different outage:

=========================  ==========================  ==========================
Enum                      ``.value``                  Migration that created it
=========================  ==========================  ==========================
``MessageRole``           ``VISITOR`` - uppercase     0013
``MessageDirection``      ``inbound`` - lowercase     0034
``MessageStatus``         ``drafted`` - lowercase     0034
=========================  ==========================  ==========================

So the rule is: ``values_callable`` **must be present**, so the Python ``.value`` is what is sent,
and the migration must agree with that ``.value``. Both halves are asserted below - the first as a
sweeping check over every enum column in the metadata, the second as exact expected labels, so that
someone "fixing" the casing gets told which migration disagrees rather than a Postgres error in
production.
"""

from __future__ import annotations

import enum

import pytest
from sqlalchemy import Enum as SQLEnum

from app.models.base import Base

#: The labels Postgres must accept, per enum, with the migration that pinned them. Written out
#: rather than derived, deliberately: deriving it from the model would make this test tautological.
EXPECTED_LABELS: dict[str, tuple[str, ...]] = {
    "message_role": ("VISITOR", "ASSISTANT", "HUMAN_OPERATOR"),
    "message_direction": ("inbound", "outbound"),
    "message_status": ("drafted", "awaiting_approval", "sent", "failed"),
}


def _enum_columns() -> list[tuple[str, str, SQLEnum]]:
    """Every enum-typed column in the model metadata, as ``(table, column, type)``."""
    found: list[tuple[str, str, SQLEnum]] = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, SQLEnum) and column.type.enum_class is not None:
                found.append((table.name, column.name, column.type))
    return found


def _python_enum_columns() -> list[tuple[str, str, SQLEnum]]:
    """The subset of :func:`_enum_columns` backed by a Python ``enum.Enum`` class.

    A ``SQLEnum`` of plain strings has no ``.value`` to defer to, so ``values_callable`` does not
    apply and it is not covered here.
    """
    return [
        (table, column, sql_enum)
        for table, column, sql_enum in _enum_columns()
        if isinstance(sql_enum.enum_class, type) and issubclass(sql_enum.enum_class, enum.Enum)
    ]


class TestValuesCallableIsPresent:
    """The sweeping half: nothing may map a Python enum without ``values_callable``."""

    def test_the_metadata_has_python_enum_columns_to_check(self) -> None:
        """A guard on the guard.

        If a refactor moved every enum off ``SQLEnum``, the loop below would pass on an empty
        collection and this file would silently stop testing anything - which is the same failure
        mode as the bug it guards, wearing a test's clothing.
        """
        assert len(_python_enum_columns()) >= 3, (
            "expected the conversation/message enums to still be SQLEnum columns; if they moved, "
            "this test is now vacuous and needs to be replaced rather than left passing"
        )

    def test_every_python_enum_column_sends_its_value_not_its_name(self) -> None:
        offenders = [
            f"{table}.{column} (type {sql_enum.name!r})"
            for table, column, sql_enum in _python_enum_columns()
            if sql_enum.enums != [m.value for m in sql_enum.enum_class]
        ]
        assert not offenders, (
            "these enum columns lack a values_callable that defers to the Python .value, so "
            "SQLAlchemy will send member.name to Postgres: " + ", ".join(offenders)
        )


class TestLabelsMatchTheMigrations:
    """The specific half: these labels are what migrations 0013 and 0034 created.

    A casing change here is a production outage that no SQLite test can see, so each assertion names
    the migration it would break.
    """

    @pytest.mark.parametrize("type_name", sorted(EXPECTED_LABELS))
    def test_the_labels_are_the_ones_the_migration_created(self, type_name: str) -> None:
        matching = [t for _, _, t in _python_enum_columns() if t.name == type_name]
        assert matching, f"no SQLEnum column uses the {type_name!r} Postgres type"

        for sql_enum in matching:
            assert tuple(sql_enum.enums) == EXPECTED_LABELS[type_name], (
                f"{type_name} labels changed. Postgres validates against the type created by "
                f"migration 0013 (message_role) or 0034 (message_direction, message_status) and "
                f"will reject the new labels. Changing casing needs a migration, not just an edit."
            )

    def test_the_three_message_enums_keep_their_mixed_case(self) -> None:
        """Document the asymmetry explicitly.

        ``MessageRole`` is uppercase because 0013 created it that way; the two others are lowercase
        because 0034 did. Making them uniform looks like tidying and breaks whichever side you move.
        """
        by_name = {t.name: t for _, _, t in _python_enum_columns()}

        assert by_name["message_role"].enums[0] == "VISITOR"
        assert by_name["message_role"].enums[0].isupper()

        assert by_name["message_direction"].enums[0] == "inbound"
        assert by_name["message_status"].enums[0] == "drafted"