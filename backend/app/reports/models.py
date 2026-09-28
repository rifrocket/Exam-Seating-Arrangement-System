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
class SeatMapReportSeat:
    """One physical seat's state for the seat-map report — mirrors the
    three states the frontend SeatMap.tsx already renders (occupied /
    empty / blocked), computed from the exact same topology data, not
    re-derived from assignment order."""

    seat_number: int
    row: int
    column: int
    state: str  # "occupied" | "empty" | "blocked"
    course_code: str | None = None
    student_number: str | None = None
    student_name: str | None = None


@dataclass(frozen=True)
class SeatMapReportRoom:
    room_code: str
    # Both None when the room has no configured topology (rows/columns)
    # — matches SeatMap.tsx's own fallback for that case; `seats` is then
    # empty and the renderer shows a short text note instead of a grid.
    rows: int | None
    columns: int | None
    seats: list[SeatMapReportSeat]  # one entry per physical seat, row-major


@dataclass(frozen=True)
class SeatMapReportData:
    course_code: str
    course_name: str
    exam_date: str
    time_slot: str
    generation_id: int
    strategy_name: str
    status: str
    rooms: list[SeatMapReportRoom]  # in the exam's canonical room order


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
