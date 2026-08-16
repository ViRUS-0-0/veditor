from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app import models
from app.auth import get_client
from app.db import get_db
from app.main import app

client = TestClient(app)


# Mocking database session and the auth dependency
@patch("app.routes.ops.get_client")
def test_ops_talks_unauthorized(mock_get_client):
    # If no api key is provided, the dependency normally raises 401.
    # But since we are directly hitting the endpoint and overriding deps or not,
    # Let's test the endpoint without mocking get_client to see it returns 401
    response = client.get("/ops/talks")
    assert response.status_code == 401


def test_ops_talks_authorized():
    mock_db = MagicMock()

    mock_client = models.Client(id=1, event_ids=[1])

    # Mocking get_client dependency
    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    # Mock data
    mock_talk = models.Talk(
        id=1,
        event_id=1,
        title="Test Talk",
        room="Room 1",
        start=datetime.now(UTC),
        end=datetime.now(UTC),
        status="waiting_for_files",
    )

    mock_db.query.return_value.filter.return_value.all.return_value = [mock_talk]

    response = client.get("/ops/talks", headers={"X-API-Key": "valid"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 1
    assert data[0]["title"] == "Test Talk"

    app.dependency_overrides.clear()


def test_ops_get_talk_authorized():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_job = models.Job(
        id=1, talk_id=1, kind="transcode", status="pending", log_path=None
    )

    mock_talk = models.Talk(
        id=1,
        event_id=1,
        title="Test Talk",
        room="Room 1",
        start=datetime.now(UTC),
        end=datetime.now(UTC),
        status="waiting_for_files",
        jobs=[mock_job],
    )

    mock_db.query.return_value.filter.return_value.first.return_value = mock_talk

    response = client.get("/ops/talks/1", headers={"X-API-Key": "valid"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["id"] == 1

    app.dependency_overrides.clear()


def test_ops_get_talk_unauthorized_event():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[2])  # Has access to event 2

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_talk = models.Talk(
        id=1,
        event_id=1,  # Talk belongs to event 1
        title="Test Talk",
        start=datetime.now(UTC),
        end=datetime.now(UTC),
        status="waiting_for_files",
    )

    mock_db.query.return_value.filter.return_value.first.return_value = mock_talk

    response = client.get("/ops/talks/1", headers={"X-API-Key": "valid"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Client is not authorized to access this event"

    app.dependency_overrides.clear()


def test_ops_get_job_authorized():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[1])

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_talk = models.Talk(
        id=1,
        event_id=1,
        title="Test Talk",
        start=datetime.now(UTC),
        end=datetime.now(UTC),
        status="waiting_for_files",
    )

    mock_job = models.Job(
        id=1,
        talk_id=1,
        kind="transcode",
        status="pending",
        log_path=None,
        talk=mock_talk,
    )

    mock_db.query.return_value.filter.return_value.first.return_value = mock_job

    response = client.get("/ops/jobs/1", headers={"X-API-Key": "valid"})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["kind"] == "transcode"

    app.dependency_overrides.clear()


def test_ops_get_job_unauthorized_event():
    mock_db = MagicMock()
    mock_client = models.Client(id=1, event_ids=[2])  # Access to event 2

    app.dependency_overrides[get_client] = lambda: mock_client
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_talk = models.Talk(
        id=1,
        event_id=1,  # Talk belongs to event 1
        title="Test Talk",
        start=datetime.now(UTC),
        end=datetime.now(UTC),
        status="waiting_for_files",
    )

    mock_job = models.Job(
        id=1,
        talk_id=1,
        kind="transcode",
        status="pending",
        log_path=None,
        talk=mock_talk,
    )

    mock_db.query.return_value.filter.return_value.first.return_value = mock_job

    response = client.get("/ops/jobs/1", headers={"X-API-Key": "valid"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Client is not authorized to access this event"

    app.dependency_overrides.clear()
