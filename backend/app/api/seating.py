from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import (
    PageMeta,
    SeatAssignmentListResponse,
    SeatAssignmentOut,
    SeatingGenerateRequest,
    SeatingGenerationListResponse,
    SeatingGenerationOut,
    SeatingGenerationResponse,
)
from app.db.repositories import (
    SqlAlchemyCourseRepository,
    SqlAlchemyExamRepository,
    SqlAlchemyExamRoomRepository,
    SqlAlchemyRegistrationRepository,
    SqlAlchemyRoomRepository,
    SqlAlchemySeatAssignmentRepository,
    SqlAlchemySeatingGenerationRepository,
    SqlAlchemyStudentRepository,
)
from app.db.session import get_db_session
from app.domain import SeatingGeneration
from app.seating import UnknownStrategyError
from app.services.seating_generation import ExamNotFoundError, SeatingService

router = APIRouter(tags=["seating"])


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
    )


def _to_generation_out(generation: SeatingGeneration) -> SeatingGenerationOut:
    assert generation.id is not None
    return SeatingGenerationOut(
        id=generation.id,
        exam_id=generation.exam_id,
        strategy_name=generation.strategy_name,
        status=generation.status.value,
        total_registered=generation.total_registered,
        total_assigned=generation.total_assigned,
        total_unassigned=generation.total_unassigned,
        capacity_shortage=generation.capacity_shortage,
        warnings=generation.warnings,
        created_at=generation.created_at,
    )


@router.post("/exams/{exam_id}/seating/generate", response_model=SeatingGenerationResponse)
def generate_seating(
    exam_id: int,
    request: SeatingGenerateRequest | None = None,
    session: Session = Depends(get_db_session),
    service: SeatingService = Depends(_seating_service),
) -> SeatingGenerationResponse:
    strategy_name = request.strategy if request is not None else "sequential"
    try:
        outcome = service.generate(exam_id, strategy_name=strategy_name)
    except ExamNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnknownStrategyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()

    base = _to_generation_out(outcome.generation)
    return SeatingGenerationResponse(
        **base.model_dump(),
        scheduled_student_count=outcome.scheduled_student_count,
        available_capacity=outcome.available_capacity,
        unassigned_student_ids=outcome.unassigned_student_ids,
    )


@router.get("/exams/{exam_id}/seating/generations", response_model=SeatingGenerationListResponse)
def list_generations(
    exam_id: int,
    session: Session = Depends(get_db_session),
) -> SeatingGenerationListResponse:
    repo = SqlAlchemySeatingGenerationRepository(session)
    items = [_to_generation_out(g) for g in repo.list_by_exam(exam_id)]
    return SeatingGenerationListResponse(items=items, meta=PageMeta(total=len(items), limit=max(len(items), 1), offset=0))


@router.get("/seating/generations/{generation_id}/assignments", response_model=SeatAssignmentListResponse)
def list_assignments(
    generation_id: int,
    session: Session = Depends(get_db_session),
) -> SeatAssignmentListResponse:
    generation_repo = SqlAlchemySeatingGenerationRepository(session)
    generation = generation_repo.get(generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Seating generation not found.")

    assignment_repo = SqlAlchemySeatAssignmentRepository(session)
    room_repo = SqlAlchemyRoomRepository(session)
    student_repo = SqlAlchemyStudentRepository(session)

    items = []
    for assignment in assignment_repo.list_by_generation(generation_id):
        room = room_repo.get(assignment.room_id)
        student = student_repo.get(assignment.student_id)
        assert room is not None
        assert student is not None
        items.append(
            SeatAssignmentOut(
                id=assignment.id,
                room_id=room.id,
                room_code=room.code,
                student_id=student.id,
                student_number=student.student_number,
                student_name=student.full_name,
                seat_number=assignment.seat_number,
            )
        )

    return SeatAssignmentListResponse(generation=_to_generation_out(generation), items=items)
