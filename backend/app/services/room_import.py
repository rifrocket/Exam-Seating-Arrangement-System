"""Room seed/import: parses the `input/locations.csv` shape (room, capacity)
and persists Rooms idempotently.

Deliberately a single small module, not a package like registration_import/
or schedule_import/ — rooms are a two-column, no-cross-reference import,
so the same three-layer split (parser / result / service) fits in one
file without the extra module ceremony being worth it.

An optional leading `index` column (present in the legacy CSV) is accepted
and ignored. Column names are matched case-insensitively so the legacy
file's lowercase `room,capacity` header works without renaming it.
"""

import csv
from dataclasses import dataclass, field
from enum import Enum
from io import StringIO

from app.domain import Room
from app.repositories.room_repository import RoomRepository

REQUIRED_COLUMNS = {"room", "capacity"}


@dataclass(frozen=True)
class RoomValidationError:
    line_number: int | None
    field: str | None
    message: str


@dataclass(frozen=True)
class RoomConflict:
    key: str
    line_number: int
    existing_value: str
    incoming_value: str


class RoomImportStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class RoomImportResult:
    status: RoomImportStatus
    rows_read: int
    rooms_created: int = 0
    rooms_existing: int = 0
    duplicate_rows: int = 0
    validation_errors: list[RoomValidationError] = field(default_factory=list)
    conflicts: list[RoomConflict] = field(default_factory=list)


@dataclass(frozen=True)
class _ParsedRoomRow:
    line_number: int
    code: str
    capacity: int


def _parse_rooms_csv(
    csv_text: str,
) -> tuple[list[_ParsedRoomRow], list[RoomValidationError], list[RoomConflict], int, int]:
    reader = csv.DictReader(StringIO(csv_text))
    if reader.fieldnames is None:
        return [], [RoomValidationError(None, None, "CSV file is empty or has no header row.")], [], 0, 0

    field_lookup = {name.strip().lower(): name for name in reader.fieldnames if name is not None}
    missing = REQUIRED_COLUMNS - field_lookup.keys()
    if missing:
        message = f"Missing required column(s): {', '.join(sorted(missing))}."
        return [], [RoomValidationError(None, None, message)], [], 0, 0

    validation_errors: list[RoomValidationError] = []
    conflicts: list[RoomConflict] = []
    rows: list[_ParsedRoomRow] = []
    seen_capacity: dict[str, int] = {}
    duplicate_rows = 0
    rows_read = 0

    for line_number, row in enumerate(reader, start=2):
        rows_read += 1
        code = (row.get(field_lookup["room"]) or "").strip()
        capacity_raw = (row.get(field_lookup["capacity"]) or "").strip()

        row_errors = []
        if not code:
            row_errors.append(RoomValidationError(line_number, "room", "room must not be empty."))

        capacity: int | None = None
        try:
            capacity = int(capacity_raw)
            if capacity < 0:
                row_errors.append(RoomValidationError(line_number, "capacity", "capacity must not be negative."))
                capacity = None
        except ValueError:
            row_errors.append(RoomValidationError(line_number, "capacity", f"Invalid capacity: '{capacity_raw}'."))

        if row_errors:
            validation_errors.extend(row_errors)
            continue
        assert capacity is not None

        if code in seen_capacity:
            if seen_capacity[code] != capacity:
                conflicts.append(RoomConflict(code, line_number, str(seen_capacity[code]), str(capacity)))
            else:
                duplicate_rows += 1
            continue

        seen_capacity[code] = capacity
        rows.append(_ParsedRoomRow(line_number, code, capacity))

    return rows, validation_errors, conflicts, duplicate_rows, rows_read


class RoomImportService:
    def __init__(self, room_repository: RoomRepository) -> None:
        self._rooms = room_repository

    def import_csv(self, csv_text: str) -> RoomImportResult:
        rows, validation_errors, conflicts, duplicate_rows, rows_read = _parse_rooms_csv(csv_text)

        if not rows and validation_errors and rows_read == 0:
            return RoomImportResult(
                status=RoomImportStatus.FAILED,
                rows_read=rows_read,
                validation_errors=validation_errors,
                conflicts=conflicts,
                duplicate_rows=duplicate_rows,
            )

        result = RoomImportResult(
            status=RoomImportStatus.SUCCESS,
            rows_read=rows_read,
            validation_errors=list(validation_errors),
            conflicts=list(conflicts),
            duplicate_rows=duplicate_rows,
        )

        for row in rows:
            existing = self._rooms.get_by_code(row.code)
            if existing is not None:
                if existing.capacity != row.capacity:
                    result.conflicts.append(
                        RoomConflict(row.code, row.line_number, str(existing.capacity), str(row.capacity))
                    )
                result.rooms_existing += 1
            else:
                self._rooms.add(Room(id=None, code=row.code, capacity=row.capacity))
                result.rooms_created += 1

        if result.validation_errors or result.conflicts:
            result.status = RoomImportStatus.PARTIAL
        return result
