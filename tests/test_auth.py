import pytest
from fastapi import HTTPException, status
from unittest.mock import MagicMock

from app.auth import hash_api_key, get_client, verify_event_access
from app.models import Client


def test_hash_api_key():
    key1 = "some-random-key"
    key2 = "some-random-key"
    key3 = "another-key"
    assert hash_api_key(key1) == hash_api_key(key2)
    assert hash_api_key(key1) != hash_api_key(key3)
    # Ensure it's 64 chars for SHA-256
    assert len(hash_api_key(key1)) == 64


def test_get_client_missing_key():
    with pytest.raises(HTTPException) as excinfo:
        get_client(None, MagicMock())
    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert excinfo.value.detail == "Missing API Key"


def test_get_client_invalid_key():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as excinfo:
        get_client("invalid-key", mock_db)

    assert excinfo.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert excinfo.value.detail == "Invalid API Key"


def test_get_client_valid_key():
    mock_client = Client(id=1, hashed_key="hashed", event_ids=[1, 2])
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_client

    client = get_client("valid-key", mock_db)
    assert client == mock_client


def test_verify_event_access_in_scope():
    mock_client = Client(id=1, event_ids=[1, 2, 3])
    # Should not raise any exception
    verify_event_access(2, mock_client)


def test_verify_event_access_out_of_scope():
    mock_client = Client(id=1, event_ids=[1, 2, 3])
    with pytest.raises(HTTPException) as excinfo:
        verify_event_access(4, mock_client)
    assert excinfo.value.status_code == status.HTTP_403_FORBIDDEN
    assert excinfo.value.detail == "Client is not authorized to access this event"
