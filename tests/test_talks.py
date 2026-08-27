from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app import models
from app.auth import get_client
from app.db import get_db
from app.main import app
from app.storage import get_storage
from tests.conftest import FakeStorageBackend

client = TestClient(app)


def test_talks_unauthorized():
    response = client.post("/talks", json={})
    assert response.status_code == 401

    response = client.get("/talks/1")
    assert response.status_code == 401


def test_create_talk_authorized():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    # Simulate talk does not exist yet
    mock_db.query.return_value.filter.return_value.first.return_value = None

    def fake_add(talk):
        talk.id = 42

    mock_db.add.side_effect = fake_add

    payload = {
        "event_id": 1,
        "title": "Intro to VEditor",
        "room": "Stage A",
        "start": datetime(2026, 8, 27, 10, 0, tzinfo=UTC).isoformat(),
        "end": datetime(2026, 8, 27, 11, 0, tzinfo=UTC).isoformat(),
    }

    response = client.post("/talks", json=payload, headers={"X-API-Key": "valid"})
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 42
    assert data["event_id"] == 1
    assert data["title"] == "Intro to VEditor"
    assert data["room"] == "Stage A"
    assert data["status"] == "waiting_for_files"
    assert mock_db.commit.called

    app.dependency_overrides.clear()


def test_create_talk_unauthorized_event():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[2])  # Access to event 2 only

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    payload = {
        "event_id": 1,  # Unauthorized event
        "title": "Intro to VEditor",
        "room": "Stage A",
        "start": datetime(2026, 8, 27, 10, 0, tzinfo=UTC).isoformat(),
        "end": datetime(2026, 8, 27, 11, 0, tzinfo=UTC).isoformat(),
    }

    response = client.post("/talks", json=payload, headers={"X-API-Key": "valid"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Client is not authorized to access this event"

    app.dependency_overrides.clear()


def test_upsert_talk_existing():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    start_dt = datetime(2026, 8, 27, 10, 0, tzinfo=UTC)
    old_end_dt = datetime(2026, 8, 27, 10, 45, tzinfo=UTC)
    new_end_dt = datetime(2026, 8, 27, 11, 0, tzinfo=UTC)

    existing_talk = models.Talk(
        id=10,
        event_id=1,
        title="Intro to VEditor",
        room="Stage A",
        start=start_dt,
        end=old_end_dt,
        status="waiting_for_files",
    )

    mock_db.query.return_value.filter.return_value.first.return_value = existing_talk

    payload = {
        "event_id": 1,
        "title": "Intro to VEditor",
        "room": "Stage B",  # Updated room
        "start": start_dt.isoformat(),
        "end": new_end_dt.isoformat(),  # Updated end
    }

    response = client.post("/talks", json=payload, headers={"X-API-Key": "valid"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 10
    assert data["room"] == "Stage B"
    assert existing_talk.room == "Stage B"
    assert existing_talk.end == new_end_dt
    assert mock_db.commit.called

    app.dependency_overrides.clear()


def test_get_talk_authorized_without_preview():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])
    fake_storage = FakeStorageBackend()

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_storage] = lambda: fake_storage

    mock_talk = models.Talk(
        id=1,
        event_id=1,
        title="Keynote",
        room="Main Hall",
        start=datetime(2026, 8, 27, 9, 0, tzinfo=UTC),
        end=datetime(2026, 8, 27, 10, 0, tzinfo=UTC),
        status="waiting_for_files",
    )

    mock_db.query.return_value.filter.return_value.first.return_value = mock_talk

    response = client.get("/talks/1", headers={"X-API-Key": "valid"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "Keynote"
    assert data["status"] == "waiting_for_files"
    assert data["preview_urls"] == []

    app.dependency_overrides.clear()


def test_get_talk_authorized_with_preview():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])
    fake_storage = FakeStorageBackend()
    fake_storage.put("1/preview/preview.mp4", b"fake preview bytes")

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_storage] = lambda: fake_storage

    mock_talk = models.Talk(
        id=1,
        event_id=1,
        title="Keynote",
        room="Main Hall",
        start=datetime(2026, 8, 27, 9, 0, tzinfo=UTC),
        end=datetime(2026, 8, 27, 10, 0, tzinfo=UTC),
        status="preview",
    )

    mock_db.query.return_value.filter.return_value.first.return_value = mock_talk

    response = client.get("/talks/1", headers={"X-API-Key": "valid"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["preview_urls"] == ["memory://1/preview/preview.mp4"]

    app.dependency_overrides.clear()


def test_get_talk_not_found():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = client.get("/talks/999", headers={"X-API-Key": "valid"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Talk not found"

    app.dependency_overrides.clear()


def test_get_talk_unauthorized_event_returns_404():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[2])  # Access to event 2 only

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_talk = models.Talk(
        id=1,
        event_id=1,  # Belongs to event 1
        title="Secret Keynote",
        start=datetime(2026, 8, 27, 9, 0, tzinfo=UTC),
        end=datetime(2026, 8, 27, 10, 0, tzinfo=UTC),
        status="waiting_for_files",
    )

    mock_db.query.return_value.filter.return_value.first.return_value = mock_talk

    # Must return 404 (not 403) to prevent leaking existence
    response = client.get("/talks/1", headers={"X-API-Key": "valid"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Talk not found"

    app.dependency_overrides.clear()


def test_create_talk_invalid_time_window():
    mock_client = models.Client(id=1, event_ids=[1])
    app.dependency_overrides[get_client] = lambda: mock_client

    payload = {
        "event_id": 1,
        "title": "Invalid Window Talk",
        "start": datetime(2026, 8, 27, 11, 0, tzinfo=UTC).isoformat(),
        "end": datetime(2026, 8, 27, 10, 0, tzinfo=UTC).isoformat(),  # End before start
    }

    response = client.post("/talks", json=payload, headers={"X-API-Key": "valid"})
    assert response.status_code == 422
    assert "Talk end time must be after start time" in response.text

    app.dependency_overrides.clear()
