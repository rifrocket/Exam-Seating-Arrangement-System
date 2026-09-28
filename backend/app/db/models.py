"""SQLAlchemy ORM models.

These mirror the domain/ dataclasses for persistence but are kept separate
from them: domain code and seating strategies never import this module,
so swapping a future seating strategy in never touches, and is never
touched by, table definitions here.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StudentModel(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))

    registrations: Mapped[list["RegistrationModel"]] = relationship(back_populates="student")


class CourseModel(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))

    registrations: Mapped[list["RegistrationModel"]] = relationship(back_populates="course")
    exams: Mapped[list["ExamModel"]] = relationship(back_populates="course")


class RegistrationModel(Base):
    __tablename__ = "registrations"
    __table_args__ = (UniqueConstraint("student_id", "course_id", name="uq_registration_student_course"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)

    student: Mapped["StudentModel"] = relationship(back_populates="registrations")
    course: Mapped["CourseModel"] = relationship(back_populates="registrations")


class ExamModel(Base):
    __tablename__ = "exams"
    __table_args__ = (
        UniqueConstraint("course_id", "exam_date", "time_slot", name="uq_exam_course_date_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    exam_date: Mapped[date] = mapped_column(Date)
    time_slot: Mapped[str] = mapped_column(String(32))
    expected_student_count: Mapped[int] = mapped_column(Integer)
    day_label: Mapped[str | None] = mapped_column(String(32), nullable=True)

    course: Mapped["CourseModel"] = relationship(back_populates="exams")
    seating_generations: Mapped[list["SeatingGenerationModel"]] = relationship(back_populates="exam")
    exam_rooms: Mapped[list["ExamRoomModel"]] = relationship(back_populates="exam")


class RoomModel(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    capacity: Mapped[int] = mapped_column(Integer)
    # Nullable: a room with neither set has no configured seat topology yet
    # (sequential seating never needs one; constraint seating does — see
    # app.domain.room.Room and app.seating.topology_provider). Added to an
    # already-shipped table in Milestone 8 — see
    # app.db.init_db._ensure_room_topology_columns for how an existing
    # database file picks these columns up without Alembic.
    rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    columns: Mapped[int | None] = mapped_column(Integer, nullable=True)

    exam_rooms: Mapped[list["ExamRoomModel"]] = relationship(back_populates="room")


class ExamRoomModel(Base):
    __tablename__ = "exam_rooms"
    __table_args__ = (UniqueConstraint("exam_id", "room_id", name="uq_exam_room_exam_room"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    allocated_students: Mapped[int] = mapped_column(Integer)

    exam: Mapped["ExamModel"] = relationship(back_populates="exam_rooms")
    room: Mapped["RoomModel"] = relationship(back_populates="exam_rooms")


class ExaminationSessionModel(Base):
    """A shared seating session grouping one or more compatible exams —
    see app.domain.examination_session for the domain concept and its
    validation (same date/time-slot, no student or room shared across
    the session's exams). Brand new as of Milestone 9; no migration
    needed for existing databases since create_all() creates any missing
    table."""

    __tablename__ = "examination_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_date: Mapped[date] = mapped_column(Date)
    time_slot: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session_exams: Mapped[list["SessionExamModel"]] = relationship(back_populates="session")
    seating_generations: Mapped[list["SeatingGenerationModel"]] = relationship(back_populates="session")


class SessionExamModel(Base):
    """The session <-> exam join. A session never copies an exam's own
    data (course, schedule, room allocations) — it only references the
    exam by id, exactly as ExamRoom references Room rather than copying
    its capacity."""

    __tablename__ = "session_exams"
    __table_args__ = (UniqueConstraint("session_id", "exam_id", name="uq_session_exam"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("examination_sessions.id"), index=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)

    session: Mapped["ExaminationSessionModel"] = relationship(back_populates="session_exams")
    exam: Mapped["ExamModel"] = relationship()


class SeatingGenerationModel(Base):
    __tablename__ = "seating_generations"
    __table_args__ = (
        CheckConstraint(
            "(exam_id IS NOT NULL AND session_id IS NULL) OR (exam_id IS NULL AND session_id IS NOT NULL)",
            name="ck_generation_exam_xor_session",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Nullable as of Milestone 9: exactly one of exam_id/session_id is set
    # (enforced above and by app.domain.seating_generation.SeatingGeneration's
    # own __post_init__) — a generation belongs to a single Exam (Milestone 4)
    # or, now, to an ExaminationSession spanning several exams/courses.
    # Relaxing exam_id's NOT NULL constraint on an already-shipped table
    # needs a real migration in SQLite (no ALTER COLUMN) — see
    # app.db.init_db._relax_seating_generation_exam_id_nullability.
    exam_id: Mapped[int | None] = mapped_column(ForeignKey("exams.id"), index=True, nullable=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("examination_sessions.id"), index=True, nullable=True
    )
    strategy_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    total_registered: Mapped[int] = mapped_column(Integer)
    total_assigned: Mapped[int] = mapped_column(Integer)
    total_unassigned: Mapped[int] = mapped_column(Integer)
    capacity_shortage: Mapped[bool] = mapped_column(Boolean, default=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exam: Mapped["ExamModel | None"] = relationship(back_populates="seating_generations")
    session: Mapped["ExaminationSessionModel | None"] = relationship(back_populates="seating_generations")
    seat_assignments: Mapped[list["SeatAssignmentModel"]] = relationship(back_populates="seating_generation")


class SeatAssignmentModel(Base):
    __tablename__ = "seat_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seating_generation_id: Mapped[int] = mapped_column(ForeignKey("seating_generations.id"), index=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    seat_number: Mapped[int] = mapped_column(Integer)

    seating_generation: Mapped["SeatingGenerationModel"] = relationship(back_populates="seat_assignments")
