"""Domain models: plain Python dataclasses describing the problem domain.

Nothing in this package imports FastAPI, SQLAlchemy, or any I/O concern.
These types are what services, seating strategies, and repository
interfaces speak to each other in; the db/ package maps them onto tables.
"""

from app.domain.course import Course
from app.domain.exam import Exam
from app.domain.registration import Registration
from app.domain.room import Room
from app.domain.seat_assignment import SeatAssignment
from app.domain.seating_generation import (
    GenerationStatus,
    SeatingGeneration,
)
from app.domain.student import Student

__all__ = [
    "Course",
    "Exam",
    "GenerationStatus",
    "Registration",
    "Room",
    "SeatAssignment",
    "SeatingGeneration",
    "Student",
]
