from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.schemas import ConflictOut, ScheduleImportResponse, ValidationErrorOut, WarningOut
from app.db.repositories import (
    SqlAlchemyCourseRepository,
    SqlAlchemyExamRepository,
    SqlAlchemyExamRoomRepository,
    SqlAlchemyRoomRepository,
)
from app.db.session import get_db_session
from app.services.schedule_import import ScheduleImportService

router = APIRouter(tags=["schedules"])


def _schedule_import_service(session: Session = Depends(get_db_session)) -> ScheduleImportService:
    return ScheduleImportService(
        course_repository=SqlAlchemyCourseRepository(session),
        room_repository=SqlAlchemyRoomRepository(session),
        exam_repository=SqlAlchemyExamRepository(session),
        exam_room_repository=SqlAlchemyExamRoomRepository(session),
    )


@router.post("/schedules/import", response_model=ScheduleImportResponse)
async def import_schedule(
    file: UploadFile,
    session: Session = Depends(get_db_session),
    service: ScheduleImportService = Depends(_schedule_import_service),
) -> ScheduleImportResponse:
    raw_bytes = await file.read()
    try:
        csv_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Uploaded file must be UTF-8 encoded text.") from exc

    result = service.import_csv(csv_text)
    session.commit()

    return ScheduleImportResponse(
        status=result.status.value,
        rows_read=result.rows_read,
        exams_created=result.exams_created,
        exams_existing=result.exams_existing,
        exam_rooms_created=result.exam_rooms_created,
        exam_rooms_existing=result.exam_rooms_existing,
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
        warnings=[WarningOut(kind=w.kind, line_number=w.line_number, message=w.message) for w in result.warnings],
    )
