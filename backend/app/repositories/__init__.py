"""Repository interfaces: boundaries between services and persistence.

These are abstract only — no SQLAlchemy-backed implementation exists yet.
Concrete implementations land alongside the milestone that first needs to
read/write real data (registration import, schedule import, ...), so this
package doesn't outgrow what's actually used.
"""

from app.repositories.base import Repository
from app.repositories.course_repository import CourseRepository
from app.repositories.exam_repository import ExamRepository
from app.repositories.registration_repository import RegistrationRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.seat_assignment_repository import SeatAssignmentRepository
from app.repositories.seating_generation_repository import SeatingGenerationRepository
from app.repositories.student_repository import StudentRepository

__all__ = [
    "CourseRepository",
    "ExamRepository",
    "RegistrationRepository",
    "Repository",
    "RoomRepository",
    "SeatAssignmentRepository",
    "SeatingGenerationRepository",
    "StudentRepository",
]
