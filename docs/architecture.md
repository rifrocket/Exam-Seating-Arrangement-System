# Architecture

This document describes the architecture of the modular Exam Seating
Arrangement System as actually implemented through Milestone 3
(Schedule & Exam Management, commit `94cb6ff`), with the **Seating
strategy abstraction** section additionally updated for Milestone 4
(Seating Engine + Sequential Seating, commit `4b4f2a6`) — the rest of
this document has not been re-synchronized against every Milestone 4
change. It complements — and does not replace — the repository audit,
which explains why the legacy `main.py`/`services/`/`models/`/`views/`
script is being superseded rather than incrementally patched.

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
    api/            HTTP boundary: health, registrations, schedules, exams, rooms
    services/        registration_import/, schedule_import/, room_import.py
                      (seating-generation orchestration reserved for a later milestone)
    domain/          plain domain models
    repositories/    persistence interfaces + SQLAlchemy-backed implementations (db/repositories.py)
    seating/         reserved — no code yet (seating-generation milestone)
    reports/         reserved — no code yet (reports milestone)
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
                                    │       └─>  seating/  ──>  domain/   (reserved, no code yet)
                                    ├─>  repositories/ (interfaces)  ──>  domain/
                                    └─>  reports/  ──>  domain/           (reserved, no code yet)

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
- `app/services/` — `registration_import/` (Milestone 2) and
  `schedule_import/` + `room_import.py` (Milestone 3) are populated;
  each is a pure parser/validator plus a service class that depends only
  on repository interfaces. Seating-generation orchestration remains
  reserved for a later milestone.
- `app/api/*` — FastAPI routers. A router calls a service for import
  endpoints (`registrations.py`, `schedules.py`, `rooms.py`'s import
  route) or composes read-only repository calls directly for list/detail
  endpoints (`students`, `courses`, `registrations`, `rooms`, `exams`,
  `exams/{id}`) — the latter is data composition (assembling a response
  DTO from one or two repository reads), never business logic. No router
  contains parsing, validation rules, or SQL.
- `app/seating/`, `app/reports/` — still empty packages (docstring only).
  Reserved boundaries, not stubs.

## Module responsibilities

| Module | Responsible for | Not responsible for |
|---|---|---|
| `api/` | HTTP request/response shapes, status codes, routing, read-only response composition | validation logic, seating, persistence details |
| `services/` | orchestrating a use case (e.g. "import this registration/schedule/room CSV") | HTTP concerns, SQL, ReportLab calls |
| `domain/` | what a Student/Course/Exam/ExamRoom/Room/etc. *is* | how it's stored, rendered, or transported |
| `repositories/` | the *interface* (and, in `db/`, the concrete implementation) for loading/saving domain objects | business rules about what to load/save and when |
| `seating/` | (reserved) the *interface and orchestration* for turning students+rooms into seat assignments | which concrete algorithm is "best" — that's a strategy's job |
| `reports/` | (reserved) turning domain data into PDFs | deciding what data to show (that's a service's job) |
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

- **Seat** (a physical, addressable seat within a room) — nothing today
  needs seat-level identity; `SeatAssignment.seat_number` is a running
  integer, not a foreign key. Introduce a real `Seat` entity when a
  strategy actually needs seat adjacency (anti-cheating, layout-aware
  constraints). Milestone 3 did not add this even though it introduced
  `ExamRoom` — room-level allocation and seat-level layout are different
  concerns, and nothing yet needs the latter.
- **Constraint** (a generic configurable rule) — no strategy exists yet
  that reads constraints. Designing a generic constraint schema now, with
  nothing to validate it against, would be speculative. `SeatingGeneration`
  is the extension point: it can carry a `config` payload once
  `ConstraintSeatingStrategy` defines what that payload needs to look like.

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

## Report boundary

`app/reports/` is reserved for a direct adaptation of the legacy
`views/seating_view.py` and `views/ranges_view.py` ReportLab code. The
layout logic (tables, margins, headings) is worth preserving as-is; what
changes is the input shape — functions will take domain objects /
service-layer DTOs instead of positional primitive arguments, so report
generation doesn't need to know about HTTP or the database.

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

- **Constraint- and optimization-based seating** — `SeatingEngine` and
  `SeatingStrategy` exist, and `SequentialSeatingStrategy` is implemented
  (Milestone 4). `ConstraintSeatingStrategy` and
  `OptimizationSeatingStrategy` do not exist yet.
- A **physical Seat model** (seat-level identity/layout).
- **Mixed-course seating.**
- **Anti-cheating rules.**
- A **constraint engine** (`ConstraintSeatingStrategy` and any generic
  `Constraint` entity/schema).
- An **optimization engine** (`OptimizationSeatingStrategy`).
- **Advanced seating UI** (seat-map visualization, drag-and-drop).
- **Generation comparison UI** (diffing/comparing `SeatingGeneration` runs).
- **Report generation** *logic* (`app/reports/` module boundary exists;
  its contents do not).
- **Alembic** — the schema-compatibility guard added in Milestone 3 is a
  safety mechanism, not a migration tool (see **Persistence boundary**);
  Alembic itself remains unintroduced.
- Redis, Celery, message queues, microservices, Kubernetes, PostgreSQL —
  none are justified by current scale or requirements.
- Authentication/authorization (not required by anything built so far).
