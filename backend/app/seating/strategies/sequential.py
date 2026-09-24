"""SequentialSeatingStrategy: the direct, corrected successor to the
legacy `buildRoomsLists` FIFO slicing in main.py.

Legacy behavior preserved: rooms are filled in the given order, each
taking the next block of students from an ordered list.

Legacy behavior deliberately NOT preserved:
- No global mutable state, no destructive list mutation (the legacy code
  repeatedly `del`'d the front of a shared dict's list). This strategy
  takes an ordered list and returns a result; the input is never mutated.
- No collapsing `min(expected_student_count, allocated_students)` into a
  single number — `registered_student_count`, `scheduled_student_count`,
  `total_physical_capacity`, and `available_capacity` are kept as
  distinct, reported figures (see SeatingResult's docstring), and
  "why students went unassigned" is reported as two distinct shortage
  flags rather than one ambiguous `capacity_shortage` boolean.
- No silent truncation. Every registered student is either assigned or
  explicitly listed as unassigned; nothing merely "doesn't appear."
"""

from app.domain import Exam, GenerationStatus, Student
from app.seating.models import RoomAllocation, SeatAssignmentRecord, SeatingResult
from app.seating.strategy import SeatingStrategy


class SequentialSeatingStrategy(SeatingStrategy):
    name = "sequential"

    def generate(
        self,
        exam: Exam,
        students: list[Student],
        room_allocations: list[RoomAllocation],
    ) -> SeatingResult:
        room_ids = [ra.room_id for ra in room_allocations]
        if len(room_ids) != len(set(room_ids)):
            raise ValueError(f"Duplicate room allocation(s) for exam {exam.id}: room_ids={room_ids}")

        registered_student_count = len(students)
        scheduled_student_count = sum(ra.allocated_students for ra in room_allocations)
        total_physical_capacity = sum(ra.capacity for ra in room_allocations)

        warnings: list[str] = []
        usable_targets: list[tuple[int, int]] = []  # (room_id, seats actually fillable)
        for ra in room_allocations:
            target = ra.allocated_students
            if ra.allocated_students > ra.capacity:
                target = ra.capacity
                warnings.append(
                    f"Room '{ra.room_code}' scheduled allocation ({ra.allocated_students}) exceeds its "
                    f"capacity ({ra.capacity}); capped at {ra.capacity} for this generation."
                )
            usable_targets.append((ra.room_id, target))

        available_capacity = sum(target for _, target in usable_targets)

        if registered_student_count > scheduled_student_count:
            warnings.append(
                f"{registered_student_count} student(s) registered but only {scheduled_student_count} "
                "seat(s) were scheduled across this exam's rooms."
            )
        elif registered_student_count < scheduled_student_count:
            warnings.append(
                f"Only {registered_student_count} student(s) registered; "
                f"{scheduled_student_count - registered_student_count} scheduled seat(s) will remain unused."
            )

        assignments: list[SeatAssignmentRecord] = []
        cursor = 0
        for room_id, target in usable_targets:
            for seat_number in range(1, target + 1):
                if cursor >= registered_student_count:
                    break
                student = students[cursor]
                assert student.id is not None
                assignments.append(SeatAssignmentRecord(student_id=student.id, room_id=room_id, seat_number=seat_number))
                cursor += 1

        assigned_student_count = len(assignments)
        unassigned_students = students[cursor:]
        unassigned_student_count = len(unassigned_students)
        unassigned_student_ids = [s.id for s in unassigned_students if s.id is not None]

        # Three independent facts — see SeatingResult's docstring for why
        # these must not be collapsed into each other:
        #  - did anyone actually go unassigned in this generation? (capacity_shortage)
        #  - was the *schedule's own plan* insufficient? (scheduled_allocation_shortage)
        #  - was the *physical room capacity* insufficient, regardless of
        #    what the schedule allocated? (physical_capacity_shortage)
        capacity_shortage = unassigned_student_count > 0
        scheduled_allocation_shortage = registered_student_count > scheduled_student_count
        physical_capacity_shortage = registered_student_count > total_physical_capacity

        if registered_student_count == 0:
            status = GenerationStatus.SUCCESS
            warnings.append("No students are registered for this exam's course.")
        elif unassigned_student_count == 0:
            status = GenerationStatus.SUCCESS
        elif assigned_student_count == 0:
            status = GenerationStatus.FAILED
        else:
            status = GenerationStatus.PARTIAL

        return SeatingResult(
            status=status,
            registered_student_count=registered_student_count,
            scheduled_student_count=scheduled_student_count,
            total_physical_capacity=total_physical_capacity,
            available_capacity=available_capacity,
            assigned_student_count=assigned_student_count,
            unassigned_student_count=unassigned_student_count,
            capacity_shortage=capacity_shortage,
            scheduled_allocation_shortage=scheduled_allocation_shortage,
            physical_capacity_shortage=physical_capacity_shortage,
            assignments=assignments,
            unassigned_student_ids=unassigned_student_ids,
            warnings=warnings,
        )
