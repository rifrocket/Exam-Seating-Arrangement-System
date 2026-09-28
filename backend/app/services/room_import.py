"""Room seed/import: parses the `input/locations.csv` shape (room, capacity)
and persists Rooms idempotently.

Deliberately a single small module, not a package like registration_import/
or schedule_import/ — rooms are a small, no-cross-reference import, so the
same three-layer split (parser / result / service) fits in one file
without the extra module ceremony being worth it.

An optional leading `index` column (present in the legacy CSV) is accepted
and ignored. Column names are matched case-insensitively so the legacy
file's lowercase `room,capacity` header works without renaming it.

Milestone 8 adds optional `rows`/`columns` columns (both, or the header
can omit both entirely — the pre-Milestone-8 two-column format must keep
working exactly as before). A row supplying only one of the two, or a
combination that doesn't multiply out to that row's capacity, is a
validation error for that row (its topology is rejected, never truncated
or guessed at) — matching how an invalid capacity value already rejects
the whole row. A room that already exists without topology gets it
backfilled from a later import row (nothing is being overwritten, since
there was nothing there before); a room that already *has* topology and
the row disagrees is reported as a conflict, the same policy already
applied to capacity.

Milestone 10 adds one more optional column, `BlockedSeats` — a
semicolon-separated list of seat numbers *within that row's own topology*
(e.g. `7;17`), only meaningful on a row that also specifies rows/columns
(blocked seat numbers are meaningless without a layout to number seats
against). Same policy as rows/columns: an existing room with no blocked
seats configured gets them backfilled; one that already has different
blocked seats reports a `room_blocked_seats` conflict rather than
overwriting.
"""

import csv
from dataclasses import dataclass, field
from enum import Enum
from io import StringIO

from app.domain import InvalidRoomTopologyError, Room
from app.repositories.room_repository import RoomRepository

REQUIRED_COLUMNS = {"room", "capacity"}
OPTIONAL_TOPOLOGY_COLUMNS = {"rows", "columns"}
OPTIONAL_BLOCKED_SEATS_COLUMN = "blockedseats"


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
    kind: str = "room_capacity"


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
    rows: int | None
    columns: int | None
    blocked_seat_numbers: tuple[int, ...]


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

    # Both-or-neither: a header with only one of "rows"/"columns" is
    # treated the same as having neither — topology stays entirely
    # optional, so a stray single column never turns into a confusing
    # "missing column" error for something optional in the first place.
    has_topology_columns = OPTIONAL_TOPOLOGY_COLUMNS <= field_lookup.keys()
    has_blocked_seats_column = OPTIONAL_BLOCKED_SEATS_COLUMN in field_lookup

    validation_errors: list[RoomValidationError] = []
    conflicts: list[RoomConflict] = []
    rows: list[_ParsedRoomRow] = []
    # code -> (capacity, rows, columns, blocked_seat_numbers)
    seen: dict[str, tuple[int, int | None, int | None, tuple[int, ...]]] = {}
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

        topology_rows: int | None = None
        topology_columns: int | None = None
        if has_topology_columns:
            rows_raw = (row.get(field_lookup["rows"]) or "").strip()
            columns_raw = (row.get(field_lookup["columns"]) or "").strip()
            if rows_raw or columns_raw:
                if not rows_raw or not columns_raw:
                    row_errors.append(
                        RoomValidationError(line_number, "rows", "Specify both rows and columns, or neither.")
                    )
                else:
                    try:
                        topology_rows = int(rows_raw)
                        topology_columns = int(columns_raw)
                        if topology_rows < 1 or topology_columns < 1:
                            row_errors.append(
                                RoomValidationError(line_number, "rows", "rows and columns must be at least 1.")
                            )
                            topology_rows = topology_columns = None
                        elif capacity is not None and topology_rows * topology_columns != capacity:
                            row_errors.append(
                                RoomValidationError(
                                    line_number,
                                    "rows",
                                    f"rows ({topology_rows}) x columns ({topology_columns}) = "
                                    f"{topology_rows * topology_columns}, which does not match capacity "
                                    f"({capacity}).",
                                )
                            )
                            topology_rows = topology_columns = None
                    except ValueError:
                        row_errors.append(
                            RoomValidationError(line_number, "rows", f"Invalid rows/columns: '{rows_raw}'/'{columns_raw}'.")
                        )

        blocked_seat_numbers: tuple[int, ...] = ()
        if has_blocked_seats_column:
            blocked_raw = (row.get(field_lookup[OPTIONAL_BLOCKED_SEATS_COLUMN]) or "").strip()
            if blocked_raw:
                if topology_rows is None or topology_columns is None:
                    row_errors.append(
                        RoomValidationError(
                            line_number,
                            "blockedseats",
                            "Blocked seats require this row to also specify rows and columns.",
                        )
                    )
                else:
                    parsed_blocked: set[int] = set()
                    seat_capacity = topology_rows * topology_columns
                    for token in blocked_raw.split(";"):
                        token = token.strip()
                        if not token:
                            continue
                        try:
                            seat_number = int(token)
                        except ValueError:
                            row_errors.append(
                                RoomValidationError(
                                    line_number, "blockedseats", f"Invalid blocked seat number: '{token}'."
                                )
                            )
                            break
                        if not (1 <= seat_number <= seat_capacity):
                            row_errors.append(
                                RoomValidationError(
                                    line_number,
                                    "blockedseats",
                                    f"Blocked seat number {seat_number} is out of range (1..{seat_capacity}).",
                                )
                            )
                            break
                        parsed_blocked.add(seat_number)
                    else:
                        blocked_seat_numbers = tuple(sorted(parsed_blocked))

        if row_errors:
            validation_errors.extend(row_errors)
            continue
        assert capacity is not None

        if code in seen:
            existing_capacity, existing_rows, existing_columns, existing_blocked = seen[code]
            if (
                existing_capacity != capacity
                or (existing_rows, existing_columns) != (topology_rows, topology_columns)
                or existing_blocked != blocked_seat_numbers
            ):
                conflicts.append(RoomConflict(code, line_number, str(existing_capacity), str(capacity)))
            else:
                duplicate_rows += 1
            continue

        seen[code] = (capacity, topology_rows, topology_columns, blocked_seat_numbers)
        rows.append(
            _ParsedRoomRow(line_number, code, capacity, topology_rows, topology_columns, blocked_seat_numbers)
        )

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
                capacity_conflict = existing.capacity != row.capacity
                if capacity_conflict:
                    result.conflicts.append(
                        RoomConflict(
                            row.code, row.line_number, str(existing.capacity), str(row.capacity), kind="room_capacity"
                        )
                    )
                # Tracks whether, after this row, the room's *effective*
                # topology is known to equal row.rows/row.columns — only
                # then is it safe to backfill blocked seats against that
                # same layout below.
                topology_confirmed = False
                if row.rows is not None and row.columns is not None:
                    if existing.has_topology:
                        if (existing.rows, existing.columns) != (row.rows, row.columns):
                            result.conflicts.append(
                                RoomConflict(
                                    f"{row.code}:topology",
                                    row.line_number,
                                    f"{existing.rows}x{existing.columns}",
                                    f"{row.rows}x{row.columns}",
                                    kind="room_topology",
                                )
                            )
                        else:
                            topology_confirmed = True
                    elif capacity_conflict:
                        # The row's rows x columns was only validated
                        # against the row's own (disagreeing) capacity —
                        # applying it to the existing, different capacity
                        # could violate rows x columns == capacity. The
                        # capacity conflict above already reports the
                        # disagreement; don't also guess at a topology.
                        result.validation_errors.append(
                            RoomValidationError(
                                row.line_number,
                                "rows",
                                f"Room '{row.code}' already has capacity {existing.capacity}, which disagrees "
                                f"with this row's capacity ({row.capacity}) — its topology was not applied.",
                            )
                        )
                    else:
                        # Nothing is being overwritten — this room simply
                        # had no topology configured until now.
                        assert existing.id is not None
                        self._rooms.set_topology(existing.id, row.rows, row.columns)
                        topology_confirmed = True
                elif existing.has_topology:
                    topology_confirmed = True  # row didn't touch topology; the existing one still applies

                if row.blocked_seat_numbers:
                    if existing.blocked_seat_numbers:
                        if existing.blocked_seat_numbers != row.blocked_seat_numbers:
                            result.conflicts.append(
                                RoomConflict(
                                    f"{row.code}:blocked_seats",
                                    row.line_number,
                                    ",".join(str(n) for n in existing.blocked_seat_numbers),
                                    ",".join(str(n) for n in row.blocked_seat_numbers),
                                    kind="room_blocked_seats",
                                )
                            )
                    elif topology_confirmed:
                        # Nothing is being overwritten — this room simply
                        # had no blocked seats configured until now.
                        assert existing.id is not None
                        self._rooms.set_blocked_seats(existing.id, row.blocked_seat_numbers)
                    else:
                        result.validation_errors.append(
                            RoomValidationError(
                                row.line_number,
                                "blockedseats",
                                f"Room '{row.code}' does not have a confirmed matching topology on this row — "
                                "blocked seats were not applied.",
                            )
                        )
                result.rooms_existing += 1
            else:
                try:
                    self._rooms.add(
                        Room(
                            id=None,
                            code=row.code,
                            capacity=row.capacity,
                            rows=row.rows,
                            columns=row.columns,
                            blocked_seat_numbers=row.blocked_seat_numbers,
                        )
                    )
                except InvalidRoomTopologyError as exc:
                    result.validation_errors.append(RoomValidationError(row.line_number, "rows", str(exc)))
                    continue
                result.rooms_created += 1

        if result.validation_errors or result.conflicts:
            result.status = RoomImportStatus.PARTIAL
        return result
