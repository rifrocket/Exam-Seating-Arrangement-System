"""Parser tests use only synthetic data (never the real student records
committed under data/*.csv), matching the legacy CSV's exact column
contract: student_id, student_name, subject_code, subject_name.
"""

from app.services.registration_import.parser import parse_registration_csv


def test_valid_csv_produces_expected_records() -> None:
    csv_text = (
        "student_id,student_name,subject_code,subject_name\n"
        "1001,Alice Example,CS101,Intro to Computer Science\n"
        "1002,Bob Sample,CS101,Intro to Computer Science\n"
    )

    result = parse_registration_csv(csv_text)

    assert result.rows_read == 2
    assert len(result.records) == 2
    assert result.validation_errors == []
    assert result.conflicts == []
    assert result.duplicate_rows == 0
    assert result.records[0].student_id == "1001"
    assert result.records[0].student_name == "Alice Example"


def test_empty_csv_with_header_only_is_not_an_error() -> None:
    csv_text = "student_id,student_name,subject_code,subject_name\n"

    result = parse_registration_csv(csv_text)

    assert result.rows_read == 0
    assert result.records == []
    assert result.validation_errors == []


def test_completely_empty_file_is_a_validation_error() -> None:
    result = parse_registration_csv("")

    assert result.records == []
    assert len(result.validation_errors) == 1
    assert "empty" in result.validation_errors[0].message.lower()


def test_missing_required_column_is_reported() -> None:
    csv_text = "student_id,student_name,subject_code\n1001,Alice Example,CS101\n"

    result = parse_registration_csv(csv_text)

    assert result.records == []
    assert len(result.validation_errors) == 1
    assert "subject_name" in result.validation_errors[0].message


def test_blank_required_field_excludes_only_that_row() -> None:
    csv_text = (
        "student_id,student_name,subject_code,subject_name\n"
        "1001,Alice Example,CS101,Intro to Computer Science\n"
        "1002,,CS101,Intro to Computer Science\n"
    )

    result = parse_registration_csv(csv_text)

    assert result.rows_read == 2
    assert len(result.records) == 1
    assert len(result.validation_errors) == 1
    assert result.validation_errors[0].field == "student_name"
    assert result.validation_errors[0].line_number == 3


def test_duplicate_registration_row_is_counted_not_duplicated() -> None:
    csv_text = (
        "student_id,student_name,subject_code,subject_name\n"
        "1001,Alice Example,CS101,Intro to Computer Science\n"
        "1001,Alice Example,CS101,Intro to Computer Science\n"
    )

    result = parse_registration_csv(csv_text)

    assert result.rows_read == 2
    assert len(result.records) == 1
    assert result.duplicate_rows == 1
    assert result.conflicts == []


def test_same_student_id_with_conflicting_name_is_a_conflict_not_silent() -> None:
    csv_text = (
        "student_id,student_name,subject_code,subject_name\n"
        "1001,Alice Example,CS101,Intro to Computer Science\n"
        "1001,Alicia Example,CS102,Data Structures\n"
    )

    result = parse_registration_csv(csv_text)

    # Both registrations are still recorded — the conflict is about the name, not the fact.
    assert len(result.records) == 2
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.kind == "student_name"
    assert conflict.key == "1001"
    assert conflict.existing_value == "Alice Example"
    assert conflict.incoming_value == "Alicia Example"
    # The canonical (first-seen) name wins for both records.
    assert all(r.student_name == "Alice Example" for r in result.records)


def test_same_course_code_with_conflicting_name_is_a_conflict_not_silent() -> None:
    csv_text = (
        "student_id,student_name,subject_code,subject_name\n"
        "1001,Alice Example,CS101,Intro to Computer Science\n"
        "1002,Bob Sample,CS101,Introduction to CS\n"
    )

    result = parse_registration_csv(csv_text)

    assert len(result.records) == 2
    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.kind == "course_name"
    assert conflict.key == "CS101"
    assert conflict.existing_value == "Intro to Computer Science"
    assert conflict.incoming_value == "Introduction to CS"
    assert all(r.subject_name == "Intro to Computer Science" for r in result.records)


def test_multiple_students_in_one_course() -> None:
    csv_text = (
        "student_id,student_name,subject_code,subject_name\n"
        "1001,Alice Example,CS101,Intro to Computer Science\n"
        "1002,Bob Sample,CS101,Intro to Computer Science\n"
        "1003,Carla Test,CS101,Intro to Computer Science\n"
    )

    result = parse_registration_csv(csv_text)

    assert len(result.records) == 3
    assert {r.student_id for r in result.records} == {"1001", "1002", "1003"}
    assert {r.subject_code for r in result.records} == {"CS101"}


def test_multiple_courses_for_one_student() -> None:
    csv_text = (
        "student_id,student_name,subject_code,subject_name\n"
        "1001,Alice Example,CS101,Intro to Computer Science\n"
        "1001,Alice Example,CS102,Data Structures\n"
        "1001,Alice Example,CS103,Algorithms\n"
    )

    result = parse_registration_csv(csv_text)

    assert len(result.records) == 3
    assert {r.subject_code for r in result.records} == {"CS101", "CS102", "CS103"}
    assert result.conflicts == []


def test_whitespace_is_normalized_but_content_is_preserved() -> None:
    csv_text = (
        "student_id,student_name,subject_code,subject_name\n"
        "  1001 ,  Alice Example  , CS101 , Intro to Computer Science \n"
    )

    result = parse_registration_csv(csv_text)

    assert result.records[0].student_id == "1001"
    assert result.records[0].student_name == "Alice Example"
    assert result.records[0].subject_code == "CS101"
