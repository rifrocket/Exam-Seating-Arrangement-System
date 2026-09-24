"""Confirms init_db() stops loudly on a stale `exams` table instead of
silently leaving it half-migrated or destroying/altering it."""

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine
from sqlalchemy.pool import StaticPool

from app.db.init_db import SchemaCompatibilityError, init_db


def test_stale_exams_table_stops_init_instead_of_silently_continuing() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    stale_metadata = MetaData()
    Table(
        "exams",
        stale_metadata,
        Column("id", Integer, primary_key=True),
        Column("course_id", Integer),
        # Missing expected_student_count / day_label — the pre-Milestone-3 shape.
    )
    stale_metadata.create_all(engine)

    with pytest.raises(SchemaCompatibilityError):
        init_db(engine)

    # Confirm nothing was silently dropped or altered by the failed attempt.
    from sqlalchemy import inspect

    columns = {col["name"] for col in inspect(engine).get_columns("exams")}
    assert columns == {"id", "course_id"}


def test_fresh_database_initializes_normally() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    init_db(engine)  # should not raise

    from sqlalchemy import inspect

    columns = {col["name"] for col in inspect(engine).get_columns("exams")}
    assert {"expected_student_count", "day_label"} <= columns
