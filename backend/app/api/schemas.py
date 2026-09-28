"""Pydantic request/response models for the API layer.

These are HTTP-facing shapes only; they mirror domain dataclasses and
service result types but never replace them — services and repositories
never import from this module.
"""

from datetime import date, datetime

from pydantic import BaseModel


class ValidationErrorOut(BaseModel):
    line_number: int | None
    field: str | None
    message: str


class ConflictOut(BaseModel):
    kind: str
    key: str
    line_number: int
    existing_value: str
    incoming_value: str


class WarningOut(BaseModel):
    kind: str
    line_number: int | None
    message: str


class RegistrationImportResponse(BaseModel):
    status: str
    rows_read: int
    students_created: int
    students_existing: int
    courses_created: int
    courses_existing: int
    registrations_created: int
    registrations_existing: int
    duplicate_rows: int
    validation_errors: list[ValidationErrorOut]
    conflicts: list[ConflictOut]


class StudentOut(BaseModel):
    id: int
    student_number: str
    full_name: str


class CourseOut(BaseModel):
    id: int
    code: str
    name: str


class RegistrationOut(BaseModel):
    id: int
    student_id: int
    course_id: int


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class StudentListResponse(BaseModel):
    items: list[StudentOut]
    meta: PageMeta


class CourseListResponse(BaseModel):
    items: list[CourseOut]
    meta: PageMeta


class RegistrationListResponse(BaseModel):
    items: list[RegistrationOut]
    meta: PageMeta


class RoomOut(BaseModel):
    id: int
    code: str
    capacity: int
    rows: int | None
    columns: int | None
    blocked_seat_numbers: list[int]
    # Both null when no topology is configured. When topology exists,
    # physical_capacity == rows * columns and usable_capacity ==
    # physical_capacity - len(blocked_seat_numbers) — Room itself is the
    # only place blocking is remembered, so these are always in sync with
    # blocked_seat_numbers above, never a separately-configurable fact.
    physical_capacity: int | None
    usable_capacity: int | None


class RoomListResponse(BaseModel):
    items: list[RoomOut]
    meta: PageMeta


class RoomImportResponse(BaseModel):
    status: str
    rows_read: int
    rooms_created: int
    rooms_existing: int
    duplicate_rows: int
    validation_errors: list[ValidationErrorOut]
    conflicts: list[ConflictOut]


class ScheduleImportResponse(BaseModel):
    status: str
    rows_read: int
    exams_created: int
    exams_existing: int
    exam_rooms_created: int
    exam_rooms_existing: int
    duplicate_rows: int
    validation_errors: list[ValidationErrorOut]
    conflicts: list[ConflictOut]
    warnings: list[WarningOut]


class ExamRoomOut(BaseModel):
    id: int
    room_id: int
    room_code: str
    room_capacity: int
    allocated_students: int


class ExamOut(BaseModel):
    id: int
    course_id: int
    course_code: str
    course_name: str
    exam_date: date
    time_slot: str
    day_label: str | None
    expected_student_count: int
    room_count: int


class ExamListResponse(BaseModel):
    items: list[ExamOut]
    meta: PageMeta


class ExamDetailOut(BaseModel):
    id: int
    course_id: int
    course_code: str
    course_name: str
    exam_date: date
    time_slot: str
    day_label: str | None
    expected_student_count: int
    exam_rooms: list[ExamRoomOut]


class SeatingGenerateRequest(BaseModel):
    strategy: str = "sequential"


class SessionSeatingGenerateRequest(BaseModel):
    strategy: str = "constraint"


class SeatingGenerationOut(BaseModel):
    id: int
    exam_id: int | None
    session_id: int | None
    strategy_name: str
    status: str
    total_registered: int
    total_assigned: int
    total_unassigned: int
    capacity_shortage: bool
    warnings: list[str]
    created_at: datetime | None


class SeatingGenerationResponse(SeatingGenerationOut):
    scheduled_student_count: int
    total_physical_capacity: int
    total_usable_capacity: int
    available_capacity: int
    unassigned_student_ids: list[int]
    # `capacity_shortage` (inherited above) only answers "did anyone go
    # unassigned?" — these three answer "why," and are not mutually exclusive.
    scheduled_allocation_shortage: bool
    physical_capacity_shortage: bool
    usable_capacity_shortage: bool


class SeatingGenerationListResponse(BaseModel):
    items: list[SeatingGenerationOut]
    meta: PageMeta


class SeatAssignmentOut(BaseModel):
    id: int
    room_id: int
    room_code: str
    student_id: int
    student_number: str
    student_name: str
    seat_number: int
    exam_id: int
    course_id: int
    course_code: str


class SeatAssignmentListResponse(BaseModel):
    generation: SeatingGenerationOut
    items: list[SeatAssignmentOut]


class ExaminationSessionCreateRequest(BaseModel):
    exam_ids: list[int]


class ExaminationSessionExamOut(BaseModel):
    exam_id: int
    course_id: int
    course_code: str
    course_name: str


class ExaminationSessionOut(BaseModel):
    id: int
    exam_date: date
    time_slot: str
    exams: list[ExaminationSessionExamOut]
    participant_count: int
    room_codes: list[str]


class ExaminationSessionListResponse(BaseModel):
    items: list[ExaminationSessionOut]
    meta: PageMeta
