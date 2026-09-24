"""API-level tests through TestClient for schedule/exam/room endpoints.
All data here is synthetic.
"""

from fastapi.testclient import TestClient

REGISTRATIONS_CSV = (
    "student_id,student_name,subject_code,subject_name\n"
    "1001,Alice Example,CS101,Intro to Computer Science\n"
    "1002,Bob Sample,CS101,Intro to Computer Science\n"
).encode("utf-8")

ROOMS_CSV = ("index,room,capacity\n1,101,50\n2,102,50\n").encode("utf-8")

SCHEDULE_HEADER = "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
SCHEDULE_CSV = (
    SCHEDULE_HEADER
    + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,101,40\n"
    + "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,80,102,40\n"
).encode("utf-8")


def _upload(client: TestClient, path: str, content: bytes, filename: str = "file.csv"):
    return client.post(path, files={"file": (filename, content, "text/csv")})


def _seed_prerequisites(client: TestClient) -> None:
    assert _upload(client, "/registrations/import", REGISTRATIONS_CSV).status_code == 200
    assert _upload(client, "/rooms/import", ROOMS_CSV).status_code == 200


def test_full_workflow_registrations_rooms_schedule_exams(client: TestClient) -> None:
    _seed_prerequisites(client)

    import_response = _upload(client, "/schedules/import", SCHEDULE_CSV)
    assert import_response.status_code == 200
    body = import_response.json()
    assert body["status"] == "success"
    assert body["exams_created"] == 1
    assert body["exam_rooms_created"] == 2
    assert body["validation_errors"] == []
    assert body["conflicts"] == []

    exams = client.get("/exams").json()
    assert exams["meta"]["total"] == 1
    exam_summary = exams["items"][0]
    assert exam_summary["course_code"] == "CS101"
    assert exam_summary["expected_student_count"] == 80
    assert exam_summary["room_count"] == 2

    detail = client.get(f"/exams/{exam_summary['id']}").json()
    assert len(detail["exam_rooms"]) == 2
    room_codes = {er["room_code"] for er in detail["exam_rooms"]}
    assert room_codes == {"101", "102"}
    allocations = {er["room_code"]: er["allocated_students"] for er in detail["exam_rooms"]}
    assert allocations == {"101": 40, "102": 40}

    rooms = client.get("/rooms").json()
    assert rooms["meta"]["total"] == 2


def test_reimporting_same_schedule_via_api_is_idempotent(client: TestClient) -> None:
    _seed_prerequisites(client)

    first = _upload(client, "/schedules/import", SCHEDULE_CSV).json()
    second = _upload(client, "/schedules/import", SCHEDULE_CSV).json()

    assert first["exams_created"] == 1
    assert second["exams_created"] == 0
    assert second["exams_existing"] == 1
    assert second["exam_rooms_created"] == 0
    assert second["exam_rooms_existing"] == 2

    exams = client.get("/exams").json()
    assert exams["meta"]["total"] == 1


def test_schedule_import_rejects_unknown_course(client: TestClient) -> None:
    _upload(client, "/rooms/import", ROOMS_CSV)  # rooms seeded, but no registrations/courses

    response = _upload(client, "/schedules/import", SCHEDULE_CSV)
    body = response.json()

    assert body["status"] == "partial"
    assert body["exams_created"] == 0
    assert any("Unknown course code" in e["message"] for e in body["validation_errors"])


def test_exam_detail_404_for_missing_exam(client: TestClient) -> None:
    response = client.get("/exams/999")

    assert response.status_code == 404


def test_rooms_import_endpoint(client: TestClient) -> None:
    response = _upload(client, "/rooms/import", ROOMS_CSV)

    assert response.status_code == 200
    body = response.json()
    assert body["rooms_created"] == 2

    rooms = client.get("/rooms").json()
    assert {r["code"] for r in rooms["items"]} == {"101", "102"}
