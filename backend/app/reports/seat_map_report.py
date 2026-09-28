"""Physical seat-map PDF: one printable grid per room, matching the
frontend SeatMap.tsx's own occupied/empty/blocked states — but built
directly from `SeatMapReportData` (itself assembled from persisted
assignment + room-topology data by `ReportService`), never a screenshot
of the React component and never re-derived from assignment list order.

Grayscale-safe by design: course is always shown as text inside the
cell, never conveyed by color alone; a blocked seat gets a light
background shade as a *supplementary* cue on top of its "BLOCKED" text,
recognizable even when printed without color.

Wide rooms (more columns than fit comfortably in portrait) switch the
whole document to a landscape page — one page-size decision for the
document, not a per-room pagination framework — and column width is
computed from the actual available page width divided by column count,
never a fixed pixel width that would overflow a wide room.
"""

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Table, TableStyle

from app.reports.models import SeatMapReportData, SeatMapReportRoom, SeatMapReportSeat

_MARGIN = 36
# Beyond this many columns, portrait A4 no longer gives each cell a
# readable width at a legible font size — switch the whole document to
# landscape instead. Comfortably covers a 2x10 or 5x8 room; a 4x5 or 6x3
# room stays portrait.
_MAX_COLUMNS_BEFORE_LANDSCAPE = 6
_MAX_CELL_WIDTH = 100.0
_MIN_CELL_WIDTH = 46.0
_CELL_HEIGHT = 46
_CELL_STYLE = ParagraphStyle(name="SeatMapCell", fontSize=7, leading=8.5, alignment=1)  # 1 = TA_CENTER


def _seat_cell_text(seat: SeatMapReportSeat) -> str:
    seat_label = f"{seat.seat_number:02d}"
    if seat.state == "blocked":
        return f"<b>{seat_label}</b><br/>BLOCKED"
    if seat.state == "empty":
        return f"<b>{seat_label}</b><br/>EMPTY"
    return f"<b>{seat_label}</b><br/>{seat.course_code}<br/>{seat.student_number}"


def _room_flowable(room: SeatMapReportRoom, available_width: float) -> Flowable:
    if room.rows is None or room.columns is None:
        return Paragraph(
            f"Room {room.room_code} has no configured physical layout (rows/columns) — "
            "see the assignment table for its seat numbers.",
            getSampleStyleSheet()["Normal"],
        )

    col_width = max(_MIN_CELL_WIDTH, min(_MAX_CELL_WIDTH, available_width / room.columns))
    grid: list[list[object]] = [[None for _ in range(room.columns)] for _ in range(room.rows)]
    for seat in room.seats:
        grid[seat.row][seat.column] = Paragraph(_seat_cell_text(seat), _CELL_STYLE)

    style_commands: list[tuple[object, ...]] = [
        ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for seat in room.seats:
        if seat.state == "blocked":
            style_commands.append(
                ("BACKGROUND", (seat.column, seat.row), (seat.column, seat.row), colors.lightgrey)
            )

    return Table(
        grid,
        colWidths=[col_width] * room.columns,
        rowHeights=[_CELL_HEIGHT] * room.rows,
        style=TableStyle(style_commands),
    )


def render_seat_map_report(data: SeatMapReportData) -> bytes:
    needs_landscape = any(
        room.columns is not None and room.columns > _MAX_COLUMNS_BEFORE_LANDSCAPE for room in data.rooms
    )
    pagesize = landscape(A4) if needs_landscape else A4
    available_width = pagesize[0] - 2 * _MARGIN

    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
    )
    styles = getSampleStyleSheet()
    content: list[Flowable] = [
        Paragraph(f"Course Name: {data.course_name}", styles["Heading4"]),
        Paragraph(f"Course Code: {data.course_code}", styles["Heading4"]),
        Paragraph(f"Exam Date: {data.time_slot}_{data.exam_date}", styles["Heading4"]),
        Paragraph(
            f"Seating Generation #{data.generation_id} ({data.strategy_name}) — {data.status}",
            styles["Heading4"],
        ),
        Paragraph(
            "Each occupied cell shows seat number, course, and student ID. "
            "An unfilled cell is still usable; a shaded cell is not.",
            styles["Normal"],
        ),
        Paragraph("<br/>", styles["Normal"]),
    ]

    for room in data.rooms:
        content.append(Paragraph(f"Room: {room.room_code}", styles["Heading4"]))
        content.append(_room_flowable(room, available_width))
        content.append(Paragraph("<br/><br/>", styles["Normal"]))

    pdf.build(content)
    return buffer.getvalue()
