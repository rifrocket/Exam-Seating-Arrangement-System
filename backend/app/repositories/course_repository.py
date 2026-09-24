from abc import abstractmethod

from app.domain import Course
from app.repositories.base import Repository


class CourseRepository(Repository[Course]):
    @abstractmethod
    def get_by_code(self, code: str) -> Course | None: ...
