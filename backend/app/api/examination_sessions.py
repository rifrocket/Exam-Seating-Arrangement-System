from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import (
    ExaminationSessionCreateRequest,
    ExaminationSessionExamOut,
    ExaminationSessionListResponse,
    ExaminationSessionOut,
    PageMeta,
    SeatingGenerationListResponse,
    SeatingGenerationResponse,
    SessionSeatingGenerateRequest,
)
from app.api.seating import _to_generation_out
from app.db.repositories import (
    SqlAlchemyCourseRepository,
    SqlAlchemyExaminationSessionRepository,
    SqlAlchemyExamRepository,
    SqlAlchemyExamRoomRepository,
    SqlAlchemyRegistrationRepository,
    SqlAlchemyRoomRepository,
    SqlAlchemySeatAssignmentRepository,
    SqlAlchemySeatingGenerationRepository,
    SqlAlchemyStudentRepository,
)
from app.db.session import get_db_session
from app.domain import ExaminationSession
from app.domain.examination_session import (
    ConflictingRoomAllocationError,
    DuplicateStudentInSessionError,
    IncompatibleExamScheduleError,
)
from app.seating import (
    RoomTopologyMismatchError,
    RoomTopologyMissingError,
    UnknownRoomTopologyError,
    UnknownStrategyError,
)
from app.services.examination_session import ExaminationSessionService
from app.services.seating_generation import SeatingService, SessionNotFoundError
from app.services.seating_generation.records import ExamNotFoundError

router = APIRouter(tags=["examination-sessions"])

MAX_PAGE_SIZE = 200


def _session_service(session: Session = Depends(get_db_session)) -> ExaminationSessionService:
    return ExaminationSessionService(
        exam_repository=SqlAlchemyExamRepository(session),
        exam_room_repository=SqlAlchemyExamRoomRepository(session),
        room_repository=SqlAlchemyRoomRepository(session),
        registration_repository=SqlAlchemyRegistrationRepository(session),
        student_repository=SqlAlchemyStudentRepository(session),
        examination_session_repository=SqlAlchemyExaminationSessionRepository(session),
    )


def _seating_service(session: Session = Depends(get_db_session)) -> SeatingService:
    return SeatingService(
        exam_repository=SqlAlchemyExamRepository(session),
        exam_room_repository=SqlAlchemyExamRoomRepository(session),
        room_repository=SqlAlchemyRoomRepository(session),
        course_repository=SqlAlchemyCourseRepository(session),
        registration_repository=SqlAlchemyRegistrationRepository(session),
        student_repository=SqlAlchemyStudentRepository(session),
        seating_generation_repository=SqlAlchemySeatingGenerationRepository(session),
        seat_assignment_repository=SqlAlchemySeatAssignmentRepository(session),
        examination_session_repository=SqlAlchemyExaminationSessionRepository(session),
    )


def _to_session_out(
    examination_session: ExaminationSession,
    session: Session,
) -> ExaminationSessionOut:
    """Builds the response by re-reading each referenced exam/course/room
    fresh — a session never copies that data onto itself, so there is
    nowhere else to read it from. `participant_count` and `room_codes`
    are therefore always current as of this request, not frozen at
    session-creation time."""
    assert examination_session.id is not None
    exam_repo = SqlAlchemyExamRepository(session)
    course_repo = SqlAlchemyCourseRepository(session)
    exam_room_repo = SqlAlchemyExamRoomRepository(session)
    room_repo = SqlAlchemyRoomRepository(session)
    registration_repo = SqlAlchemyRegistrationRepository(session)

    exams_out = []
    participant_count = 0
    room_codes: list[str] = []
    seen_room_ids: set[int] = set()
    for exam_id in examination_session.exam_ids:
        exam = exam_repo.get(exam_id)
        assert exam is not None
        course = course_repo.get(exam.course_id)
        assert course is not None
        exams_out.append(
            ExaminationSessionExamOut(
                exam_id=exam_id,
                course_id=course.id,
                course_code=course.code,
                course_name=course.name,
            )
        )
        participant_count += len(registration_repo.list_by_course(exam.course_id))
        for exam_room in exam_room_repo.list_by_exam(exam_id):
            if exam_room.room_id in seen_room_ids:
                continue
            seen_room_ids.add(exam_room.room_id)
            room = room_repo.get(exam_room.room_id)
            assert room is not None
            room_codes.append(room.code)

    return ExaminationSessionOut(
        id=examination_session.id,
        exam_date=examination_session.exam_date,
        time_slot=examination_session.time_slot,
        exams=exams_out,
        participant_count=participant_count,
        room_codes=room_codes,
    )


@router.post("/examination-sessions", response_model=ExaminationSessionOut)
def create_examination_session(
    request: ExaminationSessionCreateRequest,
    session: Session = Depends(get_db_session),
    service: ExaminationSessionService = Depends(_session_service),
) -> ExaminationSessionOut:
    try:
        examination_session = service.create_session(request.exam_ids)
    except ExamNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        IncompatibleExamScheduleError,
        ConflictingRoomAllocationError,
        DuplicateStudentInSessionError,
        ValueError,
    ) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return _to_session_out(examination_session, session)


@router.get("/examination-sessions", response_model=ExaminationSessionListResponse)
def list_examination_sessions(
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> ExaminationSessionListResponse:
    repo = SqlAlchemyExaminationSessionRepository(session)
    items = [_to_session_out(s, session) for s in repo.list(limit=limit, offset=offset)]
    return ExaminationSessionListResponse(items=items, meta=PageMeta(total=repo.count(), limit=limit, offset=offset))


@router.get("/examination-sessions/{session_id}", response_model=ExaminationSessionOut)
def get_examination_session(session_id: int, session: Session = Depends(get_db_session)) -> ExaminationSessionOut:
    repo = SqlAlchemyExaminationSessionRepository(session)
    examination_session = repo.get(session_id)
    if examination_session is None:
        raise HTTPException(status_code=404, detail="Examination session not found.")
    return _to_session_out(examination_session, session)


@router.get(
    "/examination-sessions/{session_id}/seating/generations", response_model=SeatingGenerationListResponse
)
def list_session_generations(
    session_id: int,
    session: Session = Depends(get_db_session),
) -> SeatingGenerationListResponse:
    repo = SqlAlchemySeatingGenerationRepository(session)
    items = [_to_generation_out(g) for g in repo.list_by_session(session_id)]
    return SeatingGenerationListResponse(items=items, meta=PageMeta(total=len(items), limit=max(len(items), 1), offset=0))


@router.post("/examination-sessions/{session_id}/seating/generate", response_model=SeatingGenerationResponse)
def generate_session_seating(
    session_id: int,
    request: SessionSeatingGenerateRequest | None = None,
    session: Session = Depends(get_db_session),
    service: SeatingService = Depends(_seating_service),
) -> SeatingGenerationResponse:
    strategy_name = request.strategy if request is not None else "constraint"
    try:
        outcome = service.generate_session(session_id, strategy_name=strategy_name)
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnknownStrategyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RoomTopologyMissingError, RoomTopologyMismatchError, UnknownRoomTopologyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()

    base = _to_generation_out(outcome.generation)
    return SeatingGenerationResponse(
        **base.model_dump(),
        scheduled_student_count=outcome.scheduled_student_count,
        total_physical_capacity=outcome.total_physical_capacity,
        available_capacity=outcome.available_capacity,
        unassigned_student_ids=outcome.unassigned_student_ids,
        scheduled_allocation_shortage=outcome.scheduled_allocation_shortage,
        physical_capacity_shortage=outcome.physical_capacity_shortage,
    )
