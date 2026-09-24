from abc import abstractmethod
from datetime import date

from app.domain import Exam
from app.repositories.base import Repository


class ExamRepository(Repository[Exam]):
    @abstractmethod
    def list_by_course(self, course_id: int) -> list[Exam]: ...

    @abstractmethod
    def get_by_identity(self, course_id: int, exam_date: date, time_slot: str) -> Exam | None: ...
