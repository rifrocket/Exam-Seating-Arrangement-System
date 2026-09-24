"""Seating-arrangement PDF, adapted from the legacy views/seating_view.py.

What's reused: the table layout, margins, and paragraph structure of
SeatingView.generate_pdf are carried over essentially unchanged — that
code was already clean ReportLab usage with no dependency on global
state. What's NOT reused: SeatingView's constructor, which wrote directly
to `./outputs/{date}/...` and produced one PDF per room. This adapter
instead renders every room of one generation into a single PDF (room
sections in the exam's canonical room order) and returns bytes, so the
API layer can serve it directly over HTTP with no filesystem coupling.
"""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table

from app.reports.models import SeatingReportData

_DATA_STYLE = [("GRID", (0, 0), (-1, -1), 1, colors.black), ("FONTSIZE", (0, 0), (-1, 0), 11)]
_COL_WIDTHS = [55, 65, 190, 200]


def render_seating_report(data: SeatingReportData) -> bytes:
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    content = [
        Paragraph(f"Course Name: {data.course_name}", styles["Heading4"]),
        Paragraph(f"Course Code: {data.course_code}", styles["Heading4"]),
        Paragraph(f"Exam Date: {data.time_slot}_{data.exam_date}", styles["Heading4"]),
        Paragraph(
            f"Seating Generation #{data.generation_id} ({data.strategy_name}) — {data.status}",
            styles["Heading4"],
        ),
        Paragraph("<br/>", styles["Normal"]),
    ]

    for room in data.rooms:
        content.append(Paragraph(f"Room: {room.room_code}", styles["Heading4"]))
        table_rows: list[list[object]] = [["Seat#", "Student ID", "Name", "Signature"]]
        for row in room.rows:
            table_rows.append([row.seat_number, row.student_number, row.student_name, "             "])
        content.append(Table(table_rows, style=_DATA_STYLE, colWidths=_COL_WIDTHS, rowHeights=25))
        content.append(Paragraph("<br/><br/>", styles["Normal"]))

    pdf.build(content)
    return buffer.getvalue()
