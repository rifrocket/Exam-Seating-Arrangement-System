from abc import abstractmethod

from app.domain import SeatAssignment
from app.repositories.base import Repository


class SeatAssignmentRepository(Repository[SeatAssignment]):
    @abstractmethod
    def list_by_generation(self, seating_generation_id: int) -> list[SeatAssignment]: ...
