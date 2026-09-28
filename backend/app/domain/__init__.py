"""Domain models: plain Python dataclasses describing the problem domain.

Nothing in this package imports FastAPI, SQLAlchemy, or any I/O concern.
These types are what services, seating strategies, and repository
interfaces speak to each other in; the db/ package maps them onto tables.
"""

from app.domain.course import Course
from app.domain.exam import Exam
from app.domain.exam_room import ExamRoom
from app.domain.examination_session import (
    ConflictingRoomAllocationError,
    DuplicateStudentInSessionError,
    ExaminationSession,
    ExamRoomAllocation,
    IncompatibleExamScheduleError,
    build_examination_session,
    build_session_participants,
    validate_no_conflicting_room_usage,
)
from app.domain.registration import Registration
from app.domain.room import InvalidRoomTopologyError, Room
from app.domain.seat_assignment import SeatAssignment
from app.domain.seating_generation import (
    GenerationStatus,
    InvalidSeatingGenerationTargetError,
    SeatingGeneration,
)
from app.domain.student import Student
from app.domain.student_seating_context import StudentSeatingContext

__all__ = [
    "ConflictingRoomAllocationError",
    "Course",
    "DuplicateStudentInSessionError",
    "Exam",
    "ExamRoom",
    "ExamRoomAllocation",
    "ExaminationSession",
    "GenerationStatus",
    "IncompatibleExamScheduleError",
    "InvalidRoomTopologyError",
    "InvalidSeatingGenerationTargetError",
    "Registration",
    "Room",
    "SeatAssignment",
    "SeatingGeneration",
    "Student",
    "StudentSeatingContext",
    "build_examination_session",
    "build_session_participants",
    "validate_no_conflicting_room_usage",
]
