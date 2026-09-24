from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.schemas import ExamDetailOut, ExamListResponse, ExamOut, ExamRoomOut, PageMeta
from app.db.repositories import (
    SqlAlchemyCourseRepository,
    SqlAlchemyExamRepository,
    SqlAlchemyExamRoomRepository,
    SqlAlchemyRoomRepository,
)
from app.db.session import get_db_session

router = APIRouter(tags=["exams"])

MAX_PAGE_SIZE = 200


@router.get("/exams", response_model=ExamListResponse)
def list_exams(
    limit: int = Query(default=50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> ExamListResponse:
    exam_repo = SqlAlchemyExamRepository(session)
    course_repo = SqlAlchemyCourseRepository(session)
    exam_room_repo = SqlAlchemyExamRoomRepository(session)

    exams = exam_repo.list(limit=limit, offset=offset)
    total = exam_repo.count()

    items = []
    for exam in exams:
        assert exam.id is not None
        course = course_repo.get(exam.course_id)
        assert course is not None
        room_count = len(exam_room_repo.list_by_exam(exam.id))
        items.append(
            ExamOut(
                id=exam.id,
                course_id=exam.course_id,
                course_code=course.code,
                course_name=course.name,
                exam_date=exam.exam_date,
                time_slot=exam.time_slot,
                day_label=exam.day_label,
                expected_student_count=exam.expected_student_count,
                room_count=room_count,
            )
        )
    return ExamListResponse(items=items, meta=PageMeta(total=total, limit=limit, offset=offset))


@router.get("/exams/{exam_id}", response_model=ExamDetailOut)
def get_exam(exam_id: int, session: Session = Depends(get_db_session)) -> ExamDetailOut:
    exam_repo = SqlAlchemyExamRepository(session)
    course_repo = SqlAlchemyCourseRepository(session)
    room_repo = SqlAlchemyRoomRepository(session)
    exam_room_repo = SqlAlchemyExamRoomRepository(session)

    exam = exam_repo.get(exam_id)
    if exam is None:
        raise HTTPException(status_code=404, detail="Exam not found.")

    course = course_repo.get(exam.course_id)
    assert course is not None

    exam_room_items = []
    for exam_room in exam_room_repo.list_by_exam(exam_id):
        room = room_repo.get(exam_room.room_id)
        assert room is not None
        exam_room_items.append(
            ExamRoomOut(
                id=exam_room.id,
                room_id=room.id,
                room_code=room.code,
                room_capacity=room.capacity,
                allocated_students=exam_room.allocated_students,
            )
        )

    return ExamDetailOut(
        id=exam.id,
        course_id=exam.course_id,
        course_code=course.code,
        course_name=course.name,
        exam_date=exam.exam_date,
        time_slot=exam.time_slot,
        day_label=exam.day_label,
        expected_student_count=exam.expected_student_count,
        exam_rooms=exam_room_items,
    )
