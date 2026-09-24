"""Report generation (PDF), adapted from the legacy ReportLab views.

Pure rendering functions (`render_seating_report`, `render_ranges_report`)
that take a plain dataclass (`app.reports.models`) and return PDF bytes.
No FastAPI, no SQLAlchemy, no filesystem, no repositories — assembling
the input data from persisted records is `app.services.reports`'s job.
"""

from app.reports.models import (
    RangeReportData,
    RangeReportRow,
    SeatingReportData,
    SeatingReportRoom,
    SeatingReportRow,
)
from app.reports.ranges_report import render_ranges_report
from app.reports.seating_report import render_seating_report

__all__ = [
    "RangeReportData",
    "RangeReportRow",
    "SeatingReportData",
    "SeatingReportRoom",
    "SeatingReportRow",
    "render_ranges_report",
    "render_seating_report",
]
