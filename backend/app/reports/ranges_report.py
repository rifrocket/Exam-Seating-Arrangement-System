"""ID-range PDF, adapted from the legacy views/ranges_view.py.

What's reused: the table layout of RangesView.generate_pdf. What's NOT
reused: RangesView's constructor (filesystem writes), and its data
source — the legacy `rangesObj` was built by recording the first/last ID
*consumed* from a shared, mutating registration list as main.py walked
it. That data no longer exists; this adapter instead derives start/end
IDs from persisted `SeatAssignment` rows for one generation, grouped by
room in the exam's canonical room order, using min/max seat_number within
each room (see docs/architecture.md for why this is a faithful, not
incidental, replacement: students are assigned in deterministic
student-number order, so seat_number order and student-number order
coincide within a room).

Deviation from the legacy column label, documented rather than hidden:
the legacy table's last column was headed "Capacity" but actually held
the *count of students assigned* to that room — not the room's physical
capacity, which is a different, already-precisely-named field elsewhere
in this system (Room.capacity). Reusing that label here would recreate
exactly the ambiguity the rest of this project has deliberately avoided
since the capacity-semantics work, so this adapter labels the column
"Assigned" instead.
"""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table

from app.reports.models import RangeReportData

_DATA_STYLE = [("GRID", (0, 0), (-1, -1), 1, colors.black), ("FONTSIZE", (0, 0), (-1, 0), 11)]
_COL_WIDTHS = [50, 100, 100, 100, 80]


def render_ranges_report(data: RangeReportData) -> bytes:
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    content = [
        Paragraph(f"Course Name: {data.course_name}", styles["Heading4"]),
        Paragraph(f"Course Code: {data.course_code}", styles["Heading4"]),
        Paragraph(f"Seating Generation #{data.generation_id}", styles["Heading4"]),
        Paragraph("<br/>", styles["Normal"]),
    ]

    table_rows: list[list[object]] = [["#", "Room", "Start ID", "End ID", "Assigned"]]
    for index, row in enumerate(data.rows, start=1):
        table_rows.append([index, row.room_code, row.start_student_number, row.end_student_number, row.assigned_count])
    content.append(Table(table_rows, style=_DATA_STYLE, colWidths=_COL_WIDTHS, rowHeights=25))

    pdf.build(content)
    return buffer.getvalue()
