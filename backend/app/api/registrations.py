from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.schemas import (
    ConflictOut,
    CourseListResponse,
    CourseOut,
    PageMeta,
    RegistrationImportResponse,
    RegistrationListResponse,
    RegistrationOut,
    StudentListResponse,
    StudentOut,
    ValidationErrorOut,
)
from app.db.repositories import (
    SqlAlchemyCourseRepository,
    SqlAlchemyRegistrationRepository,
    SqlAlchemyStudentRepository,
)
from app.db.session import get_db_session
from app.services.registration_import import RegistrationImportService

router = APIRouter(tags=["registrations"])

MAX_PAGE_SIZE = 200


def _import_service(session: Session = Depends(get_db_session)) -> RegistrationImportService:
    return RegistrationImportService(
        student_repository=SqlAlchemyStudentRepository(session),
        course_repository=SqlAlchemyCourseRepository(session),
        registration_repository=SqlAlchemyRegistrationRepository(session),
    )


@router.post("/registrations/import", response_model=RegistrationImportResponse)
async def import_registrations(
    file: UploadFile,
    session: Session = Depends(get_db_session),
    service: RegistrationImportService = Depends(_import_service),
) -> RegistrationImportResponse:
    raw_bytes = await file.read()
    try:
        csv_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Uploaded file must be UTF-8 encoded text.") from exc

    result = service.import_csv(csv_text)
    session.commit()

    return RegistrationImportResponse(
        status=result.status.value,
        rows_read=result.rows_read,
        students_created=result.students_created,
        students_existing=result.students_existing,
        courses_created=result.courses_created,
        courses_existing=result.courses_existing,
        registrations_created=result.registrations_created,
        registrations_existing=result.registrations_existing,
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


@router.get("/students", response_model=StudentListResponse)
def list_students(
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> StudentListResponse:
    repo = SqlAlchemyStudentRepository(session)
    items = repo.list(limit=limit, offset=offset)
    total = repo.count()
    return StudentListResponse(
        items=[StudentOut(id=s.id, student_number=s.student_number, full_name=s.full_name) for s in items],
        meta=PageMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/courses", response_model=CourseListResponse)
def list_courses(
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> CourseListResponse:
    repo = SqlAlchemyCourseRepository(session)
    items = repo.list(limit=limit, offset=offset)
    total = repo.count()
    return CourseListResponse(
        items=[CourseOut(id=c.id, code=c.code, name=c.name) for c in items],
        meta=PageMeta(total=total, limit=limit, offset=offset),
    )


@router.get("/registrations", response_model=RegistrationListResponse)
def list_registrations(
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> RegistrationListResponse:
    repo = SqlAlchemyRegistrationRepository(session)
    items = repo.list(limit=limit, offset=offset)
    total = repo.count()
    return RegistrationListResponse(
        items=[RegistrationOut(id=r.id, student_id=r.student_id, course_id=r.course_id) for r in items],
        meta=PageMeta(total=total, limit=limit, offset=offset),
    )
