# Architecture

This document describes the target architecture for the modular Exam
Seating Arrangement System, and which parts of it exist as of the
foundation milestone versus which parts are designed-for but not yet
built. It complements — and does not replace — the repository audit,
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
    api/            HTTP boundary
    services/        application/business services (empty until next milestone)
    domain/          plain domain models
    repositories/    persistence interfaces
    seating/         seating engine + strategies (empty until seating-generation milestone)
    reports/         PDF report generation (empty until reports milestone)
    db/              SQLAlchemy models, session, init
  tests/
frontend/
  app/               Next.js App Router pages (shell only, no business logic)
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
  `app/domain` dataclasses only. No SQLAlchemy import. A concrete,
  SQLAlchemy-backed implementation of these interfaces will live under
  `app/db/` (or `app/repositories/sqlalchemy_*.py`) starting with the
  milestone that first needs one — introducing it now, with nothing to
  read or write yet, would be speculative.
- `app/db/*` — SQLAlchemy `DeclarativeBase`, ORM models, engine/session
  factory, and the `init_db()` mechanism. Depends on `app/domain` (to
  eventually map to/from it) and SQLAlchemy. Nothing outside `db/`
  imports SQLAlchemy directly.
- `app/api/*` — FastAPI routers only. Talks to `services/` (once
  populated) and takes a `Session` via `Depends(get_db_session)`. The
  current `health` endpoint is the only router; it deliberately does a
  trivial `SELECT 1` through the same dependency-injected session future
  endpoints will use, so it also proves the DB wiring end-to-end.
- `app/services/`, `app/seating/`, `app/reports/` — currently empty
  packages (docstring only). Reserved boundaries, not stubs: no
  placeholder classes were added just to make the tree look complete.

## Module responsibilities

| Module | Responsible for | Not responsible for |
|---|---|---|
| `api/` | HTTP request/response shapes, status codes, routing | validation logic, seating, persistence details |
| `services/` | orchestrating a use case (e.g. "import this registration CSV", "generate seating for this exam") | HTTP concerns, SQL, ReportLab calls |
| `domain/` | what a Student/Course/Exam/Room/etc. *is* | how it's stored, rendered, or transported |
| `repositories/` | the *interface* for loading/saving domain objects | the SQL/ORM used to do so |
| `seating/` | the *interface and orchestration* for turning students+rooms into seat assignments | which concrete algorithm is "best" — that's a strategy's job |
| `reports/` | turning domain data into PDFs | deciding what data to show (that's a service's job) |
| `db/` | SQLAlchemy table definitions, engine/session lifecycle, schema initialization | business rules |
| `frontend/` | presentation, calling the API, rendering responses | seating logic, validation logic, direct DB or file access |

## Domain boundaries

Seven entities exist as of this milestone (see the audit for the full
reasoning on what was included vs. deferred):

- **Student** `(id, student_number, full_name)` — full name stored
  complete; any truncation (e.g. the legacy 3-token name) is a
  presentation concern for `reports/`, never applied to the stored value.
- **Course** `(id, code, name)`
- **Registration** `(id, student_id, course_id)` — the student↔course join.
- **Exam** `(id, course_id, exam_date, time_slot)` — one scheduled sitting
  of a course.
- **Room** `(id, code, capacity)` — first-class now; the legacy
  `input/locations.csv` shape was never actually wired into the old code.
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

**Deliberately not modeled yet:**

- **Seat** (a physical, addressable seat within a room) — nothing today
  needs seat-level identity; `SeatAssignment.seat_number` is a running
  integer, not a foreign key. Introduce a real `Seat` entity when a
  strategy actually needs seat adjacency (anti-cheating, layout-aware
  constraints).
- **Constraint** (a generic configurable rule) — no strategy exists yet
  that reads constraints. Designing a generic constraint schema now, with
  nothing to validate it against, would be speculative. `SeatingGeneration`
  is the extension point: it can carry a `config` payload once
  `ConstraintSeatingStrategy` defines what that payload needs to look like.

## Seating strategy abstraction (design, not yet implemented)

This shape is approved and documented here so every later milestone
builds toward it, but **no code exists in `app/seating/` yet** — it is
explicitly out of scope for the foundation milestone.

```python
class SeatingStrategy(ABC):
    def generate(self, exam: Exam, students: list[Student], rooms: list[Room]) -> SeatingResult: ...

class SequentialSeatingStrategy(SeatingStrategy):
    """Fills rooms in the given order, taking the next N students in list
    order per room. This is the direct successor to the legacy
    buildRoomsLists FIFO slicing — but, unlike the legacy code, it owns the
    capacity-fit decision itself rather than reading a pre-computed number
    from a schedule CSV column, and it never silently drops a student: any
    student who doesn't fit becomes part of SeatingResult.unassigned."""

class SeatingEngine:
    def __init__(self, strategy: SeatingStrategy): ...
    def run(self, exam, students, rooms) -> SeatingResult: ...
```

`SeatingResult` will explicitly carry `assignments`, `unassigned_students`,
and `capacity_shortage` — the domain must always represent total
registered vs. assigned vs. unassigned vs. capacity shortage as first-class
facts (see `SeatingGeneration` above), never as something to infer from a
diff of files, which was a real limitation of the legacy `left.json`.

Future strategies (`ConstraintSeatingStrategy`,
`OptimizationSeatingStrategy`, `MixedCourseSeatingStrategy`) implement the
same `SeatingStrategy` interface and are selected by `strategy_name` at the
service layer. Adding one requires: a new class in `app/seating/strategies/`
implementing `generate()`, and a registry entry — no change to `api/`,
`db/`, `repositories/`, or `frontend/`.

## Persistence boundary

- SQLite via SQLAlchemy 2.0 declarative models (`app/db/models.py`).
- `app/db/init_db.py` creates tables via `Base.metadata.create_all()`.
  This is the appropriate mechanism for this stage: there is no schema
  history to reconcile across environments yet. If/when the schema needs
  versioned, reviewable migrations (multiple environments, real data
  already in place), introduce Alembic then, as an additive change — not
  before, since an empty migrations directory with a single "initial"
  migration provides no real benefit over `create_all()` today.
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
  bare module-level app doing setup work at import time — keeps
  construction free of side effects and makes it straightforward to
  build a differently-configured app in tests.
- Routers live in `app/api/`, one module per concern (`health.py` today).
  A router depends on `services/`, never directly on `db/` models or
  SQLAlchemy query construction, once `services/` exists.
- The only endpoint today is `GET /health`, which also exercises the
  database dependency (`SELECT 1`) so the health check is a real
  end-to-end signal, not a hardcoded `{"status": "ok"}`.

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

## What is intentionally deferred

Per the approved Phase 1 decisions, the following are **not** implemented
yet, anywhere in the codebase:

- Registration import, schedule import, seating generation, and report
  generation *logic* (their module boundaries exist; their contents do
  not).
- `ConstraintSeatingStrategy`, `OptimizationSeatingStrategy`,
  `MixedCourseSeatingStrategy`, and any constraint/rule engine.
- A physical `Seat` entity or seat-map/layout visualization.
- Generation history *comparison* UI.
- Authentication/authorization (not required by anything built so far).
- Alembic, Redis, Celery, message queues, microservices, Kubernetes,
  PostgreSQL — none are justified by current scale or requirements.
- Any frontend page beyond the default Next.js shell page.
