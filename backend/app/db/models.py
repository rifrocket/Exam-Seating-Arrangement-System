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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    exam_date: Mapped[date] = mapped_column(Date)
    time_slot: Mapped[str] = mapped_column(String(32))

    course: Mapped["CourseModel"] = relationship(back_populates="exams")
    seating_generations: Mapped[list["SeatingGenerationModel"]] = relationship(back_populates="exam")


class RoomModel(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    capacity: Mapped[int] = mapped_column(Integer)


class SeatingGenerationModel(Base):
    __tablename__ = "seating_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)
    strategy_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    total_registered: Mapped[int] = mapped_column(Integer)
    total_assigned: Mapped[int] = mapped_column(Integer)
    total_unassigned: Mapped[int] = mapped_column(Integer)
    capacity_shortage: Mapped[bool] = mapped_column(Boolean, default=False)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exam: Mapped["ExamModel"] = relationship(back_populates="seating_generations")
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
