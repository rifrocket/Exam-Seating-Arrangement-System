"""Plain input data for the ReportLab adapters.

Mirrors app/seating/models.py's role: computation/rendering-scoped
shapes, not persisted entities. Nothing in this module imports
ReportLab, FastAPI, or SQLAlchemy — it's just what a renderer function
needs to draw a PDF, assembled by app.services.reports.ReportService.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SeatingReportRow:
    seat_number: int
    student_number: str
    student_name: str


@dataclass(frozen=True)
class SeatingReportRoom:
    room_code: str
    rows: list[SeatingReportRow]  # sorted by seat_number


@dataclass(frozen=True)
class SeatingReportData:
    course_code: str
    course_name: str
    exam_date: str
    time_slot: str
    generation_id: int
    strategy_name: str
    status: str
    rooms: list[SeatingReportRoom]  # in the exam's canonical room order


@dataclass(frozen=True)
class RangeReportRow:
    room_code: str
    start_student_number: str
    end_student_number: str
    assigned_count: int


@dataclass(frozen=True)
class RangeReportData:
    course_code: str
    course_name: str
    generation_id: int
    rows: list[RangeReportRow]  # in the exam's canonical room order
