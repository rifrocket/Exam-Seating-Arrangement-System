"""Report generation (PDF). Seating/ranges renderers adapted from the
legacy ReportLab views; `render_seat_map_report` (Milestone 14) is new.

Pure rendering functions (`render_seating_report`, `render_ranges_report`,
`render_seat_map_report`) that take a plain dataclass
(`app.reports.models`) and return PDF bytes. No FastAPI, no SQLAlchemy,
no filesystem, no repositories — assembling the input data from
persisted records is `app.services.reports`'s job.
"""

from app.reports.models import (
    RangeReportData,
    RangeReportRow,
    SeatingReportData,
    SeatingReportRoom,
    SeatingReportRow,
    SeatMapReportData,
    SeatMapReportRoom,
    SeatMapReportSeat,
)
from app.reports.ranges_report import render_ranges_report
from app.reports.seat_map_report import render_seat_map_report
from app.reports.seating_report import render_seating_report

__all__ = [
    "RangeReportData",
    "RangeReportRow",
    "SeatMapReportData",
    "SeatMapReportRoom",
    "SeatMapReportSeat",
    "SeatingReportData",
    "SeatingReportRoom",
    "SeatingReportRow",
    "render_ranges_report",
    "render_seat_map_report",
    "render_seating_report",
]
