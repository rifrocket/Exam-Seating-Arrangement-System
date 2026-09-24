"""Report endpoints. Read-only over an existing SeatingGeneration — never
triggers seating generation as a side effect (see ReportService's
docstring for the invariant this guarantees)."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.repositories import (
    SqlAlchemyCourseRepository,
    SqlAlchemyExamRepository,
    SqlAlchemyExamRoomRepository,
    SqlAlchemyRoomRepository,
    SqlAlchemySeatAssignmentRepository,
    SqlAlchemySeatingGenerationRepository,
    SqlAlchemyStudentRepository,
)
from app.db.session import get_db_session
from app.reports import render_ranges_report, render_seating_report
from app.services.reports import EmptyGenerationError, GenerationNotFoundError, ReportService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reports"])


def _report_service(session: Session = Depends(get_db_session)) -> ReportService:
    return ReportService(
        seating_generation_repository=SqlAlchemySeatingGenerationRepository(session),
        seat_assignment_repository=SqlAlchemySeatAssignmentRepository(session),
        exam_repository=SqlAlchemyExamRepository(session),
        exam_room_repository=SqlAlchemyExamRoomRepository(session),
        course_repository=SqlAlchemyCourseRepository(session),
        room_repository=SqlAlchemyRoomRepository(session),
        student_repository=SqlAlchemyStudentRepository(session),
    )


def _pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/seating/generations/{generation_id}/reports/seating")
def get_seating_report(
    generation_id: int,
    service: ReportService = Depends(_report_service),
) -> Response:
    try:
        data = service.build_seating_report_data(generation_id)
    except GenerationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EmptyGenerationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        pdf_bytes = render_seating_report(data)
    except Exception as exc:
        logger.exception("Failed to render seating report for generation %s", generation_id)
        raise HTTPException(status_code=500, detail="Failed to generate the seating report PDF.") from exc

    return _pdf_response(pdf_bytes, f"seating-generation-{generation_id}.pdf")


@router.get("/seating/generations/{generation_id}/reports/ranges")
def get_ranges_report(
    generation_id: int,
    service: ReportService = Depends(_report_service),
) -> Response:
    try:
        data = service.build_range_report_data(generation_id)
    except GenerationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EmptyGenerationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        pdf_bytes = render_ranges_report(data)
    except Exception as exc:
        logger.exception("Failed to render ranges report for generation %s", generation_id)
        raise HTTPException(status_code=500, detail="Failed to generate the ID range report PDF.") from exc

    return _pdf_response(pdf_bytes, f"ranges-generation-{generation_id}.pdf")
