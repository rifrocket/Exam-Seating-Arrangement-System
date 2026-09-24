"""SQLAlchemy-backed implementations of the repository interfaces.

Each class converts between the ORM models in app.db.models and the plain
dataclasses in app.domain — nothing outside this module (services,
seating, api) ever sees a *Model class or a SQLAlchemy Session directly
through these repositories' public methods.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CourseModel, RegistrationModel, StudentModel
from app.domain import Course, Registration, Student
from app.repositories.course_repository import CourseRepository
from app.repositories.registration_repository import RegistrationRepository
from app.repositories.student_repository import StudentRepository


def _student_to_domain(model: StudentModel) -> Student:
    return Student(id=model.id, student_number=model.student_number, full_name=model.full_name)


def _course_to_domain(model: CourseModel) -> Course:
    return Course(id=model.id, code=model.code, name=model.name)


def _registration_to_domain(model: RegistrationModel) -> Registration:
    return Registration(id=model.id, student_id=model.student_id, course_id=model.course_id)


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
