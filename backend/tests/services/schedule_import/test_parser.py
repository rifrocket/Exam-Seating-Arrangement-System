"""Parser tests use only synthetic data, formatted to match the legacy
schedule CSV's exact column contract (as surveyed across input/*.csv):
Day, Date, Time, Level, Course Code, Course Name, Instructor,
No. of Students, Required No. of Proctors, Room(s),
No. of Students/ Room, No. of proctors / Room, Proctor(s)
Only the columns the parser actually requires are included below.
"""

from app.services.schedule_import.parser import parse_schedule_csv

HEADER = "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"


def test_valid_schedule_produces_one_exam_group() -> None:
    csv_text = HEADER + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"

    result = parse_schedule_csv(csv_text)

    assert result.rows_read == 1
    assert result.validation_errors == []
    assert len(result.exam_groups) == 1
    group = result.exam_groups[0]
    assert group.course_code == "CS101"
    assert group.exam_date.isoformat() == "2024-05-30"
    assert group.time_slot == "10:00-12:00"
    assert group.expected_student_count == 80
    assert len(group.exam_rooms) == 1
    assert group.exam_rooms[0].room_code == "101"
    assert group.exam_rooms[0].allocated_students == 40


def test_multiple_rooms_for_one_exam_become_one_group() -> None:
    csv_text = HEADER + (
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,102,40\n"
    )

    result = parse_schedule_csv(csv_text)

    assert len(result.exam_groups) == 1
    group = result.exam_groups[0]
    assert {er.room_code for er in group.exam_rooms} == {"101", "102"}
    assert result.conflicts == []


def test_whitespace_variants_in_time_still_identify_the_same_exam() -> None:
    csv_text = HEADER + (
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
        "Thursday,30-May-24,10:00 - 12:00,CS101,Intro to Computer Science,80,102,40\n"
    )

    result = parse_schedule_csv(csv_text)

    assert len(result.exam_groups) == 1
    assert result.exam_groups[0].time_slot == "10:00-12:00"


def test_multiple_exams_different_dates_times() -> None:
    csv_text = HEADER + (
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
        "Friday,31-May-24,12:30-2:30,CS102,Data Structures,50,102,50\n"
    )

    result = parse_schedule_csv(csv_text)

    assert len(result.exam_groups) == 2
    assert {g.course_code for g in result.exam_groups} == {"CS101", "CS102"}


def test_course_name_conflict_within_file() -> None:
    csv_text = HEADER + (
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
        "Friday,31-May-24,12:30-2:30,CS101,Introduction to CS,80,102,40\n"
    )

    result = parse_schedule_csv(csv_text)

    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.kind == "course_name"
    assert conflict.existing_value == "Intro to Computer Science"
    assert conflict.incoming_value == "Introduction to CS"
    # Canonical (first-seen) name wins for both groups.
    assert all(g.course_name == "Intro to Computer Science" for g in result.exam_groups)


def test_expected_student_count_conflict_across_room_rows() -> None:
    csv_text = HEADER + (
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,90,102,40\n"
    )

    result = parse_schedule_csv(csv_text)

    assert len(result.exam_groups) == 1
    assert result.exam_groups[0].expected_student_count == 80  # first-seen wins
    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "expected_student_count"
    assert result.conflicts[0].existing_value == "80"
    assert result.conflicts[0].incoming_value == "90"


def test_exam_room_allocation_conflict() -> None:
    csv_text = HEADER + (
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,45\n"
    )

    result = parse_schedule_csv(csv_text)

    group = result.exam_groups[0]
    assert len(group.exam_rooms) == 1
    assert group.exam_rooms[0].allocated_students == 40  # first-seen wins
    assert len(result.conflicts) == 1
    assert result.conflicts[0].kind == "exam_room_allocation"


def test_exact_duplicate_room_row_is_counted_not_duplicated() -> None:
    csv_text = HEADER + (
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
    )

    result = parse_schedule_csv(csv_text)

    assert len(result.exam_groups[0].exam_rooms) == 1
    assert result.duplicate_rows == 1
    assert result.conflicts == []


def test_invalid_date_excludes_only_that_row() -> None:
    csv_text = HEADER + (
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
        "Thursday,44937,10:00-12:00,CS102,Data Structures,50,102,50\n"
    )

    result = parse_schedule_csv(csv_text)

    assert len(result.exam_groups) == 1
    assert len(result.validation_errors) == 1
    assert result.validation_errors[0].field == "Date"
    assert result.validation_errors[0].line_number == 3


def test_invalid_time_excludes_only_that_row() -> None:
    csv_text = HEADER + "Thursday,30-May-24,not-a-time,CS101,Intro to Computer Science,80,101,40\n"

    result = parse_schedule_csv(csv_text)

    assert result.exam_groups == []
    assert len(result.validation_errors) == 1
    assert result.validation_errors[0].field == "Time"


def test_invalid_student_count_is_reported() -> None:
    csv_text = HEADER + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,abc,101,40\n"

    result = parse_schedule_csv(csv_text)

    assert result.exam_groups == []
    assert len(result.validation_errors) == 1
    assert result.validation_errors[0].field == "No. of Students"
    assert "Invalid" in result.validation_errors[0].message


def test_negative_student_count_is_reported() -> None:
    csv_text = HEADER + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,-5,101,40\n"

    result = parse_schedule_csv(csv_text)

    assert result.exam_groups == []
    assert len(result.validation_errors) == 1
    assert "negative" in result.validation_errors[0].message.lower()


def test_negative_room_allocation_is_reported() -> None:
    csv_text = HEADER + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,-1\n"

    result = parse_schedule_csv(csv_text)

    assert result.exam_groups == []
    assert len(result.validation_errors) == 1
    assert result.validation_errors[0].field == "No. of Students/ Room"


def test_empty_schedule_with_header_only_is_not_an_error() -> None:
    result = parse_schedule_csv(HEADER)

    assert result.rows_read == 0
    assert result.exam_groups == []
    assert result.validation_errors == []


def test_completely_empty_file_is_a_validation_error() -> None:
    result = parse_schedule_csv("")

    assert result.exam_groups == []
    assert len(result.validation_errors) == 1
    assert "empty" in result.validation_errors[0].message.lower()


def test_missing_required_column_is_reported() -> None:
    csv_text = "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s)\n"  # missing allocation column

    result = parse_schedule_csv(csv_text)

    assert result.exam_groups == []
    assert len(result.validation_errors) == 1
    assert "No. of Students/ Room" in result.validation_errors[0].message


def test_missing_room_field_is_reported() -> None:
    csv_text = HEADER + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,,40\n"

    result = parse_schedule_csv(csv_text)

    assert result.exam_groups == []
    assert any(e.field == "Room(s)" for e in result.validation_errors)


def test_missing_day_column_is_tolerated() -> None:
    csv_text = (
        "Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
        "30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
    )

    result = parse_schedule_csv(csv_text)

    assert len(result.exam_groups) == 1
    assert result.exam_groups[0].day_label is None


def test_alternate_date_formats_are_supported() -> None:
    csv_text = HEADER + (
        "Sunday,14/1/2024,12:30-2:30,CS103,Algorithms,30,101,30\n"
        'Wednesday,"January 10, 2023",10:00-12:00,CS104,Databases,20,102,20\n'
    )

    result = parse_schedule_csv(csv_text)

    assert result.validation_errors == []
    dates = {g.course_code: g.exam_date.isoformat() for g in result.exam_groups}
    assert dates["CS103"] == "2024-01-14"
    assert dates["CS104"] == "2023-01-10"
