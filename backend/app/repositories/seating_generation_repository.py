from abc import abstractmethod

from app.domain import SeatingGeneration
from app.repositories.base import Repository


class SeatingGenerationRepository(Repository[SeatingGeneration]):
    @abstractmethod
    def list_by_exam(self, exam_id: int) -> list[SeatingGeneration]: ...
