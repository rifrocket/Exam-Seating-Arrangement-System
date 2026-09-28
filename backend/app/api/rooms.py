from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.schemas import (
    ConflictOut,
    PageMeta,
    RoomImportResponse,
    RoomListResponse,
    RoomOut,
    ValidationErrorOut,
)
from app.db.repositories import SqlAlchemyRoomRepository
from app.db.session import get_db_session
from app.domain import Room
from app.services.room_import import RoomImportService

router = APIRouter(tags=["rooms"])

MAX_PAGE_SIZE = 200


def _to_room_out(room: Room) -> RoomOut:
    # Room is the only place blocking is remembered (see docs/architecture.md's
    # "Availability" section) — physical/usable capacity are therefore
    # always derived from its own rows/columns/blocked_seat_numbers here,
    # never a separately-configurable fact.
    physical_capacity = room.rows * room.columns if room.has_topology else None
    usable_capacity = (
        physical_capacity - len(room.blocked_seat_numbers) if physical_capacity is not None else None
    )
    return RoomOut(
        id=room.id,
        code=room.code,
        capacity=room.capacity,
        rows=room.rows,
        columns=room.columns,
        blocked_seat_numbers=list(room.blocked_seat_numbers),
        physical_capacity=physical_capacity,
        usable_capacity=usable_capacity,
    )


def _room_import_service(session: Session = Depends(get_db_session)) -> RoomImportService:
    return RoomImportService(room_repository=SqlAlchemyRoomRepository(session))


@router.post("/rooms/import", response_model=RoomImportResponse)
async def import_rooms(
    file: UploadFile,
    session: Session = Depends(get_db_session),
    service: RoomImportService = Depends(_room_import_service),
) -> RoomImportResponse:
    raw_bytes = await file.read()
    try:
        csv_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Uploaded file must be UTF-8 encoded text.") from exc

    result = service.import_csv(csv_text)
    session.commit()

    return RoomImportResponse(
        status=result.status.value,
        rows_read=result.rows_read,
        rooms_created=result.rooms_created,
        rooms_existing=result.rooms_existing,
        duplicate_rows=result.duplicate_rows,
        validation_errors=[
            ValidationErrorOut(line_number=e.line_number, field=e.field, message=e.message)
            for e in result.validation_errors
        ],
        conflicts=[
            ConflictOut(
                kind=c.kind,
                key=c.key,
                line_number=c.line_number,
                existing_value=c.existing_value,
                incoming_value=c.incoming_value,
            )
            for c in result.conflicts
        ],
    )


@router.get("/rooms", response_model=RoomListResponse)
def list_rooms(
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> RoomListResponse:
    repo = SqlAlchemyRoomRepository(session)
    items = repo.list(limit=limit, offset=offset)
    total = repo.count()
    return RoomListResponse(
        items=[_to_room_out(r) for r in items],
        meta=PageMeta(total=total, limit=limit, offset=offset),
    )
