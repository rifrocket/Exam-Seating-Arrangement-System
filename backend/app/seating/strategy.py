"""The seating strategy interface — the one abstraction all future
seating algorithms implement.

A strategy takes plain domain/seating data and returns a SeatingResult.
It must never import FastAPI, SQLAlchemy, HTTP, filesystem, ReportLab, or
any repository — everything it needs is passed in by the calling service,
which is the only layer allowed to query a database.
"""

from abc import ABC, abstractmethod

from app.domain import Exam, Student
from app.seating.models import RoomAllocation, SeatingResult


class SeatingStrategy(ABC):
    name: str

    @abstractmethod
    def generate(
        self,
        exam: Exam,
        students: list[Student],
        room_allocations: list[RoomAllocation],
    ) -> SeatingResult: ...
