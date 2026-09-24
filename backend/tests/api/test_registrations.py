"""API-level tests through TestClient. All CSV content here is synthetic."""

from fastapi.testclient import TestClient

VALID_CSV = (
    "student_id,student_name,subject_code,subject_name\n"
    "1001,Alice Example,CS101,Intro to Computer Science\n"
    "1002,Bob Sample,CS101,Intro to Computer Science\n"
).encode("utf-8")


def _upload(client: TestClient, content: bytes, filename: str = "registrations.csv"):
    return client.post(
        "/registrations/import",
        files={"file": (filename, content, "text/csv")},
    )


def test_import_endpoint_returns_structured_summary(client: TestClient) -> None:
    response = _upload(client, VALID_CSV)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["rows_read"] == 2
    assert body["students_created"] == 2
    assert body["courses_created"] == 1
    assert body["registrations_created"] == 2
    assert body["validation_errors"] == []
    assert body["conflicts"] == []


def test_reimporting_same_file_via_api_is_idempotent(client: TestClient) -> None:
    first = _upload(client, VALID_CSV)
    assert first.status_code == 200

    second = _upload(client, VALID_CSV)
    assert second.status_code == 200
    body = second.json()
    assert body["students_created"] == 0
    assert body["students_existing"] == 2
    assert body["registrations_created"] == 0
    assert body["registrations_existing"] == 2


def test_import_then_read_endpoints_reflect_the_data(client: TestClient) -> None:
    _upload(client, VALID_CSV)

    students = client.get("/students").json()
    courses = client.get("/courses").json()
    registrations = client.get("/registrations").json()

    assert students["meta"]["total"] == 2
    assert {s["student_number"] for s in students["items"]} == {"1001", "1002"}
    assert courses["meta"]["total"] == 1
    assert courses["items"][0]["code"] == "CS101"
    assert registrations["meta"]["total"] == 2


def test_non_utf8_upload_is_rejected_without_leaking_content(client: TestClient) -> None:
    response = _upload(client, b"\xff\xfe\x00\x01not valid utf-8")

    assert response.status_code == 400
    assert "utf-8" in response.json()["detail"].lower()


def test_conflicting_name_is_reported_via_api(client: TestClient) -> None:
    _upload(client, VALID_CSV)

    conflicting = (
        "student_id,student_name,subject_code,subject_name\n"
        "1001,Alicia Example,CS103,Algorithms\n"
    ).encode("utf-8")
    response = _upload(client, conflicting)

    body = response.json()
    assert body["status"] == "partial"
    assert len(body["conflicts"]) == 1
    assert body["conflicts"][0]["kind"] == "student_name"


def test_students_endpoint_supports_pagination(client: TestClient) -> None:
    _upload(client, VALID_CSV)

    page = client.get("/students", params={"limit": 1, "offset": 0}).json()

    assert len(page["items"]) == 1
    assert page["meta"] == {"total": 2, "limit": 1, "offset": 0}
