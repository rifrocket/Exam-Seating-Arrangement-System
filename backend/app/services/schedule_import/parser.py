"""Parses and validates schedule CSV text into normalized exam groups.

Pure function over a string: no file I/O, no FastAPI, no SQLAlchemy.

Expected columns (matching the legacy repository's schedule export format,
inspected directly across every variant committed under input/ — see
docs/architecture.md for the full survey):
    Date, Time, Course Code, Course Name, No. of Students, Room(s),
    No. of Students/ Room
"Day" is read if present but is optional, unvalidated display text.
Other legacy columns (Level, Instructor, Required No. of Proctors,
No. of proctors / Room, Proctor(s)) are ignored — the legacy code never
used them for seating either, and they're inconsistently present across
files (e.g. input/summer_day1.csv omits several of them entirely).

Known real-world oddity this parser deliberately does NOT try to fix:
input/day3.csv contains a raw Excel date serial number ("44937") in one
Date cell instead of a real date string. That row is reported as a
malformed-date validation error, not guessed at — silently interpreting
an ambiguous serial number would be inventing data the source doesn't
reliably have.
"""

import csv
import re
from datetime import date, datetime
from io import StringIO

from app.services.schedule_import.records import (
    Conflict,
    NormalizedExamGroup,
    NormalizedExamRoomRow,
    ParsedScheduleCSV,
    ValidationError,
)

REQUIRED_COLUMNS = {
    "Date",
    "Time",
    "Course Code",
    "Course Name",
    "No. of Students",
    "Room(s)",
    "No. of Students/ Room",
}

# Every date format actually observed across input/*.csv. Tried in order;
# the first one that parses wins. Two-digit years ("9-Jan-23") resolve to
# the 2000s via strptime's default windowing, which is correct for this
# data's era.
_DATE_FORMATS = ("%d-%b-%Y", "%d-%b-%y", "%d/%m/%Y", "%B %d, %Y")

_TIME_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


def _parse_date(raw: str) -> date | None:
    normalized = " ".join(raw.split())
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt).date()
        except ValueError:
            continue
    return None


def _parse_time_slot(raw: str) -> str | None:
    """Normalizes to a canonical "HH:MM-HH:MM" string. The source data has
    no AM/PM marker, so hours are validated only as 0-23 literal digits,
    not resolved to a real time-of-day."""
    collapsed = re.sub(r"\s+", "", raw)
    match = _TIME_PATTERN.match(collapsed)
    if not match:
        return None
    start_h, start_m, end_h, end_m = (int(g) for g in match.groups())
    if not (0 <= start_h <= 23 and 0 <= start_m <= 59 and 0 <= end_h <= 23 and 0 <= end_m <= 59):
        return None
    return f"{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}"


def _parse_count(raw: str) -> tuple[int | None, str | None]:
    """Returns (value, error_kind). error_kind is "invalid" (not an
    integer) or "negative", or None if the value is fine."""
    try:
        value = int(raw)
    except ValueError:
        return None, "invalid"
    if value < 0:
        return None, "negative"
    return value, None


class _ExamGroupBuilder:
    __slots__ = (
        "course_code",
        "course_name",
        "exam_date",
        "time_slot",
        "day_label",
        "expected_student_count",
        "first_line_number",
        "exam_rooms",
        "_room_allocations",
    )

    def __init__(
        self,
        course_code: str,
        course_name: str,
        exam_date: date,
        time_slot: str,
        day_label: str | None,
        expected_student_count: int,
        line_number: int,
    ) -> None:
        self.course_code = course_code
        self.course_name = course_name
        self.exam_date = exam_date
        self.time_slot = time_slot
        self.day_label = day_label
        self.expected_student_count = expected_student_count
        self.first_line_number = line_number
        self.exam_rooms: list[NormalizedExamRoomRow] = []
        self._room_allocations: dict[str, int] = {}

    def add_room(self, room_code: str, allocated_students: int, line_number: int) -> tuple[bool, Conflict | None]:
        """Returns (is_duplicate, conflict). Exactly one of "recorded as a
        new exam-room", "counted as a duplicate row", or "flagged as a
        conflict" happens per call."""
        if room_code in self._room_allocations:
            existing = self._room_allocations[room_code]
            if existing != allocated_students:
                conflict = Conflict(
                    "exam_room_allocation",
                    f"{self.course_code}|{self.exam_date.isoformat()}|{self.time_slot}|{room_code}",
                    line_number,
                    str(existing),
                    str(allocated_students),
                )
                return False, conflict
            return True, None  # exact duplicate room-row within the file
        self._room_allocations[room_code] = allocated_students
        self.exam_rooms.append(NormalizedExamRoomRow(line_number, room_code, allocated_students))
        return False, None

    def to_record(self) -> NormalizedExamGroup:
        return NormalizedExamGroup(
            course_code=self.course_code,
            course_name=self.course_name,
            exam_date=self.exam_date,
            time_slot=self.time_slot,
            day_label=self.day_label,
            expected_student_count=self.expected_student_count,
            first_line_number=self.first_line_number,
            exam_rooms=self.exam_rooms,
        )


def _empty_result(message: str) -> ParsedScheduleCSV:
    return ParsedScheduleCSV(
        rows_read=0,
        exam_groups=[],
        validation_errors=[ValidationError(None, None, message)],
        conflicts=[],
        duplicate_rows=0,
    )


def parse_schedule_csv(csv_text: str) -> ParsedScheduleCSV:
    reader = csv.DictReader(StringIO(csv_text))

    if reader.fieldnames is None:
        return _empty_result("CSV file is empty or has no header row.")

    header = {name.strip() for name in reader.fieldnames if name is not None}
    missing = REQUIRED_COLUMNS - header
    if missing:
        return _empty_result(f"Missing required column(s): {', '.join(sorted(missing))}.")

    validation_errors: list[ValidationError] = []
    conflicts: list[Conflict] = []
    duplicate_rows = 0
    rows_read = 0

    canonical_course_name: dict[str, str] = {}
    exam_groups: dict[tuple[str, date, str], _ExamGroupBuilder] = {}

    try:
        for line_number, row in enumerate(reader, start=2):
            rows_read += 1

            day_label = (row.get("Day") or "").strip() or None
            date_raw = (row.get("Date") or "").strip()
            time_raw = (row.get("Time") or "").strip()
            course_code = (row.get("Course Code") or "").strip()
            course_name = (row.get("Course Name") or "").strip()
            room_code = (row.get("Room(s)") or "").strip()
            students_raw = (row.get("No. of Students") or "").strip()
            allocation_raw = (row.get("No. of Students/ Room") or "").strip()

            row_errors: list[ValidationError] = []
            if not course_code:
                row_errors.append(ValidationError(line_number, "Course Code", "Course Code must not be empty."))
            if not course_name:
                row_errors.append(ValidationError(line_number, "Course Name", "Course Name must not be empty."))
            if not room_code:
                row_errors.append(ValidationError(line_number, "Room(s)", "Room(s) must not be empty."))

            exam_date = _parse_date(date_raw) if date_raw else None
            if exam_date is None:
                row_errors.append(ValidationError(line_number, "Date", f"Malformed date: '{date_raw}'."))

            time_slot = _parse_time_slot(time_raw) if time_raw else None
            if time_slot is None:
                row_errors.append(ValidationError(line_number, "Time", f"Malformed time: '{time_raw}'."))

            expected_count, count_error = _parse_count(students_raw)
            if count_error == "invalid":
                row_errors.append(
                    ValidationError(line_number, "No. of Students", f"Invalid student count: '{students_raw}'.")
                )
            elif count_error == "negative":
                row_errors.append(
                    ValidationError(line_number, "No. of Students", "Student count must not be negative.")
                )

            allocation, allocation_error = _parse_count(allocation_raw)
            if allocation_error == "invalid":
                row_errors.append(
                    ValidationError(
                        line_number, "No. of Students/ Room", f"Invalid room allocation: '{allocation_raw}'."
                    )
                )
            elif allocation_error == "negative":
                row_errors.append(
                    ValidationError(line_number, "No. of Students/ Room", "Room allocation must not be negative.")
                )

            if row_errors:
                validation_errors.extend(row_errors)
                continue

            # mypy/type-narrowing: all four are non-None past this point.
            assert exam_date is not None
            assert time_slot is not None
            assert expected_count is not None
            assert allocation is not None

            if course_code in canonical_course_name:
                existing_name = canonical_course_name[course_code]
                if existing_name != course_name:
                    conflicts.append(Conflict("course_name", course_code, line_number, existing_name, course_name))
            else:
                canonical_course_name[course_code] = course_name

            group_key = (course_code, exam_date, time_slot)
            group = exam_groups.get(group_key)
            if group is None:
                group = _ExamGroupBuilder(
                    course_code=course_code,
                    course_name=canonical_course_name[course_code],
                    exam_date=exam_date,
                    time_slot=time_slot,
                    day_label=day_label,
                    expected_student_count=expected_count,
                    line_number=line_number,
                )
                exam_groups[group_key] = group
            elif group.expected_student_count != expected_count:
                conflicts.append(
                    Conflict(
                        "expected_student_count",
                        f"{course_code}|{exam_date.isoformat()}|{time_slot}",
                        line_number,
                        str(group.expected_student_count),
                        str(expected_count),
                    )
                )

            is_duplicate, room_conflict = group.add_room(room_code, allocation, line_number)
            if room_conflict is not None:
                conflicts.append(room_conflict)
            elif is_duplicate:
                duplicate_rows += 1
    except csv.Error as exc:
        validation_errors.append(ValidationError(None, None, f"Malformed CSV: {exc}"))

    return ParsedScheduleCSV(
        rows_read=rows_read,
        exam_groups=[g.to_record() for g in exam_groups.values()],
        validation_errors=validation_errors,
        conflicts=conflicts,
        duplicate_rows=duplicate_rows,
    )
