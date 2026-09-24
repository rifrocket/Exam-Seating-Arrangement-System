"""API-level tests for report endpoints. All data synthetic."""

from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfReader

REGISTRATIONS_CSV = (
    "student_id,student_name,subject_code,subject_name\n"
    "8001,Jordan Rivera,CS101,Intro to Computer Science\n"
    "8002,Sam Okafor,CS101,Intro to Computer Science\n"
).encode("utf-8")

ROOMS_CSV = b"index,room,capacity\n1,301,10\n"

SCHEDULE_CSV = (
    "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
    "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,2,301,2\n"
).encode("utf-8")


def _upload(client: TestClient, path: str, content: bytes, filename: str = "file.csv"):
    return client.post(path, files={"file": (filename, content, "text/csv")})


def _seed_and_generate(client: TestClient) -> int:
    assert _upload(client, "/registrations/import", REGISTRATIONS_CSV).status_code == 200
    assert _upload(client, "/rooms/import", ROOMS_CSV).status_code == 200
    assert _upload(client, "/schedules/import", SCHEDULE_CSV).status_code == 200
    exam_id = client.get("/exams").json()["items"][0]["id"]
    generation = client.post(f"/exams/{exam_id}/seating/generate").json()
    return generation["id"]


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "".join(page.extract_text() for page in reader.pages)


def test_seating_report_returns_pdf_with_expected_content(client: TestClient) -> None:
    generation_id = _seed_and_generate(client)

    response = client.get(f"/seating/generations/{generation_id}/reports/seating")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(response.content) > 0
    assert response.content.startswith(b"%PDF-")

    text = _extract_text(response.content)
    assert "CS101" in text
    assert "8001" in text
    assert "Jordan Rivera" in text
    assert "301" in text


def test_ranges_report_returns_pdf_with_expected_content(client: TestClient) -> None:
    generation_id = _seed_and_generate(client)

    response = client.get(f"/seating/generations/{generation_id}/reports/ranges")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")

    text = _extract_text(response.content)
    assert "CS101" in text
    assert "8001" in text  # start ID
    assert "8002" in text  # end ID


def test_report_for_missing_generation_returns_404(client: TestClient) -> None:
    seating_response = client.get("/seating/generations/999/reports/seating")
    ranges_response = client.get("/seating/generations/999/reports/ranges")

    assert seating_response.status_code == 404
    assert ranges_response.status_code == 404


def test_report_for_generation_with_no_assignments_returns_409(client: TestClient) -> None:
    # A registered course whose schedule references a room that was never
    # seeded: the exam is still created (per Milestone 3 policy — unknown
    # rooms are reported, not fabricated), but zero ExamRoom rows exist,
    # so generation has registered students yet cannot seat any of them.
    _upload(
        client,
        "/registrations/import",
        b"student_id,student_name,subject_code,subject_name\n9001,Nobody Seated,CS999,Empty Course\n",
    )
    _upload(
        client,
        "/schedules/import",
        (
            "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
            "Thursday,30-May-24,10:00-12:00,CS999,Empty Course,1,999,1\n"
        ).encode("utf-8"),
    )
    exams = client.get("/exams").json()["items"]
    exam_id = next(e["id"] for e in exams if e["course_code"] == "CS999")

    generation = client.post(f"/exams/{exam_id}/seating/generate").json()
    assert generation["total_registered"] == 1
    assert generation["total_assigned"] == 0
    assert generation["status"] == "failed"

    response = client.get(f"/seating/generations/{generation['id']}/reports/seating")

    assert response.status_code == 409


def test_report_never_regenerates_seating(client: TestClient) -> None:
    """Requesting a report twice must not create new SeatAssignment rows
    or a new SeatingGeneration — it's a read of what already exists."""
    generation_id = _seed_and_generate(client)

    client.get(f"/seating/generations/{generation_id}/reports/seating")
    client.get(f"/seating/generations/{generation_id}/reports/seating")
    client.get(f"/seating/generations/{generation_id}/reports/ranges")

    exam_id = client.get("/exams").json()["items"][0]["id"]
    generations = client.get(f"/exams/{exam_id}/seating/generations").json()
    assert generations["meta"]["total"] == 1  # still just the one generation


def test_generation_isolation_through_the_api(client: TestClient) -> None:
    """Regenerate after adding a new student, and confirm generation A's
    report still reflects only A's (smaller) assignment set — not B's."""
    generation_id_1 = _seed_and_generate(client)
    exam_id = client.get("/exams").json()["items"][0]["id"]

    # Widen the schedule and add a third student before regenerating, so
    # generation 2's assignment set is distinguishably different from 1's.
    _upload(client, "/rooms/import", b"index,room,capacity\n2,302,10\n")
    _upload(
        client,
        "/schedules/import",
        (
            "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
            "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,3,302,1\n"
        ).encode("utf-8"),
    )
    _upload(
        client,
        "/registrations/import",
        b"student_id,student_name,subject_code,subject_name\n8003,Taylor Nguyen,CS101,Intro to Computer Science\n",
    )
    generation_2 = client.post(f"/exams/{exam_id}/seating/generate").json()
    generation_id_2 = generation_2["id"]

    assert generation_id_1 != generation_id_2
    assert generation_2["total_registered"] == 3

    text_1 = _extract_text(client.get(f"/seating/generations/{generation_id_1}/reports/seating").content)
    text_2 = _extract_text(client.get(f"/seating/generations/{generation_id_2}/reports/seating").content)

    assert f"Seating Generation #{generation_id_1}" in text_1
    assert f"Seating Generation #{generation_id_2}" in text_2
    # The new student and new room must appear in generation 2's report
    # but never in generation 1's — that would mean generation 1 leaked
    # generation 2's data.
    assert "Taylor Nguyen" not in text_1
    assert "Taylor Nguyen" in text_2
    assert "302" not in text_1
    assert "302" in text_2
