"""Pydantic request/response models for the API layer.

These are HTTP-facing shapes only; they mirror domain dataclasses and
service result types but never replace them — services and repositories
never import from this module.
"""

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
