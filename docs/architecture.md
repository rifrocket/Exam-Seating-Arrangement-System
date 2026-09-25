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

Nine entities exist as of Milestone 3:

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
- **Room** `(id, code, capacity)` — first-class; seeded from a CSV
  matching the legacy `input/locations.csv` shape (`room, capacity`,
  with an optional ignored `index` column), which the legacy code never
  actually read.
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

**Deliberately still not modeled (unchanged since the foundation
milestone):**

- **Seat** as a *persisted* entity (a physical, addressable seat within a
  room, backed by a database table) — `SeatAssignment.seat_number` is
  still a running integer, not a foreign key, and there is no seat
  database table, layout editor, or frontend seat map. Milestone 6 did
  introduce a pure, in-memory seat topology (`SeatPosition`,
  `SeatTopology`/`RectangularRoomTopology` in `app/seating/topology.py`)
  because a constraint like "not adjacent" needs *some* spatial
  representation to be testable at all — but that representation is
  derived on the fly from a room's (rows, columns), never persisted.
  Introduce a real, persisted `Seat` entity only when a non-rectangular or
  admin-editable layout is actually needed.
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

### Two distinct shortage diagnoses (not one ambiguous flag)

`SeatingGeneration.capacity_shortage` (persisted, unchanged since
Milestone 4) means exactly one thing: `unassigned_student_count > 0` —
"did at least one registered student go unseated in this run, for
whatever reason." It has never meant, and still does not mean, "the
physical rooms were too small" specifically — that would be a different,
narrower claim, and collapsing the two would recreate the same kind of
ambiguity the legacy `min(expected, allocated)` truncation caused.

`SeatingResult` (and the `POST /exams/{id}/seating/generate` response)
carries two further, independent booleans that answer *why*:

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

Neither implies the other; a generation can have either, both, or
neither true. These two flags are **not** persisted on
`SeatingGeneration` — they're recomputed from a live run's
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

`Room` only ever stores a `code` and a physical `capacity` — it has no
rows/columns, and inferring geometry from capacity alone (e.g. "capacity
10 implies 2x5") would fabricate a physical fact the data doesn't have;
two 10-seat rooms can have completely different real layouts.
`RoomTopologyProvider` is the abstract boundary between "a room" and "a
`SeatTopology`":

```python
class RoomTopologyProvider(ABC):
    def get_topology(self, room_id: int, room_code: str, capacity: int) -> SeatTopology: ...
```

`StaticRoomTopologyProvider` is the only implementation so far: a plain,
caller-supplied `room_code -> (rows, columns)` mapping, kept purely in
memory — no database table, no admin UI. It **validates** that the
configured layout's seat count exactly equals the room's actual
`capacity`, raising `RoomTopologyMismatchError` if not (never silently
truncating a layout or padding it with extra seats), and raises
`UnknownRoomTopologyError` for any room code it wasn't given a layout
for — there is no fallback guess.

`ConstraintSeatingStrategy`'s own zero-argument constructor (needed
because `get_strategy()` calls `strategy_cls()` with no arguments) uses
`DEFAULT_DEMO_ROOM_LAYOUTS = {"401": (2, 5), "402": (2, 5)}` — an explicit,
in-memory, demo-only configuration chosen to match this project's own
sample rooms. **Any exam using a room code outside this mapping raises
`UnknownRoomTopologyError` when generated with `strategy="constraint"`** —
this is a real, current limitation of this milestone, not a bug: real,
admin-configurable room layouts are future work (see **What is
intentionally deferred**).

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
to an explicitly empty `ConstraintSet()`) auto-builds one
`SeparateCoursesConstraint` from a `StudentSeatingContext` per registered
student. In production today this is always trivially satisfied — every
student in a single-course exam shares the same `course_id`, since mixed-
course seating does not exist — but it does exercise the real
constraint-evaluation code path on every generation, rather than leaving
it entirely untested against live data.

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
- **Seat-level layout / anti-cheating adjacency**: introduce a `Seat`
  entity and extend `SeatAssignment` to reference it, once a strategy
  needs it.
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
- **Persisted, admin-configurable room layouts** — `RoomTopologyProvider`
  (Milestone 7, `app/seating/topology_provider.py`) is a real, working
  abstraction, but its only implementation (`StaticRoomTopologyProvider`)
  is a fixed, in-memory `room_code -> (rows, columns)` mapping
  (`DEFAULT_DEMO_ROOM_LAYOUTS`) covering exactly two demo room codes
  ("401", "402"). There is no seat database table, no layout editor, and
  no frontend seat map; generating with `strategy="constraint"` for any
  other room code raises `UnknownRoomTopologyError` today.
- **Mixed-course seating.** `StudentSeatingContext.course_id` (Milestone 7)
  exists because `SeparateCoursesConstraint` needs a course id per
  student, not because mixed-course exams are supported — every student
  passed into a strategy today still comes from the same single-course
  `Exam`.
- **Constraint management / admin-configurable constraints** —
  `HardConstraint`/`SoftConstraint` (Milestone 6) are real, working types,
  and `ConstraintSeatingStrategy` (Milestone 7) actually evaluates them
  during generation, but there is no UI or persistence for an admin to
  define which specific students should (or shouldn't) sit together;
  today's default constraint set is built entirely in code
  (`_build_student_seating_contexts` in `strategies/constraint.py`).
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
