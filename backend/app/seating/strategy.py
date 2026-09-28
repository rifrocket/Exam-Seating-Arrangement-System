"""The seating strategy interface — the one abstraction all future
seating algorithms implement.

A strategy takes plain domain/seating data and returns a SeatingResult.
It must never import FastAPI, SQLAlchemy, HTTP, filesystem, ReportLab, or
any repository — everything it needs is passed in by the calling service,
which is the only layer allowed to query a database.

The base `__init__` accepts an optional `RoomTopologyProvider` so
`get_strategy()` can construct *every* registered strategy uniformly
(`strategy_cls(topology_provider=...)`) without knowing which ones
actually use one. `SequentialSeatingStrategy` never overrides this or
reads `self._topology_provider` — it simply doesn't need a topology, and
inheriting this constructor unchanged is why its own file needs no
change at all for `ConstraintSeatingStrategy` (Milestone 8) to receive
one this way.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.domain import Exam, Student
from app.seating.models import RoomAllocation, SeatingResult

if TYPE_CHECKING:
    from app.seating.topology_provider import RoomTopologyProvider


class SeatingStrategy(ABC):
    name: str

    def __init__(self, *, topology_provider: "RoomTopologyProvider | None" = None) -> None:
        self._topology_provider = topology_provider

    @abstractmethod
    def generate(
        self,
        exam: Exam,
        students: list[Student],
        room_allocations: list[RoomAllocation],
    ) -> SeatingResult: ...
