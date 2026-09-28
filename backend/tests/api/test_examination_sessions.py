"""API-level tests through TestClient for the examination-sessions
endpoints — the full multi-course session workflow. All data synthetic.
"""

from fastapi.testclient import TestClient

REGISTRATIONS_CSV = (
    "student_id,student_name,subject_code,subject_name\n"
    + "".join(f"{1000 + i},Student A{i},CS101,Intro to Computer Science\n" for i in range(1, 11))
    + "".join(f"{2000 + i},Student B{i},MATH101,Calculus I\n" for i in range(1, 11))
).encode("utf-8")

ROOMS_CSV = "room,capacity,rows,columns\n401,20,4,5\n".encode("utf-8")

# Both exams share room 401 (10 + 10 = 20, exactly its capacity) — the
# manual acceptance scenario.
SCHEDULE_CSV = (
    "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
    "Friday,2-Oct-26,09:00-11:00,CS101,Intro to Computer Science,10,401,10\n"
    "Friday,2-Oct-26,09:00-11:00,MATH101,Calculus I,10,401,10\n"
).encode("utf-8")


def _upload(client: TestClient, path: str, content: bytes, filename: str = "file.csv"):
    return client.post(path, files={"file": (filename, content, "text/csv")})


def _seed_two_exams_sharing_one_room(client: TestClient) -> list[int]:
    assert _upload(client, "/registrations/import", REGISTRATIONS_CSV).status_code == 200
    assert _upload(client, "/rooms/import", ROOMS_CSV).status_code == 200
    assert _upload(client, "/schedules/import", SCHEDULE_CSV).status_code == 200
    exams = client.get("/exams").json()["items"]
    assert len(exams) == 2
    return [exam["id"] for exam in exams]


def test_create_session_from_two_compatible_exams(client: TestClient) -> None:
    exam_ids = _seed_two_exams_sharing_one_room(client)

    response = client.post("/examination-sessions", json={"exam_ids": exam_ids})

    assert response.status_code == 200
    body = response.json()
    assert body["exam_date"] == "2026-10-02"
    assert body["time_slot"] == "09:00-11:00"
    assert {e["course_code"] for e in body["exams"]} == {"CS101", "MATH101"}
    assert body["participant_count"] == 20
    assert body["room_codes"] == ["401"]


def test_create_session_with_unknown_exam_returns_404(client: TestClient) -> None:
    exam_ids = _seed_two_exams_sharing_one_room(client)

    response = client.post("/examination-sessions", json={"exam_ids": [*exam_ids, 999]})

    assert response.status_code == 404


def test_create_session_with_incompatible_schedule_returns_400(client: TestClient) -> None:
    assert _upload(client, "/registrations/import", REGISTRATIONS_CSV).status_code == 200
    assert _upload(client, "/rooms/import", ROOMS_CSV).status_code == 200
    mismatched_schedule = (
        "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
        "Friday,2-Oct-26,09:00-11:00,CS101,Intro to Computer Science,10,401,10\n"
        "Saturday,3-Oct-26,13:00-15:00,MATH101,Calculus I,10,401,10\n"
    ).encode("utf-8")
    assert _upload(client, "/schedules/import", mismatched_schedule).status_code == 200
    exam_ids = [exam["id"] for exam in client.get("/exams").json()["items"]]

    response = client.post("/examination-sessions", json={"exam_ids": exam_ids})

    assert response.status_code == 400


def test_get_and_list_session(client: TestClient) -> None:
    exam_ids = _seed_two_exams_sharing_one_room(client)
    create_response = client.post("/examination-sessions", json={"exam_ids": exam_ids})
    session_id = create_response.json()["id"]

    get_response = client.get(f"/examination-sessions/{session_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == session_id

    list_response = client.get("/examination-sessions")
    assert list_response.status_code == 200
    assert list_response.json()["meta"]["total"] == 1


def test_get_unknown_session_returns_404(client: TestClient) -> None:
    response = client.get("/examination-sessions/999")

    assert response.status_code == 404


def test_full_session_seating_workflow(client: TestClient) -> None:
    exam_ids = _seed_two_exams_sharing_one_room(client)
    session_id = client.post("/examination-sessions", json={"exam_ids": exam_ids}).json()["id"]

    generate_response = client.post(
        f"/examination-sessions/{session_id}/seating/generate", json={"strategy": "constraint"}
    )
    assert generate_response.status_code == 200
    body = generate_response.json()
    assert body["session_id"] == session_id
    assert body["exam_id"] is None
    assert body["strategy_name"] == "constraint"
    assert body["status"] == "success"
    assert body["total_assigned"] == 20
    assert body["scheduled_student_count"] == 20
    assert body["total_physical_capacity"] == 20
    generation_id = body["id"]

    generations_response = client.get(f"/examination-sessions/{session_id}/seating/generations")
    assert generations_response.status_code == 200
    assert len(generations_response.json()["items"]) == 1

    assignments_response = client.get(f"/seating/generations/{generation_id}/assignments")
    assert assignments_response.status_code == 200
    items = assignments_response.json()["items"]
    assert len(items) == 20
    course_codes = {item["course_code"] for item in items}
    assert course_codes == {"CS101", "MATH101"}
    student_ids = [item["student_id"] for item in items]
    assert len(student_ids) == len(set(student_ids))

    pdf_response = client.get(f"/seating/generations/{generation_id}/reports/seating")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"

    ranges_response = client.get(f"/seating/generations/{generation_id}/reports/ranges")
    assert ranges_response.status_code == 200
    assert ranges_response.headers["content-type"] == "application/pdf"


def test_generate_session_seating_with_unknown_session_returns_404(client: TestClient) -> None:
    response = client.post("/examination-sessions/999/seating/generate")

    assert response.status_code == 404


def test_existing_single_exam_generation_endpoint_is_unaffected(client: TestClient) -> None:
    """Regression: the session workflow must not change
    POST /exams/{exam_id}/seating/generate's own behavior."""
    exam_ids = _seed_two_exams_sharing_one_room(client)

    response = client.post(f"/exams/{exam_ids[0]}/seating/generate", json={"strategy": "sequential"})

    assert response.status_code == 200
    body = response.json()
    assert body["exam_id"] == exam_ids[0]
    assert body["session_id"] is None
    assert body["strategy_name"] == "sequential"


# --- three-course session, full workflow through the real HTTP API --------

THREE_COURSE_REGISTRATIONS_CSV = (
    "student_id,student_name,subject_code,subject_name\n"
    + "".join(f"{3000 + i},Student P{i},PHY101,Physics I\n" for i in range(1, 9))
    + "".join(f"{4000 + i},Student C{i},CHEM101,Chemistry I\n" for i in range(1, 8))
    + "".join(f"{5000 + i},Student M{i},MATH101,Calculus I\n" for i in range(1, 6))
).encode("utf-8")

THREE_COURSE_SCHEDULE_CSV = (
    "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
    "Friday,2-Oct-26,09:00-11:00,PHY101,Physics I,8,401,8\n"
    "Friday,2-Oct-26,09:00-11:00,CHEM101,Chemistry I,7,401,7\n"
    "Friday,2-Oct-26,09:00-11:00,MATH101,Calculus I,5,401,5\n"
).encode("utf-8")


def _seed_three_exams_sharing_one_room(client: TestClient) -> list[int]:
    assert _upload(client, "/registrations/import", THREE_COURSE_REGISTRATIONS_CSV).status_code == 200
    assert _upload(client, "/rooms/import", ROOMS_CSV).status_code == 200
    assert _upload(client, "/schedules/import", THREE_COURSE_SCHEDULE_CSV).status_code == 200
    exams = client.get("/exams").json()["items"]
    assert len(exams) == 3
    return [exam["id"] for exam in exams]


def test_three_course_session_full_workflow(client: TestClient) -> None:
    """Section 14's exact shape: PHY101=8, CHEM101=7, MATH101=5 sharing one
    4x5=20-seat room. Verifies the full real-HTTP path (registrations ->
    rooms/topology -> schedule -> session -> constraint generation ->
    assignments -> PDF reports) still works with three courses and the
    new anti-cheating default, not just two."""
    exam_ids = _seed_three_exams_sharing_one_room(client)
    session_id = client.post("/examination-sessions", json={"exam_ids": exam_ids}).json()["id"]

    generate_response = client.post(
        f"/examination-sessions/{session_id}/seating/generate", json={"strategy": "constraint"}
    )
    assert generate_response.status_code == 200
    body = generate_response.json()
    assert body["status"] == "success"
    assert body["total_assigned"] == 20
    assert body["total_unassigned"] == 0
    generation_id = body["id"]

    assignments_response = client.get(f"/seating/generations/{generation_id}/assignments")
    assert assignments_response.status_code == 200
    items = assignments_response.json()["items"]
    assert len(items) == 20
    course_codes = {item["course_code"] for item in items}
    assert course_codes == {"PHY101", "CHEM101", "MATH101"}
    student_ids = [item["student_id"] for item in items]
    assert len(student_ids) == len(set(student_ids))
    seat_numbers = [item["seat_number"] for item in items]
    assert len(seat_numbers) == len(set(seat_numbers))

    course_by_seat = {item["seat_number"]: item["course_code"] for item in items}
    seat_number_order = sorted(course_by_seat)
    # No single course occupies every seat in a contiguous run across the
    # whole room — a coarse but real check that the arrangement isn't one
    # naive block per course (seat numbers here wrap across rows, so this
    # is a weaker property than the 1-row adjacency check in
    # tests/services/test_session_seating_generation.py, but still rules
    # out "PHY101 gets seats 1-8, CHEM101 gets 9-15, MATH101 gets 16-20").
    longest_same_course_run = 1
    current_run = 1
    for previous, current in zip(seat_number_order, seat_number_order[1:], strict=False):
        if course_by_seat[current] == course_by_seat[previous]:
            current_run += 1
            longest_same_course_run = max(longest_same_course_run, current_run)
        else:
            current_run = 1
    assert longest_same_course_run < 8  # strictly less than PHY101's own full size

    pdf_response = client.get(f"/seating/generations/{generation_id}/reports/seating")
    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"

    ranges_response = client.get(f"/seating/generations/{generation_id}/reports/ranges")
    assert ranges_response.status_code == 200
    assert ranges_response.headers["content-type"] == "application/pdf"
