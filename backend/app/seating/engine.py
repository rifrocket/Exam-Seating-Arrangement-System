"""SeatingEngine: a thin wrapper that runs whichever SeatingStrategy it's
given, plus a small name -> strategy registry.

Not "an elaborate plugin framework" — adding a future strategy is: write
a class implementing SeatingStrategy, add one line to _STRATEGIES.
Nothing else in the app (API, db, repositories, frontend) changes.
"""

from app.domain import Exam, Student
from app.seating.models import RoomAllocation, SeatingResult
from app.seating.strategies.sequential import SequentialSeatingStrategy
from app.seating.strategy import SeatingStrategy

_STRATEGIES: dict[str, type[SeatingStrategy]] = {
    SequentialSeatingStrategy.name: SequentialSeatingStrategy,
}


class UnknownStrategyError(ValueError):
    pass


def get_strategy(name: str) -> SeatingStrategy:
    strategy_cls = _STRATEGIES.get(name)
    if strategy_cls is None:
        raise UnknownStrategyError(f"Unknown seating strategy '{name}'. Available: {sorted(_STRATEGIES)}")
    return strategy_cls()


class SeatingEngine:
    def __init__(self, strategy: SeatingStrategy) -> None:
        self._strategy = strategy

    @property
    def strategy_name(self) -> str:
        return self._strategy.name

    def run(
        self,
        exam: Exam,
        students: list[Student],
        room_allocations: list[RoomAllocation],
    ) -> SeatingResult:
        return self._strategy.generate(exam, students, room_allocations)
