"""API-level tests for seating generation. All data synthetic."""

from fastapi.testclient import TestClient

REGISTRATIONS_CSV = (
    "student_id,student_name,subject_code,subject_name\n"
    + "".join(f"{6000 + i},Student {i},CS101,Intro to Computer Science\n" for i in range(1, 81))
).encode("utf-8")

ROOMS_CSV = ("index,room,capacity\n1,101,50\n2,102,50\n").encode("utf-8")

SCHEDULE_CSV = (
    "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
    "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
    "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,102,40\n"
).encode("utf-8")


def _upload(client: TestClient, path: str, content: bytes, filename: str = "file.csv"):
    return client.post(path, files={"file": (filename, content, "text/csv")})


def _seed_full_exam(client: TestClient) -> int:
    assert _upload(client, "/registrations/import", REGISTRATIONS_CSV).status_code == 200
    assert _upload(client, "/rooms/import", ROOMS_CSV).status_code == 200
    schedule_response = _upload(client, "/schedules/import", SCHEDULE_CSV)
    assert schedule_response.status_code == 200
    exam_id = client.get("/exams").json()["items"][0]["id"]
    return exam_id


def test_generate_seating_end_to_end(client: TestClient) -> None:
    exam_id = _seed_full_exam(client)

    response = client.post(f"/exams/{exam_id}/seating/generate")
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "success"
    assert body["strategy_name"] == "sequential"
    assert body["total_registered"] == 80
    assert body["total_assigned"] == 80
    assert body["total_unassigned"] == 0
    assert body["capacity_shortage"] is False
    assert body["scheduled_student_count"] == 80
    assert body["available_capacity"] == 80
    assert body["unassigned_student_ids"] == []
    assert body["created_at"] is not None

    assignments = client.get(f"/seating/generations/{body['id']}/assignments").json()
    assert len(assignments["items"]) == 80
    room_codes = {item["room_code"] for item in assignments["items"]}
    assert room_codes == {"101", "102"}
    # Seat numbers per room are a contiguous 1..40 ordinal.
    for room_code in ("101", "102"):
        seats = sorted(a["seat_number"] for a in assignments["items"] if a["room_code"] == room_code)
        assert seats == list(range(1, 41))


def test_regenerating_creates_a_second_generation(client: TestClient) -> None:
    exam_id = _seed_full_exam(client)

    first = client.post(f"/exams/{exam_id}/seating/generate").json()
    second = client.post(f"/exams/{exam_id}/seating/generate").json()

    assert first["id"] != second["id"]

    generations = client.get(f"/exams/{exam_id}/seating/generations").json()
    assert generations["meta"]["total"] == 2
    assert {g["id"] for g in generations["items"]} == {first["id"], second["id"]}


def test_generate_seating_for_unknown_exam_returns_404(client: TestClient) -> None:
    response = client.post("/exams/999/seating/generate")

    assert response.status_code == 404


def test_generate_seating_with_unknown_strategy_returns_400(client: TestClient) -> None:
    exam_id = _seed_full_exam(client)

    response = client.post(f"/exams/{exam_id}/seating/generate", json={"strategy": "does-not-exist"})

    assert response.status_code == 400


def test_assignments_for_unknown_generation_returns_404(client: TestClient) -> None:
    response = client.get("/seating/generations/999/assignments")

    assert response.status_code == 404


def test_capacity_shortage_surfaces_through_the_api(client: TestClient) -> None:
    # 80 registered students but only one room with capacity 30 scheduled.
    _upload(client, "/registrations/import", REGISTRATIONS_CSV)
    _upload(
        client,
        "/rooms/import",
        b"index,room,capacity\n1,201,30\n",
    )
    _upload(
        client,
        "/schedules/import",
        (
            "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
            "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,201,30\n"
        ).encode("utf-8"),
    )
    exam_id = client.get("/exams").json()["items"][0]["id"]

    response = client.post(f"/exams/{exam_id}/seating/generate")
    body = response.json()

    assert body["status"] == "partial"
    assert body["capacity_shortage"] is True
    assert body["total_assigned"] == 30
    assert body["total_unassigned"] == 50
    assert len(body["unassigned_student_ids"]) == 50
