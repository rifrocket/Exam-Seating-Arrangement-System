from abc import abstractmethod

from app.domain import Exam
from app.repositories.base import Repository


class ExamRepository(Repository[Exam]):
    @abstractmethod
    def list_by_course(self, course_id: int) -> list[Exam]: ...
