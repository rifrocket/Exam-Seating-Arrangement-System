"""Seating engine and strategies.

SeatingEngine -> SeatingStrategy -> SequentialSeatingStrategy (Milestone 4).
ConstraintSeatingStrategy / OptimizationSeatingStrategy remain future,
unimplemented strategies behind the same SeatingStrategy interface — see
docs/architecture.md.

`topology` and `constraints` (Milestone 6) are foundation for a future
ConstraintSeatingStrategy: neither is referenced by SeatingEngine, any
registered strategy, or the registry in engine.py yet. Nothing in this
package imports FastAPI, SQLAlchemy, HTTP, the filesystem, ReportLab, or a
repository. It operates purely on domain data handed to it by
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
    StudentsNotAdjacentConstraint,
    evaluate_constraints,
)
from app.seating.engine import SeatingEngine, UnknownStrategyError, get_strategy
from app.seating.models import RoomAllocation, SeatAssignmentRecord, SeatingResult
from app.seating.strategy import SeatingStrategy
from app.seating.topology import (
    RectangularRoomTopology,
    SeatAssignmentCandidate,
    SeatPosition,
    SeatTopology,
)

__all__ = [
    "Constraint",
    "ConstraintEvaluation",
    "ConstraintSet",
    "ConstraintViolation",
    "HardConstraint",
    "RectangularRoomTopology",
    "RoomAllocation",
    "SeatAssignmentCandidate",
    "SeatAssignmentRecord",
    "SeatPosition",
    "SeatTopology",
    "SeatingEngine",
    "SeatingResult",
    "SeatingStrategy",
    "SeparateCoursesConstraint",
    "SoftConstraint",
    "StudentsNotAdjacentConstraint",
    "UnknownStrategyError",
    "evaluate_constraints",
    "get_strategy",
]
