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
