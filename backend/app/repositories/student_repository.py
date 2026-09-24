from abc import abstractmethod

from app.domain import Student
from app.repositories.base import Repository


class StudentRepository(Repository[Student]):
    @abstractmethod
    def get_by_student_number(self, student_number: str) -> Student | None: ...
