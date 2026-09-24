import pytest

from app.seating import SeatingEngine, UnknownStrategyError, get_strategy
from app.seating.strategies.sequential import SequentialSeatingStrategy


def test_get_strategy_returns_sequential_by_name() -> None:
    strategy = get_strategy("sequential")

    assert isinstance(strategy, SequentialSeatingStrategy)
    assert strategy.name == "sequential"


def test_get_strategy_rejects_unknown_name() -> None:
    with pytest.raises(UnknownStrategyError):
        get_strategy("does-not-exist")


def test_engine_delegates_to_its_strategy() -> None:
    from datetime import date

    from app.domain import Exam
    from app.seating.models import RoomAllocation

    engine = SeatingEngine(get_strategy("sequential"))
    exam = Exam(id=1, course_id=1, exam_date=date(2024, 1, 1), time_slot="10:00-12:00", expected_student_count=0)

    result = engine.run(exam, [], [RoomAllocation(room_id=1, room_code="A", allocated_students=10, capacity=10)])

    assert engine.strategy_name == "sequential"
    assert result.assigned_student_count == 0
