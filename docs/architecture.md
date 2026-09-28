# Architecture

This document describes the architecture of the modular Exam Seating
Arrangement System as actually implemented through Milestone 3
(Schedule & Exam Management, commit `94cb6ff`), with the **Seating
strategy abstraction** section additionally updated for Milestone 4
(Seating Engine + Sequential Seating, commit `4b4f2a6`) and the
**Report boundary** section updated for Milestone 5 (Report Generation
& End-to-End MVP Workflow) — the rest of this document has not been
re-synchronized against every change from those milestones. It
complements — and does not replace — the repository audit, which
explains why the legacy `main.py`/`services/`/`models/`/`views/` script
is being superseded rather than incrementally patched.

## Goals this architecture serves

- The seating algorithm is a **replaceable strategy**, not something wired
  into the API or database.
- The frontend **never** contains seating or business logic — it only
  calls the backend API.
- Future capabilities (mixed-course seating, anti-cheating rules,
  constraint- and optimization-based seating, seat-level layout,
  generation history/comparison) must be addable without rewriting the
  application, the database schema's shape, or the API contract.
- No infrastructure (microservices, Kubernetes, Redis, queues) is
  introduced without a demonstrated requirement. SQLite + a single FastAPI
  process is the target deployment for the foreseeable scale (hundreds of
  students, batch-run generation).

## Top-level layout

```
backend/
  app/
    api/            HTTP boundary: health, registrations, schedules, exams, rooms, seating, reports
    services/        registration_import/, schedule_import/, room_import.py,
                      seating_generation/, reports/
    domain/          plain domain models
    repositories/    persistence interfaces + SQLAlchemy-backed implementations (db/repositories.py)
    seating/         SeatingEngine, SeatingStrategy, SequentialSeatingStrategy
    reports/         pure ReportLab render functions (seating + ID-range reports)
    db/              SQLAlchemy models, session, init_db (+ schema-compatibility guard)
  tests/
frontend/
  app/               Next.js App Router pages: /registrations, /rooms, /schedule, /schedule/[examId]
docs/
  architecture.md    this file
```

## Dependency direction

Dependencies point inward, toward `domain/`, and never sideways between
peer layers:

```
frontend  ──HTTP──>  api/  ──>  services/  ──>  domain/
                                    │      \
                                    │       └─>  seating/  ──>  domain/
                                    ├─>  repositories/ (interfaces)  ──>  domain/
                                    └─>  reports/  ──>  domain/

db/  implements repositories/ against domain/, and depends on domain/ +
     SQLAlchemy — nothing in domain/, seating/, or repositories/ (as
     interfaces) imports db/, FastAPI, or SQLAlchemy.
```

Concretely, as enforced today:

- `app/domain/*` — plain `@dataclass` models. No imports of FastAPI,
  SQLAlchemy, or any other layer. This is intentional: it's the one part
  of the codebase every other layer is allowed to depend on, so it must
  depend on nothing itself.
- `app/repositories/*` — abstract interfaces (`abc.ABC`) typed against
  `app/domain` dataclasses only. No SQLAlchemy import. Concrete,
  SQLAlchemy-backed implementations live in `app/db/repositories.py`
  (`SqlAlchemyStudentRepository`, `SqlAlchemyCourseRepository`,
  `SqlAlchemyRegistrationRepository`, `SqlAlchemyRoomRepository`,
  `SqlAlchemyExamRepository`, `SqlAlchemyExamRoomRepository`) — introduced
  incrementally, one aggregate at a time, alongside the milestone that
  first needed to read/write it (Milestone 2 for
  Student/Course/Registration, Milestone 3 for Room/Exam/ExamRoom).
- `app/db/*` — SQLAlchemy `DeclarativeBase`, ORM models, engine/session
  factory, and the `init_db()` mechanism (including the schema-
  compatibility guard — see **Persistence boundary**). Depends on
  `app/domain` and SQLAlchemy. Nothing outside `db/` imports SQLAlchemy
  directly.
- `app/services/` — `registration_import/` (Milestone 2),
  `schedule_import/` + `room_import.py` (Milestone 3),
  `seating_generation/` (Milestone 4), and `reports/` (Milestone 5) are
  all populated; each depends only on repository interfaces (and, for
  `seating_generation/`, the pure `app/seating/` engine; for `reports/`,
  the pure `app/reports/` renderers) — never on FastAPI or raw SQL.
- `app/api/*` — FastAPI routers. A router calls a service for import
  endpoints (`registrations.py`, `schedules.py`, `rooms.py`'s import
  route) or composes read-only repository calls directly for list/detail
  endpoints (`students`, `courses`, `registrations`, `rooms`, `exams`,
  `exams/{id}`) — the latter is data composition (assembling a response
  DTO from one or two repository reads), never business logic. No router
  contains parsing, validation rules, or SQL.
- `app/seating/` — `SeatingEngine`, `SeatingStrategy`,
  `SequentialSeatingStrategy` (Milestone 4). `app/reports/` — pure
  ReportLab render functions (Milestone 5). Neither imports the other,
  and neither imports FastAPI/SQLAlchemy/repositories.

## Module responsibilities

| Module | Responsible for | Not responsible for |
|---|---|---|
| `api/` | HTTP request/response shapes, status codes, routing, read-only response composition | validation logic, seating, persistence details |
| `services/` | orchestrating a use case (e.g. "import this registration/schedule/room CSV", "generate seating", "assemble a report") | HTTP concerns, SQL, ReportLab calls |
| `domain/` | what a Student/Course/Exam/ExamRoom/Room/etc. *is* | how it's stored, rendered, or transported |
| `repositories/` | the *interface* (and, in `db/`, the concrete implementation) for loading/saving domain objects | business rules about what to load/save and when |
| `seating/` | the strategy interface + engine for turning students+rooms into seat assignments | which concrete algorithm is "best" — that's a strategy's job |
| `reports/` | turning already-assembled data into PDFs | deciding what data to show or querying the database (that's `services/reports/`'s job) |
| `db/` | SQLAlchemy table definitions, engine/session lifecycle, schema initialization + compatibility guard | business rules |
| `frontend/` | presentation, calling the API, rendering responses | seating logic, validation logic, direct DB or file access |

## Domain boundaries

Nine *persisted* entities exist as of Milestone 3 (see below for `Room`'s
Milestone 8 topology fields). `ExaminationSession` and its `SessionExam`
join (Milestone 9) are two more, persisted specifically because a real
multi-course generation workflow needs a stable id to create, list,
inspect, and generate against — see **Examination sessions and
multi-course seating**.

- **Student** `(id, student_number, full_name)` — full name stored
  complete; any truncation (e.g. the legacy 3-token name) is a
  presentation concern for `reports/`, never applied to the stored value.
- **Course** `(id, code, name)` — registration data is the source of
  truth for courses; nothing else is ever allowed to create one (see
  **Validation behavior**).
- **Registration** `(id, student_id, course_id)` — the student↔course join.
- **Exam** `(id, course_id, exam_date, time_slot, expected_student_count,
  day_label)` — one scheduled sitting of a course on a given date and
  time slot. `expected_student_count` is the exam's overall expected
  headcount. `time_slot` is a normalized `"HH:MM-HH:MM"` string, not a
  real time object — the source schedule data has no AM/PM marker, so
  this is an honest representation rather than an invented one.
  `day_label` is the raw, unvalidated "Day" text from the source row,
  kept only for display — never cross-checked against the actual weekday
  of `exam_date`.
- **ExamRoom** `(id, exam_id, room_id, allocated_students)` — associates
  one Exam with one Room and that room's scheduled student allocation.
  **One Exam can have multiple ExamRoom records** — this is how a single
  real-world exam that spans several rooms is represented; it was never
  forced into a many-to-one Exam→Room relationship.
- **Room** `(id, code, capacity, rows, columns)` — first-class; seeded
  from a CSV matching the legacy `input/locations.csv` shape (`room,
  capacity`, with an optional ignored `index` column), which the legacy
  code never actually read. `rows`/`columns` (Milestone 8) are optional
  and always both-or-neither — a room without them isn't an error, it
  just has no configured seat topology yet (see **Room topology**).
- **SeatingGeneration** `(id, exam_id, strategy_name, status,
  total_registered, total_assigned, total_unassigned, capacity_shortage,
  warnings, created_at)` — one identifiable, versioned run of a seating
  strategy. `status` is `pending | success | partial | failed`; `partial`
  exists specifically so a generation that couldn't seat everyone is a
  visible, queryable outcome rather than a silently dropped student (this
  corrects a real gap in the legacy system's `left.json` behavior).
- **SeatAssignment** `(id, seating_generation_id, exam_id, room_id,
  student_id, seat_number)` — one student's assigned room + running
  position for a generation.

**Deliberately still not modeled:**

- **Seat** as a *persisted, individually-addressable* entity — there is
  still no seat database table, no row per physical seat, and
  `SeatAssignment.seat_number` is still a running integer, not a foreign
  key. What *is* persisted, as of Milestone 8, is `Room.rows`/`Room.columns`
  — a room's overall rectangular *shape*, not individual seat rows. A
  `SeatPosition`/`SeatTopology` (Milestone 6, `app/seating/topology.py`)
  is still derived on the fly from those two integers each time it's
  needed, never itself stored. Introduce a real, persisted `Seat` entity
  only when a non-rectangular or per-seat-editable layout is actually
  needed — a rectangular room described by two integers doesn't need one.
- **Constraint** as a *generic, database-configurable* rule (e.g. a JSON
  schema an admin edits through the UI) — `ConstraintSeatingStrategy`
  (Milestone 7) does now read and evaluate constraints during generation,
  but only the fixed, in-code default described in **Constraint seating
  strategy** above; there is still no database-backed generic rule schema,
  and designing one now, with only one real caller, would be speculative.
  Milestone 6's typed Python `Constraint`/`HardConstraint`/`SoftConstraint`
  classes are not the same thing as a configurable schema: they're a fixed
  set of small classes in code. `SeatingGeneration` remains the extension
  point for a persisted `config` payload once there's an actual need for
  an admin to configure constraints per generation.

### Three numbers that must never collapse into one

This is the audit's central finding about the legacy system, and the
reason `Exam`, `ExamRoom`, and `Room` are three separate entities instead
of one:

| Value | Lives on | Meaning |
|---|---|---|
| `Exam.expected_student_count` | Exam | How many students the exam sitting as a whole is expected to have (the legacy CSV's "No. of Students" column, repeated on every room-row for that exam). |
| `ExamRoom.allocated_students` | ExamRoom | How many students this *specific room* is scheduled to hold for this exam (the legacy CSV's "No. of Students/ Room" column, one value per room-row). |
| `Room.capacity` | Room | The room's physical seating limit, independent of any exam. |

The legacy system computed `min(No. of Students, No. of Students/ Room)`
and only ever stored that one collapsed number. Milestone 3 preserves all
three values exactly as imported, unmodified. This is what lets a future
`SeatingEngine` validate "does the scheduled allocation fit the room's
real capacity?" and "does the sum of scheduled allocations across a
exam's rooms cover its expected headcount?" — questions the legacy data
model could never answer because the numbers it needed had already been
thrown away during import.

## Data flow

**Registration** (Milestone 2):
```
CSV upload → parser/validator (app/services/registration_import/parser.py)
           → RegistrationImportService
           → StudentRepository / CourseRepository / RegistrationRepository
           → database (students, courses, registrations tables)
```

**Room** (Milestone 3):
```
CSV upload → room_import.py (parser + RoomImportService in one module —
             a two-column, no-cross-reference import doesn't need the
             parser/service split as separate files)
           → RoomRepository
           → database (rooms table)
```

**Schedule** (Milestone 3):
```
CSV upload → parser/validator (app/services/schedule_import/parser.py)
           → ScheduleImportService
           → CourseRepository (lookup only — never creates a Course)
           → RoomRepository (lookup only — never creates a Room)
           → ExamRepository / ExamRoomRepository
           → database (exams, exam_rooms tables)
```

Every import follows the same shape: **API → parser/validator (pure,
no DB) → service (orchestrates repositories) → repositories →
database.** The parser never touches a database session; the service
never parses CSV text or does I/O.

## The schedule importer's responsibility (and what it explicitly does not do)

**The schedule importer does not perform seating allocation.** It imports
already-scheduled exam/room allocations exactly as they appear in the
source CSV — the legacy spreadsheet-authoring process (or whatever
produces the schedule CSV) has already decided which rooms an exam uses
and how many students go in each one. `ScheduleImportService`'s job is
purely to parse, validate, and persist that pre-existing decision as
`Exam` + `ExamRoom` rows; it does not decide room counts, does not split
students into rooms, and does not run any capacity-fitting logic beyond
*flagging* (not correcting) a scheduled allocation that exceeds a room's
capacity. Actually deciding "which students go in which seat" is the
seating engine's job, and remains fully unimplemented (see below).

## Validation behavior (current, as implemented)

**Registration import:**
- missing required column, blank required field, malformed CSV
- duplicate registration row (same student+course repeated) — counted, not re-inserted
- same student ID with a conflicting name — reported, stored name never overwritten
- same course code with a conflicting name — reported, stored name never overwritten

**Schedule import:**
- missing required column, malformed CSV
- malformed date (including a real legacy example: `input/day3.csv` has
  an unconverted Excel serial number in one Date cell — reported as
  malformed, never guessed at)
- malformed time, invalid/negative student count, invalid/negative room allocation
- **unknown course code** — the exam group is skipped and reported; the
  course is never auto-created (registration data is the source of truth
  for courses)
- **unknown room code** — that room-row is skipped and reported; the
  room is never auto-created
- course-name conflict (schedule's Course Name vs. the already-stored
  Course) — reported, stored name never overwritten
- expected-student-count conflict (same exam, disagreeing room-rows, or
  vs. an already-stored Exam) — reported, stored value never overwritten
- exam-room allocation conflict (same exam+room, disagreeing rows, or
  vs. an already-stored ExamRoom) — reported, stored value never overwritten
- **room-capacity warning** — a room's scheduled allocation exceeding its
  physical capacity is reported as a `warning`, not a blocking error: it's
  a real fact about the source schedule (which the future seating engine
  needs to know), not a reason to refuse importing it
- exact-duplicate room-row — counted as a duplicate, not re-inserted

**Room import:**
- missing required column, invalid/negative capacity
- conflicting capacity for an already-known room code — reported, stored
  capacity never overwritten

Across all three importers, nothing is ever silently dropped: every
excluded row or disagreement is a reported `validation_errors` /
`conflicts` / `warnings` entry, never a value that just quietly changes.

## Seating strategy abstraction (Milestone 4: SequentialSeatingStrategy implemented)

`app/seating/` is populated as of Milestone 4. It has no dependency on
FastAPI, SQLAlchemy, HTTP, the filesystem, ReportLab, or a repository —
`SequentialSeatingStrategy`'s own test suite runs with none of those
present, which is what proves the boundary actually holds.

```python
class SeatingStrategy(ABC):
    name: str
    def generate(self, exam: Exam, students: list[Student], room_allocations: list[RoomAllocation]) -> SeatingResult: ...

class SequentialSeatingStrategy(SeatingStrategy):
    """Fills rooms in the given order, taking the next N students in list
    order per room. This is the direct successor to the legacy
    buildRoomsLists FIFO slicing — but, unlike the legacy code, it owns the
    capacity-fit decision itself rather than reading a pre-computed number
    from a schedule CSV column, and it never silently drops a student: any
    student who doesn't fit becomes part of SeatingResult.unassigned_student_ids."""

class SeatingEngine:
    def __init__(self, strategy: SeatingStrategy): ...
    def run(self, exam: Exam, students: list[Student], room_allocations: list[RoomAllocation]) -> SeatingResult: ...
```

`RoomAllocation` is `app/seating/`'s own flattened join of `ExamRoom` +
`Room` (room_id, room_code, allocated_students, capacity) — the strategy
never queries a repository, so `app.services.seating_generation.SeatingService`
builds this list before calling the engine.

```
SeatingEngine
  └── SeatingStrategy (interface)
        ├── SequentialSeatingStrategy       (Milestone 4 — implemented)
        ├── ConstraintSeatingStrategy       (future — not implemented)
        └── OptimizationSeatingStrategy     (future — not implemented)
```

Future strategies (`ConstraintSeatingStrategy`,
`OptimizationSeatingStrategy`, `MixedCourseSeatingStrategy`) implement the
same `SeatingStrategy` interface and are selected by `strategy_name` at the
service layer (`app/seating/engine.py`'s registry). Adding one requires: a
new class in `app/seating/strategies/` implementing `generate()`, and a
registry entry — no change to `api/`, `db/`, `repositories/`, `frontend/`,
or the `Exam`/`ExamRoom` schema.

### Three distinct shortage diagnoses (not one ambiguous flag)

`SeatingGeneration.capacity_shortage` (persisted, unchanged since
Milestone 4) means exactly one thing: `unassigned_student_count > 0` —
"did at least one registered student go unseated in this run, for
whatever reason." It has never meant, and still does not mean, "the
physical rooms were too small" specifically — that would be a different,
narrower claim, and collapsing the two would recreate the same kind of
ambiguity the legacy `min(expected, allocated)` truncation caused.

`SeatingResult` (and the `POST /exams/{id}/seating/generate` response)
carries three further, independent booleans that answer *why*:

- `scheduled_allocation_shortage` = `registered_student_count >
  scheduled_student_count`. The schedule's own plan didn't allocate
  enough seats for this exam. This can be true even when the assigned
  rooms had physical room to spare — it's a scheduling gap, not a room
  problem.
- `physical_capacity_shortage` = `registered_student_count >
  total_physical_capacity` (sum of the assigned rooms' `Room.capacity`,
  completely independent of what was scheduled). This can be true even
  when the schedule "on paper" allocated more seats than there are
  students — the rooms themselves don't have that many physical seats.
- `usable_capacity_shortage` (Milestone 10) = `registered_student_count >
  total_usable_capacity`, where `total_usable_capacity` is the sum of
  each room's *usable* seats (physical seats minus any blocked ones — see
  **Physical seat layout and availability** below). Because usable seats
  are a subset of physical seats, `physical_capacity_shortage` implies
  `usable_capacity_shortage`, but not the other way around: a room can
  have enough physical seats yet too few usable ones once blocking is
  taken into account. This is expected, not a bug — the two flags answer
  different questions ("enough seats exist at all" vs. "enough seats are
  actually assignable").

None of the three imply each other beyond that one direction; a
generation can have any combination true. These flags are **not**
persisted on `SeatingGeneration` — they're recomputed from a live run's
`RoomAllocation` inputs and returned only in that run's API response
(see `SeatingGenerationOutcome` in
`app/services/seating_generation/records.py`). Persisting them is
deliberately deferred until something needs to inspect a *past*
generation's shortage reason, not just the one just run — adding the
columns now, with nothing reading them back, would be speculative.

### Deterministic ordering (why regeneration reproduces the same seating)

Sequential seating is only useful if running it twice on the same data
produces the same assignments — otherwise "regenerate" would be
indistinguishable from "reshuffle." Two ordering decisions make that true:

- **Students**: `SeatingService._load_registered_students` sorts the
  course's registered students by `(len(student_number), student_number)`
  before handing them to the strategy — comparing length first avoids the
  lexicographic-sort bug that would otherwise misorder numeric IDs of
  different digit-lengths (e.g. `"9001"` sorting after `"10001"`). The
  legacy system never guaranteed this: `main.py` simply consumed whatever
  order the registration CSV happened to be in, which was an accident of
  the export, not a designed property. Sorting explicitly by student
  number also preserves something the legacy PDF "ID range per room"
  reports depended on implicitly — a contiguous ID range per room is only
  a meaningful summary if the students were processed in ID order to
  begin with.
- **Rooms**: `SqlAlchemyExamRoomRepository.list_by_exam` orders explicitly
  by `ExamRoomModel.id` (ascending, i.e. insertion/import order) rather
  than relying on the database's unspecified default row order. Since the
  strategy fills rooms strictly in the order it's given them, an
  unordered query would make the room-fill sequence — and therefore which
  student ends up in which room — dependent on incidental database
  behavior instead of the schedule's own original room order.

Together, these two decisions are what make `test_result_is_deterministic_across_repeated_runs`
(`backend/tests/seating/test_sequential_strategy.py`) and the
regenerate-twice HTTP smoke test both hold: identical input always
produces identical `SeatAssignmentRecord`s, in both content and per-room
seat numbering.

## Constraint seating foundation (Milestone 6, consumed by Milestone 7)

Milestone 6 added the domain layer `ConstraintSeatingStrategy` (Milestone
7 — see **Constraint seating strategy** below) is built on. At the time
Milestone 6 shipped, none of it was wired into `SeatingEngine` or the API;
Milestone 7 is what actually registers and uses it. This section documents
the foundation types themselves; see the next section for the strategy
that consumes them:

```
Current (implemented, unchanged since Milestone 4):
SeatingStrategy
  └── SequentialSeatingStrategy

Foundation (Milestone 6), now consumed by ConstraintSeatingStrategy:
SeatTopology / RectangularRoomTopology   (app/seating/topology.py)
Constraint / HardConstraint / SoftConstraint,
ConstraintSet, ConstraintEvaluation, StudentSeatingContext,
evaluate_constraints()                   (app/seating/constraints.py)

Implemented (Milestone 7):
ConstraintSeatingStrategy                (app/seating/strategies/constraint.py)
RoomTopologyProvider / StaticRoomTopologyProvider
                                          (app/seating/topology_provider.py)

Future (not implemented):
OptimizationSeatingStrategy
```

### Seat topology (`app/seating/topology.py`)

`SequentialSeatingStrategy` only needs a per-room ordinal (`seat_number`);
a constraint like "these two students must not sit next to each other"
needs actual spatial structure. `SeatPosition` (room_id, seat_number, row,
column) is that structure, and `SeatTopology` is the abstract interface
for answering spatial questions about it: `same_row`, `same_column`,
`is_adjacent`, `distance`. `RectangularRoomTopology` is the one concrete
implementation so far — a plain `rows x columns` grid, numbered row-major
from 1, with no persistence at all: positions are derived from
`seat_number` on demand, the same way a test fixture would. `is_adjacent`
counts diagonal neighbors as adjacent (Chebyshev distance 1), matching
what an anti-cheating "don't sit next to" rule actually needs.

This is deliberately not a full room-layout feature: no seat database
table, no graphical layout editor, no frontend seat map. The `SeatTopology`
interface is what leaves room for a later, persisted, non-rectangular
layout — a future implementation of the same interface — without any
constraint or strategy code changing.

`SeatAssignmentCandidate` (student_id + `SeatPosition`) is the constraint
layer's own input shape, distinct from `SeatAssignmentRecord` (the
engine's persistence-facing room_id + seat_number output) the same way
`RoomAllocation` is already a boundary-specific shape distinct from the
persisted `ExamRoom`.

### Constraint model (`app/seating/constraints.py`)

Two constraint severities, as two distinct ABCs rather than one type with
a severity flag:

- **`HardConstraint`** — must never be violated. Example implemented here:
  `StudentsNotAdjacentConstraint` (two specific students must not end up
  in adjacent seats).
- **`SoftConstraint`** — should be satisfied when possible, but violating
  one still leaves the seating acceptable. Example implemented here:
  `SeparateCoursesConstraint` (prefer that adjacent seats hold
  same-course students, i.e. each course seats as a contiguous block).
  It takes a plain `Mapping[int, int]` of student_id -> course_id supplied
  by its caller — it does not look courses up itself, and its existence
  here is not mixed-course seating support: nothing about how
  `Exam`/`ExamRoom`/`SeatingService` allocate a single course's students
  has changed.

Both constraints take a `Mapping[int, SeatTopology]` keyed by `room_id`
(added in Milestone 7), not a single `SeatTopology` — a real seating spans
multiple rooms, each potentially with its own layout, so a constraint
comparing two students' positions must resolve the right topology for
whichever room each one is actually in.

`StudentSeatingContext` (student_id + course_id) is the minimum per-student
attribute set a constraint might need, built by the strategy itself from
`Exam`/`Student` — never a generic metadata dict, never looked up by a
constraint directly, and never a SQLAlchemy model. Add a field to it only
when a real constraint needs one.

`ConstraintSet` groups a run's hard and soft constraints. This is
deliberately not a generic rule language or DSL — adding a new constraint
means writing one small class implementing `HardConstraint` or
`SoftConstraint`, the same way adding a new `SeatingStrategy` means
writing one small class.

### Constraint evaluation

`evaluate_constraints(constraint_set, assignments) -> ConstraintEvaluation`
is a pure function checking one proposed (student_id -> position) seating
against a `ConstraintSet`. `ConstraintEvaluation.satisfied` answers only
"is this seating acceptable at all" — true iff there are no hard-constraint
violations; a soft-constraint violation is recorded in `violations` (via
`soft_violations`) but never flips `satisfied` to False. `ConstraintSeatingStrategy`
(Milestone 7, below) calls this once per candidate seating it considers.

Like the rest of `app/seating/`, `topology.py` and `constraints.py` import
nothing from FastAPI, SQLAlchemy, ReportLab, a repository, or `app.api`/
`app.db` (enforced by
`backend/tests/seating/test_constraint_foundation_boundaries.py`, which
parses each module's imports directly rather than relying on whatever
happens to already be loaded in `sys.modules`).

## Constraint seating strategy (Milestone 7: implemented)

`ConstraintSeatingStrategy` is registered in `app/seating/engine.py`'s
`_STRATEGIES` registry exactly like `SequentialSeatingStrategy` —
`get_strategy("constraint")` now returns a real, working strategy instead
of raising `UnknownStrategyError`, and `POST /exams/{id}/seating/generate`
accepts `{"strategy": "constraint"}` with **no API code change**, since
the endpoint already forwarded `strategy_name` to `get_strategy()` before
this milestone existed.

### RoomTopologyProvider (`app/seating/topology_provider.py`)

`RoomTopologyProvider` is the abstract boundary between "a room" and "a
`SeatTopology`":

```python
class RoomTopologyProvider(ABC):
    def get_topology(self, room_id: int, room_code: str, capacity: int) -> SeatTopology: ...
```

As of Milestone 7 this had one implementation, `StaticRoomTopologyProvider`
— a fixed, caller-supplied `room_code -> (rows, columns)` mapping, and
`ConstraintSeatingStrategy`'s own zero-argument constructor defaulted to
one hardcoded to this project's own two sample rooms
(`{"401": (2, 5), "402": (2, 5)}`). **Milestone 8 replaces that default**:
see **Room topology** below for `RepositoryRoomTopologyProvider`, the
real production provider. `StaticRoomTopologyProvider` still exists (it's
useful for tests and synthetic scenarios) but is no longer wired in by
default anywhere.

### The constructive algorithm

Not a solver — no OR-Tools, CP-SAT, ILP, backtracking, or randomness.
`ConstraintSeatingStrategy.generate()`:

1. Builds the same room-then-seat-number candidate list
   `SequentialSeatingStrategy` would fill (preserving room order and
   per-room seat numbering exactly), but each candidate now carries a
   `SeatPosition` (row/column) from that room's `SeatTopology`.
2. For each student, in the given (already deterministic) order: scans
   remaining seats in that same order, keeps only the ones where adding
   this placement to what's already been placed keeps every hard
   constraint satisfied (`evaluate_constraints(...).satisfied`), and
   among the survivors picks the one with the fewest soft-constraint
   violations — ties broken by whichever qualifying seat came first in
   order, so the result is deterministic.
3. A student with no surviving candidate goes unassigned; the algorithm
   continues with the next student rather than failing the whole run.

This is a simple greedy heuristic, not a complete algorithm: it is **not**
guaranteed to find a feasible seating even when one exists (a different
assignment order could occasionally succeed where this one leaves someone
unassigned). That trade-off is intentional for this milestone — the
constraint model needs to prove itself before any solver is chosen.

**When given an empty `ConstraintSet`**, every candidate always has zero
violations, so the very first (room-then-seat-order) candidate always
wins — which is exactly `SequentialSeatingStrategy`'s own fill order.
`test_constraint_strategy.py::test_matches_sequential_strategy_when_there_are_no_constraints`
asserts the two strategies produce byte-identical assignments in that
case.

`ConstraintSeatingStrategy`'s default (`constraint_set=None`, as opposed
to an explicitly empty `ConstraintSet()`) builds a
`StudentSeatingContext` per registered student regardless. At the time
this milestone shipped, mixed-course seating did not exist yet, so this
was always trivially a single-course mapping — see **Anti-cheating
seating** (Milestone 11) below for what the default actually does with
that mapping once multi-course sessions exist.

### Capacity semantics are unchanged

`scheduled_allocation_shortage` and `physical_capacity_shortage` are
computed identically to `SequentialSeatingStrategy` — from the same raw
registered/scheduled/physical-capacity counts, independent of how the
constructive algorithm actually placed students. A student going
unassigned because every remaining seat violated a hard constraint is a
distinct fact — a **constraint** shortfall, not a **capacity** one — and
is reported only as an additional entry in `SeatingResult.warnings`
("N student(s) could not be seated because every remaining seat violated
a hard constraint"), never by reinterpreting either shortage flag or
`SeatingGeneration.capacity_shortage`. No new field was added to
`SeatingResult` for this — the existing `warnings: list[str]` mechanism
was judged sufficient (see Phase 7 spec, section 10).

### Frontend

The exam detail page (`frontend/app/exams/[examId]/page.tsx`) gained a
minimal `Strategy: [Sequential ▼]` selector next to "Generate Seating",
offering only `Sequential` and `Constraint` — `Optimization` is
deliberately not listed, since it doesn't exist. No other UI changed.

## Room topology (Milestone 8: `Room.rows`/`Room.columns`, `RepositoryRoomTopologyProvider`)

Milestone 7's `ConstraintSeatingStrategy` could only seat exams whose
rooms happened to be "401" or "402", from a hardcoded demo mapping.
Milestone 8 replaces that with real, per-room configuration:

```
Room
    code
    capacity
    rows        (optional)
    columns     (optional)
```

**Topology is explicit, never inferred from capacity.** Two 10-seat rooms
can have completely different real layouts, so `rows`/`columns` must be
given directly — there is no "capacity 10 implies 2x5" rule anywhere in
the codebase. `Room.__post_init__` enforces the invariant
`rows * columns == capacity` exactly (and both-or-neither: a room can't
have just `rows` without `columns`), raising `InvalidRoomTopologyError`
immediately rather than letting a mismatched layout reach a strategy.

**A room with no configured topology is normal, valid state** — it simply
means "topology not configured yet":

```
Sequential strategy  -> only reads Room.capacity -> works regardless
Constraint strategy  -> needs a SeatTopology      -> raises RoomTopologyMissingError
```

`RepositoryRoomTopologyProvider` (`app/services/seating_generation/room_topology_provider.py`)
is the production `RoomTopologyProvider`: it reads a room's own
`rows`/`columns` through a `RoomRepository` and returns a
`RectangularRoomTopology`. It lives in `app.services`, not `app.seating`,
for the same reason `SeatingService` itself does — it needs a repository,
and `app.seating` never does. `SeatingService.generate()` builds one per
call and passes it to `get_strategy()`, which forwards it to *every*
strategy uniformly via `SeatingStrategy`'s own base `__init__`
(`SequentialSeatingStrategy` inherits that constructor unchanged and never
reads it). `POST /exams/{id}/seating/generate` maps
`RoomTopologyMissingError`/`RoomTopologyMismatchError`/`UnknownRoomTopologyError`
to a `400` with the error's own message, the same way it already did for
`UnknownStrategyError`.

### Database migration

`rows`/`columns` are nullable, purely additive columns on the
already-shipped `rooms` table. `app.db.init_db._ensure_room_topology_columns()`
runs a plain `ALTER TABLE rooms ADD COLUMN ...` for either one that's
missing from an existing database file, *unlike* `check_schema_compatibility`'s
loud-failure approach for the `exams` table (Milestone 3) — see
`init_db.py`'s own docstring for exactly why nullable-and-additive is safe
to auto-migrate while that case wasn't. No existing room row's meaning
changes; every pre-Milestone-8 room simply gets `rows=NULL, columns=NULL`
("topology not configured"). Alembic remains deliberately unintroduced.

### Room import

The pre-Milestone-8 two-column format (`room,capacity`, with an optional
legacy `index` column) still imports unchanged. Two new, **optional**
columns are accepted together (`rows`, `columns`):

```
room,capacity,rows,columns
401,10,2,5
402,10,2,5
```

A row supplying only one of the two, or a combination that doesn't
multiply out to that row's capacity, is a validation error for that row —
its topology is rejected outright, never truncated or guessed at
(matching how an invalid capacity value already rejects the whole row).
An existing room with no topology gets one backfilled from a later import
row (nothing is overwritten — there was nothing there before); an
existing room that already has topology and the row disagrees is reported
as a `room_topology` conflict, via the same never-overwrite policy
already applied to capacity (`room_capacity` conflicts). `GET /rooms`
exposes `rows`/`columns` (`null` when unconfigured), and the Rooms page
shows them plus a `Configured`/`Not configured` badge.

## Examination sessions and multi-course seating (Milestone 8 domain concept; Milestone 9 persists it and wires up generation)

```
Exam
    = one course's scheduled examination (course, date, time, rooms).
ExaminationSession
    = a shared seating session grouping one or more compatible Exams.
Session participants
    = each session exam's registered students, combined into one
      list of StudentSeatingContext (student_id, course_id).
Session seating
    = one SeatingGeneration using one strategy, built from every
      session exam's combined room allocations and students.
```

`Exam` is not overloaded to mean this — `ExaminationSession`
(`app/domain/examination_session.py`) is a separate domain concept:

```python
@dataclass(frozen=True)
class ExaminationSession:
    id: int | None
    exam_ids: list[int]
    exam_date: date
    time_slot: str
```

Milestone 8 introduced this as a pure, non-persisted concept. Milestone 9
persists it (`ExaminationSessionModel` + a `SessionExamModel` join table —
see **Persistence** below) and adds the actual multi-course generation
workflow, because a real user-facing workflow needs a session id stable
enough to create, list, inspect, and generate against across separate
requests — a purely in-memory session could not do that.

### Creating a session (`ExaminationSessionService.create_session`)

Follows this exact order, so a caller always learns about the *first*
real problem with their requested exam combination:

1. Load the exams (`ExamNotFoundError` if any id doesn't exist).
2. `build_examination_session(exams)` — every exam must share the same
   `exam_date` and `time_slot` (`IncompatibleExamScheduleError`
   otherwise). A session of exactly one exam is always valid, which is
   how the existing single-exam MVP conceptually fits this model without
   anything about today's behavior needing to change.
3. Room compatibility (see below) — `ConflictingRoomAllocationError` if a
   shared room is over-committed.
4. `build_session_participants(...)` — a student registered in more than
   one of the session's exams raises `DuplicateStudentInSessionError`,
   never silently deduplicated or double-seated.
5. Persist the session and its exam references.

A session never copies course/student-count/room-capacity/schedule data
onto itself — `SessionExamModel` only references exam ids, the same way
`ExamRoom` references `Room` rather than copying its capacity. Reading a
session back (`GET /examination-sessions/{id}`) re-resolves
`participant_count`/`room_codes` fresh from current data every time.

### Room sharing across a session's exams

Two exams in the same session *can* reference the same physical room —
this is what actually makes "multi-course seating" mean something (two
courses seated into the same room together), rather than just "several
single-course exams generated in one batch." The rule
(`validate_no_conflicting_room_usage`) is: a room used by only one exam
needs no check; a room shared by two or more exams is fine as long as the
**sum** of each sharing exam's own `allocated_students` for that room
does not exceed the room's real physical capacity. That sum is never
invented — each number was already explicitly recorded against its own
exam — and "does it physically fit" is an unambiguous, checkable fact.
Only an over-committed shared room (sum > capacity) is rejected.

### Building one seating input from several exams (`SeatingService.generate_session`)

`SeatingService` gains `generate_session(session_id, strategy_name)`
alongside the existing `generate(exam_id, strategy_name)` — `generate()`
itself is completely unchanged (confirmed by its own file's zero-line
diff for this milestone). `generate_session()`:

1. Loads every session exam's `RoomAllocation`s and registered students.
2. **Merges** any room shared by two exams into a single
   `RoomAllocation` (summing `allocated_students`, keeping the room's own
   `capacity` once, not once per exam) — `SeatingStrategy.generate()`
   itself treats two entries with the same `room_id` as a data-integrity
   error, correctly, for the single-exam path; a session's sharing case
   needs this collapsed *before* the engine ever sees it.
3. Builds one combined, deterministically-ordered student list —
   ordered by **`(course_id, student_number)`**, not student_number
   alone, purely so each course's own students stay in a stable,
   deterministic relative order for tie-breaking. This grouping does
   *not* control the strategy's actual placement order any more — see
   **Anti-cheating seating** (Milestone 11): `ConstraintSeatingStrategy`
   re-interleaves this list internally by course before placing anyone,
   specifically so one course can't claim a long unbroken run of
   placement turns before another gets one. A single-exam generation
   keeps using its original, unchanged sort (one exam only ever has one
   course_id anyway, so there is nothing to interleave).
4. Passes the resulting `student_id -> course_id` mapping to
   `ConstraintSeatingStrategy` directly (a new, optional
   `student_course_ids` constructor argument) instead of letting it
   derive one course id for every student from a single `exam.course_id`
   — which only makes sense for the single-exam case. The interface
   still takes one `Exam`; a session passes a *representative* exam (its
   first) purely so that slot's `exam.id` has something real for an
   already-prevented duplicate-room-id error message — none of its other
   fields are read once `student_course_ids` is supplied.
5. Persists one `SeatingGeneration` (`session_id` set, `exam_id` `NULL`)
   and its `SeatAssignment`s. Each assignment still records its own
   `exam_id` (the specific exam *that student* belongs to, resolved
   per-student during the merge above) — this is what lets a session
   generation's assignments, reports, and API responses recover "which
   course is this student in" without adding a new column anywhere.

Capacity semantics are computed exactly like the single-exam case, from
the same raw counts, now summed across the session: a student left
unassigned because every remaining seat violated a hard constraint is
reported only via `SeatingResult.warnings`, never by reinterpreting
`scheduled_allocation_shortage` or `physical_capacity_shortage` — the
worked example from **Constraint seating strategy** above holds
identically for a session.

### Persistence

```
ExaminationSessionModel   (id, exam_date, time_slot, created_at)
SessionExamModel          (session_id -> ExaminationSessionModel,
                            exam_id -> ExamModel)
```

Both are brand-new tables — no migration needed for existing databases,
since `create_all()` creates any missing table.

`SeatingGenerationModel.exam_id` becomes **nullable**, and gains a new
nullable `session_id` (with a `CHECK` requiring exactly one of the two to
be set — mirrored by `SeatingGeneration.__post_init__` at the domain
level). SQLite has no `ALTER COLUMN`, so relaxing an already-shipped
column's `NOT NULL` needs the standard SQLite rebuild dance:
`_relax_seating_generation_exam_id_nullability()` renames the old table,
creates the new schema, copies every existing row across unchanged (each
keeps its real `exam_id`; the new `session_id` simply starts `NULL` for
all of them), drops the old table, and restores its indexes. No existing
generation or its assignments (referenced by `seating_generation_id`,
never touched) is altered or invalidated — verified against a copy of
the real dev database before this ran against the live one.

`SeatAssignmentModel.exam_id` is **not** changed — it was already
present, and stays `NOT NULL`: every assignment, session or not, still
belongs to exactly one real exam.

### API

```
POST /examination-sessions                              (create)
GET  /examination-sessions                               (list)
GET  /examination-sessions/{session_id}                  (detail)
GET  /examination-sessions/{session_id}/seating/generations
POST /examination-sessions/{session_id}/seating/generate
```

`POST /exams/{exam_id}/seating/generate` is completely unchanged —
same request shape, same response shape, same behavior; it still
generates seating for exactly one exam. `GET /seating/generations/{id}/assignments`
(generation-scoped, not exam-scoped) needed no new endpoint to support
sessions — it already worked by `generation_id` alone; it now also
resolves each assignment's `course_id`/`course_code` (batch-resolved
once per unique exam referenced, not once per assignment), which single-
exam responses get too, for consistency. A `RoomTopologyMissingError`/
`RoomTopologyMismatchError`/`UnknownRoomTopologyError` during session
generation maps to `400`, the same way it already did for the single-exam
endpoint.

### Reports

`ReportService` branches once, at load time, on whether a generation has
an `exam_id` or a `session_id`, and produces the *same* header shape
(`course_code`, `course_name`, `exam_date`, `time_slot`) and the *same*
room-order list either way — the ReportLab renderers in `app/reports/`
are completely untouched. For a session, multiple courses are joined into
one display string (e.g. `"PHY101, CHEM101"`) rather than inventing a new
report layout, and room order is the concatenation of each session exam's
own canonical room order.

### Frontend

Two new pages: `/examination-sessions` (list existing sessions; create
one by checking compatible exams — exams whose date/time differ from the
first one checked are visibly disabled, not silently rejected only on
submit) and `/examination-sessions/[sessionId]` (mirrors the exam detail
page: stats, courses, rooms, a Constraint-only Generate Seating action,
capacity diagnostics, generation history). `AssignmentsViewer` gained an
optional course column and course filter, shown only when a generation's
assignments actually span more than one course — a single-exam
generation's view is visually unchanged. No seat-map, no drag-and-drop,
no Optimization option anywhere.

## Physical seat layout and availability (Milestone 10)

Milestone 8 gave rooms a *shape* (`rows`/`columns`) but every seat within
that shape was implicitly usable. Milestone 10 adds the ability to mark
individual seats within an otherwise-configured topology as **blocked**
(broken chair, seat too close to a wall socket, reserved for invigilator
equipment, etc.) — a seat that physically exists but must never receive a
student.

```
SeatPosition
    room_id, seat_number, row, column
    available: bool = True   # False only for a blocked seat
```

A blocked seat is not removed from the topology or renumbered — it is
still a real `SeatPosition` that participates in adjacency/distance
queries exactly like any other seat (blocking a seat next to seat 12
still makes seat 12 "have a blocked neighbor," which is a fact a future
anti-cheating constraint might one day care about). It is excluded only
from the *usable* candidate list that strategies draw seat assignments
from:

```python
class SeatTopology(ABC):
    def all_positions(self) -> list[SeatPosition]: ...     # every physical seat, row-major
    def usable_positions(self) -> list[SeatPosition]: ...  # all_positions() minus blocked ones, same order
    physical_capacity: int   # len(all_positions())
    usable_capacity: int     # len(usable_positions())
```

`RectangularRoomTopology` takes an optional `blocked_seat_numbers`
(any iterable of ints, deduplicated and range-validated against
`1..physical_capacity`) and filters exactly those seat numbers out of
`usable_positions()`, preserving row-major order — blocking never
reshuffles or renumbers the remaining seats.

### Where blocking is configured (and the persistence decision)

The milestone's own worked example (the Rooms page showing a room's
*Usable Seats* differing from its *Physical Capacity* on the persistent
room list itself) can only be true if blocking is remembered per-room,
not re-supplied per seating run. Rather than guess, this was confirmed
with the project owner directly: **blocking is persisted on `Room`**,
the same way `warnings` already is — a single additive, nullable-safe
JSON column, `Room.blocked_seat_numbers`, no separate seats table:

```
Room
    code, capacity, rows, columns
    blocked_seat_numbers: list[int] = []   # new, JSON column
```

Deliberately **not** built, per the milestone's own scope boundary:
- A `Seat` database table or any seat-level CRUD endpoint.
- A graphical seat designer (drag-and-drop, canvas, etc.) — blocking is
  configured the same way topology itself is: through the room-import
  CSV.
- Any optimization (OR-Tools/CP-SAT/ILP/backtracking/ML) to *choose*
  which seats to block — blocking is an administrative fact supplied by
  the operator, never inferred or optimized.

`app.db.init_db._ensure_room_blocked_seats_column()` adds the column via
a single `ALTER TABLE rooms ADD COLUMN blocked_seat_numbers JSON NOT NULL
DEFAULT '[]'` — SQLite supports a `NOT NULL DEFAULT` addition to an
existing table directly, unlike the exam_id-nullability change Milestone
9 needed, so no table-rebuild dance is required here. Every pre-Milestone-10
room simply gets `blocked_seat_numbers = []` ("nothing blocked"), which is
byte-for-byte the same seating behavior as before this milestone.

### Room import

A third optional CSV column, `blockedseats`, joins `rows`/`columns`:

```
room,capacity,rows,columns,blockedseats
500,20,4,5,7;17
```

Seat numbers are semicolon-separated within the cell (the CSV's own
delimiter is already the comma). Blocked seats require a topology on the
*same* row — a room with no `rows`/`columns` configured has no seat
numbering to block seats within, so `blockedseats` without topology is a
validation error for that row, matching how a rows/columns mismatch is
already rejected outright rather than partially applied. The same
backfill/conflict policy already established for topology applies here
too: an existing room with no blocked seats gets them backfilled from a
later import row; an existing room whose blocked seats disagree with the
row is reported as a `room_blocked_seats` conflict and left unchanged.

### Strategy behavior

Both `SequentialSeatingStrategy` and `ConstraintSeatingStrategy` draw
seat-number candidates exclusively from `usable_positions()` (falling
back to plain `1..capacity` when no topology is configured at all, the
same "sequential never requires a topology" guarantee Milestone 8
established) — a blocked seat is skipped the same unremarkable way a
seat that's already been filled is skipped, never as a bolted-on special
case in the fill loop. For a room with zero blocked seats, the usable
list is identical to the old raw range, so every pre-Milestone-10 test
scenario (no topology, or topology with nothing blocked) produces
byte-identical assignments to before.

`usable_capacity_shortage` (see **Three distinct shortage diagnoses**
above) is the new, third capacity flag this makes possible:
`registered_student_count > total_usable_capacity`. Because it can be
true independently of `physical_capacity_shortage`, both strategies take
care to only describe a shortage as "caused by blocked seats" in their
warning text when usable capacity is actually less than physical
capacity for the affected room(s) — a pure physical-capacity shortfall
(no blocking involved at all) gets its own, separate wording rather than
misleadingly claiming seats are blocked when none are.

### Frontend

`RoomOut` gained `blocked_seat_numbers`, `physical_capacity`, and
`usable_capacity` (the latter two `null` together whenever no topology is
configured, mirroring `rows`/`columns`). The Rooms page adds three
columns — *Physical Capacity*, *Usable Seats*, *Blocked Seats* — next to
the existing *Rows*/*Columns*/*Topology* ones. `CapacityDiagnostics`
gained a third, separately-labeled diagnostic item for
`usable_capacity_shortage`, alongside the two Milestone 9 already showed.
No seat-map UI, no per-seat click-to-block control anywhere — blocking
remains CSV-import-only, matching the persistence decision above.

## Anti-cheating seating (Milestone 11)

Milestone 7's `ConstraintSeatingStrategy` could already seat several
courses into one shared room (Milestone 9), but its own default soft
constraint (`SeparateCoursesConstraint`) preferred that adjacent seats
hold the *same* course — i.e. each course seated as one contiguous
block. That is exactly backwards for a real exam room: two courses
sharing a room is supposed to make copying harder, not produce

```
P P P P P
P P P P P
C C C C C
C C C C C
```

Milestone 11 replaces that default with a topology-aware anti-cheating
heuristic, without touching `SequentialSeatingStrategy`, without
bypassing `SeatingEngine`/`SeatingStrategy`, and without adding a second
topology system — the new code only ever calls `SeatTopology`'s existing
`same_row`/`same_column`/`is_adjacent`/`distance`.

### Two pieces, both in `app/seating/anti_cheating.py`

1. **Placement order** — `order_students_for_placement(students,
   student_course_ids)` interleaves the students handed to the greedy
   placement loop by course: on every turn it takes the next student from
   whichever course currently has the most students still waiting, ties
   broken by the smallest course_id. This is what stops one course from
   claiming a long unbroken run of placement turns before another course
   gets one — the root cause of contiguous blocks even when individual
   seat choices look locally reasonable. It is generic across course
   *count* by construction: 2, 3, 4, 6, or 50 courses all go through the
   same loop, and a dominant course's turns simply taper off as its own
   remaining count drops to meet the next-largest course (see the
   function's own docstring for a worked example with a 12/4 split).
2. **Candidate scoring** — `same_course_penalty(candidate, course_id,
   placed, student_course_ids, topology)` replaces the old soft-
   constraint-violation *count* as the greedy loop's tie-breaking score
   among candidates that already survive hard-constraint filtering. It
   compares `candidate` only against **the same course's** already-placed
   positions (a different course nearby is never penalized — mixing
   courses is the goal), weighing, worst to least severe: orthogonal
   same-course adjacency, diagonal same-course adjacency, same-row
   concentration, same-column concentration, local density (any
   same-course neighbor within `LOCAL_DENSITY_RADIUS` seat-units), and
   raw proximity to the nearest same-course student. The weights are
   chosen so each tier dominates every lower tier combined (a
   deliberately lexicographic-like ordering expressed as arithmetic, not
   a tuned model) — see the module's own docstring for the exact values
   and reasoning.

Both are **skipped entirely** — falling back to the exact original
zero-violations-wins behavior — whenever fewer than two distinct courses
are present in the student/course mapping. A single-course exam has no
other course to separate from; applying anti-cheating scoring anyway
would scatter that exam's own students for no reason.
`tests/services/test_constraint_seating_integration.py::test_constraint_and_sequential_strategies_agree_when_unconstrained`
and several tests in `tests/seating/test_anti_cheating.py` pin this down
directly: with one course, `ConstraintSeatingStrategy` still produces
byte-identical assignments to `SequentialSeatingStrategy`.

### Where this plugs into `ConstraintSeatingStrategy`

Only the strategy's own *default* (`constraint_set=None`, as opposed to
an explicitly-supplied — even empty — `ConstraintSet()`) uses any of
this. An explicit `ConstraintSet` (however it was built — empty, hard
constraints only, or with a caller's own `SeparateCoursesConstraint`)
opts out entirely and runs the original, unmodified boolean hard/soft
constraint evaluation from Milestone 7 — this is what keeps every
existing constraint-model test (`test_constraints.py`, most of
`test_constraint_strategy.py`) byte-for-byte unchanged; only the two
tests that exercised the *old default's* clustering behavior specifically
needed updating, since that behavior was the thing being fixed. In
production, `SeatingService.generate()` and `.generate_session()` never
supply an explicit `ConstraintSet`, so both single-exam and multi-course
session generation always go through the new default path — for a
single-exam generation this is a no-op (one course), and for a session it
is exactly where anti-cheating separation matters.

`SeparateCoursesConstraint` itself (`app/seating/constraints.py`) still
exists, is still fully tested, and still means what it always meant
(prefer same-course adjacency) — it simply is not what
`ConstraintSeatingStrategy` reaches for by default anymore. It remains
available as an explicit, opt-in constraint for a caller with a genuinely
different goal (e.g. deliberately keeping one course together for
logistics reasons), the same way `StudentsNotAdjacentConstraint` remains
available as an explicit hard constraint.

### This is a heuristic, not a solver

Exactly like `ConstraintSeatingStrategy`'s own greedy placement (Milestone
7), this is a deterministic constructive heuristic: no OR-Tools, no
CP-SAT, no ILP, no backtracking, no graph-coloring solver, no genetic
algorithm, no simulated annealing, no machine learning, and no
randomness. It does **not** guarantee a globally optimal spatial
arrangement, and does not claim any particular seating matrix is "the"
correct answer for a given input — only that it materially reduces
same-course adjacency relative to the naive course-blocked ordering this
milestone replaces. `app/seating/quality_metrics.py`'s
`evaluate_seating_quality` (pure, test-only, never imported by production
code) is what the test suite uses to check that "materially reduces"
claim on representative cases (2/3/4/6-course, unequal course sizes,
blocked seats present) — see that module's own docstring for exactly
what each measurement means (same-course adjacent pairs, diagonal pairs,
local pair count, row/column distribution) and its explicit statement
that it does not define a single combined "score" or claim optimality.

### What is intentionally *not* solved by this milestone

- No proctor/invigilator seating or allocation.
- No student behavioral profiling, biometric integration, or
  surveillance functionality of any kind.
- No manual drag-and-drop seat editor — blocking and course assignment
  remain exactly as configured elsewhere (CSV import, registrations).
- No admin-configurable weights for the scoring tiers above — the
  weights are fixed constants in `anti_cheating.py`, matching this
  milestone's "a simple deterministic scoring model is preferred, do not
  over-engineer" instruction; a future milestone could expose them if a
  real need for tuning ever appears.
- No support for combining a caller-supplied hard constraint (e.g.
  `StudentsNotAdjacentConstraint`) with the anti-cheating default
  *simultaneously* — supplying any explicit `ConstraintSet` opts out of
  anti-cheating entirely (see above). Nothing in production needs this
  combination today (there is no admin UI for custom hard constraints at
  all — see "What is intentionally deferred" below); a future milestone
  that adds one would need to decide how the two interact.
- No claim of finding a feasible seating whenever one exists, or of
  finding the spatially-best seating among all feasible ones — same
  limitation `ConstraintSeatingStrategy`'s greedy placement has always
  had (Milestone 7).

### Frontend

No new page, no seating editor. The exam detail page shows a small
"Constraint strategy: anti-cheating spatial separation enabled" note
whenever the Constraint strategy is selected; the session detail page
(which only ever generates with the constraint strategy) shows the same
note unconditionally. Neither changes what the strategy selector offers,
the result stats shown, or how capacity diagnostics/warnings/assignments
are displayed.

### Validation (Milestone 13)

`tests/seating/test_anti_cheating_validation.py` and one added test in
`tests/services/test_session_seating_generation.py` are a focused
validation suite, not a new algorithm: for a representative set of
fixtures (2/3/5/6-course, unequal sizes, a dominant course, tiny
courses, blocked seats, a 2x10 and a 5x8 room, a real multi-course
session), each generates the *same* input through both
`SequentialSeatingStrategy` and `ConstraintSeatingStrategy` and compares
same-course spatial adjacency with `quality_metrics.evaluate_seating_quality`.
This confirms the deterministic heuristic behaves as intended across
realistic shapes — it does **not** establish or claim mathematical
optimality, and no test asserts a universal percentage improvement:
actual effectiveness depends on room topology, course size distribution,
blocked seats, and any hard constraints in play, and a highly unequal or
capacity-constrained fixture may show a smaller (though still verified
non-negative) improvement than a balanced one.

## Physical seat map (Milestone 12, frontend visualization only)

`components/seating/SeatMap.tsx` renders the room-by-room physical grid
a generation's assignments actually landed in, next to the existing
assignment table on both the exam and session detail pages. No backend
change was needed: `GET /rooms` already exposes each room's own
`rows`/`columns`/`blocked_seat_numbers`, and `GET
/seating/generations/{id}/assignments` already gives each assignment's
`room_id`/`seat_number` — the component maps a seat number to its
row/column itself (`row = floor((seat_number-1)/columns)`, `column =
(seat_number-1) % columns`), the exact formula
`RectangularRoomTopology.position_for_seat` uses on the backend, rather
than inferring position from assignment list order.

Every physical seat in `1..rows*columns` gets a cell, in one of three
states: **occupied** (has an assignment — shows seat number, course
code, and student number, colored per course), **empty** (usable, no
assignment yet), or **blocked** (in the room's `blocked_seat_numbers` —
shown distinctly from empty, never as if it were available). Course
colors cycle through a fixed palette keyed by each course's alphabetical
position, shared across every room in one generation; the course code is
always shown as text too, so information is never carried by color
alone. A wide room scrolls horizontally inside its own container
(fixed-width cells, `overflow-x-auto`) rather than shrinking seats or
breaking the page layout.

This is visualization-only: nothing is clickable, editable, or
persisted, and no seating decision is made or changed here — it reads
the same finished assignments the table and PDF reports already read.

## Persistence boundary

- SQLite via SQLAlchemy 2.0 declarative models (`app/db/models.py`).
  Milestone 3 added `expected_student_count` and `day_label` columns plus
  a `UNIQUE(course_id, exam_date, time_slot)` constraint to the existing
  `exams` table, and a new `exam_rooms` table
  (`UNIQUE(exam_id, room_id)`).
- `app/db/init_db.py` creates tables via `Base.metadata.create_all()`.
  This remains the appropriate mechanism for *new* tables: there is no
  schema history to reconcile across environments yet.
- **Schema-compatibility guard.** `create_all()` cannot alter a table
  that already exists — it silently does nothing to it. Because
  Milestone 3 added required columns to the already-shipped `exams`
  table, `init_db()` now calls `check_schema_compatibility()` first,
  which inspects any pre-existing `exams` table and raises
  `SchemaCompatibilityError` — refusing to proceed — if it's missing a
  column this milestone requires. **This guard is not a migration tool
  and is not a replacement for one.** It does not alter, upgrade, or
  transform an incompatible schema in any way; it only detects the
  incompatible case and stops loudly instead of leaving the app to fail
  later with a confusing "no such column" error, or silently running
  against a half-stale schema. A real schema change against a database
  that already holds data still requires an actual migration (e.g.
  introducing Alembic at that point) — the guard exists so that need
  becomes an explicit, safe stop rather than silent corruption.
- Engine/session construction reads `DATABASE_URL` from `app.config.Settings`
  (environment-variable driven, prefix `APP_`, `.env`-file supported) —
  never a hardcoded path. A relative SQLite file path's parent directory
  is created on demand; in-memory SQLite (used by the test suite) is
  pinned to a single shared connection via `StaticPool` so a test's
  `init_db()` and its later queries see the same database.
- `get_db_session()` is a FastAPI dependency, overridable in tests
  (`app.dependency_overrides`), so tests never touch a real file-backed
  database.

## API boundary

- FastAPI app factory (`create_app()` in `app/main.py`) rather than a
  bare module-level app doing setup work at import time. A `lifespan`
  hook calls `init_db()` on startup (idempotent, and now guarded — see
  above) so a fresh database is ready without a separate manual step.
- Routers live in `app/api/`, one module per concern: `health.py`,
  `registrations.py`, `schedules.py`, `exams.py`, `rooms.py`.
- Current endpoints: `GET /health`, `POST /registrations/import`,
  `GET /students`, `GET /courses`, `GET /registrations`,
  `POST /schedules/import`, `GET /exams`, `GET /exams/{exam_id}`,
  `POST /rooms/import`, `GET /rooms`. All list endpoints support
  `limit`/`offset` pagination. No SQLAlchemy model or raw dict is ever
  returned directly — every response is a Pydantic model in
  `app/api/schemas.py`.

## Report boundary (Milestone 5: implemented)

```text
API (app/api/reports.py)
 ↓
ReportService (app/services/reports/service.py)
 ↓
repositories (SeatingGeneration, SeatAssignment, Exam, ExamRoom, Course, Room, Student — read-only)
 ↓
ReportLab adapter (app/reports/seating_report.py, app/reports/ranges_report.py)
 ↓
PDF bytes → FastAPI Response(media_type="application/pdf")
```

`app/reports/` holds only pure rendering functions
(`render_seating_report`, `render_ranges_report`) that take a plain
dataclass (`app.reports.models`) and return PDF bytes — no FastAPI, no
SQLAlchemy, no filesystem, no repositories. `app/services/reports/`
assembles that dataclass by reading (never writing) from repositories.
Neither layer imports `app/seating/` — the seating engine and its
strategies remain completely unaware that ReportLab, PDF generation, or
HTTP responses exist, and nothing in the report path can trigger a
seating generation.

**Legacy code assessment** (`views/seating_view.py`,
`views/ranges_view.py`): each file's `generate_pdf` method — the actual
ReportLab table/paragraph layout — was already clean, dependency-free
code and is reused almost verbatim (same column widths, same table
style, same paragraph structure). What was **not** reused: each class's
constructor, which wrote directly to `./outputs/{date}/...` on disk (the
new adapters take a `BytesIO` buffer and return bytes instead, so the API
can serve the PDF over HTTP with no filesystem coupling); and the data
these views were fed, which came from `main.py`'s global, mutating
`registerationObj`/`rangesObj` dicts built while walking the schedule
FIFO-style — that data source no longer exists and is replaced by
`ReportService` reading persisted `SeatAssignment` rows for one specific
`SeatingGeneration`.

**Supported report types:**
- **Seating Arrangement Report** (`SeatingReportData` /
  `render_seating_report`) — one PDF per generation, with a room-by-room
  section (room code, then a `Seat# | Student ID | Name | Signature`
  table) covering every room that has at least one assignment in that
  generation, in the exam's canonical room order (see "Deterministic
  ordering" above).
- **ID Range Report** (`RangeReportData` / `render_ranges_report`) — the
  legacy "start ID / end ID per room" report, preserved because it
  remains meaningful under the new model: since students are assigned in
  deterministic student-number order and a room's seat numbers are
  contiguous within that order, `min`/`max` student_number among a room's
  `SeatAssignment` rows is a faithful start/end ID range — not an
  incidental one. One documented deviation: the legacy table's last
  column was labeled "Capacity" but actually held the count of students
  *assigned* to that room, not the room's physical capacity — reusing
  that label here would recreate exactly the ambiguity the capacity-
  semantics work (the `c68a355` follow-up) fixed elsewhere, so this
  column is labeled "Assigned" instead. A room with zero assigned
  students in a given generation is omitted from both reports' room
  lists rather than shown with an empty range.

**Report data source and the core invariant:** both report types are
built exclusively from a specific, already-persisted `SeatingGeneration`
and its `SeatAssignment` rows (`SeatAssignmentRepository.list_by_generation(generation_id)`).
`ReportService` never calls `SeatingService`, never touches
`app/seating/`, and never re-queries current registrations — a report
for generation X reflects generation X's stored assignments, permanently,
even after later regenerations for the same exam create generations
Y, Z, .... This is what makes per-generation reports meaningful once
multiple generations exist for one exam (see "Generation status" and
"Seating generation" above — regeneration was already designed to be
non-destructive; reports are simply a read view over that same
append-only history).

**Report endpoints** (`app/api/reports.py`), both scoped to an existing
generation, never to an exam directly — requesting a report can never
create or recompute a generation as a side effect:
- `GET /seating/generations/{generation_id}/reports/seating`
- `GET /seating/generations/{generation_id}/reports/ranges`

Both return `application/pdf` with `Content-Disposition: inline` (so a
plain `<a target="_blank">` link lets the browser display the PDF rather
than forcing a download — the frontend's report buttons are exactly
that, no blob-fetching JavaScript involved). Error behavior: unknown
`generation_id` → 404; a generation with zero `SeatAssignment` rows
(e.g. `status: failed`, or an exam with no rooms ever scheduled) → 409,
not a silently-empty PDF, so a genuine data gap stays visible instead of
looking like a successful-but-blank report; an unexpected rendering
failure → 500 with a generic message (the real exception is logged, not
returned to the client). "Invalid report type" needs no special handling
— it's just a 404 from normal FastAPI routing, since only these two
paths exist under `/reports/`.

## Future extension points

- **New seating strategy**: implement `SeatingStrategy`, register it,
  select it via `strategy_name`. No other layer changes.
- **New registration source** (e.g. reviving a live API import instead of
  CSV upload): add a new adapter at the `services/` boundary that
  produces the same `Registration`/`Student`/`Course` domain objects the
  CSV path produces. `domain/`, `repositories/`, `api/` response shapes
  are unaffected.
- **Seat-level anti-cheating adjacency**: seat-level layout and
  availability already exist (`SeatTopology`, `SeatPosition`, blocked
  seats — Milestone 10); what remains is a constraint that actually
  *uses* adjacency-to-a-blocked-seat as a rule, and a `Seat` database
  entity if per-seat state beyond blocked/usable is ever needed.
- **Constraint configuration**: introduce a `Constraint` entity and a
  `SeatingGeneration.config` payload once `ConstraintSeatingStrategy`'s
  actual requirements are known.
- **Generation history/comparison**: `SeatingGeneration` already gives
  every run an identity; a comparison feature is a read-side
  service/endpoint over existing rows, not a schema change.
- **Real schema migrations**: if a future schema change needs to run
  against a database that already holds real data, introduce Alembic at
  that point (see **Persistence boundary** — the current guard is a
  safety stop, not a substitute for this).

## What is intentionally deferred

The following are **not** implemented yet, anywhere in the codebase:

- **Optimization-based seating** — `ConstraintSeatingStrategy` (Milestone
  7) is a deterministic greedy heuristic, not a solver: no OR-Tools,
  CP-SAT, ILP, backtracking, or randomness, and it is not guaranteed to
  find a feasible seating even when one exists. `OptimizationSeatingStrategy`
  itself does not exist, and no solver has been chosen — the constraint
  model needs to prove itself first.
- **Graphical/admin room-layout configuration.** `Room.rows`/`Room.columns`
  (Milestone 8) are real, persisted, per-room fields, configurable via the
  room import CSV's optional `Rows`/`Columns` columns, and
  `RepositoryRoomTopologyProvider` reads them for *any* room code — this
  is no longer the Milestone 7 hardcoded two-room demo mapping. What's
  still missing is only the *editing surface*: no drag-and-drop layout
  designer, no graphical seat map, no way to set topology except by
  (re-)importing a CSV row. A room with no topology configured is normal,
  valid state (`RoomTopologyMissingError` only when constraint seating
  actually needs one — see **Room topology** above).
- **Mixed-course seating is implemented as of Milestone 9** (see
  **Examination sessions and multi-course seating**) — this bullet
  previously said it was deferred; it no longer is.
  `POST /examination-sessions/{session_id}/seating/generate` genuinely
  seats several courses together, including sharing one physical room
  across exams when the combined allocation fits. What remains genuinely
  deferred around it specifically: a room can be shared by at most the
  exams already validated not to over-commit it (no partial/percentage
  room splits, no reshuffling an existing session's rooms after the
  fact), and the constructive greedy algorithm inherits the same
  no-backtracking limitation `ConstraintSeatingStrategy` already has for
  a single exam.
- **Constraint management / admin-configurable constraints** —
  `HardConstraint`/`SoftConstraint` (Milestone 6) are real, working types,
  and `ConstraintSeatingStrategy` (Milestone 7) actually evaluates them
  during generation, but there is no UI or persistence for an admin to
  define which specific students should (or shouldn't) sit together;
  today's default constraint set is built entirely in code
  (`_build_student_seating_contexts` in `strategies/constraint.py`).
- **Per-seat blocking/availability is implemented as of Milestone 10**
  (see **Physical seat layout and availability** above) — this used to be
  entirely absent. What's still missing: a `Seat` database table or
  per-seat CRUD endpoint (blocking is configured only via the room-import
  CSV's optional `blockedseats` column, backed by a single JSON column on
  `Room`), any graphical seat designer, and any anti-cheating rule that
  reasons about *which specific* seats are adjacent to a blocked one
  (the topology can already answer that query — see `is_adjacent` — but
  no constraint uses it yet).
- **Advanced seating UI** (seat-map visualization, drag-and-drop).
- **Generation comparison UI** (diffing/comparing `SeatingGeneration` runs
  side by side — each generation's own report is available (Milestone 5),
  but nothing compares two generations against each other).
- **Alembic** — the schema-compatibility guard added in Milestone 3 is a
  safety mechanism, not a migration tool (see **Persistence boundary**);
  Alembic itself remains unintroduced.
- Redis, Celery, message queues, microservices, Kubernetes, PostgreSQL —
  none are justified by current scale or requirements.
- Authentication/authorization (not required by anything built so far).
