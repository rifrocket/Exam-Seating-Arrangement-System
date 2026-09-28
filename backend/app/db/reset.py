"""Database reset: deletes every row from every application table while
leaving the schema itself completely untouched — the destructive
counterpart to `init_db()`'s additive table creation.

Tables are deleted in `Base.metadata.sorted_tables`'s *reverse* order,
which SQLAlchemy computes from the models' own `ForeignKey` declarations
— a child table (one with a foreign key to another table) is always
deleted before the parent it points to, so this never violates a
foreign-key constraint regardless of whether the underlying engine
enforces them. It also means a table added to `app/db/models.py` in the
future is picked up here automatically, with nothing in this file
needing to change.

Deliberately *not* `Base.metadata.drop_all()` + `create_all()`: dropping
and recreating the schema is a heavier, riskier operation (momentarily
no schema at all, every index/constraint rebuilt) for no benefit over
simply deleting every row — the schema itself never needs to change
here, only its data. This app also has no immutable/reference-data
table to preserve: every row in every table (students, courses,
registrations, exams, rooms, exam_rooms, examination_sessions,
session_exams, seating_generations, seat_assignments) is data the
application itself created via CSV import or seating generation, not
static configuration — see docs/architecture.md's "Database reset"
section.
"""

from sqlalchemy.orm import Session

from app.db import models  # noqa: F401  (ensures models are registered on Base.metadata)
from app.db.base import Base


def reset_database(session: Session) -> None:
    """Issues one DELETE per table, in dependency-safe order, using the
    given session. Deliberately does not commit or roll back itself —
    the caller owns the transaction boundary, so a single
    `session.commit()` (or `session.rollback()` on failure) covers every
    table's deletion atomically, never a partial reset."""
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
