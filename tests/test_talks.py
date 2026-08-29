from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app import models
from app.auth import get_client
from app.db import get_db
from app.main import app
from app.storage import get_storage_backend
from tests.conftest import FakeStorageBackend

client = TestClient(app)


def test_post_talks_unauthorized():
    response = client.post(
        "/talks",
        json={
            "event_id": 1,
            "title": "Introduction to FastAPI",
            "room": "Hall A",
            "start": datetime.now(UTC).isoformat(),
            "end": datetime.now(UTC).isoformat(),
        },
    )
    assert response.status_code == 401


def test_post_talks_forbidden_event():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[2])

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    response = client.post(
        "/talks",
        json={
            "event_id": 1,
            "title": "Introduction to FastAPI",
            "room": "Hall A",
            "start": datetime.now(UTC).isoformat(),
            "end": datetime.now(UTC).isoformat(),
        },
        headers={"X-API-Key": "valid_key"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Client is not authorized to access this event"

    app.dependency_overrides.clear()


def test_post_talks_create_success():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    # Simulate talk does not exist
    mock_db.query.return_value.filter.return_value.first.return_value = None

    start_time = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    end_time = datetime(2026, 9, 1, 11, 0, tzinfo=UTC)

    def fake_refresh(obj):
        obj.id = 42

    mock_db.refresh.side_effect = fake_refresh

    response = client.post(
        "/talks",
        json={
            "event_id": 1,
            "title": "Keynote Address",
            "room": "Main Stage",
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
        },
        headers={"X-API-Key": "valid_key"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 42
    assert data["event_id"] == 1
    assert data["title"] == "Keynote Address"
    assert data["room"] == "Main Stage"
    assert data["status"] == "waiting_for_files"
    assert data["preview_urls"] == []

    assert mock_db.add.called
    assert mock_db.commit.called

    app.dependency_overrides.clear()


def test_post_talks_upsert_update_success():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    start_time = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    initial_end = datetime(2026, 9, 1, 10, 45, tzinfo=UTC)
    updated_end = datetime(2026, 9, 1, 11, 0, tzinfo=UTC)

    existing_talk = models.Talk(
        id=10,
        event_id=1,
        title="Keynote Address",
        room="Old Room",
        start=start_time,
        end=initial_end,
        status="cutting",
    )

    mock_db.query.return_value.filter.return_value.first.return_value = existing_talk

    response = client.post(
        "/talks",
        json={
            "event_id": 1,
            "title": "Keynote Address",
            "room": "Updated Room",
            "start": start_time.isoformat(),
            "end": updated_end.isoformat(),
        },
        headers={"X-API-Key": "valid_key"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 10
    assert data["room"] == "Updated Room"
    assert data["status"] == "cutting"
    assert existing_talk.room == "Updated Room"
    assert existing_talk.end == updated_end
    assert existing_talk.status == "cutting"

    assert not mock_db.add.called
    assert mock_db.commit.called

    app.dependency_overrides.clear()


def test_post_talks_concurrent_race_handled():
    """Verify that a race condition on insert (IntegrityError) recovers and performs upsert."""
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    start_time = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    updated_end = datetime(2026, 9, 1, 11, 0, tzinfo=UTC)

    existing_talk = models.Talk(
        id=20,
        event_id=1,
        title="Concurrent Talk",
        room="Original Room",
        start=start_time,
        end=datetime(2026, 9, 1, 10, 30, tzinfo=UTC),
        status="waiting_for_files",
    )

    mock_db.query.return_value.filter.return_value.first.side_effect = [
        None,
        existing_talk,
    ]

    mock_db.commit.side_effect = [
        IntegrityError("duplicate key", params=None, orig=Exception("uq")),
        None,
    ]

    response = client.post(
        "/talks",
        json={
            "event_id": 1,
            "title": "Concurrent Talk",
            "room": "Updated Concurrent Room",
            "start": start_time.isoformat(),
            "end": updated_end.isoformat(),
        },
        headers={"X-API-Key": "valid_key"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 20
    assert data["room"] == "Updated Concurrent Room"
    assert existing_talk.room == "Updated Concurrent Room"
    assert existing_talk.end == updated_end
    assert mock_db.rollback.called

    app.dependency_overrides.clear()


def test_get_talk_unauthorized():
    response = client.get("/talks/1")
    assert response.status_code == 401


def test_get_talk_not_found():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = client.get("/talks/999", headers={"X-API-Key": "valid_key"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Talk not found"

    app.dependency_overrides.clear()


def test_get_talk_unauthorized_event_returns_404():
    """Talk in unowned event must return 404 (not 403) to avoid leaking existence."""
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[2])

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_talk = models.Talk(
        id=1,
        event_id=1,
        title="Secret Talk",
        room="Room X",
        start=datetime.now(UTC),
        end=datetime.now(UTC),
        status="waiting_for_files",
    )
    mock_db.query.return_value.filter.return_value.first.return_value = mock_talk

    response = client.get("/talks/1", headers={"X-API-Key": "valid_key"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Talk not found"

    app.dependency_overrides.clear()


def test_get_talk_authorized_without_previews():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])
    fake_storage = FakeStorageBackend()

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_storage_backend] = lambda: fake_storage

    mock_talk = models.Talk(
        id=5,
        event_id=1,
        title="Public Talk",
        room="Auditorium",
        start=datetime.now(UTC),
        end=datetime.now(UTC),
        status="waiting_for_files",
    )
    mock_db.query.return_value.filter.return_value.first.return_value = mock_talk

    response = client.get("/talks/5", headers={"X-API-Key": "valid_key"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 5
    assert data["title"] == "Public Talk"
    assert data["preview_urls"] == []

    app.dependency_overrides.clear()


def test_get_talk_authorized_with_previews():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])
    fake_storage = FakeStorageBackend()
    fake_storage.put("5/preview/small_video.mp4", b"dummy_small")
    fake_storage.put("5/preview/big_video.mp4", b"dummy_big")

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_storage_backend] = lambda: fake_storage

    mock_talk = models.Talk(
        id=5,
        event_id=1,
        title="Preview Ready Talk",
        room="Auditorium",
        start=datetime.now(UTC),
        end=datetime.now(UTC),
        status="preview",
    )
    mock_db.query.return_value.filter.return_value.first.return_value = mock_talk

    response = client.get("/talks/5", headers={"X-API-Key": "valid_key"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 5
    assert data["status"] == "preview"
    assert len(data["preview_urls"]) == 2
    assert "memory://5/preview/small_video.mp4" in data["preview_urls"]
    assert "memory://5/preview/big_video.mp4" in data["preview_urls"]

    app.dependency_overrides.clear()
