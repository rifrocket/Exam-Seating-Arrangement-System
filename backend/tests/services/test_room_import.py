"""Tests for the room seed/import module, matching input/locations.csv's
lowercase `room,capacity` (with an ignored `index` column) shape. All data
here is synthetic.
"""

from sqlalchemy.orm import Session

from app.db.repositories import SqlAlchemyRoomRepository
from app.services.room_import import RoomImportService, RoomImportStatus

LOCATIONS_HEADER = "index,room,capacity\n"


def test_valid_room_import(db_session: Session) -> None:
    service = RoomImportService(SqlAlchemyRoomRepository(db_session))

    result = service.import_csv(LOCATIONS_HEADER + "1,101,40\n2,102,16\n")

    assert result.status == RoomImportStatus.SUCCESS
    assert result.rooms_created == 2
    assert SqlAlchemyRoomRepository(db_session).count() == 2


def test_reimporting_same_rooms_is_idempotent(db_session: Session) -> None:
    service = RoomImportService(SqlAlchemyRoomRepository(db_session))
    csv_text = LOCATIONS_HEADER + "1,101,40\n"

    service.import_csv(csv_text)
    db_session.commit()
    result = service.import_csv(csv_text)

    assert result.rooms_created == 0
    assert result.rooms_existing == 1
    assert SqlAlchemyRoomRepository(db_session).count() == 1


def test_conflicting_capacity_is_reported_and_not_overwritten(db_session: Session) -> None:
    service = RoomImportService(SqlAlchemyRoomRepository(db_session))
    service.import_csv(LOCATIONS_HEADER + "1,101,40\n")
    db_session.commit()

    result = service.import_csv(LOCATIONS_HEADER + "1,101,50\n")

    assert len(result.conflicts) == 1
    stored = SqlAlchemyRoomRepository(db_session).get_by_code("101")
    assert stored is not None
    assert stored.capacity == 40


def test_missing_required_column(db_session: Session) -> None:
    service = RoomImportService(SqlAlchemyRoomRepository(db_session))

    result = service.import_csv("index,room\n1,101\n")

    assert result.status == RoomImportStatus.FAILED
    assert "capacity" in result.validation_errors[0].message


def test_old_two_column_format_still_imports_with_no_topology(db_session: Session) -> None:
    """The pre-Milestone-8 format must keep working exactly as before —
    rooms imported this way simply have no configured topology."""
    service = RoomImportService(SqlAlchemyRoomRepository(db_session))

    result = service.import_csv(LOCATIONS_HEADER + "1,101,40\n")

    assert result.status == RoomImportStatus.SUCCESS
    stored = SqlAlchemyRoomRepository(db_session).get_by_code("101")
    assert stored is not None
    assert stored.has_topology is False


def test_topology_aware_csv_imports_rows_and_columns(db_session: Session) -> None:
    service = RoomImportService(SqlAlchemyRoomRepository(db_session))
    csv_text = "room,capacity,rows,columns\n401,10,2,5\n402,10,2,5\n"

    result = service.import_csv(csv_text)

    assert result.status == RoomImportStatus.SUCCESS
    assert result.rooms_created == 2
    room_repo = SqlAlchemyRoomRepository(db_session)
    room_401 = room_repo.get_by_code("401")
    assert room_401 is not None
    assert (room_401.rows, room_401.columns) == (2, 5)


def test_topology_mismatch_with_capacity_is_rejected(db_session: Session) -> None:
    service = RoomImportService(SqlAlchemyRoomRepository(db_session))
    csv_text = "room,capacity,rows,columns\n401,10,2,4\n"  # 2x4 = 8, not 10

    result = service.import_csv(csv_text)

    assert result.status == RoomImportStatus.PARTIAL
    assert len(result.validation_errors) == 1
    assert "does not match capacity" in result.validation_errors[0].message
    assert SqlAlchemyRoomRepository(db_session).get_by_code("401") is None  # rejected, not half-created


def test_only_one_of_rows_or_columns_given_is_rejected(db_session: Session) -> None:
    service = RoomImportService(SqlAlchemyRoomRepository(db_session))
    csv_text = "room,capacity,rows,columns\n401,10,2,\n"

    result = service.import_csv(csv_text)

    assert result.status == RoomImportStatus.PARTIAL
    assert "both rows and columns" in result.validation_errors[0].message


def test_existing_room_without_topology_gets_backfilled_on_reimport(db_session: Session) -> None:
    """Nothing is being overwritten here — the room simply had no
    topology configured until this import."""
    service = RoomImportService(SqlAlchemyRoomRepository(db_session))
    service.import_csv(LOCATIONS_HEADER + "1,401,10\n")
    db_session.commit()

    result = service.import_csv("room,capacity,rows,columns\n401,10,2,5\n")

    assert result.rooms_existing == 1
    assert result.conflicts == []
    stored = SqlAlchemyRoomRepository(db_session).get_by_code("401")
    assert stored is not None
    assert (stored.rows, stored.columns) == (2, 5)


def test_conflicting_topology_on_existing_room_is_reported_and_not_overwritten(db_session: Session) -> None:
    service = RoomImportService(SqlAlchemyRoomRepository(db_session))
    service.import_csv("room,capacity,rows,columns\n401,10,2,5\n")
    db_session.commit()

    result = service.import_csv("room,capacity,rows,columns\n401,10,1,10\n")

    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "room_topology"
    stored = SqlAlchemyRoomRepository(db_session).get_by_code("401")
    assert stored is not None
    assert (stored.rows, stored.columns) == (2, 5)  # unchanged


def test_capacity_conflict_kind_is_reported_correctly(db_session: Session) -> None:
    service = RoomImportService(SqlAlchemyRoomRepository(db_session))
    service.import_csv(LOCATIONS_HEADER + "1,101,40\n")
    db_session.commit()

    result = service.import_csv(LOCATIONS_HEADER + "1,101,50\n")

    assert result.conflicts[0].kind == "room_capacity"
