"""ExaminationSessionService: validates and persists an ExaminationSession
from a set of existing exam ids.

Follows the exact order the Phase 9 spec lays out — load exams, validate
they exist, validate same date, validate same time slot, build the
participant set, reject duplicate students, validate room compatibility,
create the session — so a caller always finds out about the *first*
real problem with their requested combination of exams, not just
whichever one this implementation happened to check last.

Never duplicates course/student-count/room-capacity/schedule data onto
the session itself — it only ever stores which exams belong to it
(`SessionExamModel`), the same way `ExamRoom` references `Room` rather
than copying its capacity.
"""

from app.domain import (
    ExaminationSession,
    ExamRoomAllocation,
    Student,
    build_examination_session,
    build_session_participants,
    validate_no_conflicting_room_usage,
)
from app.repositories.exam_repository import ExamRepository
from app.repositories.exam_room_repository import ExamRoomRepository
from app.repositories.examination_session_repository import ExaminationSessionRepository
from app.repositories.registration_repository import RegistrationRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.student_repository import StudentRepository
from app.services.seating_generation.records import ExamNotFoundError


class ExaminationSessionService:
    def __init__(
        self,
        exam_repository: ExamRepository,
        exam_room_repository: ExamRoomRepository,
        room_repository: RoomRepository,
        registration_repository: RegistrationRepository,
        student_repository: StudentRepository,
        examination_session_repository: ExaminationSessionRepository,
    ) -> None:
        self._exams = exam_repository
        self._exam_rooms = exam_room_repository
        self._rooms = room_repository
        self._registrations = registration_repository
        self._students = student_repository
        self._sessions = examination_session_repository

    def create_session(self, exam_ids: list[int]) -> ExaminationSession:
        if not exam_ids:
            raise ValueError("An examination session needs at least one exam id.")
        if len(exam_ids) != len(set(exam_ids)):
            raise ValueError(f"Duplicate exam id(s) in request: {exam_ids}.")

        exams = []
        for exam_id in exam_ids:
            exam = self._exams.get(exam_id)
            if exam is None:
                raise ExamNotFoundError(exam_id)
            assert exam.id is not None
            exams.append(exam)

        # Same date + same time slot (IncompatibleExamScheduleError otherwise).
        draft = build_examination_session(exams)

        # A room shared by two or more of these exams must not be
        # over-committed beyond its physical capacity
        # (ConflictingRoomAllocationError otherwise) — checked before
        # loading registrations, since it's the cheaper check.
        exam_room_allocations = []
        for exam in exams:
            for exam_room in self._exam_rooms.list_by_exam(exam.id):
                room = self._rooms.get(exam_room.room_id)
                assert room is not None
                exam_room_allocations.append(
                    ExamRoomAllocation(
                        exam_id=exam.id,
                        room_id=exam_room.room_id,
                        allocated_students=exam_room.allocated_students,
                        room_capacity=room.capacity,
                    )
                )
        validate_no_conflicting_room_usage(exam_room_allocations)

        # No student registered in more than one of the session's exams
        # (DuplicateStudentInSessionError otherwise) — computed for its
        # validation side effect; the participants themselves are rebuilt
        # at generation time from whatever is registered *then*, not
        # frozen at session-creation time.
        students_by_exam_id = {exam.id: self._registered_students(exam.course_id) for exam in exams}
        course_id_by_exam_id = {exam.id: exam.course_id for exam in exams}
        build_session_participants(draft, students_by_exam_id, course_id_by_exam_id)

        return self._sessions.add(draft)

    def _registered_students(self, course_id: int) -> list[Student]:
        registrations = self._registrations.list_by_course(course_id)
        students = []
        for registration in registrations:
            student = self._students.get(registration.student_id)
            assert student is not None
            students.append(student)
        return students
