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


# --- Phase 14: physical seat-map PDF report --------------------------------


def _extract_pages(pdf_bytes: bytes) -> list:
    return PdfReader(BytesIO(pdf_bytes)).pages


def test_seat_map_report_single_course_exam(client: TestClient) -> None:
    """Room has a real topology (4x5=20) but only 2 of its 20 seats are
    occupied — the PDF must show both occupied seats with course/student,
    and EMPTY for the remaining 18, with no course legend clutter needed
    (single course)."""
    csv_registrations = (
        "student_id,student_name,subject_code,subject_name\n"
        "8001,Jordan Rivera,CS101,Intro to Computer Science\n"
        "8002,Sam Okafor,CS101,Intro to Computer Science\n"
    ).encode("utf-8")
    csv_rooms = b"room,capacity,rows,columns\n401,20,4,5\n"
    csv_schedule = (
        "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,2,401,2\n"
    ).encode("utf-8")
    assert _upload(client, "/registrations/import", csv_registrations).status_code == 200
    assert _upload(client, "/rooms/import", csv_rooms).status_code == 200
    assert _upload(client, "/schedules/import", csv_schedule).status_code == 200
    exam_id = client.get("/exams").json()["items"][0]["id"]
    generation_id = client.post(f"/exams/{exam_id}/seating/generate").json()["id"]

    response = client.get(f"/seating/generations/{generation_id}/reports/seat-map")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")

    text = "".join(page.extract_text() for page in _extract_pages(response.content))
    assert "CS101" in text
    assert "8001" in text
    assert "8002" in text
    assert "Room: 401" in text
    assert "EMPTY" in text  # 18 of 20 seats unassigned
    assert "BLOCKED" not in text  # nothing blocked in this room


def test_seat_map_report_multi_course_session(client: TestClient) -> None:
    """PHY101=8, CHEM101=7, MATH101=5 sharing one 4x5=20-seat room, exactly
    filled — every course must be visible in the PDF text, and since every
    seat is occupied there should be no EMPTY or BLOCKED cells."""
    csv_registrations = (
        "student_id,student_name,subject_code,subject_name\n"
        + "".join(f"{3000 + i},Student P{i},PHY101,Physics I\n" for i in range(1, 9))
        + "".join(f"{4000 + i},Student C{i},CHEM101,Chemistry I\n" for i in range(1, 8))
        + "".join(f"{5000 + i},Student M{i},MATH101,Calculus I\n" for i in range(1, 6))
    ).encode("utf-8")
    csv_rooms = b"room,capacity,rows,columns\n401,20,4,5\n"
    csv_schedule = (
        "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
        "Friday,2-Oct-26,09:00-11:00,PHY101,Physics I,8,401,8\n"
        "Friday,2-Oct-26,09:00-11:00,CHEM101,Chemistry I,7,401,7\n"
        "Friday,2-Oct-26,09:00-11:00,MATH101,Calculus I,5,401,5\n"
    ).encode("utf-8")
    assert _upload(client, "/registrations/import", csv_registrations).status_code == 200
    assert _upload(client, "/rooms/import", csv_rooms).status_code == 200
    assert _upload(client, "/schedules/import", csv_schedule).status_code == 200
    exam_ids = [e["id"] for e in client.get("/exams").json()["items"]]
    session_id = client.post("/examination-sessions", json={"exam_ids": exam_ids}).json()["id"]
    generation_id = client.post(
        f"/examination-sessions/{session_id}/seating/generate", json={"strategy": "constraint"}
    ).json()["id"]

    response = client.get(f"/seating/generations/{generation_id}/reports/seat-map")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    text = "".join(page.extract_text() for page in _extract_pages(response.content))
    assert "PHY101" in text
    assert "CHEM101" in text
    assert "MATH101" in text
    assert "Room: 401" in text
    assert "EMPTY" not in text  # exactly 20/20 filled
    assert "BLOCKED" not in text


def test_seat_map_report_blocked_seats(client: TestClient) -> None:
    """Room 401 (4x5=20) with seats 3 and 12 blocked. Blocked seats must
    be labeled BLOCKED, never shown as if they held a student."""
    csv_registrations = (
        "student_id,student_name,subject_code,subject_name\n"
        + "".join(f"{6000 + i},Student {i},CS101,Intro to CS\n" for i in range(1, 7))
    ).encode("utf-8")
    csv_rooms = b"room,capacity,rows,columns,blockedseats\n401,20,4,5,3;12\n"
    csv_schedule = (
        "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to CS,6,401,6\n"
    ).encode("utf-8")
    assert _upload(client, "/registrations/import", csv_registrations).status_code == 200
    assert _upload(client, "/rooms/import", csv_rooms).status_code == 200
    assert _upload(client, "/schedules/import", csv_schedule).status_code == 200
    exam_id = client.get("/exams").json()["items"][0]["id"]
    generation_id = client.post(f"/exams/{exam_id}/seating/generate").json()["id"]

    response = client.get(f"/seating/generations/{generation_id}/reports/seat-map")

    assert response.status_code == 200
    text = "".join(page.extract_text() for page in _extract_pages(response.content))
    assert text.count("BLOCKED") == 2  # exactly seats 3 and 12
    assert "EMPTY" in text  # 20 physical - 2 blocked - 6 occupied = 12 empty


def test_seat_map_report_multiple_rooms(client: TestClient) -> None:
    """One exam scheduled across two separate rooms — both must appear as
    their own, clearly-labeled room sections in the PDF."""
    csv_registrations = (
        "student_id,student_name,subject_code,subject_name\n"
        + "".join(f"{7000 + i},Student {i},CS101,Intro to CS\n" for i in range(1, 21))
    ).encode("utf-8")
    csv_rooms = b"room,capacity,rows,columns\n401,10,2,5\n402,10,2,5\n"
    csv_schedule = (
        "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to CS,20,401,10\n"
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to CS,20,402,10\n"
    ).encode("utf-8")
    assert _upload(client, "/registrations/import", csv_registrations).status_code == 200
    assert _upload(client, "/rooms/import", csv_rooms).status_code == 200
    assert _upload(client, "/schedules/import", csv_schedule).status_code == 200
    exam_id = client.get("/exams").json()["items"][0]["id"]
    generation_id = client.post(f"/exams/{exam_id}/seating/generate").json()["id"]

    response = client.get(f"/seating/generations/{generation_id}/reports/seat-map")

    assert response.status_code == 200
    text = "".join(page.extract_text() for page in _extract_pages(response.content))
    assert "Room: 401" in text
    assert "Room: 402" in text


def test_seat_map_report_non_square_room(client: TestClient) -> None:
    """A deliberately non-square 3x7=21 room."""
    csv_registrations = (
        "student_id,student_name,subject_code,subject_name\n"
        + "".join(f"{8100 + i},Student {i},CS101,Intro to CS\n" for i in range(1, 11))
    ).encode("utf-8")
    csv_rooms = b"room,capacity,rows,columns\n701,21,3,7\n"
    csv_schedule = (
        "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to CS,10,701,10\n"
    ).encode("utf-8")
    assert _upload(client, "/registrations/import", csv_registrations).status_code == 200
    assert _upload(client, "/rooms/import", csv_rooms).status_code == 200
    assert _upload(client, "/schedules/import", csv_schedule).status_code == 200
    exam_id = client.get("/exams").json()["items"][0]["id"]
    generation_id = client.post(f"/exams/{exam_id}/seating/generate").json()["id"]

    response = client.get(f"/seating/generations/{generation_id}/reports/seat-map")

    assert response.status_code == 200
    text = "".join(page.extract_text() for page in _extract_pages(response.content))
    assert "Room: 701" in text
    assert "8101" in text


def test_seat_map_report_wide_room_uses_landscape_page(client: TestClient) -> None:
    """A 2x10=20 wide room — the whole PDF document must switch to a
    landscape page (wider than tall) so the grid doesn't overflow, rather
    than shrinking seats to the point of being unreadable."""
    csv_registrations = (
        "student_id,student_name,subject_code,subject_name\n"
        + "".join(f"{8200 + i},Student {i},CS101,Intro to CS\n" for i in range(1, 13))
    ).encode("utf-8")
    csv_rooms = b"room,capacity,rows,columns\n501,20,2,10\n"
    csv_schedule = (
        "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
        "Thursday,30-May-24,10:00-12:00,CS101,Intro to CS,12,501,12\n"
    ).encode("utf-8")
    assert _upload(client, "/registrations/import", csv_registrations).status_code == 200
    assert _upload(client, "/rooms/import", csv_rooms).status_code == 200
    assert _upload(client, "/schedules/import", csv_schedule).status_code == 200
    exam_id = client.get("/exams").json()["items"][0]["id"]
    generation_id = client.post(f"/exams/{exam_id}/seating/generate").json()["id"]

    response = client.get(f"/seating/generations/{generation_id}/reports/seat-map")

    assert response.status_code == 200
    pages = _extract_pages(response.content)
    page_box = pages[0].mediabox
    assert float(page_box.width) > float(page_box.height)  # landscape
    text = "".join(page.extract_text() for page in pages)
    assert "Room: 501" in text
    assert "8201" in text


def test_seat_map_report_for_missing_generation_returns_404(client: TestClient) -> None:
    response = client.get("/seating/generations/999/reports/seat-map")

    assert response.status_code == 404


def test_seat_map_report_room_without_topology_falls_back_gracefully(client: TestClient) -> None:
    """A room with capacity only (no rows/columns) is normal, valid state
    for a sequential-only exam — the seat-map report must not crash for
    it, just show a short note instead of a grid for that room."""
    generation_id = _seed_and_generate(client)  # ROOMS_CSV above has no rows/columns

    response = client.get(f"/seating/generations/{generation_id}/reports/seat-map")

    assert response.status_code == 200
    text = "".join(page.extract_text() for page in _extract_pages(response.content))
    assert "301" in text
    assert "no configured physical layout" in text


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
