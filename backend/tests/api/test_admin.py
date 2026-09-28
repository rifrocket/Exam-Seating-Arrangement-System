"""API-level tests for the admin database-reset endpoint. All data
synthetic.

`APP_ADMIN_PASSWORD` is configured per-test via `monkeypatch.setenv` +
`get_settings.cache_clear()` (never relying on whatever the process's
real environment happens to have) — every test that cares about a
specific admin-password state establishes it explicitly at the start,
so test order never matters.
"""

from fastapi.testclient import TestClient

from app.config import get_settings

ADMIN_PASSWORD = "correct-horse-battery-staple"

REGISTRATIONS_CSV = (
    "student_id,student_name,subject_code,subject_name\n"
    "9001,Jordan Rivera,CS101,Intro to Computer Science\n"
    "9002,Sam Okafor,CS101,Intro to Computer Science\n"
).encode("utf-8")
ROOMS_CSV = b"room,capacity,rows,columns\n401,10,2,5\n"
SCHEDULE_CSV = (
    "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
    "Thursday,30-May-24,10:00-12:00,CS101,Intro to Computer Science,2,401,2\n"
).encode("utf-8")


def _upload(client: TestClient, path: str, content: bytes, filename: str = "file.csv"):
    return client.post(path, files={"file": (filename, content, "text/csv")})


def _set_admin_password(monkeypatch, password: str | None) -> None:
    if password is None:
        monkeypatch.delenv("APP_ADMIN_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("APP_ADMIN_PASSWORD", password)
    get_settings.cache_clear()


def _seed_full_application_state(client: TestClient) -> int:
    """Populates every table the reset must clear: students, courses,
    registrations (via the registrations import), rooms, exams,
    exam_rooms (via schedule import), and a seating generation +
    assignments (via seating generation) — everything except
    examination_sessions/session_exams, seeded separately where needed.
    Returns the generation id."""
    assert _upload(client, "/registrations/import", REGISTRATIONS_CSV).status_code == 200
    assert _upload(client, "/rooms/import", ROOMS_CSV).status_code == 200
    assert _upload(client, "/schedules/import", SCHEDULE_CSV).status_code == 200
    exam_id = client.get("/exams").json()["items"][0]["id"]
    generation = client.post(f"/exams/{exam_id}/seating/generate").json()
    assert generation["total_assigned"] == 2
    return generation["id"]


# --- 1/2/3: password verification -------------------------------------


def test_valid_admin_password_allows_reset(client: TestClient, monkeypatch) -> None:
    _set_admin_password(monkeypatch, ADMIN_PASSWORD)
    _seed_full_application_state(client)

    response = client.post("/admin/database/reset", json={"password": ADMIN_PASSWORD})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_invalid_password_returns_401(client: TestClient, monkeypatch) -> None:
    _set_admin_password(monkeypatch, ADMIN_PASSWORD)
    _seed_full_application_state(client)

    response = client.post("/admin/database/reset", json={"password": "wrong-password"})

    assert response.status_code == 401
    # Data must survive an unauthorized attempt.
    assert client.get("/students").json()["meta"]["total"] == 2


def test_missing_password_is_rejected(client: TestClient, monkeypatch) -> None:
    _set_admin_password(monkeypatch, ADMIN_PASSWORD)

    response = client.post("/admin/database/reset", json={})

    assert response.status_code == 401


def test_empty_password_is_rejected(client: TestClient, monkeypatch) -> None:
    _set_admin_password(monkeypatch, ADMIN_PASSWORD)

    response = client.post("/admin/database/reset", json={"password": ""})

    assert response.status_code == 401


def test_unconfigured_admin_password_rejects_every_attempt(client: TestClient, monkeypatch) -> None:
    """No APP_ADMIN_PASSWORD configured at all — the endpoint must not
    fall back to accepting anything; it fails safely closed."""
    _set_admin_password(monkeypatch, None)

    response = client.post("/admin/database/reset", json={"password": "anything"})

    assert response.status_code == 500
    assert "anything" not in response.text


# --- 9: POST only -------------------------------------------------------


def test_reset_endpoint_does_not_accept_get(client: TestClient, monkeypatch) -> None:
    _set_admin_password(monkeypatch, ADMIN_PASSWORD)

    response = client.get("/admin/database/reset")

    assert response.status_code == 405


# --- 4/5/6: reset actually clears data, schema stays usable -------------


def test_reset_removes_all_application_data_and_schema_stays_usable(client: TestClient, monkeypatch) -> None:
    _set_admin_password(monkeypatch, ADMIN_PASSWORD)
    generation_id = _seed_full_application_state(client)

    response = client.post("/admin/database/reset", json={"password": ADMIN_PASSWORD})
    assert response.status_code == 200

    assert client.get("/students").json()["meta"]["total"] == 0
    assert client.get("/courses").json()["meta"]["total"] == 0
    assert client.get("/registrations").json()["meta"]["total"] == 0
    assert client.get("/exams").json()["meta"]["total"] == 0
    assert client.get("/rooms").json()["meta"]["total"] == 0
    assert client.get("/examination-sessions").json()["meta"]["total"] == 0
    # The generation and its assignments are gone too — the report for it
    # now 404s exactly as it would for any generation that never existed.
    assert client.get(f"/seating/generations/{generation_id}/reports/seating").status_code == 404

    # Schema remains intact and immediately usable: a brand new import
    # right after reset must work exactly as it would on a fresh database.
    reimport = _upload(client, "/registrations/import", REGISTRATIONS_CSV)
    assert reimport.status_code == 200
    assert reimport.json()["status"] == "success"
    assert client.get("/students").json()["meta"]["total"] == 2


def test_reset_removes_examination_sessions_and_related_records(client: TestClient, monkeypatch) -> None:
    """A multi-course session (examination_sessions + session_exams +
    a session-scoped seating generation) must also be fully cleared."""
    _set_admin_password(monkeypatch, ADMIN_PASSWORD)
    registrations_csv = (
        "student_id,student_name,subject_code,subject_name\n"
        "9101,Alice,PHY101,Physics I\n"
        "9102,Bob,MATH101,Calculus I\n"
    ).encode("utf-8")
    rooms_csv = b"room,capacity,rows,columns\n501,10,2,5\n"
    schedule_csv = (
        "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room\n"
        "Friday,2-Oct-26,09:00-11:00,PHY101,Physics I,1,501,1\n"
        "Friday,2-Oct-26,09:00-11:00,MATH101,Calculus I,1,501,1\n"
    ).encode("utf-8")
    assert _upload(client, "/registrations/import", registrations_csv).status_code == 200
    assert _upload(client, "/rooms/import", rooms_csv).status_code == 200
    assert _upload(client, "/schedules/import", schedule_csv).status_code == 200
    exam_ids = [e["id"] for e in client.get("/exams").json()["items"]]
    session_response = client.post("/examination-sessions", json={"exam_ids": exam_ids})
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]
    generate_response = client.post(
        f"/examination-sessions/{session_id}/seating/generate", json={"strategy": "constraint"}
    )
    assert generate_response.status_code == 200
    assert client.get("/examination-sessions").json()["meta"]["total"] == 1

    response = client.post("/admin/database/reset", json={"password": ADMIN_PASSWORD})
    assert response.status_code == 200

    assert client.get("/examination-sessions").json()["meta"]["total"] == 0
    assert client.get(f"/examination-sessions/{session_id}").status_code == 404


# --- 7/8: transactional, no partial deletion on failure -----------------


def test_failed_reset_leaves_no_partial_deletion(client: TestClient, monkeypatch) -> None:
    """Simulates a failure partway through the reset (after some rows are
    deleted, before the transaction commits) and verifies every row —
    including the ones that were already deleted in the failed attempt —
    is still present afterward, proving the whole operation rolled back
    rather than leaving a half-reset database."""
    _set_admin_password(monkeypatch, ADMIN_PASSWORD)
    _seed_full_application_state(client)

    def _delete_students_then_explode(session):
        from app.db.models import StudentModel

        session.execute(StudentModel.__table__.delete())  # a real, partial delete
        raise RuntimeError("simulated mid-reset failure")

    monkeypatch.setattr("app.api.admin.reset_database", _delete_students_then_explode)

    response = client.post("/admin/database/reset", json={"password": ADMIN_PASSWORD})

    assert response.status_code == 500
    assert ADMIN_PASSWORD not in response.text
    # The partial delete must have been rolled back along with everything
    # else — students must still be present, not just "everything but
    # students."
    assert client.get("/students").json()["meta"]["total"] == 2
    assert client.get("/exams").json()["meta"]["total"] == 1


# --- 10: password never leaks into any response --------------------------


def test_password_never_appears_in_any_response(client: TestClient, monkeypatch) -> None:
    _set_admin_password(monkeypatch, ADMIN_PASSWORD)
    _seed_full_application_state(client)

    wrong_response = client.post("/admin/database/reset", json={"password": "not-the-real-password"})
    assert ADMIN_PASSWORD not in wrong_response.text
    assert "not-the-real-password" not in wrong_response.text

    ok_response = client.post("/admin/database/reset", json={"password": ADMIN_PASSWORD})
    assert ADMIN_PASSWORD not in ok_response.text
