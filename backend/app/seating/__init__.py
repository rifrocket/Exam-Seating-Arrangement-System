"""Seating engine and strategies.

SeatingEngine -> SeatingStrategy -> SequentialSeatingStrategy (Milestone 4),
ConstraintSeatingStrategy (Milestone 7). OptimizationSeatingStrategy
remains future, unimplemented, behind the same SeatingStrategy interface —
see docs/architecture.md.

`topology` and `constraints` (Milestone 6) are the foundation
`ConstraintSeatingStrategy` (Milestone 7, `strategies/constraint.py`) is
built on. `topology_provider` (Milestone 7, extended Milestone 8) is the
abstract boundary between a `Room` (which has its own optional
`rows`/`columns` as of Milestone 8) and a `SeatTopology` — see its module
docstring for why capacity alone can't imply geometry. The concrete,
repository-backed provider used in production
(`RepositoryRoomTopologyProvider`) lives in
`app.services.seating_generation`, not here, since it needs a repository.

`anti_cheating` (this milestone) holds the deterministic, topology-aware
heuristics `ConstraintSeatingStrategy` uses by default to spatially
separate different courses' students instead of letting them cluster —
see that module's own docstring and docs/architecture.md's "Anti-cheating
seating" section. `quality_metrics` is a pure, test-only measurement
helper for that behavior; nothing in production imports it.

Nothing in this package imports FastAPI, SQLAlchemy, HTTP, the
filesystem, ReportLab, or a repository. It operates purely on domain data
handed to it by app.services.seating_generation.
"""

from app.seating.anti_cheating import order_students_for_placement, same_course_penalty
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
from app.seating.quality_metrics import SeatingQualityReport, evaluate_seating_quality
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
    RoomTopologyMissingError,
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
    "RoomTopologyMissingError",
    "RoomTopologyProvider",
    "SeatAssignmentCandidate",
    "SeatAssignmentRecord",
    "SeatPosition",
    "SeatTopology",
    "SeatingEngine",
    "SeatingQualityReport",
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
    "evaluate_seating_quality",
    "get_strategy",
    "order_students_for_placement",
    "same_course_penalty",
]
