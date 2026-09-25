"""Seating engine and strategies.

SeatingEngine -> SeatingStrategy -> SequentialSeatingStrategy (Milestone 4),
ConstraintSeatingStrategy (Milestone 7). OptimizationSeatingStrategy
remains future, unimplemented, behind the same SeatingStrategy interface —
see docs/architecture.md.

`topology` and `constraints` (Milestone 6) are the foundation
`ConstraintSeatingStrategy` (Milestone 7, `strategies/constraint.py`) is
built on. `topology_provider` (Milestone 7) is the boundary between a
`Room` (code + physical capacity only) and a `SeatTopology` — see its
module docstring for why capacity alone can't imply geometry. Nothing in
this package imports FastAPI, SQLAlchemy, HTTP, the filesystem, ReportLab,
or a repository. It operates purely on domain data handed to it by
app.services.seating_generation.
"""

from app.seating.constraints import (
    Constraint,
    ConstraintEvaluation,
    ConstraintSet,
    ConstraintViolation,
    HardConstraint,
    SeparateCoursesConstraint,
    SoftConstraint,
    StudentSeatingContext,
    StudentsNotAdjacentConstraint,
    evaluate_constraints,
)
from app.seating.engine import SeatingEngine, UnknownStrategyError, get_strategy
from app.seating.models import RoomAllocation, SeatAssignmentRecord, SeatingResult
from app.seating.strategies.constraint import ConstraintSeatingStrategy
from app.seating.strategy import SeatingStrategy
from app.seating.topology import (
    RectangularRoomTopology,
    SeatAssignmentCandidate,
    SeatPosition,
    SeatTopology,
)
from app.seating.topology_provider import (
    RoomTopologyMismatchError,
    RoomTopologyProvider,
    StaticRoomTopologyProvider,
    UnknownRoomTopologyError,
)

__all__ = [
    "Constraint",
    "ConstraintEvaluation",
    "ConstraintSeatingStrategy",
    "ConstraintSet",
    "ConstraintViolation",
    "HardConstraint",
    "RectangularRoomTopology",
    "RoomAllocation",
    "RoomTopologyMismatchError",
    "RoomTopologyProvider",
    "SeatAssignmentCandidate",
    "SeatAssignmentRecord",
    "SeatPosition",
    "SeatTopology",
    "SeatingEngine",
    "SeatingResult",
    "SeatingStrategy",
    "SeparateCoursesConstraint",
    "SoftConstraint",
    "StaticRoomTopologyProvider",
    "StudentSeatingContext",
    "StudentsNotAdjacentConstraint",
    "UnknownRoomTopologyError",
    "UnknownStrategyError",
    "evaluate_constraints",
    "get_strategy",
]
