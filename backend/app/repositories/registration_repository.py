from abc import abstractmethod

from app.domain import Registration
from app.repositories.base import Repository


class RegistrationRepository(Repository[Registration]):
    @abstractmethod
    def list_by_course(self, course_id: int) -> list[Registration]: ...

    @abstractmethod
    def list_by_student(self, student_id: int) -> list[Registration]: ...

    @abstractmethod
    def get_by_student_and_course(self, student_id: int, course_id: int) -> Registration | None: ...
