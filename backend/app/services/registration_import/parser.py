"""Parses and validates registration CSV text into normalized records.

Pure function over a string: no file I/O, no FastAPI, no SQLAlchemy. This
is what makes it independently testable, and what lets the API layer stay
free of parsing logic.

Expected columns (matching the legacy repository's registration export
format exactly, so existing CSVs remain compatible):
    student_id, student_name, subject_code, subject_name
"""

import csv
from io import StringIO

from app.services.registration_import.records import (
    Conflict,
    NormalizedRegistrationRow,
    ParsedRegistrationCSV,
    ValidationError,
)

REQUIRED_COLUMNS = {"student_id", "student_name", "subject_code", "subject_name"}


def _empty_result(message: str) -> ParsedRegistrationCSV:
    return ParsedRegistrationCSV(
        rows_read=0,
        records=[],
        validation_errors=[ValidationError(line_number=None, field=None, message=message)],
        conflicts=[],
        duplicate_rows=0,
    )


def parse_registration_csv(csv_text: str) -> ParsedRegistrationCSV:
    reader = csv.DictReader(StringIO(csv_text))

    if reader.fieldnames is None:
        return _empty_result("CSV file is empty or has no header row.")

    header = {name.strip() for name in reader.fieldnames if name is not None}
    missing = REQUIRED_COLUMNS - header
    if missing:
        return _empty_result(f"Missing required column(s): {', '.join(sorted(missing))}.")

    validation_errors: list[ValidationError] = []
    conflicts: list[Conflict] = []
    records: list[NormalizedRegistrationRow] = []

    seen_registration_keys: set[tuple[str, str]] = set()
    canonical_student_name: dict[str, str] = {}
    canonical_course_name: dict[str, str] = {}
    duplicate_rows = 0
    rows_read = 0

    try:
        for line_number, row in enumerate(reader, start=2):
            rows_read += 1

            student_id = (row.get("student_id") or "").strip()
            student_name = (row.get("student_name") or "").strip()
            subject_code = (row.get("subject_code") or "").strip()
            subject_name = (row.get("subject_name") or "").strip()

            row_errors = [
                ValidationError(line_number, field_name, f"{field_name} must not be empty.")
                for field_name, value in (
                    ("student_id", student_id),
                    ("student_name", student_name),
                    ("subject_code", subject_code),
                    ("subject_name", subject_name),
                )
                if not value
            ]
            if row_errors:
                validation_errors.extend(row_errors)
                continue

            if student_id in canonical_student_name:
                existing_name = canonical_student_name[student_id]
                if existing_name != student_name:
                    conflicts.append(
                        Conflict("student_name", student_id, line_number, existing_name, student_name)
                    )
            else:
                canonical_student_name[student_id] = student_name

            if subject_code in canonical_course_name:
                existing_name = canonical_course_name[subject_code]
                if existing_name != subject_name:
                    conflicts.append(
                        Conflict("course_name", subject_code, line_number, existing_name, subject_name)
                    )
            else:
                canonical_course_name[subject_code] = subject_name

            registration_key = (student_id, subject_code)
            if registration_key in seen_registration_keys:
                duplicate_rows += 1
                continue
            seen_registration_keys.add(registration_key)

            records.append(
                NormalizedRegistrationRow(
                    line_number=line_number,
                    student_id=student_id,
                    student_name=canonical_student_name[student_id],
                    subject_code=subject_code,
                    subject_name=canonical_course_name[subject_code],
                )
            )
    except csv.Error as exc:
        validation_errors.append(ValidationError(None, None, f"Malformed CSV: {exc}"))

    return ParsedRegistrationCSV(
        rows_read=rows_read,
        records=records,
        validation_errors=validation_errors,
        conflicts=conflicts,
        duplicate_rows=duplicate_rows,
    )
