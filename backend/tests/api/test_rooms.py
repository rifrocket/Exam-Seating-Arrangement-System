"""API-level tests through TestClient for the rooms endpoints. All data
here is synthetic.
"""

from fastapi.testclient import TestClient


def _upload(client: TestClient, path: str, content: bytes, filename: str = "file.csv"):
    return client.post(path, files={"file": (filename, content, "text/csv")})


def test_room_list_exposes_topology_fields(client: TestClient) -> None:
    csv_text = "room,capacity,rows,columns\n401,10,2,5\n402,10,2,5\n".encode()
    assert _upload(client, "/rooms/import", csv_text).status_code == 200

    response = client.get("/rooms")

    assert response.status_code == 200
    items = {r["code"]: r for r in response.json()["items"]}
    assert items["401"]["rows"] == 2
    assert items["401"]["columns"] == 5
    assert items["402"]["rows"] == 2
    assert items["402"]["columns"] == 5


def test_room_without_topology_reports_null_rows_and_columns(client: TestClient) -> None:
    csv_text = "index,room,capacity\n1,101,40\n".encode()
    assert _upload(client, "/rooms/import", csv_text).status_code == 200

    response = client.get("/rooms")

    items = {r["code"]: r for r in response.json()["items"]}
    assert items["101"]["rows"] is None
    assert items["101"]["columns"] is None


def test_topology_conflict_reports_room_topology_kind(client: TestClient) -> None:
    assert _upload(client, "/rooms/import", "room,capacity,rows,columns\n401,10,2,5\n".encode()).status_code == 200

    response = _upload(client, "/rooms/import", "room,capacity,rows,columns\n401,10,1,10\n".encode())

    assert response.status_code == 200
    body = response.json()
    assert body["conflicts"][0]["kind"] == "room_topology"
