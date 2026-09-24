"""Seating engine and strategies.

SeatingEngine -> SeatingStrategy -> SequentialSeatingStrategy (Milestone 4).
ConstraintSeatingStrategy / OptimizationSeatingStrategy remain future,
unimplemented strategies behind the same SeatingStrategy interface — see
docs/architecture.md.

Nothing in this package imports FastAPI, SQLAlchemy, HTTP, the
filesystem, ReportLab, or a repository. It operates purely on domain data
handed to it by app.services.seating_generation.
"""

from app.seating.engine import SeatingEngine, UnknownStrategyError, get_strategy
from app.seating.models import RoomAllocation, SeatAssignmentRecord, SeatingResult
from app.seating.strategy import SeatingStrategy

__all__ = [
    "RoomAllocation",
    "SeatAssignmentRecord",
    "SeatingEngine",
    "SeatingResult",
    "SeatingStrategy",
    "UnknownStrategyError",
    "get_strategy",
]
