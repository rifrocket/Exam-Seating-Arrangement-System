"""SQLAlchemy-backed implementations of the repository interfaces.

Each class converts between the ORM models in app.db.models and the plain
dataclasses in app.domain — nothing outside this module (services,
seating, api) ever sees a *Model class or a SQLAlchemy Session directly
through these repositories' public methods.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    CourseModel,
    ExamModel,
    ExamRoomModel,
    RegistrationModel,
    RoomModel,
    SeatAssignmentModel,
    SeatingGenerationModel,
    StudentModel,
)
from app.domain import (
    Course,
    Exam,
    ExamRoom,
    GenerationStatus,
    Registration,
    Room,
    SeatAssignment,
    SeatingGeneration,
    Student,
)
from app.repositories.course_repository import CourseRepository
from app.repositories.exam_repository import ExamRepository
from app.repositories.exam_room_repository import ExamRoomRepository
from app.repositories.registration_repository import RegistrationRepository
from app.repositories.room_repository import RoomRepository
from app.repositories.seat_assignment_repository import SeatAssignmentRepository
from app.repositories.seating_generation_repository import SeatingGenerationRepository
from app.repositories.student_repository import StudentRepository


def _student_to_domain(model: StudentModel) -> Student:
    return Student(id=model.id, student_number=model.student_number, full_name=model.full_name)


def _course_to_domain(model: CourseModel) -> Course:
    return Course(id=model.id, code=model.code, name=model.name)


def _registration_to_domain(model: RegistrationModel) -> Registration:
    return Registration(id=model.id, student_id=model.student_id, course_id=model.course_id)


def _room_to_domain(model: RoomModel) -> Room:
    return Room(id=model.id, code=model.code, capacity=model.capacity)


def _exam_to_domain(model: ExamModel) -> Exam:
    return Exam(
        id=model.id,
        course_id=model.course_id,
        exam_date=model.exam_date,
        time_slot=model.time_slot,
        expected_student_count=model.expected_student_count,
        day_label=model.day_label,
    )


def _exam_room_to_domain(model: ExamRoomModel) -> ExamRoom:
    return ExamRoom(
        id=model.id,
        exam_id=model.exam_id,
        room_id=model.room_id,
        allocated_students=model.allocated_students,
    )


def _seating_generation_to_domain(model: SeatingGenerationModel) -> SeatingGeneration:
    return SeatingGeneration(
        id=model.id,
        exam_id=model.exam_id,
        strategy_name=model.strategy_name,
        status=GenerationStatus(model.status),
        total_registered=model.total_registered,
        total_assigned=model.total_assigned,
        total_unassigned=model.total_unassigned,
        capacity_shortage=model.capacity_shortage,
        warnings=list(model.warnings or []),
        created_at=model.created_at,
    )


def _seat_assignment_to_domain(model: SeatAssignmentModel) -> SeatAssignment:
    return SeatAssignment(
        id=model.id,
        seating_generation_id=model.seating_generation_id,
        exam_id=model.exam_id,
        room_id=model.room_id,
        student_id=model.student_id,
        seat_number=model.seat_number,
    )


class SqlAlchemyStudentRepository(StudentRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, entity_id: int) -> Student | None:
        model = self._session.get(StudentModel, entity_id)
        return _student_to_domain(model) if model else None

    def get_by_student_number(self, student_number: str) -> Student | None:
        model = self._session.scalar(select(StudentModel).where(StudentModel.student_number == student_number))
        return _student_to_domain(model) if model else None

    def list(self, limit: int | None = None, offset: int = 0) -> list[Student]:
        stmt = select(StudentModel).order_by(StudentModel.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [_student_to_domain(m) for m in self._session.scalars(stmt)]

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(StudentModel)) or 0

    def add(self, entity: Student) -> Student:
        model = StudentModel(student_number=entity.student_number, full_name=entity.full_name)
        self._session.add(model)
        self._session.flush()
        return _student_to_domain(model)


class SqlAlchemyCourseRepository(CourseRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, entity_id: int) -> Course | None:
        model = self._session.get(CourseModel, entity_id)
        return _course_to_domain(model) if model else None

    def get_by_code(self, code: str) -> Course | None:
        model = self._session.scalar(select(CourseModel).where(CourseModel.code == code))
        return _course_to_domain(model) if model else None

    def list(self, limit: int | None = None, offset: int = 0) -> list[Course]:
        stmt = select(CourseModel).order_by(CourseModel.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [_course_to_domain(m) for m in self._session.scalars(stmt)]

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(CourseModel)) or 0

    def add(self, entity: Course) -> Course:
        model = CourseModel(code=entity.code, name=entity.name)
        self._session.add(model)
        self._session.flush()
        return _course_to_domain(model)


class SqlAlchemyRegistrationRepository(RegistrationRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, entity_id: int) -> Registration | None:
        model = self._session.get(RegistrationModel, entity_id)
        return _registration_to_domain(model) if model else None

    def get_by_student_and_course(self, student_id: int, course_id: int) -> Registration | None:
        model = self._session.scalar(
            select(RegistrationModel).where(
                RegistrationModel.student_id == student_id,
                RegistrationModel.course_id == course_id,
            )
        )
        return _registration_to_domain(model) if model else None

    def list_by_course(self, course_id: int) -> list[Registration]:
        stmt = select(RegistrationModel).where(RegistrationModel.course_id == course_id)
        return [_registration_to_domain(m) for m in self._session.scalars(stmt)]

    def list_by_student(self, student_id: int) -> list[Registration]:
        stmt = select(RegistrationModel).where(RegistrationModel.student_id == student_id)
        return [_registration_to_domain(m) for m in self._session.scalars(stmt)]

    def list(self, limit: int | None = None, offset: int = 0) -> list[Registration]:
        stmt = select(RegistrationModel).order_by(RegistrationModel.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [_registration_to_domain(m) for m in self._session.scalars(stmt)]

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(RegistrationModel)) or 0

    def add(self, entity: Registration) -> Registration:
        model = RegistrationModel(student_id=entity.student_id, course_id=entity.course_id)
        self._session.add(model)
        self._session.flush()
        return _registration_to_domain(model)


class SqlAlchemyRoomRepository(RoomRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, entity_id: int) -> Room | None:
        model = self._session.get(RoomModel, entity_id)
        return _room_to_domain(model) if model else None

    def get_by_code(self, code: str) -> Room | None:
        model = self._session.scalar(select(RoomModel).where(RoomModel.code == code))
        return _room_to_domain(model) if model else None

    def list(self, limit: int | None = None, offset: int = 0) -> list[Room]:
        stmt = select(RoomModel).order_by(RoomModel.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [_room_to_domain(m) for m in self._session.scalars(stmt)]

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(RoomModel)) or 0

    def add(self, entity: Room) -> Room:
        model = RoomModel(code=entity.code, capacity=entity.capacity)
        self._session.add(model)
        self._session.flush()
        return _room_to_domain(model)


class SqlAlchemyExamRepository(ExamRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, entity_id: int) -> Exam | None:
        model = self._session.get(ExamModel, entity_id)
        return _exam_to_domain(model) if model else None

    def get_by_identity(self, course_id: int, exam_date: date, time_slot: str) -> Exam | None:
        model = self._session.scalar(
            select(ExamModel).where(
                ExamModel.course_id == course_id,
                ExamModel.exam_date == exam_date,
                ExamModel.time_slot == time_slot,
            )
        )
        return _exam_to_domain(model) if model else None

    def list_by_course(self, course_id: int) -> list[Exam]:
        stmt = select(ExamModel).where(ExamModel.course_id == course_id)
        return [_exam_to_domain(m) for m in self._session.scalars(stmt)]

    def list(self, limit: int | None = None, offset: int = 0) -> list[Exam]:
        stmt = select(ExamModel).order_by(ExamModel.exam_date, ExamModel.time_slot).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [_exam_to_domain(m) for m in self._session.scalars(stmt)]

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(ExamModel)) or 0

    def add(self, entity: Exam) -> Exam:
        model = ExamModel(
            course_id=entity.course_id,
            exam_date=entity.exam_date,
            time_slot=entity.time_slot,
            expected_student_count=entity.expected_student_count,
            day_label=entity.day_label,
        )
        self._session.add(model)
        self._session.flush()
        return _exam_to_domain(model)


class SqlAlchemyExamRoomRepository(ExamRoomRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, entity_id: int) -> ExamRoom | None:
        model = self._session.get(ExamRoomModel, entity_id)
        return _exam_room_to_domain(model) if model else None

    def get_by_exam_and_room(self, exam_id: int, room_id: int) -> ExamRoom | None:
        model = self._session.scalar(
            select(ExamRoomModel).where(
                ExamRoomModel.exam_id == exam_id,
                ExamRoomModel.room_id == room_id,
            )
        )
        return _exam_room_to_domain(model) if model else None

    def list_by_exam(self, exam_id: int) -> list[ExamRoom]:
        # Ordered by id (= insertion/import order) so the seating engine's
        # room-fill sequence is deterministic and reproducible, not left to
        # an unspecified database row order.
        stmt = select(ExamRoomModel).where(ExamRoomModel.exam_id == exam_id).order_by(ExamRoomModel.id)
        return [_exam_room_to_domain(m) for m in self._session.scalars(stmt)]

    def list(self, limit: int | None = None, offset: int = 0) -> list[ExamRoom]:
        stmt = select(ExamRoomModel).order_by(ExamRoomModel.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [_exam_room_to_domain(m) for m in self._session.scalars(stmt)]

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(ExamRoomModel)) or 0

    def add(self, entity: ExamRoom) -> ExamRoom:
        model = ExamRoomModel(
            exam_id=entity.exam_id,
            room_id=entity.room_id,
            allocated_students=entity.allocated_students,
        )
        self._session.add(model)
        self._session.flush()
        return _exam_room_to_domain(model)


class SqlAlchemySeatingGenerationRepository(SeatingGenerationRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, entity_id: int) -> SeatingGeneration | None:
        model = self._session.get(SeatingGenerationModel, entity_id)
        return _seating_generation_to_domain(model) if model else None

    def list_by_exam(self, exam_id: int) -> list[SeatingGeneration]:
        stmt = select(SeatingGenerationModel).where(SeatingGenerationModel.exam_id == exam_id).order_by(
            SeatingGenerationModel.id
        )
        return [_seating_generation_to_domain(m) for m in self._session.scalars(stmt)]

    def list(self, limit: int | None = None, offset: int = 0) -> list[SeatingGeneration]:
        stmt = select(SeatingGenerationModel).order_by(SeatingGenerationModel.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [_seating_generation_to_domain(m) for m in self._session.scalars(stmt)]

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(SeatingGenerationModel)) or 0

    def add(self, entity: SeatingGeneration) -> SeatingGeneration:
        model = SeatingGenerationModel(
            exam_id=entity.exam_id,
            strategy_name=entity.strategy_name,
            status=entity.status.value,
            total_registered=entity.total_registered,
            total_assigned=entity.total_assigned,
            total_unassigned=entity.total_unassigned,
            capacity_shortage=entity.capacity_shortage,
            warnings=list(entity.warnings),
        )
        self._session.add(model)
        self._session.flush()
        self._session.refresh(model)
        return _seating_generation_to_domain(model)


class SqlAlchemySeatAssignmentRepository(SeatAssignmentRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, entity_id: int) -> SeatAssignment | None:
        model = self._session.get(SeatAssignmentModel, entity_id)
        return _seat_assignment_to_domain(model) if model else None

    def list_by_generation(self, seating_generation_id: int) -> list[SeatAssignment]:
        stmt = (
            select(SeatAssignmentModel)
            .where(SeatAssignmentModel.seating_generation_id == seating_generation_id)
            .order_by(SeatAssignmentModel.room_id, SeatAssignmentModel.seat_number)
        )
        return [_seat_assignment_to_domain(m) for m in self._session.scalars(stmt)]

    def list(self, limit: int | None = None, offset: int = 0) -> list[SeatAssignment]:
        stmt = select(SeatAssignmentModel).order_by(SeatAssignmentModel.id).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [_seat_assignment_to_domain(m) for m in self._session.scalars(stmt)]

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(SeatAssignmentModel)) or 0

    def add(self, entity: SeatAssignment) -> SeatAssignment:
        model = SeatAssignmentModel(
            seating_generation_id=entity.seating_generation_id,
            exam_id=entity.exam_id,
            room_id=entity.room_id,
            student_id=entity.student_id,
            seat_number=entity.seat_number,
        )
        self._session.add(model)
        self._session.flush()
        return _seat_assignment_to_domain(model)
